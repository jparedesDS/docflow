# -*- coding: utf-8 -*-
"""Carpetas de devolución con las dos revisiones: «rev 2-C COM» = nuestra
revisión 2 (del ERP), que el cliente llama C.

· Nuestra revisión: el último «Enviado Rev. N» del historial del ERP hasta el
  día de la devolución. La del cliente: la del transmittal («TR Rev» en TR).
· Si esa revisión ya tiene carpeta (también al estilo antiguo) se sigue usando.
· La misma pareja otra vez con otro PDF: al lado, con la fecha.
· Sin nuestra revisión en el ERP: como antes, y se avisa.

Datos inventados (pedido P-99/001, ERP simulado).

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


# ── Nuestra revisión, del historial del ERP ──────────────────────────────────
H = "15/10/2099 Enviado Rev. 1 // 08/10/2099 Com. Menores Rev. 0 // 11/09/2099 Enviado Rev. 0"
ok(D.revision_del_historial(H, date(2099, 10, 8)) == "0", "devuelta el 08/10: lo enviado el 11/09, rev 0")
ok(D.revision_del_historial(H, date(2099, 10, 16)) == "1", "devuelta el 16/10: la rev 1 del 15/10")
ok(D.revision_del_historial(H, date(2099, 9, 1)) is None, "antes de ningún envío: no se sabe")
ok(D.revision_del_historial("10/10/2099 Enviado Rev. 3 // 10/10/2099 Enviado Rev. 2",
                            date(2099, 10, 10)) == "3", "dos envíos el mismo día: el más nuevo (va primero)")
ok(D.revision_del_historial("12-01-2099 Aprobado Rev. 3 // 12-01-2099 Enviado Rev. 03", date(2099, 2, 1)) == "3",
   "también con guiones, y sin ceros delante")
ok(D.revision_del_historial("10/09/2099 Com. Menores Rev.  // 22/07/2099 Enviado Rev. ", date(2099, 10, 1)) is None,
   "sin número de revisión no vale")
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
ok(not D._es_de_la_revision(0, "", "1", "0"), "y no si la nuestra es otra: ese 0 era la del cliente")
ok(not D._es_de_la_revision(1, "", "1", "0"), "ni al revés: no hay forma de saber qué número era")

# ── Archivando ───────────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="revisiones_"))
tecnico = tmp / "P-99-001-S00 - CLIENTE - CAUDAL" / "2-Tecnico"
(tecnico / "env. Cálculos").mkdir(parents=True)
(tecnico / "dev. Cálculos").mkdir()
dev = tecnico / "dev. Cálculos"
tecnico_real = D.tecnico_dir
D.tecnico_dir = lambda _pedido: tecnico

ERP = {}
D._docs_erp = lambda: [{"Nº Doc. EIPSA": c, "Historial Rev.": h} for c, h in ERP.items()]


def doc(n, rev, estado, rev_tr=""):
    return {"Nº Pedido": "P-99/001", "Supp.": "S00", "Doc. EIPSA": f"99-001-CAL-{n:04d}",
            "Doc. Cliente": f"CLI-CAL-{n:04d}", "Título": "CALCULO DE PRUEBA",
            "Tipo de documento": "Cálculos", "Rev.": rev, "_rev_cliente": rev_tr, "Estado": estado}


def archivar(docs, contenido=b"%PDF", fecha="10-10-2099 09:00:00", dry=False):
    paquete = tmp / "paquete.zip"
    with zipfile.ZipFile(paquete, "w") as zf:
        for d in docs:
            zf.writestr(f"{d['Doc. EIPSA']}.pdf", contenido + d["Doc. EIPSA"].encode())
    return D.archive_return(paquete, docs, "P-99/001", email_raw=b"correo", email_date=fecha, dry_run=dry)


def donde(res):
    return {Path(f).stem: str(Path(dest).parent.relative_to(dev)) for f, dest in res["archived"]}


try:
    # Nuestra 2, cliente C, comentarios mayores
    ERP["99-001-CAL-0001"] = "05/10/2099 Enviado Rev. 2 // 01/09/2099 Com. Menores Rev. 1 // 01/08/2099 Enviado Rev. 1"
    r = archivar([doc(1, "C", "Com. Mayores")])
    ok(donde(r) == {"99-001-CAL-0001": "rev 2-C COM"}, f"nuestra primero, la del cliente detrás: {donde(r)}")
    ok(not r["sin_rev_nuestra"] and (dev / "rev 2-C COM" / "dev 10-10-2099.eml").exists(), "con su correo")

    # Volver a archivarlo: el mismo sitio, nada nuevo
    antes = sorted(p.name for p in dev.iterdir())
    r = archivar([doc(1, "C", "Com. Mayores")])
    ok(sorted(p.name for p in dev.iterdir()) == antes and not r["created"], "volver a archivar no cambia nada")

    # Otra vez la misma pareja con un PDF distinto: al lado, con la fecha
    r = archivar([doc(1, "C", "Com. Mayores")], contenido=b"%PDF-otro", fecha="12-10-2099 10:00:00")
    ok(donde(r) == {"99-001-CAL-0001": "rev 2-C COM 12-10-2099"}, f"repetida, con la fecha: {donde(r)}")
    ok((dev / "rev 2-C COM" / "99-001-CAL-0001.pdf").read_bytes().startswith(b"%PDF99"),
       "lo archivado antes no se toca")
    r = archivar([doc(1, "C", "Com. Mayores")], contenido=b"%PDF-tercero", fecha="12-10-2099 16:00:00")
    ok(donde(r) == {"99-001-CAL-0001": "rev 2-C COM 12-10-2099 (2)"}, f"y otra el mismo día: {donde(r)}")

    # Coinciden (0 y 0) y no hay carpeta: «rev 0-0 AP», las dos siempre
    ERP["99-001-CAL-0002"] = "01/10/2099 Enviado Rev. 0"
    r = archivar([doc(2, "0", "Aprobado")])
    ok(donde(r) == {"99-001-CAL-0002": "rev 0-0 AP"}, f"coinciden: las dos igual: {donde(r)}")

    # Esa revisión ya tiene carpeta antigua repartida por resolución: se sigue usando
    (dev / "rev0 com" / "com. menores").mkdir(parents=True)
    ERP["99-001-CAL-0003"] = "01/10/2099 Enviado Rev. 0"
    r = archivar([doc(3, "0", "Com. Menores")])
    ok(donde(r) == {"99-001-CAL-0003": "rev0 com\\com. menores"}, f"sigue en la antigua: {donde(r)}")

    # Antigua con guion («rev1-B com»): la misma pareja, se sigue usando
    (dev / "rev1-B com").mkdir()
    ERP["99-001-CAL-0004"] = "01/10/2099 Enviado Rev. 1"
    r = archivar([doc(4, "1", "Com. Menores", rev_tr="B")])
    ok(donde(r) == {"99-001-CAL-0004": "rev1-B com"}, f"«rev1-B com» es la 1-B: {donde(r)}")

    # Un «rev0 com» antiguo NO es de la nuestra 1 aunque el cliente diga 0
    ERP["99-001-CAL-0005"] = "01/10/2099 Enviado Rev. 1"
    r = archivar([doc(5, "0", "Com. Menores")])
    ok(donde(r) == {"99-001-CAL-0005": "rev 1-0 com"}, f"nuestra 1, cliente 0: carpeta nueva: {donde(r)}")

    # TR: la «Vendor Rev» (4) no manda; la nuestra es la del ERP (3)
    ERP["99-001-CAL-0006"] = "22/09/2099 Aprobado Rev. 3 // 01/09/2099 Enviado Rev. 3"
    r = archivar([doc(6, "4", "Aprobado", rev_tr="4")])
    ok(donde(r) == {"99-001-CAL-0006": "rev 3-4 AP"}, f"TR: nuestra 3, TR 4: {donde(r)}")

    # Varias resoluciones de la misma pareja en un paquete: una subcarpeta cada una
    for n in (7, 8):
        ERP[f"99-001-CAL-{n:04d}"] = "01/10/2099 Enviado Rev. 3"
    r = archivar([doc(7, "D", "Com. Menores"), doc(8, "D", "Com. Mayores")])
    ok(donde(r) == {"99-001-CAL-0007": "rev 3-D\\com. menores", "99-001-CAL-0008": "rev 3-D\\com. mayores"},
       f"mezcladas, por subcarpeta: {donde(r)}")

    # Un anulado va dentro de la revisión que cancela
    r = archivar([doc(1, "C", "M - VOID")], contenido=b"%PDF-void", fecha="13-10-2099 09:00:00")
    ok(list(donde(r).values())[0].endswith("VOID") and list(donde(r).values())[0].startswith("rev 2-C COM"),
       f"VOID dentro de la 2-C: {donde(r)}")

    # Sin nuestra revisión en el ERP: como antes, y se avisa
    r = archivar([doc(9, "1", "Aprobado")])
    ok(r["sin_rev_nuestra"] == ["99-001-CAL-0009.pdf"] and len(r["archived"]) == 1,
       f"sin ERP: se archiva igual y se avisa: {r['sin_rev_nuestra']} {donde(r)}")
    ok(not donde(r)["99-001-CAL-0009"].startswith("rev 1-"), f"con la regla de antes: {donde(r)}")
    ok("sin nuestra revisión en el ERP" in D.summary_line(r), f"el resumen lo dice: {D.summary_line(r)}")
finally:
    D.tecnico_dir = tecnico_real
    shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
