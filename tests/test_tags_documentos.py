# -*- coding: utf-8 -*-
"""Buscar un tag en la sección Documentos: formatos, texto de los PDF y de qué
documento es cada PDF. Sin ERP ni M:: todo se sustituye por datos inventados.

    .venv\\Scripts\\python.exe tests\\test_tags_documentos.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import tags_documentos as T
from gui.views import documentos_tags as G

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


# ── Los formatos ────────────────────────────────────────────────────────────
for forma in ("1234-FE-0567", "1234-FE    -0567", "1234 FE 0567", "1234fe0567", " 1234-fe-0567 "):
    ok(T.clave_tag(forma) == "1234FE0567", f"{forma!r} es el mismo tag: {T.clave_tag(forma)!r}")
for texto, espera in (("1234-FE-0567", True), ("ABFE   0110", True), ("FE-12", False),
                      ("26-027", False), ("planos", False), ("", False)):
    ok(T.parece_tag(texto) == espera, f"¿{texto!r} parece un tag? {T.parece_tag(texto)}")

patron = T._patron("1234-FE    -0567")
for texto, espera in (("TAG 1234-FE-0567 ORIFICE", True), ("1234-FE -0567", True),
                      ("(1234 FE 0567)", True), ("1234-FE-05673", False), ("11234-FE-0567", False)):
    ok(bool(patron.search(texto)) == espera, f"1234-FE-0567 en {texto!r}: {bool(patron.search(texto))}")
ok(not T._patron("450-FE-003").search("450-FE-003A"), "450-FE-003 no es 450-FE-003A")
ok(T._patron("450-FE-003").search("450-FE-003 / 450-FE-004"), "pero sí cuando va suelto")

# ── Buscar en los tags del ERP ──────────────────────────────────────────────


def fila(tag, pedido, posicion="1", calc="", plano=""):
    return {"tag": tag, "pedido": pedido, "posicion": posicion, "estado": "PURCHASED",
            "familia": "Caudal", "calc": calc, "plano": plano}


INDICE = {}
for f in (fila("1234-FE    -0567", "P-99/001-S01", "2", plano="99-001-S01-PLG-0005"),
          fila("1234-FE    -0567", "P-99/001-S01", "1"),
          fila("450-FE-003A", "P-99/002-S00"), fila("450-FE-004A", "P-99/002-S00")):
    INDICE.setdefault(T.clave_tag(f["tag"]), []).append(f)

indice_real = T.indice
T.indice = lambda forzar=False: INDICE
try:
    exactos, parecidos = T.buscar("1234-FE-0567")
    ok(len(exactos) == 2 and not parecidos, f"se encuentra escrito sin espacios: {exactos}")
    exactos, parecidos = T.buscar("450-fe-003")
    ok(not exactos and parecidos == ["450-FE-003A"], f"sin exacto, se propone el parecido: {parecidos}")
    ok(T.buscar("FE-0") == ([], []), "un trozo corto no busca nada")
finally:
    T.indice = indice_real

# ── De qué documento es cada PDF ────────────────────────────────────────────
DOCS = [
    {"Nº Pedido": "P-99/001-S00", "Nº Doc. EIPSA": "99-001-PLG-0005", "Nº Doc. Cliente": "AD-3000-I-50353",
     "Tipo Doc.": "Cálculo y plano", "Título": "BASE"},
    {"Nº Pedido": "P-99/001-S01", "Nº Doc. EIPSA": "99-001-S01-PLG-0005", "Nº Doc. Cliente": "AD-3000-I-50516",
     "Tipo Doc.": "Cálculo y plano", "Título": "S01"},
    {"Nº Pedido": "P-99/001-S01", "Nº Doc. EIPSA": "99-001-S01-MAN-0001", "Nº Doc. Cliente": "AD-3000-I-50517",
     "Tipo Doc.": "Manual", "Título": "MANUAL"},
    {"Nº Pedido": "P-99/002-S00", "Nº Doc. EIPSA": "99-002-CAL-0001", "Nº Doc. Cliente": "V-CLI-002",
     "Tipo Doc.": "Cálculos", "Título": "CALC"},
]
ok(T.documento_del_fichero(Path("AD-3000-I-50516 PLA.pdf"), DOCS) is DOCS[1], "por el código del cliente")
ok(T.documento_del_fichero(Path("01 99-002-CAL-0001-T-00.pdf"), DOCS) is DOCS[3],
   "por el código EIPSA, aunque lleve un número delante")
ok(T.documento_del_fichero(Path("AD-3000-I-503531.pdf"), DOCS) is None,
   "«…50353» no es «…503531»: sin cifra pegada detrás")
ok(T.documento_del_fichero(Path("Portadas.pdf"), DOCS) is None, "y un PDF sin código no es de ninguno")

# ── Dónde está ──────────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp())
reales = T.pdfs_enviados, T.paginas_pdf
try:
    carpeta = tmp / "P-99-001-S01" / "2-Tecnico" / "env cál-pla" / "rev 1"
    carpeta.mkdir(parents=True)
    PDFS = {
        "AD-3000-I-50516 PLA.pdf": ["PORTADA", "TAG 1234-FE -0567 ORIFICE PLATE", "NADA", "1234-FE-0567"],
        "AD-3000-I-50353.pdf": ["1234-FE-0567"],          # el del S00, enviado desde el S01
        "1234-FE-0567.pdf": [""],                          # suelto, y es imagen
        "INDICE.pdf": ["1234-FE-0566 1234-FE-05673"],      # otros tags: no cuenta
    }
    for nombre in PDFS:
        (carpeta / nombre).write_bytes(b"%PDF")
    T.pdfs_enviados = lambda pedido: sorted(carpeta.iterdir()) if pedido == "P-99/001-S01" else []
    T.paginas_pdf = lambda pdf: PDFS[pdf.name]

    filas = INDICE[T.clave_tag("1234-FE-0567")]
    avisos = []
    res = T.donde_esta(filas, DOCS, progreso=lambda n, total, nombre, h: avisos.append((n, total)))
    hallazgos = res["hallazgos"]
    ok(avisos and avisos[-1] == (4, 4), f"avisa del progreso PDF a PDF: {avisos}")
    ok(res["leidos"] == 4 and res["sin_texto"] == 1, f"4 leídos, 1 imagen: {res}")
    ok(not res["por_pedido"], "lo encuentra por contenido")

    primero = hallazgos[0]
    ok(primero["doc"] is DOCS[1], f"lo del ERP va primero: {primero['doc']}")
    pruebas = [p["que"] for p in primero["pruebas"]]
    ok(pruebas == ["ERP · plano", "texto, págs. 2, 4"], f"con el ERP y las páginas: {pruebas}")
    ok(primero["pruebas"][1]["fichero"].name == "AD-3000-I-50516 PLA.pdf", "y el fichero de esas páginas")

    del_s00 = [h for h in hallazgos if h["doc"] is DOCS[0]]
    ok(del_s00 and del_s00[0]["pruebas"][0]["que"] == "texto, pág. 1",
       f"el PDF del S00 enviado desde el S01 es de su documento del S00: {del_s00}")
    sueltos = [h for h in hallazgos if h["doc"] is None]
    ok([h["pruebas"][0]["que"] for h in sueltos] == ["nombre del fichero"],
       f"el PDF suelto del tag sale por su nombre, aunque sea imagen: {sueltos}")
    ok(not any(h["pruebas"][0]["fichero"] and h["pruebas"][0]["fichero"].name == "INDICE.pdf"
               for h in hallazgos), "y el índice con otros tags parecidos no cuenta")

    # Si no aparece en ningún sitio: los cálculos y planos de su pedido
    T.paginas_pdf = lambda pdf: [""]
    T.pdfs_enviados = lambda pedido: []
    res = T.donde_esta([fila("9999-XX-0001", "P-99/001-S01")], DOCS)
    ok(res["por_pedido"] and [h["doc"] for h in res["hallazgos"]] == [DOCS[1]],
       f"sin rastro: el cálculo y plano de su pedido, no el manual: {res['hallazgos']}")
    ok(res["hallazgos"][0]["pruebas"][0]["que"] == "por pedido (P-99/001-S01)", "y se dice por qué")
finally:
    T.pdfs_enviados, T.paginas_pdf = reales

# ── La caché del texto ──────────────────────────────────────────────────────
cache_real = T._cache_dir
try:
    T._cache_dir = lambda: tmp / "indice_pdf"
    roto = tmp / "roto.pdf"
    roto.write_bytes(b"esto no es un PDF")
    ok(T.paginas_pdf(roto) == [], "un PDF que no se puede leer da páginas vacías, sin reventar")
    ok(not list((tmp / "indice_pdf").glob("*.json")),
       "y no se guarda: si fue la red, la próxima vez se reintenta")
    # Con la misma firma se usa lo guardado sin volver a leer el PDF
    st = roto.stat()
    ficha = (tmp / "indice_pdf") / (T.hashlib.sha1(str(roto).lower().encode("utf-8")).hexdigest() + ".json")
    ficha.parent.mkdir(parents=True, exist_ok=True)
    ficha.write_text(json.dumps({"size": st.st_size, "mtime": int(st.st_mtime),
                                 "paginas": ["DE LA CACHE"]}), encoding="utf-8")
    ok(T.paginas_pdf(roto) == ["DE LA CACHE"], "la segunda vez sale de la caché")
    roto.write_bytes(b"ahora es otro fichero, mas largo")
    ok(T.paginas_pdf(roto) == [], "y si el fichero cambia, se vuelve a leer")
finally:
    T._cache_dir = cache_real
    shutil.rmtree(tmp, ignore_errors=True)

# ── Lo que enseña la ficha ──────────────────────────────────────────────────
ok(G.tag_legible("1234-FE    -0567") == "1234-FE-0567", G.tag_legible("1234-FE    -0567"))
ok(G.tag_legible("ABFE   0110") == "ABFE 0110", G.tag_legible("ABFE   0110"))
ok(G.ruta_corta(Path(r"M:\x\P-99\2-Tecnico\env cál\rev 1\a.pdf")) == r"env cál\rev 1\a.pdf",
   "la ruta, desde 2-Tecnico")
resumen = G._resumen_erp([fila("T-1", "P-99/001-S01", "10"), fila("T-1", "P-99/001-S01", "2"),
                          fila("T-1", "", "1")])
ok(resumen == "P-99/001-S01 · pos. 2, 10 · Caudal · PURCHASED",
   f"pedido, posiciones en orden y sin la fila de oferta: {resumen!r}")

print("FALLOS:", fallos)
