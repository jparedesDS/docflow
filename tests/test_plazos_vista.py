# -*- coding: utf-8 -*-
"""Plazos en la app: lo que enseñan las tarjetas, la tabla de pedidos y la de
personas (sin abrir ventanas). Mismo criterio que el Excel: pocas columnas,
nombres legibles, nada negativo y las personas que más pedidos llevan, arriba.

Datos inventados (P-99/…).

    .venv\\Scripts\\python.exe tests\\test_plazos_vista.py
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import seguimiento as seg  # noqa: E402
from gui.views import plazos as vista  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


ped = {"pedido": "P-99/001-S00", "base": "P-99/001", "oferta": "O-99/010", "cliente": "CLIENTE FICTICIO",
       "equipo": "Vainas", "responsable": "Pepa Ruiz", "recep_date": date(2099, 1, 2),
       "presentation_date": date(2099, 1, 6), "order_date": date(2099, 2, 25), "expected_date": date(2099, 5, 1),
       "envio": None, "porc_taller": None, "cerrado": False}
compras = {"P-99/001": {"primer_pedido": date(2099, 3, 1), "ultima_recepcion": date(2099, 3, 20), "pendiente": 0}}
planos = {"P-99/001-S00": {"estado": "ok", "creado": datetime(2099, 3, 5), "autor": "luis-ejemplo", "ruta": ""}}
carpetas = {"P-99/001-S00": {"oc": {"fecha": datetime(2099, 2, 27), "de": "luis-ejemplo", "para": "ana-ejemplo"},
                             "activacion": {"fecha": datetime(2099, 2, 26), "de": "pepa-ruiz", "para": ""},
                             "po": {"fecha": datetime(2099, 3, 1), "de": "x", "para": "y"}}}
f = seg.construir_filas([ped], compras, {}, planos, {}, {}, carpetas)[0]

ok(vista.PED_COLUMNS == ["Pedido", "Cliente", "Contestar", "Orden de compra", "Compras", "Proveedor",
                         "Planos a fábrica", "Puede empezar", "Total", "Lo que retrasó", "Técnico"],
   f"pocas columnas, con nombre claro: {vista.PED_COLUMNS}")
fila = vista.fila_pedido(f)
ok(fila == ["P-99/001-S00", "CLIENTE FICTICIO", "4", "1", "2", "19", "7", "22", "77", "Material", "Luis Ejemplo"],
   f"fila de un pedido: {fila}")
neg = dict(f, tramos={**f["tramos"], "tec_oc": -6})
ok(vista.fila_pedido(neg)[3] == "—", "un tramo negativo sale «—», no «-6»")

r = seg.resumen([f])
pp = [{"paso": "tecnico", "persona": "B", "n": 5}, {"paso": "tecnico", "persona": "A", "n": 90},
      {"paso": "comercial", "persona": "C", "n": 1}, {"paso": "tec_oc", "persona": "D", "n": 3}]
ok([(p["paso"], p["persona"]) for p in vista.personas_ordenadas(pp)]
   == [("comercial", "C"), ("tec_oc", "D"), ("tecnico", "A"), ("tecnico", "B")],
   "personas por paso, en el orden de la cadena, y dentro la que más pedidos lleva primero")
ok(all(len(t) <= 34 for t in vista.PASOS.values()), f"los pasos caben: {vista.PASOS}")

tarjetas = vista.tarjetas(r, [])
etiquetas = [t[0] for t in tarjetas]
ok(etiquetas == ["Contestar una oferta", "Técnico: orden de compra a Compras", "Proveedor: entrega el material",
                 "Técnico: planos a fábrica", "Esperan planos con el material listo"],
   f"tarjetas como el resumen del Excel: {etiquetas}")
ok(tarjetas[2][1] == "19 d" and tarjetas[4][1] == 0, f"valores: {tarjetas}")

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
