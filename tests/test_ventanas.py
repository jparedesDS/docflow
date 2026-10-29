# -*- coding: utf-8 -*-
"""Toda ventana emergente sale entera y centrada en el escritorio, y aparece
sin saltos: oculta mientras se construye, ya colocada y con un fundido.

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
# Tk y el escritorio miden en píxeles de pantalla; geometry() de CustomTkinter,
# sin escalar. Con Windows a 125 % (el escritorio remoto) 900 son 1125 px, y el
# marco de Windows también crece: todo se compara a la escala de la sesión.
ESCALA = ventanas.escala(root)
MARGEN, MARCO_ANCHO, MARCO_ALTO = ventanas.bordes(root)
ventanas_abiertas = {}
nada_mas_crear = {}


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
    # La que se oculta a propósito (quien la creó la quiere oculta) no se enseña
    oculta = ctk.CTkToplevel(root)
    oculta.withdraw()
    ventanas_abiertas.update(alta=alta, llena=llena, natural=natural, globo=globo, oculta=oculta)
    nada_mas_crear["estado"] = alta.state()
    root.after(800, comprobar)


def dentro(win, nombre):
    """Tamaño en píxeles de pantalla, tras comprobar que cabe y va centrada."""
    win.update_idletasks()
    x, y = win.winfo_x(), win.winfo_y()
    w, h = win.winfo_width(), win.winfo_height()
    ok(x >= IZQ and y >= ARRIBA, f"{nombre}: empieza dentro del escritorio ({x},{y})")
    ok(x + w + MARCO_ANCHO <= DER and y + h + MARCO_ALTO <= ABAJO,
       f"{nombre}: acaba dentro del escritorio ({x},{y} {w}x{h})")
    centro_x = x + (w + MARCO_ANCHO) / 2
    ok(abs(centro_x - (IZQ + DER) / 2) <= 2, f"{nombre}: centrada en horizontal ({centro_x})")
    return w, h


def logico(win):
    """(ancho, alto) sin escalar, como los pide geometry()."""
    w, h = win.geometry().split("+")[0].split("x")
    return int(w), int(h)


def comprobar():
    v = ventanas_abiertas
    w, h = dentro(v["alta"], "alta")
    util = ABAJO - ARRIBA - 2 * MARGEN - MARCO_ALTO          # en píxeles de pantalla
    # Sin escalar, exacto; en pantalla, lo útil salvo lo que se pierde al
    # redondear a un tamaño sin escalar (menos de un paso de escala)
    ok(logico(v["alta"]) == (900, int(util / ESCALA)) and w == round(900 * ESCALA)
       and util - ESCALA < h <= util,
       f"la alta se recorta a la altura útil: {w}x{h} ({logico(v['alta'])} a escala {ESCALA}, útil {util})")
    ok(v["alta"]._min_height * ESCALA <= h, f"y su mínimo ya no obliga a salirse: {v['alta']._min_height}")
    w, h = dentro(v["llena"], "llena")
    ok(w >= 500 and h >= 400, f"la que no cabía crece hasta su contenido: {w}x{h}")
    w, h = dentro(v["natural"], "natural")
    ok(not getattr(v["natural"], "_encaje_tamano", False), "la natural no se congela a un tamaño fijo")
    ok((v["globo"].winfo_x(), v["globo"].winfo_y()) == (5, 5), "el globo sin marco no se mueve")
    ok(nada_mas_crear.get("estado") == "withdrawn", f"nace oculta: {nada_mas_crear}")
    for nombre in ("alta", "llena", "natural", "globo"):
        win = v[nombre]
        ok(win.state() == "normal" and float(win.attributes("-alpha")) >= 0.99,
           f"{nombre}: a la vista y opaca tras el fundido ({win.state()}, {win.attributes('-alpha')})")
    ok(v["oculta"].state() == "withdrawn", "la que se ocultó a propósito sigue oculta")
    v["oculta"].deiconify()
    ok(v["oculta"].state() == "normal", "y se enseña cuando quien la usa lo pide")

    # La principal (login, app) pide su tamaño sin escalar: más grande que el
    # escritorio, se recorta a lo que cabe (ya escalada) y se centra
    ventanas.encajar_principal(root, 1600, 1000)
    w, h = dentro(root, "principal grande")
    ok(DER - IZQ - MARCO_ANCHO - ESCALA < w and ABAJO - ARRIBA - MARCO_ALTO - ESCALA < h,
       f"la principal grande ocupa el escritorio: {w}x{h}")
    # Si cabe, con su tamaño (escalado) y en la posición que traía
    ventanas.encajar_principal(root, 400, 300, IZQ + 10, ARRIBA + 10)
    root.update_idletasks()
    ok((root.winfo_x(), root.winfo_y()) == (IZQ + 10, ARRIBA + 10) and logico(root) == (400, 300)
       and (root.winfo_width(), root.winfo_height()) == (round(400 * ESCALA), round(300 * ESCALA)),
       f"la principal que cabe se queda donde estaba: {root.wm_geometry()}")
    # Y si al escalarla ya no cabe donde estaba, se recoloca
    ventanas.encajar_principal(root, 400, 300, DER - MARCO_ANCHO - 400, ARRIBA)
    dentro(root, "principal en el borde")

    # Cambio de sección: lo de dentro cambia y no queda ninguna capa encima
    marco = ctk.CTkFrame(root)
    marco.pack(fill="both", expand=True)
    hecho = []
    ventanas.transicion(root, marco, lambda: hecho.append(1))
    ok(hecho == [1], "la transición hace el cambio")
    root.after(400, lambda: fin_transicion(len(root.winfo_children())))


def fin_transicion(antes):
    capas = [w for w in root.winfo_children() if w.winfo_class() == "Toplevel" and w.overrideredirect()
             and not isinstance(w, ctk.CTkToplevel)]
    ok(not capas, f"y la foto del fundido se va sola: {capas}")
    root.quit()


root.after(200, abrir)
root.after(15000, root.quit)
root.mainloop()
print("FALLOS:", fallos)
