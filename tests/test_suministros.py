# -*- coding: utf-8 -*-
"""Cada documento de una devolución, con SU suministro.

Un mismo aviso puede traer documentos del pedido base y de sus suplementos. El
parser de SACYR (y los de Document Space y AYESA) ponía a todos el suministro
del primero que encontraba en el ERP: la tarjeta del aviso decía «S00» aunque
hubiera documentos del S01, y sus PDF se archivaban en la carpeta del S00.

Sin ERP de verdad: se sustituye por unas filas inventadas.

    .venv\\Scripts\\python.exe tests\\test_suministros.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.parsers import base_parser as B
from core.parsers import sacyr_parser
from core.services import dev_folders, transmittal


fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


# ── El suministro que dice el código ────────────────────────────────────────
for codigo, espera in (("26-059-S01-CAL-0001", "S01"), ("26-059-CAL-0001", ""),
                       ("26-001-S09R-ESP-0005", "S09R"), (" 26 - 001 - s10-ESP-0005", "S10"),
                       ("", ""), (None, ""), ("V-REC627-01-010", "")):
    ok(B.supp_de_codigo(codigo) == espera, f"{codigo!r} → {B.supp_de_codigo(codigo)!r}, no {espera!r}")

df = pd.DataFrame({"Doc. EIPSA": ["26-059-LIS-0001", "26-059-S01-CAL-0001", "26-059-S01-DWG-0001"],
                   "Supp.": ["S00", "S00", "S00"]})
B.supp_por_documento(df)
ok(list(df["Supp."]) == ["S00", "S01", "S01"],
   f"el código manda sobre lo que puso el parser: {list(df['Supp.'])}")
ok(transmittal.suministros_de(df) == "S00, S01", f"y la tarjeta dice los dos: {transmittal.suministros_de(df)!r}")

sin_supp = pd.DataFrame({"Doc. EIPSA": ["26-059-S02-CAL-0001", ""]})
B.supp_por_documento(sin_supp)
ok(list(sin_supp["Supp."]) == ["S02", ""], f"sin columna, se crea: {list(sin_supp['Supp.'])}")
ok(B.supp_por_documento(pd.DataFrame()) is not None, "un correo sin documentos no revienta")

# Y el reparto en carpetas hace caso al código antes que al «Supp.»
ok(dev_folders.sufijo_de({"Supp.": "S00", "Doc. EIPSA": "26-059-S01-CAL-0001"}) == "S01",
   "el PDF del S01 va a la carpeta del S01 aunque el parser dijera S00")
ok(dev_folders.sufijo_de({"Supp.": "S02", "Doc. EIPSA": ""}) == "S02", "sin código, el «Supp.»")

# ── Las filas del ERP, inventadas ───────────────────────────────────────────
ERP = [
    {"Nº Pedido": "P-99/001-S00", "Nº Doc. EIPSA": "99-001-LIS-0001",
     "Nº Doc. Cliente": "V-CLI-99001-001", "Título": "LISTA DE DOCUMENTOS",
     "Cliente": "ACME", "Material": "CAUDAL", "Nº PO": "PO-99001"},
    {"Nº Pedido": "P-99/001-S01", "Nº Doc. EIPSA": "99-001-S01-CAL-0001",
     "Nº Doc. Cliente": "V-CLI-99001-010", "Título": "HOJAS DE DATOS Y CALCULOS - S01",
     "Cliente": "ACME", "Material": "CAUDAL", "Nº PO": "PO-99001"},
    {"Nº Pedido": "P-99/001-S01", "Nº Doc. EIPSA": "",       # sin código EIPSA todavía
     "Nº Doc. Cliente": "V-CLI-99001-011", "Título": "PLANOS DIMENSIONALES - S01",
     "Cliente": "ACME", "Material": "CAUDAL", "Nº PO": "PO-99001"},
]
INDICE = {B.norm_doc_code(d["Nº Doc. Cliente"]): d for d in ERP}

reales = (sacyr_parser.erp_client_code_index, sacyr_parser.get_responsable_initials,
          B.erp_client_code_index, B.get_responsable_initials)
try:
    sacyr_parser.erp_client_code_index = B.erp_client_code_index = lambda: INDICE
    sacyr_parser.get_responsable_initials = B.get_responsable_initials = lambda _p: "JP"

    # SACYR: cada documento, del suministro de su fila del ERP
    html = """<table>
      <tr><td>Document Number</td><td>Title</td><td>Rev</td></tr>
      <tr><td>V-CLI-99001-001</td><td>DOCUMENT LIST</td><td>1</td></tr>
      <tr><td>V-CLI-99001-010</td><td>DATASHEETS</td><td>0</td></tr>
      <tr><td>V-CLI-99001-011</td><td>DRAWINGS</td><td>0</td></tr>
    </table>"""
    asunto = "Supplier Document Issue: 9 - WF#:9-X-SP-OBTS-000001 - DISC:270 - PO:PO-99001 OBTS-000001"
    df = sacyr_parser.parse(html, asunto, "15-10-2026 09:00:00")
    ok(list(df["Supp."]) == ["S00", "S01", "S01"],
       f"SACYR: cada documento con el suyo, aunque uno no tenga código EIPSA: {list(df['Supp.'])}")
    ok(set(df["Nº Pedido"]) == {"P-99/001"}, f"y el pedido, el mismo para todos: {set(df['Nº Pedido'])}")

    # La red de seguridad común: rellena el suministro de cada fila con la suya
    df = pd.DataFrame({"Doc. Cliente": ["V-CLI-99001-011", "V-CLI-99001-001"],
                       "Nº Pedido": ["", ""], "Supp.": ["", ""], "Doc. EIPSA": ["", ""],
                       "Cliente": ["", ""], "Material": ["", ""], "PO": ["", ""]})
    B.enrich_missing_from_erp(df)
    ok(list(df["Supp."]) == ["S01", "S00"],
       f"el hueco de cada fila se rellena con SU suministro, no el del primero: {list(df['Supp.'])}")
    df = pd.DataFrame({"Doc. Cliente": ["V-CLI-99001-011"], "Nº Pedido": [""], "Supp.": ["S03"],
                       "Doc. EIPSA": [""], "Cliente": [""], "Material": [""], "PO": [""]})
    B.enrich_missing_from_erp(df)
    ok(list(df["Supp."]) == ["S03"], "y lo que ya puso el parser se respeta")
finally:
    (sacyr_parser.erp_client_code_index, sacyr_parser.get_responsable_initials,
     B.erp_client_code_index, B.get_responsable_initials) = reales

print("FALLOS:", fallos)
