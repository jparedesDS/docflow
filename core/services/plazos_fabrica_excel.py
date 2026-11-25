"""Plazos a fábrica en Excel: del pedido activado a los planos en fábrica.

El otro Excel de Plazos (`seguimiento_excel`) cuenta días naturales. Este,
más escueto, pone al lado los días laborables: sin sábados, domingos,
festivos (nacionales y de la Comunidad de Madrid) ni agosto, que la empresa
cierra. Así un pedido activado el 29/07 y pasado a fábrica el 02/09 cuenta 4
días, no 35.

  · Resumen — media y mediana, en días naturales y laborables.
  · Pedidos — pedido, activado, planos a fábrica y los días. En verde, los que
    faltan por pasar a fábrica (días hasta hoy) y, si ya llevan más que lo
    normal, el retraso, en rojo; en gris, sin fecha de planos.
  · Personas — lo que tarda normalmente cada uno en su paso, en días
    naturales y laborables.
  · Festivos — los días que no se cuentan. Se pueden añadir filas en el Excel
    (fiestas locales…): las fórmulas las cogen.

Fuera quedan los suministros «R» (regularizaciones: en el ERP o en el nombre
de la carpeta) y los anulados en el ERP.
Los días van como fórmulas de Excel para que se pueda ver y tocar el cálculo.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill

from core.services.plazos_dias import (  # noqa: F401 — pascua, laborables…: también se usan desde aquí
    FESTIVOS_AÑO, FIJOS, fuera, laborables, no_laborables, pascua, pendiente, por_persona)
from core.services.seguimiento import _dia
from core.services.seguimiento_excel import (AZUL, LETRA, PERSONAS, ROJO, _BORDE, _FORMATO_FECHA, _imprimir,
                                             nombre)

VERDE, GRIS, CEBRA = "C6EFCE", "E7E6E6", "F2F2F2"
FILAS_LIBRES_FESTIVOS = 100     # hueco al final de «Festivos» que ya entra en las fórmulas

def filas(datos: dict) -> tuple[list[dict], dict]:
    """[{pedido, activado, planos, estado}] por activación (pendientes al final) y lo que se quitó.

    estado: «hecho» (planos en fábrica), «pendiente» (en la cola esperando planos)
    o «sin_fecha» (no se encontró el correo de planos de uno ya hecho o enviado).
    No se usa la cola: descarta los de entrega vencida hace meses, y a veces es
    solo que el ERP tiene mal el año de la entrega."""
    quitados = {"R": 0, "anulado": 0}
    out = []
    for f in datos["filas"]:
        motivo = fuera(f)
        if motivo:
            quitados[motivo] += 1
            continue
        activado = _dia(f["hitos"]["activacion"]["fecha"])
        if not activado:
            continue
        planos = _dia(f["hitos"]["planos"]["fecha"])
        estado = "hecho" if planos else ("pendiente" if pendiente(f) else "sin_fecha")
        out.append({"pedido": f["pedido"], "activado": activado, "planos": planos, "estado": estado})
    out.sort(key=lambda x: (x["estado"] == "pendiente", x["activado"], x["pedido"]))
    return out, quitados


# ── Excel ─────────────────────────────────────────────────────────────────────

def _celda(ws, fila, col, valor, *, negrita=False, relleno=None, centro=True, formato=None, tamaño=LETRA):
    c = ws.cell(fila, col, valor)
    c.font = Font(size=tamaño, bold=negrita)
    c.border = _BORDE
    c.alignment = Alignment(vertical="center", horizontal="center" if centro else "left")
    if formato:
        c.number_format = formato
    if relleno:
        c.fill = PatternFill("solid", fgColor=relleno)
    return c


def _titulo(ws, titulo: str, frase: str) -> None:
    ws.cell(1, 1, titulo).font = Font(size=20, bold=True, color=AZUL)
    ws.cell(2, 1, frase).font = Font(size=LETRA, italic=True, color="595959")
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 24


def _cabecera(ws, fila: int, textos: list[str], desde: int = 1) -> None:
    for j, t in enumerate(textos, start=desde):
        c = ws.cell(fila, j, t)
        c.font = Font(size=LETRA, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _BORDE
    ws.row_dimensions[fila].height = 42


def _festivos(wb, cerrado: dict[date, str]) -> str:
    ws = wb.create_sheet("Festivos")
    _titulo(ws, "Días que no se cuentan",
            "Festivos nacionales y de Madrid, y agosto entero. Añade filas (fiestas locales…) y las fórmulas las cogen.")
    _cabecera(ws, 3, ["Fecha", "Motivo"])
    for i, (d, motivo) in enumerate(cerrado.items(), start=4):
        _celda(ws, i, 1, datetime(d.year, d.month, d.day), formato=_FORMATO_FECHA)
        _celda(ws, i, 2, motivo, centro=False)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 40
    ws.freeze_panes = "A4"
    _imprimir(ws)
    return f"Festivos!$A$4:$A${3 + len(cerrado) + FILAS_LIBRES_FESTIVOS}"


def _personas(wb, datos: dict, cerrado) -> None:
    ws = wb.create_sheet("Personas")
    _titulo(ws, "Personas", "Lo que tarda normalmente cada uno en su paso (la mitad tarda menos), y en cuántos pedidos.")
    _cabecera(ws, 3, ["Quién", "Qué hace", "Pedidos", "Lo normal (días naturales)", "Lo normal (días laborables)"])
    lista = por_persona(datos, cerrado, PERSONAS)
    for i, p in enumerate(lista, start=4):
        relleno = CEBRA if i % 2 else None
        _celda(ws, i, 1, nombre(p["persona"]), relleno=relleno, centro=False)
        _celda(ws, i, 2, p["que"], relleno=relleno, centro=False)
        _celda(ws, i, 3, p["n"], relleno=relleno)
        _celda(ws, i, 4, p["naturales"], relleno=relleno)
        _celda(ws, i, 5, p["laborables"], relleno=relleno, negrita=True)
        ws.row_dimensions[i].height = 22
    if not lista:
        _celda(ws, 4, 1, "Sin datos todavía.", centro=False)
    for col, ancho in zip("ABCDE", (28, 40, 12, 18, 18)):
        ws.column_dimensions[col].width = ancho
    ws.freeze_panes = "A4"
    ws.print_title_rows = "3:3"
    _imprimir(ws)


def exportar(datos: dict, ruta) -> str:
    """Escribe el Excel y devuelve su ruta."""
    generado = datos.get("generado") or datetime.now()
    hoy = generado.date()
    lista, quitados = filas(datos)
    años = {d.year for x in lista for d in (x["activado"], x["planos"]) if d} | {hoy.year}
    cerrado = no_laborables(range(min(años), max(años) + 1))

    wb = Workbook()
    res = wb.active
    res.title = "Resumen"
    ped = wb.create_sheet("Pedidos")
    _personas(wb, datos, cerrado)
    rango_fes = _festivos(wb, cerrado)

    # Pedidos
    _titulo(ped, "Del pedido activado a los planos en fábrica",
            "Días laborables: sin sábados, domingos, festivos ni agosto. En verde, los que faltan por pasar "
            "a fábrica (días hasta hoy); en rojo, los que ya llevan más que lo normal; en gris, sin fecha de planos.")
    _cabecera(ped, 3, ["Pedido", "Pedido activado", "Planos a fábrica", "Días naturales", "Días laborables",
                       "Esperando / retraso (días laborables)"])
    for i, x in enumerate(lista, start=4):
        a = x["activado"]
        if x["estado"] == "hecho":
            relleno = CEBRA if i % 2 else None
            planos = datetime(x["planos"].year, x["planos"].month, x["planos"].day)
            nat, lab = f"=C{i}-B{i}", f"=MAX(0,NETWORKDAYS(B{i}+1,C{i},{rango_fes}))"
            espera = ""
        elif x["estado"] == "pendiente":
            relleno, planos = VERDE, "Pendiente"
            nat, lab = f"=Resumen!$C$4-B{i}", f"=MAX(0,NETWORKDAYS(B{i}+1,Resumen!$C$4,{rango_fes}))"
            # Retraso: lleva más días laborables que lo normal (la mediana del Resumen)
            espera = (f'=IF(AND(ISNUMBER(Resumen!$D$8),E{i}>Resumen!$D$8),'
                      f'"Retraso: "&(E{i}-Resumen!$D$8)&" días más de lo normal",'
                      f'"Esperando: "&E{i}&IF(E{i}=1," día"," días"))')
        else:
            relleno, planos = GRIS, "Sin fecha"
            nat = lab = espera = ""
        _celda(ped, i, 1, x["pedido"], relleno=relleno, centro=False)
        _celda(ped, i, 2, datetime(a.year, a.month, a.day), relleno=relleno, formato=_FORMATO_FECHA)
        _celda(ped, i, 3, planos, relleno=relleno, formato=_FORMATO_FECHA)
        _celda(ped, i, 4, nat, relleno=relleno)
        _celda(ped, i, 5, lab, relleno=relleno)
        _celda(ped, i, 6, espera, relleno=relleno, centro=False)
        ped.row_dimensions[i].height = 22
    ultima = 3 + max(len(lista), 1)
    for col, ancho in zip("ABCDEF", (20, 17, 17, 15, 15, 42)):
        ped.column_dimensions[col].width = ancho
    ped.conditional_formatting.add(
        f"A4:F{ultima}", FormulaRule(formula=['LEFT($F4,7)="Retraso"'], stopIfTrue=True,
                                     fill=PatternFill("solid", fgColor=ROJO, bgColor=ROJO),
                                     font=Font(bold=True, color="9C0006")))
    ped.freeze_panes = "A4"
    ped.print_title_rows = "3:3"
    ped.auto_filter.ref = f"A3:F{ultima}"
    _imprimir(ped)

    # Resumen. Los pendientes van al final: las medias, solo con el bloque de
    # arriba (las filas sin fecha llevan "" y Excel no las cuenta).
    k = 3 + sum(1 for x in lista if x["estado"] != "pendiente")
    _titulo(res, "Del pedido activado a los planos en fábrica",
            f"Pedidos de {' y '.join(str(a) for a in datos.get('años') or ())} · actualizado el {hoy:%d/%m/%Y}")
    res.cell(4, 2, "Hoy").font = Font(size=LETRA, bold=True)
    _celda(res, 4, 3, datetime(hoy.year, hoy.month, hoy.day), formato=_FORMATO_FECHA)
    _cabecera(res, 6, ["Días naturales", "Días laborables"], desde=3)
    for fila, texto, fn in ((7, "Media", "ROUND(AVERAGE({}),0)"),
                            (8, "Lo normal (la mitad tarda menos)", "ROUND(MEDIAN({}),0)")):
        _celda(res, fila, 2, texto, negrita=True, centro=False, tamaño=16)
        for col, letra in ((3, "D"), (4, "E")):
            v = f"=IFERROR({fn.format(f'Pedidos!{letra}4:{letra}{k}')},\"—\")" if k > 3 else "—"
            c = _celda(res, fila, col, v, tamaño=16)
            c.font = Font(size=16, bold=True, color=AZUL)
        res.row_dimensions[fila].height = 28
    n = {e: sum(1 for x in lista if x["estado"] == e) for e in ("hecho", "pendiente", "sin_fecha")}
    for fila, texto, v in ((10, "Pedidos contados", n["hecho"]),
                           (11, "Faltan por pasar a fábrica (en verde)", n["pendiente"]),
                           (12, "    De ellos, con retraso (en rojo)",
                            f'=COUNTIF(Pedidos!F4:F{ultima},"Retraso*")'),
                           (13, "Sin fecha de planos (en gris, no cuentan)", n["sin_fecha"]),
                           (14, "Quitados: suministros «R» (regularizaciones)", quitados["R"]),
                           (15, "Quitados: anulados", quitados["anulado"])):
        _celda(res, fila, 2, texto, centro=False)
        _celda(res, fila, 3, v)
    nota = res.cell(17, 2, "Días laborables: no cuentan sábados, domingos, festivos ni agosto, que la empresa "
                           "cierra (hoja «Festivos»). Ejemplo: activado el 29/07 y a fábrica el 02/09 son 35 "
                           "días naturales y 4 laborables. Retraso: un pedido sin pasar a fábrica que ya lleva "
                           "más días laborables que lo normal.")
    nota.font = Font(size=LETRA, italic=True, color="595959")
    nota.alignment = Alignment(wrap_text=True, vertical="top")
    res.merge_cells("B17:D20")
    res.column_dimensions["A"].width = 3
    res.column_dimensions["B"].width = 52
    res.column_dimensions["C"].width = 18
    res.column_dimensions["D"].width = 18
    _imprimir(res)

    ruta = Path(ruta)
    wb.save(ruta)
    return str(ruta)
