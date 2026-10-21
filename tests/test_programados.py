# -*- coding: utf-8 -*-
"""Reportes programados: el último envío dice a quién fue, a quién no (sin
pendientes) y qué falló; si Teams no acepta ninguna tarjeta no cuenta como
correcto. No envía nada: el envío a Teams está simulado.

    .venv\\Scripts\\python.exe tests\\test_programados.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import scheduled_reports as sr, teams, weekly_summary  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


tmp = Path(tempfile.mkdtemp(prefix="programados_"))
sr.SCHEDULES_FILE = str(tmp / "scheduled_reports.json")
teams.is_configured = lambda: True
SID = "weekly-teams-personal"
ok(sr.get_schedule(SID) is not None, "existe el de Pendientes por Teams")

resultado = {}
weekly_summary.post_all_personal_to_teams = lambda user_filter=None: dict(resultado)

resultado.update(sent=["AA", "BB"], skipped=["CC"], errors=[], count=2)
res = sr.execute_schedule(SID)
ultimo = sr.get_schedule(SID)["last_run"]
ok(res["status"] == "success" and ultimo["status"] == "success", f"envío normal: {ultimo}")
ok(ultimo["detalle"] == "enviado a AA, BB · sin pendientes: CC", f"dice a quién y a quién no: {ultimo['detalle']}")

resultado.update(sent=["AA"], skipped=[], errors=["BB"], count=1)
sr.execute_schedule(SID)
ultimo = sr.get_schedule(SID)["last_run"]
ok(ultimo["status"] == "partial" and "falló: BB" in ultimo["detalle"], f"uno falla: parcial: {ultimo}")

resultado.update(sent=[], skipped=["CC"], errors=["AA", "BB"], count=0)
res = sr.execute_schedule(SID)
ultimo = sr.get_schedule(SID)["last_run"]
ok(res["status"] == "error" and ultimo["status"] == "error", f"fallan todas: error, no «correcto»: {ultimo}")

resultado.update(sent=[], skipped=["AA", "BB", "CC"], errors=[], count=0)
sr.execute_schedule(SID)
ultimo = sr.get_schedule(SID)["last_run"]
ok(ultimo["status"] == "success" and ultimo["detalle"] == "no se envió a nadie · sin pendientes: AA, BB, CC",
   f"nadie con pendientes: se dice: {ultimo}")

ok(sr._detalle({"sent_to": ["aa@ejemplo.test"], "skipped": []}) == "enviado a aa",
   "el correo personal también")

print("FALLOS:", fallos)
