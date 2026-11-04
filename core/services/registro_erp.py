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
que se apunta) y el 1er envío. De cada documento cuenta su última devolución.

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


def anotar(archive: dict, fecha_correo: str = "", portal: str = "", capturar: bool = True) -> int:
    """Apunta los documentos que `dev_folders` acaba de archivar
    (`archive["devueltos"]`). Devuelve cuántos son nuevos."""
    devueltos = (archive or {}).get("devueltos") or []
    if not devueltos:
        return 0
    reg = _cargar()
    fecha = _fecha_erp(fecha_correo) or date.today().strftime("%d/%m/%Y")
    nuevos = 0
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
            "carpeta": str(d.get("carpeta") or ""),
            "portal": portal,
            "anotado": datetime.now().isoformat(timespec="seconds"),
        }
        clave = f"{_clave_doc(entrada)}|{nuestra}|{entrada['estado']}"
        if clave in reg["devueltos"]:
            continue                 # la misma devolución, otra vez (rearchivo)
        reg["devueltos"][clave] = entrada
        nuevos += 1
    if nuevos:
        _guardar(reg)
        logger.info("Registro ERP: %d devolución(es) apuntada(s)", nuevos)
        # Ahora el ERP aún dice «Enviado»: es cuando se ve la fecha del 1er envío
        if capturar:
            capturar_envios()
    return nuevos


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
    falta = []
    dev, puesta = _a_fecha(e.get("fecha")), _a_fecha(erp["fecha"])
    if dev and not (puesta and dev - timedelta(days=_FECHA_ANTES) <= puesta
                    <= dev + timedelta(days=_FECHA_DESPUES)):
        falta.append("fecha")
    if _fold(erp["estado"]) != _fold(e["estado"]):
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
    reg = _cargar()
    ultimas: dict[str, tuple[str, dict]] = {}
    for clave, e in reg["devueltos"].items():
        k = _clave_doc(e)
        orden = (_a_fecha(e.get("fecha")) or date.min, int(e["nuestra"]) if str(e.get("nuestra")).isdigit() else -1,
                 e.get("anotado", ""))
        if k not in ultimas or orden > ultimas[k][0]:
            ultimas[k] = (orden, clave)
    vigentes = [(clave, reg["devueltos"][clave]) for _o, clave in ultimas.values()]
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
        dif = comparar(e, erp.get(_clave_doc(e)))
        if dif is not None:
            filas.append({"clave": clave, **e, **dif})
    filas.sort(key=lambda f: (_a_fecha(f.get("fecha")) or date.min, f.get("pedido", "")), reverse=True)
    return {"ok": True, "motivo": "", "filas": filas, "total": len(vigentes)}


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
