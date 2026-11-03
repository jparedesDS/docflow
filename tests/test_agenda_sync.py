# -*- coding: utf-8 -*-
"""La sincronización de la Agenda respeta lo que se hace a mano: una tarea
automática completada o borrada no vuelve mientras su documento siga en esa
revisión; con una revisión nueva, sí. Fichero de agenda temporal y documentos
inventados.

    .venv\\Scripts\\python.exe tests\\test_agenda_sync.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import agenda as A  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


def doc(codigo, rev="0", estado="Sin Enviar"):
    return {"Nº Pedido": "P-99/001", "Nº Doc. EIPSA": codigo, "Nº Revisión": rev,
            "Estado": estado, "Título": f"Documento {codigo}", "Crítico": ""}


def tarea(codigo, rev="0"):
    sid = f"P-99/001_{codigo}_{rev}"
    return next((t for t in A.get_tareas("JP") if t.get("source_doc_id") == sid), None)


tmp = Path(tempfile.mkdtemp())
try:
    A.AGENDA_FILE = str(tmp / "agenda_data.json")
    CAL, PLA, ESP = "99-001-CAL-0001", "99-001-PLG-0002", "99-001-ESP-0003"
    pendientes = [doc(CAL), doc(PLA), doc(ESP)]
    res = A.sync_tareas("JP", pendientes)
    ok(res["created"] == 3, f"la primera sincronización crea una tarea por documento: {res}")

    # ── Completada a mano: no se reabre mientras siga en esa revisión ────────
    A.marcar_tarea(tarea(CAL)["id"], True)
    A.sync_tareas("JP", pendientes)
    ok(tarea(CAL)["estado"] == "completada", "la completada a mano sigue completada")

    # ── Borrada a mano: no se vuelve a crear ────────────────────────────────
    A.delete("tareas", tarea(PLA)["id"])
    res = A.sync_tareas("JP", pendientes)
    ok(tarea(PLA) is None and res["created"] == 0, f"la borrada no vuelve: {res}")

    # ── Completada por la sincronización: esa sí se reabre ──────────────────
    A.sync_tareas("JP", [doc(CAL), doc(PLA)])              # el ESP ya no está pendiente
    ok(tarea(ESP)["estado"] == "completada", "si el documento deja de estar pendiente, se completa")
    A.sync_tareas("JP", pendientes)                         # y vuelve a estarlo
    ok(tarea(ESP)["estado"] == "pendiente", "y si vuelve, se reabre: no la cerraste tú")

    # ── Reabrir a mano quita la marca: la sincronización vuelve a mandar ────
    A.marcar_tarea(tarea(CAL)["id"], False)
    ok(tarea(CAL)["estado"] == "pendiente" and not tarea(CAL)["cerrada_a_mano"],
       "reabierta a mano, vuelve a ser normal")

    # ── Una revisión nueva del documento sí trae tarea ──────────────────────
    nueva = [doc(CAL), doc(PLA, rev="1"), doc(ESP)]
    res = A.sync_tareas("JP", nueva)
    ok(tarea(PLA, rev="1") is not None and tarea(PLA, rev="1")["estado"] == "pendiente",
       f"la Rev. 1 del documento borrado tiene su tarea: {res}")

    # ── La lista de borradas no crece sin fin ───────────────────────────────
    datos = A._load()
    ok("P-99/001_99-001-PLG-0002_0" not in datos.get(A.DESCARTADAS, []),
       f"la Rev. 0 ya no está pendiente: se olvida: {datos.get(A.DESCARTADAS)}")

    # ── Las de antes de la marca: completadas, se respetan ──────────────────
    # (hasta ahora casi nunca se reabrían; no se sabe si las cerraste tú)
    datos = A._load()
    vieja = next(t for t in datos["tareas"] if t.get("source_doc_id") == f"P-99/001_{ESP}_0")
    vieja["estado"] = "completada"
    del vieja["cerrada_a_mano"]
    A._save(datos)
    A.sync_tareas("JP", nueva)
    ok(tarea(ESP)["estado"] == "completada", "una completada de antes no se reabre de golpe")

    # ── Borrar una tarea hecha a mano no apunta nada ────────────────────────
    propia = A.create_tarea("JP", {"titulo": "Llamar al cliente", "estado": "pendiente"})
    A.delete("tareas", propia["id"])
    ok(A._load().get(A.DESCARTADAS, []) == [], "las tareas propias no se apuntan como descartadas")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
