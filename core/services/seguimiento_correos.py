"""Plazos: la hora de los correos de la cadena.

  · **Oferta recibida y contestada.** Los correos de los buzones de Ofertas
    (y su respuesta, buscada en Enviados por `ofertas.enrich_replies`) se
    enlazan con la oferta del ERP: el remitente está en `offers.mails` (lo que
    va tras «copia:» son direcciones nuestras y no cuentan) o la referencia del
    cliente sale en el asunto, y la fecha cae entre 3 días antes y 1 después de
    `recep_date`. Un correo sirve a una sola oferta: gana la más cercana.
  · **Activación.** Las tareas «Abrir pedido …» de la Agenda guardan la hora y
    el remitente del correo ACTIVACIÓN.

El buzón solo guarda lo reciente, así que lo enlazado se acumula en
`state/seguimiento_correos.json`: el histórico crece con cada pasada.
Buzones en solo lectura (lo que ya hace `ofertas`).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from core.services import agenda

logger = logging.getLogger(__name__)

VENTANA_ANTES, VENTANA_DESPUES = 3, 1
# Los buzones de Ofertas se leen enteros: lo que guarden (desde mayo de 2026 en
# los compartidos). Un año hacia atrás y hasta este número de correos por buzón.
DIAS_BUZON = 400
LIMITE_BUZON = 3000

_RE_EMAIL = re.compile(r"[\w.+\-]+@[\w.\-]+\.\w+")
_REF_GENERICAS = {"EMAIL", "MAIL", "CORREO", "-", "*"}
_RE_PO = re.compile(r"^\s*P\.?O\.?\s*\d+\s*$", re.I)


def _cache_por_defecto() -> Path:
    from core.paths import state_dir
    return state_dir() / "seguimiento_correos.json"


def _dt(v) -> datetime | None:
    """Hora local sin zona: las cabeceras traen la del remitente (o ninguna, con «-0000»)
    y mezclarlas daría días corridos o un TypeError al comparar."""
    if not isinstance(v, datetime):
        try:
            v = datetime.fromisoformat(str(v)) if v else None
        except ValueError:
            return None
    if v is not None and v.tzinfo is not None:
        v = v.astimezone().replace(tzinfo=None)
    return v


def ref_util(ref: str) -> bool:
    """¿Sirve esta referencia del cliente para reconocer su correo?"""
    r = (ref or "").strip()
    if not r or r.upper() in _REF_GENERICAS or _RE_PO.match(r):
        return False
    return sum(c.isalnum() for c in r) >= 5


def _correos_cliente(mails: str) -> set[str]:
    antes = re.split(r"copia\s*:", mails or "", maxsplit=1, flags=re.I)[0]
    return {m.lower() for m in _RE_EMAIL.findall(antes)}


def _coincide(c: dict, o: dict) -> bool:
    if (c.get("from_email") or "").lower() in _correos_cliente(o.get("mails")):
        return True
    ref = o.get("num_ref_offer") or ""
    return ref_util(ref) and ref.strip().lower() in (c.get("subject") or "").lower()


def enlazar(correos: list[dict], ofertas_erp: list[dict]) -> dict[str, dict]:
    """{num_offer: {"recibido", "contestado", "contesta", "message_id"}}."""
    pares = []
    for i, c in enumerate(correos):
        cuando = _dt(c.get("date"))
        if not cuando:
            continue
        for o in ofertas_erp:
            recep = o.get("recep_date")
            if not isinstance(recep, date) or not o.get("num_offer"):
                continue
            delta = (cuando.date() - recep).days
            if -VENTANA_ANTES <= delta <= VENTANA_DESPUES and _coincide(c, o):
                pares.append((abs(delta), cuando.timestamp(), i, o["num_offer"]))
    pares.sort()
    usados, out = set(), {}
    for _dist, _t, i, num in pares:
        if i in usados or num in out:
            continue
        usados.add(i)
        c = correos[i]
        out[num] = {"recibido": _dt(c.get("date")), "contestado": _dt(c.get("answered_at")),
                    "contesta": c.get("answered_from") or "", "message_id": c.get("message_id") or ""}
    return out


# ── Lo que se lee de fuera (sustituible en las pruebas) ──────────────────────

def _buzon(dias: int) -> list[dict]:
    from core.services import ofertas
    correos = ofertas.fetch_inbox_offers(days=dias, force=True, limit=LIMITE_BUZON)
    return ofertas.enrich_replies(correos, days=dias, limit=LIMITE_BUZON)


def _ofertas_erp(desde: date) -> list[dict]:
    from core.services.erp_common import query
    return query("SELECT num_offer, recep_date, mails, num_ref_offer FROM public.offers "
                 "WHERE recep_date >= %s", (desde,))


# ── Caché acumulada ──────────────────────────────────────────────────────────

def _a_json(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}


def _de_json(d: dict) -> dict:
    return {**d, "recibido": _dt(d.get("recibido")), "contestado": _dt(d.get("contestado"))}


def cache(cache_file: Path | None = None) -> dict[str, dict]:
    """Lo enlazado hasta ahora, sin leer buzones."""
    from core.utils.json_store import read_json
    data = read_json(str(Path(cache_file) if cache_file else _cache_por_defecto()), default={}) or {}
    return {k: _de_json(v) for k, v in data.items() if isinstance(v, dict)}


def actualizar(dias: int = DIAS_BUZON, cache_file: Path | None = None) -> dict[str, dict]:
    """Lee los buzones de Ofertas, enlaza y acumula. Devuelve toda la caché."""
    from core.utils.json_store import write_json
    cache_file = Path(cache_file) if cache_file else _cache_por_defecto()
    actual = cache(cache_file)
    buzon = _buzon(dias)
    nuevos = enlazar(buzon, _ofertas_erp(date.today() - timedelta(days=dias + VENTANA_ANTES)))
    # Lo de un correo que sigue en el buzón se recalcula entero: puede que ahora
    # esté su oferta de verdad. Lo de correos que ya no están, se conserva.
    en_buzon = {c.get("message_id") for c in buzon if c.get("message_id")}
    actual = {k: v for k, v in actual.items() if v.get("message_id") not in en_buzon}
    usados = {v.get("message_id") for v in actual.values() if v.get("message_id")}
    for num, n in nuevos.items():
        if num in actual and actual[num].get("recibido"):
            continue            # ya enlazada con otro correo, que ya no está en el buzón
        if n.get("message_id") in usados:
            continue
        actual[num] = n
    write_json(str(cache_file), {k: _a_json(v) for k, v in actual.items()})
    return actual


# ── Activaciones ─────────────────────────────────────────────────────────────

def activaciones_por_pedido() -> dict[str, dict]:
    """{"P-99/001-S04": {"recibido", "remitente"}} de las tareas de activación."""
    from core.services.activaciones import ORIGEN
    out = {}
    for t in agenda.get_tareas(agenda.DEFAULT_OWNER):
        if t.get("origen") != ORIGEN or not t.get("pedido"):
            continue
        clave = f"{t['pedido']}-{(t.get('supp') or 'S00').upper()}"
        recibido = _dt(t.get("recibido"))
        if recibido and (clave not in out or recibido < out[clave]["recibido"]):
            out[clave] = {"recibido": recibido, "remitente": t.get("remitente") or ""}
    return out
