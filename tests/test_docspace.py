# -*- coding: utf-8 -*-
"""Qué correos de Document Space son devoluciones: solo los transmittals de un
proyecto dado de alta, no sus avisos. Asuntos inventados con el mismo formato.

    .venv\\Scripts\\python.exe tests\\test_docspace.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.parsers import docspace_parser as D  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


D.DOCSPACE_PROJECT_MAP = {"PRY&001": "P-99/001 | S00 | REF001"}

for asunto in ("[PRY&001-CI0021-HS-EI-T-0039] Vendor Data Review Result for Orifice",
               "[PRY&001-CI0021-HS-EI-T-0043] Vendor Data Review Result for Orifice"):
    ok(D.matches_subject(asunto), f"un transmittal es una devolución: {asunto}")

for asunto, porque in (
        ("[PRY&001-CI-PO-0021] Notification of vendor document delay", "aviso de retraso"),
        ("[PRY&001-CI-PO-0021] Notification of vendor document submission", "aviso de envío"),
        ("[DocumentSpace] Authentication Number Infomation", "aviso del sistema"),
        ("[SACE2] Vendor document IFC", "correo de una persona"),
        ("[VDTR-CI-1602] PRY&001-CI0021-EIPSA-HS-T-0063", "aviso de workflow"),
        ("[OTRO&009-CI0021-HS-EI-T-0001] Vendor Data Review Result", "proyecto sin dar de alta")):
    ok(not D.matches_subject(asunto), f"{porque}: no es una devolución ({asunto})")

print("FALLOS:", fallos)
