"""Piezas sueltas de la sección de pedidos.

Colores por fase y por estado, conversiones de fecha y número, y los
ladrillos de layout (tarjeta, regla, campo, rejilla de campos).
"""

import logging
import re

import customtkinter as ctk

from gui import theme
from gui.widgets import ui

logger = logging.getLogger(__name__)
# ── Helpers ───────────────────────────────────────────────────────────────────
_section_header = ui.section_header  # design system compartido


def _phase_color(pct: int) -> str:
    if pct >= 100:
        return theme.GREEN
    if pct > 0:
        return theme.AMBER
    return theme.RED


# Columnas de la tabla de equipos, con el mismo formato que la de Documentos:
# key · etiqueta de cabecera · ancho mínimo · estira · alineación.
TAG_COLS = [
    {"key": "Familia",    "label": "Familia",    "min": 104, "anchor": "w"},
    {"key": "TAG",        "label": "TAG",        "min": 168, "anchor": "w"},
    {"key": "Tipo",       "label": "Tipo",       "min": 140, "anchor": "w", "stretch": True},
    {"key": "Tamaño",     "label": "Tamaño",     "min": 66,  "anchor": "center"},
    {"key": "Rating",     "label": "Rating",     "min": 60,  "anchor": "center"},
    {"key": "Facing",     "label": "Facing",     "min": 60,  "anchor": "center"},
    {"key": "Estado",     "label": "Estado",     "min": 116, "anchor": "center"},
    {"key": "Fab.",       "label": "Fabricación", "min": 116, "anchor": "center"},
    {"key": "Insp.",      "label": "Insp.",      "min": 84,  "anchor": "center"},
    {"key": "Plano Dim.", "label": "Plano dim.", "min": 146, "anchor": "w"},
    {"key": "OTs",        "label": "OTs",        "min": 72,  "anchor": "center"},
    {"key": "Docs",       "label": "Docs",       "min": 132, "anchor": "w"},
]


# Equipos por página. Un pedido puede traer cientos y la tabla crea un widget
# por celda: pintarlos todos deja a Tk sin completar el layout (salía en blanco).
TAGS_PAGE_SIZE = 20


# Color del símbolo de estado documental que se pinta en la columna «Docs»
_DOC_SYM_COLOR = {"✓": theme.GREEN, "✕": theme.RED, "⚠": theme.AMBER,
                  "⏳": theme.BLUE, "○": theme.TEXT_MUTED, "?": theme.TEXT_MUTED}


def _tag_state_color(estado: str, vigente: bool, eliminado: bool) -> str:
    """Color del estado de un equipo. Lo que ya no cuenta, apagado."""
    if eliminado:
        return theme.RED
    if not vigente:
        return theme.TEXT_MUTED
    e = str(estado or "").upper()
    if "INVOIC" in e or "PURCHASED" in e:
        return theme.GREEN
    if "DELETED" in e or "RECHAZ" in e:
        return theme.RED
    return theme.BLUE


def _to_int(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _norm_doc(s) -> str:
    """Nº de documento comparable: sin espacios y en mayúsculas."""
    return re.sub(r"\s+", "", str(s or "")).upper()


def _date(v) -> str:
    """Fecha del ERP → '14-10-2024'. El Timestamp de pandas arrastra la hora."""
    if v is None or v == "":
        return ""
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return s.split(" ")[0][:24]


def _num(v) -> str:
    """Número del ERP → texto sin decimal de más ('272.0' → '272').

    Ojo con el cero: es un valor válido, no un hueco (un 0 % es «0 %»).
    """
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    try:
        f = float(s)
        return f"{int(f)}" if f == int(f) else f"{f:g}"
    except (TypeError, ValueError):
        return s


def _card(parent, **kw):
    """Tarjeta base: fondo, borde fino y esquinas del sistema."""
    return ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_LG,
                        border_width=1, border_color=theme.BORDER, **kw)


def _rule(parent, pady=theme.SPACE_3):
    ctk.CTkFrame(parent, fg_color=theme.BORDER, height=1).pack(fill="x", pady=pady)


def _field(parent, label: str, value: str, *, color: str | None = None,
           wrap: int = 330) -> None:
    """Fila compacta de ficha: rótulo pequeño arriba, dato grande debajo."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=(0, theme.SPACE_2))
    ctk.CTkLabel(row, text=str(label).upper(), font=theme.FONT_LABEL,
                 text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
    ctk.CTkLabel(row, text=str(value) if value not in ("", None) else "—",
                 font=theme.font(14, "bold"), text_color=color or theme.TEXT_MAIN,
                 anchor="w", justify="left", wraplength=wrap).pack(anchor="w")


def _fields_grid(parent, campos: list, ncols: int = 2) -> None:
    """Reparte los campos en columnas para que la ficha no se haga interminable.

    Se llenan por columnas (no por filas): así se lee de arriba abajo y el
    orden de los campos se mantiene."""
    grid = ctk.CTkFrame(parent, fg_color="transparent")
    grid.pack(fill="x")
    ncols = max(1, min(ncols, len(campos)))
    for c in range(ncols):
        grid.grid_columnconfigure(c, weight=1, uniform="fic")
    por_col = -(-len(campos) // ncols)          # techo de la división
    for c in range(ncols):
        col = ctk.CTkFrame(grid, fg_color="transparent")
        col.grid(row=0, column=c, sticky="nsew", padx=(0, theme.SPACE_3 if c < ncols - 1 else 0))
        for lab, val, color in campos[c * por_col:(c + 1) * por_col]:
            _field(col, lab, val, color=color, wrap=200 if ncols > 1 else 330)
