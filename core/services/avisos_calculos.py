"""Avisos de «Cálculos realizados» (y de planos): del correo a la Agenda.

El departamento técnico avisa por correo cuando termina los cálculos de un
pedido («P-26/123 - Cálculos realizados»): en qué carpeta están, qué revisión
es y, a veces, algo a tener en cuenta («OJO con el nº de documento del cliente…»). Para el
Document Controller eso es trabajo: ya se puede subir la documentación.

Aquí se leen esos correos (solo lectura, no se marcan como leídos), y de cada
uno sale una tarea con el pedido, la carpeta y las notas. Una respuesta al aviso
(«RE: … ACTUALIZACIÓN. He incluido…») no es tarea nueva: se anota en la que ya
hay. Y la tarea se cierra sola cuando el seguimiento de documentos dice que los
cálculos de ese pedido salieron al cliente después del aviso.

Los planos suelen llegar como respuesta a ese mismo correo («RE: … Cálculos
realizados — Ya están hechos los planos… Se puede enviar para aprobación»):
eso es otra tarea, «Subir planos», con la carpeta y la revisión de los cálculos.

Los correos ya vistos se recuerdan por su Message-ID: una tarea que se borra a
mano no vuelve a aparecer en la siguiente pasada.
"""

import logging
import re
import unicodedata
from datetime import date, datetime, timedelta
from email.utils import parseaddr

from core.paths import state_dir
from core.services import agenda
from core.utils.json_store import read_json, write_json

logger = logging.getLogger(__name__)

REGISTRO_FILE = str(state_dir() / "avisos_calculos.json")

# Cuántos días atrás se mira el buzón. La primera vez trae lo de estas dos
# semanas que siga sin enviarse; luego solo lo que no se haya visto.
DIAS_ATRAS = 14
# Lo que se le pide al servidor, cualquiera de los dos en el asunto (ASCII:
# «lculo» vale para Cálculos y Calculos). El filtro de verdad son los _RE_ASUNTO.
BUSQUEDA = ("lculo", "plano")
# Se olvidan los Message-ID de hace más de esto (ya no entran en la búsqueda)
_OLVIDAR_DIAS = 120

_RE_ASUNTO = re.compile(r"c[aá]lculos?\b.*\b(realizad|revisad|hech|terminad|list)", re.I)
_RE_ASUNTO_PLANOS = re.compile(r"\bplanos?\b.*\b(realizad|revisad|hech|terminad|list)", re.I)
# Los planos suelen llegar como respuesta al aviso de cálculos: «Ya están hechos
# los planos y adjuntado al documento de cálculo y plano. Se puede enviar…»
_RE_PLANOS_LISTOS = re.compile(
    r"\bya\s+est[aá]n\s+(?:\w+\s+){0,2}?(hech|revisad|terminad|acabad|list)\w*\s+(?:\w+\s+){0,2}?planos\b"
    r"|\bplanos\s+(?:\w+\s+){0,3}?(?:ya\s+)?est[aá]n\s+(hech|revisad|terminad|acabad|list)", re.I)
_RE_SALUDO = re.compile(r"^\s*(hola\b|buen[oa]s\b)", re.I)
_RE_PREFIJO = re.compile(r"^\s*(?:re|rv|fw|fwd|tr|reenv\w*)\s*:\s*", re.I)
_RE_PEDIDO = re.compile(r"\b(PA?)\s*-\s*(\d{2})\s*/\s*(\d{3})(?:\s*-\s*S\s*(\d{2}))?", re.I)
# En la carpeta el pedido va con guiones: «P-26-123-S00 - CLIENTE - PRODUCTO»
_RE_PEDIDO_CARPETA = re.compile(r"^(PA?)-(\d{2})-(\d{3})(?:\s*-\s*S?(\d{2}))?\b", re.I)
_RE_RUTA = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\)[^<>\r\n\"]+")
_RE_REV = re.compile(r"\brev\.?\s*(\d+(?:\s*-\s*\d+)?)", re.I)
# Dónde acaba lo que escribió el remitente: despedida, cita de otro correo, pie legal
_RE_FIN = re.compile(r"^\s*(si necesit|un saludo|saludos|gracias|atentamente|nota legal)", re.I)
_RE_CITA = re.compile(r"^\s*(de|from|enviado el|sent)\s*:|^\s*-{2,}\s*(mensaje original|original message)",
                      re.I)
# La firma, cuando no hay despedida antes
_RE_FIRMA = re.compile(r"^\s*(tl?f\w*\.?\s*:|tel\w*\.?\s*:|www\.|https?://|technical department)", re.I)
# Lo que no es una nota: saludo, la frase del aviso, la línea que llevan todos
_RE_RELLENO = re.compile(r"^\s*(hola\b|buen[oa]s\b)|siguiente carpeta|^\s*ya est[aá]n .*c[aá]lculo"
                         r"|^\s*erp actualizado con los datos\.?\s*$|^\s*actualizaci[oó]n\W*$", re.I)


# ── Leer un aviso ─────────────────────────────────────────────────────────────

def analizar(asunto: str, texto: str, remitente: str = "", fecha_iso: str = "",
             message_id: str = "") -> dict | None:
    """Asunto y cuerpo (texto) de un correo → el aviso, o None si no lo es.

    El pedido sale del asunto; el suministro, de la carpeta si viene (es donde
    están los ficheros: el asunto a veces lo omite o lo cambia)."""
    asunto = (asunto or "").strip()
    limpio, respuesta = asunto, False
    while _RE_PREFIJO.match(limpio):
        limpio, respuesta = _RE_PREFIJO.sub("", limpio, count=1), True
    de_calculos = bool(_RE_ASUNTO.search(limpio))
    if not de_calculos and not _RE_ASUNTO_PLANOS.search(limpio):
        return None
    m = _RE_PEDIDO.search(limpio) or _RE_PEDIDO.search(texto or "")
    if not m:
        return None
    pedido = f"{m[1].upper()}-{m[2]}/{m[3]}"
    supp = f"S{m[4]}" if m[4] else ""

    nombre, correo = parseaddr(remitente or "")
    nombre = nombre.strip().strip("'\"").strip()
    del_correo = _nombre_de_correo(correo)
    # Hay cuentas cuyo «nombre» es la dirección otra vez («pepe-perez pepe-perez»)
    if not nombre or "-" in nombre or "@" in nombre:
        nombre = del_correo or nombre
    lineas = _lineas_propias(texto or "", nombre, del_correo)
    propio = " ".join(lineas)
    # Planos: lo dice el texto («ya están hechos los planos…») o un asunto de planos
    planos = bool(_RE_PLANOS_LISTOS.search(propio)) or not de_calculos
    eco = _comparable(limpio)
    rutas: list[str] = []
    notas: list[str] = []
    for ln in lineas:
        sin_enlace = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", ln)).strip()
        encontradas = [_ruta(r) for r in _RE_RUTA.findall(sin_enlace)]
        if encontradas:
            rutas.extend(r for r in encontradas if r and r not in rutas)
            continue
        if not sin_enlace or eco in _comparable(sin_enlace):
            continue                          # vacía, o el asunto repetido en el cuerpo
        # En los de planos la frase «Ya están hechos los planos…» ES el mensaje
        if (_RE_SALUDO.search(sin_enlace) if planos else _RE_RELLENO.search(sin_enlace)):
            continue
        notas.append(sin_enlace if len(sin_enlace) <= 220 else sin_enlace[:219] + "…")
    notas = notas[:8]

    carpeta = rutas[0] if rutas else ""
    cliente, rev = "", ""
    if carpeta:
        for parte in re.split(r"[\\/]", carpeta):
            mc = _RE_PEDIDO_CARPETA.match(parte.strip())
            if mc and f"{mc[1].upper()}-{mc[2]}/{mc[3]}" == pedido:
                if mc[4]:
                    supp = f"S{mc[4]}"
                cliente = re.sub(r"^PA?-\d{2}-\d{3}(?:\s*-\s*S?\d{2})?\s*-\s*", "",
                                 parte.strip(), flags=re.I)
                break
        revs = _RE_REV.findall(carpeta)
        rev = re.sub(r"\s+", "", revs[-1]) if revs else ""

    return {
        "tipo": "planos" if planos else ("actualizacion" if respuesta else "aviso"),
        "respuesta": respuesta,
        "pedido": pedido,
        "supp": supp,
        "pedido_completo": f"{pedido}-{supp}" if supp else pedido,
        "carpeta": carpeta,
        "otras_carpetas": rutas[1:],
        "rev": rev,
        "cliente": cliente,
        "notas": notas,
        "remitente": nombre,
        "remitente_correo": correo.lower(),
        "fecha": _fecha_corta(fecha_iso),
        "recibido": fecha_iso or "",
        "message_id": message_id or "",
        "asunto": asunto,
    }


def _lineas_propias(texto: str, *nombres: str) -> list[str]:
    """Las líneas que escribió el remitente: hasta la despedida, la firma
    (empieza por su nombre) o la cita del correo anterior."""
    firmas = {_comparable(n) for n in nombres if _comparable(n)}
    out = []
    for ln in texto.splitlines():
        if _RE_FIN.match(ln) or _RE_CITA.match(ln) or _RE_FIRMA.match(ln):
            break
        if any(_comparable(ln).startswith(f) for f in firmas):
            break
        out.append(ln.strip())
    return out


def _comparable(texto: str) -> str:
    return " ".join(re.split(r"[\s\-._]+", _sin_acentos(texto).lower())).strip()


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn")


def _ruta(texto: str) -> str:
    r = texto.strip().rstrip(".,;:").strip()
    return r.replace("/", "\\") if re.match(r"^[A-Za-z]:", r) else r


def _nombre_de_correo(correo: str) -> str:
    local = (correo or "").split("@")[0]
    return " ".join(p.capitalize() for p in re.split(r"[-._]+", local) if p)


def _fecha_corta(fecha_iso: str) -> str:
    d = _a_fecha(fecha_iso)
    return d.strftime("%d-%m-%Y") if d else ""


def _a_fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    txt = str(valor or "").strip()
    if not txt:
        return None
    try:
        return datetime.fromisoformat(txt).date()
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(txt[:10], fmt).date()
        except ValueError:
            continue
    return None


def texto_del_correo(msg) -> str:
    """Cuerpo legible de un email.Message (el HTML pasado a texto, o el plano)."""
    from core.services import imap as imap_service
    from core.services import inbox
    html = imap_service.get_html_body(msg) or ""
    texto = inbox.html_to_text(html) if html else ""
    return texto or imap_service.get_plain_body(msg) or ""


# ── La tarea ──────────────────────────────────────────────────────────────────

# Origen de la tarea → qué tipo de documento la cierra al enviarse
ORIGENES = {"calculos": "lculo", "planos": "plano"}


def tarea_de(aviso: dict, owner: str = agenda.DEFAULT_OWNER, base: dict | None = None) -> dict:
    """La tarea de un aviso. Para los planos, `base` es la tarea de cálculos
    del mismo pedido: la respuesta de planos no trae carpeta ni revisión, y son
    las de los cálculos (los planos van adjuntos al documento de cálculo)."""
    base = base or {}
    planos = aviso.get("tipo") == "planos"
    rev = aviso.get("rev") or (base.get("rev", "") if planos else "")
    cliente = aviso.get("cliente") or (base.get("cliente", "") if planos else "")
    titulo = f"Subir {'planos' if planos else 'cálculos'} {aviso['pedido_completo']}"
    if rev:
        titulo += f" · rev {rev}"
    partes = [cliente] if cliente else []
    partes += aviso.get("notas") or []
    return {
        "titulo": titulo,
        "descripcion": " · ".join(partes),
        "prioridad": "media",
        "estado": "pendiente",
        # Ya se puede subir: toca desde el día que llega el aviso
        "fecha_limite": aviso.get("fecha", ""),
        "asignado": owner,
        "origen": "planos" if planos else "calculos",
        "source_msgid": aviso.get("message_id", ""),
        "pedido": aviso["pedido"],
        "supp": aviso.get("supp", ""),
        "carpeta": aviso.get("carpeta") or (base.get("carpeta", "") if planos else ""),
        "otras_carpetas": aviso.get("otras_carpetas") or [],
        "rev": rev,
        "cliente": cliente,
        "notas": aviso.get("notas") or [],
        "remitente": aviso.get("remitente", ""),
        "recibido": aviso.get("recibido", ""),
        "actualizaciones": [],
    }


def _mismo_pedido(doc_pedido: str, pedido: str, supp: str) -> bool:
    np = re.sub(r"\s+", "", str(doc_pedido or "")).upper()
    if supp:
        return np == f"{pedido}-{supp}".upper()
    return np == pedido.upper() or np.startswith(pedido.upper() + "-")


def ya_enviado(pedido: str, supp: str, recibido, docs: list[dict], origen: str = "calculos") -> bool:
    """¿Salieron cálculos (o planos) de ese pedido al cliente el día del aviso o después?

    Lo dice el seguimiento de documentos: un documento de ese tipo («Cálculo y
    plano» vale para los dos) de ese pedido —y suministro, si se sabe— con
    fecha de envío no anterior al aviso."""
    desde = _a_fecha(recibido)
    clave = ORIGENES.get(origen, "lculo")
    if desde is None:
        return False
    for d in docs or ():
        if clave not in str(d.get("Tipo Doc.", "") or "").lower():
            continue
        if not _mismo_pedido(d.get("Nº Pedido", ""), pedido, supp):
            continue
        enviado = _a_fecha(d.get("Fecha Env. Doc."))
        if enviado and enviado >= desde:
            return True
    return False


def cerrar_enviados(owner: str, docs: list[dict]) -> list[dict]:
    """Completa las tareas de aviso cuyos documentos ya salieron al cliente."""
    cerradas = []
    for t in agenda.get_tareas(owner):
        if t.get("origen") not in ORIGENES or t.get("estado") == "completada":
            continue
        if ya_enviado(t.get("pedido", ""), t.get("supp", ""), t.get("recibido"), docs, t["origen"]):
            hecha = agenda.update("tareas", t["id"], {
                "estado": "completada",
                "cerrada_sola": date.today().strftime("%d-%m-%Y"),
            })
            if hecha:
                cerradas.append(hecha)
    return cerradas


def _de_calculos(owner: str, pedido: str, supp: str, abiertas: bool = True) -> list[dict]:
    return [t for t in agenda.get_tareas(owner)
            if t.get("origen") == "calculos" and t.get("pedido") == pedido
            and (not abiertas or t.get("estado") != "completada")
            and (not supp or t.get("supp") in ("", supp))]


def _anotar(owner: str, aviso: dict) -> dict | None:
    """Una respuesta al aviso: se añade a la tarea abierta de ese pedido."""
    if not aviso.get("notas"):
        return None
    abiertas = _de_calculos(owner, aviso["pedido"], aviso.get("supp", ""))
    if not abiertas:
        return None
    t = max(abiertas, key=lambda x: x.get("recibido") or "")
    nota = {"fecha": aviso.get("fecha", ""), "remitente": aviso.get("remitente", ""),
            "texto": " · ".join(aviso["notas"])}
    return agenda.update("tareas", t["id"], {
        "actualizaciones": list(t.get("actualizaciones") or []) + [nota]})


# ── La pasada por el buzón ────────────────────────────────────────────────────

def _cargar_registro() -> dict:
    reg = read_json(REGISTRO_FILE, default={})
    if not isinstance(reg, dict):
        reg = {}
    if not isinstance(reg.get("vistos"), dict):
        reg["vistos"] = {}
    return reg


def _guardar_registro(reg: dict) -> None:
    limite = (date.today() - timedelta(days=_OLVIDAR_DIAS)).isoformat()
    reg["vistos"] = {k: v for k, v in reg["vistos"].items() if str(v) >= limite}
    write_json(REGISTRO_FILE, reg)


def carpetas_de_pedidos(nombres: list[str]) -> list[str]:
    """La bandeja de entrada y las carpetas del año (donde se archivan por
    pedido: «INBOX/P. 2026/P-26-123»). En enero, también las del año pasado."""
    hoy = date.today()
    anos = {hoy.year} | ({hoy.year - 1} if hoy.month == 1 else set())
    patron = re.compile(r"\b(" + "|".join(str(a) for a in sorted(anos)) + r")\b")
    return [n for n in nombres if n.upper() == "INBOX" or patron.search(n)]


def _dominio(correo: str) -> str:
    return correo.rsplit("@", 1)[-1].lower() if "@" in (correo or "") else ""


def buzones() -> list[dict]:
    """Los buzones donde mirar: el de la app y, si se configuró en Ajustes ▸
    Correo, el personal (hay avisos que solo llegan ahí: una respuesta de
    planos a la que no se puso al buzón compartido)."""
    from core import config
    out = [{"user": config.IMAP_USER or "", "password": None}]
    extra = (getattr(config, "AVISOS_USER", "") or "").strip()
    if extra and extra.lower() != (config.IMAP_USER or "").lower() and config.AVISOS_PASS:
        out.append({"user": extra, "password": config.AVISOS_PASS})
    return out


def revisar(completo: bool = False, owner: str = agenda.DEFAULT_OWNER,
            docs: list[dict] | None = None, buscar=None, cuentas: list[dict] | None = None) -> dict:
    """Busca avisos nuevos (cálculos y planos) y los pasa a la Agenda.

    completo=False mira solo la bandeja de entrada (rápido); True también las
    carpetas de los pedidos. Con `docs` (el seguimiento de documentos) no se
    crea tarea de lo que ya se envió y se cierran las que ya están enviadas.
    Un correo que llega a los dos buzones tiene el mismo Message-ID: cuenta una
    vez. `buscar` y `cuentas` existen para las pruebas.
    """
    if buscar is None:
        from core.services import imap as imap_service
        buscar = imap_service.buscar_asunto
    if cuentas is None:
        cuentas = buzones()
    propios = {(c.get("user") or "").lower() for c in cuentas} - {""}
    interno = next((_dominio(u) for u in propios if _dominio(u)), "")

    reg = _cargar_registro()
    vistos: dict = reg["vistos"]
    ya_en_agenda = {t.get("source_msgid") for t in agenda.get_tareas(owner)
                    if t.get("origen") in ORIGENES and t.get("source_msgid")}
    conocidos = set(vistos) | ya_en_agenda

    correos, errores = [], []
    for cuenta in cuentas:
        try:
            correos += buscar(BUSQUEDA, days=DIAS_ATRAS,
                              carpetas=carpetas_de_pedidos if completo else "INBOX",
                              saltar=conocidos | {c.get("message_id") for c in correos},
                              imap_user=cuenta.get("user") or None,
                              imap_pass=cuenta.get("password") or None)
        except Exception as exc:  # noqa: BLE001 — un buzón que falla no para el otro
            logger.info("Avisos: no se pudo leer %s: %s", cuenta.get("user"), exc)
            errores.append(f"{cuenta.get('user')}: {exc}")
    if errores and len(errores) == len(cuentas):
        raise RuntimeError("; ".join(errores))
    # El aviso antes que sus respuestas
    correos = sorted(correos, key=lambda c: c.get("date") or "")

    hoy = date.today().isoformat()
    nuevas, actualizadas = [], []
    for c in correos:
        clave = c.get("message_id") or f"{c.get('subject', '')}|{c.get('date', '')}"
        if clave in conocidos:
            continue
        conocidos.add(clave)
        vistos[clave] = hoy
        texto = c.get("texto")
        if texto is None:
            texto = texto_del_correo(c["msg"]) if c.get("msg") is not None else ""
        aviso = analizar(c.get("subject", ""), texto, c.get("from", ""),
                         c.get("date", ""), c.get("message_id", ""))
        if aviso is None:
            continue
        de = aviso["remitente_correo"]
        # Solo compañeros: ni un cliente que conteste con ese asunto, ni lo propio
        if (interno and _dominio(de) != interno) or de in propios:
            continue
        if aviso["tipo"] == "actualizacion":
            t = _anotar(owner, aviso)
            if t:
                actualizadas.append(t)
            continue
        base = None
        if aviso["tipo"] == "planos":
            todas = _de_calculos(owner, aviso["pedido"], aviso["supp"], abiertas=False)
            base = max(todas, key=lambda x: x.get("recibido") or "") if todas else None
            if base and not aviso["supp"] and base.get("supp"):
                aviso["supp"] = base["supp"]
                aviso["pedido_completo"] = f"{aviso['pedido']}-{base['supp']}"
            if aviso["respuesta"]:
                _anotar(owner, aviso)         # que la de cálculos también lo diga
        origen = "planos" if aviso["tipo"] == "planos" else "calculos"
        if docs is not None and ya_enviado(aviso["pedido"], aviso["supp"], aviso["recibido"], docs, origen):
            continue
        aviso["message_id"] = clave
        nuevas.append(agenda.create_tarea(owner, tarea_de(aviso, owner, base)))
        logger.info("Aviso de %s %s → tarea en la Agenda", origen, aviso["pedido_completo"])

    if completo:
        reg["ultimo_completo"] = datetime.now().isoformat(timespec="seconds")
    _guardar_registro(reg)
    cerradas = cerrar_enviados(owner, docs) if docs is not None else []
    return {"nuevas": nuevas, "actualizadas": actualizadas, "cerradas": cerradas,
            "errores": errores}
