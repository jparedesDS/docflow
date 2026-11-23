"""Correos del expediente de un cliente: lectura con caché, reclamaciones y contactos.

Lee (solo lectura, BODY.PEEK) las carpetas del buzón de documentación de cada
pedido (`INBOX/P. 20YY/P-YY-NNN`) y lo que se le pida por asunto en INBOX. Leer
cientos de correos tarda minutos, así que cada correo se guarda en una caché
JSON por Message-ID y no se vuelve a descargar.

De esos correos salen:
  · las **reclamaciones**: fechas en que EIPSA reclamó o actualizó el estado, y
    en que contestó el cliente; también las citadas dentro de los hilos
    («De: … Enviado el: … Asunto: …»), que llegan a meses antes de lo que queda
    en el buzón;
  · los **contactos** del cliente, ordenados por la fecha de su último correo
    enviado, con cargo y teléfono leídos de su firma (JP los corrige a mano).

El buzón se lee a través de una «fuente» con dos operaciones (`ids`, `bajar`):
la real va sobre `core.services.imap`; los tests usan un doble.
"""
from __future__ import annotations

import email
import json
import logging
import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MAX_CUERPO = 60_000
_PREF_AUTOMATICO = ("dev:", "leído:", "leido:", "read:")
_RECORDATORIO = re.compile(r"^P-\d{2}/\d{3} / PO: .* // DOCUMENTS PENDING REVIEW$", re.I)
_RECLAMACION = re.compile(r"RECLAIM|PENDING REVIEW|FORMAL CLAIM|DOCUMENT STATUS UPDATE|Pending documents|PENDING DOCUMENT", re.I)
_BLOQUE = re.compile(
    r"^\s*(?:De|From):\s*(?P<de>.+?)\s*$"
    r"(?:\n^.*$){0,2}?\n^\s*(?:Enviado el|Enviado|Sent|Fecha|Date):\s*(?P<f>.+?)\s*$"
    r"(?:\n^.*$){0,14}?\n^\s*(?:Asunto|Subject):\s*(?P<a>.+?)\s*$", re.M)
_MESES = {m: i + 1 for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                          "septiembre", "octubre", "noviembre", "diciembre"])}
_MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december"])}
_TELEFONO = re.compile(r"(\+\d[\d\s().-]{7,}\d)")
_DIRECCION = re.compile(r"\d|@|www\.|\b(calle|c/|avda|avenida|av\.|street|st\.|floor|planta|tel|phone|mob|fax|p\.?o\.? box)\b", re.I)


# ── Lectura ───────────────────────────────────────────────────────────────────

def carpetas_pedido(pedidos: list[str], todas: list[str]) -> list[str]:
    """Las carpetas del buzón que son de alguno de esos pedidos (P-99/048 → …/P-99-048)."""
    sufijos = tuple(p.replace("/", "-").upper() for p in pedidos)
    return [c for c in todas if c.rstrip("/").upper().endswith(sufijos)]


class _BuzonIMAP:
    """Fuente real: el buzón de documentación vía core.services.imap, solo lectura."""

    def __init__(self):
        from core.services import imap
        self.imap = imap
        self.conn = None
        self.actual = None

    def _abrir(self, carpeta):
        if self.conn is None:
            self.conn = self.imap._connect("INBOX")
        if carpeta != self.actual:
            typ, data = self.conn.select(self.imap._nombre_carpeta(carpeta), readonly=True)
            if typ != "OK":
                raise RuntimeError(f"No se pudo abrir la carpeta «{carpeta}»")
            self.actual = carpeta

    def ids(self, carpeta, asunto=None):
        self._abrir(carpeta)
        crit = ("SUBJECT", f'"{asunto}"') if asunto else ("ALL",)
        typ, d = self.conn.uid("search", None, *crit)
        uids = d[0].split() if typ == "OK" and d and d[0] else []
        out = []
        for i in range(0, len(uids), 200):
            typ, data = self.conn.uid("fetch", b",".join(uids[i:i + 200]),
                                      "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            for item in data or []:
                if not isinstance(item, tuple):
                    continue
                m = re.search(rb"UID (\d+)", item[0])
                mid = email.message_from_bytes(item[1]).get("Message-ID", "").strip()
                if m:
                    out.append((m.group(1).decode(), mid))
        return out

    def bajar(self, carpeta, uid):
        self._abrir(carpeta)
        typ, data = self.conn.uid("fetch", str(uid).encode(), "(BODY.PEEK[])")
        return next(x[1] for x in data if isinstance(x, tuple))

    def cerrar(self):
        try:
            if self.conn is not None:
                self.conn.logout()
        except Exception:  # noqa: BLE001
            pass


def _decodifica(v) -> str:
    from core.services import imap
    return str(imap._decode_header_value(v) or "") if v else ""


def _parsear(raw: bytes, carpeta: str) -> dict:
    from core.services import imap
    m = email.message_from_bytes(raw)
    nombre, mail = (getaddresses([_decodifica(m.get("From")).replace("\n", " ")]) or [("", "")])[0]
    try:
        fecha = parsedate_to_datetime(m.get("Date"))
        fecha = fecha.replace(tzinfo=None) if fecha.tzinfo is None else fecha.astimezone().replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        fecha = datetime(1900, 1, 1)
    try:
        cuerpo = imap.get_plain_body(m) or ""
    except Exception:  # noqa: BLE001
        cuerpo = ""
    return {"msgid": (m.get("Message-ID") or "").strip(), "fecha": fecha, "de_nombre": nombre.strip("'\" "),
            "de_email": mail.lower().strip(), "para": _decodifica(m.get("To")), "cc": _decodifica(m.get("Cc")),
            "asunto": re.sub(r"\s+", " ", _decodifica(m.get("Subject"))).strip(), "cuerpo": cuerpo[:MAX_CUERPO],
            "adjuntos": [_decodifica(p.get_filename()) for p in m.walk() if p.get_filename()], "carpeta": carpeta}


def _cargar_cache(cache: Path) -> dict:
    try:
        datos = json.loads(Path(cache).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for c in datos.values():
        try:
            c["fecha"] = datetime.fromisoformat(c["fecha"])
        except (KeyError, ValueError, TypeError):
            c["fecha"] = datetime(1900, 1, 1)
    return datos


def _guardar_cache(cache: Path, datos: dict) -> None:
    Path(cache).parent.mkdir(parents=True, exist_ok=True)
    serial = {k: {**v, "fecha": v["fecha"].isoformat()} for k, v in datos.items()}
    tmp = Path(str(cache) + ".tmp")
    tmp.write_text(json.dumps(serial, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache)


def leer(carpetas: list[str], asuntos: list[str], cache: Path,
         progreso: Callable[[str], None] | None = None, fuente=None) -> tuple[list[dict], list[str]]:
    """(correos sin duplicados, avisos). Lo que ya está en la caché no se descarga.

    Un fallo del buzón o de una carpeta no corta: se apunta en `avisos`."""
    datos = _cargar_cache(cache)
    avisos: list[str] = []
    propia = fuente is None
    try:
        if propia:
            fuente = _BuzonIMAP()
    except Exception as exc:  # noqa: BLE001
        return list(datos.values()), [f"Sin buzón: {exc}"]
    vistos: set[str] = set()
    trabajos = [(c, None) for c in carpetas] + [("INBOX", a) for a in asuntos]
    try:
        for carpeta, asunto in trabajos:
            if progreso:
                progreso(f"Leyendo {carpeta}" + (f" («{asunto}»)" if asunto else ""))
            try:
                ids = fuente.ids(carpeta, asunto)
            except Exception as exc:  # noqa: BLE001
                avisos.append(f"{carpeta}: {exc}")
                continue
            for uid, mid in ids:
                if mid and mid in datos:
                    vistos.add(mid)
                    continue
                try:
                    c = _parsear(fuente.bajar(carpeta, uid), carpeta)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Expediente: no se pudo leer el correo %s de %s: %s", uid, carpeta, exc)
                    continue
                clave = c["msgid"] or f"{carpeta}#{uid}"
                c["msgid"] = clave
                datos[clave] = c
                vistos.add(clave)
    finally:
        if propia and hasattr(fuente, "cerrar"):
            fuente.cerrar()
    _guardar_cache(cache, datos)
    return [datos[k] for k in vistos], avisos


def es_automatico(c: dict, propio: str) -> bool:
    """Avisos que no cuentan como correo «de verdad»: devoluciones de DocFlow,
    acuses de lectura, avisos de eGesdoc y nuestros recordatorios repetidos."""
    asunto = c.get("asunto", "")
    if asunto.lower().startswith(_PREF_AUTOMATICO) or "egesdoc - new transmittal" in asunto.lower():
        return True
    return c.get("de_email", "") == (propio or "").lower() and bool(_RECORDATORIO.match(asunto))


# ── Reclamaciones ─────────────────────────────────────────────────────────────

def _fecha_texto(t: str) -> date | None:
    t = t.lower()
    for pat, meses, orden in ((r"(\d{1,2}) de (\w+) de (\d{4})", _MESES, "dmy"),
                              (r"(\w+) (\d{1,2}), (\d{4})", _MONTHS, "mdy"),
                              (r"(\d{1,2}) (\w+) (\d{4})", _MONTHS, "dmy")):
        m = re.search(pat, t)
        if not m:
            continue
        a, b, y = m.groups()
        dia, mes = (a, b) if orden == "dmy" else (b, a)
        if mes in meses:
            try:
                return date(int(y), meses[mes], int(dia))
            except ValueError:
                return None
    return None


def _claves_busqueda(claves: list[str]) -> list[str]:
    out = []
    for k in claves:
        d = re.sub(r"\D", "", k)
        out.append(d[:9] if len(d) >= 9 and d == k.strip() else k)
    return out


def _de_aqui(remitente: str, dominio: str) -> bool:
    r = remitente.lower()
    return bool(dominio) and (r.endswith("@" + dominio.lower()) or dominio.lower() in r)


def reclamaciones(correos: list[dict], claves: list[str], propio_dominio: str,
                  log: list[dict]) -> tuple[list[date], list[date]]:
    """(fechas de EIPSA, fechas del cliente): días únicos ordenados."""
    ks = _claves_busqueda(claves)

    def es(asunto: str) -> bool:
        return bool(_RECLAMACION.search(asunto)) and any(k in asunto for k in ks)

    eipsa, cliente = set(), set()
    for c in correos:
        if es(c.get("asunto", "")):
            (eipsa if _de_aqui(c.get("de_email", ""), propio_dominio) else cliente).add(c["fecha"].date())
        for b in _BLOQUE.finditer(str(c.get("cuerpo", "")).replace("\r", "")):
            if es(b.group("a")):
                d = _fecha_texto(b.group("f"))
                if d:
                    (eipsa if _de_aqui(b.group("de"), propio_dominio) else cliente).add(d)
    for h in log or []:
        try:
            eipsa.add(datetime.fromisoformat(str(h.get("sent_at"))).date())
        except ValueError:
            continue
    return sorted(eipsa), sorted(cliente)


# ── Contactos ─────────────────────────────────────────────────────────────────

def _normal(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn").lower().strip()


def firma(cuerpo: str, nombre: str) -> tuple[str, str]:
    """(cargo, teléfono) leídos de la firma: la línea con el nombre y las siguientes."""
    lineas = [ln.strip() for ln in str(cuerpo or "").splitlines()]
    n = _normal(nombre)
    if not n:
        return "", ""
    clave = " ".join(n.split()[:2])
    for i, ln in enumerate(lineas):
        if not ln or not _normal(ln).startswith(clave):
            continue
        siguientes = [x for x in lineas[i + 1:i + 9] if x]
        cargo = ""
        for x in siguientes[:4]:
            if _DIRECCION.search(x):
                break
            if x.isupper():                    # nombre de empresa en mayúsculas
                continue
            cargo = x.rstrip(".")
            break
        tel = ""
        for x in siguientes:
            m = _TELEFONO.search(x)
            if m:
                tel = re.sub(r"\s+", " ", m.group(1)).strip()
                break
        return cargo, tel
    return "", ""


def contactos(correos: list[dict], dominio: str, hoy: date) -> list[dict]:
    """Contactos del cliente: primero quien ha escrito, por su último correo; luego
    los que solo van en copia (al menos dos veces)."""
    dom = (dominio or "").lower()
    escritos: dict[str, dict] = {}
    for c in sorted(correos, key=lambda c: c["fecha"]):
        mail = c.get("de_email", "")
        if not dom or not mail.endswith("@" + dom):
            continue
        x = escritos.setdefault(mail, {"nombre": "", "email": mail, "cargo": "", "telefono": "", "ultimo": None,
                                       "asunto": "", "enviados": 0, "msgid": ""})
        x["enviados"] += 1
        x["nombre"] = c.get("de_nombre") or x["nombre"] or mail.split("@")[0]
        x["ultimo"], x["asunto"], x["msgid"] = c["fecha"].date(), c.get("asunto", ""), c.get("msgid", "")
        cargo, tel = firma(c.get("cuerpo", ""), x["nombre"])
        x["cargo"] = cargo or x["cargo"]
        x["telefono"] = tel or x["telefono"]
    copias, nombres = Counter(), {}
    for c in correos:
        for campo in ("para", "cc"):
            for nom, mail in getaddresses([str(c.get(campo) or "").replace("\n", " ")]):
                mail = mail.lower().strip()
                if dom and mail.endswith("@" + dom) and mail not in escritos:
                    copias[mail] += 1
                    nombres.setdefault(mail, nom.strip("'\" ") or mail.split("@")[0])
    out = sorted(escritos.values(), key=lambda x: x["ultimo"], reverse=True)
    out += [{"nombre": nombres[m], "email": m, "cargo": "", "telefono": "", "ultimo": None, "asunto": "", "enviados": 0,
             "msgid": ""} for m, k in copias.most_common() if k >= 2]
    return out
