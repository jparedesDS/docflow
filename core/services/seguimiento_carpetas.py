"""Plazos: cuándo se pasaron los planos a fábrica y qué técnico lo hizo.

El técnico manda los planos a fábrica por correo («P.Fabricación (envío 01)»),
y ese correo se guarda como .msg en `3-Fabricacion\\Envíos` (suelto o en
«envío 01», «envío 02», «superado»…). El hito es el **correo más antiguo**: su
fecha y hora y su remitente. Uno «superado» también cuenta: llegó a fábrica.
Si no hay correo legible, vale la creación del PDF más antiguo, y se dice.
(`Planos OF` no sirve: no son los planos que se mandan a fábrica.)

Solo lectura en M:. Lo leído se guarda en `state/seguimiento_envios.json`
junto con la fecha de modificación de la carpeta Envíos: mientras no cambie,
no se vuelve a recorrer. Una carpeta vacía se mira siempre.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from core.services import apertura

logger = logging.getLogger(__name__)

_RE_FAB = re.compile(r"^\s*3\s*-?\s*fabric", re.I)
_RE_ENVIOS = re.compile(r"^\s*envios?\b", re.I)
_RE_EMAIL = re.compile(r"([\w.+\-]+)@[\w.\-]+")
_IGNORAR = {"thumbs.db", "desktop.ini"}


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c))


def _cache_por_defecto() -> Path:
    from core.paths import state_dir
    return state_dir() / "seguimiento_envios.json"


# ── Quién ─────────────────────────────────────────────────────────────────────

def remitente(texto: str) -> str:
    """«<ana-x@dominio>» → «ana-x»; «luis-x luis-x» → «luis-x»."""
    m = _RE_EMAIL.search(texto or "")
    if m:
        return m.group(1)
    palabras = re.sub(r"[<>\"']", " ", texto or "").split()
    vistas = []
    for p in palabras:
        if p not in vistas:
            vistas.append(p)
    return " ".join(vistas)


def propietario(ruta: Path) -> str:
    """Usuario de Windows propietario del fichero, sin dominio; «» si no se sabe."""
    if os.name != "nt":
        return ""
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    sid = ctypes.c_void_p()
    sd = ctypes.c_void_p()
    # SE_FILE_OBJECT = 1, OWNER_SECURITY_INFORMATION = 1
    res = advapi.GetNamedSecurityInfoW(ctypes.c_wchar_p(str(ruta)), 1, 1, ctypes.byref(sid),
                                       None, None, None, ctypes.byref(sd))
    if res != 0:
        return ""
    try:
        nombre = ctypes.create_unicode_buffer(256)
        dominio = ctypes.create_unicode_buffer(256)
        n_nombre, n_dominio = wintypes.DWORD(256), wintypes.DWORD(256)
        uso = wintypes.DWORD()
        if not advapi.LookupAccountSidW(None, sid, nombre, ctypes.byref(n_nombre), dominio,
                                        ctypes.byref(n_dominio), ctypes.byref(uso)):
            return ""
        return nombre.value
    finally:
        kernel.LocalFree(sd)


# ── Ficheros ──────────────────────────────────────────────────────────────────

def _leer_msg(ruta: Path) -> tuple[datetime | None, str]:
    """(fecha del correo en hora local, remitente) de un .msg de Outlook."""
    import extract_msg
    try:
        m = extract_msg.openMsg(str(ruta))
    except Exception:  # noqa: BLE001 — un .msg dañado no para nada
        logger.debug("No se pudo abrir %s", ruta, exc_info=True)
        return None, ""
    try:
        fecha = m.date if isinstance(m.date, datetime) else None
        if fecha and fecha.tzinfo:
            fecha = fecha.astimezone().replace(tzinfo=None)
        return fecha, str(m.sender or "")
    except Exception:  # noqa: BLE001
        return None, ""
    finally:
        m.close()


def _creado(st) -> float:
    return getattr(st, "st_birthtime", None) or st.st_ctime


def _ficheros(carpeta: Path) -> list[Path]:
    out = []
    for raiz, _dirs, nombres in os.walk(carpeta):
        for n in nombres:
            if n.lower() in _IGNORAR or n.startswith("~$"):
                continue
            out.append(Path(raiz) / n)
    return out


def primer_envio(carpeta: Path) -> dict | None:
    """{"creado", "autor", "fuente", "envios"} del primer envío a fábrica, o None."""
    ficheros = _ficheros(carpeta)
    correos = []
    for f in ficheros:
        if f.suffix.lower() == ".msg":
            fecha, quien = _leer_msg(f)
            if fecha:
                correos.append((fecha, quien))
    if correos:
        fecha, quien = min(correos, key=lambda c: c[0])
        return {"creado": fecha, "autor": remitente(quien), "fuente": "correo", "envios": len(correos)}
    pdfs = []
    for f in ficheros:
        if f.suffix.lower() == ".pdf":
            try:
                pdfs.append((_creado(f.stat()), f))
            except OSError:
                continue
    if not pdfs:
        return None
    t, f = min(pdfs)
    return {"creado": datetime.fromtimestamp(t), "autor": propietario(f), "fuente": "pdf", "envios": 0}


# ── Carpetas ──────────────────────────────────────────────────────────────────

def _partes(pedido: str) -> tuple[str, str, int] | None:
    """'P-99/021-S03R' → ('P-99-021', 'S03R', 2099)."""
    try:
        folder_id, suf = apertura.parse_pedido(pedido)
    except ValueError:
        return None
    return folder_id, (suf or "S00").upper(), 2000 + int(folder_id.split("-")[1])


def _listado(base_dir: Path, año: int, memo: dict) -> list[Path]:
    clave = (str(base_dir), año)
    if clave not in memo:
        d = Path(base_dir) / f"Año {año}" / f"{año} Pedidos"
        try:
            memo[clave] = [e for e in d.iterdir() if e.is_dir()] if d.is_dir() else []
        except OSError:
            memo[clave] = []
    return memo[clave]


def _carpeta_pedido(pedido: str, base_dir: Path, memo: dict) -> Path | None:
    """La carpeta del suministro. Un suministro sin carpeta propia no toma la de otro:
    vale la que lo nombra, o para S00 la que no nombra ninguno."""
    p = _partes(pedido)
    if not p:
        return None
    folder_id, suf, año = p
    candidatas = []
    for e in _listado(base_dir, año, memo):
        meta = apertura.parse_folder_meta(e.name)
        if meta and meta["folder_id"].upper() == folder_id.upper():
            candidatas.append(e)
    candidatas.sort(key=lambda e: e.name)
    for e in candidatas:
        if suf in apertura.sufijos_de_carpeta(e.name):
            return e
    if suf == "S00":
        for e in candidatas:
            if not apertura.sufijos_de_carpeta(e.name):
                return e
    return None


def _hija(carpeta: Path, regex) -> Path | None:
    try:
        for e in sorted(carpeta.iterdir(), key=lambda e: e.name):
            if e.is_dir() and regex.search(_sin_acentos(e.name)):
                return e
    except OSError:
        return None
    return None


def _carpeta_envios(pedido: str, base_dir: Path, memo: dict) -> Path | None:
    d = _carpeta_pedido(pedido, base_dir, memo)
    fab = _hija(d, _RE_FAB) if d else None
    return _hija(fab, _RE_ENVIOS) if fab else None


def _leer(envios_dir: Path) -> dict:
    primero = primer_envio(envios_dir)
    if not primero:
        return {"estado": "vacia", "creado": None, "autor": "", "fuente": "", "envios": 0, "ruta": str(envios_dir)}
    return {"estado": "ok", **primero, "ruta": str(envios_dir)}


_SIN_CARPETA = {"estado": "sin_carpeta", "creado": None, "autor": "", "fuente": "", "envios": 0, "ruta": ""}


def planos_de(pedido: str, base_dir: Path = apertura.DEFAULT_BASE_DIR) -> dict:
    """{"estado": "ok"|"vacia"|"sin_carpeta", "creado", "autor", "fuente", "envios", "ruta"}."""
    d = _carpeta_envios(pedido, Path(base_dir), {})
    return _leer(d) if d else dict(_SIN_CARPETA)


def leer_planos(pedidos: list[str], base_dir: Path = apertura.DEFAULT_BASE_DIR,
                cache_file: Path | None = None) -> dict[str, dict]:
    """El primer envío a fábrica de muchos pedidos, con caché por carpeta."""
    from core.utils.json_store import read_json, write_json
    cache_file = Path(cache_file) if cache_file else _cache_por_defecto()
    cache = read_json(str(cache_file), default={}) or {}
    memo: dict = {}
    out, cambios = {}, False
    for pedido in pedidos:
        d = _carpeta_envios(pedido, Path(base_dir), memo)
        if not d:
            out[pedido] = dict(_SIN_CARPETA)
            continue
        try:
            mtime = d.stat().st_mtime_ns
        except OSError:
            out[pedido] = dict(_SIN_CARPETA)
            continue
        guardado = cache.get(str(d))
        # Una vacía se vuelve a mirar siempre: los envíos pueden llegar a una
        # subcarpeta sin cambiar la fecha de Envíos, y recorrerla vacía es barato
        if guardado and guardado.get("mtime") == mtime and guardado.get("estado") != "vacia":
            creado = guardado.get("creado")
            out[pedido] = {"estado": guardado["estado"], "autor": guardado.get("autor", ""),
                           "fuente": guardado.get("fuente", ""), "envios": guardado.get("envios", 0),
                           "ruta": str(d), "creado": datetime.fromisoformat(creado) if creado else None}
            continue
        r = _leer(d)
        out[pedido] = r
        cache[str(d)] = {"mtime": mtime, "estado": r["estado"], "autor": r["autor"], "fuente": r["fuente"],
                         "envios": r["envios"], "creado": r["creado"].isoformat() if r["creado"] else None}
        cambios = True
    if cambios:
        try:
            write_json(str(cache_file), cache)
        except OSError:
            logger.warning("No se pudo guardar la caché de envíos a fábrica", exc_info=True)
    return out
