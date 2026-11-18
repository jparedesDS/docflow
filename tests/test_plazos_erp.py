# -*- coding: utf-8 -*-
"""Plazos: lectura del ERP (pedidos, compras y OTs) con consultas sustituidas.

Datos inventados (P-99/…): no se conecta al ERP.

    .venv\\Scripts\\python.exe tests\\test_plazos_erp.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import seguimiento_erp as se  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


FILAS = {
    "pedidos": [
        {"num_order": "P-99/005", "num_offer": "O-99/010", "client": "CLIENTE FICTICIO", "final_client": "",
         "material": "Vainas", "responsible": "p.ruiz", "recep_date": date(2099, 1, 2),
         "presentation_date": date(2099, 1, 6), "order_date": date(2099, 2, 25), "expected_date": date(2099, 5, 1),
         "last_date_deliveries": "10/03/2099 parcial", "porc_workshop": 40, "closed": ""},
        {"num_order": "P-99/006-S03R", "num_offer": "", "client": "OTRO", "final_client": "PLANTA FICTICIA",
         "material": "RO", "responsible": None, "recep_date": None, "presentation_date": None,
         "order_date": date(2099, 2, 1), "expected_date": None, "last_date_deliveries": "",
         "porc_workshop": None, "closed": "OK"},
        {"num_order": "PA-99/001", "num_offer": "", "client": "X", "final_client": "", "material": "",
         "responsible": "", "recep_date": None, "presentation_date": None, "order_date": date(2099, 1, 1),
         "expected_date": None, "last_date_deliveries": "", "porc_workshop": None, "closed": ""},
    ],
    "compras": [
        {"notes": "P-99/001 Y P-99/002", "order_date": date(2099, 3, 1), "pending": 0,
         "deliv_date_1": date(2099, 3, 10), "deliv_date_2": None, "deliv_date_3": None},
        {"notes": "P-99/001", "order_date": date(2099, 2, 27), "pending": 2,
         "deliv_date_1": None, "deliv_date_2": None, "deliv_date_3": None},
    ],
    "ots": [
        {"tag": "P-99/001-S00", "start_date": date(2099, 3, 5), "primer_fichaje": date(2099, 3, 9)},
        {"tag": "P-99/001-S00", "start_date": date(2099, 3, 2), "primer_fichaje": None},
    ],
}
se._q = lambda sql, params, label: FILAS[label]
se.who = lambda u: {"p.ruiz": "Pepa Ruiz"}.get(u or "", "")

ps = se.pedidos([2099])
ok([p["pedido"] for p in ps] == ["P-99/005-S00", "P-99/006-S03R"], f"P con su suministro, sin PA: {ps}")
p = ps[0]
ok(p["base"] == "P-99/005" and p["oferta"] == "O-99/010" and p["responsable"] == "Pepa Ruiz", f"datos: {p}")
ok(p["envio"] == date(2099, 3, 10) and p["porc_taller"] == 40 and p["cerrado"] is False, "envío con ruido, taller")
ok(ps[1]["cerrado"] is True and ps[1]["cliente"] == "PLANTA FICTICIA", "cerrado OK; cliente final si lo hay")

cp = se.compras(date(2099, 1, 1))
ok(cp["P-99/001"]["pendiente"] == 2 and cp["P-99/001"]["ultima_recepcion"] == date(2099, 3, 10),
   f"pendiente y última recepción: {cp.get('P-99/001')}")
ok(cp["P-99/001"]["primer_pedido"] == date(2099, 2, 27), "primer pedido a proveedor")
ok("P-99/002" in cp and cp["P-99/002"]["pendiente"] == 0, "un pedido a proveedor para dos pedidos cuenta en ambos")

ot = se.ots(date(2099, 1, 1))
ok(ot["P-99/001-S00"] == {"primera_ot": date(2099, 3, 2), "primer_fichaje": date(2099, 3, 9)}, f"OTs: {ot}")

# El suministro, si viene, separa: las OTs y compras de S01 no son de S00
FILAS["ots"] = [{"tag": "P-99/001-S01", "start_date": date(2099, 6, 1), "primer_fichaje": None},
                {"tag": "P-99/001", "start_date": date(2099, 3, 1), "primer_fichaje": None}]
ot = se.ots(date(2099, 1, 1))
ok(set(ot) == {"P-99/001-S01", "P-99/001"} and ot["P-99/001-S01"]["primera_ot"] == date(2099, 6, 1),
   f"OTs por suministro y, sin él, por pedido: {ot}")
FILAS["compras"] = [{"notes": "P-99/001 S6 Y P-99/002", "order_date": date(2099, 5, 1), "pending": 0,
                     "deliv_date_1": None, "deliv_date_2": None, "deliv_date_3": None}]
cp = se.compras(date(2099, 1, 1))
ok(set(cp) == {"P-99/001-S06", "P-99/002"}, f"compras: «S6» es el suministro S06: {set(cp)}")

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
