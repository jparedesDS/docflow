# -*- coding: utf-8 -*-
"""Expediente de cliente: datos por PO (agrupar pedidos, documentos, facturas,
avales y el expediente montado). Funciones puras: no se conecta al ERP ni al
buzón.

Datos inventados (P-99/…, PO 1099…, @ejemplo.test).

    .venv\\Scripts\\python.exe tests\\test_expediente_datos.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import expediente as ex  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


def fila(pedido, ref, **kw):
    base = {"num_order": pedido, "num_ref_order": ref, "order_date": date(2099, 1, 10), "order_amount": "1.000,00 €",
            "porc_deliveries": 100, "last_date_deliveries": "20/06/2099", "closed": "OK", "warranty_bond_state": None,
            "warranty_bond_amount": None, "warranty_bond_bank": None, "warranty_bond_expiring_date": None,
            "warranty_bond_reference": None, "payment_term": "90_10", "material": "Niveles"}
    base.update(kw)
    return base


# ── Task 1: agrupar pedidos en PO ────────────────────────────────────────────
def test_agrupar():
    ok(ex.clave_po("1099010710-00", "P-99/048-S00") == "109901071", "sufijo -00")
    ok(ex.clave_po("109901071", "P-99/048-S01") == "109901071", "9 dígitos")
    ok(ex.clave_po("1099010710 Sup.04", "P-99/048-S04") == "109901071", "Sup.")
    ok(ex.clave_po("N/A", "P-99/074-S02R") == "P-99/074", "sin dígitos → pedido")
    ok(ex.clave_po(None, "P-99/074-S00") == "P-99/074", "vacío → pedido")
    g = ex.agrupar([fila("P-99/048-S00", "109901071"), fila("P-99/048-S01", "1099010710-01"),
                    fila("P-99/080-S00", "10990107-02")],            # errata: un dígito de menos
                   extra={"1099010710": ["P-99/080"]})
    ok(list(g) == ["109901071"] and g["109901071"]["po"] == "1099010710", g)
    ok(g["109901071"]["pedidos"] == ["P-99/048", "P-99/080"], g)
    ok(len(g["109901071"]["ordenes"]) == 3, "las tres filas van al PO")
    # un pedido sin referencia no se pierde: va con su propio número
    g2 = ex.agrupar([fila("P-99/074-S00", None), fila("P-99/074-S01", "")])
    ok(list(g2) == ["P-99/074"] and g2["P-99/074"]["po"] == "P-99/074" and g2["P-99/074"]["pedidos"] == ["P-99/074"], g2)


test_agrupar()

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
