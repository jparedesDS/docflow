r"""El SharePoint de SACYR con la sesión de la propia app, sin OneDrive.

Cada aviso de SACYR trae en «Comments» un enlace a la carpeta de la devolución:

    https://<tenant>.sharepoint.com/:f:/r/sites/<sitio>/<biblioteca>/…/<WF>?d=…

Detrás está el inicio de sesión de Microsoft del tenant de SACYR, con MFA, así
que no hay formulario al que mandar usuario y contraseña como en eGesDoc. Y la
sesión del Chrome de cada uno no se puede aprovechar: desde la versión 127
Chrome cifra sus cookies para que solo él las lea, y su perfil está bloqueado
mientras está abierto.

Lo que se hace es que la app tenga **su propio perfil de Chrome**
(`state/sacyr_navegador`). La primera vez se abre una ventana y JP inicia sesión
a mano —la contraseña la escribe él y la app no la ve—; a partir de ahí la app
reutiliza esa sesión sin ventana: abre el enlace, deja que Microsoft la renueve
sola y le pide a SharePoint, por su API, los ficheros de la carpeta.

La carpeta se baja entera a `state/sacyr_descargas/<WF>`, que es una raíz más
donde `sacyr.find_package` busca. Desde ahí sigue todo igual que con la carpeta
sincronizada o descargada a mano.

El perfil guarda una sesión válida: es tan sensible como una contraseña y está
en `.gitignore` igual que los demás secretos.
"""

from __future__ import annotations

import contextlib
import importlib.util
import logging
import re
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from core.paths import state_dir

logger = logging.getLogger(__name__)

# Lo que tarda Microsoft en renovar la sesión solo, redirección tras redirección.
ESPERA_SIN_VENTANA = 45
# Lo que se le da a JP para escribir la contraseña y aprobar el MFA.
ESPERA_INICIO_SESION = 300

_HOSTS_LOGIN = ("login.microsoftonline.com", "login.microsoft.com", "login.live.com")
_ACEPTA_JSON = {"Accept": "application/json;odata=nometadata"}

# Un único Chrome a la vez: el perfil no admite dos procesos.
_lock = threading.Lock()


class SesionNecesaria(RuntimeError):
    """SharePoint pide iniciar sesión: hay que hacerlo una vez a mano."""


def perfil() -> Path:
    return state_dir() / "sacyr_navegador"


def cache() -> Path:
    """Donde quedan las carpetas bajadas, una por devolución."""
    return state_dir() / "sacyr_descargas"


def disponible() -> bool:
    """¿Está Playwright instalado? Sin él, solo queda la carpeta local."""
    return importlib.util.find_spec("playwright") is not None


def hay_sesion() -> bool:
    """Si alguna vez se inició sesión (que siga valiendo lo dice SharePoint)."""
    try:
        return perfil().is_dir() and any(perfil().iterdir())
    except OSError:
        return False


def cerrar_sesion() -> None:
    """Olvida la sesión: borra el perfil de Chrome de la app."""
    with _lock:
        shutil.rmtree(perfil(), ignore_errors=True)
    logger.info("SACYR: sesión de SharePoint borrada")


# ── El enlace ────────────────────────────────────────────────────────────────

def carpeta_del_enlace(url: str) -> tuple[str, str, str] | None:
    """(origen, sitio, ruta de la carpeta) a la que apunta el enlace, o None.

    · «…/:f:/r/sites/X/Biblioteca/…/WF?d=…» lleva la ruta tal cual: es el que
      mandan los avisos de SACYR.
    · «…/Forms/AllItems.aspx?id=/sites/X/…» es donde acaba el navegador.
    """
    partes = urlsplit(str(url or "").strip())
    host = (partes.hostname or "").lower()
    if not host.endswith(".sharepoint.com"):
        return None
    origen = f"{partes.scheme or 'https'}://{partes.netloc}"
    ids = parse_qs(partes.query).get("id")
    if ids:
        ruta = ids[0]
    else:
        ruta = unquote(partes.path)
        m = re.match(r"^/:[a-z]:/[rs](/.*)$", ruta, re.I)
        if m:
            ruta = m.group(1)
        elif ruta.lower().endswith(".aspx"):
            return None
    ruta = ruta.rstrip("/")
    trozos = ruta.split("/")
    if len(trozos) < 4 or trozos[1].lower() not in ("sites", "teams"):
        return None
    return origen, "/".join(trozos[:3]), ruta


def _alias(valor: str) -> str:
    """Valor de un alias @a de la API REST, entre comillas y escapado."""
    return "'" + quote(valor.replace("'", "''"), safe="/") + "'"


# ── El navegador ─────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _navegador(*, visible: bool):
    from playwright.sync_api import sync_playwright

    if not _lock.acquire(timeout=600):
        raise RuntimeError("El navegador de SACYR lleva diez minutos ocupado")
    try:
        perfil().mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            # El Chrome instalado, no uno descargado por Playwright: es el mismo
            # navegador al que el tenant de SACYR ya está acostumbrado.
            ctx = pw.chromium.launch_persistent_context(
                str(perfil()), channel="chrome", headless=not visible,
                accept_downloads=False, viewport=None if visible else {"width": 1280, "height": 900})
            try:
                yield ctx
            finally:
                ctx.close()
    finally:
        _lock.release()


def _api_ok(ctx, origen: str, sitio: str) -> bool:
    """¿La API de ese sitio contesta con la sesión que hay?"""
    try:
        r = ctx.request.get(f"{origen}{sitio}/_api/web/currentuser", headers=_ACEPTA_JSON,
                            timeout=30_000, max_redirects=0)
        return r.ok
    except Exception:  # noqa: BLE001
        return False


def _entrar(ctx, url: str, origen: str, sitio: str, espera: int) -> bool:
    """Abre el enlace y espera a estar dentro. True si se llega."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except Exception as exc:  # noqa: BLE001 — una redirección a medias no es un error
        logger.debug("SACYR: carga del enlace: %s", exc)
    fin = time.monotonic() + espera
    while time.monotonic() < fin:
        try:
            host = (urlsplit(page.url).hostname or "").lower()
        except Exception:  # noqa: BLE001 — JP ha cerrado la ventana
            return False
        if host.endswith(".sharepoint.com") and "/_forms/" not in page.url.lower():
            if _api_ok(ctx, origen, sitio):
                return True
        try:
            page.wait_for_timeout(1000)
        except Exception:  # noqa: BLE001 — ventana cerrada
            return False
    return False


def iniciar_sesion(url: str, espera: int = ESPERA_INICIO_SESION) -> bool:
    """Abre una ventana de Chrome en ese enlace para que JP inicie sesión.

    Vuelve cuando SharePoint ya contesta (True) o cuando se cierra la ventana o
    se acaba el tiempo (False). La sesión queda guardada en el perfil de la app.
    """
    destino = carpeta_del_enlace(url)
    if destino is None:
        raise ValueError("Eso no es un enlace a una carpeta de SharePoint")
    origen, sitio, _ruta = destino
    with _navegador(visible=True) as ctx:
        dentro = _entrar(ctx, url, origen, sitio, espera)
    logger.info("SACYR: inicio de sesión en SharePoint %s", "correcto" if dentro else "sin completar")
    return dentro


# ── La descarga ──────────────────────────────────────────────────────────────

def _get(ctx, url: str, *, json: bool = True):
    r = ctx.request.get(url, headers=_ACEPTA_JSON if json else None, timeout=300_000)
    if r.status in (401, 403):
        raise SesionNecesaria("SharePoint de SACYR no da acceso con la sesión guardada")
    if r.status == 404:
        raise FileNotFoundError("La carpeta del enlace ya no está en SharePoint")
    if not r.ok:
        raise RuntimeError(f"SharePoint de SACYR respondió {r.status}")
    return r.json() if json else r.body()


def _ficheros(ctx, origen: str, sitio: str, ruta: str, rel: str = "") -> list[tuple[str, str]]:
    """[(ruta en SharePoint, ruta relativa dentro de la carpeta)], subcarpetas incluidas."""
    datos = _get(ctx, f"{origen}{sitio}/_api/web/GetFolderByServerRelativePath(decodedurl=@a)"
                      f"?@a={_alias(ruta)}&$expand=Files,Folders")
    fuera = [(f["ServerRelativeUrl"], f"{rel}{f['Name']}") for f in datos.get("Files") or []]
    for sub in datos.get("Folders") or []:
        if sub.get("Name") == "Forms":           # la de sistema de la biblioteca
            continue
        fuera += _ficheros(ctx, origen, sitio, sub["ServerRelativeUrl"], f"{rel}{sub['Name']}/")
    return fuera


def descargar(url: str, nombre: str) -> Path:
    """Baja la carpeta del enlace a `cache()/nombre` y devuelve esa carpeta.

    Se baja primero a una carpeta temporal y solo al final toma su nombre: una
    descarga cortada a medias nunca pasa por un paquete completo.

    Lanza `SesionNecesaria` si hay que volver a iniciar sesión.
    """
    destino = carpeta_del_enlace(url)
    if destino is None:
        raise ValueError(f"El enlace de SACYR no apunta a una carpeta de SharePoint: {url[:80]}")
    origen, sitio, ruta = destino
    final = cache() / nombre
    parcial = cache() / f".{nombre}.parcial"
    shutil.rmtree(parcial, ignore_errors=True)
    with _navegador(visible=False) as ctx:
        if not _entrar(ctx, url, origen, sitio, ESPERA_SIN_VENTANA):
            raise SesionNecesaria(
                "La sesión de SharePoint de SACYR ha caducado o no se ha iniciado. "
                "Inicia sesión en Ajustes ▸ Portales ▸ SACYR.")
        ficheros = _ficheros(ctx, origen, sitio, ruta)
        if not ficheros:
            raise FileNotFoundError(f"La carpeta «{ruta.rsplit('/', 1)[-1]}» de SharePoint está vacía")
        for remoto, rel in ficheros:
            datos = _get(ctx, f"{origen}{sitio}/_api/web/GetFileByServerRelativePath"
                              f"(decodedurl=@a)/$value?@a={_alias(remoto)}", json=False)
            local = parcial / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(datos)
    shutil.rmtree(final, ignore_errors=True)
    parcial.rename(final)
    logger.info("SACYR: %d fichero(s) bajados de SharePoint a %s", len(ficheros), final)
    return final
