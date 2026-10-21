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
publicar_de_verdad = weekly_summary.post_all_personal_to_teams
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

# ── Las tarjetas de verdad (Teams simulado) ──────────────────────────────────
DOCS = [
    {"Repsonsable": "AA", "Estado": "Com. Menores", "Nº Doc. EIPSA": "99-001-CAL-0001",
     "Título": "CALCULO DE ORIFICIO DE RESTRICCION PARA LINEA DE PRUEBA NUMERO UNO CON TEXTO LARGO",
     "Tipo Doc.": "Cálculos", "Días Devolución": 20},
    {"Repsonsable": "AA", "Estado": "Aprobado", "Nº Doc. EIPSA": "99-001-CAL-0002"},
    {"Repsonsable": "BB", "Estado": "Aprobado", "Nº Doc. EIPSA": "99-002-DWG-0001"},
    {"Repsonsable": "BB", "Estado": "Enviado", "Nº Doc. EIPSA": "99-002-DWG-0002"},
]
publicadas = []
weekly_summary.monitoring_service.get_monitoring_data = lambda: DOCS
weekly_summary.USERS = {"AA": {"nombre": "Ana Alonso", "emails": ["aa@ejemplo.test"]},
                        "BB": {"nombre": "Beto Blanco", "emails": ["bb@ejemplo.test"]}}
weekly_summary._save_personal_report = lambda ini, pdata: (None, None)
weekly_summary._user_email = lambda ini: f"{ini.lower()}@ejemplo.test"
weekly_summary.time.sleep = lambda s: None
teams.post_card = lambda **kw: publicadas.append(kw) or {"ok": True, "status": 202}

r = publicar_de_verdad(user_filter=["AA", "BB"])
ok(r["sent"] == ["AA", "BB"] and r["al_dia"] == ["BB"], f"también quien está al día recibe la suya: {r}")
ok(sr._detalle(r) == "enviado a AA, BB · al día: BB", f"y se dice: {sr._detalle(r)}")
tabla = publicadas[0]["table_html"]
ok("<th>Título</th>" in tabla and "CALCULO DE ORIFICIO" in tabla and "…" in tabla,
   f"la tabla lleva el título (recortado si es largo): {tabla[:200]}")
al_dia = publicadas[1]
ok(al_dia["subtitle"].startswith("Sin pendientes") and ("Aprobados", 1) in al_dia["facts"]
   and ("En el cliente", 1) in al_dia["facts"], f"tarjeta de todo al día: {al_dia}")

# ── Un documento de dos responsables («AA/BB») es de los dos ─────────────────
from core.services import analytics, monitoring  # noqa: E402

ok(monitoring.responsables("EC/SS") == ["EC", "SS"] and monitoring.responsables(" jp ") == ["JP"]
   and monitoring.responsables("") == [], "«EC/SS» → EC y SS")
DOCS.append({"Repsonsable": "AA/BB", "Estado": "Rechazado", "Nº Doc. EIPSA": "99-003-PRC-0001",
             "Título": "PROCEDIMIENTO COMPARTIDO", "Tipo Doc.": "Procedimientos"})
publicadas.clear()
r = publicar_de_verdad(user_filter=["AA", "BB"])
ok(r["al_dia"] == [], f"BB ya no está al día: el compartido también es suyo: {r}")
ok(all("99-003-PRC-0001" in p["table_html"] for p in publicadas),
   "el compartido sale en la tarjeta de los dos")
ranking = {x["responsable"]: x["total"] for x in analytics.get_ranking()}
ok(ranking.get("AA") == 3 and ranking.get("BB") == 3 and "AA/BB" not in ranking,
   f"ranking: cuenta para cada uno y no es un responsable más: {ranking}")
equipo = {x["iniciales"]: x["n_pendientes"] for x in analytics.get_team_overview()}
ok(equipo.get("AA") == 2 and equipo.get("BB") == 1, f"pendientes del equipo: {equipo}")

print("FALLOS:", fallos)
