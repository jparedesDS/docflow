# -*- coding: utf-8 -*-
"""ui.en_ui — volver al hilo de la interfaz sin romperse si ya no hay ventana.

Lo que se comprueba es el caso feo: el hilo termina la consulta cuando el
usuario ya ha cerrado el diálogo. Antes eso dejaba una traza de Tcl en el log;
ahora el resultado se descarta y no pasa nada.
"""
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import customtkinter as ctk  # noqa: E402

from gui.widgets import ui  # noqa: E402

fallos = 0


def comprobar(condicion: bool, texto: str) -> None:
    global fallos
    if condicion:
        print(f"  OK    {texto}")
    else:
        fallos += 1
        print(f"  FALLO {texto}")


root = ctk.CTk()
root.withdraw()

# 1) Con la ventana viva, la función se ejecuta en el hilo de la interfaz
marca = []
ui.en_ui(root, lambda: marca.append("pintado"))
root.update()
comprobar(marca == ["pintado"], "con la ventana viva, se ejecuta")

# 2) Con argumentos
suma = []
ui.en_ui(root, lambda a, b: suma.append(a + b), 2, 3)
root.update()
comprobar(suma == [5], "los argumentos llegan a la función")

# 3) El widget se destruye antes de que llegue el resultado: ni error ni pintura
marco = ctk.CTkFrame(root)
marco.pack()
root.update()
tardio = []
marco.destroy()
try:
    ui.en_ui(marco, lambda: tardio.append("tarde"))
    root.update()
    exploto = False
except Exception:  # noqa: BLE001
    exploto = True
comprobar(not exploto, "sobre un widget destruido no lanza excepción")
comprobar(tardio == [], "sobre un widget destruido no ejecuta nada")

# 4) Se destruye entre que se programa y se ejecuta: tampoco se pinta
otro = ctk.CTkFrame(root)
otro.pack()
root.update()
entre = []
ui.en_ui(otro, lambda: entre.append("tarde"))
otro.destroy()
root.update()
comprobar(entre == [], "si se destruye antes de ejecutarse, se descarta")

# 5) Llamado desde un hilo, que es para lo que existe. Aquí hace falta el bucle
#    de Tk de verdad: sin él, Tkinter no acepta encargos de otros hilos.
desde_hilo = []


def trabajo() -> None:
    ui.en_ui(root, lambda: (desde_hilo.append("ok"), root.quit()))


root.after(50, lambda: threading.Thread(target=trabajo, daemon=True).start())
root.after(3000, root.quit)          # por si algo se atasca, no colgar la prueba
root.mainloop()
comprobar(desde_hilo == ["ok"], "desde un hilo de carga, se ejecuta")

try:
    root.destroy()
except Exception:  # noqa: BLE001
    pass

print(f"FALLOS: {fallos}")
sys.exit(1 if fallos else 0)
