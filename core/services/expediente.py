"""Expediente de un cliente que no paga: los datos de cada PO, en un sitio.

Cuando un cliente retiene pagos con la excusa de la documentación, hay que
contar PO a PO qué falta y de qué lado está, qué nos deben, qué se ha
reclamado y con quién hablar. Este módulo junta eso sin interfaz: devuelve
diccionarios planos que leen las salidas (Excel, Word) y la pantalla de
revisión. Ver docs/superpowers/specs/2026-11-23-expediente-cliente-design.md.

Un **PO** es el pedido del cliente; en el ERP agrupa varios pedidos nuestros
(P-99/048, P-99/080…) y sus suplementos. La relación está en
`orders.num_ref_order`, escrita de muchas formas para el mismo PO
(`109901071`, `1099010710-00`, `1099010710 Sup.04`, a veces con un dígito de
menos): se agrupa por los 9 primeros dígitos y lo que no encaje lo corrige JP.

Todo es lectura: ERP, DocFlow, buzón.
"""
from __future__ import annotations

import re
from collections import Counter

from core.services.erp_common import norm_order

_NO_DIGITO = re.compile(r"\D")


def _digitos(ref) -> str:
    return _NO_DIGITO.sub("", str(ref or ""))


def clave_po(ref: str | None, pedido: str) -> str:
    """Clave de agrupación: los 9 primeros dígitos de la referencia del PO.

    Sin una referencia con al menos 9 dígitos, el pedido (sin sufijo de
    suministro) hace de clave: así un pedido sin PO no se pierde."""
    d = _digitos(ref)
    if len(d) >= 9:
        return d[:9]
    return norm_order(pedido) or str(pedido or "").strip()


def agrupar(ordenes: list[dict], extra: dict[str, list[str]] | None = None) -> dict[str, dict]:
    """{clave: {"po", "pedidos", "ordenes"}} a partir de las filas de pedidos.

    `extra` = {po: [pedido]} guardado por JP: esos pedidos van a ese PO aunque
    su referencia diga otra cosa."""
    destino = {}
    for po, peds in (extra or {}).items():
        k = clave_po(po, po)
        for p in peds:
            destino[norm_order(p) or p] = (k, po)

    grupos: dict[str, dict] = {}
    candidatos: dict[str, Counter] = {}
    forzado: dict[str, str] = {}
    for o in ordenes:
        pedido = norm_order(o.get("num_order")) or str(o.get("num_order") or "")
        if pedido in destino:
            k, po = destino[pedido]
            forzado.setdefault(k, po)
        else:
            k = clave_po(o.get("num_ref_order"), o.get("num_order"))
        g = grupos.setdefault(k, {"po": k, "pedidos": [], "ordenes": []})
        g["ordenes"].append(o)
        if pedido and pedido not in g["pedidos"]:
            g["pedidos"].append(pedido)
        d = _digitos(o.get("num_ref_order"))
        if len(d) >= 10 and d[:9] == k:
            candidatos.setdefault(k, Counter())[d[:10]] += 1

    for k, g in grupos.items():
        g["pedidos"].sort()
        if candidatos.get(k):
            g["po"] = candidatos[k].most_common(1)[0][0]
        elif len(_digitos(forzado.get(k))) >= 10:
            g["po"] = _digitos(forzado[k])[:10]
    return grupos
