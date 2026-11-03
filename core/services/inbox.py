"""Servicio Inbox — lectura de correos IMAP con flag is_read y detalle completo.

Port simplificado de inbox_service del DocFlow grande. El análisis con IA de un
correo (`analizar`) es opcional: solo funciona con la clave de Ajustes ▸ IA.
"""

import imaplib
import logging
from email.utils import parsedate_to_datetime

from core.config import IMAP_HOST, IMAP_PASS, IMAP_PORT, IMAP_USER
from core.services import imap as imap_service

logger = logging.getLogger(__name__)

_CAMPOS = "(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])"
_decode_header_value = imap_service._decode_header_value


def _connect(folder: str = "INBOX", escribir: bool = False) -> imaplib.IMAP4_SSL:
    """En solo lectura (EXAMINE) salvo para marcar como no leído."""
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(IMAP_USER, IMAP_PASS)
    conn.select(folder, readonly=not escribir)
    return conn


def list_emails(folder: str = "INBOX", filter: str = "all", limit: int = 200) -> list[dict]:
    """Lista correos con flag is_read.

    filter: 'all' | 'unread' | 'read'
    """
    conn = _connect(folder)
    try:
        criterion = {
            "unread": "UNSEEN",
            "read":   "SEEN",
        }.get(filter, "ALL")
        _, data = conn.search(None, criterion)
        uids = data[0].split() if data and data[0] else []
        # Más recientes primero, recortado al límite
        uids = list(reversed(uids))[:limit]

        # En lote y solo las tres cabeceras que se enseñan: antes era una
        # petición al servidor por correo (hasta 200) con la cabecera entera.
        return [{"uid": c["seq"],
                 "subject": _decode_header_value(c["msg"].get("Subject", "")),
                 "from": _decode_header_value(c["msg"].get("From", "")),
                 "date": c["date"],
                 "is_read": "\\Seen" in c["flags"]}
                for c in imap_service.cabeceras_en_lote(conn, uids, _CAMPOS)]
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()


def contar_no_leidos(folder: str = "INBOX") -> int:
    """Cuántos correos sin leer hay: una búsqueda, sin bajar ninguna cabecera
    (Inicio solo enseña el número)."""
    conn = _connect(folder)
    try:
        _, data = conn.search(None, "UNSEEN")
        return len(data[0].split()) if data and data[0] else 0
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()


def get_email_detail(uid: str, folder: str = "INBOX") -> dict:
    """Detalle completo del email: cabeceras + cuerpos HTML/plain."""
    msg = imap_service.fetch_email(uid, folder)

    subject = _decode_header_value(msg.get("Subject", ""))
    sender = _decode_header_value(msg.get("From", ""))
    to = _decode_header_value(msg.get("To", ""))
    cc = _decode_header_value(msg.get("Cc", ""))
    date_str = msg.get("Date", "")
    try:
        date_iso = parsedate_to_datetime(date_str).isoformat()
    except Exception:
        date_iso = date_str

    html_body = imap_service.get_html_body(msg) or ""
    plain_body = imap_service.get_plain_body(msg) or ""

    return {
        "uid": uid,
        "subject": subject,
        "from": sender,
        "to": to,
        "cc": cc,
        "date": date_iso,
        "html_body": html_body,
        "plain_body": plain_body,
    }


# ── Análisis IA (opcional: solo con clave, core.services.ia) ─────────────────

def cuerpo_legible(d: dict) -> str:
    """El texto del correo: el plano o, si no hay, el HTML pasado a texto."""
    return d.get("plain_body") or html_to_text(d.get("html_body", ""))


def prompt_analisis(d: dict) -> str:
    """Lo que se le pide a Claude sobre un correo del buzón de documentación."""
    return (
        "Eres el asistente del Document Controller de EIPSA, un fabricante de "
        "instrumentación que envía documentación técnica (cálculos, planos, "
        "procedimientos, dosieres) a sus clientes y recibe sus devoluciones con "
        "comentarios. Analiza este correo del buzón de documentación y responde "
        "en español, en texto plano sin Markdown, con estas cuatro líneas:\n"
        "Resumen: qué dice, en una o dos frases.\n"
        "Qué piden: lo que esperan de nosotros, o «nada» si es informativo.\n"
        "Referencias: pedidos (P-xx/xxx), documentos, transmittals o revisiones "
        "que se mencionen, o «ninguna».\n"
        "Siguiente paso: la acción concreta que propones y si corre prisa.\n"
        "No inventes datos que no estén en el correo.\n\n"
        f"Asunto: {d.get('subject') or '(sin asunto)'}\n"
        f"De: {d.get('from', '')}\n"
        f"Para: {d.get('to', '')}\n"
        + (f"Cc: {d['cc']}\n" if d.get("cc") else "")
        + f"Fecha: {d.get('date', '')}\n\n"
        f"Mensaje:\n{cuerpo_legible(d) or '(sin cuerpo legible)'}"
    )


def analizar(d: dict) -> str | None:
    """El análisis de Claude de un correo, o None sin clave o si falla."""
    from core.services import ia
    return ia.redactar(prompt_analisis(d))


def mark_read(uid: str, folder: str = "INBOX") -> None:
    imap_service.mark_as_read(uid, folder)


def mark_unread(uid: str, folder: str = "INBOX") -> None:
    """Quita el flag \\Seen del email."""
    conn = _connect(folder, escribir=True)
    try:
        target = uid.encode() if isinstance(uid, str) else uid
        conn.store(target, "-FLAGS", "\\Seen")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()


# ── Extracción de texto plano legible ─────────────────────────────────────────

def html_to_text(html: str) -> str:
    """Convierte HTML a texto plano legible (mantiene saltos de párrafo)."""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        # Eliminar style/script
        for tag in soup(["style", "script"]):
            tag.decompose()
        # Mejor representación de saltos
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for block in soup.find_all(["p", "div", "tr", "h1", "h2", "h3", "h4", "li"]):
            block.append("\n")
        text = soup.get_text(separator=" ")
        # Limpiar espacios y saltos múltiples
        lines = [ln.strip() for ln in text.splitlines()]
        out = []
        prev_blank = False
        for ln in lines:
            if not ln:
                if not prev_blank and out:
                    out.append("")
                prev_blank = True
            else:
                out.append(ln)
                prev_blank = False
        return "\n".join(out).strip()
    except Exception as exc:
        logger.warning("html_to_text fallback: %s", exc)
        # Fallback simple
        import re
        t = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", t).strip()
