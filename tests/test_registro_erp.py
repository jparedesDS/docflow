# -*- coding: utf-8 -*-
"""«Pendiente en el ERP»: cada devolución archivada se apunta con lo que hay que
poner en el ERP (estado con su nombre del ERP, fecha del correo y NUESTRA
revisión, la de la carpeta), y sale de la lista cuando el ERP ya cuadra. La
revisión del cliente (A, 0, B…) no se compara con nada.

Datos inventados (pedidos P-99/…): nada de clientes reales.

    .venv\\Scripts\\python.exe tests\\test_registro_erp.py
"""
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import dev_folders as D  # noqa: E402
from core.services import registro_erp as R  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


tmp = Path(tempfile.mkdtemp(prefix="registro_erp_"))
R.REGISTRO_FILE = str(tmp / "registro_erp.json")

# ── Estado del ERP ────────────────────────────────────────────────────────────
for portal, erp in [("Aprobado", "Aprobado"), ("Com. Menores", "Com. Menores"),
                    ("Com. Mayores", "Com. Mayores"), ("Comentado", "Comentado"),
                    ("Rechazado", "Rechazado"), ("Informativo", "Información"), ("VOID", "Eliminado"),
                    ("M - VOID", "Eliminado"), ("Comentarios mayores", "Com. Mayores")]:
    ok(R.estado_erp(portal) == erp, f"{portal!r} → {R.estado_erp(portal)!r}, no {erp!r}")

# ── Al archivar se apunta, con NUESTRA revisión ──────────────────────────────
tecnico_real = D.tecnico_dir
try:
    tecnico = tmp / "P-99-004-S00 - CLIENTE" / "2-Tecnico"
    dev = tecnico / "dev. Planos"
    (dev / "rev 0-A com").mkdir(parents=True)                  # la primera devolución ya archivada
    (dev / "rev 0-A com" / "CLI-DWG-0001-A.PDF").write_bytes(b"%PDF-vieja")
    (tecnico / "env. Planos").mkdir()
    D.tecnico_dir = lambda _pedido: tecnico

    # El cliente numera con letras: devuelve su «B», que es nuestra 1
    PLANO = {"Nº Pedido": "P-99/004", "Supp.": "S00", "Doc. EIPSA": "99-004-PLG-0005",
             "Doc. Cliente": "CLI-DWG-0001", "Título": "GENERAL ARRANGEMENT",
             "Tipo de documento": "Planos", "Rev.": "B", "Estado": "Aprobado"}
    paquete = tmp / "dev.zip"
    with zipfile.ZipFile(paquete, "w") as zf:
        zf.writestr("CLI-DWG-0001-B.PDF", b"%PDF-plano-B")
        zf.writestr("CLI-DWG-0001-B (otra hoja).PDF", b"%PDF-plano-B2")
    res = D.archive_return(paquete, [PLANO], "P-99/004", email_date="2099-03-10 09:20:00")
    ok(len(res["archived"]) == 2, f"se archiva: {res}")
    dv = res.get("devueltos") or []
    ok(len(dv) == 1, f"un apunte por documento aunque traiga dos ficheros: {dv}")
    ok(dv and dv[0]["nuestra"] == "1" and dv[0]["cliente"] == "B",
       f"nuestra 1 (la siguiente a la archivada), del cliente B: {dv}")
    ok(dv and dv[0]["pedido"] == "P-99/004-S00", f"con el suministro: {dv}")
    ok(R.anotar(res, "2099-03-10 09:20:00") == 1, "se apunta")
    ok(R.anotar(res, "2099-03-10 09:20:00") == 0, "rearchivar no lo apunta dos veces")

    # Sin paquete (solo el correo) también
    INFO = dict(PLANO, **{"Doc. EIPSA": "99-004-ESP-0003", "Doc. Cliente": "CLI-SPC-0002",
                          "Título": "DATA SHEET", "Rev.": "0", "Estado": "Informativo"})
    res2 = D.archive_email_only([INFO], "P-99/004", email_raw=b"correo", email_date="2099-03-11")
    ok(R.anotar(res2, "2099-03-11") == 1 and res2["devueltos"][0]["nuestra"] == "0",
       f"la devolución sin paquete también: {res2.get('devueltos')}")
    # Un simulacro no apunta nada
    ok(not D.archive_return(paquete, [PLANO], "P-99/004", dry_run=True).get("devueltos"),
       "dry_run no apunta")
finally:
    D.tecnico_dir = tecnico_real

# ── Contra el ERP ─────────────────────────────────────────────────────────────
res = R.pendientes(erp=None)
ok(not res["ok"] and res["filas"] == [], "sin ERP no se puede decir nada")

# El ERP aún dice «Enviado» rev 1, y el de información no está
ERP = {"99-004-PLG-0005": {"num_doc_eipsa": "99-004-PLG-0005", "state": "Enviado", "revision": 1,
                           "state_date": "01/03/2099"}}
res = R.pendientes(erp=ERP)
por = {f["doc_eipsa"]: f for f in res["filas"]}
ok(res["ok"] and set(por) == {"99-004-PLG-0005", "99-004-ESP-0003"}, f"las dos pendientes: {list(por)}")
p = por.get("99-004-PLG-0005", {})
ok(p.get("estado") == "Aprobado" and p.get("fecha") == "10/03/2099" and p.get("nuestra") == "1",
   f"lo que hay que poner: {p}")
ok(p.get("falta") == ["estado", "fecha"], f"la revisión ya cuadra; faltan estado y fecha: {p.get('falta')}")
ok(por.get("99-004-ESP-0003", {}).get("falta") == ["documento"], "el que no está en el ERP se dice")

# Ya puesto, con la fecha del día que se apuntó (dos días después): cuadra
ERP["99-004-PLG-0005"].update(state="Aprobado", state_date="12/03/2099")
ok("99-004-PLG-0005" not in {f["doc_eipsa"] for f in R.pendientes(erp=ERP)["filas"]},
   "con estado, revisión y fecha razonable sale de la lista")
# La revisión del ERP no es la nuestra: no cuadra aunque el estado sí
ERP["99-004-PLG-0005"].update(revision=2)
f = next((x for x in R.pendientes(erp=ERP)["filas"] if x["doc_eipsa"] == "99-004-PLG-0005"), None)
ok(f is None, "si el ERP ya va por una revisión nuestra posterior (se reenvió), esto es historia")
ERP["99-004-PLG-0005"].update(revision=0)
f = next((x for x in R.pendientes(erp=ERP)["filas"] if x["doc_eipsa"] == "99-004-PLG-0005"), None)
ok(f and f["falta"] == ["revision"], f"revisión anterior en el ERP: falta la revisión: {f}")

# Se busca también por el Nº del cliente (con espacios en el ERP)
ERP2 = {"CLI:CLI-SPC-0002": {"num_doc_client": "CLI-SPC- 0002", "state": "Información", "revision": 0,
                             "state_date": "11/03/2099"}}
ok(R.comparar(next(e for e in R._cargar()["devueltos"].values() if e["doc_cliente"] == "CLI-SPC-0002"),
              ERP2["CLI:CLI-SPC-0002"]) is None, "cuadra el que se encuentra por el Nº del cliente")

# Grupos para pegar de una vez y ocultar
filas = R.pendientes(erp={})["filas"]
ok(all("documento" in x["falta"] for x in filas) and R.grupos(filas) == [], "sin ERP para ellos: sin grupos")
filas = R.pendientes(erp={k: dict(v, state="Enviado") for k, v in ERP.items()})["filas"]
g = R.grupos([x for x in filas if "documento" not in x["falta"]])
ok(g and g[0]["estado"] == "Aprobado" and g[0]["fecha"] == "10/03/2099", f"grupo por estado y fecha: {g}")
xlsx = R.exportar_excel(filas, tmp / "pendiente.xlsx")
from openpyxl import load_workbook  # noqa: E402
ws = load_workbook(xlsx).active
ok(ws["A1"].value == "num_doc_eipsa" and ws["D2"].value == "Aprobado" and ws["F2"].value == 1,
   f"Excel: {[c.value for c in ws[2]]}")
clave = next(x["clave"] for x in filas if x["doc_eipsa"] == "99-004-PLG-0005")
R.ignorar(clave)
ok(all(x["doc_eipsa"] != "99-004-PLG-0005" for x in R.pendientes(erp={})["filas"]), "la ocultada no vuelve")

# ── La ventana ────────────────────────────────────────────────────────────────
import customtkinter as ctk  # noqa: E402

from gui.views.devoluciones import pendiente_erp as V  # noqa: E402

R.pendientes = lambda: {"ok": True, "motivo": "", "total": 1, "filas": [
    {"clave": "k", "pedido": "P-99/004-S00", "doc_eipsa": "99-004-PLG-0006", "doc_cliente": "", "titulo": "X",
     "nuestra": "2", "cliente": "C", "estado": "Com. Menores", "fecha": "10/03/2099", "carpeta": "",
     "falta": ["estado"], "erp": {"estado": "Enviado", "revision": 2, "fecha": "01/03/2099"}}]}
root = ctk.CTk()
root.withdraw()
# Carga en un hilo y pinta con ui.en_ui: hace falta el bucle de Tk
w = None


def abrir():
    global w
    w = V.PendienteErpWindow(root)
    esperar(0)


def esperar(n):
    if w._filas or n > 100:
        root.quit()
    else:
        root.after(30, lambda: esperar(n + 1))


root.after(10, abrir)
root.mainloop()
ok(len(w._filas) == 1, "la ventana enseña la pendiente")
c = V.celdas(w._filas[0])
ok(c["Rev"]["text"] == "2  (cli C)" and c["ERP"]["text"] == "Enviado · rev 2 · 01/03/2099"
   and c["Estado"]["bold"], f"celdas: {c}")
ok("1 por registrar" in w.lbl_estado.cget("text"), f"resumen: {w.lbl_estado.cget('text')}")
root.destroy()
shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
