"""Detalle de un equipo: sus documentos y sus órdenes de taller."""

import logging

import customtkinter as ctk

from core.services import erp as erp_service
from gui import theme
from gui.views.documentos import _status_color
from gui.widgets import ui
from gui.widgets.scrollframe import ScrollFrame

from gui.views.pedidos.comun import (
    _norm_doc,
    _section_header,
)

logger = logging.getLogger(__name__)


class TagDetailWindow(ctk.CTkToplevel):
    # Claves de resumen que no se repiten en las secciones
    _SKIP = {"TAG", "Nº Pedido", "Familia", "Tamaño", "OTs", "Docs"}

    def __init__(self, master, tag: dict, doc_state=None, on_open_documento=None):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self._doc_state = doc_state or (lambda _n: ("?", "", ""))
        self._on_open_documento = on_open_documento
        self.title(f"Equipo  ·  {tag.get('TAG', '—')}")
        self.geometry("860x740")
        self.minsize(560, 480)
        self.transient(master)
        self.grab_set()
        self._build(tag)

    def _build(self, tag: dict) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 6))
        ctk.CTkLabel(header, text=str(tag.get("TAG", "—")), font=theme.font(18, "bold"),
                     text_color=theme.ACCENT, anchor="w").pack(anchor="w")
        sub = " · ".join(str(tag.get(k, "")) for k in ("Familia", "Tipo", "Nº Pedido", "Estado")
                         if str(tag.get(k, "") or ""))
        ctk.CTkLabel(header, text=sub, font=theme.FONT_SMALL,
                     text_color=theme.TEXT_SUB, anchor="w").pack(anchor="w", pady=(2, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=22, pady=(0, 14))
        ui.button(footer, "Cerrar", "secondary", size="lg", command=self.destroy).pack(side="right")

        scroll = ScrollFrame(self, fg_color=theme.BG_CARD)
        scroll.pack(side="top", fill="both", expand=True, padx=22, pady=(8, 12))

        self._docs_block(scroll, tag)
        self._ots_block(scroll, tag)

        shown: set[str] = set(self._SKIP)
        for title, keys in erp_service.TAGS_DETAIL_SECTIONS:
            visibles = [(k, tag.get(k, "")) for k in keys
                        if str(tag.get(k, "") or "").strip() not in ("", "0", "0.0", "—")]
            shown.update(keys)
            if visibles:
                self._section(scroll, title, visibles)
        # Resto de campos con etiqueta (temperatura / nivel / otros)
        rest = [(k, v) for k, v in tag.items()
                if not k.startswith("_") and k not in shown
                and str(v or "").strip() not in ("", "0", "0.0", "—")]
        if rest:
            self._section(scroll, "Otros datos del equipo", rest)

    def _section(self, scroll, title: str, items: list) -> None:
        _section_header(scroll, title).pack(fill="x", padx=14, pady=(theme.SPACE_3, theme.SPACE_1))
        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, theme.SPACE_1))
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="d")
        for i, (k, v) in enumerate(items):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=i // 3, column=i % 3, sticky="ew", padx=(0, theme.SPACE_3), pady=2)
            ctk.CTkLabel(cell, text=k, font=theme.FONT_TINY, text_color=theme.TEXT_MUTED,
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(cell, text=str(v), font=theme.FONT_SMALL, text_color=theme.TEXT_MAIN,
                         anchor="w", justify="left", wraplength=230).pack(anchor="w")

    def _docs_block(self, scroll, tag: dict) -> None:
        docs = [(lab, tag.get(key, "")) for lab, key in
                (("Cálculo", "Doc EIPSA Calc."), ("Plano", "Doc EIPSA Plano"))]
        docs = [(lab, num) for lab, num in docs if num]
        _section_header(scroll, "Documentación EIPSA enlazada").pack(
            fill="x", padx=14, pady=(theme.SPACE_3, theme.SPACE_1))
        if not docs:
            ctk.CTkLabel(scroll, text="Este equipo no tiene cálculo ni plano EIPSA asignados en el ERP.",
                         font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, anchor="w").pack(
                fill="x", padx=14, pady=(0, theme.SPACE_1))
            return
        for lab, num in docs:
            sym, est, eipsa = self._doc_state(num)
            # Si el ERP guardó el nº del cliente, mostrar también el nº EIPSA resuelto
            shown = num if (not eipsa or _norm_doc(eipsa) == _norm_doc(num)) else f"{num}  →  {eipsa}"
            r = ctk.CTkFrame(scroll, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=1)
            ctk.CTkLabel(r, text=lab, font=theme.FONT_TINY, text_color=theme.TEXT_MUTED,
                         width=60, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=shown, font=theme.FONT_SMALL_BOLD, text_color=theme.ACCENT,
                         width=260, anchor="w").pack(side="left")
            if sym == "?":
                ctk.CTkLabel(r, text="no figura en Documentos", font=theme.FONT_SMALL,
                             text_color=theme.TEXT_MUTED, anchor="w").pack(side="left", fill="x", expand=True)
            else:
                ecol = _status_color(est)
                ctk.CTkLabel(r, text=f" {sym} {est or 'Sin enviar'} ", font=theme.FONT_TINY,
                             text_color=ecol, fg_color=ui.blend(ecol, theme.BG_CARD, 0.20),
                             corner_radius=7, height=20).pack(side="left")
            if self._on_open_documento:
                ui.button(r, "Ver en Documentos  →", "outline", size="xs", font=theme.FONT_TINY,
                          command=lambda n=(eipsa or num): (self.destroy(), self._on_open_documento(n))
                          ).pack(side="right")

    def _ots_block(self, scroll, tag: dict) -> None:
        ots = tag.get("_ots") or []
        _section_header(scroll, "Órdenes de fabricación").pack(
            fill="x", padx=14, pady=(theme.SPACE_3, theme.SPACE_1))
        if not ots:
            ctk.CTkLabel(scroll, text="Sin órdenes de trabajo registradas para este equipo.",
                         font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, anchor="w").pack(
                fill="x", padx=14, pady=(0, theme.SPACE_1))
            return
        for o in ots:
            r = ctk.CTkFrame(scroll, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=1)
            done = o["terminada"]
            ctk.CTkLabel(r, text="✓" if done else "•", font=theme.FONT_SMALL,
                         text_color=theme.GREEN if done else theme.AMBER, width=16).pack(side="left")
            ctk.CTkLabel(r, text=f"OT {o['ot']}", font=theme.FONT_SMALL_BOLD, text_color=theme.ACCENT,
                         width=90, anchor="w").pack(side="left")
            what = " · ".join(x for x in (o["plano"], o["elemento"],
                                          f"x{o['cantidad']}" if o["cantidad"] else "") if x)
            ctk.CTkLabel(r, text=what, font=theme.FONT_SMALL, text_color=theme.TEXT_MAIN,
                         anchor="w").pack(side="left", fill="x", expand=True)
            when = (f"{o['inicio']} → {o['fin']}" if done
                    else (f"desde {o['inicio']}" if o["inicio"] else "sin fecha"))
            ctk.CTkLabel(r, text=when, font=theme.FONT_TINY, text_color=theme.TEXT_MUTED).pack(side="right")
