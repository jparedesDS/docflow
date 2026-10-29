# -*- coding: utf-8 -*-
"""Carpetas de devolución con las dos revisiones: «rev 2-C COM» = nuestra
revisión 2, que el cliente llama C.

· Nuestra revisión se CUENTA: la primera devolución de un documento es la 0 y
  cada revisión suya ya archivada suma una. El ERP no sirve (se rellena a mano
  y se salta revisiones o empieza en la 1).
· La del cliente es la del transmittal («TR Rev» en TR), escriba como escriba.
· Si el cliente devuelve otra vez una revisión que ya está archivada, es esa
  misma: va al lado con la fecha.
· Si esa revisión ya tiene carpeta (también al estilo antiguo) se sigue usando.

Datos inventados (pedido P-99/001).

    .venv\\Scripts\\python.exe tests\\test_revisiones.py
"""
import shutil
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import dev_folders as D  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


ok(D.fecha_de("19-10-2099 09:22:06") == date(2099, 10, 19) and D.fecha_de("2099-10-19") == date(2099, 10, 19)
   and D.fecha_de("") is None, "fechas del correo")

# ── La del cliente ───────────────────────────────────────────────────────────
ok(D.revision_cliente({"Rev.": "1", "_rev_cliente": "B"}) == "B", "TR: la de su columna, no la «Vendor Rev»")
ok(D.revision_cliente({"Rev.": "R00 (AF)"}) == "0", "«R00 (AF)» → 0")
ok(D.revision_cliente({"Rev.": "01"}) == "1" and D.revision_cliente({"Rev.": "Rev. C"}) == "C",
   "sin ceros ni «Rev.»")
ok(D.nombre_rev("2", "C") == "rev 2-C" and D.nombre_rev("0", "0") == "rev 0-0", "el nombre: «rev 2-C»")

# ── ¿Esta carpeta es de esa pareja? ──────────────────────────────────────────
ok(D._es_de_la_revision(1, "B", "1", "B"), "«rev1-B com» (antigua, sin espacio) es la 1-B")
ok(not D._es_de_la_revision(1, "B", "1", "C"), "pero no la 1-C")
ok(D._es_de_la_revision(0, "", "0", "0"), "«rev0 com» vale si las dos son 0")
ok(not D._es_de_la_revision(0, "", "1", "0"), "y no si la nuestra es otra")

# ── Archivando ───────────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="revisiones_"))
tecnico = tmp / "P-99-001-S00 - CLIENTE - CAUDAL" / "2-Tecnico"
(tecnico / "env. Cálculos").mkdir(parents=True)
(tecnico / "dev. Cálculos").mkdir()
dev = tecnico / "dev. Cálculos"
tecnico_real = D.tecnico_dir
D.tecnico_dir = lambda _pedido: tecnico


def doc(n, rev, estado, rev_tr=""):
    return {"Nº Pedido": "P-99/001", "Supp.": "S00", "Doc. EIPSA": f"99-001-CAL-{n:04d}",
            "Doc. Cliente": f"CLI-CAL-{n:04d}", "Título": "CALCULO DE PRUEBA",
            "Tipo de documento": "Cálculos", "Rev.": rev, "_rev_cliente": rev_tr, "Estado": estado}


def archivar(docs, contenido=b"%PDF", fecha="10-10-2099 09:00:00", nombre=None):
    paquete = tmp / "paquete.zip"
    with zipfile.ZipFile(paquete, "w") as zf:
        for d in docs:
            zf.writestr(nombre or f"{d['Doc. Cliente']}.pdf", contenido + d["Doc. Cliente"].encode())
    return D.archive_return(paquete, docs, "P-99/001", email_raw=b"correo", email_date=fecha)


def donde(res):
    return {Path(f).stem: str(Path(dest).parent.relative_to(dev)) for f, dest in res["archived"]}


try:
    # Primera devolución: nuestra 0, el cliente la llama A
    r = archivar([doc(1, "A", "Com. Mayores")])
    ok(donde(r) == {"CLI-CAL-0001": "rev 0-A COM"}, f"la primera es la 0: {donde(r)}")
    ok((dev / "rev 0-A COM" / "dev 10-10-2099.eml").exists(), "con su correo")

    # Volver a archivarlo: el mismo sitio, nada nuevo, y no cuenta como anterior
    antes = sorted(p.name for p in dev.iterdir())
    r = archivar([doc(1, "A", "Com. Mayores")])
    ok(sorted(p.name for p in dev.iterdir()) == antes and not r["created"]
       and donde(r) == {"CLI-CAL-0001": "rev 0-A COM"}, f"volver a archivar no cambia nada: {donde(r)}")

    # Segunda devolución (el cliente la llama B): nuestra 1
    r = archivar([doc(1, "B", "Com. Menores")], contenido=b"%PDF-B", fecha="20-10-2099 09:00:00")
    ok(donde(r) == {"CLI-CAL-0001": "rev 1-B com"}, f"la siguiente suma una: {donde(r)}")

    # El cliente devuelve OTRA VEZ la B, con otro PDF: es la misma revisión,
    # no suma; y como ya hay un PDF así, va al lado con la fecha
    r = archivar([doc(1, "B", "Com. Menores")], contenido=b"%PDF-B2", fecha="22-10-2099 09:00:00")
    ok(donde(r) == {"CLI-CAL-0001": "rev 1-B com 22-10-2099"}, f"la misma B otra vez: {donde(r)}")
    ok((dev / "rev 1-B com" / "CLI-CAL-0001.pdf").read_bytes().startswith(b"%PDF-B"),
       "lo archivado antes no se toca")

    # Y la siguiente (C) es la 2, no la 3: la B repetida no cuenta dos veces
    r = archivar([doc(1, "C", "Aprobado")], contenido=b"%PDF-C", fecha="01-11-2099 09:00:00")
    ok(donde(r) == {"CLI-CAL-0001": "rev 2-C AP"}, f"la C es la 2: {donde(r)}")

    # Un cliente que empieza en la 1: su primera devolución es nuestra 0
    r = archivar([doc(2, "1", "Com. Menores")])
    ok(donde(r) == {"CLI-CAL-0002": "rev 0-1 com"}, f"empieza en la 1, para nosotros es la 0: {donde(r)}")
    # …y pasa a la 2 (se salta la 1 al renumerar): nuestra 1, sin huecos
    r = archivar([doc(2, "3", "Aprobado")], contenido=b"%PDF-3", fecha="20-10-2099 09:00:00")
    ok(donde(r) == {"CLI-CAL-0002": "rev 1-3 AP"}, f"aunque el cliente salte, la nuestra no: {donde(r)}")

    # Coinciden (0 y 0): las dos igual
    r = archivar([doc(3, "0", "Aprobado")])
    ok(donde(r) == {"CLI-CAL-0003": "rev 0-0 AP"}, f"coinciden: «rev 0-0 AP»: {donde(r)}")

    # Esa revisión ya tiene carpeta antigua repartida por resolución: se sigue usando
    (dev / "rev0 com" / "com. menores").mkdir(parents=True)
    r = archivar([doc(4, "0", "Com. Menores")])
    ok(donde(r) == {"CLI-CAL-0004": "rev0 com\\com. menores"}, f"sigue en la antigua: {donde(r)}")
    # Y volver a archivarlo lo reconoce DENTRO de la subcarpeta: no abre la 1
    r = archivar([doc(4, "0", "Com. Menores")])
    ok(donde(r) == {"CLI-CAL-0004": "rev0 com\\com. menores"} and not r["created"],
       f"lo ya archivado en una subcarpeta no cuenta como anterior: {donde(r)} {r['created']}")

    # Un código que contiene a otro (CLI-CAL-0010 lleva dentro CLI-CAL-001…) no
    # es el mismo documento: el CLI-CAL-0001 tiene sus tres revisiones, el 10 ninguna
    r = archivar([doc(10, "A", "Com. Menores")])
    ok(donde(r) == {"CLI-CAL-0010": "rev 0-A com"}, f"el 10 empieza en la 0: {donde(r)}")

    # Lo anulado (VOID) no es una revisión: no suma
    r = archivar([doc(5, "A", "Aprobado")])
    r = archivar([doc(5, "A", "M - VOID")], contenido=b"%PDF-void", fecha="13-10-2099 09:00:00")
    ok(list(donde(r).values())[0] == "rev 0-A AP\\VOID", f"VOID dentro de la que cancela: {donde(r)}")
    r = archivar([doc(5, "B", "Aprobado")], contenido=b"%PDF-B", fecha="20-10-2099 09:00:00")
    ok(donde(r) == {"CLI-CAL-0005": "rev 1-B AP"}, f"el VOID no cuenta: la B es la 1: {donde(r)}")

    # Varias resoluciones de la misma pareja en un paquete: una subcarpeta cada una
    r = archivar([doc(7, "A", "Com. Menores"), doc(8, "A", "Com. Mayores")])
    ok(donde(r) == {"CLI-CAL-0007": "rev 0-A\\com. menores", "CLI-CAL-0008": "rev 0-A\\com. mayores"},
       f"mezcladas, por subcarpeta: {donde(r)}")

    # Lo devuelto antes a mano en carpetas con otro nombre también cuenta
    (dev / "rev0 com").mkdir(exist_ok=True)
    (dev / "rev0 com" / "CLI-CAL-0009 comentado.pdf").write_bytes(b"%PDF a mano")
    (dev / "rev1 AP").mkdir()
    (dev / "rev1 AP" / "CLI-CAL-0009_R1.pdf").write_bytes(b"%PDF a mano 2")
    r = archivar([doc(9, "C", "Com. Menores")])
    ok(donde(r) == {"CLI-CAL-0009": "rev 2-C com"}, f"dos anteriores a mano: la 2: {donde(r)}")

    # Si falta una (la 1 fue una anulación sin carpeta de devolución), manda el
    # número de la última: 0-A, 2-B, 3-C → la D es la 4, no la 3 (26-031-ESP-0003)
    for nombre, letra in (("rev0-A COM", "A"), ("rev2-B COM", "B"), ("rev3-C com", "C")):
        (dev / nombre).mkdir()
        (dev / nombre / "CLI-CAL-0011.pdf").write_bytes(b"%PDF " + letra.encode())
    r = archivar([doc(11, "D", "Aprobado")], contenido=b"%PDF-D")
    # La 4; y escrita como la última que se hizo en esta carpeta («rev3-C com», sin espacio)
    ok(donde(r) == {"CLI-CAL-0011": "rev4-D AP"}, f"la última más uno: {donde(r)}")
finally:
    D.tecnico_dir = tecnico_real
    shutil.rmtree(tmp, ignore_errors=True)

# ── El formato y la carpeta de las devoluciones anteriores ───────────────────
# 1043010640-T-0047: la de envío es «env MANUFACTURIG RECORD BOOK» (errata) y
# las devoluciones están en «dev MANUFACTURING RECORD BOOK», escritas «rev5-4
# com». Se abrió una «dev MANUFACTURIG…» nueva con «rev 6-5 AP».
tmp = Path(tempfile.mkdtemp(prefix="revisiones_"))
tecnico = tmp / "P-99-002 - S00 - CLIENTE - TEMPERATURA" / "2-Tecnico"
envio = tecnico / "env MANUFACTURIG RECORD BOOK" / "rev6"
envio.mkdir(parents=True)
(envio / "CLI-DOS-0002.pdf").write_bytes(b"enviado")
buena = tecnico / "dev MANUFACTURING RECORD BOOK"
for nombre in ("rev0-B com", "rev1-0 AP", "rev2-50 com", "rev3-2 com", "rev4-3 com", "rev5-4 com"):
    (buena / nombre).mkdir(parents=True)
    (buena / nombre / "CLI-DOS-0002.pdf").write_bytes(b"%PDF " + nombre.encode())
D.tecnico_dir = lambda _pedido: tecnico
try:
    dossier = {"Nº Pedido": "P-99/002", "Supp.": "S00", "Doc. EIPSA": "99-002-DOS-0002",
               "Doc. Cliente": "CLI-DOS-0002", "Título": "MANUFACTURING RECORDS BOOK",
               "Tipo de documento": "Dossier", "Rev.": "5", "_rev_cliente": "5", "Estado": "Aprobado"}
    paquete = tmp / "T-0047.zip"
    with zipfile.ZipFile(paquete, "w") as zf:
        zf.writestr("CLI-DOS-0002.pdf", b"%PDF-septima")
    r = D.archive_return(paquete, [dossier], "P-99/002", email_date="29-10-2099 12:00:00")
    destino = Path(r["archived"][0][1])
    ok(destino.parent.parent == buena, f"a la carpeta con sus devoluciones: {destino.parent.parent.name}")
    ok(not (tecnico / "dev MANUFACTURIG RECORD BOOK").exists(), "sin abrir la de la errata")
    ok(destino.parent.name == "rev6-5 AP", f"con el formato de las anteriores, sin espacio: {destino.parent.name}")
    ok(D._estilo_rev(buena) == ("rev", ""), f"estilo de la carpeta: {D._estilo_rev(buena)}")
    ok(D._estilo_rev(tmp / "vacia") == ("rev", " "), "una carpeta sin revisiones: «rev » con espacio")
    (tmp / "mayus" / "REV 3 AP").mkdir(parents=True)
    ok(D._estilo_rev(tmp / "mayus") == ("REV", " "), "y «REV 3» se copia en mayúsculas")
finally:
    D.tecnico_dir = tecnico_real
    shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
