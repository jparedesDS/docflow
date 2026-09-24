# -*- coding: utf-8 -*-
"""Los datos de la empresa, fuera del código.

    docflow_env\\Scripts\\python.exe tests\\test_organizacion.py

Lo que se comprueba es que sacarlos del repositorio no ha roto nada: que lo que
se guarda se relee igual, que quien importó una tabla (media app hace
`from core.config import USERS`) ve los cambios sin reiniciar, y que una
instalación en blanco arranca sin datos en vez de petar.
"""
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import customtkinter as ctk  # noqa: E402

from core import organizacion  # noqa: E402
from gui.widgets.mapa import EquipoEditor, ListaEditor, MapaEditor  # noqa: E402

fallos = 0


def comprobar(condicion: bool, texto: str) -> None:
    global fallos
    if condicion:
        print(f"  OK    {texto}")
    else:
        fallos += 1
        print(f"  FALLO {texto}")


# Sobre un fichero de mentira: las tablas de verdad no se tocan
real = organizacion.ORGANIZACION_FILE
tmp = Path(tempfile.mkdtemp())
try:
    organizacion.ORGANIZACION_FILE = str(tmp / "organizacion.json")

    # ── En blanco ────────────────────────────────────────────────────────────
    organizacion.cargar()
    comprobar(organizacion.equipo == {} and organizacion.clientes == {},
              "una instalación nueva arranca sin datos, no con los de nadie")
    comprobar(organizacion.hay_datos() is False, "y lo dice")
    comprobar(organizacion.email_de("JP") == "", "preguntar por alguien que no está no rompe")

    # ── Guardar y releer ─────────────────────────────────────────────────────
    equipo = organizacion.equipo          # la misma referencia que usa config.USERS
    organizacion.guardar(equipo={"jp": {"nombre": "Quien Sea",
                                        "emails": "uno@empresa.com, dos@empresa.com"}},
                         clientes={"10002": "CLIENTE UNO"})
    comprobar(equipo is organizacion.equipo,
              "la tabla no se reemplaza: quien la importó sigue viendo la buena")
    comprobar(equipo.get("JP", {}).get("nombre") == "Quien Sea",
              "y ve lo nuevo sin reiniciar")
    comprobar(organizacion.equipo["JP"]["emails"] == ["uno@empresa.com", "dos@empresa.com"],
              "los correos escritos en una línea se separan solos")
    comprobar(organizacion.email_de("jp") == "uno@empresa.com",
              "email_de da el primero y no distingue mayúsculas")

    organizacion.cargar()
    comprobar(organizacion.equipo["JP"]["nombre"] == "Quien Sea" and
              organizacion.clientes["10002"] == "CLIENTE UNO",
              "lo guardado se relee igual del fichero")

    # Guardar una tabla no se lleva por delante las demás
    organizacion.guardar(clientes={"10002": "CLIENTE UNO", "10003": "CLIENTE DOS"})
    comprobar(organizacion.equipo.get("JP") is not None and len(organizacion.clientes) == 2,
              "guardar una tabla deja las otras en su sitio")

    try:
        organizacion.guardar(inventada={"a": "b"})
        comprobar(False, "una tabla que no existe se rechaza")
    except KeyError:
        comprobar(True, "una tabla que no existe se rechaza")

    # Las listas de correo, igual
    organizacion.guardar(correo_cc="uno@empresa.com; dos@empresa.com")
    comprobar(organizacion.correo_cc == ["uno@empresa.com", "dos@empresa.com"],
              "una lista de correos admite comas y puntos y coma")
finally:
    organizacion.ORGANIZACION_FILE = real
    organizacion.cargar()

# ── Los editores de Ajustes ──────────────────────────────────────────────────
root = ctk.CTk()
root.withdraw()

mapa = MapaEditor(root, "Clave", "Valor", {"A": "uno"})
mapa.ent_clave.insert(0, "B")
mapa.ent_valor.insert(0, "dos")
mapa._anadir()
comprobar(mapa.valores() == {"A": "uno", "B": "dos"}, "el editor añade una línea")
mapa.ent_clave.insert(0, "A")
mapa._quitar()
comprobar(mapa.valores() == {"B": "dos"}, "y quita la que se le diga")
mapa.ent_clave.insert(0, "B")
mapa.ent_valor.insert(0, "DOS")
mapa._anadir()
comprobar(mapa.valores() == {"B": "DOS"}, "repetir una clave la cambia, no la duplica")

equipo = EquipoEditor(root, {"JP": {"nombre": "Quien Sea", "emails": ["uno@empresa.com"]}})
comprobar(equipo.valores()["JP"]["emails"] == ["uno@empresa.com"], "el equipo se pinta")
equipo.ent_ini.insert(0, "ac")
equipo.ent_nombre.insert(0, "Otra Persona")
equipo.ent_correos.insert(0, "otra@empresa.com, otra2@empresa.com")
equipo._anadir()
comprobar(equipo.valores().get("AC", {}).get("emails") == ["otra@empresa.com", "otra2@empresa.com"],
          "las iniciales se guardan en mayúsculas y los correos separados")

lista = ListaEditor(root, "Para", ["uno@empresa.com"])
comprobar(lista.valores() == ["uno@empresa.com"], "la lista se pinta")
lista.poner(["a@x.com", "b@x.com"])
comprobar(lista.valores() == ["a@x.com", "b@x.com"], "y se puede cambiar entera")

root.update_idletasks()
try:
    root.destroy()
except Exception:  # noqa: BLE001
    pass

print(f"FALLOS: {fallos}")
sys.exit(1 if fallos else 0)
