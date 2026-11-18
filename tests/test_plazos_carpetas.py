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

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
