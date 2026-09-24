# -*- coding: utf-8 -*-
"""Importa TODOS los módulos de core/ y gui/.

Es la red que caza los fallos que ruff no ve: un import circular, un módulo que
ejecuta algo al cargarse y revienta, un nombre que se quedó a medias en un
renombrado. Tarda unos segundos y se lanza antes que nada.
"""
import importlib
import sys
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

ok, fallos = 0, []
for paquete in ("core", "gui"):
    for py in (BASE / paquete).rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        modulo = ".".join(py.relative_to(BASE).with_suffix("").parts)
        if modulo.endswith(".__init__"):
            modulo = modulo[: -len(".__init__")]
        try:
            importlib.import_module(modulo)
            ok += 1
        except Exception:  # noqa: BLE001
            fallos.append((modulo, traceback.format_exc().strip().splitlines()[-1]))

print(f"Modulos importados: {ok}")
for modulo, error in fallos:
    print(f"  {modulo}: {error}")
print(f"FALLOS: {len(fallos)}")
sys.exit(1 if fallos else 0)
