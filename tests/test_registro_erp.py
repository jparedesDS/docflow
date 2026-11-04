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
    # capturar=False: sin ir al ERP de verdad (el 1er envío se prueba más abajo con uno falso)
    ok(R.anotar(res, "2099-03-10 09:20:00", capturar=False) == 1, "se apunta")
    ok(R.anotar(res, "2099-03-10 09:20:00", capturar=False) == 0, "rearchivar no lo apunta dos veces")

    # Sin paquete (solo el correo) también
    INFO = dict(PLANO, **{"Doc. EIPSA": "99-004-ESP-0003", "Doc. Cliente": "CLI-SPC-0002",
                          "Título": "DATA SHEET", "Rev.": "0", "Estado": "Informativo"})
    res2 = D.archive_email_only([INFO], "P-99/004", email_raw=b"correo", email_date="2099-03-11")
    ok(R.anotar(res2, "2099-03-11", capturar=False) == 1 and res2["devueltos"][0]["nuestra"] == "0",
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
ok(p.get("falta") == ["fecha", "estado"],
   f"fecha y estado, en ese orden; la revisión no se toca y no es la 1ª devolución: {p.get('falta')}")
ok(por.get("99-004-ESP-0003", {}).get("falta") == ["documento"], "el que no está en el ERP se dice")

# Ya puesto, con la fecha del día que se apuntó (dos días después): cuadra
ERP["99-004-PLG-0005"].update(state="Aprobado", state_date="12/03/2099")
ok("99-004-PLG-0005" not in {f["doc_eipsa"] for f in R.pendientes(erp=ERP)["filas"]},
   "con estado y una fecha de esos días sale de la lista")
# Una revisión que no es la nuestra no importa: al recibir no se toca
ERP["99-004-PLG-0005"].update(revision=0)
ok("99-004-PLG-0005" not in {f["doc_eipsa"] for f in R.pendientes(erp=ERP)["filas"]},
   "la revisión del ERP no se compara")
# …salvo para saber que ya se reenvió: el ERP va por una revisión nuestra posterior
ERP["99-004-PLG-0005"].update(revision=2, state="Enviado")
ok("99-004-PLG-0005" not in {f["doc_eipsa"] for f in R.pendientes(erp=ERP)["filas"]},
   "si el ERP ya va por una revisión nuestra posterior (se reenvió), esto es historia")
ERP["99-004-PLG-0005"].update(revision=1)

# ── 1er envío, con la primera devolución (nuestra rev 0) ─────────────────────
# El de información es la rev 0: mientras el ERP dice «Enviado» rev 0, su fecha
# de estado es la del primer envío, y se guarda antes de que se pise
ERP["99-004-ESP-0003"] = {"num_doc_eipsa": "99-004-ESP-0003", "state": "Enviado", "revision": 0,
                          "state_date": "02/03/2099", "date_first_rev": ""}
f = next(x for x in R.pendientes(erp=ERP)["filas"] if x["doc_eipsa"] == "99-004-ESP-0003")
ok(f["falta"] == ["fecha", "estado", "primer_envio"] and f["primer_envio"] == "02/03/2099",
   f"1ª devolución: fecha, estado y 1er envío = la fecha del envío: {f['falta']} {f['primer_envio']}")
ok(next(e for e in R._cargar()["devueltos"].values() if e["doc_eipsa"] == "99-004-ESP-0003")
   .get("primer_envio") == "02/03/2099", "y se queda guardada")
# Se pone la fecha de la devolución (la del envío se pierde en el ERP): se sigue sabiendo
ERP["99-004-ESP-0003"].update(state="Información", state_date="11/03/2099")
f = next(x for x in R.pendientes(erp=ERP)["filas"] if x["doc_eipsa"] == "99-004-ESP-0003")
ok(f["falta"] == ["primer_envio"] and f["primer_envio"] == "02/03/2099", f"solo falta el 1er envío: {f}")
ERP["99-004-ESP-0003"]["date_first_rev"] = "02/03/2099"
ok("99-004-ESP-0003" not in {x["doc_eipsa"] for x in R.pendientes(erp=ERP)["filas"]}, "con él, cuadra")
# Sin verlo a tiempo, no se inventa
nuevo = {"doc_eipsa": "99-004-ESP-0009", "nuestra": "0", "estado": "Aprobado", "fecha": "10/03/2099"}
f = R.comparar(nuevo, {"state": "Aprobado", "revision": 0, "state_date": "10/03/2099", "date_first_rev": ""})
ok(f and f["falta"] == ["primer_envio"] and f["primer_envio"] == "", f"sin la fecha a la vista, vacío: {f}")
# En una devolución que no es la primera no se pide
ok(R.comparar(dict(nuevo, nuestra="2"), {"state": "Aprobado", "revision": 2, "state_date": "10/03/2099",
                                         "date_first_rev": ""}) is None, "en la rev 2 no se pide el 1er envío")

# Se busca también por el Nº del cliente (con espacios en el ERP)
ERP2 = {"CLI:CLI-SPC-0002": {"num_doc_client": "CLI-SPC- 0002", "state": "Información", "revision": 0,
                             "state_date": "11/03/2099", "date_first_rev": "02/03/2099"}}
ok(R.comparar(next(e for e in R._cargar()["devueltos"].values() if e["doc_cliente"] == "CLI-SPC-0002"),
              ERP2["CLI:CLI-SPC-0002"]) is None, "cuadra el que se encuentra por el Nº del cliente")

# Grupos para pegar de una vez y ocultar
filas = R.pendientes(erp={})["filas"]
ok(all("documento" in x["falta"] for x in filas) and R.grupos(filas) == [], "sin ERP para ellos: sin grupos")
# Un estado equivocado (un «Enviado» de después sería un reenvío y ya no faltaría nada)
filas = R.pendientes(erp={k: dict(v, state="Rechazado") for k, v in ERP.items()})["filas"]
g = R.grupos([x for x in filas if "documento" not in x["falta"]])
ok(g and g[0]["estado"] == "Aprobado" and g[0]["fecha"] == "10/03/2099", f"grupo por estado y fecha: {g}")
xlsx = R.exportar_excel(filas, tmp / "pendiente.xlsx")
from openpyxl import load_workbook  # noqa: E402
ws = load_workbook(xlsx).active
cab = [c.value for c in ws[1]]
ok(cab[:6] == ["num_doc_eipsa", "num_doc_client", "num_order", "state_date", "state", "date_first_rev"]
   and "revision" not in cab, f"Excel: fecha, estado, 1er envío y sin columna de revisión: {cab}")
fila_plg = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] == "99-004-PLG-0005")
ok(fila_plg[3] == "10/03/2099" and fila_plg[4] == "Aprobado" and fila_plg[5] is None,
   f"Excel: lo que hay que poner (sin 1er envío en una rev 1): {fila_plg}")
clave = next(x["clave"] for x in filas if x["doc_eipsa"] == "99-004-PLG-0005")
R.ignorar(clave)
ok(all(x["doc_eipsa"] != "99-004-PLG-0005" for x in R.pendientes(erp={})["filas"]), "la ocultada no vuelve")

# ── La columna «ERP» de Devoluciones: por correo (código del transmittal) ────
def _dv(doc, nuestra="1", estado="Aprobado"):
    return {"doc_eipsa": doc, "doc_cliente": "", "nuestra": nuestra, "estado": estado,
            "pedido": "P-99/005", "titulo": "", "cliente": "B", "carpeta": ""}


ok(R.anotar({"devueltos": [_dv("99-005-CAL-0001"), _dv("99-005-PLG-0002")]}, "2099-05-02",
            capturar=False, codigo="TR-99-0001") == 2, "dos documentos de un transmittal")
ok(R.anotar({"devueltos": [_dv("99-004-PLG-0005", "1")]}, "2099-03-10", capturar=False,
            codigo="TR-99-0000") == 0, "un rearchivo no es nuevo…")
ok(next(e for e in R._cargar()["devueltos"].values() if e["doc_eipsa"] == "99-004-PLG-0005")
   .get("codigo") == "TR-99-0000", "…pero se queda con el código del transmittal")
ERP3 = {"99-005-CAL-0001": {"state": "Aprobado", "revision": 1, "state_date": "02/05/2099"},
        "99-005-PLG-0002": {"state": "Enviado", "revision": 1, "state_date": "20/04/2099"}}
st = R.estado_por_codigo(erp=ERP3)
ok(st.get("TR-99-0001") == {"total": 2, "faltan": 1}, f"uno hecho y otro no: {st}")
ERP3["99-005-PLG-0002"].update(state="Aprobado", state_date="03/05/2099")
ok(R.estado_por_codigo(erp=ERP3).get("TR-99-0001") == {"total": 2, "faltan": 0}, "los dos hechos")
ok(R.estado_por_codigo(erp=None) is None, "sin ERP no se sabe")

# ── Lo archivado antes de que hubiera registro ───────────────────────────────
base = tmp / "P-99-006-S00 - CLIENTE" / "2-Tecnico"
com = base / "dev. Planos" / "rev 1-B com"
com.mkdir(parents=True)
(com / "CLI-DWG-0061.pdf").write_bytes(b"x" * 10)          # de otra devolución, otro tamaño
(com / "CLI-DWG-0061_1.pdf").write_bytes(b"y" * 25)        # el de ésta, guardado al lado
ap = base / "dev. Cálculos" / "rev 0-0 AP"
ap.mkdir(parents=True)
(ap / "CLI-CAL-0062-R0.pdf").write_bytes(b"z" * 7)
zp = tmp / "tr.zip"
with zipfile.ZipFile(zp, "w") as zf:
    zf.writestr("CLI-DWG-0061.pdf", b"y" * 25)
    zf.writestr("CLI-CAL-0062-R0.pdf", b"z" * 7)
    zf.writestr("NO-ES-DE-NADIE.pdf", b"?")
eml = tmp / "dev.eml"
eml.write_bytes(b"Date: Fri, 30 Oct 2099 13:25:08 +0100\r\nSubject: x\r\n\r\ncuerpo")
DESCARGAS = {"TR-99-0006": {"pedido": "P-99/006", "zip": str(zp), "eml": str(eml), "when": "2099-11-02T08:00:00",
                            "portal": "tr", "dev_folders": [str(com), str(ap)]}}
SEGUIMIENTO = [{"Nº Pedido": "P-99/006-S00", "Nº Doc. EIPSA": "99-006-PLG-0001", "Nº Doc. Cliente": "CLI-DWG-0061"},
               {"Nº Pedido": "P-99/006-S00", "Nº Doc. EIPSA": "99-006-CAL-0002", "Nº Doc. Cliente": "CLI-CAL-0062"}]
ok(R.recuperar_archivado(docs=SEGUIMIENTO, descargas=DESCARGAS) == 2, "recupera los dos documentos")
rec = {e["doc_eipsa"]: e for e in R._cargar()["devueltos"].values() if e.get("codigo") == "TR-99-0006"}
p, c = rec.get("99-006-PLG-0001", {}), rec.get("99-006-CAL-0002", {})
ok(p.get("estado") == "Com. Menores" and p.get("nuestra") == "1" and p.get("cliente") == "B",
   f"de la carpeta «rev 1-B com», aunque el fichero se guardara como _1: {p}")
ok(p.get("fecha") == "30/10/2099" and p.get("recibido") == "2099-10-30T13:25:08",
   f"la fecha y la hora del correo, no las de la descarga: {p.get('fecha')} {p.get('recibido')}")
ok(c.get("estado") == "Aprobado" and c.get("estado_alt") == ["Información"] and c.get("nuestra") == "0",
   f"un AP recuperado vale como Aprobado o Información: {c}")
ok(R.comparar(c, {"state": "Información", "revision": 0, "state_date": "30/10/2099",
                  "date_first_rev": "01/10/2099"}) is None, "y si el ERP dice Información, cuadra")
ok(R.recuperar_archivado(docs=SEGUIMIENTO, descargas=DESCARGAS) == 0, "cada transmittal se mira una vez")
ok(R._rev_de_carpeta(base / "dev. Planos" / "rev0" / "com. mayores") == ("0", "", "Com. Mayores"),
   "resolución en subcarpeta")
ok(R._rev_de_carpeta(base / "rev0-A" / "VOID") is None, "un VOID no se recupera")

# Reenviado aunque el ERP no subiera la revisión: «Enviado» de después de la devolución
dev51 = {"doc_eipsa": "99-007-DOS-0002", "nuestra": "5", "cliente": "51", "estado": "Com. Menores",
         "fecha": "31/10/2099"}
ok(R.comparar(dev51, {"state": "Enviado", "revision": 5, "state_date": "03/11/2099"}) is None,
   "se envió la 52 después de devolverse la 51: es historia")
ok(R.comparar(dev51, {"state": "Enviado", "revision": 5, "state_date": "20/10/2099"}) is not None,
   "un «Enviado» de antes de la devolución es el envío que se devolvió: falta")
ok(R.comparar(dev51, {"state": "Enviado", "revision": 6, "state_date": "31/10/2099"}) is None,
   "reenviado el mismo día que volvió")
# Otro resultado del MISMO día: otra devolución que la app no vio (la segunda llegó por correo)
cal = {"doc_eipsa": "99-007-CAL-0007", "nuestra": "1", "cliente": "B", "estado": "Aprobado", "fecha": "30/10/2099"}
ok(R.comparar(cal, {"state": "Com. Menores", "revision": 1, "state_date": "30/10/2099"}) is None,
   "Com. Menores del mismo día en el ERP: lo apuntado es lo bueno")
f = R.comparar(cal, {"state": "Com. Menores", "revision": 1, "state_date": "28/10/2099"})
ok(f and "estado" in f["falta"], f"de otro día sí falta: {f}")

# El mismo documento devuelto dos veces el mismo día: vale cualquiera de los dos
reg = R._cargar()
reg["devueltos"]["a"] = {"doc_eipsa": "99-008-PLG-0005", "doc_cliente": "", "nuestra": "1", "cliente": "B",
                         "estado": "Aprobado", "fecha": "30/10/2099", "recibido": "2099-10-30T07:57:00",
                         "codigo": "TR-A", "anotado": "2099-10-30"}
reg["devueltos"]["b"] = dict(reg["devueltos"]["a"], estado="Com. Menores", recibido="2099-10-30T13:25:00",
                             codigo="TR-B")
R._guardar(reg)
ERP4 = {"99-008-PLG-0005": {"state": "Aprobado", "revision": 1, "state_date": "30/10/2099",
                            "date_first_rev": "01/10/2099"}}
st = R.estado_por_codigo(erp=ERP4)
ok(st.get("TR-B") == {"total": 1, "faltan": 0}, f"la última es com, el ERP dice el AP del mismo día: {st.get('TR-B')}")
ok(R._con_hermanas(R._cargar(), "b").get("estado_alt") == ["Aprobado"], "con su hermana como alternativa")

# Carpeta movida a mano después de archivar: manda la ruta donde se archivó
movida = base / "dev. Planos" / "rev 2-C AP"                 # no existe
zp2 = tmp / "tr2.zip"
with zipfile.ZipFile(zp2, "w") as zf:
    zf.writestr("CLI-DWG-0061.pdf", b"w" * 40)
DESC2 = {"TR-99-0009": {"pedido": "P-99/006", "zip": str(zp2), "when": "2099-11-05T08:00:00",
                        "dev_folders": [str(movida)]}}
ok(R.recuperar_archivado(docs=SEGUIMIENTO, descargas=DESC2) == 1, "recupera el de la carpeta movida")
m = next(e for e in R._cargar()["devueltos"].values() if e.get("codigo") == "TR-99-0009")
ok(m["estado"] == "Aprobado" and m["nuestra"] == "2" and m["cliente"] == "C", f"con lo que decía su carpeta: {m}")

from gui.views.devoluciones.lista import _CARGANDO, DevolucionesView  # noqa: E402

lista = DevolucionesView.__new__(DevolucionesView)      # solo la celda, sin buzón
correo = {"download": {"code": "TR-99-0001"}}
lista._erp = _CARGANDO
ok(lista._estado_erp(correo)[1]["text"] == "…", "mientras consulta")
lista._erp = {"TR-99-0001": {"total": 2, "faltan": 0}}
ok(lista._estado_erp(correo)[1]["text"] == "✓  hecho", "hecho")
lista._erp = {"TR-99-0001": {"total": 3, "faltan": 2}}
ok(lista._estado_erp(correo)[1]["text"] == "faltan 2 de 3", "lo que falta")
lista._erp = {"TR-99-0001": {"total": 1, "faltan": 1}}
ok(lista._estado_erp(correo)[1]["text"] == "falta", "uno solo")
ok(lista._estado_erp({"download": {"code": "OTRO"}})[1]["text"] == "—", "sin documentos archivados")
lista._erp = None
ok(lista._estado_erp(correo)[1]["text"] == "sin ERP", "sin ERP")

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
ok(c["Rev"]["text"] == "2  (cli C)" and c["ERP"]["text"] == "01/03/2099 · Enviado · rev 2"
   and c["Estado"]["bold"] and not c["Fecha"].get("bold") and c["Primer"]["text"] == "", f"celdas: {c}")
ok([col["key"] for col in V.COLUMNS][3:6] == ["Fecha", "Estado", "Primer"], "columnas en el orden del ERP")
c = V.celdas(dict(w._filas[0], nuestra="0", falta=["fecha", "estado", "primer_envio"], primer_envio=""))
ok(c["Primer"]["text"] == "? búscalo" and c["Primer"]["bold"], f"1er envío sin fecha a la vista: {c['Primer']}")
ok("1 por registrar" in w.lbl_estado.cget("text"), f"resumen: {w.lbl_estado.cget('text')}")
root.destroy()
shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
