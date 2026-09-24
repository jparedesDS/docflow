"""Piezas sueltas del Centro de Reportes.

El catálogo de Excel que se puede descargar y el formato de tamaños de fichero.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys


from gui import theme

logger = logging.getLogger(__name__)
EXCEL_REPORTS = [
    {
        "id": "monitoring",
        "kind": "excel",
        "icon": "📊",
        "color": theme.BLUE,
        "title": "Monitoring Report",
        "desc": ("Excel multi-hoja con secciones ALL DOC. / ENVIADOS / DEVOLUCIONES / "
                 "CRÍTICOS / CRÍTICOS +15d / SIN ENVIAR + STATUS GLOBAL con gráfico."),
        "filename": "Monitoring_Report_{date}.xlsx",
    },
    {
        "id": "export",
        "kind": "excel",
        "icon": "📥",
        "color": theme.GREEN,
        "title": "Export Excel (simple)",
        "desc": "Excel plano con todos los documentos + hoja de resumen por estado.",
        "filename": "Export_DocFlow_{date}.xlsx",
    },
]


def _fmt_size(path: str) -> str:
    try:
        return _fmt_size_bytes(os.path.getsize(path))
    except Exception:
        return ""


def _fmt_size_bytes(size: int | float) -> str:
    try:
        size = int(size)
        if size < 1024:
            return f"{size} B"
        if size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"
        if size < 1024 ** 3:
            return f"{size / 1024 ** 2:.1f} MB"
        return f"{size / 1024 ** 3:.1f} GB"
    except Exception:
        return ""


def _open_path(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception as exc:
        logger.warning("No se pudo abrir %s: %s", path, exc)
