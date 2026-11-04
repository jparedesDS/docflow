"""Lo que el cliente ha devuelto y el ERP todavía no dice.

Cada devolución que la app archiva en `dev. <Tipo>\\rev <nuestra>-<cliente> AP|COM|com|REJ`
se apunta aquí con lo que habría que poner en el ERP, en el orden en que se
mete en la línea del documento:

  · **Fecha**: la del correo de la devolución, «dd/mm/aaaa» como la guarda el ERP.
  · **Estado**: el de la resolución, con el nombre del ERP — Aprobado,
    Com. Menores, Com. Mayores, Comentado, Rechazado; «Informativo» es
    «Información» y un VOID se propone «Eliminado», a revisar.
  · **1er envío** (`date_first_rev`), si el ERP no lo tiene: la fecha en que
    se envió la rev 0. Mientras el documento sigue «Enviado» en rev 0, es su
    fecha de estado; al poner la de la devolución esa fecha se pierde, así que
    se guarda aquí en cuanto se ve. El registro de cambios del ERP no sirve para
    sacarla después (probado: casi nunca coincide).

La **revisión no se toca**: solo cambia al ENVIAR. La nuestra (la de la
carpeta, desde el 0) y la del cliente (A, 0, B…) se enseñan para reconocer el
documento, y la nuestra dice cuándo una devolución ya es historia: si el ERP va
por una revisión posterior, se volvió a enviar.

Luego se compara con el ERP (solo lectura) y queda lo que no cuadra. Una línea
sale sola cuando el ERP ya tiene ese estado, una fecha de esos días (es el día
que se apunta) y el 1er envío; o cuando el documento ya se reenvió (el ERP dice
«Enviado» de después de la devolución, o va por una revisión posterior). De
cada documento cuenta su última devolución; si el cliente lo devolvió varias
veces el mismo día con la misma revisión, vale cualquiera de esos resultados.

El registro es local (`state/registro_erp.json`) y no escribe en el ERP.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from core.paths import state_dir
from core.utils.json_store import read_json, write_json

logger = logging.getLogger(__name__)

REGISTRO_FILE = str(state_dir() / "registro_erp.json")

# Las devoluciones de hace más de esto se olvidan (ya no son trabajo)
_OLVIDAR_DIAS = 365
# El ERP se apunta el día que se trabaja la devolución, no siempre el mismo
_FECHA_ANTES, _FECHA_DESPUES = 3, 10

APROBADO, INFORMACION = "Aprobado", "Información"
COM_MENORES, COM_MAYORES = "Com. Menores", "Com. Mayores"
RECHAZADO, ELIMINADO = "Rechazado", "Eliminado"


def _fold(s) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower())
                   if unicodedata.category(c) != "Mn")


COMENTADO = "Comentado"
# Los parsers dejan el estado con estos nombres (VALID_STATUSES de Devoluciones)
_DIRECTO = {"aprobado": APROBADO, "com. menores": COM_MENORES, "com. mayores": COM_MAYORES,
            "comentado": COMENTADO, "rechazado": RECHAZADO, "informativo": INFORMACION,
            "void": ELIMINADO}


def estado_erp(estado_portal: str) -> str:
    """La resolución del cliente → el «Estado» que lleva en el ERP."""
    from core.services import dev_folders
    directo = _DIRECTO.get(_fold(estado_portal).strip())
    if directo:
        return directo
    sufijo = dev_folders._suffix(estado_portal)
    if sufijo == dev_folders.VOID_DIR:
        return ELIMINADO
    if sufijo == "AP":
        e = _fold(estado_portal)
        return INFORMACION if ("informa" in e and "aprob" not in e) else APROBADO
    return {"REJ": RECHAZADO, "COM": COM_MAYORES}.get(sufijo, COM_MENORES)


def norm(code) -> str:
    return re.sub(r"\s+", "", str(code or "")).upper()


def _clave_doc(e: dict) -> str:
    return norm(e.get("doc_eipsa")) or f"CLI:{norm(e.get('doc_cliente'))}"


def _fecha_erp(valor) -> str:
    """Una fecha (ISO, «dd-mm-aaaa», datetime) → «dd/mm/aaaa»."""
    from core.services.dev_folders import fecha_de
    d = valor if isinstance(valor, date) else fecha_de(str(valor or ""))
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d/%m/%Y") if d else ""


def _a_fecha(txt) -> date | None:
    txt = str(txt or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(txt[:10], fmt).date()
        except ValueError:
            continue
    return None


# ── El registro ───────────────────────────────────────────────────────────────

def _cargar() -> dict:
    reg = read_json(REGISTRO_FILE, default={})
    if not isinstance(reg, dict):
        reg = {}
    if not isinstance(reg.get("devueltos"), dict):
        reg["devueltos"] = {}
    return reg


def _guardar(reg: dict) -> None:
    limite = (date.today() - timedelta(days=_OLVIDAR_DIAS)).isoformat()
    reg["devueltos"] = {k: v for k, v in reg["devueltos"].items()
                        if str(v.get("anotado", "")) >= limite}
    write_json(REGISTRO_FILE, reg)


def anotar(archive: dict, fecha_correo: str = "", portal: str = "", capturar: bool = True,
           codigo: str = "") -> int:
    """Apunta los documentos que `dev_folders` acaba de archivar
    (`archive["devueltos"]`). `codigo` es el del transmittal: une la devolución
    con su correo en la lista. Devuelve cuántos son nuevos."""
    devueltos = (archive or {}).get("devueltos") or []
    if not devueltos:
        return 0
    reg = _cargar()
    fecha = _fecha_erp(fecha_correo) or date.today().strftime("%d/%m/%Y")
    nuevos, cambiado = 0, False
    for d in devueltos:
        if not (norm(d.get("doc_eipsa")) or norm(d.get("doc_cliente"))):
            continue
        nuestra = str(d.get("nuestra") or "").strip()
        entrada = {
            "pedido": d.get("pedido", ""),
            "doc_eipsa": norm(d.get("doc_eipsa")),
            "doc_cliente": norm(d.get("doc_cliente")),
            "titulo": str(d.get("titulo") or "")[:160],
            "nuestra": nuestra,
            "cliente": str(d.get("cliente") or ""),
            "estado_portal": str(d.get("estado") or ""),
            "estado": estado_erp(d.get("estado") or ""),
            "fecha": fecha,
            "recibido": _momento(fecha_correo),
            "carpeta": str(d.get("carpeta") or ""),
            "portal": portal,
            "codigo": codigo,
            "anotado": datetime.now().isoformat(timespec="seconds"),
        }
        if d.get("recuperado"):
            # Sacado de la carpeta: «AP» no distingue aprobado de informativo
            entrada["recuperado"] = True
            if entrada["estado"] == APROBADO:
                entrada["estado_alt"] = [INFORMACION]
        clave = f"{_clave_doc(entrada)}|{nuestra}|{entrada['estado']}"
        if clave in reg["devueltos"]:
            # La misma devolución, otra vez (rearchivo): como mucho, se le pone el código
            if codigo and not reg["devueltos"][clave].get("codigo"):
                reg["devueltos"][clave]["codigo"] = codigo
                cambiado = True
            continue
        reg["devueltos"][clave] = entrada
        nuevos += 1
    if cambiado and not nuevos:
        _guardar(reg)
    if nuevos:
        _guardar(reg)
        logger.info("Registro ERP: %d devolución(es) apuntada(s)", nuevos)
        # Ahora el ERP aún dice «Enviado»: es cuando se ve la fecha del 1er envío
        if capturar:
            capturar_envios()
    return nuevos


# ── Lo archivado antes de que existiera el registro ──────────────────────────

# Subcarpeta de resolución dentro de una revisión («rev0\\com. menores») → sufijo
_SUBCARPETA_SUFIJO = {"com. menores": "com", "com. mayores": "COM", "aprobados": "AP",
                      "rechazados": "REJ"}
_ESTADO_SUFIJO = {"AP": APROBADO, "com": COM_MENORES, "COM": COM_MAYORES, "REJ": RECHAZADO}


def _rev_de_carpeta(carpeta) -> tuple[str, str, str] | None:
    """(nuestra, cliente, estado ERP) de la carpeta donde quedó un fichero
    devuelto, o None si no es una carpeta de revisión (o es un VOID)."""
    from pathlib import Path

    from core.services import dev_folders
    carpeta = Path(carpeta)
    sufijo = _SUBCARPETA_SUFIJO.get(carpeta.name.strip().lower())
    rev = carpeta.parent if sufijo else carpeta
    partes = dev_folders._partes_rev(rev.name)
    if not partes:
        return None
    num, cliente, cola = partes
    if not sufijo:
        sufijo = (cola.split() or [""])[0]          # «COM 22-10-2026» → «COM»
    if sufijo.upper() == "AP":
        sufijo = "AP"
    elif sufijo.upper() == "REJ":
        sufijo = "REJ"
    estado = _ESTADO_SUFIJO.get(sufijo)            # com / COM: la caja importa
    if estado is None:
        return None
    return (str(num) if num is not None else ""), cliente, estado


def _documento_del_fichero(nombre: str, codigos: dict) -> tuple[str, str] | None:
    """(Nº EIPSA, Nº cliente) del documento cuyo código va en el nombre del
    fichero; el más largo, que «…-001» no se confunda con «…-0010»."""
    tallo = norm(nombre.rsplit(".", 1)[0])
    hits = [c for c in codigos if len(c) >= 6 and c in tallo]
    if not hits:
        return None
    return codigos[max(hits, key=len)]


def _donde_quedo(carpetas: list[str], nombre: str, tamaño: int):
    """La carpeta de esa devolución donde está ESE fichero: mismo nombre y mismo
    tamaño. Un nombre solo no basta: el cliente devuelve el mismo fichero con el
    mismo nombre en otra revisión, y puede estar en dos de ellas. Y si al
    archivarlo ya había uno con ese nombre, se guardó al lado como «nombre_1.pdf»."""
    from pathlib import Path
    tallo, punto, ext = nombre.rpartition(".")
    otro = re.compile(re.escape(tallo) + r"_\d+" + re.escape(punto + ext) + "$", re.I) if punto else None
    for f in carpetas:
        carpeta = Path(f)
        try:
            ruta = carpeta / nombre
            if ruta.is_file() and ruta.stat().st_size == tamaño:
                return carpeta
            if otro is not None and carpeta.is_dir():
                for hermano in carpeta.iterdir():
                    if otro.match(hermano.name) and hermano.stat().st_size == tamaño:
                        return carpeta
        except OSError:
            continue
    return None


def _fecha_del_correo(eml) -> str:
    """La fecha (cabecera Date) del correo de la devolución guardado, ISO, o ''."""
    if not eml:
        return ""
    try:
        from email.parser import BytesHeaderParser
        from email.utils import parsedate_to_datetime
        with open(eml, "rb") as fh:
            cab = BytesHeaderParser().parse(fh)
        # Con la hora: el mismo documento puede devolverse dos veces el mismo día
        return parsedate_to_datetime(cab.get("Date", "")).replace(tzinfo=None).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001 — sin fecha legible, la de la descarga
        return ""


def recuperar_archivado(docs: list[dict] | None = None, descargas: dict | None = None) -> int:
    """Apunta las devoluciones que la app archivó antes de que hubiera registro.

    Solo lee: de cada descarga (`portal_downloads`), los nombres de su zip y las
    carpetas `dev.` donde quedaron. La carpeta da nuestra revisión, la del
    cliente y la resolución (AP, com, COM, REJ); el nombre del fichero, el
    documento (su Nº del cliente o EIPSA, contra el seguimiento de documentos);
    la fecha es la de la descarga, que va minutos detrás del correo. Un AP puede
    ser «Información» en el ERP: se admite cualquiera de las dos.

    Cada transmittal se mira una vez (`reg["recuperados2"]`). Devuelve cuántas
    devoluciones nuevas apunta. Nunca lanza."""
    import zipfile
    from pathlib import Path
    try:
        if descargas is None:
            from core.services import portal_downloads
            descargas = portal_downloads._registry().get("done", {})
        reg = _cargar()
        vistos = set(reg.setdefault("recuperados2", []))
        vistos |= {e.get("codigo") for e in reg["devueltos"].values() if e.get("codigo")}
        pendientes = {c: d for c, d in (descargas or {}).items()
                      if c not in vistos and d.get("dev_folders") and d.get("zip")}
        if not pendientes:
            return 0
        if docs is None:
            from core.services import monitoring
            docs = monitoring.get_monitoring_data() or []
        por_pedido: dict[str, dict] = {}
        for d in docs:
            ped = re.sub(r"-S\d{2}[A-Z]?$", "", str(d.get("Nº Pedido", "")).strip(), flags=re.I).upper()
            ids = (norm(d.get("Nº Doc. EIPSA")), norm(d.get("Nº Doc. Cliente")))
            sitio = por_pedido.setdefault(ped, {})
            for c in ids:
                if c:
                    sitio.setdefault(c, ids)
        nuevos = 0
        for codigo, d in pendientes.items():
            try:
                with zipfile.ZipFile(d["zip"]) as zf:
                    ficheros = [(Path(i.filename).name, i.file_size) for i in zf.infolist() if not i.is_dir()]
            except (OSError, zipfile.BadZipFile):
                # Un PDF suelto (Document Space no empaqueta) o el zip ya no está
                zp = Path(d["zip"])
                try:
                    ficheros = [(zp.name, zp.stat().st_size)] if zp.suffix.lower() == ".pdf" else []
                except OSError:
                    ficheros = []
            codigos = por_pedido.get(str(d.get("pedido", "")).upper(), {})
            devueltos = []
            # Carpetas donde se archivó y que ya no están (se movieron a mano): su
            # nombre sigue diciendo lo que el cliente resolvió entonces
            movidas = [f for f in d["dev_folders"] if not Path(f).is_dir()]
            for nombre, tamaño in ficheros:
                doc = _documento_del_fichero(nombre, codigos)
                carpeta = _donde_quedo(d["dev_folders"], nombre, tamaño) if doc else None
                if doc and carpeta is None and len(movidas) == 1:
                    carpeta = Path(movidas[0])
                rev = _rev_de_carpeta(carpeta) if (doc and carpeta) else None
                if not rev or any(x["doc_eipsa"] == doc[0] and x["doc_cliente"] == doc[1] for x in devueltos):
                    continue
                devueltos.append({"pedido": d.get("pedido", ""), "doc_eipsa": doc[0], "doc_cliente": doc[1],
                                  "titulo": "", "nuestra": rev[0], "cliente": rev[1],
                                  "estado": rev[2], "carpeta": str(carpeta), "recuperado": True})
            if devueltos:
                nuevos += anotar({"devueltos": devueltos}, _fecha_del_correo(d.get("eml")) or d.get("when", ""),
                                 d.get("portal", ""), capturar=False, codigo=codigo)
            reg = _cargar()
            reg.setdefault("recuperados2", []).append(codigo)
            _guardar(reg)
        if nuevos:
            logger.info("Registro ERP: %d devolución(es) recuperadas de lo ya archivado", nuevos)
            capturar_envios()
        return nuevos
    except Exception as exc:  # noqa: BLE001 — es un apunte: no puede tirar nada
        logger.warning("Registro ERP: no se pudo recuperar lo archivado: %s", exc)
        return 0


def ignorar(clave: str) -> None:
    """Que esa devolución deje de salir (p. ej. se decidió no registrarla)."""
    reg = _cargar()
    if clave in reg["devueltos"]:
        reg["devueltos"][clave]["ignorada"] = date.today().isoformat()
        _guardar(reg)


# ── Contra el ERP ─────────────────────────────────────────────────────────────

_SQL = """
    SELECT num_doc_eipsa, num_doc_client, num_order, state, revision, state_date, date_first_rev
    FROM documentation
    WHERE upper(num_doc_eipsa) = ANY(%s)
       OR upper(regexp_replace(num_doc_client, '\\s', '', 'g')) = ANY(%s)
"""


def leer_erp(entradas: list[dict]) -> dict | None:
    """{clave_doc → fila del ERP} de esos documentos, o None si no hay ERP."""
    from core.services import erp_common
    if not erp_common.available():
        return None
    eipsa = sorted({e["doc_eipsa"] for e in entradas if e.get("doc_eipsa")})
    cliente = sorted({e["doc_cliente"] for e in entradas if e.get("doc_cliente")})
    if not (eipsa or cliente):
        return {}
    # Un array vacío no tiene tipo para PostgreSQL: «''» no casa con nada
    filas = erp_common.query(_SQL, (eipsa or [""], cliente or [""]))
    por_eipsa = {norm(f.get("num_doc_eipsa")): f for f in filas if f.get("num_doc_eipsa")}
    por_cliente = {norm(f.get("num_doc_client")): f for f in filas if f.get("num_doc_client")}
    out = {}
    for e in entradas:
        f = por_eipsa.get(e.get("doc_eipsa", "")) or por_cliente.get(e.get("doc_cliente", ""))
        if f is not None:
            out[_clave_doc(e)] = f
    return out


def _reenviado_en_disco(e: dict, desde: date) -> bool | None:
    """¿Hay en las carpetas env del pedido un fichero de ese documento con
    fecha de `desde` o posterior? None si no se puede mirar (sin carpeta, M:
    caída): entonces no se sabe y manda el ERP."""
    import os
    from pathlib import Path
    carpeta = str(e.get("carpeta") or "")
    if "2-Tecnico" not in carpeta:
        return None
    tecnico = Path(carpeta.split("2-Tecnico")[0] + "2-Tecnico")
    codigos = [c for c in (norm(e.get("doc_eipsa")), norm(e.get("doc_cliente"))) if len(c) >= 6]
    try:
        if not codigos or not tecnico.is_dir():
            return None
        for sub in tecnico.iterdir():
            if not (sub.is_dir() and sub.name.lower().startswith("env")):
                continue
            for raiz, _dirs, ficheros in os.walk(sub):
                for nombre in ficheros:
                    if any(c in norm(nombre) for c in codigos):
                        if date.fromtimestamp(os.path.getmtime(os.path.join(raiz, nombre))) >= desde:
                            return True
    except OSError:
        return None
    return False


# Los estados que son el resultado de una devolución (no «Enviado» ni vacío)
_RESULTADOS = {_fold(x) for x in (APROBADO, INFORMACION, COM_MENORES, COM_MAYORES, COMENTADO, RECHAZADO)}


def _rev_erp(fila: dict) -> int | None:
    try:
        r = fila.get("revision")
        return int(r) if r not in (None, "") else None
    except (TypeError, ValueError):
        return None


def envio_rev0(fila: dict | None) -> str:
    """La fecha del envío de la rev 0, si el ERP aún la tiene a la vista: el
    documento sigue «Enviado» en rev 0 y su fecha de estado es la del envío."""
    if not fila or _fold(fila.get("state")).strip() != "enviado" or _rev_erp(fila) != 0:
        return ""
    d = _a_fecha(fila.get("state_date"))
    return d.strftime("%d/%m/%Y") if d else ""


def comparar(e: dict, fila: dict | None) -> dict | None:
    """Lo que falta en el ERP para esa devolución, o None si ya cuadra.

    {falta: [campos, en el orden en que se meten], erp: {…}, primer_envio, motivo}.
    `falta` puede llevar «fecha», «estado» y «primer_envio»; la revisión no:
    no se toca al recibir."""
    if fila is None:
        return {"falta": ["documento"], "erp": {}, "primer_envio": "", "motivo": "no está en el ERP"}
    erp = {"estado": str(fila.get("state") or "").strip(),
           "revision": fila.get("revision"),
           "fecha": str(fila.get("state_date") or "").strip(),
           "primer_envio": str(fila.get("date_first_rev") or "").strip()}
    nuestra = e.get("nuestra", "")
    n = int(nuestra) if str(nuestra).isdigit() else None
    rev_erp = _rev_erp(fila)
    # El ERP ya va por una revisión nuestra posterior: se reenvió, esto es historia
    if n is not None and rev_erp is not None and rev_erp > n:
        return None
    dev, puesta = _a_fecha(e.get("fecha")), _a_fecha(erp["fecha"])
    estado_erp_ahora = _fold(erp["estado"]).strip()
    # O dice «Enviado» del día de la devolución o de después: también se reenvió,
    # aunque la revisión del ERP no se subiera (P-23/044: devuelta la 51 el 31/10,
    # enviada la 52 el 03/11 y el ERP seguía en rev 5; P-23/037, reenviado el
    # mismo día que volvió)
    # Pero solo si de verdad salió algo: un «Enviado» con la fecha cambiada y
    # el estado sin cambiar no es un reenvío (P-23/105: aprobado el 29/10 y el
    # ERP quedó «Enviado 01/11»). Lo dice la carpeta env: un fichero del
    # documento enviado ese día o después. Si no se puede mirar, vale el ERP.
    if dev and puesta and puesta >= dev and estado_erp_ahora == "enviado" \
            and _reenviado_en_disco(e, dev) is not False:
        return None
    falta = []
    if dev and not (puesta and dev - timedelta(days=_FECHA_ANTES) <= puesta
                    <= dev + timedelta(days=_FECHA_DESPUES)):
        falta.append("fecha")
    validos = {_fold(x) for x in [e["estado"], *(e.get("estado_alt") or [])]}
    # Un resultado de devolución con la misma fecha es otra devolución de ese día
    # que la app no vio (CAL-0007 de Silleno: la AP por el portal y, ese mismo
    # día, Com. Menores por correo): lo apuntado en el ERP es lo bueno
    otra_del_dia = (dev and puesta == dev and estado_erp_ahora in _RESULTADOS)
    if estado_erp_ahora not in validos and not otra_del_dia:
        falta.append("estado")
    # El 1er envío se pone con la primera devolución (la de nuestra rev 0)
    if n == 0 and not erp["primer_envio"]:
        falta.append("primer_envio")
    if not falta:
        return None
    return {"falta": falta, "erp": erp, "motivo": "",
            "primer_envio": e.get("primer_envio") or envio_rev0(fila)}


def pendientes(erp: dict | None = "leer") -> dict:
    """Las devoluciones que el ERP aún no refleja.

    {ok, motivo, filas: [{clave, …entrada, falta, erp}]}, la más reciente
    primero. Sin ERP, ok=False y no se puede decir nada."""
    if erp == "leer":
        recuperar_archivado()
    reg = _cargar()
    vigentes = [(clave, reg["devueltos"][clave]) for clave in _ultimas(reg)]
    vigentes = [(c, e) for c, e in vigentes if not e.get("ignorada")]
    if erp == "leer":
        try:
            erp = leer_erp([e for _c, e in vigentes])
        except Exception as exc:  # noqa: BLE001 — el ERP puede caerse a media consulta
            logger.info("Registro ERP: no se pudo leer el ERP: %s", exc)
            erp = None
    if erp is None:
        return {"ok": False, "motivo": "No se llega al ERP: no se puede comparar.", "filas": [],
                "total": len(vigentes)}
    _guardar_envios(reg, vigentes, erp)
    filas = []
    for clave, e in vigentes:
        dif = comparar(_con_hermanas(reg, clave), erp.get(_clave_doc(e)))
        if dif is not None:
            filas.append({"clave": clave, **e, **dif})
    filas.sort(key=lambda f: (_a_fecha(f.get("fecha")) or date.min, f.get("pedido", "")), reverse=True)
    return {"ok": True, "motivo": "", "filas": filas, "total": len(vigentes)}


def _momento(valor) -> str:
    """Fecha y hora del correo, ISO y sin zona («2026-10-30T13:25:00»), o ''."""
    txt = str(valor or "").strip()
    try:
        return datetime.fromisoformat(txt.replace(" ", "T")[:19]).isoformat(timespec="seconds")
    except ValueError:
        d = _a_fecha(txt)
        return d.isoformat() if d else ""


def _ultimas(reg: dict) -> list[str]:
    """Las claves de la última devolución de cada documento (por fecha; el mismo
    día, por la hora del correo; luego por nuestra revisión): las anteriores ya
    no son trabajo."""
    ultimas: dict[str, tuple] = {}
    for clave, e in reg["devueltos"].items():
        k = _clave_doc(e)
        orden = (_a_fecha(e.get("fecha")) or date.min, e.get("recibido", ""),
                 int(e["nuestra"]) if str(e.get("nuestra")).isdigit() else -1, e.get("anotado", ""))
        if k not in ultimas or orden > ultimas[k][0]:
            ultimas[k] = (orden, clave)
    return [clave for _o, clave in ultimas.values()]


def _con_hermanas(reg: dict, clave: str) -> dict:
    """La devolución, con los estados de sus hermanas como alternativas: el
    mismo documento devuelto otra vez el mismo día con la misma revisión nuestra
    (Silleno, P-26/032: el plano volvió aprobado a las 07:57 y comentado a las
    13:25). Cualquiera de esos resultados es una forma correcta de apuntarlo."""
    e = reg["devueltos"][clave]
    otros = [x["estado"] for k, x in reg["devueltos"].items()
             if k != clave and _clave_doc(x) == _clave_doc(e) and x.get("nuestra") == e.get("nuestra")
             and x.get("fecha") == e.get("fecha") and x.get("estado") != e.get("estado")]
    if not otros:
        return e
    return {**e, "estado_alt": list(dict.fromkeys([*(e.get("estado_alt") or []), *otros]))}


def estado_por_codigo(erp: dict | None = "leer") -> dict | None:
    """Para la columna «ERP» de Devoluciones: {código del transmittal → {total, faltan}}.

    `total` son los documentos de esa devolución que la app archivó; `faltan`,
    los que el ERP aún no dice. Una devolución vieja de un documento que ya se
    ha vuelto a devolver no falta (la que cuenta es la nueva), ni una ocultada.
    None si no se llega al ERP."""
    if erp == "leer":
        recuperar_archivado()        # lo archivado antes del registro (una vez por transmittal)
    reg = _cargar()
    con_codigo = {c: e for c, e in reg["devueltos"].items() if e.get("codigo")}
    if not con_codigo:
        return {}
    ultimas = set(_ultimas(reg))
    if erp == "leer":
        try:
            erp = leer_erp(list(con_codigo.values()))
        except Exception as exc:  # noqa: BLE001
            logger.info("Registro ERP: no se pudo leer el ERP: %s", exc)
            erp = None
    if erp is None:
        return None
    out: dict[str, dict] = {}
    for clave, e in con_codigo.items():
        r = out.setdefault(e["codigo"], {"total": 0, "faltan": 0})
        r["total"] += 1
        if (clave in ultimas and not e.get("ignorada")
                and comparar(_con_hermanas(reg, clave), erp.get(_clave_doc(e))) is not None):
            r["faltan"] += 1
    return out


def _guardar_envios(reg: dict, entradas, erp: dict) -> int:
    """Se queda con la fecha del envío de la rev 0 de los que aún la tienen a la
    vista en el ERP: en cuanto se ponga la fecha de la devolución, se pierde."""
    nuevas = 0
    for _clave, e in entradas:
        if e.get("primer_envio"):
            continue
        fecha = envio_rev0(erp.get(_clave_doc(e)))
        if fecha:
            e["primer_envio"] = fecha
            nuevas += 1
    if nuevas:
        _guardar(reg)
    return nuevas


def capturar_envios() -> int:
    """`_guardar_envios` sobre todo el registro, leyendo el ERP. Nunca lanza.
    Se llama al apuntar devoluciones nuevas: es cuando el ERP aún dice «Enviado»."""
    try:
        reg = _cargar()
        entradas = [(c, e) for c, e in reg["devueltos"].items() if not e.get("primer_envio")]
        if not entradas:
            return 0
        erp = leer_erp([e for _c, e in entradas])
        return _guardar_envios(reg, entradas, erp) if erp else 0
    except Exception as exc:  # noqa: BLE001
        logger.info("Registro ERP: no se pudo mirar el 1er envío: %s", exc)
        return 0


def grupos(filas: list[dict]) -> list[dict]:
    """Las pendientes por (fecha, estado): lo que se pega de una vez en el ERP
    seleccionando esas filas. [{estado, fecha, filas}], los grupos grandes primero."""
    por: dict[tuple, list] = {}
    for f in filas:
        if "documento" in f["falta"]:
            continue
        por.setdefault((f["estado"], f["fecha"]), []).append(f)
    out = [{"estado": k[0], "fecha": k[1], "filas": v} for k, v in por.items()]
    return sorted(out, key=lambda g: (-len(g["filas"]), g["estado"]))


def exportar_excel(filas: list[dict], destino) -> str:
    """Excel con lo que hay que poner (una fila por documento): para tenerlo a
    mano o para una importación de actualizaciones en el ERP, si llega a haberla."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Actualizar ERP"
    # En el orden en que se meten: fecha, estado y (en la primera devolución) el
    # 1er envío. La revisión va solo para reconocer el documento, con un nombre
    # que no es una columna del ERP: no se toca al recibir.
    ws.append(["num_doc_eipsa", "num_doc_client", "num_order", "state_date", "state", "date_first_rev",
               "rev_nuestra (info)", "rev_cliente (info)", "estado_portal", "carpeta"])
    for f in filas:
        if "documento" in f["falta"]:
            continue
        primer = f.get("primer_envio", "") if "primer_envio" in f["falta"] else ""
        ws.append([f.get("doc_eipsa"), f.get("doc_cliente"), f.get("pedido"), f.get("fecha"),
                   f.get("estado"), primer or None, f.get("nuestra"), f.get("cliente"),
                   f.get("estado_portal"), f.get("carpeta")])
    for col, ancho in zip("ABCDEFGHIJ", (28, 34, 14, 12, 14, 14, 12, 12, 22, 60)):
        ws.column_dimensions[col].width = ancho
    wb.save(destino)
    return str(destino)
