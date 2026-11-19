# -*- coding: utf-8 -*-
"""Plazos: cuándo se pasaron los planos a fábrica y quién (3-Fabricacion\\Envíos).

El técnico manda a fábrica un correo («P.Fabricación (envío 01)») que se guarda
como .msg en Envíos (o en «envío 01», «envío 02», «superado»…). Se toma el más
antiguo: su fecha y hora y su remitente. Sin correo, el PDF más antiguo.

Carpetas temporales con datos inventados (P-99/…): nunca toca M:. Los .msg de
prueba no son de Outlook: su lectura se sustituye.

    .venv\\Scripts\\python.exe tests\\test_plazos_carpetas.py
"""
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import seguimiento_carpetas as sc  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


tmp = Path(tempfile.mkdtemp(prefix="plazos_"))
año = tmp / "Año 2099" / "2099 Pedidos"

# Lo que «dice» cada .msg de prueba, por nombre de fichero
CORREOS = {
    "envio01.msg": (datetime(2099, 3, 5, 9, 46), "<tecnico-uno@ejemplo.test>"),
    "superado.msg": (datetime(2099, 3, 5, 8, 10), "tecnico-dos tecnico-dos"),
    "envio02.msg": (datetime(2099, 3, 20, 16, 0), "<tecnico-uno@ejemplo.test>"),
    "roto.msg": (None, ""),
}
leidos = []


def falso_msg(ruta):
    leidos.append(Path(ruta).name)
    return CORREOS.get(Path(ruta).name, (None, ""))


sc._leer_msg = falso_msg


def envios(nombre, fab="3-Fabricacion", env="Envíos"):
    d = año / nombre / fab / env
    d.mkdir(parents=True, exist_ok=True)
    return d


# P-99/001: correos en subcarpetas; el más antiguo es el de «superado»
d1 = envios("P-99-001 - CLIENTE FICTICIO - VAINAS")
for sub, f in (("envío 01", "envio01.msg"), ("superado", "superado.msg"), ("envío 02", "envio02.msg")):
    (d1 / sub).mkdir()
    (d1 / sub / f).write_bytes(b"x")
(d1 / "envío 01" / "P-99-001 P.Fabricación-signed.pdf").write_bytes(b"%PDF")
(d1 / "Thumbs.db").write_bytes(b"x")

r = sc.planos_de("P-99/001-S00", base_dir=tmp)
ok(r["estado"] == "ok" and r["creado"] == datetime(2099, 3, 5, 8, 10), f"el correo más antiguo, también si está superado: {r}")
ok(r["autor"] == "tecnico-dos" and r["fuente"] == "correo", f"remitente limpio: {r['autor']!r}")
ok(r["ruta"] == str(d1), f"ruta de Envíos: {r['ruta']}")
ok(r["envios"] == 3, f"cuántos correos a fábrica: {r.get('envios')}")

# Sin correo legible pero con el PDF firmado: la creación del PDF, y se dice
d2 = envios("P-99-002-S01 - CLIENTE FICTICIO - RO")
(d2 / "roto.msg").write_bytes(b"x")
(d2 / "~$temporal.pdf").write_bytes(b"x")
time.sleep(0.05)
(d2 / "P-99-002 P.Fabricación-signed.pdf").write_bytes(b"%PDF")
r = sc.planos_de("P-99/002-S01", base_dir=tmp)
st = (d2 / "P-99-002 P.Fabricación-signed.pdf").stat()
ok(r["estado"] == "ok" and r["fuente"] == "pdf" and
   abs(r["creado"].timestamp() - (getattr(st, "st_birthtime", None) or st.st_ctime)) < 1,
   f"sin correo: el PDF (no el temporal ~$): {r}")
ok(r["autor"] and "\\" not in r["autor"], f"autor del PDF sin dominio: {r['autor']!r}")

ok(sc.planos_de("P-99/001-S02", base_dir=tmp)["estado"] == "sin_carpeta",
   "un suministro sin carpeta propia no hereda los envíos de S00")
envios("P-99-003 - CLIENTE FICTICIO - NIVEL")
ok(sc.planos_de("P-99/003-S00", base_dir=tmp)["estado"] == "vacia", "Envíos vacía")
(año / "P-99-004 - CLIENTE FICTICIO - NIVEL" / "2-Tecnico").mkdir(parents=True)
ok(sc.planos_de("P-99/004-S00", base_dir=tmp)["estado"] == "sin_carpeta", "sin 3-Fabricacion")
d5 = envios("P-99-005 - CLIENTE FICTICIO - TC", fab="3-Fabricación", env="ENVIOS")
(d5 / "envio01.msg").write_bytes(b"x")
ok(sc.planos_de("P-99/005-S00", base_dir=tmp)["estado"] == "ok", "3-Fabricación y ENVIOS también valen")
envios("P-99-007 - CLIENTE FICTICIO - TC", env="Planos OF")
ok(sc.planos_de("P-99/007-S00", base_dir=tmp)["estado"] == "sin_carpeta", "Planos OF ya no cuenta")
ok(sc.planos_de("P-99/777-S00", base_dir=tmp)["estado"] == "sin_carpeta", "pedido sin carpeta")

ok(sc.remitente("<ana-ejemplo@ejemplo.test>") == "ana-ejemplo", "remitente con correo")
ok(sc.remitente("luis-ejemplo luis-ejemplo luis-ejemplo") == "luis-ejemplo", "remitente repetido")
ok(sc.remitente('"Pepa Ruiz" <pepa-ruiz@ejemplo.test>') == "pepa-ruiz", "remitente con nombre")
ok(sc.propietario(d2 / "P-99-002 P.Fabricación-signed.pdf"), "propietario de un fichero")
ok(sc.propietario(tmp / "no-existe.pdf") == "", "propietario de lo que no existe: vacío")

# Caché: lo encontrado no se vuelve a leer; lo vacío sí; lo cambiado sí
cache = tmp / "cache.json"
pedidos = ["P-99/001-S00", "P-99/003-S00"]
leidos.clear()
a = sc.leer_planos(pedidos, base_dir=tmp, cache_file=cache)
n1 = len(leidos)
b = sc.leer_planos(pedidos, base_dir=tmp, cache_file=cache)
ok(n1 == 3 and len(leidos) == n1, f"segunda lectura desde la caché: {n1} → {len(leidos)}")
ok(a["P-99/001-S00"] == b["P-99/001-S00"] and b["P-99/003-S00"]["estado"] == "vacia", f"la caché devuelve lo mismo: {b}")
d3 = año / "P-99-003 - CLIENTE FICTICIO - NIVEL" / "3-Fabricacion" / "Envíos"
mt = os.stat(d3).st_mtime_ns
(d3 / "envío 01").mkdir()
(d3 / "envío 01" / "envio02.msg").write_bytes(b"x")
os.utime(d3, ns=(mt, mt))
c = sc.leer_planos(pedidos, base_dir=tmp, cache_file=cache)
ok(c["P-99/003-S00"]["estado"] == "ok", "una vacía se vuelve a mirar aunque su fecha no cambie (subcarpeta)")
time.sleep(0.05)
(d1 / "envío 03").mkdir()
(d1 / "envío 03" / "envio02.msg").write_bytes(b"x")
os.utime(d1)
leidos.clear()
sc.leer_planos(pedidos, base_dir=tmp, cache_file=cache)
ok(len(leidos) == 4, f"la carpeta cambiada se vuelve a leer: {leidos}")

# ── Correos de las carpetas del pedido: orden de compra, activación y PO ─────
# Lo que «dice» cada .msg de prueba (fecha, de, para, asunto), por nombre
MSGS = {
    "oc.msg": (datetime(2099, 3, 2, 9, 18), "<tecnico-uno@ejemplo.test>",
               '"Compras Uno" <compras-uno@ejemplo.test>; otro@ejemplo.test', "P-99/011, orden de compra disponible"),
    "oc_rev1.msg": (datetime(2099, 3, 9, 10, 0), "<tecnico-uno@ejemplo.test>", "compras-uno@ejemplo.test",
                    "P-99/011, orden de compra rev 1"),
    "ACTIVACIÓN P-99_011-S00 _ CLIENTE.msg": (datetime(2099, 2, 26, 8, 5), "Pepa Ruiz <pepa-ruiz@ejemplo.test>",
                                              "documentacion@ejemplo.test", "ACTIVACIÓN P-99/011-S00 / CLIENTE"),
    "Purchase Order - 4500012345.msg": (datetime(2099, 2, 24, 16, 30), "<compras@cliente.ejemplo.test>",
                                        "pepa-ruiz@ejemplo.test", "Purchase Order - 4500012345 - EIPSA"),
    "RE_ dudas de calidad.msg": (datetime(2099, 2, 20, 8, 0), "<x@cliente.ejemplo.test>", "y@ejemplo.test",
                                 "RE: dudas de calidad"),
    "PO antigua en subcarpeta.msg": (datetime(2099, 1, 1, 8, 0), "<x@cliente.ejemplo.test>", "y@ejemplo.test",
                                     "PO 1"),
}
leidos_c = []


def falso_correo(ruta):
    leidos_c.append(Path(ruta).name)
    f = MSGS.get(Path(ruta).name)
    return {"fecha": f[0], "de": f[1], "para": f[2], "asunto": f[3]} if f else None


sc._leer_correo = falso_correo
p11 = año / "P-99-011 - CLIENTE FICTICIO - VAINAS"
(p11 / "3-Fabricacion" / "Orden de compra" / "cambios").mkdir(parents=True)
(p11 / "3-Fabricacion" / "Orden de compra" / "oc.msg").write_bytes(b"x")
(p11 / "3-Fabricacion" / "Orden de compra" / "cambios" / "oc_rev1.msg").write_bytes(b"x")
(p11 / "3-Fabricacion" / "Orden de compra" / "orden rev 0.xlsx").write_bytes(b"x")
(p11 / "1-Comercial" / "SUPLEMENTOS").mkdir(parents=True)
for n in ("ACTIVACIÓN P-99_011-S00 _ CLIENTE.msg", "Purchase Order - 4500012345.msg", "RE_ dudas de calidad.msg"):
    (p11 / "1-Comercial" / n).write_bytes(b"x")
(p11 / "1-Comercial" / "SUPLEMENTOS" / "PO antigua en subcarpeta.msg").write_bytes(b"x")

r = sc.correos_pedido("P-99/011-S00", base_dir=tmp)
ok(r["oc"] == {"fecha": datetime(2099, 3, 2, 9, 18), "de": "tecnico-uno", "para": "compras-uno"},
   f"orden de compra a Compras: el más antiguo, quién y a quién: {r['oc']}")
ok(r["activacion"] == {"fecha": datetime(2099, 2, 26, 8, 5), "de": "pepa-ruiz", "para": "documentacion"},
   f"activación del primer nivel de 1-Comercial: {r['activacion']}")
ok(r["po"] and r["po"]["fecha"] == datetime(2099, 2, 24, 16, 30),
   f"PO del cliente, solo en el primer nivel (no la de SUPLEMENTOS): {r['po']}")
ok(sc.correos_pedido("P-99/011-S03", base_dir=tmp) == {"oc": None, "activacion": None, "po": None},
   "un suministro sin carpeta propia no hereda los correos")
ok(sc.correos_pedido("P-99/003-S00", base_dir=tmp) == {"oc": None, "activacion": None, "po": None},
   "sin carpetas Orden de compra ni 1-Comercial")

cache_c = tmp / "correos_carpetas.json"
leidos_c.clear()
a = sc.leer_correos_pedido(["P-99/011-S00"], base_dir=tmp, cache_file=cache_c)
n1 = len(leidos_c)
b = sc.leer_correos_pedido(["P-99/011-S00"], base_dir=tmp, cache_file=cache_c)
ok(n1 >= 5 and len(leidos_c) == n1 and a == b, f"la segunda vez, desde la caché: {n1} → {len(leidos_c)}")
time.sleep(0.05)
(p11 / "1-Comercial" / "ACTIVACIÓN P-99_011-S00 _ CLIENTE.msg").unlink()
c = sc.leer_correos_pedido(["P-99/011-S00"], base_dir=tmp, cache_file=cache_c)
ok(c["P-99/011-S00"]["activacion"] is None and c["P-99/011-S00"]["oc"] == a["P-99/011-S00"]["oc"],
   f"la carpeta cambiada se vuelve a leer: {c}")

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
