# -*- coding: utf-8 -*-
"""La lista de sobres de DocuSign, dibujada en un lienzo: pinta cada sobre, un
clic elige el de debajo (también tras desplazarla), la selección se resalta y
sin sobres lo dice. Sobres inventados; sin la API de DocuSign.

    .venv\\Scripts\\python.exe tests\\test_docusign_lista.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk  # noqa: E402

from gui import theme  # noqa: E402
from gui.views import docusign as D  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


SOBRES = [{"id": f"s{i}", "subject": f"Contrato de prueba {i}" + (" muy largo" * 12 if i == 1 else ""),
           "status": "completed" if i % 2 else "sent", "sender_name": "Persona Inventada",
           "sent_at": "2026-10-0%dT10:00:00Z" % (i % 9 + 1),
           "recipients": [{"name": "Ana Ejemplo", "status": "completed"}] * (8 if i == 2 else 1)}
          for i in range(30)]

root = ctk.CTk()
root.geometry("520x500+0+0")
elegidos = []
try:
    lista = D._ListaSobres(root, on_select=elegidos.append)
    lista.pack(fill="both", expand=True)
    root.update()
    lista.mostrar(SOBRES, seleccionado=None)
    root.update()
    c = lista.canvas

    textos = [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]
    ok(len(lista._cajas) == 30, f"una tarjeta por sobre: {len(lista._cajas)}")
    ok("Contrato de prueba 0" in textos and "Persona Inventada" in textos,
       "con el asunto y el remitente")
    largo = next(t for t in textos if t.startswith("Contrato de prueba 1"))
    ok(largo.endswith("…") and len(largo) < len(SOBRES[1]["subject"]),
       f"el asunto que no cabe se remata con «…»: {largo!r}")
    ok("+2" in textos, "más de 6 firmantes: los que sobran se cuentan")

    # Un clic en la segunda tarjeta elige ese sobre
    y0, y1, _ = lista._cajas[1]
    lista._clic(NS(x=50, y=(y0 + y1) // 2))
    ok([e["id"] for e in elegidos] == ["s1"], f"el clic elige el sobre de debajo: {elegidos}")

    # Desplazada la lista, el clic sigue eligiendo el de debajo
    c.yview_moveto(0.5)
    root.update()
    arriba = int(c.canvasy(0))
    debajo = next(i for i, (a, b, _) in enumerate(lista._cajas) if a <= arriba + 40 <= b)
    lista._clic(NS(x=50, y=40))
    ok(elegidos[-1]["id"] == f"s{debajo}", f"desplazada, elige el de debajo: {elegidos[-1]['id']}")

    # La selección se resalta con el color de acento
    lista.seleccionar("s3")
    root.update()
    bordes = [c.itemcget(i, "outline") for i in c.find_all() if c.type(i) == "polygon"]
    ok(bordes.count(D.ACCENT_DS) == 1, "solo el seleccionado lleva el borde de acento")
    rellenos = [c.itemcget(i, "fill") for i in c.find_all() if c.type(i) == "polygon"]
    ok(rellenos.count(theme.ACCENT_SOFT) == 1, "y su fondo")

    # Sin sobres, lo dice
    lista.mostrar([], seleccionado=None, vacio="No se encontraron sobres")
    root.update()
    textos = [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]
    ok(any("No se encontraron sobres" in t for t in textos), f"sin sobres, el aviso: {textos}")
    lista._clic(NS(x=50, y=60))
    ok(len(elegidos) == 2, "y un clic ahí no elige nada")
finally:
    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass

print("FALLOS:", fallos)
