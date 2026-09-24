# -*- coding: utf-8 -*-
"""Prueba de humo: construye TODAS las vistas en una ventana oculta.

Caza los fallos de construcción —un widget con un argumento que no existe, un
atributo que falta, un import dentro de un método— sin tener que abrir la app y
recorrerla a mano. No comprueba comportamiento: solo que cada sección se levanta.

Los diálogos se neutralizan para que ninguno bloquee, la red se acorta a dos
segundos para que lo que consulte IMAP o el ERP falle rápido, y se callan las
excepciones de los hilos de carga: aquí no hay bucle de Tk, así que su `after`
siempre protesta y no significa nada.
"""
import logging
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
socket.setdefaulttimeout(2)
threading.excepthook = lambda args: None
logging.disable(logging.CRITICAL)

from tkinter import messagebox  # noqa: E402

for _nombre in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, _nombre, lambda *a, **k: None)
for _nombre in ("askyesno", "askokcancel", "askretrycancel"):
    setattr(messagebox, _nombre, lambda *a, **k: False)

import customtkinter as ctk  # noqa: E402

from core import auth, session  # noqa: E402

auth.initialize()
usuario = auth.get_user("JP") or {"initials": "JP", "nombre": "el administrador", "role": "admin"}
session.set_user(usuario)

root = ctk.CTk()
root.withdraw()
contenedor = ctk.CTkFrame(root)
contenedor.pack(fill="both", expand=True)


def noop(*a, **k):
    return None


VISTAS = [
    ("home", "gui.views.home", "HomeView", {"on_navigate": noop}),
    ("agenda", "gui.views.agenda", "AgendaView", {}),
    ("apertura", "gui.views.apertura", "AperturaView", {}),
    ("portadas", "gui.views.portadas", "PortadasView", {}),
    ("vpr", "gui.views.vpr", "VprView", {}),
    ("ofertas", "gui.views.ofertas", "OfertasView", {}),
    ("pedidos", "gui.views.pedidos", "PedidosView", {"on_open_documentos": noop}),
    ("documentos", "gui.views.documentos", "DocumentosView", {"on_navigate": noop}),
    ("almacen", "gui.views.almacen", "AlmacenView", {"on_open_pedido": noop}),
    ("compras", "gui.views.compras", "ComprasView", {"on_open_pedido": noop}),
    ("calidad", "gui.views.calidad", "CalidadView", {"on_open_pedido": noop}),
    ("produccion", "gui.views.produccion", "ProduccionView", {"on_open_pedido": noop}),
    ("administracion", "gui.views.administracion", "AdministracionView",
     {"on_open_pedido": noop}),
    ("inbox", "gui.views.inbox", "InboxView", {}),
    ("devoluciones", "gui.views.devoluciones", "DevolucionesView", {}),
    ("reclamaciones", "gui.views.reclamaciones", "ReclamacionesView", {}),
    ("docusign", "gui.views.docusign", "DocusignView", {}),
    ("informes", "gui.views.informes", "InformesView", {}),
    ("reportes", "gui.views.reportes", "ReportesView", {}),
    ("ajustes", "gui.views.ajustes", "AjustesView", {"on_restart": noop}),
]

# Diálogos que viven aparte de su vista y que nadie construiría en el recorrido
# normal: se levantan con lo mínimo para que un fallo de construcción salte aquí.
DIALOGOS = [
    ("devolución manual", "gui.views.devoluciones", "ManualDevolucionWindow", (root,)),
    ("preview devolución", "gui.views.devoluciones", "PreviewWindow", (root, "1")),
    # buscar=False: se monta la ventana, pero no se llama a eGesDoc
    ("comentados del PO", "gui.views.pedidos", "FinalesWindow",
     (root, "P-26/001", "1000100010", False)),
]

bien, fallos = [], []
for clave, modulo, clase, kwargs in VISTAS:
    t0 = time.perf_counter()
    try:
        vista = getattr(__import__(modulo, fromlist=[clase]), clase)(contenedor, **kwargs)
        vista.pack(fill="both", expand=True)
        root.update_idletasks()
        root.update()
        vista.destroy()
        bien.append((clave, (time.perf_counter() - t0) * 1000))
    except Exception:  # noqa: BLE001
        fallos.append((clave, traceback.format_exc().strip().splitlines()[-1]))

for clave, modulo, clase, args in DIALOGOS:
    t0 = time.perf_counter()
    try:
        dialogo = getattr(__import__(modulo, fromlist=[clase]), clase)(*args)
        root.update_idletasks()
        root.update()
        dialogo.destroy()
        bien.append((clave, (time.perf_counter() - t0) * 1000))
    except Exception:  # noqa: BLE001
        fallos.append((clave, traceback.format_exc().strip().splitlines()[-1]))

print(f"Vistas levantadas: {len(bien)}/{len(VISTAS) + len(DIALOGOS)}")
for clave, ms in bien:
    print(f"  {clave:15} {ms:6.0f} ms")
for clave, error in fallos:
    print(f"  {clave:15} {error}")
print(f"FALLOS: {len(fallos)}")

try:
    root.destroy()
except Exception:  # noqa: BLE001
    pass
sys.exit(1 if fallos else 0)
