"""Piezas compartidas de la sección de devoluciones.

Fechas, remitentes, atajos para abrir carpetas y el mapeo de un pedido a sus
datos. Lo que usan las tres pantallas.
"""

import logging
import os
from datetime import datetime
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def _lookup_pedido(raw: str) -> dict | None:
    """Busca cliente / material / PO de un pedido en los datos del ERP.

    Acepta el Nº de pedido en cualquier formato (P-26/029, P-26-029, p26029…):
    normaliza quitando separadores y casa por prefijo (incluye suplementos)."""
    import re
    key = re.sub(r"[^0-9a-z]", "", (raw or "").lower())
    if len(key) < 4:
        return None
    try:
        from core.services import monitoring
        docs = monitoring.get_monitoring_data()
    except Exception:
        logger.debug("No se pudo cargar monitoring para autocompletar pedido", exc_info=True)
        return None
    for d in docs:
        np = re.sub(r"[^0-9a-z]", "", str(d.get("Nº Pedido", "")).lower())
        if np and (np == key or np.startswith(key)):
            return {
                "cliente": str(d.get("Cliente", "") or ""),
                "material": str(d.get("Material", "") or ""),
                "po": str(d.get("Nº PO", "") or ""),
            }
    return None


def _today_dmy() -> str:
    """Hoy en formato DD-MM-YYYY como placeholder práctico."""
    from datetime import datetime as _dt
    return _dt.now().strftime("%d-%m-%Y")


def _open_html_preview(html: str, kind: str) -> None:
    """Guarda el HTML en un tmpfile y lo abre en el navegador del sistema."""
    import tempfile
    import webbrowser
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=f"_{kind}_preview.html", delete=False,
    )
    tmp.write(html)
    tmp.close()
    webbrowser.open(f"file://{tmp.name}")


def _friendly_error(msg: str) -> str:
    low = msg.lower()
    if "bad username or password" in low or "authentication failed" in low:
        return "Credenciales IMAP incorrectas. Edita .env y rellena IMAP_USER / IMAP_PASS."
    if "name or service not known" in low or "getaddrinfo" in low or "timed out" in low:
        return "No se pudo contactar con el servidor IMAP. Revisa IMAP_HOST en .env."
    return msg


def _open_return_folders(folder, dev_folders=()) -> None:
    """Abre en el Explorador la carpeta 00 TRANS Y RES\\NNN de la devolución y
    también cada carpeta dev. donde se archivaron los PDF."""
    from core.services import dev_folders as dv

    for p in [folder, *[dv.carpeta_vigente(d) for d in dev_folders]]:
        if p:
            try:
                os.startfile(str(p))
            except OSError as exc:
                logger.warning("No se pudo abrir %s: %s", p, exc)


def _orden_descarga(dl: dict) -> int:
    """Para ordenar la columna Descarga: nada < solo correo < pendiente < guardada."""
    if not dl or not dl.get("downloadable"):
        return 1 if dl.get("only_email") else 0
    return 3 if dl.get("downloaded") else 2


def _trunc(text, n: int) -> str:
    txt = str(text or "").strip()
    return txt if len(txt) <= n else txt[:n - 1] + "…"


def _remitente(value: str) -> str:
    """«"Proarc@SACYR" <sacyr@proarconline.com>» → «sacyr@proarconline.com»."""
    txt = str(value or "").strip()
    if "<" in txt and ">" in txt:
        txt = txt[txt.rfind("<") + 1:txt.rfind(">")]
    return txt.strip().strip('"')


def _parse_dt(iso: str) -> datetime | None:
    """Fecha del correo, venga en ISO (con o sin zona) o en formato RFC 2822."""
    txt = str(iso or "").strip()
    if not txt:
        return None
    try:
        return datetime.fromisoformat(txt)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(txt)
    except Exception:  # noqa: BLE001
        return None


def _fmt_date(iso: str) -> str:
    dt = _parse_dt(iso)
    return dt.strftime("%d %b · %H:%M") if dt else str(iso or "")[:16]


def _dias_desde(iso: str) -> int | None:
    """Días transcurridos desde que llegó el correo."""
    dt = _parse_dt(iso)
    if dt is None:
        return None
    ahora = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return max(0, (ahora - dt).days)


def _status_tag(estado: str) -> str:
    s = (estado or "").lower().strip().replace(".", "").replace(" ", "_")
    if "aprobado" in s: return "status_aprobado"
    if "rechazado" in s: return "status_rechazado"
    if "comentado" in s or "menores" in s or "mayores" in s: return "status_comentado"
    if "enviado" in s: return "status_enviado"
    return ""
