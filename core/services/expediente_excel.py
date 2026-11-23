"""«Estado documentación.xlsx» del expediente de un cliente.

Las 5 hojas de la carpeta que JP validó a mano (noviembre de 2026): Resumen,
Estado documentación, Documentos pendientes, Últimos correos y Contactos. Mismo
orden, títulos, columnas, colores y anchos.

Dos reglas que salen de lo que falló en el caso real:
  · el libro se escribe **entero cada vez** (nada de insertar filas en uno
    existente: openpyxl mueve el texto pero no los enlaces);
  · cada enlace sale de `enlaces[msgid]` (ruta relativa «Correos/…»), nunca de la
    posición de la fila; si un correo no está en `enlaces`, la celda queda vacía.
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.services import expediente_texto as tx

NOMBRE = "Estado documentación.xlsx"
AZUL = "1B3A5C"
F_CAB = PatternFill("solid", fgColor=AZUL)
F_CLIENTE = PatternFill("solid", fgColor="FDE2E1")
F_EIPSA = PatternFill("solid", fgColor="FFF2CC")
F_OK = PatternFill("solid", fgColor="E2F0D9")
F_ZEBRA = PatternFill("solid", fgColor="F3F6FA")
BORDE = Border(*(Side(style="thin", color="C9D3DF"),) * 4)
LINK = Font(color="0563C1", underline="single")
ROJO = Font(bold=True, color="B41E1E")
FILA_CAB = 4


def _dmy(d) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _sano(t: str) -> str:
    return re.sub(r'[\\/:*?"<>|\[\]]', "", str(t or "")).strip()


def _hoja(wb, nombre, titulo, nota, cab, anchos, filtro=False):
    ws = wb.create_sheet(nombre[:31])
    ws.cell(1, 1, titulo).font = Font(bold=True, size=14, color=AZUL)
    ws.cell(2, 1, nota).font = Font(italic=True, size=10, color="666666")
    for i, h in enumerate(cab, 1):
        c = ws.cell(FILA_CAB, i, h)
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.fill = F_CAB
        c.alignment = Alignment(vertical="center", wrap_text=True)
        c.border = BORDE
    for i, w in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"A{FILA_CAB + 1}"
    ws._filtro = filtro
    return ws


def _fila(ws, valores, enlace=None, col_enlace=None, negrita=False):
    r = max(ws.max_row, FILA_CAB) + 1
    for i, v in enumerate(valores, 1):
        c = ws.cell(r, i, v)
        c.alignment = Alignment(vertical="top", wrap_text=True)
        c.border = BORDE
        if negrita:
            c.font = Font(bold=True)
        if (r - FILA_CAB) % 2 == 0:
            c.fill = F_ZEBRA
    if enlace and col_enlace:
        c = ws.cell(r, col_enlace, "Abrir correo")
        c.hyperlink = enlace
        c.font = LINK
    return r


def _cerrar(ws):
    if ws._filtro and ws.max_row > FILA_CAB:
        ws.auto_filter.ref = f"A{FILA_CAB}:{get_column_letter(ws.max_column)}{ws.max_row}"
    ws.sheet_view.zoomScale = 90
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0


def _ultimo_enlace(po, texto, enlaces):
    for c in tx.ultimos(po, texto):
        if c["msgid"] in enlaces:
            return enlaces[c["msgid"]]
    return None


def exportar(exp: dict, texto: dict, enlaces: dict[str, str], carpeta: Path, corto: str) -> Path:
    """Escribe `carpeta/Estado documentación.xlsx` desde cero y lo devuelve."""
    corto = _sano(corto) or "cliente"
    cliente = exp.get("cliente", "")
    hoy = exp.get("hoy")
    tpos = (texto or {}).get("pos", {})
    tcor = (texto or {}).get("correos", {})
    tcon = (texto or {}).get("contactos", {})
    propio_dom = str(exp.get("propio") or "").split("@")[-1]
    wb = Workbook()
    wb.remove(wb.active)

    # 1. Resumen
    ws = _hoja(wb, "Resumen", f"{cliente}: resumen por PO",
               f"Datos a {_dmy(hoy)}. Fuente: ERP, DocFlow y el buzón de documentación.",
               ["PO", "Pedido", "Proyecto", "Lo esencial"], [13, 20, 9, 120])
    for po, p in exp["pos"].items():
        g = tpos.get(po, {})
        punto = tx.elegir(g.get("punto"), tx.punto_auto(p)[0])
        vinetas = tx.lo_esencial(p, hoy) + [f"En qué punto estamos: {punto}"]
        _fila(ws, [po, " + ".join(p["pedidos"]), p.get("proyecto", ""), "\n".join("• " + v for v in vinetas)])
    _cerrar(ws)

    # 2. Estado documentación
    ws = _hoja(wb, "Estado documentación", "Estado de la documentación por PO",
               f"Rojo = lo tiene {corto} o su cliente final · Amarillo = lo tiene EIPSA. "
               "Los días se cuentan desde el último envío de EIPSA.",
               ["PO", "Pedido", "Proyecto", "Equipo", "Total docs.", "Aprobados", f"Esperando a {corto} / cliente",
                "En EIPSA", "Días máx. esperando", "En qué punto estamos", "Siguiente paso", "Último correo"],
               [13, 20, 9, 28, 9, 10, 12, 9, 11, 60, 40, 14])
    tot = [0, 0, 0, 0]
    for po, p in exp["pos"].items():
        d, g = p["docs"], tpos.get(po, {})
        reemitir = g.get("reemitir", [])
        en_eipsa = len(d["eipsa"]) + len(reemitir)
        auto = tx.punto_auto(p)
        mx = max((x.get("dias") or 0 for x in d["cliente"]), default=0)
        r = _fila(ws, [po, " + ".join(p["pedidos"]), p.get("proyecto", ""), p.get("equipo", ""), d["total"], d["aprobados"],
                       len(d["cliente"]), en_eipsa, mx, tx.elegir(g.get("punto"), auto[0]),
                       tx.elegir(g.get("siguiente"), auto[1]), ""],
                  _ultimo_enlace(p, texto, enlaces), 12)
        ws.cell(r, 7).fill = F_CLIENTE
        ws.cell(r, 8).fill = F_EIPSA if en_eipsa else F_OK
        for i, v in enumerate((d["total"], d["aprobados"], len(d["cliente"]), en_eipsa)):
            tot[i] += v
    _fila(ws, ["TOTAL", "", "", "", *tot, "", "", "", ""], negrita=True)
    _cerrar(ws)

    # 3. Documentos pendientes
    ws = _hoja(wb, "Documentos pendientes", "Documentos que faltan por cerrar",
               "Ordenado por PO y por días de espera. «Veces enviado» es un mínimo según el historial del ERP.",
               ["PO", "Pedido", f"Nº documento {corto}", "Título", "De qué lado", f"Dónde está (según {corto})",
                "Último envío EIPSA", "Días esperando", "Veces enviado", "Qué falta"],
               [13, 15, 27, 55, 15, 38, 12, 10, 9, 55], filtro=True)
    for po, p in exp["pos"].items():
        g = tpos.get(po, {})
        segun = g.get("segun_cliente", {})
        for lado, docs in (("cliente", p["docs"]["cliente"]), ("eipsa", p["docs"]["eipsa"])):
            for dd in docs:
                r = _fila(ws, [po, dd["pedido"], dd["doc_cliente"], dd["titulo"],
                               f"CLIENTE ({corto})" if lado == "cliente" else "EIPSA", segun.get(dd["doc_cliente"], ""),
                               _dmy(dd.get("enviado")), dd.get("dias"), dd.get("envios"), tx.que_falta(dd, lado)])
                ws.cell(r, 5).fill = F_CLIENTE if lado == "cliente" else F_EIPSA
                ws.cell(r, 5).font = Font(bold=True)
                if (dd.get("dias") or 0) >= 60:
                    ws.cell(r, 8).font = ROJO
        for doc in g.get("reemitir", []):
            r = _fila(ws, [po, "", doc, "", f"EIPSA (espera a {corto})", "", "Por reemitir", "", "",
                           "Reemitir en As Built cuando el cliente devuelva el resto de documentos."])
            ws.cell(r, 5).fill = F_EIPSA
            ws.cell(r, 5).font = Font(bold=True)
    _cerrar(ws)

    # 4. Últimos correos
    ws = _hoja(wb, "Últimos correos", "Últimos correos importantes",
               "Los enlaces abren el correo original guardado en la carpeta Correos, junto a este Excel.",
               ["PO / proyecto", "Fecha", "De", "Asunto", "Qué dice", "Respuesta / situación", "Correo"],
               [13, 11, 24, 45, 60, 38, 13], filtro=True)
    for po, p in exp["pos"].items():
        for c in tx.ultimos(p, texto):
            t = tcor.get(c["msgid"], {})
            nuestro = propio_dom and c.get("de_email", "").endswith("@" + propio_dom)
            _fila(ws, [po, _dmy(c["fecha"]), "EIPSA" if nuestro else (c.get("de_nombre") or c.get("de_email", "")),
                       c.get("asunto", ""), tx.elegir(t.get("que_dice"), c.get("asunto", "")), t.get("respuesta", ""), ""],
                  enlaces.get(c["msgid"]), 7)
    _cerrar(ws)

    # 5. Contactos
    ws = _hoja(wb, f"Contactos {corto}", f"Contactos de {cliente}, por orden de su última respuesta",
               "Arriba, quien ha contestado más recientemente. Solo personas que han escrito al menos un correo; "
               "las que solo van en copia, abajo.",
               ["#", "Nombre", "Cargo", "Correo", "Teléfono", "Último correo enviado", "Asunto de ese correo",
                "Correos enviados", "PO en los que interviene", "Correo"],
               [4, 26, 38, 34, 22, 13, 50, 10, 30, 13], filtro=True)
    escritos = [k for k in exp.get("contactos", []) if k.get("ultimo")]
    copias = [k for k in exp.get("contactos", []) if not k.get("ultimo")]
    for i, k in enumerate(escritos, 1):
        t = tcon.get(k["email"], {})
        _fila(ws, [i, k["nombre"], tx.elegir(t.get("cargo"), k.get("cargo", "")), k["email"],
                   tx.elegir(t.get("telefono"), k.get("telefono", "")), _dmy(k["ultimo"]), k.get("asunto", ""),
                   k.get("enviados", 0), ", ".join(k.get("pos", [])), ""], enlaces.get(k.get("msgid", "")), 10)
    if copias:
        _fila(ws, ["", "Solo en copia (no han escrito)", "", "", "", "", "", "", "", ""], negrita=True)
        for k in copias:
            t = tcon.get(k["email"], {})
            _fila(ws, ["", k["nombre"], tx.elegir(t.get("cargo"), k.get("cargo", "")), k["email"],
                       tx.elegir(t.get("telefono"), k.get("telefono", "")), "", "", 0, ", ".join(k.get("pos", [])), ""])
    _cerrar(ws)

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / NOMBRE
    wb.save(ruta)
    return ruta
