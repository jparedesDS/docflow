# -*- coding: utf-8 -*-
"""Expediente de cliente: «Estado documentación.xlsx» (las 5 hojas de la
carpeta validada, enlaces relativos solo a correos que existan).

Datos inventados (P-99/…, PO 1099…, @ejemplo.test).

    .venv\\Scripts\\python.exe tests\\test_expediente_excel.py
"""
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import expediente_excel as xl  # noqa: E402

fallos = 0
TMP = Path(tempfile.mkdtemp())


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


def doc(n, dias):
    return {"pedido": "P-99/023-S00", "doc_cliente": f"5099_18-1099010610-0000{n}", "doc_eipsa": f"99-023-DOC-000{n}",
            "titulo": f"DOCUMENTO {n}", "estado": "Enviado", "rev": "3", "enviado": date(2099, 8, 1), "dias": dias,
            "envios": 2, "primer_envio": date(2099, 1, 1), "seguimiento": ""}


def correo(mid, de, nombre, dia, auto=False):
    return {"msgid": mid, "fecha": datetime(2099, 11, dia, 11, 14), "de_nombre": nombre, "de_email": de, "para": "",
            "cc": "", "asunto": f"RE: estado {mid}", "cuerpo": "", "adjuntos": [], "carpeta": "X", "automatico": auto}


PO1 = {"po": "1099010610", "pedidos": ["P-99/023", "P-99/064"], "proyecto": "UNO", "equipo": "Termómetros",
       "importe": 5260.0, "ultima_entrega": date(2099, 9, 29), "suministros": [],
       "docs": {"total": 14, "aprobados": 2, "cliente": [doc(1, 111), doc(2, 13)],
                "eipsa": [dict(doc(3, 5), estado="Com. Menores")]},
       "facturas": [{"numero": "F-99/239", "fecha": date(2099, 9, 16), "dias": 64, "base": 2980.0, "total": 3605.8,
                     "concepto": "TAG", "iva": 21.0, "pedido": "P-99/023", "su_ref": "", "reciente": True}],
       "verificar": [], "deuda_base": 2980.0, "deuda_total": 3605.8, "avales": [],
       "correos": [correo("m1", "ana@ejemplo.test", "Ana Ejemplo", 18), correo("m2", "doc@eipsa.test", "Doc", 17),
                   correo("m3", "x@ejemplo.test", "X", 16, auto=True)],
       "recl_eipsa": [date(2099, 10, 16)], "recl_cliente": []}
PO2 = dict(PO1, po="1099020910", pedidos=["P-99/090"], docs={"total": 3, "aprobados": 3, "cliente": [], "eipsa": []},
           facturas=[], deuda_base=0.0, deuda_total=0.0, correos=[], recl_eipsa=[])
EXP = {"cliente": "CLIENTE FICTICIO", "hoy": date(2099, 11, 19), "avisos": [], "propio": "doc@eipsa.test",
       "pos": {"1099010610": PO1, "1099020910": PO2},
       "contactos": [{"nombre": "Luis Ejemplo", "email": "luis@ejemplo.test", "cargo": "Expeditor", "telefono": "",
                      "ultimo": date(2099, 11, 18), "asunto": "RE: estado", "enviados": 3, "msgid": "m9",
                      "pos": ["1099010610"]},
                     {"nombre": "Ana Ejemplo", "email": "ana@ejemplo.test", "cargo": "", "telefono": "",
                      "ultimo": date(2099, 11, 10), "asunto": "x", "enviados": 1, "msgid": "m1", "pos": ["1099010610"]},
                     {"nombre": "Marta Ejemplo", "email": "marta@ejemplo.test", "cargo": "", "telefono": "",
                      "ultimo": None, "asunto": "", "enviados": 0, "msgid": "", "pos": []}]}
TEXTO = {"pos": {"1099010610": {"segun_cliente": {"5099_18-1099010610-00001": "Con su cliente final (CF, 18/11)"},
                                "punto": "Texto de JP"}},
         "correos": {"m1": {"que_dice": "Contesta con el estado.", "respuesta": "Último correo."}},
         "contactos": {"ana@ejemplo.test": {"cargo": "Document Expeditor", "telefono": "+34 600"}}}
ENL = {"m1": "Correos/2099-11-18 11h14 - ana - RE estado.eml"}


def test_exportar():
    ruta = xl.exportar(EXP, TEXTO, ENL, TMP, corto="CF")
    ok(ruta.name == "Estado documentación.xlsx" and ruta.exists(), ruta)
    wb = load_workbook(ruta)
    ok(wb.sheetnames == ["Resumen", "Estado documentación", "Documentos pendientes", "Últimos correos", "Contactos CF"],
       wb.sheetnames)
    r = wb["Resumen"]
    ok(r["A1"].value == "CLIENTE FICTICIO: resumen por PO" and [c.value for c in r[4]] == ["PO", "Pedido", "Proyecto", "Lo esencial"],
       [c.value for c in r[4]])
    ok(str(r["D5"].value).startswith("• Nos deben 2.980,00 €") and "• En qué punto estamos: Texto de JP" in r["D5"].value, r["D5"].value)
    ws = wb["Estado documentación"]
    cab = [c.value for c in ws[4]]
    ok(cab[6] == "Esperando a CF / cliente" and ws["A5"].value == "1099010610", cab)
    ok(ws.cell(5, 7).fill.fgColor.rgb.endswith("FDE2E1") and ws.cell(5, 8).fill.fgColor.rgb.endswith("FFF2CC"), "rojo / amarillo")
    ok(ws.cell(6, 8).fill.fgColor.rgb.endswith("E2F0D9"), "verde si no hay nada en EIPSA")
    ok(ws.cell(5, 10).value == "Texto de JP" and ws.cell(5, 11).value == "Reclamar la devolución de los 2 documentos.",
       (ws.cell(5, 10).value, ws.cell(5, 11).value))
    ok(ws.cell(5, 12).hyperlink is not None and ws.cell(5, 12).hyperlink.target == ENL["m1"], "último correo del PO enlazado")
    ok(ws.cell(ws.max_row, 1).value == "TOTAL" and ws.cell(ws.max_row, 5).value == 17 and ws.cell(ws.max_row, 7).value == 2,
       [c.value for c in ws[ws.max_row]])
    dp = wb["Documentos pendientes"]
    ok(dp.cell(5, 3).value == "5099_18-1099010610-00001" and dp.cell(5, 6).value == "Con su cliente final (CF, 18/11)",
       [c.value for c in dp[5]])
    ok(dp.cell(5, 5).value == "CLIENTE (CF)" and dp.cell(5, 8).font.bold and dp.cell(7, 5).value == "EIPSA", "lados y días ≥ 60")
    ok(dp.auto_filter.ref and dp.freeze_panes == "A5", (dp.auto_filter.ref, dp.freeze_panes))
    uc = wb["Últimos correos"]
    links = [c.hyperlink.target for row in uc.iter_rows(min_row=5) for c in row if c.hyperlink]
    ok(links == [ENL["m1"]], links)                                      # relativo y solo el que existe
    filas = [[c.value for c in row] for row in uc.iter_rows(min_row=5)]
    ok([f[2] for f in filas] == ["Ana Ejemplo", "EIPSA"], "los automáticos fuera; lo nuestro sale como EIPSA")
    ok(filas[0][4] == "Contesta con el estado." and filas[1][4] == "RE: estado m2", "qué dice: lo de JP o el asunto")
    k = wb["Contactos CF"]
    ok(k.cell(5, 2).value == "Luis Ejemplo" and k.cell(5, 1).value == 1, "último en responder, primero")
    ok(k.cell(6, 3).value == "Document Expeditor" and k.cell(6, 5).value == "+34 600", "cargo y teléfono de JP")
    ok(k.cell(6, 10).hyperlink.target == ENL["m1"] and k.cell(5, 10).hyperlink is None, "enlace solo si existe")
    ok(k.cell(7, 2).value == "Solo en copia (no han escrito)" and k.cell(8, 2).value == "Marta Ejemplo", "copias abajo")


def test_casos_raros():
    vacio = dict(EXP, cliente="A/B:C S.A.", pos={}, contactos=[])
    ruta = xl.exportar(vacio, {}, {}, TMP / "vacio", corto="A/B:C")
    wb = load_workbook(ruta)
    ok(wb.sheetnames[-1] == "Contactos ABC", wb.sheetnames)
    ok(len(xl.exportar(dict(EXP, pos={}), {}, {}, TMP / "largo", corto="X" * 40).name) > 0, "corto largo")
    ok(len(load_workbook(TMP / "largo" / "Estado documentación.xlsx").sheetnames[-1]) <= 31, "hoja ≤ 31 caracteres")


test_exportar()
test_casos_raros()

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
