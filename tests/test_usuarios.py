# -*- coding: utf-8 -*-
"""Usuarios y permisos: dar y quitar secciones a las cuentas.

Trabaja sobre un users.json temporal con cuentas inventadas: el de verdad no
se toca.

    .venv\\Scripts\\python.exe tests\\test_usuarios.py
"""
import logging
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.CRITICAL)

from tkinter import messagebox  # noqa: E402

import customtkinter as ctk  # noqa: E402

from core import auth, session  # noqa: E402
from gui import navegacion  # noqa: E402
from gui.app import DocFlowLiteApp  # noqa: E402

tmp = Path(tempfile.mkdtemp())
auth.USERS_FILE = str(tmp / "users.json")          # nunca el de verdad

from gui.views import usuarios as U  # noqa: E402
from gui.widgets import ui  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


errores = []
messagebox.showerror = lambda titulo, texto, **k: errores.append(texto)
respuesta = {"confirmar": True}
ui.confirm = lambda *a, **k: respuesta["confirmar"]

# ── Todas las secciones del menú se pueden dar y quitar ─────────────────────
del_menu = {it["key"] for _, items in navegacion.grupos_de_permisos() for it in items}
ok(del_menu == set(auth.SECTION_KEYS),
   f"menú y permisos son las mismas secciones: faltan {del_menu - set(auth.SECTION_KEYS)}, "
   f"sobran {set(auth.SECTION_KEYS) - del_menu}")
ok(DocFlowLiteApp.NAV_LAYOUT is navegacion.NAV_LAYOUT, "el menú sale de gui/navegacion.py")
ok({"portadas", "vpr"} <= set(auth.SECTION_KEYS), "Portadas y VPR ya se pueden dar")
ok("home" not in del_menu, "Inicio lo ve todo el mundo: no se da ni se quita")

# ── Cuentas inventadas ──────────────────────────────────────────────────────
auth.initialize()                                   # crea el admin


def solo(**permisos):
    return {k: permisos.get(k, "none") for k in auth.SECTION_KEYS}


auth.create_user("AA", "Ana Alba", permisos=solo(documentos="gestionar", pedidos="ver"))
auth.create_user("BB", "Beto Bravo", permisos=solo(inbox="ver"))
# Una cuenta de antes de que existieran Portadas y VPR
datos = auth._load()
for u in datos["users"]:
    if u["initials"] == "BB":
        del u["permisos"]["portadas"], u["permisos"]["vpr"]
auth._save(datos)
auth.initialize()
bb = auth.get_user("BB")
ok(bb["permisos"]["portadas"] == "none" and bb["permisos"]["vpr"] == "none",
   f"una sección nueva llega cerrada a las cuentas que ya existen: {bb['permisos']}")
ok(not auth.can_view(bb, "portadas") and auth.can_view(auth.get_user("JP"), "portadas"),
   "y solo la ve quien tiene permiso (el admin, todas)")

ok(U.resumen({"documentos": "gestionar", "pedidos": "ver"}) == "Ve 1 · Gestiona 1", U.resumen({"a": 1}))
ok(U.resumen({}) == "Sin acceso a ninguna sección", U.resumen({}))
ok(U.permisos_completos({"documentos": "raro"})["documentos"] == "none", "lo que no se entiende, sin acceso")

# ── La vista ────────────────────────────────────────────────────────────────
session.set_user({"initials": "BB", "nombre": "Beto"})
root = ctk.CTk()
root.withdraw()
vista = U.UsuariosView(root)
ok(not hasattr(vista, "lista"), "quien no es admin no ve las cuentas")
vista.destroy()

session.set_user(auth.get_user("JP"))
vista = U.UsuariosView(root)
vista.pack(fill="both", expand=True)
root.update()
ok([u["initials"] for u in vista._usuarios][0] == "JP", "el admin va primero en la lista")
ok(vista._sel == "AA", f"se abre la primera cuenta que no es admin: {vista._sel}")
ok(vista.btn_guardar.cget("state") == "disabled", "sin cambios no se puede guardar")
ok(set(vista._segs) == set(auth.SECTION_KEYS), "un selector por sección")
ok(vista._segs["documentos"].get() == "Gestionar" and vista._segs["almacen"].get() == "Sin acceso",
   "cada selector enseña lo que tiene la cuenta")

# Quitar una sección y dar otra
vista._poner(["documentos"], "none")
vista._poner(["portadas"], "ver")
ok(vista.btn_guardar.cget("state") == "normal", "con cambios, se puede guardar")
ok(auth.get_user("AA")["permisos"]["documentos"] == "gestionar", "y no se guarda hasta pulsar")
vista._guardar()
aa = auth.get_user("AA")["permisos"]
ok(aa["documentos"] == "none" and aa["portadas"] == "ver" and aa["pedidos"] == "ver",
   f"guardado: quita Documentos, da Portadas y deja lo demás: {aa}")
ok(vista.btn_guardar.cget("state") == "disabled", "y vuelve a estar sin cambios")

# Un departamento entero, y todas
grupo, claves = next((s, c) for s, c in vista._segs_grupo if "devoluciones" in c)
vista._poner(claves, "ver")
ok(all(vista._borrador[k] == "ver" for k in claves) and grupo.get() == "Ver",
   "el selector del departamento cambia sus secciones")
vista._poner(["devoluciones"], "gestionar")
ok(grupo.get() == "", "si dentro hay de todo, el del departamento no marca ninguno")
vista._poner(auth.SECTION_KEYS, "none")
ok(U.resumen(vista._borrador) == "Sin acceso a ninguna sección", "«Todas: Sin acceso»")

# Cambiar de cuenta con cambios pendientes
respuesta["confirmar"] = False
vista._pedir("BB")
ok(vista._sel == "AA", "si no se quiere descartar, se queda en la cuenta")
respuesta["confirmar"] = True
vista._pedir("BB")
ok(vista._sel == "BB" and auth.get_user("AA")["permisos"]["pedidos"] == "ver",
   "descartando, cambia de cuenta y lo descartado no se guarda")

# Copiar de otra
vista._copiar(auth.get_user("AA"), type("M", (), {"set": lambda *a: None})())
vista._guardar()
ok(U.permisos_completos(auth.get_user("BB")["permisos"]) == U.permisos_completos(auth.get_user("AA")["permisos"]),
   "copiar los permisos de otra cuenta")

# El admin no se recorta
vista._pedir("JP")
ok(not vista._segs, "la ficha del admin no tiene selectores")

# Cuenta nueva: empieza sin acceso a nada
vista._nueva_cuenta()
ok(vista._nueva and all(v == "none" for v in vista._borrador.values()), "una cuenta nueva empieza cerrada")
vista.e_ini.insert(0, "cc")
vista.e_nombre.insert(0, "Carla Cid")
vista._poner(["agenda"], "ver")
vista._guardar()
cc = auth.get_user("CC")
ok(cc and cc["nombre"] == "Carla Cid" and cc["must_change_password"], f"creada, y cambiará la contraseña: {cc}")
ok(cc and U.resumen(cc["permisos"]) == "Ve 1", f"solo con lo que se le dio: {cc and cc['permisos']}")
ok(vista._sel == "CC" and not vista._nueva, "y queda abierta")

vista._nueva_cuenta()
vista.e_ini.insert(0, "AA")
vista._guardar()
ok(errores and "Ya existe" in errores[-1], f"no se repiten iniciales: {errores}")
vista._descartar()

# Eliminar
vista._pedir("CC")
vista._eliminar()
ok(auth.get_user("CC") is None and vista._sel != "CC", "eliminada")
ok(auth.delete_user("JP")[0] is False, "la del admin no se puede eliminar")

root.destroy()
shutil.rmtree(tmp, ignore_errors=True)
print("FALLOS:", fallos)
