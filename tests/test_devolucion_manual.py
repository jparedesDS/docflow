# -*- coding: utf-8 -*-
"""Devolución manual: al escribir el pedido se completan cliente, material y
PO, también si el pedido aún no tiene documentos (solo está en la consulta de
pedidos del ERP); y si no existe, se dice. Datos inventados.

    .venv\\Scripts\\python.exe tests\\test_devolucion_manual.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk  # noqa: E402

from core.services import erp, monitoring  # noqa: E402
from gui.views.devoluciones import comun  # noqa: E402
from gui.views.devoluciones.manual import ManualDevolucionWindow  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


monitoring.get_monitoring_data = lambda: [
    {"Nº Pedido": "P-99/001-S00", "Cliente": "CLIENTE UNO", "Material": "Caudal", "Nº PO": "PO-1"}]
erp.consulta = lambda pedido="": [
    {"Nº Pedido": "P-99/001-S00", "Cliente": "CLIENTE UNO", "Tipo Equipo": "Orificios", "Nº Referencia": "PO-1"},
    {"Nº Pedido": "PA-99/112", "Cliente": "CLIENTE ALMACÉN ", "Tipo Equipo": "Vainas", "Nº Referencia": "REF/01"}]

ok(comun._lookup_pedido("P-99/001") == {"cliente": "CLIENTE UNO", "material": "Caudal", "po": "PO-1"},
   "con documentos: del seguimiento, como siempre")
ok(comun._lookup_pedido("pa99112") == {"cliente": "CLIENTE ALMACÉN", "material": "Vainas", "po": "REF/01"},
   "sin documentos: de la consulta de pedidos")
ok(comun._lookup_pedido("PA-99/999") is None, "uno que no existe")

root = ctk.CTk()
root.withdraw()
win = ManualDevolucionWindow(root)


def esperar(cond, segundos=5):
    """Deja correr el bucle de Tk hasta que se cumpla `cond`: lo que vuelve de
    un hilo entra con after(), y eso solo se atiende con el bucle en marcha."""
    fin = time.monotonic() + segundos

    def mirar():
        if cond() or time.monotonic() > fin:
            root.quit()
        else:
            root.after(20, mirar)
    root.after(20, mirar)
    root.mainloop()


win.ent_pedido.insert(0, "PA-99/112")
win._autofill_from_pedido()
esperar(lambda: win.ent_cliente.get())
ok(win.ent_cliente.get() == "CLIENTE ALMACÉN" and win.ent_material.get() == "Vainas"
   and win.ent_po.get() == "REF/01", f"la ventana se rellena: {win.ent_cliente.get()!r}")
ok(win.lbl_status.cget("text").startswith("✓"), f"y lo dice: {win.lbl_status.cget('text')}")

win.ent_pedido.delete(0, "end")
win.ent_pedido.insert(0, "PA-99/999")
win._autofill_from_pedido()
esperar(lambda: "no está en el ERP" in win.lbl_status.cget("text"))
ok("no está en el ERP" in win.lbl_status.cget("text"), f"si no existe, avisa: {win.lbl_status.cget('text')}")
win.destroy()
root.destroy()

print("FALLOS:", fallos)
