# -*- coding: utf-8 -*-
"""Excel «Plazos a fábrica»: días laborables (sin fines de semana, festivos ni
agosto), qué suministros quedan fuera y cómo se pinta cada pedido.

Datos inventados (P-99/…).

    .venv\\Scripts\\python.exe tests\\test_plazos_fabrica.py
"""
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import load_workbook  # noqa: E402

from core.services import plazos_fabrica_excel as px  # noqa: E402
from core.services.seguimiento_erp import anulado  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


# ── Calendario ────────────────────────────────────────────────────────────────
ok(px.pascua(2024) == date(2024, 3, 31), px.pascua(2024))
ok(px.pascua(2025) == date(2025, 4, 20), px.pascua(2025))
ok(px.pascua(2026) == date(2026, 4, 5), px.pascua(2026))

cerrado = px.no_laborables([2025, 2026])
ok(date(2026, 4, 2) in cerrado and date(2026, 4, 3) in cerrado, "Jueves y Viernes Santo 2026")
ok(date(2025, 8, 18) in cerrado, "agosto entero")
ok(date(2025, 8, 16) not in cerrado, "los fines de semana no hace falta listarlos")
ok(all(d.weekday() < 5 for d in cerrado), "solo días de diario")

L = px.laborables
ok(L(date(2026, 7, 29), date(2026, 9, 2), cerrado) == 4, "29/07 → 02/09: 4 laborables (agosto no cuenta)")
ok(L(date(2026, 11, 20), date(2026, 11, 23), cerrado) == 1, "viernes → lunes: 1")
ok(L(date(2026, 11, 20), date(2026, 11, 20), cerrado) == 0, "el mismo día: 0")
ok(L(date(2026, 11, 20), date(2026, 11, 19), cerrado) == 0, "planos antes de activar: 0, no negativo")
ok(L(date(2026, 12, 4), date(2026, 12, 9), cerrado) == 1, "puente de diciembre 2026: solo el 9")

# ── Anulados en el ERP ─────────────────────────────────────────────────────────
ok(anulado("El cliente final ha anulado el pedido", None), "notas: anulado")
ok(anulado("", "PEDIDO ANULADO"), "observación de entregas: ANULADO")
ok(not anulado("IGNACIO CANCELA PINTO", None), "un apellido no es una anulación")
ok(not anulado(None, None), "sin texto")


# ── Filas ─────────────────────────────────────────────────────────────────────
def fila(pedido, activado, planos=None, **extra):
    h = {k: {"fecha": None, "fuente": "", "persona": ""} for k in ("activacion", "planos", "envio")}
    h["activacion"]["fecha"] = activado
    h["planos"]["fecha"] = planos
    h["envio"]["fecha"] = extra.pop("envio", None)
    return {"pedido": pedido, "hitos": h, "estado": "ok", "cerrado": False, "porc_taller": None,
            "anulado": False, **extra}


datos = {
    "generado": datetime(2026, 11, 25, 9, 0), "años": (2025, 2026), "cola": [],
    "filas": [
        fila("P-99/001-S00", date(2026, 7, 29), datetime(2026, 9, 2, 10, 30)),
        fila("P-99/002-S00", date(2026, 3, 2), date(2026, 3, 12)),
        fila("P-99/002-S01R", date(2026, 4, 1)),                       # regularización: fuera
        fila("P-99/003-S00", date(2026, 2, 1), anulado=True),          # anulado: fuera
        fila("P-99/004-S00", date(2026, 11, 18)),                      # en marcha: pendiente
        fila("P-99/005-S00", date(2025, 5, 5), envio=date(2025, 9, 1)),  # enviado sin correo: sin fecha
    ],
}
lista, quitados = px.filas(datos)
ok(quitados == {"R": 1, "anulado": 1}, quitados)
ok([x["pedido"] for x in lista] == ["P-99/005-S00", "P-99/002-S00", "P-99/001-S00", "P-99/004-S00"],
   [x["pedido"] for x in lista])
ok([x["estado"] for x in lista] == ["sin_fecha", "hecho", "hecho", "pendiente"], [x["estado"] for x in lista])
ok(lista[2]["planos"] == date(2026, 9, 2), "la hora del correo se reduce a su día")

# ── Excel ─────────────────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp())
wb = load_workbook(px.exportar(datos, tmp / "fabrica.xlsx"))
ok(wb.sheetnames == ["Resumen", "Pedidos", "Festivos"], wb.sheetnames)
ped = wb["Pedidos"]
ok([c.value for c in ped[3]] == ["Pedido", "Pedido activado", "Planos a fábrica", "Días naturales",
                                 "Días laborables"], [c.value for c in ped[3]])
ok(ped["A6"].value == "P-99/001-S00" and ped["D6"].value == "=C6-B6", (ped["A6"].value, ped["D6"].value))
ok(ped["E6"].value.startswith("=MAX(0,NETWORKDAYS(B6+1,C6,Festivos!$A$4:"), ped["E6"].value)
ok(ped["C4"].value == "Sin fecha" and ped["D4"].value in ("", None), "sin fecha: sin días")
ok(ped["C7"].value == "Pendiente" and "Resumen!$C$4" in ped["E7"].value, "pendiente: días hasta hoy")
ok(ped["B6"].number_format == "dd/mm/yyyy", ped["B6"].number_format)
res = wb["Resumen"]
ok(res["C7"].value == '=IFERROR(ROUND(AVERAGE(Pedidos!D4:D6),0),"—")', res["C7"].value)
ok(res["D8"].value == '=IFERROR(MEDIAN(Pedidos!E4:E6),"—")', "las medias no cogen a los pendientes")
ok(res["C10"].value == 2 and res["C11"].value == 1 and res["C12"].value == 1, "recuentos")
ok(res["C13"].value == 1 and res["C14"].value == 1, "quitados")
fes = wb["Festivos"]
ok(fes["A4"].value is not None and fes["B4"].value, "festivos listados")

vacio = load_workbook(px.exportar({**datos, "filas": []}, tmp / "vacio.xlsx"))
ok(vacio["Resumen"]["C7"].value == "—", "sin pedidos no hay fórmulas rotas")

print("OK" if not fallos else f"{fallos} fallo(s)")
sys.exit(1 if fallos else 0)
