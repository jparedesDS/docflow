"""Lo que el cliente ha devuelto y el ERP todavía no dice.

Cada devolución que la app archiva en `dev. <Tipo>\\rev <nuestra>-<cliente> AP|COM|com|REJ`
se apunta aquí con lo que habría que poner en el ERP:

  · **Estado**: el de la resolución, con el nombre del ERP — Aprobado,
    Com. Menores, Com. Mayores, Comentado, Rechazado; «Informativo» es
    «Información» y un VOID se propone «Eliminado», a revisar.
  · **Nº Revisión**: la NUESTRA, la de la carpeta (desde el 0 y sumando). La
    del cliente (A, 0, 1, B… según cada uno) no se compara con nada: solo se
    enseña, para reconocer el documento.
  · **Fecha**: la del correo de la devolución, «dd/mm/aaaa» como la guarda el ERP.

Luego se compara con el ERP (solo lectura) y queda lo que no cuadra. Una línea
sale sola cuando el ERP ya tiene ese estado y esa revisión (con la fecha de la
devolución o de pocos días después: es el día que se apunta), o cuando el ERP
ya va por una revisión nuestra posterior (se volvió a enviar). De cada documento
cuenta solo su última devolución.

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


def anotar(archive: dict, fecha_correo: str = "", portal: str = "") -> int:
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
    return nuevos


def ignorar(clave: str) -> None:
    """Que esa devolución deje de salir (p. ej. se decidió no registrarla)."""
    reg = _cargar()
    if clave in reg["devueltos"]:
        reg["devueltos"][clave]["ignorada"] = date.today().isoformat()
        _guardar(reg)


# ── Contra el ERP ─────────────────────────────────────────────────────────────

_SQL = """
    SELECT num_doc_eipsa, num_doc_client, num_order, state, revision, state_date
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


def comparar(e: dict, fila: dict | None) -> dict | None:
    """Lo que falta en el ERP para esa devolución, o None si ya cuadra.

    {falta: [campos], erp: {estado, revision, fecha}, motivo}."""
    if fila is None:
        return {"falta": ["documento"], "erp": {}, "motivo": "no está en el ERP"}
    erp = {"estado": str(fila.get("state") or "").strip(),
           "revision": fila.get("revision"),
           "fecha": str(fila.get("state_date") or "").strip()}
    nuestra = e.get("nuestra", "")
    n = int(nuestra) if str(nuestra).isdigit() else None
    try:
        rev_erp = int(erp["revision"]) if erp["revision"] not in (None, "") else None
    except (TypeError, ValueError):
        rev_erp = None
    # El ERP ya va por una revisión nuestra posterior: esto es historia
    if n is not None and rev_erp is not None and rev_erp > n:
        return None
    falta = []
    if _fold(erp["estado"]) != _fold(e["estado"]):
        falta.append("estado")
    if n is not None and rev_erp != n:
        falta.append("revision")
    dev, puesta = _a_fecha(e.get("fecha")), _a_fecha(erp["fecha"])
    if dev and not (puesta and dev - timedelta(days=_FECHA_ANTES) <= puesta
                    <= dev + timedelta(days=_FECHA_DESPUES)):
        falta.append("fecha")
    if not falta:
        return None
    return {"falta": falta, "erp": erp, "motivo": ""}


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
    filas = []
    for clave, e in vigentes:
        dif = comparar(e, erp.get(_clave_doc(e)))
        if dif is not None:
            filas.append({"clave": clave, **e, **dif})
    filas.sort(key=lambda f: (_a_fecha(f.get("fecha")) or date.min, f.get("pedido", "")), reverse=True)
    return {"ok": True, "motivo": "", "filas": filas, "total": len(vigentes)}


def grupos(filas: list[dict]) -> list[dict]:
    """Las pendientes por (estado, fecha): lo que se pega de una vez en el ERP
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
    ws.append(["num_doc_eipsa", "num_doc_client", "num_order", "state", "state_date", "revision",
               "rev_cliente", "estado_portal", "carpeta"])
    for f in filas:
        if "documento" in f["falta"]:
            continue
        ws.append([f.get("doc_eipsa"), f.get("doc_cliente"), f.get("pedido"), f.get("estado"),
                   f.get("fecha"), int(f["nuestra"]) if str(f.get("nuestra")).isdigit() else None,
                   f.get("cliente"), f.get("estado_portal"), f.get("carpeta")])
    for col, ancho in zip("ABCDEFGHI", (28, 34, 14, 14, 12, 9, 11, 22, 60)):
        ws.column_dimensions[col].width = ancho
    wb.save(destino)
    return str(destino)
