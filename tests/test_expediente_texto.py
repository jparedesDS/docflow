# -*- coding: utf-8 -*-
"""Expediente de cliente: texto automático y texto guardado de JP.

Datos inventados (P-99/…, PO 1099…). El estado se guarda en una carpeta
temporal, nunca en state/ de verdad.

    .venv\\Scripts\\python.exe tests\\test_expediente_texto.py
"""
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import expediente_texto as tx  # noqa: E402

fallos = 0
TMP = Path(tempfile.mkdtemp())
tx.state_dir = lambda: TMP          # nunca el state/ real


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


def d(dias):
    return {"doc_cliente": f"5099-{dias}", "titulo": "DOC", "dias": dias, "enviado": date(2099, 1, 1), "envios": 1}


PO = {"po": "1099010610", "pedidos": ["P-99/023"], "ultima_entrega": date(2099, 7, 30),
      "facturas": [{"numero": "F-99/061", "fecha": date(2099, 2, 20), "dias": 272, "base": 3095.58}],
      "deuda_base": 3095.58, "avales": [],
      "docs": {"total": 16, "aprobados": 12, "cliente": [d(111), d(57), d(35), d(13)], "eipsa": []},
      "recl_eipsa": [date(2099, 1, 8), date(2099, 3, 1)], "correos": []}


def c(mid, dia, auto=False):
    return {"msgid": mid, "fecha": datetime(2099, 10, dia, 9, 0), "automatico": auto, "asunto": mid}


def test_guardado():
    tx.guardar_texto("Cliente / Ficticio: S.A.", {"pos": {"1099010610": {"situacion": "Texto de JP"}}})
    g = tx.cargar_texto("Cliente / Ficticio: S.A.")
    ok(g["pos"]["1099010610"]["situacion"] == "Texto de JP" and g["correos"] == {} and g["carpetas"] == [], g)
    ok((TMP / "expedientes" / "cliente-ficticio-s-a.json").exists(), list(TMP.rglob("*")))
    ok(tx.cargar_texto("Otro")["contexto"] == {}, "cliente sin guardar → vacío")
    ok(tx.elegir("", "auto") == "auto" and tx.elegir("JP", "auto") == "JP" and tx.elegir(None, "auto") == "auto", "elegir")


def test_lo_esencial():
    v = tx.lo_esencial(PO, date(2099, 11, 19))
    ok(v[0].startswith("Nos deben 3.095,58 € sin IVA en 1 factura(s); la más antigua (F-99/061, 20/02/2099) lleva 272 días"), v[0])
    ok(v[1] == "Material entregado (última entrega 30/07/2099).", v[1])
    ok(v[2] == "Documentación: 12 de 16 aprobados; 4 esperando al cliente (el más antiguo, 111 días); 0 en EIPSA.", v[2])
    ok(v[3] == "Al menos 2 reclamaciones o actualizaciones por escrito desde el 08/01/2099.", v[3])
    sin = dict(PO, facturas=[], deuda_base=0.0, avales=[{"importe": 1000.0, "vence": "30/01/2100"}], recl_eipsa=[])
    v2 = tx.lo_esencial(sin, date(2099, 11, 19))
    ok(v2[0] == "No hay facturas pendientes: el 10 % de documentación final ya está cobrado.", v2[0])
    ok(v2[1] == "Avales en vigor: 1.000,00 € (vencen el 30/01/2100).", v2[1])
    ok(not any(x.startswith("Al menos") for x in v2), "sin reclamaciones no hay viñeta")


def test_punto():
    ok(tx.punto_auto(PO) == ("4 documentos esperando al cliente; el más antiguo lleva 111 días.",
                             "Reclamar la devolución de los 4 documentos."), tx.punto_auto(PO))
    solo_eipsa = dict(PO, docs={"total": 3, "aprobados": 2, "cliente": [], "eipsa": [d(5)]})
    ok(tx.punto_auto(solo_eipsa) == ("Pendiente de EIPSA: 1 documentos.", "Corregir y reenviar."), tx.punto_auto(solo_eipsa))
    nada = dict(PO, docs={"total": 3, "aprobados": 3, "cliente": [], "eipsa": []})
    ok(tx.punto_auto(nada) == ("Documentación completa.", "Facturar lo pendiente."), tx.punto_auto(nada))
    ok(tx.que_falta(d(1), "cliente") == "Que el cliente lo devuelva aprobado." and
       tx.que_falta(d(1), "eipsa") == "Corregir y reenviar.", "que_falta")


def test_ultimos():
    cs = [c(f"m{i:02d}", 10 + i) for i in range(12)] + [c("auto", 28, auto=True), c("m-viejo", 1)]
    u = tx.ultimos(dict(PO, correos=cs), {"correos": {"m-viejo": {"importante": True}}})
    ok(len(u) == 11 and u[0]["msgid"] == "m11" and u[-1]["msgid"] == "m-viejo", [x["msgid"] for x in u])
    ok("auto" not in [x["msgid"] for x in u], "los automáticos no entran")
    ok(len(tx.ultimos(dict(PO, correos=cs), {}, n=3)) == 3, "n")


test_guardado()
test_lo_esencial()
test_punto()
test_ultimos()

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
