# -*- coding: utf-8 -*-
"""Tablas: el recorte con «…» no puede comerse ni un dato.

El texto que no cabe se corta para enseñarlo, pero el valor entero tiene que
seguir ahí: se copia, se lee para mandar una reclamación y se reescribe cuando
alguien marca una casilla. La primera versión del recorte se comía esos cambios
al redimensionar, que es lo que comprueba la segunda mitad de este fichero.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import customtkinter as ctk  # noqa: E402

from gui.widgets.table import DataTable  # noqa: E402

fallos = 0


def comprobar(condicion: bool, texto: str) -> None:
    global fallos
    if condicion:
        print(f"  OK    {texto}")
    else:
        fallos += 1
        print(f"  FALLO {texto}")


LARGO = "PRESERVATION AND STORAGE PROCEDURE FOR RESTRICTION ORIFICES"

root = ctk.CTk()
root.withdraw()
tabla = DataTable(root, columns=["Marca", "Título"])
tabla.pack(fill="both", expand=True)
tabla.add_row(["☐", LARGO], iid="d0")
tabla.add_row(["☑", "OTRO DOCUMENTO"], iid="d1")
tabla.set_columns_width({"Marca": 40, "Título": 120})
root.update_idletasks()
tabla.recortar_celdas()
root.update()

pintado = tabla.tree.item("d0", "values")[1]
comprobar(pintado != LARGO and pintado.endswith("…"), "el título que no cabe sale con «…»")
comprobar(tabla.row_values("d0")[1] == LARGO, "row_values devuelve el título entero")
comprobar(tabla.cell_value("d0", 1) == LARGO, "cell_value devuelve el título entero")

# Marcar la casilla de la primera fila, como hace Reclamaciones
valores = list(tabla.row_values("d0"))
valores[0] = "☑"
tabla.set_values("d0", valores)
root.update()
comprobar(tabla.row_values("d0")[0] == "☑", "la marca se guarda")
comprobar(tabla.row_values("d0")[1] == LARGO, "y el título sigue entero")

# El ajuste de anchos vuelve a recortar: el cambio NO puede perderse
tabla.recortar_celdas()
root.update()
comprobar(tabla.row_values("d0")[0] == "☑", "la marca sobrevive a un recorte posterior")
comprobar(tabla.tree.item("d0", "values")[0] == "☑", "y se sigue viendo marcada")

# Lo mismo al cambiar el ancho de la columna, que es lo que pasa al maximizar.
# 560 px son de sobra para el título (mide 514).
tabla.set_columns_width({"Título": 560})
root.update_idletasks()
tabla.recortar_celdas()
root.update()
comprobar(tabla.tree.item("d0", "values")[1] == LARGO,
          "si la columna se ensancha, vuelve a verse el título entero")
comprobar(tabla.row_values("d0")[0] == "☑", "y la marca sigue puesta")

# Una fila corta no se toca
comprobar(tabla.tree.item("d1", "values")[1] == "OTRO DOCUMENTO",
          "lo que cabe se deja como está")

# Una fila con menos valores que columnas se deja en paz: recortarla con zip()
# se comería las columnas que faltan
tabla.add_row(["☐"], iid="d2")
tabla.set_columns_width({"Título": 100})
root.update_idletasks()
tabla.recortar_celdas()
root.update()
comprobar(list(tabla.tree.item("d2", "values")) == ["☐"],
          "una fila incompleta no se reescribe")

try:
    root.destroy()
except Exception:  # noqa: BLE001
    pass

print(f"FALLOS: {fallos}")
sys.exit(1 if fallos else 0)
