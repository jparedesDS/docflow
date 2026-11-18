"""Plazos: lo que dice el ERP de cada pedido (solo lectura).

  · Pedidos con su oferta: recepción y presentación de la oferta, responsable
    comercial, fecha del pedido, entrega contractual, envío y avance del taller.
  · Compras: primer pedido a proveedor y cuándo llegó todo el material
    (`purch_fact`; el pedido nuestro sale de `notes`, como en `purchases.py`).
  · OTs: la primera OT lanzada (paso a fábrica) y el primer fichaje.

Las consultas lanzan si el ERP no responde: quien llama decide qué hacer.
"""

from __future__ import annotations

import re
from datetime import date

from core.services.erp_common import as_date, clean, query, who

_SQL_PEDIDOS = """
    SELECT o.num_order, o.num_offer, f.client, f.final_client, f.material, f.responsible,
           f.recep_date, f.presentation_date, o.order_date, o.expected_date,
           o.last_date_deliveries, o.porc_workshop, o.closed
    FROM public.orders o
    LEFT JOIN public.offers f ON f.num_offer = o.num_offer
    WHERE o.order_year = ANY(%s) AND o.num_order LIKE 'P-%%'
    ORDER BY o.num_order
"""

_SQL_COMPRAS = """
    SELECT h.notes, h.order_date, d.pending, h.deliv_date_1 AS h1, h.deliv_date_2 AS h2,
           h.deliv_date_3 AS h3, d.deliv_date_1, d.deliv_date_2, d.deliv_date_3
    FROM purch_fact.supplier_ord_detail d
    JOIN purch_fact.supplier_ord_header h ON h.id = d.supplier_ord_header_id
    WHERE h.order_date >= %s
"""

_SQL_OTS = """
    SELECT f.tag, f.start_date, i.primer_fichaje
    FROM fabrication.fab_order f
    LEFT JOIN (SELECT number_ot::text AS ot, min(date_ot) AS primer_fichaje
               FROM fabrication.imp_ot GROUP BY 1) i ON i.ot = f.ot_num::text
    WHERE f.ot_num IS NOT NULL AND f.start_date >= %s
"""

_RE_PEDIDO = re.compile(r"^\s*P-(\d{2})/(\d{1,3})(?:\s*-\s*(S\d{2}[A-Z]?))?", re.I)

# Un pedido dentro de un texto libre, con su suministro si lo dice:
# «P-99/071-S00», «P-98/066 S06», «P-99/27-S1», «P-99/022 Y ALMACEN»
_RE_EN_TEXTO = re.compile(r"\bP(?!A)\s*-?\s*(\d{2})\s*[/-]\s*(\d{1,3})(?:\s*-?\s*S\s*(\d{1,2})([A-Z]?)(?![A-Z0-9]))?",
                          re.I)


def _claves(texto) -> list[str]:
    """Pedidos de un texto: «P-99/071-S00» si dice el suministro, «P-99/071» si no."""
    out = []
    for yy, nnn, sxx, letra in _RE_EN_TEXTO.findall(str(texto or "")):
        clave = f"P-{yy}/{int(nnn):03d}" + (f"-S{int(sxx):02d}{letra.upper()}" if sxx else "")
        if clave not in out:
            out.append(clave)
    return out


def _q(sql: str, params, label: str) -> list[dict]:
    return query(sql, params)


def _pedido(num_order: str) -> tuple[str, str] | None:
    """'P-99/021-S03R' → ('P-99/021-S03R', 'P-99/021'); sin suministro → S00."""
    m = _RE_PEDIDO.match(num_order or "")
    if not m:
        return None
    base = f"P-{m[1]}/{int(m[2]):03d}"
    return f"{base}-{(m[3] or 'S00').upper()}", base


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def pedidos(años: list[int]) -> list[dict]:
    """Los pedidos P de esos años, en el formato que espera `seguimiento.construir_filas`."""
    out = []
    for r in _q(_SQL_PEDIDOS, (list(años),), "pedidos"):
        p = _pedido(clean(r.get("num_order")))
        if not p:
            continue
        out.append({
            "pedido": p[0], "base": p[1],
            "oferta": clean(r.get("num_offer")),
            "cliente": clean(r.get("final_client")) or clean(r.get("client")),
            "equipo": clean(r.get("material")),
            "responsable": who(r.get("responsible")),
            "recep_date": as_date(r.get("recep_date")),
            "presentation_date": as_date(r.get("presentation_date")),
            "order_date": as_date(r.get("order_date")),
            "expected_date": as_date(r.get("expected_date")),
            "envio": as_date(r.get("last_date_deliveries")),
            "porc_taller": _int(r.get("porc_workshop")),
            "cerrado": clean(r.get("closed")).upper() == "OK",
        })
    return out


def compras(desde: date) -> dict[str, dict]:
    """{"P-99/071-S00" o, si la nota no dice el suministro, "P-99/071": {"primer_pedido", "ultima_recepcion", "pendiente"}}."""
    out: dict[str, dict] = {}
    for r in _q(_SQL_COMPRAS, (desde,), "compras"):
        fecha = as_date(r.get("order_date"))
        recepciones = [as_date(r.get(k)) for k in ("deliv_date_1", "deliv_date_2", "deliv_date_3",
                                                    "h1", "h2", "h3")]
        recepciones = [d for d in recepciones if d]
        try:
            pendiente = float(r.get("pending") or 0)
        except (TypeError, ValueError):
            pendiente = 0.0
        for clave in _claves(r.get("notes")):
            x = out.setdefault(clave, {"primer_pedido": None, "ultima_recepcion": None, "pendiente": 0.0})
            if fecha and (x["primer_pedido"] is None or fecha < x["primer_pedido"]):
                x["primer_pedido"] = fecha
            for d in recepciones:
                if x["ultima_recepcion"] is None or d > x["ultima_recepcion"]:
                    x["ultima_recepcion"] = d
            x["pendiente"] += pendiente
    return out


def ots(desde: date) -> dict[str, dict]:
    """{"P-99/071-S00" o "P-99/071" (sin suministro en el tag): {"primera_ot", "primer_fichaje"}}."""
    out: dict[str, dict] = {}
    for r in _q(_SQL_OTS, (desde,), "ots"):
        inicio, fichaje = as_date(r.get("start_date")), as_date(r.get("primer_fichaje"))
        for clave in _claves(r.get("tag")):
            x = out.setdefault(clave, {"primera_ot": None, "primer_fichaje": None})
            if inicio and (x["primera_ot"] is None or inicio < x["primera_ot"]):
                x["primera_ot"] = inicio
            if fichaje and (x["primer_fichaje"] is None or fichaje < x["primer_fichaje"]):
                x["primer_fichaje"] = fichaje
    return out
