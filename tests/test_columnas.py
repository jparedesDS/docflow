# -*- coding: utf-8 -*-
"""Las tablas reparten el ancho: todas las columnas a la vista, los códigos
enteros, el texto largo con «…» y scroll horizontal solo si ni así caben.

    .venv\\Scripts\\python.exe tests\\test_columnas.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk  # noqa: E402

from gui import theme  # noqa: E402
from gui.widgets import columnas  # noqa: E402
from gui.widgets.pilltable import PillTable  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


# ── El reparto ──────────────────────────────────────────────────────────────
ok(columnas.repartir([100, 200], [50, 80], 400) == [100, 200], "con sitio, cada una a su preferido")
r = columnas.repartir([100, 200], [50, 80], 250)
ok(sum(r) == 250 and r[0] >= 50 and r[1] >= 80, f"con menos, encogen y caben justas: {r}")
ok(r[1] < 200 and 200 - r[1] > 100 - r[0], f"encoge más la que más holgura tiene: {r}")
ok(columnas.repartir([100, 200], [90, 190], 200) == [90, 190], "ni con los suelos: los suelos (y scroll)")
ok(columnas.medidas(60, 40, 300, largo=columnas.LARGO) == (150, 150), "texto libre: suelo hasta LARGO")
ok(columnas.medidas(60, 40, 170, largo=columnas.CODIGO) == (170, 170),
   "un código: su preferido crece hasta que se vea entero")
ok(columnas.medidas(200, 40, 400, fijo=90) == (200, 90), "un suelo puesto a mano manda")

# ── La tabla ────────────────────────────────────────────────────────────────
COLS = [
    {"key": "Doc", "label": "Nº Doc.", "min": 120},
    {"key": "Titulo", "label": "Título", "min": 300, "stretch": True, "floor": 90},
    {"key": "Estado", "label": "Estado", "min": 110, "anchor": "center"},
]
CODIGO = "99-001-S01-PLG-0005-EXTRA"
LARGO = "PRESERVATION AND STORAGE PROCEDURE FOR RESTRICTION ORIFICES AND FLOW ELEMENTS"
filas = [(f"r{i}", {"Doc": {"text": CODIGO, "fg": theme.ACCENT},
                    "Titulo": {"text": LARGO},
                    "Estado": {"text": "Aprobado", "pill": True, "fg": theme.GREEN,
                               "pill_bg": theme.BG_INPUT}}) for i in range(6)]

root = ctk.CTk()
root.geometry("520x400+40+40")
elegidas = []
tabla = PillTable(root, COLS, on_select=elegidas.append, multiselect=True)
tabla.pack(fill="both", expand=True)
root.update()
tabla.set_rows(filas)
root.update()

hay = tabla._canvas.winfo_width()
ok(sum(tabla._anchos) <= hay, f"las tres columnas caben en {hay}px: {tabla._anchos}")
ok(not tabla._hsb.winfo_ismapped(), "y sin scroll horizontal")
fuente = tabla._fuente(11)
ok(tabla._anchos[0] >= fuente.measure(CODIGO) + 12, f"el código se ve entero: {tabla._anchos[0]}")
celdas = tabla._filas[0]["items"]
ok(celdas[0]["visto"] == CODIGO, f"código sin «…»: {celdas[0]['visto']}")
ok(celdas[1]["visto"].endswith("…") and celdas[1]["texto"] == LARGO,
   f"el título largo se recorta pero se guarda entero: {celdas[1]['visto']}")
ok(tabla.row_values("r0") == [CODIGO, LARGO, "Aprobado"], "row_values da el texto entero")

# Más estrecha que los suelos: scroll horizontal, nada fuera de la vista
root.geometry("300x400")
root.update()
root.update()
ok(tabla._hsb.winfo_ismapped(), "sin sitio ni para los suelos: aparece el scroll horizontal")
ok(sum(tabla._anchos) > tabla._canvas.winfo_width(), "y las columnas siguen con su suelo")
root.geometry("900x400")
root.update()
root.update()
ok(not tabla._hsb.winfo_ismapped() and tabla._anchos[1] > 300,
   f"con sitio de sobra, lo que sobra a la que estira: {tabla._anchos}")

# Selección: clic, ctrl+clic y mayús+clic
tabla.select("r1")
tabla.select("r3", mode="toggle")
ok(tabla.selected_ids() == ["r1", "r3"] and elegidas[-1] == "r3", f"ctrl+clic suma: {tabla.selected_ids()}")
tabla.select("r5", mode="range")
ok(set(tabla.selected_ids()) == {"r1", "r3", "r4", "r5"}, f"mayús+clic, el rango: {tabla.selected_ids()}")
tabla.select("r0")
ok(tabla.selected_ids() == ["r0"], "un clic normal deja solo esa")
ok(tabla._canvas.itemcget(tabla._filas[0]["rect"], "fill") == theme.ACCENT_SOFT, "y se pinta seleccionada")

# Orden: la flecha va en la cabecera
tabla.set_sort_arrow("Estado", False)
root.update()
ok(tabla._cabecera[2][0].endswith("▼"), f"flecha de orden: {tabla._cabecera[2]}")

tabla.clear()
ok(tabla.row_values("r0") == [] and tabla.selected_ids() == [], "clear la deja vacía")
root.destroy()
print("FALLOS:", fallos)
