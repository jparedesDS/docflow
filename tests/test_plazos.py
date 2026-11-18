# -*- coding: utf-8 -*-
"""Plazos: del correo de la oferta a la fábrica. Hitos y días de cada paso,
tiempos típicos por paso y por persona, la cola de planos con su margen, y el
cálculo completo con el Excel.

Datos inventados (pedidos P-99/…, dominio ejemplo.test): nada de clientes reales.

    .venv\\Scripts\\python.exe tests\\test_plazos.py
"""
import sys
from datetime import date, datetime, timedelta  # noqa: F401
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import seguimiento as seg  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


def ped(**kw):
    base = {"pedido": "P-99/001-S00", "base": "P-99/001", "oferta": "O-99/010", "cliente": "CLIENTE FICTICIO",
            "equipo": "Vainas", "responsable": "Pepa Ruiz", "recep_date": date(2099, 1, 2),
            "presentation_date": date(2099, 1, 6), "order_date": date(2099, 2, 25),
            "expected_date": date(2099, 5, 1), "envio": None, "porc_taller": None, "cerrado": False}
    base.update(kw)
    return base


# ── Tarea 1: hitos y tramos ──────────────────────────────────────────────────

PLANOS = {"P-99/001-S00": {"estado": "ok", "creado": datetime(2099, 3, 5, 17, 52), "autor": "tecnico.uno", "ruta": "X"}}
CORREOS = {"O-99/010": {"recibido": datetime(2099, 1, 1, 23, 50), "contestado": datetime(2099, 1, 6, 9, 0),
                        "contesta": "Pepa Ruiz"}}
ACT = {"P-99/001-S00": {"recibido": datetime(2099, 2, 26, 8, 0), "remitente": "Pepa Ruiz"}}
COMPRAS = {"P-99/001": {"primer_pedido": date(2099, 3, 1), "ultima_recepcion": date(2099, 3, 20), "pendiente": 0}}
OTS = {"P-99/001": {"primera_ot": date(2099, 3, 5), "primer_fichaje": date(2099, 3, 9)}}

f = seg.construir_filas([ped()], COMPRAS, OTS, PLANOS, CORREOS, ACT)[0]
ok(f["hitos"]["rfq"]["fuente"] == "correo" and f["tramos"]["comercial"] == 5,
   f"rfq del correo; 1-ene 23:50 → 6-ene = 5 días: {f['hitos']['rfq']} {f['tramos']['comercial']}")
ok(f["hitos"]["contestada"]["persona"] == "Pepa Ruiz", "quien contesta")
ok(f["tramos"]["cliente"] == 50, f"6-ene → 25-feb: {f['tramos']['cliente']}")
ok(f["tramos"]["tecnico"] == 7 and f["hitos"]["planos"]["persona"] == "tecnico.uno",
   f"26-feb → 5-mar, autor: {f['tramos']['tecnico']}")
ok(f["tramos"]["material"] == 22 and f["tramos"]["compras_pedir"] == 3, "compras en paralelo desde la activación")
ok(f["tramos"]["a_fabrica"] == 0 and f["tramos"]["cola_taller"] == 4, "planos → 1.ª OT → 1.er fichaje")
ot_antes = seg.construir_filas([ped()], COMPRAS, {"P-99/001": {"primera_ot": date(2099, 3, 1), "primer_fichaje": None}},
                               PLANOS, CORREOS, ACT)[0]
ok(ot_antes["tramos"]["total"] == 63,
   f"total: correo de la oferta → planos a fábrica (1-ene → 5-mar), no a la OT: {ot_antes['tramos']['total']}")
ok(f["estado"] == "ok" and f["compartido"] is False, f"estado normal: {f['estado']} {f['compartido']}")
ok(f["ruta"] == "X", "ruta de los planos")
f = seg.construir_filas([ped()], {}, {}, {"P-99/001-S00": {**PLANOS["P-99/001-S00"], "fuente": "correo",
                                                          "envios": 2}}, {}, {})[0]
ok(f["hitos"]["planos"]["fuente"] == "correo" and f["envios"] == 2, "planos a fábrica: del correo de Envíos")

# Revisión final: el día de un correo es el día aquí, no en la zona del remitente
rec = datetime.fromisoformat("2026-11-09T19:30:00-05:00")
con = datetime.fromisoformat("2026-11-10T10:00:00+01:00")
f = seg.construir_filas([ped(recep_date=date(2026, 11, 10), presentation_date=date(2026, 11, 10),
                             order_date=date(2026, 12, 1))], {}, {}, {},
                        {"O-99/010": {"recibido": rec, "contestado": con, "contesta": "X"}}, {})[0]
esperado = (con.astimezone().date() - rec.astimezone().date()).days
ok(f["tramos"]["comercial"] == esperado, f"días en hora local: {f['tramos']['comercial']} (esperado {esperado})")

f = seg.construir_filas([ped()], {}, {}, PLANOS, {}, {})[0]
ok(f["hitos"]["rfq"]["fuente"] == "erp" and f["tramos"]["comercial"] == 4, "sin correo: días del ERP")
ok(f["hitos"]["activacion"]["fecha"] == date(2099, 2, 25) and f["hitos"]["activacion"]["fuente"] == "erp",
   "sin correo de activación: order_date")
ok(f["hitos"]["contestada"]["persona"] == "Pepa Ruiz", "sin respuesta en el correo: responsable del ERP")
ok(f["hitos"]["material"]["fuente"] == "sin_compras", "sin compras = stock")

f = seg.construir_filas([ped()], {}, {}, {"P-99/001-S00": {"estado": "ok", "creado": datetime(2099, 2, 20),
                                                          "autor": "t", "ruta": ""}}, {}, {})[0]
ok(f["estado"] == "planos_antes" and f["tramos"]["tecnico"] == -5, "planos antes del pedido")

VACIA = {"estado": "vacia", "creado": None, "autor": "", "ruta": ""}
f = seg.construir_filas([ped(porc_taller=99)], {}, {}, {"P-99/001-S00": VACIA}, {}, {})[0]
ok(f["estado"] == "fabricado_sin_planos", "vacía + taller 99 %")
f = seg.construir_filas([ped()], {}, {}, {"P-99/001-S00": VACIA}, {}, {})[0]
ok(f["estado"] == "pendiente_planos", "vacía y sin fabricar")
f = seg.construir_filas([ped()], {}, {}, {}, {}, {})[0]
ok(f["estado"] == "sin_carpeta", "sin datos de carpeta: sin carpeta")

dos = seg.construir_filas([ped(), ped(pedido="P-99/001-S01")], COMPRAS, OTS, PLANOS, {}, {})
ok(all(x["compartido"] for x in dos), "compras/OTs del pedido base repartidas a sus suministros")
ok(f["tramos"]["activar"] is None, "sin correo de activación no hay días de activar (no es un 0)")

# Lo del propio suministro manda; lo del pedido base solo vale si no es de antes de su activación
OTS_SUM = {"P-99/001-S01": {"primera_ot": date(2099, 6, 10), "primer_fichaje": None}, **OTS}
tarde = seg.construir_filas([ped(), ped(pedido="P-99/001-S01", order_date=date(2099, 6, 1))],
                            COMPRAS, OTS_SUM, {**PLANOS, "P-99/001-S01": PLANOS["P-99/001-S00"]}, {}, {})
ok(tarde[1]["hitos"]["fabrica"]["fecha"] == date(2099, 6, 10), "la OT del propio suministro")
ok(tarde[1]["hitos"]["compra_1"]["fecha"] is None and tarde[1]["hitos"]["material"]["fuente"] == "sin_compras",
   "las compras del pedido de marzo no son de un suministro activado en junio")
ok(tarde[0]["hitos"]["compra_1"]["fecha"] == date(2099, 3, 1), "el suministro de antes sí las tiene")
otro = seg.construir_filas([ped(pedido="P-99/001-S02", order_date=date(2099, 6, 1)), ped()], COMPRAS, OTS,
                           PLANOS, {}, {})
ok(otro[0]["hitos"]["fabrica"]["fecha"] is None, "la OT del pedido de marzo no es de un suministro de junio")

f = seg.construir_filas([ped(expected_date=date(2098, 1, 1))], {}, {}, PLANOS, {}, {})[0]
ok(any("entrega" in a for a in f["avisos"]), "entrega anterior al pedido: aviso")
f = seg.construir_filas([ped(oferta="", recep_date=None, presentation_date=None)], {}, {}, PLANOS, {}, {})[0]
ok(f["tramos"]["comercial"] is None and f["tramos"]["cliente"] is None, "pedido interno sin oferta")

# ── Tarea 2: resumen ─────────────────────────────────────────────────────────

# activación = order_date 25-feb; planos 1..5 de marzo → técnico 4, 5, 6, 7, 8 días
filas = seg.construir_filas([ped(pedido=f"P-99/00{i}-S00", base=f"P-99/00{i}") for i in range(1, 6)], {}, {},
                            {f"P-99/00{i}-S00": {"estado": "ok", "creado": datetime(2099, 3, i),
                                                 "autor": "tecnico.uno", "ruta": ""} for i in range(1, 6)}, {}, {})
r = seg.resumen(filas)
ok(r["tramos"]["tecnico"] == {"n": 5, "mediana": 6, "p25": 4.5, "p75": 7.5}, f"stats técnico: {r['tramos']['tecnico']}")
ok(not any(p["paso"] == "cliente" for p in r["por_persona"]), "el cliente no se carga a nadie")
tec = next((p for p in r["por_persona"] if p["paso"] == "tecnico"), {})
ok(tec.get("persona") == "tecnico.uno" and tec.get("n") == 5, f"técnico por autor: {tec}")
com = next((p for p in r["por_persona"] if p["paso"] == "comercial"), {})
ok(com.get("persona") == "Pepa Ruiz" and com.get("mediana") == 4, f"comercial: {com}")
ok(seg._stats([7, 9]) == {"n": 2, "mediana": 8, "p25": None, "p75": None}, "pocos casos: sin cuantiles")
ok(seg._stats([]) == {"n": 0, "mediana": None, "p25": None, "p75": None}, "sin casos")
ok(r["con_hora"] == {"rfq": 0, "total": 5}, f"ninguna con hora de correo: {r['con_hora']}")
ok(r["por_mes"]["2099-02"]["tecnico"]["n"] == 5 and r["por_equipo"]["Vainas"]["tecnico"]["mediana"] == 6,
   "por mes del pedido y por tipo de equipo")
filas.append(seg.construir_filas([ped(pedido="P-99/009-S00", base="P-99/009")], {}, {},
                                 {"P-99/009-S00": {"estado": "ok", "creado": datetime(2099, 2, 1),
                                                   "autor": "tecnico.uno", "ruta": ""}}, {}, {})[0])
ok(seg.resumen(filas)["tramos"]["tecnico"]["n"] == 5, "planos antes del pedido: fuera de la mediana del técnico")


# ── Tarea 3: cola y margen ───────────────────────────────────────────────────

H = []  # histórico: 7 vainas con planos→envío de 20…80 días → p25 = 30, p75 = 70
for i, d in enumerate([20, 30, 40, 50, 60, 70, 80]):
    H += seg.construir_filas([ped(pedido=f"P-98/0{i}0-S00", base=f"P-98/0{i}0", envio=date(2099, 3, 5) + timedelta(days=d))],
                             {}, {}, {f"P-98/0{i}0-S00": {"estado": "ok", "creado": datetime(2099, 3, 5), "autor": "t",
                                                          "ruta": ""}}, {}, {})
hoy = date(2099, 3, 1)
filas = seg.construir_filas([
    ped(pedido="P-99/001-S00", base="P-99/001", expected_date=date(2099, 5, 30)),   # sin planos, material recibido
    ped(pedido="P-99/002-S00", base="P-99/002", expected_date=date(2099, 4, 1)),    # sin planos, material pendiente
    ped(pedido="P-99/003-S00", base="P-99/003"),                                    # con planos, material pendiente
    ped(pedido="P-99/004-S00", base="P-99/004", porc_taller=99),                    # fabricado: fuera
    ped(pedido="P-99/005-S00", base="P-99/005", equipo="RO", expected_date=date(2099, 6, 9)),  # RO, sin compras
    ped(pedido="P-99/006-S00", base="P-99/006"),                                    # ya en fábrica: fuera
], {"P-99/001": {"primer_pedido": date(2099, 2, 27), "ultima_recepcion": date(2099, 2, 28), "pendiente": 0},
    "P-99/002": {"primer_pedido": date(2099, 2, 27), "ultima_recepcion": None, "pendiente": 3},
    "P-99/003": {"primer_pedido": date(2099, 2, 27), "ultima_recepcion": None, "pendiente": 3}},
   {"P-99/006": {"primera_ot": date(2099, 2, 28), "primer_fichaje": None}},
   {"P-99/001-S00": VACIA, "P-99/002-S00": VACIA, "P-99/004-S00": VACIA, "P-99/005-S00": VACIA,
    "P-99/003-S00": {"estado": "ok", "creado": datetime(2099, 2, 28), "autor": "t", "ruta": ""},
    "P-99/006-S00": {"estado": "ok", "creado": datetime(2099, 2, 27), "autor": "t", "ruta": ""}}, {}, {})
c = seg.cola(filas, H, hoy)
ok([x["pedido"] for x in c] == ["P-99/001-S00", "P-99/005-S00", "P-99/002-S00", "P-99/003-S00"],
   f"orden por grupo y margen: {[x['pedido'] for x in c]}")
ok(c[0]["grupo"] == 1 and c[0]["falta"] == "planos", "material recibido, sin planos: lo primero")
# 1-mar → 30-may = 90 días; 90 − 70 = 20, 90 − 30 = 60. 1-mar → 9-jun = 100 días
ok(c[0]["margen"] == (20, 60) and c[0]["margen_n"] == 7 and c[0]["margen_de"] == "Vainas", f"margen: {c[0]}")
ok(c[1]["grupo"] == 1 and c[1]["margen_de"] == "todos los tipos" and c[1]["margen"] == (30, 70),
   f"RO: todos los tipos: {c[1]['margen_de']} {c[1]['margen']}")
ok(c[2]["grupo"] == 2 and c[2]["falta"] == "ambos" and c[2]["margen"] == (-39, 1),
   f"material pendiente: grupo 2; 31 días a la entrega: {c[2]['margen']}")
ok(c[3]["grupo"] == 3 and c[3]["margen"] is None and c[3]["falta"] == "material", "con planos: sin margen")
c = seg.cola(filas, H[:3], hoy)
ok(c[0]["margen"] is None, "con menos de 4 casos no hay horquilla")
# La OT se lanza antes de mandar los planos: con OT y sin planos a fábrica, sigue en la cola
con_ot = seg.construir_filas([ped(pedido="P-99/021-S00", base="P-99/021")], {},
                             {"P-99/021": {"primera_ot": date(2099, 2, 26), "primer_fichaje": None}},
                             {"P-99/021-S00": VACIA}, {}, {})
c = seg.cola(con_ot, H, hoy)
ok([x["pedido"] for x in c] == ["P-99/021-S00"] and c[0]["falta"] == "planos", f"OT lanzada sin planos: en cola: {c}")
imposible = seg.construir_filas([ped(expected_date=date(2098, 11, 30), order_date=date(2098, 12, 1))], {}, {},
                                 {"P-99/001-S00": VACIA}, {}, {})
ok(seg.cola(imposible, H, date(2098, 12, 2))[0]["margen"] is None, "entrega imposible: sin margen")

# Fuera de la cola: lo cerrado o enviado aunque no tenga carpeta, y los zombis del ERP
fuera = seg.construir_filas([
    ped(pedido="P-99/011-S00", base="P-99/011", cerrado=True),
    ped(pedido="P-99/012-S00", base="P-99/012", envio=date(2099, 2, 28)),
    ped(pedido="P-99/013-S00", base="P-99/013", order_date=date(2098, 1, 10), expected_date=date(2098, 8, 31)),
    ped(pedido="P-99/014-S00", base="P-99/014", order_date=date(2098, 1, 10), expected_date=date(2098, 9, 2)),
], {}, {}, {}, {}, {})
ok([c["pedido"] for c in seg.cola(fuera, H, hoy)] == ["P-99/014-S00"],
   f"cerrado, enviado y entrega vencida hace más de 180 días fuera: {[c['pedido'] for c in seg.cola(fuera, H, hoy)]}")


# ── Tarea 7: cargar() y Excel ────────────────────────────────────────────────

import tempfile  # noqa: E402

from openpyxl import load_workbook  # noqa: E402

from core.services import seguimiento_carpetas, seguimiento_correos, seguimiento_erp  # noqa: E402
from core.services import seguimiento_excel  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="plazos_t7_"))


def falla(*a, **k):
    raise RuntimeError("no responde")


seguimiento_erp.pedidos = falla
seguimiento_erp.compras = falla
seguimiento_erp.ots = falla
seguimiento_carpetas.leer_planos = lambda pedidos, **k: {}
seguimiento_correos.cache = lambda *a, **k: {}
seguimiento_correos.activaciones_por_pedido = lambda: {}
d = seg.cargar((2099,), hoy=date(2099, 3, 1), correo=False, base_dir=tmp)
ok(d["filas"] == [] and "Sin ERP" in d["avisos"], f"sin ERP no se cae: {d['avisos']}")
d = seg.cargar((2099,), hoy=date(2099, 3, 1), correo=False, base_dir=tmp / "no-existe")
ok("Sin acceso a M:" in d["avisos"], f"sin M: {d['avisos']}")

seguimiento_erp.pedidos = lambda años: [ped(), ped(pedido="P-98/001-S00", base="P-98/001",
                                                 order_date=date(2098, 2, 1), envio=date(2098, 4, 1))]
seguimiento_erp.compras = lambda desde: COMPRAS
seguimiento_erp.ots = lambda desde: {}
seguimiento_carpetas.leer_planos = lambda pedidos, **k: {**PLANOS, "P-98/001-S00": PLANOS["P-99/001-S00"]}
seguimiento_correos.cache = lambda *a, **k: CORREOS
seguimiento_correos.activaciones_por_pedido = lambda: ACT
seguimiento_correos.actualizar = falla
d = seg.cargar((2099,), hoy=date(2099, 3, 1), correo=False, base_dir=tmp)
ok([f["pedido"] for f in d["filas"]] == ["P-99/001-S00"], f"solo los pedidos del año: {[f['pedido'] for f in d['filas']]}")
ok(d["avisos"] == [] and d["resumen"]["tramos"]["tecnico"]["n"] == 1 and isinstance(d["cola"], list),
   f"cálculo completo: {d['avisos']}")
ok(d["filas"][0]["hitos"]["rfq"]["fuente"] == "correo", "con correo desde la caché")
d2 = seg.cargar((2099,), hoy=date(2099, 3, 1), correo=True, base_dir=tmp)
ok("Sin correo" in d2["avisos"] and len(d2["filas"]) == 1, "si el buzón falla: aviso y sigue")

ruta = seguimiento_excel.exportar(d, tmp / "plazos.xlsx")
wb = load_workbook(ruta)
ok(wb.sheetnames == ["Pedidos", "Cola", "Por persona", "Resumen"], f"hojas: {wb.sheetnames}")
ok(wb["Pedidos"]["A2"].value == "P-99/001-S00", f"primera fila de pedidos: {wb['Pedidos']['A2'].value}")
cab = [c.value for c in wb["Pedidos"][1]]
TEC = "Días técnico (activación → planos a fábrica)"
ok("Oferta recibida" in cab and TEC in cab and "Técnico" in cab and "Fuente planos a fábrica" in cab,
   f"cabeceras: {cab}")
fila = {cab[i]: c.value for i, c in enumerate(wb["Pedidos"][2])}
ok(fila["Oferta recibida"] == datetime(2099, 1, 1, 23, 50) and fila["Fuente oferta recibida"] == "correo",
   f"fecha con hora y su fuente: {fila['Oferta recibida']}")
ok(fila[TEC] == 7, "días del técnico")


# ── Tarea 8: informe web ─────────────────────────────────────────────────────

import re  # noqa: E402

from core.services.interactive_report import plazos as rep  # noqa: E402

html = rep.render_plazos_html(d)
ok("P-99/001-S00" in html and "tiempo del cliente" in html.lower(), "el informe lleva el pedido y el tiempo del cliente")
ok("None" not in html and not re.search(r"\bnan\b", html), "sin None ni nan en el informe")
ok("1 de 1 ofertas" in html, "dice cuántas ofertas tienen la hora del correo")
vacio = {"filas": [], "cola": [], "resumen": seg.resumen([]), "generado": datetime(2099, 3, 1, 8, 0),
         "avisos": ["Sin ERP"], "años": (2099,)}
html = rep.render_plazos_html(vacio)
ok("Sin ERP" in html and "None" not in html, "informe vacío con su aviso")


print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
