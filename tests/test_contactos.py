# -*- coding: utf-8 -*-
"""Elegir destinatarios de un clic, en Devoluciones y Reclamaciones.

    .venv\\Scripts\\python.exe tests\\test_contactos.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from core import organizacion
from gui import theme
from gui.widgets import contactos

fallos = 0


def ok(cond, msg):
    global fallos
    if cond:
        print("  OK   ", msg)
    else:
        fallos += 1
        print("  FALLO", msg)


EQUIPO = {
    "AC": {"nombre": "Ana Calvo", "emails": ["ana-calvo@eipsa.es"]},
    "LM": {"nombre": "Laura Mínguez", "emails": ["laura-minguez@eipsa.es"]},
    "JM": {"nombre": "Jesus Martinez", "emails": ["jesus-martinez@eipsa.es"]},
    "JP": {"nombre": "Jose Paredes", "emails": ["documentacion@eipsa.es",
                                                "jose-paredes@eipsa.es"]},
    "SN": {"nombre": "Sin Correo", "emails": []},
}

equipo_real = dict(organizacion.equipo)
organizacion.equipo.clear()
organizacion.equipo.update(EQUIPO)

root = ctk.CTk()
root.geometry("900x500")

try:
    # ── La lista de contactos ────────────────────────────────────────────────
    gente = contactos.contactos()
    ok([c["ini"] for c in gente] == ["AC", "JM", "JP", "LM"],
       f"salen ordenados por nombre y sin quien no tiene correo: {[c['ini'] for c in gente]}")
    ok(next(c for c in gente if c["ini"] == "JP")["email"] == "documentacion@eipsa.es",
       "de quien tiene dos correos se ofrece el primero")

    # ── Reconocer lo que ya hay en el campo ──────────────────────────────────
    ok(contactos._correo_de("Ana Calvo <ana-calvo@eipsa.es>") == "ana-calvo@eipsa.es",
       "el correo se saca igual de «Nombre <correo>» que pelado")
    ok(contactos._trozos("a@x.es; b@x.es , c@x.es") == ["a@x.es", "b@x.es", "c@x.es"],
       "el campo se parte por comas y por puntos y coma")

    # ── El selector sobre un campo ───────────────────────────────────────────
    ent = ctk.CTkEntry(root)
    ent.pack()
    boton = contactos.boton_contactos(root, ent, "Para")
    boton.pack()
    root.update()
    ok(str(boton.cget("state")) == "normal", "con equipo registrado el botón está vivo")

    sel = contactos.SelectorContactos(boton, ent, "Para")
    root.update()

    sel._alternar("ana-calvo@eipsa.es")
    ok(ent.get() == "ana-calvo@eipsa.es", f"un clic añade: {ent.get()!r}")
    sel._alternar("laura-minguez@eipsa.es")
    ok(ent.get() == "ana-calvo@eipsa.es, laura-minguez@eipsa.es",
       f"otro clic añade al lado, separado por comas: {ent.get()!r}")
    sel._alternar("ana-calvo@eipsa.es")
    ok(ent.get() == "laura-minguez@eipsa.es", f"y el clic de vuelta la quita: {ent.get()!r}")

    # No duplica a quien ya estaba escrito de otra forma
    ent.delete(0, "end")
    ent.insert(0, "Ana Calvo <ana-calvo@eipsa.es>, cliente@otra.com")
    sel._alternar("ana-calvo@eipsa.es")
    ok(ent.get() == "cliente@otra.com",
       f"reconoce «Nombre <correo>» y la quita sin tocar al cliente: {ent.get()!r}")
    sel._alternar("ana-calvo@eipsa.es")
    ok(ent.get() == "cliente@otra.com, ana-calvo@eipsa.es",
       f"y al volver a añadirla no duplica ni pierde al cliente: {ent.get()!r}")

    # ── La marca de quién está puesto ────────────────────────────────────────
    sel._pintar("")
    puestos = {f["email"] for f in sel._filas if f["tick"].cget("text")}
    ok(puestos == {"ana-calvo@eipsa.es"}, f"la lista marca a quien está en el campo: {puestos}")

    # ── El buscador ──────────────────────────────────────────────────────────
    ok([c["ini"] for c in sel._coinciden("lau")] == ["LM"], "busca por nombre")
    ok([c["ini"] for c in sel._coinciden("mínguez")] == ["LM"], "y con acentos o sin ellos")
    ok([c["ini"] for c in sel._coinciden("minguez")] == ["LM"], "busca sin acentos")
    ok([c["ini"] for c in sel._coinciden("JM")] == ["JM"], "busca por iniciales")
    ok([c["ini"] for c in sel._coinciden("documentacion")] == ["JP"], "y por correo")
    ok(sel._coinciden("zzz") == [], "y si no hay nadie no inventa")
    sel._pintar("zzz")
    ok(not sel._filas and sel.lista.winfo_children(),
       "sin coincidencias se pinta el estado vacío, no una lista a medias")

    # ── Los dos atajos ───────────────────────────────────────────────────────
    sel._limpiar()
    ok(ent.get() == "", "«Limpiar» vacía el campo")
    sel._todos()
    ok(contactos._trozos(ent.get()) == [c["email"] for c in gente],
       f"«Todo el equipo» mete a los cuatro: {ent.get()!r}")
    ent.delete(0, "end")
    ent.insert(0, "cliente@otra.com, ana-calvo@eipsa.es")
    sel._todos()
    ok(contactos._trozos(ent.get())[0] == "cliente@otra.com"
       and ent.get().count("ana-calvo@eipsa.es") == 1,
       f"y respeta lo que ya hay, sin duplicar: {ent.get()!r}")

    sel.destroy()
    root.update()

    # ── Sin nadie registrado el botón se apaga ───────────────────────────────
    organizacion.equipo.clear()
    ent2 = ctk.CTkEntry(root)
    boton2 = contactos.boton_contactos(root, ent2, "Copia")
    ok(str(boton2.cget("state")) == "disabled",
       "sin equipo registrado el botón sale apagado y no engaña")
    ok(contactos.contactos() == [], "y la lista está vacía")
finally:
    organizacion.equipo.clear()
    organizacion.equipo.update(equipo_real)
    root.update_idletasks()
    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass

# theme se importa para que un cambio de nombre en las constantes que usa el
# widget se vea aquí y no al abrir la ventana.
_ = theme.SPACE_2

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
