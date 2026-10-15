r"""En qué documento está un tag.

Se busca en tres sitios, porque ninguno está completo:

1. **El ERP.** Cada tag de caudal y temperatura puede apuntar a su documento de
   cálculo (`calc_num_doc_eipsa`) y a su plano (`dwg_num_doc_eipsa`). Es la
   respuesta exacta, pero solo está rellena en una parte: la mitad de los tags
   de 2024-25 y casi ninguno de 2026.
2. **El texto de los PDF enviados** (las carpetas `env …` del pedido). Los
   libros de cálculo de TR traen los tags escritos, con su página. Los PDF que
   son imagen no tienen texto que leer: eso pediría OCR.
3. **El nombre del fichero**: cuando cada tag se manda en su propio PDF
   («450-fe-006A.pdf»).

Si nada de eso lo encuentra, se dan al menos los cálculos y planos de su
pedido, avisando de que es por pedido y no por contenido.

**Los formatos.** El ERP escribe los tags de mil maneras —«1234-FE    -0598»,
«ABFE   0110», «361LG310614-A»— y quien busca, de otra. Se comparan solo las
letras y los números, así que «1234-FE-0567», «1234-FE    -0567» y
«1234FE0567» son el mismo tag. En el texto de los PDF, además, se exige que el
tag no siga pegado a otra letra o cifra: «450-FE-003» no es «450-FE-003A».

El texto de cada PDF se guarda en `state/indice_pdf` (fuera de git: es
contenido de documentos del cliente) y solo se vuelve a leer si el fichero
cambia, así que la segunda búsqueda en un pedido es inmediata.

Del ERP solo se lee: la sesión se abre en modo solo lectura (`erp_db`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path

from core.paths import state_dir

logger = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)   # avisos de PDF mal formados

INDICE_TTL = 600            # s que vale la lista de tags del ERP
MAX_PAGINAS = 1500          # un PDF más largo se lee hasta aquí
MAX_BYTES = 200 * 1024 * 1024
MIN_CLAVE = 5               # menos que esto no es un tag, es un trozo

# Tipos de documento donde van los tags, para cuando solo se sabe el pedido.
TIPOS_CON_TAGS = {"cálculo y plano", "planos", "cálculos", "datos técnicos"}

# tabla → (familia, columna del doc. de cálculo, columna del plano)
_TABLAS = {
    "tags_flow": ("Caudal", "calc_num_doc_eipsa", "dwg_num_doc_eipsa"),
    "tags_temp": ("Temperatura", "calc_num_doc_eipsa", "dwg_num_doc_eipsa"),
    "tags_level": ("Nivel", None, "dwg_num_doc_eipsa"),
    "tags_others": ("Otros", None, None),
}

_lock = threading.Lock()
_indice: tuple[float, dict[str, list[dict]]] | None = None


def clave_tag(texto) -> str:
    """Solo letras y números, en mayúsculas: lo que identifica un tag."""
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def parece_tag(texto) -> bool:
    """¿Merece la pena buscarlo como tag? Letras y números, y no demasiado corto."""
    k = clave_tag(texto)
    return len(k) >= MIN_CLAVE and any(c.isdigit() for c in k) and any(c.isalpha() for c in k)


def _patron(tag: str) -> re.Pattern | None:
    """El tag en un texto, con cualquier separador entre sus caracteres y sin
    otra letra o cifra pegada delante o detrás."""
    k = clave_tag(tag)
    if not k:
        return None
    sep = r"[\s\-_./]*"
    return re.compile(r"(?<![A-Z0-9])" + sep.join(re.escape(c) for c in k) + r"(?![A-Z0-9])")


# ── Los tags del ERP ─────────────────────────────────────────────────────────

def _leer_indice() -> dict[str, list[dict]]:
    from core.services import erp_db

    conn = erp_db._connect()                 # sesión de solo lectura
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = 30000;")
        indice: dict[str, list[dict]] = {}
        for tabla, (familia, c_calc, c_plano) in _TABLAS.items():
            cur.execute(
                f"SELECT tag, num_order, position, tag_state, "
                f"{c_calc or 'NULL'}, {c_plano or 'NULL'} FROM tags_data.{tabla} "
                "WHERE coalesce(tag_state, '') NOT IN ('SUPERADO', 'DELETED')")
            for tag, pedido, posicion, estado, calc, plano in cur.fetchall():
                k = clave_tag(tag)
                if not k:
                    continue
                indice.setdefault(k, []).append({
                    "tag": str(tag).strip(), "pedido": str(pedido or "").strip(),
                    "posicion": _texto(posicion), "estado": _texto(estado),
                    "familia": familia, "calc": _texto(calc), "plano": _texto(plano),
                })
        return indice
    finally:
        conn.close()


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return "" if s.lower() in ("none", "nan", "null") else s


def indice(forzar: bool = False) -> dict[str, list[dict]]:
    """{clave del tag → [filas del ERP]}. Lanza si el ERP no responde."""
    global _indice
    with _lock:
        if forzar or _indice is None or time.time() - _indice[0] > INDICE_TTL:
            _indice = (time.time(), _leer_indice())
        return _indice[1]


def buscar(texto: str, maximo: int = 12) -> tuple[list[dict], list[str]]:
    """(tags que son exactamente ese, otros que lo contienen) — los segundos,
    solo si no hay ninguno exacto, para proponerlos."""
    k = clave_tag(texto)
    if len(k) < MIN_CLAVE:
        return [], []
    idx = indice()
    if k in idx:
        return idx[k], []
    parecidos = sorted({filas[0]["tag"] for clave, filas in idx.items() if k in clave},
                       key=lambda t: (len(clave_tag(t)), t))
    return [], parecidos[:maximo]


# ── El texto de los PDF ──────────────────────────────────────────────────────

def _cache_dir() -> Path:
    return state_dir() / "indice_pdf"


def paginas_pdf(pdf: Path) -> list[str]:
    """Texto de cada página, en mayúsculas y con los espacios juntos.

    Se guarda y solo se vuelve a leer si el fichero cambia de tamaño o fecha.
    Un PDF que es imagen da páginas vacías.
    """
    try:
        st = pdf.stat()
    except OSError:
        return []
    firma = {"size": st.st_size, "mtime": int(st.st_mtime)}
    ficha = _cache_dir() / (hashlib.sha1(str(pdf).lower().encode("utf-8")).hexdigest() + ".json")
    try:
        guardado = json.loads(ficha.read_text(encoding="utf-8"))
        if guardado.get("size") == firma["size"] and guardado.get("mtime") == firma["mtime"]:
            return guardado.get("paginas") or []
    except (OSError, ValueError):
        pass

    paginas: list[str] = []
    fallo = False
    if st.st_size <= MAX_BYTES:
        try:
            from pypdf import PdfReader
            for i, pagina in enumerate(PdfReader(str(pdf)).pages):
                if i >= MAX_PAGINAS:
                    break
                try:
                    texto = pagina.extract_text() or ""
                except Exception:  # noqa: BLE001 — una página rota no tira el resto
                    texto = ""
                paginas.append(re.sub(r"\s+", " ", texto.upper()).strip())
        except Exception as exc:  # noqa: BLE001
            logger.info("Tags: no se pudo leer %s: %s", pdf.name, exc)
            fallo = True
    if fallo:
        # No se guarda: si fue la red (M: que se cae un momento), la próxima
        # vez se reintenta en vez de dar el PDF por vacío para siempre.
        return paginas
    try:
        _cache_dir().mkdir(parents=True, exist_ok=True)
        ficha.write_text(json.dumps({**firma, "ruta": str(pdf), "paginas": paginas}),
                         encoding="utf-8")
    except OSError:
        pass
    return paginas


def pdfs_enviados(pedido: str) -> list[Path]:
    """Los PDF de las carpetas `env …` de ese pedido (con su suministro)."""
    from core.services import dev_folders

    tecnico = dev_folders.tecnico_dir(pedido)
    if tecnico is None:
        return []
    fuera: set[Path] = set()
    for carpeta in dev_folders.scan_folders(tecnico):
        if carpeta["kind"] != "env":
            continue
        try:
            fuera.update(f for f in carpeta["path"].rglob("*.pdf") if f.is_file())
        except OSError:
            continue
    return sorted(fuera)


# ── De fichero a documento ───────────────────────────────────────────────────

def _codigo_en(nombre_clave: str, codigo: str) -> bool:
    """¿Ese código de documento va en el nombre? Sin cifra pegada detrás:
    «…01-002» no es «…01-0021»."""
    k = clave_tag(codigo)
    if len(k) < 8:
        return False
    i = nombre_clave.find(k)
    while i >= 0:
        fin = i + len(k)
        if fin >= len(nombre_clave) or not nombre_clave[fin].isdigit():
            return True
        i = nombre_clave.find(k, i + 1)
    return False


def documento_del_fichero(pdf: Path, docs: list[dict]) -> dict | None:
    """El documento cuyo código (EIPSA o del cliente) lleva el nombre del PDF."""
    nombre = clave_tag(pdf.stem)
    mejor, largo = None, 0
    for d in docs:
        for col in ("Nº Doc. EIPSA", "Nº Doc. Cliente"):
            codigo = str(d.get(col, "") or "")
            if _codigo_en(nombre, codigo) and len(clave_tag(codigo)) > largo:
                mejor, largo = d, len(clave_tag(codigo))
    return mejor


# ── La búsqueda ──────────────────────────────────────────────────────────────

def _por_codigo(docs: list[dict]) -> dict[str, dict]:
    return {clave_tag(d.get("Nº Doc. EIPSA")): d for d in docs if clave_tag(d.get("Nº Doc. EIPSA"))}




def _base(pedido: str) -> str:
    """El pedido sin suministro: «P-26/001-S01» → «P-26/001»."""
    return re.sub(r"-S\d{2}[A-Z]?$", "", str(pedido or "").strip(), flags=re.I)


_CARPETAS_CON_TAGS = re.compile(r"C[AÁ]L|PLA|DWG|DRAW|DATA", re.I)


def _prioridad(pdf: Path) -> tuple:
    """Primero lo que más probablemente trae el tag —las carpetas de cálculos y
    planos—, y dentro, lo pequeño: así los resultados salen enseguida y los
    certificados de cien páginas van al final."""
    try:
        tamaño = pdf.stat().st_size
    except OSError:
        tamaño = 0
    return (not _CARPETAS_CON_TAGS.search(str(pdf.parent)), tamaño)


def donde_esta(filas: list[dict], docs: list[dict], progreso=None) -> dict:
    """Los documentos donde aparece el tag.

    `filas`: las del ERP para ese tag (puede estar en varios pedidos).
    `docs`: los de la sección Documentos.
    `progreso(hechos, total, nombre, hallazgos)`: se llama tras cada PDF con lo
    encontrado hasta ese momento, para enseñarlo sin esperar al final.

    Devuelve {hallazgos, por_pedido, leidos, sin_texto}. Cada hallazgo es
    {doc, pedido, pruebas: [{que, fichero}]}: un documento con todo lo que dice
    que el tag está en él, o —si el PDF no lleva el código de ningún
    documento— el fichero solo, con `doc` None.
    """
    por_codigo = _por_codigo(docs)
    hallazgos: dict[tuple, dict] = {}

    def apuntar(pedido: str, que: str, doc: dict | None = None, fichero: Path | None = None):
        clave = ("doc", id(doc)) if doc is not None else ("fichero", str(fichero).lower())
        h = hallazgos.setdefault(clave, {"doc": doc, "pedido": pedido, "pruebas": []})
        prueba = {"que": que, "fichero": fichero}
        if prueba not in h["pruebas"]:
            h["pruebas"].append(prueba)

    # 1) El ERP
    for f in filas:
        for col, que in (("calc", "ERP · cálculo"), ("plano", "ERP · plano")):
            doc = por_codigo.get(clave_tag(f[col]))
            if doc is not None:
                apuntar(f["pedido"], que, doc)

    # 2) y 3) Los PDF enviados de cada pedido del tag
    patron = _patron(filas[0]["tag"]) if filas else None
    pedidos = list(dict.fromkeys(f["pedido"] for f in filas if f["pedido"]))
    # Para saber de qué documento es cada PDF: los de su suministro y, si no,
    # los de todo el pedido —desde la carpeta del S01 se manda a veces el
    # documento del S00—.
    candidatos = {p: ([d for d in docs if str(d.get("Nº Pedido", "")) == p],
                      [d for d in docs if _base(d.get("Nº Pedido", "")) == _base(p)])
                  for p in pedidos}
    pdfs = sorted(((p, pdf) for p in pedidos for pdf in pdfs_enviados(p)),
                  key=lambda x: _prioridad(x[1]))
    leidos = sin_texto = 0
    for n, (pedido, pdf) in enumerate(pdfs, 1):
        suyos, del_pedido = candidatos[pedido]
        doc = documento_del_fichero(pdf, suyos) or documento_del_fichero(pdf, del_pedido)
        if patron and patron.search(pdf.stem.upper()):
            apuntar(pedido, "nombre del fichero", doc, pdf)
        paginas = paginas_pdf(pdf)
        leidos += 1
        if not any(paginas):
            sin_texto += 1
        elif patron:
            en = [i for i, texto in enumerate(paginas, 1) if patron.search(texto)]
            if en:
                apuntar(pedido, _paginas_txt(en), doc, pdf)
        if progreso:
            progreso(n, len(pdfs), pdf.name, _ordenar(hallazgos))

    # Si nada lo encuentra: los cálculos y planos de su pedido
    por_pedido = not hallazgos
    if por_pedido:
        for pedido in pedidos:
            for d in docs:
                if (str(d.get("Nº Pedido", "")) == pedido
                        and str(d.get("Tipo Doc.", "")).strip().lower() in TIPOS_CON_TAGS):
                    apuntar(pedido, f"por pedido ({pedido})", d)
    return {"hallazgos": _ordenar(hallazgos), "por_pedido": por_pedido,
            "leidos": leidos, "sin_texto": sin_texto}


def _ordenar(hallazgos: dict) -> list[dict]:
    """Lo del ERP primero; después los documentos y, al final, los ficheros sueltos."""
    return sorted(hallazgos.values(), key=lambda h: (
        not any(p["que"].startswith("ERP") for p in h["pruebas"]), h["doc"] is None,
        str((h["doc"] or {}).get("Nº Doc. EIPSA", "")),
        str(h["pruebas"][0]["fichero"] or "")))


def _paginas_txt(paginas: list[int]) -> str:
    if len(paginas) > 8:
        return f"texto, págs. {', '.join(map(str, paginas[:8]))}… ({len(paginas)} páginas)"
    return ("texto, pág. " if len(paginas) == 1 else "texto, págs. ") + ", ".join(map(str, paginas))
