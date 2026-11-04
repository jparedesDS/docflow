"""Activaciones de pedidos: el correo de Comercial que abre un pedido nuevo.

Comercial avisa con «ACTIVACIÓN P-99/001-S04 / CLIENTE» cuando entra una orden
de compra, siempre con la misma plantilla:

    Hemos recibido la orden de compra 4500012345-04 de CLIENTE / PROYECTO.
    Nuestro pedido es P-99/001-S04.
    La fecha de entrega contractual es 30-04-2099.
    El plazo de entrega acordado es 26/28 semanas.
    INFORMACIÓN ADICIONAL: …   EXTRAS: …   DOCUMENTACIÓN: …

Para el Document Controller eso es trabajo: abrir el pedido (00 DOCUMENTACIÓN,
Planning, VDDL) y empezar con la documentación. Cada activación es una tarea
en la Agenda, «Abrir pedido …», que lleva los datos del correo para rellenar
«Nuevo pedido» con un clic.

La tarea se cierra sola al procesar el pedido en «Nuevo pedido», o cuando en su
00 DOCUMENTACIÓN ya hay un Planning o un VDDL de después del correo (se abrió
por otro lado). Los correos se leen en la misma pasada que los avisos de
cálculos (`avisos_calculos.revisar`), con el mismo registro de Message-ID.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from core.services import agenda

logger = logging.getLogger(__name__)

ORIGEN = "activacion"

# «ACTIVACIÓN …», también reenviada; una respuesta («RE: ACTIVACIÓN») es charla, no otra activación
_RE_ASUNTO = re.compile(r"^\s*(?:(?:rv|fw|fwd|tr|reenv\w*)\s*:\s*)*activaci[oó]n\b", re.I)
_RE_PEDIDO = re.compile(r"\b(PA?)\s*-\s*(\d{2})\s*[/\-]\s*(\d{3})(?:\s*-\s*S\s*(\d{2}[A-Z]?))?", re.I)
_RE_NUESTRO = re.compile(r"nuestro\s+pedido\s+es\s+([^\n]+)", re.I)
_RE_PO = re.compile(r"orden\s+de\s+compra\s+(.+?)\s+de\s+(.+?)\s*\.?\s*$", re.I | re.M)
_RE_ENTREGA = re.compile(r"entrega\s+contractual\s+es\s+(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{2,4})",
                         re.I)
_RE_PLAZO = re.compile(r"plazo\s+de\s+entrega\s+acordado\s+es\s+(.+?)\s*\.?\s*$", re.I | re.M)
# Los tres apartados del final, cada uno hasta el siguiente
_RE_APARTADO = re.compile(r"^\s*(informaci[oó]n\s+adicional|extras|documentaci[oó]n)\s*:\s*(.*)$", re.I)
_RE_FIN = re.compile(r"^\s*(un saludo|saludos|atentamente|gracias|nota legal|espa[ñn]ola de instrumentaci)",
                     re.I)
_RE_CITA = re.compile(r"^\s*(de|from|enviado el|sent)\s*:|^\s*-{2,}\s*(mensaje original|original message)",
                      re.I)
_APARTADOS = {"informacion adicional": "info", "extras": "extras", "documentacion": "documentacion"}


def es_asunto(asunto: str) -> bool:
    """¿Este asunto (ya descodificado) es el de una activación?"""
    return bool(_RE_ASUNTO.match(asunto or ""))


def _sin_acentos(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn")


def _pedido(texto: str):
    m = _RE_PEDIDO.search(texto or "")
    if not m:
        return None
    return f"{m[1].upper()}-{m[2]}/{m[3]}", (f"S{m[4].upper()}" if m[4] else "")


def _apartados(texto: str) -> dict:
    """INFORMACIÓN ADICIONAL, EXTRAS y DOCUMENTACIÓN → sus líneas."""
    out = {"info": [], "extras": [], "documentacion": []}
    actual = None
    for ln in (texto or "").splitlines():
        if _RE_FIN.match(ln) or _RE_CITA.match(ln):
            break
        m = _RE_APARTADO.match(ln)
        if m:
            actual = _APARTADOS[re.sub(r"\s+", " ", _sin_acentos(m[1]).lower())]
            ln = m[2]
        if actual is None:
            continue
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            out[actual].append(ln if len(ln) <= 220 else ln[:219] + "…")
    return {k: v[:10] for k, v in out.items()}


def analizar(asunto: str, texto: str, remitente: str = "", fecha_iso: str = "",
             message_id: str = "") -> dict | None:
    """Asunto y cuerpo de un correo → la activación, o None si no lo es.

    El pedido sale de «Nuestro pedido es …» (el asunto a veces lo abrevia) y,
    si no, del asunto."""
    from core.services.avisos_calculos import _fecha_corta, _nombre_de_correo
    from email.utils import parseaddr

    asunto = (asunto or "").strip()
    if not es_asunto(asunto):
        return None
    texto = texto or ""
    mn = _RE_NUESTRO.search(texto)
    ped = (_pedido(mn[1]) if mn else None) or _pedido(asunto)
    if not ped:
        return None
    pedido, supp = ped

    po, cliente, proyecto = "", "", ""
    mp = _RE_PO.search(texto)
    if mp:
        # «la orden de compra PO 123»: el «PO» sobra, ya se dice
        po = re.sub(r"^(?:P\.?O\.?|n[ºo°]\.?)\s*[:#]?\s+", "", mp[1].strip(), flags=re.I)
        partes = [p.strip() for p in mp[2].split("/")]
        cliente = partes[0]
        proyecto = " / ".join(p for p in partes[1:] if p)
    if not cliente:
        # «ACTIVACIÓN P-99/001-S00 / CLIENTE»: lo que va tras la última « / »
        cliente = asunto.rsplit(" / ", 1)[1].strip() if " / " in asunto else ""

    entrega = ""
    me = _RE_ENTREGA.search(texto)
    if me:
        d, m_, a = int(me[1]), int(me[2]), int(me[3])
        a += 2000 if a < 100 else 0
        try:
            entrega = date(a, m_, d).isoformat()
        except ValueError:
            entrega = ""
    mz = _RE_PLAZO.search(texto)
    plazo = mz[1].strip() if mz else ""

    ap = _apartados(texto)
    nombre, correo = parseaddr(remitente or "")
    nombre = nombre.strip().strip("'\"").strip()
    if not nombre or "-" in nombre or "@" in nombre:
        nombre = _nombre_de_correo(correo) or nombre

    return {
        "pedido": pedido,
        "supp": supp,
        "pedido_completo": f"{pedido}-{supp}" if supp else pedido,
        "po": po,
        "cliente": cliente,
        "proyecto": proyecto,
        "entrega": entrega,                     # ISO, «» si no viene
        "plazo": plazo,
        "info": ap["info"],
        "extras": ap["extras"],
        "documentacion": " · ".join(ap["documentacion"]),
        "remitente": nombre,
        "remitente_correo": (correo or "").lower(),
        "fecha": _fecha_corta(fecha_iso),
        "recibido": fecha_iso or "",
        "message_id": message_id or "",
        "asunto": asunto,
    }


def _fecha_es(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d-%m-%Y")
    except (TypeError, ValueError):
        return ""


def tarea_de(act: dict, owner: str = agenda.DEFAULT_OWNER) -> dict:
    """La tarea «Abrir pedido …» de una activación."""
    titulo = f"Abrir pedido {act['pedido_completo']}"
    if act.get("cliente"):
        titulo += f" · {act['cliente']}"
    partes = []
    if act.get("po"):
        partes.append(f"PO {act['po']}")
    if act.get("proyecto"):
        partes.append(act["proyecto"])
    if act.get("entrega"):
        partes.append(f"entrega {_fecha_es(act['entrega'])}"
                      + (f" ({act['plazo']})" if act.get("plazo") else ""))
    elif act.get("plazo"):
        partes.append(f"plazo {act['plazo']}")
    if act.get("documentacion"):
        partes.append(f"Documentación: {act['documentacion']}")
    notas = list(act.get("info") or [])
    if act.get("extras"):
        notas.append("Extras: " + ", ".join(act["extras"]))
    return {
        "titulo": titulo,
        "descripcion": " · ".join(partes + notas),
        "prioridad": "media",
        "estado": "pendiente",
        "fecha_limite": act.get("fecha", ""),
        "asignado": owner,
        "origen": ORIGEN,
        "source_msgid": act.get("message_id", ""),
        "pedido": act["pedido"],
        "supp": act.get("supp", ""),
        "cliente": act.get("cliente", ""),
        "notas": notas,
        "remitente": act.get("remitente", ""),
        "recibido": act.get("recibido", ""),
        # Lo que rellena «Nuevo pedido»
        "activacion": {k: act.get(k, "") for k in
                       ("po", "cliente", "proyecto", "entrega", "plazo", "documentacion")},
        "actualizaciones": [],
    }


# ── Las tareas ────────────────────────────────────────────────────────────────

def pendientes(owner: str = agenda.DEFAULT_OWNER) -> list[dict]:
    """Las activaciones aún sin abrir, la más reciente primero."""
    abiertas = [t for t in agenda.get_tareas(owner)
                if t.get("origen") == ORIGEN and t.get("estado") != "completada"]
    return sorted(abiertas, key=lambda t: t.get("recibido") or "", reverse=True)


def _misma(t: dict, pedido: str, supp: str) -> bool:
    return (t.get("pedido") or "").upper() == pedido.upper() and \
        (not supp or not t.get("supp") or t["supp"].upper() == supp.upper())


def existe(owner: str, pedido: str, supp: str) -> bool:
    """¿Ya hay una tarea de activación (abierta o no) de ese pedido y suministro?
    Una activación reenviada no es trabajo nuevo."""
    return any(t.get("origen") == ORIGEN and (t.get("pedido") or "").upper() == pedido.upper()
               and (t.get("supp") or "").upper() == (supp or "").upper()
               for t in agenda.get_tareas(owner))


def cerrar(pedido: str, supp: str = "", owner: str = agenda.DEFAULT_OWNER,
           motivo: str = "abierto en Nuevo pedido") -> list[dict]:
    """Completa las activaciones abiertas de ese pedido (y suministro, si se da).

    `pedido` vale con guiones o con barra: «P-99-001» o «P-99/001»."""
    m = _pedido(pedido)
    if not m:
        return []
    ped, supp_ped = m
    supp = (supp or supp_ped or "").upper()
    hoy = date.today().strftime("%d-%m-%Y")
    cerradas = []
    for t in pendientes(owner):
        if _misma(t, ped, supp):
            hecha = agenda.update("tareas", t["id"], {"estado": "completada", "cerrada_sola": hoy,
                                                      "cerrada_por": motivo})
            if hecha:
                cerradas.append(hecha)
    return cerradas


def _ya_abierto(t: dict, base_dir=None) -> bool:
    """¿Su 00 DOCUMENTACIÓN tiene un Planning o un VDDL de después del correo?"""
    from core.services import apertura
    desde = None
    try:
        desde = datetime.fromisoformat(t.get("recibido") or "").date()
    except ValueError:
        return False
    pedido = t.get("pedido") or ""
    nombres = [f"{pedido}-{t['supp']}", pedido] if t.get("supp") else [pedido]
    kw = {"base_dir": Path(base_dir)} if base_dir else {}
    vistas = set()
    for nombre in nombres:
        try:
            doc = apertura.find_documentacion_dir(nombre, create=False, **kw)
        except Exception:  # noqa: BLE001 — M: puede no estar
            doc = None
        if doc is None or doc in vistas or not doc.exists():
            continue
        vistas.add(doc)
        for f in doc.iterdir():
            n = f.name.upper()
            if f.is_file() and (n.startswith("03 PLANNING - ") or n.startswith("01 IMPORTAR DOCUMENTOS - ERP - P")):
                try:
                    if date.fromtimestamp(f.stat().st_mtime) >= desde:
                        return True
                except OSError:
                    continue
    return False


def cerrar_abiertas(owner: str = agenda.DEFAULT_OWNER, base_dir=None) -> list[dict]:
    """Cierra las activaciones cuyo pedido ya se abrió (por la app o a mano)."""
    cerradas = []
    hoy = date.today().strftime("%d-%m-%Y")
    for t in pendientes(owner):
        if _ya_abierto(t, base_dir):
            hecha = agenda.update("tareas", t["id"], {"estado": "completada", "cerrada_sola": hoy,
                                                      "cerrada_por": "ya tiene Planning/VDDL"})
            if hecha:
                cerradas.append(hecha)
    return cerradas
