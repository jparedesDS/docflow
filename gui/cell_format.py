"""Formateadores de celda compartidos para las tablas.

La información va codificada en el SÍMBOLO (forma) además del color, de modo
que sigue siendo legible en escala de grises o para personas daltónicas.
"""

from __future__ import annotations

# ── Urgencia (reclamaciones) → icono ─────────────────────────────────────────

_URGENCY_ICONS = {"high": "⚠", "medium": "◑", "low": "○"}


def urgency_with_icon(label: str, urgency_key: str) -> str:
    """'ALTA' + 'high' → '⚠  ALTA'."""
    icon = _URGENCY_ICONS.get(urgency_key, "")
    return f"{icon}  {label}" if icon else label
