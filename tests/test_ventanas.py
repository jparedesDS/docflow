# -*- coding: utf-8 -*-
"""Toda ventana emergente sale entera y centrada en el escritorio.

    .venv\\Scripts\\python.exe tests\\test_ventanas.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk  # noqa: E402

from gui.widgets import ventanas  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


ventanas.instalar()
ventanas.instalar()                        # dos veces no engancha dos veces
AREA = (100, 50, 1466, 778)                 # un portátil de 1366x728 útiles, desplazado
ventanas.area_trabajo = lambda win: AREA
IZQ, ARRIBA, DER, ABAJO = AREA

root = ctk.CTk()
root.geometry("400x300+0+0")
ventanas_abiertas = {}


def abrir():
    # Más alta que el escritorio: se recorta a lo que cabe, también su mínimo
    alta = ctk.CTkToplevel(root)
    alta.geometry("900x1200")
    alta.minsize(600, 900)
    # Con más contenido que tamaño: crece hasta que se ve todo
    llena = ctk.CTkToplevel(root)
    llena.geometry("300x200")
    ctk.CTkFrame(llena, width=500, height=400).pack()
    # Sin tamaño propio: se coloca sin congelar su tamaño
    natural = ctk.CTkToplevel(root)
    ctk.CTkFrame(natural, width=320, height=160).pack()
    # Un globo sin marco se queda donde lo pusieron
    globo = ctk.CTkToplevel(root)
    globo.overrideredirect(True)
    globo.geometry("120x40+5+5")
    ventanas_abiertas.update(alta=alta, llena=llena, natural=natural, globo=globo)
    root.after(800, comprobar)


def dentro(win, nombre):
    x, y = win.winfo_x(), win.winfo_y()
    w, h = win.winfo_width(), win.winfo_height()
    ok(x >= IZQ and y >= ARRIBA, f"{nombre}: empieza dentro del escritorio ({x},{y})")
    ok(x + w + ventanas.MARCO_ANCHO <= DER and y + h + ventanas.MARCO_ALTO <= ABAJO,
       f"{nombre}: acaba dentro del escritorio ({x},{y} {w}x{h})")
    centro_x = x + (w + ventanas.MARCO_ANCHO) / 2
    ok(abs(centro_x - (IZQ + DER) / 2) <= 2, f"{nombre}: centrada en horizontal ({centro_x})")
    return w, h


def comprobar():
    v = ventanas_abiertas
    w, h = dentro(v["alta"], "alta")
    ok(w == 900 and h == ABAJO - ARRIBA - 2 * ventanas.MARGEN - ventanas.MARCO_ALTO,
       f"la alta se recorta a la altura útil: {w}x{h}")
    ok(v["alta"]._min_height <= h, f"y su mínimo ya no obliga a salirse: {v['alta']._min_height}")
    w, h = dentro(v["llena"], "llena")
    ok(w >= 500 and h >= 400, f"la que no cabía crece hasta su contenido: {w}x{h}")
    w, h = dentro(v["natural"], "natural")
    ok(not getattr(v["natural"], "_encaje_tamano", False), "la natural no se congela a un tamaño fijo")
    ok((v["globo"].winfo_x(), v["globo"].winfo_y()) == (5, 5), "el globo sin marco no se mueve")
    root.quit()


root.after(200, abrir)
root.after(15000, root.quit)
root.mainloop()
print("FALLOS:", fallos)
