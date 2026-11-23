"""Texto del expediente de un cliente: el automático y el que escribe JP.

Las cifras y las frases que salen de los datos se escriben solas («Quedan 4
documentos con el cliente; el más antiguo lleva 111 días»). Lo que solo sabe JP
(que unos certificados hay que actualizarlos, para qué PO prepara el cliente el
cierre…) lo escribe él en la pantalla de revisión, y se guarda por cliente en
`state/expedientes/<cliente>.json`. **Lo de JP manda**: si hay texto guardado,
se usa ese; si no, el automático.

Estilo: frases cortas, en primera persona del plural cuando habla EIPSA, sin
firma ni nombres de gente de la casa.
"""
from __future__ import annotations

from datetime import date

from core.paths import state_dir
from core.services.expediente import slug
from core.utils.json_store import read_json, write_json

VACIO = {"contexto": {}, "pos": {}, "correos": {}, "contactos": {}, "carpetas": [], "pedidos_extra": {}}


def _ruta(cliente: str):
    return state_dir() / "expedientes" / f"{slug(cliente)}.json"


def cargar_texto(cliente: str) -> dict:
    datos = read_json(str(_ruta(cliente)), default={}) or {}
    return {k: datos.get(k, type(v)()) for k, v in VACIO.items()} | {k: v for k, v in datos.items() if k not in VACIO}


def guardar_texto(cliente: str, datos: dict) -> None:
    """Guarda lo que se pasa sin borrar lo demás: lo de JP no se pisa."""
    write_json(str(_ruta(cliente)), {**cargar_texto(cliente), **datos})


def elegir(guardado: str | None, auto: str) -> str:
    return guardado if (guardado or "").strip() else auto


def eur(v: float) -> str:
    """3095.58 → '3.095,58 €'."""
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _dmy(d) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def lo_esencial(po: dict, hoy: date) -> list[str]:
    """Las viñetas de «lo esencial» de un PO, en orden."""
    out = []
    fs = po.get("facturas") or []
    if fs:
        v = max(fs, key=lambda f: f.get("dias") or 0)
        out.append(f"Nos deben {eur(po.get('deuda_base', 0.0))} sin IVA en {len(fs)} factura(s); la más antigua "
                   f"({v['numero']}, {_dmy(v.get('fecha'))}) lleva {v.get('dias', 0)} días sin cobrar.")
    elif po.get("cobrado_10"):
        out.append("No hay facturas pendientes: el 10 % de documentación final ya está cobrado.")
    else:
        out.append("No hay facturas emitidas pendientes de cobro.")
    ver = po.get("verificar") or []
    if ver:
        out.append(f"Hay {len(ver)} factura(s) por confirmar con Administración ({', '.join(f['numero'] for f in ver)}): "
                   "se reemitió para confirming y no consta el cobro.")
    if po.get("avales"):
        tot = sum(a.get("importe", 0.0) for a in po["avales"])
        out.append(f"Avales en vigor: {eur(tot)} (vencen el {po['avales'][0].get('vence', '')}).")
    if po.get("ultima_entrega"):
        out.append(f"Material entregado (última entrega {_dmy(po['ultima_entrega'])}).")
    d = po.get("docs") or {}
    cli, eip = d.get("cliente") or [], d.get("eipsa") or []
    mx = max((x.get("dias") or 0 for x in cli), default=0)
    out.append(f"Documentación: {d.get('aprobados', 0)} de {d.get('total', 0)} aprobados; {len(cli)} esperando al cliente"
               + (f" (el más antiguo, {mx} días)" if cli else "") + f"; {len(eip)} en EIPSA.")
    if po.get("recl_eipsa"):
        out.append(f"Al menos {len(po['recl_eipsa'])} reclamaciones o actualizaciones por escrito desde el "
                   f"{_dmy(po['recl_eipsa'][0])}.")
    return out


def punto_auto(po: dict) -> tuple[str, str]:
    """(en qué punto estamos, siguiente paso) a partir de la documentación."""
    d = po.get("docs") or {}
    cli, eip = d.get("cliente") or [], d.get("eipsa") or []
    if cli:
        mx = max((x.get("dias") or 0 for x in cli), default=0)
        return (f"{len(cli)} documentos esperando al cliente; el más antiguo lleva {mx} días.",
                f"Reclamar la devolución de los {len(cli)} documentos.")
    if eip:
        return f"Pendiente de EIPSA: {len(eip)} documentos.", "Corregir y reenviar."
    return "Documentación completa.", "Facturar lo pendiente."


def que_falta(doc: dict, lado: str) -> str:
    return "Que el cliente lo devuelva aprobado." if lado == "cliente" else "Corregir y reenviar."


def ultimos(po: dict, guardado: dict, n: int = 10) -> list[dict]:
    """Los `n` correos más recientes que no son avisos automáticos, más los
    marcados como importantes, del más reciente al más antiguo."""
    marcados = {k for k, v in (guardado or {}).get("correos", {}).items() if v.get("importante")}
    cs = sorted(po.get("correos") or [], key=lambda c: c["fecha"], reverse=True)
    elegidos = [c for c in cs if not c.get("automatico")][:n]
    ids = {c["msgid"] for c in elegidos}
    elegidos += [c for c in cs if c["msgid"] in marcados and c["msgid"] not in ids]
    return sorted(elegidos, key=lambda c: c["fecha"], reverse=True)
