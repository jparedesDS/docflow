# -*- coding: utf-8 -*-
"""Volver a archivar una devolución que se descargó sin repartir.

    docflow_env\\Scripts\\python.exe tests\\test_rearchivo.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import dev_folders
from core.services import portal_downloads as P

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg)


CODE = "1000100070-T-0066"
DEV = Path(r"M:\pedidos\P-26-412\2-Tecnico\dev NDE\revC AP")

tmp = Path(tempfile.mkdtemp())
registro, archivar_real = P.PORTAL_DOWNLOADS_FILE, dev_folders.archive_return
try:
    P.PORTAL_DOWNLOADS_FILE = tmp / "portal_downloads.json"
    P._mark_done(CODE, {"pedido": "P-26/412", "zip": r"M:\pedidos\…\1000100070-T-0066.zip",
                        "folder": r"M:\pedidos\…\001 (18-09-2026)"})
    ok(not P.downloaded_info(CODE).get("dev_folders"),
       "la descarga que no colocó nada no apunta ninguna carpeta")

    # Al repartirlo, las carpetas quedan apuntadas: son las que el correo enlaza
    dev_folders.archive_return = lambda *a, **k: {
        "archived": [("3998_18-1000100070-00019.pdf", DEV / "3998_18-1000100070-00019.pdf")],
        "skipped": [], "created": [DEV], "plan": []}
    res = P._archivar(CODE, Path("paquete.zip"), [], "P-26/412")
    ok(res["dev_folders"] == [str(DEV)], f"carpeta del reparto: {res['dev_folders']}")
    ok(P.downloaded_info(CODE).get("dev_folders") == [str(DEV)],
       "y quedan en el registro, que es de donde las saca el correo")
    ok(P.download_status("eGesDoc <egesdoc@grupotr.es>",
                         "eGesdoc - New transmittal registered (1000100070-T-0066) - PO(1000100070)"
                         ).get("dev_folders") == [str(DEV)],
       "la lista de devoluciones también las ve")

    # Si el reparto falla, no se lleva por delante la descarga ni el registro
    def revienta(*a, **k):
        raise OSError("M: no está conectada")

    dev_folders.archive_return = revienta
    res = P._archivar("OTRO-0001", Path("paquete.zip"), [], "P-26/412")
    ok(res["dev_folders"] == [] and res["archive"]["skipped"],
       f"el fallo se cuenta como «sin colocar», no como excepción: {res}")
    ok(P.downloaded_info("OTRO-0001") is None, "y no se inventa un registro")
finally:
    dev_folders.archive_return = archivar_real
    P.PORTAL_DOWNLOADS_FILE = registro
    shutil.rmtree(tmp, ignore_errors=True)

# ── Lo que cada portal añade a los documentos del correo ────────────────────
docs = [{"Doc. EIPSA": "23-037-PRC-0006", "Rev.": "C"}]

mismos, ficheros = P._docs_y_ficheros({"portal": "prodoc", "code": "X", "po": "1"},
                                      docs, "asunto", b"")
ok(mismos is docs and ficheros == {},
   "un portal cuyos ficheros ya llevan el código no necesita mapa")

# Y si el portal no contesta, se archiva lo que se pueda en vez de fallar
guardado = P.egesdoc.transmittal_file_map
try:
    def no_contesta(*a, **k):
        raise TimeoutError("eGesDoc no responde")

    P.egesdoc.transmittal_file_map = no_contesta
    mismos, ficheros = P._docs_y_ficheros({"portal": "egesdoc", "code": "X", "po": "1"},
                                          docs, "asunto", b"")
    ok(mismos is docs and ficheros == {}, "sin mapa de ficheros, pero sin reventar")
finally:
    P.egesdoc.transmittal_file_map = guardado

# ── Devolución sin paquete: también deja rastro en la carpeta dev. ─────────
# Wood avisa de documentos «2I - FOR INFORMATION ONLY» sin enlace: no hay zip,
# pero el correo tiene que quedar en «00 TRANS Y RES» y en la carpeta dev.
VACIO = "TL-1234AB00A-VDC-6480"
tmp = Path(tempfile.mkdtemp())
registro, trans_root_real = P.PORTAL_DOWNLOADS_FILE, P.trans_root
archivar_real = dev_folders.archive_email_only
try:
    P.PORTAL_DOWNLOADS_FILE = tmp / "portal_downloads.json"
    trans = tmp / "00 TRANS Y RES"
    trans.mkdir()
    P.trans_root = lambda _pedido: trans
    DEVDIR = tmp / "2-Tecnico" / "dev. PMI PROCEDURE" / "rev0 AP"
    dev_folders.archive_email_only = lambda *a, **k: {
        "archived": [], "skipped": [], "created": [DEVDIR], "plan": [],
        "emails": [DEVDIR / "dev 2026-09-24.eml"]}

    res = P.save_email_only(VACIO, "P-26/004", subject="Wood Transmittal", raw_email=b"correo",
                            portal="prodoc", po="7000100010", motivo="sin enlace",
                            docs=[{"Título": "PMI PROCEDURE"}], fecha="2026-09-24")
    ok(res["folder"].is_dir() and res["eml"] and res["eml"].is_file(),
       f"el correo se archiva en su carpeta del pedido: {res['folder'].name}")
    ok(res["dev_folders"] == [str(DEVDIR)], f"y en la carpeta dev.: {res['dev_folders']}")
    ok(P.nothing_info(VACIO).get("dev_folders") == [str(DEVDIR)],
       "queda apuntado en el registro, que es de donde lo lee la ventana")
    ok(P.download_status("Prodoc.postmaster@woodgroup.com",
                         f"Wood Transmittal {VACIO} - algo").get("dev_folders") == [str(DEVDIR)],
       "y la lista de devoluciones también lo ve")

    # Repetirlo no vuelve a archivar ni crea otra carpeta «NNN (fecha)»
    carpetas = sorted(p.name for p in trans.iterdir())
    otra = P.save_email_only(VACIO, "P-26/004", subject="Wood Transmittal", raw_email=b"correo",
                             portal="prodoc", po="7000100010", motivo="sin enlace",
                             docs=[{"Título": "PMI PROCEDURE"}], fecha="2026-09-24")
    ok(otra["already"] and sorted(p.name for p in trans.iterdir()) == carpetas,
       "la segunda vez se reutiliza lo que ya había")

    # Si colocar el correo falla, la devolución sigue archivada igual
    def revienta(*a, **k):
        raise OSError("M: no está conectada")

    dev_folders.archive_email_only = revienta
    res = P.save_email_only("OTRO-VACIO", "P-26/004", subject="x", raw_email=b"c",
                            portal="prodoc", po="1", motivo="sin enlace",
                            docs=[{"Título": "X"}], fecha="2026-09-24")
    ok(res["dev_folders"] == [] and res["archive"]["skipped"],
       f"el fallo se cuenta como «sin colocar», no como excepción: {res['archive']['skipped']}")
    ok(res["eml"] is not None and res["eml"].is_file(),
       "y el correo se queda guardado igual")
finally:
    dev_folders.archive_email_only = archivar_real
    P.trans_root = trans_root_real
    P.PORTAL_DOWNLOADS_FILE = registro
    shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
