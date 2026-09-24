"""Centro de Reportes: la ventana y sus pestañas.

Aquí solo está el esqueleto; lo que hace cada pestaña vive en su módulo.
"""

from __future__ import annotations

import logging

import customtkinter as ctk

from gui import theme
from gui.widgets import ui

from gui.views.reportes.interactivos import (
    InteractivosMixin,
)
from gui.views.reportes.excels import (
    ExcelsMixin,
)
from gui.views.reportes.resumenes import (
    ResumenesMixin,
)
from gui.views.reportes.programados import (
    ProgramadosMixin,
)

logger = logging.getLogger(__name__)


class ReportesView(InteractivosMixin, ExcelsMixin, ResumenesMixin, ProgramadosMixin, ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_PAGE, **kwargs)
        self._busy_id: str | None = None
        self._excel_cards: dict[str, dict] = {}
        self._schedule_rows: dict[str, dict] = {}
        self._build_layout()

    def _build_layout(self) -> None:
        # Header
        ui.page_header(
            self, "Centro de Reportes",
            "Genera Excels e informes web, envía resúmenes por email o Teams y programa envíos automáticos.",
            help_key="reportes")

        # Status line global
        self.lbl_status = ctk.CTkLabel(
            self, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, anchor="w",
        )
        self.lbl_status.pack(fill="x", padx=theme.SPACE_6, pady=(theme.SPACE_2, 0))

        # Tabs
        self.tabs = ui.tabview(self)
        self.tabs.pack(fill="both", expand=True,
                       padx=theme.SPACE_5, pady=(theme.SPACE_3, theme.SPACE_4))

        # Pestañas perezosas: cada una se construye la primera vez que se abre
        # (abrir la vista pasa de ~530 ms a construir solo "Excels").
        # 3 pestañas: Informes (Excel + web) · Resúmenes por email · Programados.
        # Las fuentes de datos y el refresco del ERP viven en Ajustes ▸ Fuentes de datos.
        frames = ui.lazy_tabs(self.tabs, {
            "Informes": self._build_tab_informes,
            "Resúmenes por email": self._build_tab_summaries,
            "Programados": self._build_tab_scheduled,
        })
        self.tab_informes = frames["Informes"]
        self.tab_summaries = frames["Resúmenes por email"]
        self.tab_scheduled = frames["Programados"]
