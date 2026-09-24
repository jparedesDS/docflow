"""Portal eGesDoc (Técnicas Reunidas) — cliente HTTP de solo lectura/descarga.

El portal es ASP.NET MVC clásico con jQuery/DataTables. Este módulo reproduce,
sin navegador, exactamente las peticiones que hace Chrome cuando el usuario
entra, elige el PO, abre «Transmittals» y pulsa «Download»:

  1. POST /Login/Login                  (con el token anti-falsificación de /Login/Index)
  2. POST /Main/SelectProject           {projectCode}   → proyecto activo en sesión
  3. GET  /Main/SelectPurchaseOrder     ?project=&purchaseOrder=  → entra en el PO
  4. POST /Supplier/Transmittal/GetTransmittals          → JSON con los transmittals del PO
  5. POST /Supplier/Transmittal/ExportTransmittal {id}   → el portal prepara el zip
     GET  /Supplier/Transmittal/DownloadTransmittal      → lo descarga

Y lo mismo para la sección «Documents» del PO, que es de donde se sacan los
documentos ya cerrados con su PDF comentado por el cliente:

  6. POST /Supplier/Documents/GetPagedVddlRecordsFromView    → la tabla de documentos
  7. POST /Supplier/Documents/DownloadCommentedDocumentAjax {id}  → prepara el comentado
     GET  /Supplier/Documents/DownloadExportedDocumentFromPath    → lo descarga

Nunca se sube ni se modifica nada en el portal.

Credenciales: preferencia ``egesdoc_user`` + secreto ``egesdoc_pass`` (keyring /
cifrado local, igual que el correo). Nunca se escriben en disco en claro.
"""

from __future__ import annotations

import csv
import logging
import re
import time
import unicodedata
from datetime import datetime
from html import unescape
from pathlib import Path

import requests

from core import credentials, preferences
from core.utils import http

logger = logging.getLogger(__name__)

BASE = "https://egesdoc.tecnicasreunidas.es"
# El portal de TR tiene días malos: el 2026-09-14 el login tardaba 22 s, con lo
# que 25 s se quedaban cortos y las descargas se caían por timeout a media
# mañana. Con 60 hay margen sin que un portal caído deje la app colgada.
TIMEOUT = 60
DOWNLOAD_TIMEOUT = 180
EXPORT_RETRIES = 3
OPEN_RETRIES = 3


class PortalOcupado(RuntimeError):
    """El portal no está pudiendo atender ahora: ni es culpa nuestra ni se
    arregla mirando las credenciales. Se distingue para que estos fallos no
    gasten los intentos del job, que están para los errores de verdad."""


class SesionCaducada(RuntimeError):
    """La sesión se ha caído por el camino y el portal contesta su página de
    entrada. Se distingue porque tiene arreglo: volver a entrar y seguir."""


_AJAX = {"X-Requested-With": "XMLHttpRequest"}

# Asunto típico: "eGesdoc - New transmittal registered (10001-TRXXX-V-13174) - PO(1000100020)"
# También: "… registered (1000100030-VT-0022) - PO(1000100030)" (otro formato de código).
_REGISTERED_RE = re.compile(r"transmittal\s+registered\s*\(\s*([^()\s]+)\s*\)", re.I)
_CODE_RE = re.compile(r"\b(\d{5}-[A-Z0-9]{2,}-[A-Z]-\d+)\b")
_PROJECT_PREFIX_RE = re.compile(r"^(\d{5})-(?!\d)")
_PO_RE = re.compile(r"PO\s*\(\s*(\d{10})\s*\)", re.I)
_PO_ANY_RE = re.compile(r"\b(\d{10})\b")


# ── Credenciales ──────────────────────────────────────────────────────────────

def _creds() -> tuple[str, str]:
    user = (preferences.get("egesdoc_user") or "").strip()
    pwd = credentials.get("egesdoc_pass", env_fallback="EGESDOC_PASS") or ""
    return user, pwd


def is_configured() -> bool:
    user, pwd = _creds()
    return bool(user and pwd)


# En el ERP, Técnicas Reunidas aparece como cliente de varias maneras: el
# nombre entero con tilde y también abreviado con el proyecto detrás
# («TR - SIGMA», «TR-OMEGA»). El «TR» suelto no vale: KAPPA no es TR.
_TR_RE = re.compile(r"^TR\b|TECNICAS REUNIDAS")


def is_tr_client(name: str) -> bool:
    """¿Este cliente es el de eGesDoc? (el `Cliente` de consulta_erp)."""
    plano = "".join(c for c in unicodedata.normalize("NFD", str(name or ""))
                    if not unicodedata.combining(c)).upper().strip()
    return bool(_TR_RE.search(plano))


# ── Asunto del correo ─────────────────────────────────────────────────────────

def parse_subject(subject: str) -> dict:
    """Extrae del asunto el código de transmittal, el PO y el proyecto (los 5
    primeros dígitos del transmittal; OJO: no coinciden con los del PO)."""
    subject = subject or ""
    m = _REGISTERED_RE.search(subject) or _CODE_RE.search(subject)
    code = m.group(1).strip() if m else ""
    m = _PO_RE.search(subject) or _PO_ANY_RE.search(subject)
    po = m.group(1) if m else ""
    # El proyecto solo se deduce si el código empieza por sus 5 dígitos
    # («10001-TRXXX-…»); con códigos tipo «1000100030-VT-0022» se buscará.
    pm = _PROJECT_PREFIX_RE.match(code)
    return {"code": code, "po": po, "project": pm.group(1) if pm else ""}


# ── Sesión / login ────────────────────────────────────────────────────────────

def _new_session() -> requests.Session:
    return http.session()


def _hidden(html: str, name: str) -> str:
    m = re.search(r'name="%s"[^>]*value="([^"]*)"' % re.escape(name), html) or \
        re.search(r'value="([^"]*)"[^>]*name="%s"' % re.escape(name), html)
    return unescape(m.group(1)) if m else ""


def login(session: requests.Session | None = None) -> requests.Session:
    """Abre sesión en el portal. Lanza RuntimeError si no se puede."""
    user, pwd = _creds()
    if not user or not pwd:
        raise RuntimeError("Faltan usuario o contraseña de eGesDoc (Ajustes ▸ Portales).")
    s = session or _new_session()
    try:
        r = s.get(f"{BASE}/Login/Index", timeout=TIMEOUT)
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise PortalOcupado("No se llega a eGesDoc: el portal está caído o sin red. "
                            "Se reintenta en la siguiente pasada.") from exc
    if r.status_code >= 500:
        # El 2026-09-14 el portal pasó de ir lento a devolver 503 en su propia
        # página de entrada: no hay nada que revisar por nuestra parte.
        raise PortalOcupado(
            f"eGesDoc está caído (HTTP {r.status_code} en la página de entrada). "
            "Se reintenta en la siguiente pasada.")
    r.raise_for_status()
    token = _hidden(r.text, "__RequestVerificationToken")
    version = _hidden(r.text, "Version")
    data = {"__RequestVerificationToken": token, "Username": user, "Password": pwd,
            "RememberMe": "false"}
    if version:
        data["Version"] = version
    try:
        r = s.post(f"{BASE}/Login/Login", data=data, timeout=TIMEOUT, allow_redirects=True,
                   headers={"Referer": f"{BASE}/Login/Index"})
        # Verificación robusta: la raíz ya no redirige al login
        chk = s.get(f"{BASE}/", timeout=TIMEOUT, allow_redirects=True)
    except requests.Timeout as exc:
        # Que el portal no conteste a tiempo no es una contraseña mal puesta, y
        # decirlo así manda a buscar el fallo donde no está.
        raise PortalOcupado(
            f"eGesDoc no contesta (más de {TIMEOUT} s). El portal va lento o está "
            "caído; se reintenta en la siguiente pasada.") from exc
    if "/Login" in chk.url or 'id="loginForm"' in chk.text:
        hint = ""
        try:
            j = r.json()
            hint = f" ({j.get('message') or j.get('Message') or j})"
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError("eGesDoc rechazó el acceso: revisa usuario/contraseña" + hint)
    logger.info("eGesDoc: sesión abierta como %s", user)
    return s


def test_login() -> tuple[bool, str]:
    """(ok, mensaje). No modifica nada en el portal."""
    try:
        s = login()
        s.close()
        return True, "Acceso correcto a eGesDoc"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).splitlines()[0] if str(exc) else repr(exc)


# ── Proyecto y PO ─────────────────────────────────────────────────────────────

def projects(s: requests.Session) -> list[tuple[str, str]]:
    """[(código, nombre)] de los proyectos visibles para el usuario (selector de la Home)."""
    r = s.get(f"{BASE}/", timeout=TIMEOUT)
    r.raise_for_status()
    m = re.search(r'<select[^>]*id="project-select"[^>]*>(.*?)</select>', r.text, re.S | re.I)
    if not m:
        return []
    out = []
    for value, inner in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', m.group(1), re.S | re.I):
        if value and value != "-1":
            name = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", inner))).strip()
            out.append((value, name))
    return out


def select_project(s: requests.Session, project: str) -> bool:
    r = s.post(f"{BASE}/Main/SelectProject", data={"projectCode": project}, headers=_AJAX, timeout=TIMEOUT)
    r.raise_for_status()
    try:
        return bool(r.json().get("setProject", True))
    except ValueError:
        return r.ok


def purchase_orders(s: requests.Session) -> list[str]:
    """POs del proyecto activo en sesión."""
    r = s.post(f"{BASE}/Main/GetPurchaseOrders", data="", headers=_AJAX, timeout=TIMEOUT)
    r.raise_for_status()
    try:
        return [str(x.get("id") or x.get("text") or "") for x in r.json()]
    except ValueError:
        return []


def _po_projects() -> dict:
    return dict(preferences.get("egesdoc_po_projects") or {})


def remembered_project(po: str) -> str:
    """El proyecto en el que salió este PO la última vez, si ya se buscó."""
    return str(_po_projects().get(str(po), ""))


def _remember_project(po: str, project: str) -> None:
    datos = _po_projects()
    if datos.get(str(po)) != project:
        datos[str(po)] = project
        preferences.set_value("egesdoc_po_projects", datos)


def find_project_for_po(s: requests.Session, po: str, hint: str | None = None) -> str:
    """Proyecto al que pertenece el PO. Prueba primero `hint` (los 5 dígitos del
    transmittal) y, si no cuadra, recorre el resto de proyectos del usuario.

    Buscar a ciegas cuesta dos peticiones por proyecto —con 27 proyectos, casi
    un minuto—, así que el que sale se apunta en las preferencias y la próxima
    vez se va directo. Si el apunte ya no vale, se vuelve a buscar.
    """
    recordado = remembered_project(po)
    if recordado and select_project(s, recordado) and po in purchase_orders(s):
        return recordado
    codes = [c for c, _ in projects(s)]
    order = ([hint] if hint in codes else []) + [c for c in codes if c != hint]
    for code in order:
        if select_project(s, code) and po in purchase_orders(s):
            _remember_project(po, code)
            return code
    raise LookupError(f"El PO {po} no aparece en ningún proyecto de eGesDoc para este usuario")


def enter_po(s: requests.Session, project: str, po: str) -> None:
    """Equivale a pulsar «Open» en la tarjeta del PO: deja el PO activo en sesión.

    Igual que al preparar el zip, el portal contesta 500 de forma transitoria
    cuando va cargado (el 2026-09-14 lo hacía toda la mañana, tardando 30 s en
    contestarlo), así que se reintenta antes de darlo por perdido."""
    select_project(s, project)
    r = None
    for intento in range(1, OPEN_RETRIES + 1):
        try:
            r = s.get(f"{BASE}/Main/SelectPurchaseOrder",
                      params={"project": project, "purchaseOrder": po},
                      timeout=TIMEOUT, allow_redirects=True)
        except requests.Timeout:
            logger.info("eGesDoc: el PO %s no contesta (intento %d/%d)", po, intento, OPEN_RETRIES)
            if intento == OPEN_RETRIES:
                raise PortalOcupado(
                    f"eGesDoc no contesta al abrir el PO {po} (más de {TIMEOUT} s por "
                    "intento). El portal está saturado; se reintenta en la siguiente "
                    "pasada.") from None
            time.sleep(3 * intento)
            continue
        if r.status_code < 500:
            break
        logger.info("eGesDoc: abrir el PO %s devolvió %s (intento %d/%d)",
                    po, r.status_code, intento, OPEN_RETRIES)
        if intento < OPEN_RETRIES:
            time.sleep(3 * intento)
    if r is not None and r.status_code >= 500:
        raise PortalOcupado(
            f"eGesDoc da error {r.status_code} al abrir el PO {po}. Es cosa del portal, "
            "no del acceso; se reintenta en la siguiente pasada.")
    r.raise_for_status()
    if "/Supplier/" not in r.url:
        raise RuntimeError(f"eGesDoc no abrió el PO {po} (respuesta: {r.url})")


# ── Transmittals ──────────────────────────────────────────────────────────────

def _json_date(value) -> datetime | None:
    m = re.search(r"/Date\((-?\d+)", str(value or ""))
    return datetime.fromtimestamp(int(m.group(1)) / 1000) if m else None


def list_transmittals(s: requests.Session) -> list[dict]:
    """Transmittals del PO activo: [{id, code, date, documents, remarks}]."""
    data = {"draw": 1, "start": 0, "length": 2000, "search[value]": "", "search[regex]": "false",
            "order[0][column]": 1, "order[0][dir]": "desc"}
    r = s.post(f"{BASE}/Supplier/Transmittal/GetTransmittals", data=data,
               headers={**_AJAX, "Referer": f"{BASE}/Supplier/Transmittal"}, timeout=TIMEOUT)
    r.raise_for_status()
    rows = r.json().get("data") or []
    return [{
        "id": row.get("Id"),
        "code": (row.get("Transmittal") or "").strip(),
        "date": _json_date(row.get("RegisterDate")),
        "documents": row.get("DocumentCount"),
        "remarks": row.get("Remarks") or "",
    } for row in rows]


def transmittal_documents(s: requests.Session, transmittal_id: int) -> list[dict]:
    """Documentos de un transmittal: [{id, vendor_number, tr_number, vendor_rev, tr_rev, title, status}]."""
    r = s.post(f"{BASE}/Supplier/Transmittal/GetReturnedDocumentsByTransmittal",
               data={"returnId": transmittal_id},
               headers={**_AJAX, "Referer": f"{BASE}/Supplier/Transmittal"}, timeout=TIMEOUT)
    r.raise_for_status()
    return [{
        "id": d.get("Id"),
        "vendor_number": (d.get("VendorNumber") or "").strip(),
        "tr_number": (d.get("TrNumber") or "").strip(),
        "vendor_rev": d.get("VendorRev"), "tr_rev": d.get("TrRev"),
        "title": d.get("VendorTitle") or "", "status": d.get("ReturnStatus") or "",
    } for d in (r.json().get("data") or [])]


def document_filename(s: requests.Session, document_id: int) -> str:
    """Nombre del fichero de un documento devuelto, SIN descargarlo: se pide la
    exportación y se leen solo las cabeceras de la descarga."""
    r = s.post(f"{BASE}/Supplier/Documents/DownloadDocumentAjax", data={"id": document_id},
               headers={**_AJAX, "Referer": f"{BASE}/Supplier/Transmittal"}, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    try:
        if not r.json().get("result"):
            return ""
    except ValueError:
        return ""
    r = s.get(f"{BASE}/Supplier/Documents/DownloadExportedDocument", timeout=DOWNLOAD_TIMEOUT, stream=True)
    try:
        return http.filename_from_headers(r.headers) if r.ok else ""
    finally:
        r.close()


def transmittal_file_map(po: str, code: str, *, project_hint: str | None = None,
                         session: requests.Session | None = None) -> dict[str, dict]:
    """{nombre de fichero en el zip → {vendor_number, tr_number}}.

    Los ficheros del zip de eGesDoc llevan el id interno de TR (AD-3000-Q-96517.pdf),
    que no figura ni en el correo ni en el detalle: se consulta el nombre de cada
    documento para poder archivarlo en su carpeta dev. correcta.
    """
    own = session is None
    s = session or login()
    out: dict[str, dict] = {}
    try:
        project = find_project_for_po(s, po, hint=project_hint)
        enter_po(s, project, po)
        match = next((t for t in list_transmittals(s) if t["code"].upper() == code.upper()), None)
        if match is None:
            return out
        for d in transmittal_documents(s, match["id"]):
            try:
                name = document_filename(s, d["id"])
            except Exception as exc:  # noqa: BLE001 — un doc sin nombre no debe tumbar el resto
                logger.info("eGesDoc: sin nombre de fichero para %s: %s", d["vendor_number"], exc)
                name = ""
            if name:
                out[name] = {"vendor_number": d["vendor_number"], "tr_number": d["tr_number"]}
    finally:
        if own:
            s.close()
    return out


def download_transmittal(po: str, code: str, dest_dir: Path | str, *,
                         project_hint: str | None = None,
                         session: requests.Session | None = None) -> Path:
    """Descarga el zip del transmittal `code` del PO `po` en `dest_dir`.

    Devuelve la ruta del zip. Si se pasa `session` (ya logada) se reutiliza y no
    se cierra; si no, se abre y cierra una sesión propia.
    """
    own = session is None
    s = session or login()
    try:
        project = find_project_for_po(s, po, hint=project_hint)
        enter_po(s, project, po)
        rows = list_transmittals(s)
        match = next((t for t in rows if t["code"].upper() == code.upper()), None)
        if match is None:
            raise LookupError(f"El transmittal {code} no está en el PO {po} (el portal lista {len(rows)})")

        # El portal a veces contesta 500 de forma transitoria al preparar el zip
        # (p. ej. si aún está sirviendo una exportación anterior): se reintenta.
        ok = False
        for attempt in range(1, EXPORT_RETRIES + 1):
            r = s.post(f"{BASE}/Supplier/Transmittal/ExportTransmittal", data={"id": match["id"]},
                       headers={**_AJAX, "Referer": f"{BASE}/Supplier/Transmittal"}, timeout=DOWNLOAD_TIMEOUT)
            if r.status_code < 500:
                r.raise_for_status()
                try:
                    ok = bool(r.json().get("result"))
                except ValueError:
                    ok = False
                break
            logger.info("eGesDoc: ExportTransmittal %s devolvió %s (intento %d/%d)",
                        code, r.status_code, attempt, EXPORT_RETRIES)
            time.sleep(3 * attempt)
        if not ok:
            raise RuntimeError(f"eGesDoc no pudo preparar el zip de {code} (HTTP {r.status_code})")

        r = s.get(f"{BASE}/Supplier/Transmittal/DownloadTransmittal", timeout=DOWNLOAD_TIMEOUT, stream=True)
        r.raise_for_status()
        target = http.save_response(r, dest_dir, f"{code}.zip")
        if not http.is_zip(target):
            target.unlink(missing_ok=True)
            raise RuntimeError("eGesDoc no devolvió un zip (¿sesión caducada o transmittal sin fichero?)")
        logger.info("eGesDoc: %s descargado en %s", code, target)
        return target
    finally:
        if own:
            s.close()


# ── Documentos del PO ─────────────────────────────────────────────────────────

# Los recuadros del panel de resumen de la sección «Documents» (el `itemprop` de
# cada celda). «Finals» es el verde de abajo a la derecha: los documentos ya
# cerrados, los que la tabla enseña con DOC. STATUS = Final.
DOC_FILTERS = ("Pending", "Complete", "All", "Claimed", "Returned", "Rejected",
               "PendingCritical", "Finals")


def list_documents(s: requests.Session, *, summary: str = "Finals") -> list[dict]:
    """Documentos del PO activo, filtrados por uno de los recuadros del resumen.

    `naReturned` es el «N/A» del filtro de fecha de devolución y no se puede
    omitir: si no va, el portal lo da por 0 y contesta una tabla vacía sin
    decir nada. Con 2 (todos) salen los mismos que enseña el navegador.
    """
    data = {"draw": 1, "start": 0, "length": 5000,
            "search[value]": "", "search[regex]": "false",
            "order[0][column]": 0, "order[0][dir]": "asc",
            "naScheduled": 2, "naReturned": 2, "Critical": "All",
            "SummaryFilter": summary}
    r = s.post(f"{BASE}/Supplier/Documents/GetPagedVddlRecordsFromView", data=data,
               headers={**_AJAX, "Referer": f"{BASE}/Supplier/Documents"}, timeout=TIMEOUT)
    r.raise_for_status()
    return [{
        "id": row.get("Id"),                     # la línea del VDDL
        "document_id": row.get("DocumentId"),    # la revisión subida: el id de las descargas
        "code": (row.get("VendorNumber") or "").strip(),
        "tr_number": (row.get("TrNumber") or "").strip(),
        "title": row.get("VendorTitle") or "",
        "type": row.get("TypeDocCode") or "",
        "status": row.get("DocumentStatus") or "",
        "return_status": row.get("ReturnStatus") or "",
        "return_date": _json_date(row.get("ReturnDate")),
    } for row in (r.json().get("data") or [])]


def download_commented_file(s: requests.Session, document_id: int, dest_dir: Path | str,
                            name: str = "") -> Path | None:
    """El «Download commented file» de un documento, en `dest_dir`.

    Devuelve dónde quedó, o None si el portal dice que ese documento no tiene
    fichero comentado. Con `name` se le pone nuestro nombre en vez del id
    interno de TR (V-1000100010-0111.pdf), que no dice nada a nadie; si `name`
    va sin extensión se le pone la del fichero que mande el portal.
    """
    r = s.post(f"{BASE}/Supplier/Documents/DownloadCommentedDocumentAjax",
               data={"id": document_id},
               headers={**_AJAX, "Referer": f"{BASE}/Supplier/Documents"},
               timeout=DOWNLOAD_TIMEOUT)
    if r.status_code >= 500:
        raise PortalOcupado(f"eGesDoc da error {r.status_code} al preparar el comentado")
    r.raise_for_status()
    try:
        if not r.json().get("result"):
            return None
    except ValueError:
        return None

    r = s.get(f"{BASE}/Supplier/Documents/DownloadExportedDocumentFromPath",
              timeout=DOWNLOAD_TIMEOUT, stream=True)
    try:
        if r.status_code >= 500:
            raise PortalOcupado(f"eGesDoc da error {r.status_code} al bajar el comentado")
        r.raise_for_status()
        # Si la sesión ha caducado el portal contesta la página de entrada con
        # un 200 tan tranquilo; guardarla sería dejar un «PDF» que es HTML.
        if "text/html" in (r.headers.get("Content-Type") or "").lower():
            raise SesionCaducada("eGesDoc devolvió una página en vez del fichero")
        if name and not Path(name).suffix:
            name += Path(http.filename_from_headers(r.headers)).suffix or ".pdf"
        target = http.save_response(r, dest_dir, f"{document_id}.pdf", name)
    finally:
        r.close()
    if not (http.is_pdf(target) or http.is_zip(target)):
        target.unlink(missing_ok=True)
        raise RuntimeError("eGesDoc no devolvió ni un PDF ni un zip")
    return target


def write_summary(filas: list[dict], dest_dir: Path | str) -> Path:
    """Deja en la carpeta un CSV con lo bajado y lo que no.

    Cada pasada escribe el suyo, con la hora en el nombre: el de la anterior es
    justo lo que dice qué se quedó sin bajar, así que no se pisa.
    """
    destino = Path(dest_dir) / f"_resumen {datetime.now():%d-%m-%Y %H%M}.csv"
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Documento", "Título", "Fichero", "Problema"])
        for f in filas:
            w.writerow([f["code"], f["title"],
                        Path(f["file"]).name if f["file"] else "", f["error"]])
    return destino


def nombre_de(doc: dict) -> str:
    """Con qué nombre se guarda el fichero de un documento —y con cuál se busca
    después—. Los dos sitios tienen que usar el mismo: si uno mira por el código
    y el otro guarda «documento-413929», lo bajado se daría por pendiente para
    siempre."""
    return str(doc.get("code") or f"documento-{doc.get('document_id')}")


def ya_bajado(dest: Path, code: str) -> Path | None:
    """El fichero de ese documento si ya está en la carpeta. Lo que permite
    relanzar la descarga sin volver a pedirle al portal lo que ya vino."""
    if not code:
        return None
    for f in dest.iterdir():
        # «26-001-ESP-0001.pdf» y también el «26-001-ESP-0001 (2).pdf» que deja
        # la regla de no pisar nada; pero no el «26-001-ESP-00010.pdf» de otro.
        if f.is_file() and (f.stem == code or f.stem.startswith(f"{code} ")):
            return f
    return None


def download_final_documents(po: str, dest_dir: Path | str, *, project_hint: str | None = None,
                             session: requests.Session | None = None, docs: list[dict] | None = None,
                             progreso=None, retries: int = 3, limite: int = 0) -> list[dict]:
    """Baja el «commented file» de todos los documentos en Final del PO.

    Devuelve una línea por documento: `{code, title, file, error}`. Con `file`
    puesto ya está en disco; con `error`, es lo que habrá que reintentar; sin
    ninguno de los dos, el portal no guarda comentado de ese documento.

    Está pensado para relanzarse: lo que ya esté en la carpeta no se vuelve a
    pedir, así que una segunda pasada solo cuesta lo que falló la primera. Cada
    documento se reintenta `retries` veces —el portal se atraganta a ratos— y si
    la sesión se cae por el camino se vuelve a entrar y se sigue por donde iba.

    `progreso(n, total, doc, estado)` se llama al terminar cada documento, para
    que quien lo lance pueda ir contando; si devuelve False se para ahí (es lo
    que usa el botón de cancelar). `limite` corta la lista para probar un PO sin
    bajarse los cuatro gigas de golpe. Con `docs` se trabaja sobre una lista ya
    pedida (la ventana la enseña antes de bajar nada) y no se vuelve a pedir.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    own = session is None
    s = session or login()
    try:
        project = find_project_for_po(s, po, hint=project_hint)
        enter_po(s, project, po)
        if docs is None:
            docs = list_documents(s, summary="Finals")
        logger.info("eGesDoc: %d documentos en Final en el PO %s", len(docs), po)
        if limite:
            docs = docs[:limite]

        salida = []
        cortado = ""
        for n, doc in enumerate(docs, 1):
            code = nombre_de(doc)
            fila = {"code": code, "title": doc["title"], "file": "", "error": ""}
            ya = ya_bajado(dest, code)
            if ya is not None:
                fila["file"] = str(ya)
                estado = "ya estaba"
            else:
                estado = ""
                for intento in range(1, retries + 1):
                    try:
                        ruta = download_commented_file(s, doc["document_id"], dest, code)
                        fila["file"] = str(ruta) if ruta else ""
                        # Salió bien: si un intento anterior había fallado, ese
                        # error ya no cuenta —ni en el resumen ni en el «quedan».
                        fila["error"] = ""
                        estado = "bajado" if ruta else "sin comentado"
                        break
                    except SesionCaducada as exc:
                        logger.info("eGesDoc: sesión caída en %s, se vuelve a entrar", code)
                        fila["error"] = str(exc)
                        estado = "error"
                        try:
                            s = login(s)
                            enter_po(s, project, po)
                        except Exception as vuelta:  # noqa: BLE001
                            # Sin sesión no hay nada que hacer con los que faltan:
                            # se para y se devuelve lo que sí se bajó.
                            fila["error"] = f"no se pudo volver a entrar: {vuelta}"
                            cortado = fila["error"]
                            break
                    except (PortalOcupado, requests.RequestException, OSError,
                            RuntimeError) as exc:
                        fila["error"] = str(exc).splitlines()[0]
                        estado = "error"
                        logger.info("eGesDoc: %s falló (intento %d/%d): %s",
                                    code, intento, retries, fila["error"])
                        time.sleep(3 * intento)
                else:
                    estado = estado or "error"
            salida.append(fila)
            if progreso is not None and progreso(n, len(docs), doc, estado) is False:
                logger.info("eGesDoc: descarga parada a petición en %s (%d de %d)",
                            code, n, len(docs))
                break
            if cortado:
                logger.warning("eGesDoc: descarga cortada en %s (%d de %d): %s",
                               code, n, len(docs), cortado)
                break
        return salida
    finally:
        if own:
            s.close()
