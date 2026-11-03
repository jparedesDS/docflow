# -*- coding: utf-8 -*-
"""Los Excel temporales del refresco del ERP no se acumulan en data/: se borra
el propio si el refresco falla, y los de más de un día al refrescar. Sin ERP:
una carpeta temporal y un DataFrame inventado.

    .venv\\Scripts\\python.exe tests\\test_temporales_erp.py
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core.services import erp_db as E  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


def temporales(carpeta):
    return sorted(p.name for p in carpeta.glob("*.tmp-*"))


df = pd.DataFrame({"Nº Pedido": ["P-99/001"], "Doc. EIPSA": ["99-001-CAL-0001"]})
tmp = Path(tempfile.mkdtemp())
try:
    destino = tmp / "data_erp.xlsx"

    # Un refresco normal deja el Excel y ningún temporal
    E._write_xlsx(df, destino, make_backup=False)
    ok(destino.is_file() and not temporales(tmp), f"refresco normal: {temporales(tmp)}")

    # Si el cambio de nombre falla (el destino abierto en Excel), el temporal se borra
    os_replace = os.replace

    def bloqueado(origen, final):
        raise PermissionError("abierto en Excel")

    os.replace = bloqueado
    try:
        E._write_xlsx(df, destino, make_backup=False)
        ok(False, "el fallo tenía que subir a quien refresca")
    except PermissionError:
        pass
    finally:
        os.replace = os_replace
    ok(not temporales(tmp), f"el refresco que falla no deja temporal: {temporales(tmp)}")

    # Los que dejó un cierre a la fuerza: los de más de un día se van al
    # refrescar; el reciente (otro refresco en marcha) y los de otro Excel no
    viejo = tmp / "data_erp.tmp-074416.xlsx"
    reciente = tmp / "data_erp.tmp-120000.xlsx"
    de_otro = tmp / "consulta_erp.tmp-074416.xlsx"
    for p in (viejo, reciente, de_otro):
        p.write_bytes(b"xlsx")
    hace_dos_dias = time.time() - 2 * 24 * 3600
    os.utime(viejo, (hace_dos_dias, hace_dos_dias))
    os.utime(de_otro, (hace_dos_dias, hace_dos_dias))
    E._write_xlsx(df, destino, make_backup=False)
    ok(not viejo.exists(), "el temporal viejo se borra")
    ok(reciente.exists(), "el reciente se respeta")
    ok(de_otro.exists(), "los de otro Excel los limpia su propio refresco")
    ok(destino.is_file(), "y el Excel sigue ahí")

    # Las copias del botón manual: solo se guardan las 3 últimas de cada Excel
    for fecha in ("20260901_080000", "20260902_080000", "20260903_080000", "20260904_080000"):
        (tmp / f"data_erp.backup-{fecha}.xlsx").write_bytes(b"xlsx")
    (tmp / "consulta_erp.backup-20260901_080000.xlsx").write_bytes(b"xlsx")
    E._write_xlsx(df, destino, make_backup=True)          # hace la 5.ª
    copias = sorted(p.name for p in tmp.glob("data_erp.backup-*"))
    ok(len(copias) == 3 and "data_erp.backup-20260901_080000.xlsx" not in copias
       and "data_erp.backup-20260902_080000.xlsx" not in copias,
       f"se quedan las 3 últimas: {copias}")
    ok((tmp / "consulta_erp.backup-20260901_080000.xlsx").exists(),
       "y las de otro Excel no se tocan")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
