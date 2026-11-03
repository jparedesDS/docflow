"""ERP service LITE — Consulta ERP, Tags & Inspecciones y analítica de Proyectos.

Combina, sin DB ni API, las tres áreas del DocFlow grande que la sección
"Pedidos" reúne en una sola pantalla:

  1. Consulta ERP   → ficha del pedido (consulta_erp.xlsx): proyecto, cliente,
                       fases Fabricación/Montaje/Envío con % y observaciones.
  2. Tags & Insp.   → equipos del pedido desde el ERP (erp_tags: tags_data.*
                       + órdenes de fabricación); secciones de detalle aquí.
  3. Proyectos      → tabla por pedido (reutiliza monitoring.get_status_global)
                       + dashboard por pedido + analítica (curva-S, predicciones,
                       urgencias, heatmap) portada de analytics_service.

Lecturas de Excel cacheadas (TTL corto). Paths resueltos vía data_source para
respetar import/vínculo configurado por el usuario.
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

from core.services import monitoring

logger = logging.getLogger(__name__)

CACHE_TTL = 180  # segundos — alineado con monitoring (el auto-refresco invalida)


# ════════════════════════════════════════════════════════════════════════════
# Lectura de Excel cacheada
# ════════════════════════════════════════════════════════════════════════════

_cache: dict[str, tuple[float, object]] = {}


def invalidate_cache() -> None:
    _cache.clear()
    monitoring.invalidate_cache()


def _effective_path(kind: str, fallback: str) -> str:
    """Path efectivo del Excel (respeta vínculo configurado), con fallback."""
    try:
        from core import data_source
        return data_source.get_effective_path(kind)
    except Exception:
        return fallback


def _read_excel_cached(path: str) -> pd.DataFrame:
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    key = f"xlsx::{path}::{os.path.getmtime(path)}"
    now = time.time()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < CACHE_TTL:
        return hit[1]
    try:
        from core.utils.excel import read_excel_fast
        df = read_excel_fast(path)
    except Exception as exc:
        logger.warning("No se pudo leer %s: %s", path, exc)
        df = pd.DataFrame()
    _cache[key] = (now, df)
    return df


def _clean_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → list[dict] con NaN/inf saneados a ''."""
    if df.empty:
        return []
    rows = df.fillna("").to_dict(orient="records")
    for r in rows:
        for k, v in r.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                r[k] = ""
    return rows


def _num(v):
    """Convierte a float de forma tolerante. Devuelve None si no es numérico."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    try:
        return float(str(v).strip().replace("%", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def _parse_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    head = s.split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(head, fmt)
        except ValueError:
            continue
    return None


# ════════════════════════════════════════════════════════════════════════════
# 1) Consulta ERP
# ════════════════════════════════════════════════════════════════════════════

def _consulta_path() -> str:
    from core.config import CONSULTA_ERP_PATH
    return _effective_path("consulta_erp", CONSULTA_ERP_PATH)


def consulta(pedido: str = "") -> list[dict]:
    """Filas de consulta_erp.xlsx que casan con `pedido` (substring, case-insensitive).

    Sin `pedido` devuelve todas (puede ser grande — la UI suele exigir búsqueda).
    """
    df = _read_excel_cached(_consulta_path())
    rows = _clean_records(df)
    if not pedido:
        return rows
    q = pedido.strip().lower()
    return [r for r in rows if q in str(r.get("Nº Pedido", "")).lower()]


def comercial_por_pedido() -> dict:
    """{Nº Pedido sin sufijo de suministro → iniciales del comercial} del ERP.

    Se cachea igual que la propia consulta: se consulta una vez por documento
    al preparar una devolución y son ~3.700 pedidos.
    """
    path = _consulta_path()
    key = f"comercial::{path}::{os.path.getmtime(path) if os.path.exists(path) else 0}"
    now = time.time()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < CACHE_TTL:
        return hit[1]
    idx: dict[str, str] = {}
    for row in consulta():
        # Hay pedidos escritos con espacio antes del suministro («P-18/021 -S00»).
        ped = str(row.get("Nº Pedido", "")).split("-S")[0].strip()
        ini = str(row.get("Responsable", "") or "").strip().upper()
        if ped and ini and ped not in idx:
            idx[ped] = ini
    _cache[key] = (now, idx)
    return idx


# Fases (título, columna %, columna fecha, columna observaciones)
CONSULTA_PHASES = [
    ("Fabricación", "% Fabricación", "Fecha Fabricación", "Obs. Fabricación"),
    ("Montaje",     "% Montaje",     "Fecha Montaje",     "Obs. Montaje"),
    ("Envío",       "% Envío",       "Fecha Envío",       "Obs. Envío"),
]


def consulta_phases(row: dict) -> list[dict]:
    """Extrae las 3 fases de una fila de consulta para pintar barras de progreso."""
    out = []
    for title, pct_col, date_col, obs_col in CONSULTA_PHASES:
        pct = _num(row.get(pct_col))
        out.append({
            "title": title,
            "pct": int(pct) if pct is not None else 0,
            "date": str(row.get(date_col, "") or ""),
            "obs": str(row.get(obs_col, "") or ""),
        })
    return out


# ════════════════════════════════════════════════════════════════════════════
# 2) Tags & Inspecciones
# ════════════════════════════════════════════════════════════════════════════


# Secciones de detalle (réplica de ErpTags.js DETAIL_SECTIONS)
TAGS_DETAIL_SECTIONS = [
    ("Identificación", [
        "ID", "TAG", "Estado", "Nº Oferta", "Nº Pedido", "PO", "Posición",
        "Subposición", "Tipo"]),
    ("Especificaciones de Línea", [
        "Tamaño Línea", "Rating", "Facing", "Schedule", "Pipe Spec.", "NACE",
        "Nº Saltos"]),
    ("Materiales", [
        "Mat. Brida", "Tipo Brida", "Mat. Tubo", "Mat. Elemento", "Mat. Junta",
        "Mat. Torn.", "Mat. Tuercas", "Mat. Tapón", "Mat. Extractor",
        "Mat. Porta RTJ", "Con. Vlv.", "Mat. Cuerpo Vlv.", "Mat. Conos Vent."]),
    ("Elemento / Placa", [
        "Tipo Placa", "Esp. Placa", "Std Paca", "øOrif. (mm)", "øD/V (mm)",
        "Tipo RTJ"]),
    ("Tomas", ["Tamaño Tomas", "Nº Tomas", "Orient. Tomas"]),
    ("Tornillería y Juntas", [
        "Tamaño Torn.", "Cant. Torn", "Cant. Juntas", "Espesor RTJ",
        "Tamaño Extractor", "Cant. Extractor", "Cant. Tapón"]),
    ("Dimensiones", [
        "Peso (mm)", "Long. (mm)", "øInt. Línea", "øExt. Placa", "Cota C Placa",
        "Alto Mango", "Ancho Mango", "Espesor Mango", "Cota P RTJ", "Cota E RTJ",
        "Cota F RTJ", "O Brida", "A Brida", "C Brida", "Y Brida", "X Brida",
        "R Brida", "D Brida", "T Brida", "øBore Torn.", "A Venturi", "D Venturi",
        "E Venturi", "F Venturi", "G Venturi", "C Venturi", "H Venturi", "T Venturi"]),
    ("Documentación", [
        "Doc EIPSA Calc.", "Doc EIPSA Plano", "Plano Dim.", "Rev. Plano Dim.",
        "Fecha Plano Dim.", "Plano OF", "Rev. Plano OF", "Fecha Plano OF",
        "Orden de Compra", "Fecha Orden Compra", "Notas Orden Compra"]),
    ("Fabricación e Inspección", [
        "Estado Fab.", "Inspeccion", "Fecha IRC", "Colada Placa", "Cert. Placa",
        "Colada Brida", "Cert. Brida", "Fecha PMI", "Fecha PH1", "Fecha PH2",
        "Fecha LP", "Fecha Dureza", "Fecha Verif. Dim.", "Estado Verif. Dim.",
        "Notas Verif. Dim", "Fecha Verif. OF", "Estado Verif. OF",
        "Notas Verif. OF", "Envío RN", "Fecha RN"]),
    ("Notas", [
        "Notas Oferta", "Cambios Com.", "Fecha Contr.", "Cambios Tec.",
        "Notas Tec.", "Notas Equipo", "Notas Brida", "Notas Tornillos",
        "Notas Tuercas", "Notas Placa", "Notas Junta", "Notas Tapones",
        "Notas Extractor"]),
    ("Fotos y Planos", ["Fotos", "Fotos 2", "Ruta Dim.", "Ruta OF"]),
]


# ════════════════════════════════════════════════════════════════════════════
# 3) Proyectos — tabla, dashboard y analítica
# ════════════════════════════════════════════════════════════════════════════

def project_list() -> list[dict]:
    """Tabla de proyectos (uno por pedido base) — reutiliza monitoring."""
    return monitoring.get_status_global()


def project_dashboard(pedido: str) -> dict | None:
    """Dashboard de un pedido: KPIs, fases (consulta) y TODOS sus documentos."""
    pedido = (pedido or "").strip()
    if not pedido:
        return None
    docs = monitoring.get_monitoring_data(pedido=pedido)
    if not docs:
        return None

    kpis = monitoring.compute_kpis(docs)

    # Datos de cabecera (primer doc) + fases desde consulta_erp
    first = docs[0]
    cliente = str(first.get("Cliente", "") or "")
    consulta_rows = consulta(pedido)
    phases = consulta_phases(consulta_rows[0]) if consulta_rows else []
    consulta_info = consulta_rows[0] if consulta_rows else {}

    # avg días respuesta (devoluciones con días > 0)
    dias_vals = [
        n for n in (_num(d.get("Días Devolución")) for d in docs)
        if n is not None and n > 0
    ]
    avg_dias = round(sum(dias_vals) / len(dias_vals), 1) if dias_vals else 0

    return {
        "pedido": pedido,
        "cliente": cliente,
        "kpis": kpis,
        "avg_dias_respuesta": avg_dias,
        "phases": phases,
        "consulta": consulta_info,
        "documents": docs,
        "total": len(docs),
        "seguimiento": _prediccion_for_group(docs),
    }


# ── Analítica (porte de analytics_service) ──────────────────────────────────

ESTADOS_APROBADOS = ("aprobado",)
ESTADOS_DEVOLUCION = ("com. menores", "com. mayores", "rechazado", "comentado")


def get_seguimiento() -> list[dict]:
    """Predicción por pedido (curva-S): pct real vs esperado, fecha estimada."""
    docs = monitoring.get_monitoring_data()
    return _prediccion_pedidos(docs)


def _prediccion_for_group(docs: list[dict]) -> dict:
    """Predicción curva-S de un conjunto de documentos tratado como un pedido."""
    total = len(docs)
    aprobados = sum(1 for d in docs if "aprobado" in str(d.get("Estado", "") or "").lower())
    fecha_pedido = fecha_prevista = None
    for d in docs:
        if fecha_pedido is None:
            fecha_pedido = _parse_date(d.get("Fecha Pedido"))
        if fecha_prevista is None:
            fecha_prevista = _parse_date(d.get("Fecha Prevista"))
        if fecha_pedido and fecha_prevista:
            break

    pendientes = total - aprobados
    pct = round(aprobados / total * 100) if total > 0 else 0
    hoy = datetime.now()
    dias_transcurridos = max((hoy.date() - fecha_pedido.date()).days, 1) if fecha_pedido else None

    prediccion_fecha = dias_restantes = None
    if dias_transcurridos and aprobados > 0 and pendientes > 0:
        velocidad = aprobados / dias_transcurridos
        dias_restantes = round(pendientes / velocidad)
        prediccion_fecha = (hoy + timedelta(days=dias_restantes)).strftime("%d/%m/%Y")

    fecha_prevista_str = en_plazo = pct_esperado = None
    if fecha_prevista:
        fecha_prevista_str = fecha_prevista.strftime("%d/%m/%Y")
        if dias_restantes is not None:
            en_plazo = (hoy + timedelta(days=dias_restantes)).date() <= fecha_prevista.date()
        if fecha_pedido and dias_transcurridos is not None:
            duracion = max((fecha_prevista.date() - fecha_pedido.date()).days, 1)
            pct_esperado = round(min(max(dias_transcurridos / duracion * 100, 0), 100))

    return {
        "total": total, "aprobados": aprobados, "pendientes": pendientes, "pct": pct,
        "pct_esperado": pct_esperado, "prediccion_fecha": prediccion_fecha,
        "dias_restantes": dias_restantes, "fecha_prevista": fecha_prevista_str,
        "en_plazo": en_plazo,
    }


def _prediccion_pedidos(docs: list[dict]) -> list[dict]:
    grupos: dict[str, list] = defaultdict(list)
    for doc in docs:
        pedido = str(doc.get("Nº Pedido", "") or "").strip()
        if pedido:
            grupos[pedido].append(doc)
    result = []
    for pedido, items in grupos.items():
        r = _prediccion_for_group(items)
        r["pedido"] = pedido
        result.append(r)
    result.sort(key=lambda x: x["pct"])
    return result
