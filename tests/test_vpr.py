# -*- coding: utf-8 -*-
"""El informe de avance (VPR): lo que se mide y cómo se escribe en el Word.

    docflow_env\\Scripts\\python.exe tests\\test_vpr.py
"""
import shutil
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import formulario_docx as F
from core.services import vpr

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg)


# ── Cómo se agrupan los equipos ─────────────────────────────────────────────
def tag(**kw):
    base = {"Familia": "Caudal", "Tipo": "F+P", "Tamaño": '6"', "Mat. Brida": "ASTM A105",
            "Plano Dim.": "26-059-S00-105", "Estado Fab.": "", "Fecha Verif. Dim.": "",
            "Fecha Verif. OF": "", "Fecha PH1": ""}
    base.update(kw)
    return base


ok(vpr._grupo(tag()) == "Placa+bridas A105", vpr._grupo(tag()))
ok(vpr._grupo(tag(**{"Mat. Brida": "ASTM A182 F5"})) == "Placa+bridas F5",
   "el acero aleado va aparte: es el que manda la fecha")
ok(vpr._grupo(tag(Tipo="M.RUN", Tamaño='1"')) == 'Meter run 1"', "el meter run, en su línea")
ok(vpr._grupo(tag(Familia="Temperatura", Tipo="TW+TE", Tamaño='3/4"')) == 'Vaina+termopar 3/4"',
   "las de temperatura, por tamaño")

# Un grupo de caudal: 2 de 4 fabricados y verificados, ninguno con hidrostática
caudal = [tag(**{"Estado Fab.": "FABRICADO", "Fecha Verif. Dim.": "03/09/2026"}),
          tag(**{"Estado Fab.": "FABRICADO", "Fecha Verif. Dim.": "04/09/2026"}),
          tag(), tag()]
a = vpr._avance_grupo(caudal)
ok(a["nombre"] == "Placa+bridas A105 (4)", f"el nombre lleva cuántos son: {a['nombre']}")
ok(a["ingenieria"] == 100, "con plano dimensional, la ingeniería está emitida")
ok(a["fabricacion"] == 50, f"2 de 4 fabricados: {a['fabricacion']}")
ok(a["inspeccion"] == 25, f"verificados 2 de 4 y sin hidrostática: {a['inspeccion']}")

# Y uno de temperatura, que se mide con la verificación de fabricación
vainas = [tag(Familia="Temperatura", Tipo="TW+TE", Tamaño='3/4"',
              **{"Fecha Verif. OF": "07/09/2026", "Fecha PH1": "17/09/2026"})]
ok(vpr._avance_grupo(vainas)["inspeccion"] == 100, "verificada y probada: inspección al 100 %")

# ── El material de un subpedido, en una línea ───────────────────────────────
crudo = "ADD COURIER CHARGES · Barra Redonda 130 AISI-316/316L · Portes"
ok(vpr._material_resumen(crudo, 36) == "Barra Redonda 130 AISI-316/316L (36 uds)",
   f"fuera los portes: {vpr._material_resumen(crudo, 36)}")
largo = vpr._material_resumen(" · ".join([f"Brida {n}\"300 WNRF Sch-40 A-182 F5" for n in range(8)]), 14)
ok(largo.endswith("(14 uds)") and "…" in largo and len(largo) < 90, f"recortado: {largo}")
ok(vpr._material_resumen("", 5) == "5 uds", "sin descripción, al menos las unidades")

# ── El plan: lo que tocaría a día de hoy ────────────────────────────────────
ok(vpr._planificado("01-09-2026", "30-10-2026", date(2026, 9, 30)) == 49,
   f"a mitad de camino: {vpr._planificado('01-09-2026', '30-10-2026', date(2026, 9, 30))}")
ok(vpr._planificado("01-09-2026", "30-10-2026", date(2026, 11, 5)) == 100, "pasada la fecha, 100")
ok(vpr._planificado("", "30-10-2026", date(2026, 9, 30)) == 100, "sin fechas no se inventa nada")

# ── La propuesta no promete nada después de la entrega del pedido ───────────
datos = {
    "pedido": "P-26/022",
    "cabecera": {"pedido": "P-26/022-S00", "po": "C.181752/01", "fecha_pedido": "17-07-2026",
                 "entrega": "30-10-2026", "items": 121, "taller": 40, "montaje": 25,
                 "entregas": 45, "obs_taller": "", "obs_envios": "TRANSPORTES X",
                 "envio_parcial": "08-09-2026"},
    "equipos": 4,
    "grupos": [vpr._avance_grupo(caudal)],
    "documentos": {"total": 9, "emitidos": 8, "aprobados": 7, "pendientes": [], "docs": []},
    "subpedidos": [{"numero": "2260149", "fecha": "28-07-2026", "proveedor": "Officine",
                    "material": "Bridas F5 (14 uds)", "unidades": 14, "pendientes": 14,
                    "contractual": "30-10-2026", "estado": "PENDIENTE — 14 uds"}],
    "fabricacion": {"fabricados": 2, "verificados": 2, "ensayados": 0, "entregados": 0},
    "avance": {"ingenieria": 100, "documentacion": 78, "subpedidos": 100, "acopio": 0,
               "fabricacion": 50, "inspeccion": 25, "transporte": 50},
}
p = vpr.propuesta(datos, numero="VPR-001", hoy=date(2026, 9, 21))
ok(set(p["previstas"].values()) == {"30-10-2026"},
   f"todas las previsiones, a la fecha del pedido: {p['previstas']}")
ok(all(v["fin"] == "30-10-2026" for k, v in p["resumen"].items() if k != "subpedidos"),
   "y ninguna área termina después")
ok(p["resumen"]["fabricacion"]["real"] == 50, "el % real es el medido, no se toca")
ok("2260149" in " ".join(p["textos"]["subpedidos"]), "el subpedido pendiente sale en el texto")
ok("40 %" in " ".join(p["textos"]["fabricacion"]), "y el avance del taller, tal como lo dice el ERP")

# ── Escribir en el Word sin estropearlo ─────────────────────────────────────
HOJA = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:tbl><w:tr><w:trPr><w:trHeight w:hRule="exact" w:val="300"/></w:trPr>
<w:tc><w:tcPr><w:tcW w:w="1000" w:type="dxa"/></w:tcPr><w:p><w:r><w:rPr><w:b/></w:rPr>
<w:t>VENDOR PROGRESS REPORT</w:t></w:r></w:p></w:tc>
<w:tc><w:tcPr><w:tcW w:w="1000" w:type="dxa"/></w:tcPr><w:p/><w:p><w:r><w:t>sobra</w:t></w:r></w:p>
</w:tc></w:tr></w:tbl>
<w:p><w:r><w:pict><w:txbxContent><w:p><w:r><w:rPr><w:i/></w:rPr><w:t>escribe aquí</w:t></w:r>
</w:p></w:txbxContent></w:pict></w:r></w:p>
<w:p><w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:drawing/></w:r></w:p>
</w:body></w:document>"""

tmp = Path(tempfile.mkdtemp())
try:
    plantilla = tmp / "form.docx"
    with zipfile.ZipFile(plantilla, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", HOJA)
        z.writestr("word/media/logo.png", b"\x89PNG-de-mentira")

    doc = F.Formulario(plantilla)
    doc.altura_flexible(0, [0])
    doc.escribir_celda(0, 0, 1, ["primera", "segunda"])
    doc.escribir_caja(1, "comentario nuevo")
    doc.escribir_tras_dibujo(2, "debajo del recuadro")
    destino = doc.guardar(tmp / "relleno.docx")

    with zipfile.ZipFile(destino) as z:
        salida = z.read("word/document.xml").decode("utf-8")
        ok(z.read("word/media/logo.png") == b"\x89PNG-de-mentira",
           "el logo y todo lo demás se copia byte a byte")
    ok("<w:br/>" in salida.replace(" />", "/>"), "las dos líneas van con salto dentro de la celda")
    ok("primera" in salida and "segunda" in salida and "sobra" not in salida,
       "se escribe en el primer párrafo y se quitan los demás")
    ok('w:hRule="atLeast"' in salida, "la fila ya puede crecer")
    ok('<w:tcW w:w="1000"' in salida.replace(" w:type", " w:type"), "la casilla conserva su formato")
    ok("comentario nuevo" in salida and "escribe aquí" not in salida, "el cuadro de texto, escrito")
    ok("<w:txbxContent>" in salida, "y el cuadro sigue siendo un cuadro")
    ok("<w:drawing" in salida and "debajo del recuadro" in salida,
       "el recuadro dibujado se conserva y el texto va detrás")
    ok("ns0:" not in salida, "sin prefijos raros: Word lo abre")

    # Una plantilla que no es un VPR no se rellena por error
    ok(vpr.formato_de(plantilla) is not None, "esta sí se reconoce (lleva las señas)")
    otra = tmp / "otra.docx"
    with zipfile.ZipFile(otra, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", HOJA.replace("VENDOR PROGRESS REPORT", "OTRA COSA"))
    ok(vpr.formato_de(otra) is None, "y una cualquiera, no")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ok(vpr.fecha_valida("30-10-2026") and not vpr.fecha_valida("30/10/2026"),
   "las fechas van como las quiere el formulario")

print("FALLOS:", fallos)
