"""Plazos en Excel, para que se entienda a la primera.

Cuatro hojas, letra grande y solo lo importante:
  · Resumen — lo que tarda normalmente cada paso, en días.
  · Qué hacer primero — los pedidos que esperan planos o material, con su
    prioridad en palabras y en color.
  · Pedidos — uno por línea: las fechas clave y los días.
  · Personas — lo que tarda normalmente cada uno en su paso.

Nada de medianas, cuartiles, horquillas, horas ni de dónde sale cada fecha:
eso se queda en la sección Plazos de la app. Lo pinta a partir de
`seguimiento.cargar()`; no calcula nada.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

LETRA = 14
AZUL = "1F3864"
ROJO, AMBAR, VERDE, GRIS = "F4CCCC", "FCE5CD", "D9EAD3", "E7E6E6"
_LINEA = Side(style="thin", color="BFBFBF")
_BORDE = Border(left=_LINEA, right=_LINEA, top=_LINEA, bottom=_LINEA)
_FORMATO_FECHA = "dd/mm/yyyy"

FALTA = {"planos": "Planos (el material ya está)", "ambos": "Planos y material",
         "material": "Material (planos ya en fábrica)"}

# (paso, «qué hace»). El de activar no va: siempre ~0 días y confunde.
PERSONAS = [("comercial", "Contestar ofertas"), ("activar", "Activar pedidos"),
            ("tec_oc", "Pasar la orden de compra a Compras"), ("compras", "Pedir el material al proveedor"),
            ("tecnico", "Mandar planos a fábrica")]

# (tramo, texto, nota, sangría). Tramo None: título con una línea en blanco
# antes; tramo "": subtítulo («Material:», «Planos:»).
RESUMEN = [
    ("comercial", "Contestar una oferta", "", 0),
    ("cliente", "El cliente tarda en hacer el pedido", "no depende de nosotros", 0),
    ("activar", "Activar el pedido, desde que llega la PO", "", 0),
    (None, "Desde que se activa el pedido (material y planos, a la vez):", "", 0),
    ("", "Material:", "", 1),
    ("tec_oc", "Técnico: pasa la orden de compra a Compras", "", 2),
    ("compras_pedir", "Compras: pide el material al proveedor", "", 2),
    ("proveedor", "Proveedor: entrega el material", "", 2),
    ("", "Planos:", "", 1),
    ("tecnico", "Técnico: manda los planos a fábrica", "", 2),
    ("listo:con_compras", "→ La fábrica puede empezar, si hay que comprar material", "", 1),
    ("listo:sin_compras", "→ La fábrica puede empezar, si no hace falta comprar", "", 1),
    ("total", "De la oferta a la fábrica, en total", "", 0),
]

RETRASO = {"material": "Material", "planos": "Planos", "los dos": "Los dos"}

# Qué falta de verdad cuando una fuente no responde (los avisos de `seguimiento.cargar`)
AVISOS = {
    "Sin ERP": "No se pudo leer el ERP: faltan pedidos y fechas; las cifras no valen esta vez.",
    "Sin acceso a M:": "No se pudo entrar en la unidad M: faltan las fechas de los planos a fábrica.",
    "Sin correo": "No se pudo leer el correo de Ofertas: las fechas de las ofertas son las del ERP "
                  "(el día, sin la hora). El resto de cifras vale.",
}


def frase_retraso(cuello: dict) -> str:
    """«Lo que más retrasa: el material (en 8 de cada 10 pedidos con compras)»."""
    total = cuello.get("total") or 0
    if not total:
        return ""
    m, p = cuello.get("material", 0), cuello.get("planos", 0)
    if m == p:
        return "Lo que más retrasa: el material y los planos, a partes iguales"
    que, n = ("el material", m) if m > p else ("los planos", p)
    return f"Lo que más retrasa: {que} (en {round(10 * n / total)} de cada 10 pedidos con compras)"


# ── Ayudas ────────────────────────────────────────────────────────────────────

def _dia(v) -> date | None:
    if isinstance(v, datetime):
        return (v.astimezone() if v.tzinfo else v).date()
    return v if isinstance(v, date) else None


def _dias(n) -> str:
    if n is None:
        return "—"
    n = int(round(n))
    return "1 día" if n == 1 else f"{n} días"


def _entero(n):
    """Días como número entero; «—» si no hay o sale negativo."""
    if n is None or n < 0:
        return "—"
    return int(round(n))


def quedan(entrega, hoy: date) -> str:
    """«84 días», «1 día», «vencida hace 12 días» o «—»."""
    entrega = _dia(entrega)
    if not entrega:
        return "—"
    n = (entrega - hoy).days
    if n < 0:
        return "vencida hace 1 día" if n == -1 else f"vencida hace {-n} días"
    return _dias(n)


def prioridad(item: dict, hoy: date) -> tuple[str, str]:
    """(texto, color de fondo) de un pedido de la cola."""
    if item.get("falta") == "material":
        return "ESPERA MATERIAL", GRIS
    margen = item.get("margen")
    if margen:
        peor = margen[0]
        if peor < 0:
            return "URGENTE", ROJO
        return ("JUSTO", AMBAR) if peor < 15 else ("CON TIEMPO", VERDE)
    entrega = _dia(item["hitos"]["entrega"]["fecha"])
    if not entrega:
        return "SIN FECHA", GRIS
    n = (entrega - hoy).days
    if n < 30:
        return "URGENTE", ROJO
    return ("JUSTO", AMBAR) if n < 60 else ("CON TIEMPO", VERDE)


def nombre(persona: str) -> str:
    """«luis-x» → «Luis X»; «ana.x» → «Ana X»; las iniciales («AC») y los nombres ya escritos, igual."""
    p = (persona or "").strip()
    if not p or (p.isupper() and len(p) <= 4) or (" " in p and p != p.lower()):
        return p
    palabras = []
    for w in re.split(r"[\s.\-_]+", p):
        if w and w.capitalize() not in palabras:
            palabras.append(w.capitalize())
    return " ".join(palabras)


def _celda_fecha(v):
    """Una fecha como fecha de Excel, sin hora (y sin zona, que openpyxl no admite)."""
    d = _dia(v)
    return datetime(d.year, d.month, d.day) if d else v


# ── Hojas ─────────────────────────────────────────────────────────────────────

def _imprimir(ws) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_options.horizontalCentered = True


def _hoja(wb, titulo: str, frase: str, cabecera: list[str], filas: list[list], anchos: list[int],
          colores: list[str | None] | None = None):
    """Título, frase, cabecera y filas, con letra grande y lista para imprimir."""
    ws = wb.create_sheet(titulo)
    ws.cell(1, 1, titulo).font = Font(size=20, bold=True, color=AZUL)
    ws.cell(2, 1, frase).font = Font(size=LETRA, italic=True, color="595959")
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 24
    for j, texto in enumerate(cabecera, start=1):
        c = ws.cell(3, j, texto)
        c.font = Font(size=LETRA, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _BORDE
    ws.row_dimensions[3].height = 42
    for i, fila in enumerate(filas, start=4):
        relleno = (colores[i - 4] if colores else None) or ("F2F2F2" if i % 2 else None)
        for j, v in enumerate(fila, start=1):
            v = _celda_fecha(v) if isinstance(v, (datetime, date)) else v
            c = ws.cell(i, j, v)
            c.font = Font(size=LETRA, bold=(colores is not None and j == 2))
            c.border = _BORDE
            izquierda = isinstance(v, str) and v != "—" and not v[:1].isdigit()
            c.alignment = Alignment(vertical="center", horizontal="left" if izquierda else "center")
            if isinstance(v, datetime):
                c.number_format = _FORMATO_FECHA
            if relleno:
                c.fill = PatternFill("solid", fgColor=relleno)
        ws.row_dimensions[i].height = 24
    for j, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(j)].width = ancho
    ws.freeze_panes = "A4"
    ws.print_title_rows = "3:3"
    _imprimir(ws)
    return ws


def _resumen(wb, datos: dict) -> None:
    ws = wb.create_sheet("Resumen")
    ws.column_dimensions["A"].width = 84
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 30
    generado = datos.get("generado") or datetime.now()
    años = " y ".join(str(a) for a in datos.get("años") or ())
    ws.cell(1, 1, "Plazos: de la oferta a la fábrica").font = Font(size=22, bold=True, color=AZUL)
    ws.cell(2, 1, f"Pedidos de {años} · actualizado el {generado:%d/%m/%Y}").font = \
        Font(size=LETRA, italic=True, color="595959")
    ws.row_dimensions[1].height = 36
    fila = 3
    for aviso in datos.get("avisos") or []:
        fila += 1
        texto = AVISOS.get(aviso, f"{aviso}: puede faltar algún dato.")
        ws.cell(fila, 1, f"⚠ {texto}").font = Font(size=LETRA, bold=True, color="C00000")
    fila += 2
    ws.cell(fila, 1, "Lo normal:").font = Font(size=16, bold=True)
    tramos = datos["resumen"]["tramos"]
    for tramo, texto, nota, sangria in RESUMEN:
        fila += 1
        ws.row_dimensions[fila].height = 26
        if tramo is None:
            fila += 1
            ws.row_dimensions[fila].height = 26
            ws.cell(fila, 1, texto).font = Font(size=16, italic=True)
            continue
        if tramo == "":
            c = ws.cell(fila, 1, texto)
            c.font = Font(size=16, bold=True)
            c.alignment = Alignment(indent=3 * sangria)
            continue
        listo = tramo.startswith("listo:")
        stats = datos["resumen"]["listo"][tramo.split(":")[1]] if listo else tramos[tramo]
        c = ws.cell(fila, 1, texto)
        c.font = Font(size=16, bold=listo)
        c.alignment = Alignment(indent=3 * sangria)
        c = ws.cell(fila, 2, _dias(stats["mediana"]))
        c.font = Font(size=16, bold=True, color=AZUL)
        c.alignment = Alignment(horizontal="right")
        if nota:
            ws.cell(fila, 3, f"({nota})").font = Font(size=LETRA, italic=True, color="7F7F7F")
        if tramo == "listo:sin_compras" and frase_retraso(datos["resumen"].get("cuello") or {}):
            fila += 1
            c = ws.cell(fila, 1, frase_retraso(datos["resumen"]["cuello"]))
            c.font = Font(size=LETRA, italic=True, color="7F7F7F")
            c.alignment = Alignment(indent=6)
            fila += 1
    cola = datos["cola"]
    hoy = generado.date()
    esperan = sum(1 for c in cola if c["falta"] == "planos")
    urgentes = sum(1 for c in cola if prioridad(c, hoy)[0] == "URGENTE")
    fila += 2
    ws.cell(fila, 1, "Ahora mismo:").font = Font(size=16, bold=True)
    for texto in (f"{esperan} pedidos tienen el material y esperan los planos.",
                  f"{urgentes} pedidos son urgentes.",
                  "Ver la hoja «Qué hacer primero»."):
        fila += 1
        ws.cell(fila, 1, texto).font = Font(size=16)
        ws.row_dimensions[fila].height = 26
    _imprimir(ws)


def _que_hacer(wb, datos: dict) -> None:
    hoy = (datos.get("generado") or datetime.now()).date()
    filas, colores = [], []
    for i, c in enumerate(datos["cola"], start=1):
        texto, color = prioridad(c, hoy)
        entrega = c["hitos"]["entrega"]["fecha"]
        filas.append([i, texto, c["pedido"], c["cliente"] or "—", FALTA.get(c["falta"], c["falta"]),
                      entrega or "—", quedan(entrega, hoy)])
        colores.append(color)
    if not filas:
        filas, colores = [["", "No hay pedidos esperando planos ni material.", "", "", "", "", ""]], [None]
    _hoja(wb, "Qué hacer primero",
          "Los pedidos que esperan planos o material. Arriba, los que hay que sacar antes.",
          ["#", "Prioridad", "Pedido", "Cliente", "Qué falta", "Entrega", "Quedan"],
          filas, [6, 24, 18, 30, 36, 15, 26], colores)


def _pedidos(wb, datos: dict) -> None:
    filas = []
    orden = sorted(datos["filas"], key=lambda f: (_dia(f["hitos"]["pedido"]["fecha"]) or date.min, f["pedido"]),
                   reverse=True)
    for f in orden:
        h, t = f["hitos"], f["tramos"]
        if h["material"]["fecha"]:
            material = h["material"]["fecha"]
        elif h["material"]["fuente"] == "sin_compras":
            material = "Sin compras"
        else:
            material = "Pendiente"
        filas.append([f["pedido"], f["cliente"] or "—", h["rfq"]["fecha"] or "—", h["contestada"]["fecha"] or "—",
                      _entero(t["comercial"]), h["activacion"]["fecha"] or "—", h["oc"]["fecha"] or "—", material,
                      h["planos"]["fecha"] or "—", _entero(t["tecnico"]), RETRASO.get(f.get("retraso_por"), "—"),
                      _entero(t["total"])])
    _hoja(wb, "Pedidos",
          "Un pedido por línea, el más reciente arriba. Días: los que pasan entre una fecha y la siguiente.",
          ["Pedido", "Cliente", "Llega la oferta", "Contestada", "Días en contestar", "Activado",
           "Orden de compra", "Material recibido", "Planos a fábrica", "Días hasta planos",
           "Lo que retrasó", "Días en total"],
          filas, [18, 30, 15, 15, 13, 15, 20, 16, 15, 13, 14, 13])


def _personas(wb, datos: dict) -> None:
    filas = []
    por_persona = datos["resumen"]["por_persona"]
    for paso, que in PERSONAS:
        for p in sorted((p for p in por_persona if p["paso"] == paso), key=lambda p: -p["n"]):
            filas.append([nombre(p["persona"]), que, _dias(p["mediana"]), p["n"]])
    if not filas:
        filas = [["Sin datos todavía.", "", "", ""]]
    _hoja(wb, "Personas",
          "Lo que tarda normalmente cada uno, y en cuántos pedidos.",
          ["Quién", "Qué hace", "Lo normal", "Pedidos"], filas, [28, 42, 16, 14])


def exportar(datos: dict, ruta) -> str:
    """Escribe el Excel y devuelve su ruta."""
    wb = Workbook()
    wb.remove(wb.active)
    _resumen(wb, datos)
    _que_hacer(wb, datos)
    _pedidos(wb, datos)
    _personas(wb, datos)
    ruta = Path(ruta)
    wb.save(ruta)
    return str(ruta)
