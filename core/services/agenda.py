"""Servicio Agenda — Notas, Reuniones y Tareas persistidas en JSON local.

Port de agenda_service.py del DocFlow grande, sin dependencia IMAP/IA.
Las tareas pueden sincronizarse con los docs pendientes del Monitoring.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone

from core.paths import state_dir
from core.utils.json_store import read_json, write_json

logger = logging.getLogger(__name__)

AGENDA_FILE = str(state_dir() / "agenda_data.json")

TIPOS = ("notas", "reuniones", "tareas")
_DEFAULT = {"notas": [], "reuniones": [], "tareas": []}

# Las tareas automáticas que se borraron a mano, por documento y revisión
# (`source_doc_id`): la sincronización no las vuelve a crear. Una revisión
# nueva del documento es otra clave, y esa sí trae tarea.
DESCARTADAS = "tareas_descartadas"

ESTADOS_PENDIENTES = {"sin enviar", "", "com. menores", "com. mayores", "comentado", "rechazado"}
DEFAULT_OWNER = "JP"

# Leer, cambiar y guardar va de una pieza: la pantalla y los avisos que llegan
# por correo (en otro hilo) escriben el mismo fichero, y sin esto uno pisaba
# lo que acababa de guardar el otro.
_mutex = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    # Listas nuevas cada vez: con dict(_DEFAULT) eran las mismas de la plantilla,
    # y lo primero que se guardaba sin fichero se quedaba en ella para siempre.
    data = read_json(AGENDA_FILE, default={k: [] for k in _DEFAULT})
    if not isinstance(data, dict):
        return {k: [] for k in TIPOS}
    for k in TIPOS:
        data.setdefault(k, [])
    return data


def _save(data: dict) -> None:
    write_json(AGENDA_FILE, data)


# ── CRUD genérico ─────────────────────────────────────────────────────────────

def get_all(tipo: str) -> list[dict]:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo inválido: {tipo}")
    return _load().get(tipo, [])


def create(tipo: str, item: dict) -> dict:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo inválido: {tipo}")
    with _mutex:
        data = _load()
        now = _now()
        item = {**item, "id": str(uuid.uuid4()), "createdAt": now, "updatedAt": now}
        data[tipo].append(item)
        _save(data)
    return item


def update(tipo: str, item_id: str, changes: dict) -> dict | None:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo inválido: {tipo}")
    with _mutex:
        data = _load()
        for i, it in enumerate(data[tipo]):
            if it.get("id") == item_id:
                updated = {**it, **changes, "id": item_id, "updatedAt": _now()}
                data[tipo][i] = updated
                _save(data)
                return updated
    return None


def delete(tipo: str, item_id: str) -> bool:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo inválido: {tipo}")
    with _mutex:
        data = _load()
        borradas = [it for it in data[tipo] if it.get("id") == item_id]
        if not borradas:
            return False
        data[tipo] = [it for it in data[tipo] if it.get("id") != item_id]
        if tipo == "tareas":
            for t in borradas:
                sid = t.get("source_doc_id")
                descartadas = _descartadas(data, t.get("owner") or DEFAULT_OWNER)
                if t.get("auto_generated") and sid and sid not in descartadas:
                    descartadas.append(sid)
        _save(data)
    return True


def _descartadas(data: dict, owner: str) -> list[str]:
    """Las automáticas que `owner` borró a mano (cada uno las suyas: la
    sincronización de uno no puede olvidar las del otro)."""
    por_owner = data.get(DESCARTADAS)
    if not isinstance(por_owner, dict):
        por_owner = data[DESCARTADAS] = {}
    return por_owner.setdefault(owner, [])


def marcar_tarea(item_id: str, hecha: bool) -> dict | None:
    """Completar o reabrir una tarea a mano. Lo que decide quien la usa manda
    sobre la sincronización: una automática completada a mano no se reabre
    aunque su documento siga pendiente en esa revisión."""
    return update("tareas", item_id, {"estado": "completada" if hecha else "pendiente",
                                      "cerrada_a_mano": bool(hecha)})


# ── Tareas (con owner) ────────────────────────────────────────────────────────

def get_tareas(owner: str = DEFAULT_OWNER) -> list[dict]:
    with _mutex:
        data = _load()
        changed = False
        for tarea in data["tareas"]:
            if "owner" not in tarea:
                asignado = (tarea.get("asignado") or "").strip()
                tarea["owner"] = asignado if asignado else DEFAULT_OWNER
                changed = True
        if changed:
            _save(data)
    return [t for t in data["tareas"] if t.get("owner") == owner]


def create_tarea(owner: str, item: dict) -> dict:
    item = {**item, "owner": owner}
    return create("tareas", item)


def sync_tareas(owner: str, docs: list[dict]) -> dict:
    """Sincroniza tareas auto-generadas con docs pendientes actuales del monitoring.

    - Crea tareas para docs nuevos pendientes
    - Marca completadas las que ya no están pendientes
    - Actualiza descripción de las que cambiaron de estado
    """
    with _mutex:
        return _sync_tareas(owner, docs)


def _sync_tareas(owner: str, docs: list[dict]) -> dict:
    data = _load()

    pending_by_source: dict[str, dict] = {}
    for doc in docs:
        sid = f"{doc.get('Nº Pedido', '')}_{doc.get('Nº Doc. EIPSA', '')}_{doc.get('Nº Revisión', doc.get('Rev.', ''))}"
        pending_by_source[sid] = doc

    existing_ids: set[str] = set()
    completed = updated = created = reopened = reabribles = 0
    now = _now()

    for tarea in data["tareas"]:
        if not tarea.get("auto_generated") or tarea.get("owner") != owner:
            continue
        sid = tarea.get("source_doc_id")
        if not sid:
            continue
        existing_ids.add(sid)

        if sid not in pending_by_source:
            if tarea.get("estado") != "completada":
                tarea["estado"] = "completada"
                tarea["cerrada_a_mano"] = False
                tarea["updatedAt"] = now
                completed += 1
            elif docs and tarea.get("cerrada_a_mano", True) is not False:
                # Completada a mano y el documento ya no está pendiente: lo que
                # decidiste se cumplió. Si vuelve en esta revisión (el cliente
                # la devuelve comentada) es trabajo nuevo y se reabre. Con una
                # lista vacía no: más bien no se pudo leer el seguimiento, y la
                # siguiente sincronización reabriría lo que cerraste tú.
                tarea["cerrada_a_mano"] = False
                reabribles += 1
        else:
            doc = pending_by_source[sid]
            new_desc = (
                f"Pedido {doc.get('Nº Pedido', '')} · "
                f"Rev. {doc.get('Nº Revisión', '')} · "
                f"Estado: {doc.get('Estado', '') or 'Sin Enviar'}"
            )
            if tarea.get("descripcion") != new_desc:
                tarea["descripcion"] = new_desc
                tarea["updatedAt"] = now
                updated += 1
            # La completó la sincronización y el documento vuelve a estar
            # pendiente: se reabre. Si la completaste tú, se respeta. Las de
            # antes de esta marca (sin ella) no se sabe quién las cerró: se
            # respetan, como hasta ahora, en que casi nunca se reabrían.
            if tarea.get("estado") == "completada" and tarea.get("cerrada_a_mano", True) is False:
                tarea["estado"] = "pendiente"
                tarea["updatedAt"] = now
                reopened += 1      # sin contarla no se guardaba: no se reabría nunca

    # Crear nuevas (salvo las que borraste: esa revisión ya no trae tarea)
    descartadas = _descartadas(data, owner)
    for sid, doc in pending_by_source.items():
        if sid in existing_ids or sid in descartadas:
            continue
        estado = (doc.get("Estado") or "").strip().lower()
        prioridad = "alta" if estado in {"rechazado", "com. mayores", "comentado"} else "media"
        if estado in {"sin enviar", ""} and str(doc.get("Crítico", "")).lower().strip() in ("sí", "si"):
            prioridad = "alta"
        titulo_raw = doc.get("Título") or doc.get("Material") or ""
        new_task = {
            "titulo": f"[{doc.get('Nº Doc. EIPSA', '')}] {titulo_raw[:60]}",
            "descripcion": (
                f"Pedido {doc.get('Nº Pedido', '')} · "
                f"Rev. {doc.get('Nº Revisión', '')} · "
                f"Estado: {doc.get('Estado', '') or 'Sin Enviar'}"
            ),
            "prioridad": prioridad,
            "estado": "pendiente",
            "fecha_limite": str(doc.get("Fecha Prevista", "") or ""),
            "asignado": owner,
            "auto_generated": True,
            "cerrada_a_mano": False,
            "source_doc_id": sid,
            "owner": owner,
            "id": str(uuid.uuid4()),
            "createdAt": now,
            "updatedAt": now,
        }
        # Sobre el mismo `data`: antes se guardaba aparte con create() y el
        # _save(data) de abajo, con la copia vieja, las borraba si además
        # se había completado o actualizado alguna.
        data["tareas"].append(new_task)
        created += 1

    # Las descartadas cuyo documento ya no está pendiente en esa revisión no
    # van a volver: se olvidan, para que la lista no crezca sin fin. Con una
    # lista vacía no: eso es más bien que no se pudo leer el seguimiento, y se
    # olvidarían todas de golpe.
    podadas = False
    if docs:
        vigentes = [sid for sid in descartadas if sid in pending_by_source]
        podadas = len(vigentes) != len(descartadas)
        descartadas[:] = vigentes

    if completed or updated or created or reopened or reabribles or podadas:
        _save(data)

    return {"created": created, "completed": completed, "updated": updated,
            "reopened": reopened}
