"""La pestaña de Excel del Centro de Reportes."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.services import monitoring as monitoring_service
from core.services import reports as reports_service
from gui import theme
from gui.widgets import ui
from gui.widgets.scrollframe import ScrollFrame

from gui.views.reportes.comun import (
    EXCEL_REPORTS,
    _fmt_size,
    _open_path,
)

logger = logging.getLogger(__name__)


class ExcelsMixin:
    """La pestaña de Excel: el Monitoring Report y los demás listados."""

    def _build_tab_excels(self, parent, container=None) -> None:
        scroll = container or ScrollFrame(parent)
        if container is None:
            scroll.pack(fill="both", expand=True)

        # Excel
        ctk.CTkLabel(scroll, text="HOJAS DE CÁLCULO (EXCEL)", font=theme.font(10, "bold"),
                     text_color=theme.TEXT_MUTED, anchor="w").pack(fill="x", pady=(4, 6))
        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="cols")
        for i, report in enumerate(EXCEL_REPORTS):
            row, col = divmod(i, 2)
            self._excel_cards[report["id"]] = self._build_excel_card(grid, row, col, report)

    def _build_excel_card(self, parent, row: int, col: int, report: dict) -> dict:
        card = ctk.CTkFrame(
            parent, fg_color=theme.BG_CARD, corner_radius=12,
            border_width=1, border_color=theme.BORDER,
        )
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=18)

        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text=report["icon"],
                     font=theme.font(22), text_color=report["color"]).pack(side="left")
        ctk.CTkLabel(title_row, text=report["title"],
                     font=theme.font(15, "bold"),
                     text_color=theme.TEXT_MAIN, anchor="w").pack(side="left", padx=(8, 0))

        ctk.CTkLabel(inner, text=report["desc"], wraplength=380,
                     font=theme.FONT_BODY, text_color=theme.TEXT_SUB,
                     justify="left", anchor="w").pack(anchor="w", pady=(8, 12), fill="x")

        lbl_card = ctk.CTkLabel(inner, text="", font=theme.font(10),
                                text_color=theme.TEXT_MUTED, anchor="w")
        lbl_card.pack(anchor="w", pady=(0, 8))

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(fill="x", side="bottom")
        btn_download = ui.button(actions, "⬇  Descargar", "primary", size="lg",
                                 command=lambda r=report: self._on_download_excel(r))
        btn_download.pack(side="left", fill="x", expand=True)

        return {"card": card, "lbl": lbl_card, "btn": btn_download, "last_path": None}

    def _on_download_excel(self, report: dict) -> None:
        if self._busy_id is not None:
            return
        default_name = report["filename"].format(date=datetime.now().strftime("%Y-%m-%d"))
        path = filedialog.asksaveasfilename(
            parent=self, title=f"Guardar {report['title']}",
            defaultextension=".xlsx", initialfile=default_name,
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")],
        )
        if not path:
            return

        self._busy_id = report["id"]
        card = self._excel_cards[report["id"]]
        card["btn"].configure(state="disabled", text="Generando…")
        card["lbl"].configure(text="⏳  Generando Excel…",
                              text_color=theme.TEXT_MUTED)
        self.lbl_status.configure(text=f"Generando {report['title']}…", text_color=theme.TEXT_MUTED)

        rid = report["id"]
        title = report["title"]

        def worker():
            try:
                if rid == "monitoring":
                    sections = monitoring_service.get_monitoring_report_sections()
                    if not sections.get("all_docs"):
                        raise RuntimeError("No hay documentos en data_erp.xlsx")
                    data = reports_service.generate_monitoring_excel(sections)
                elif rid == "export":
                    docs = monitoring_service.get_monitoring_data()
                    if not docs:
                        raise RuntimeError("No hay documentos en data_erp.xlsx")
                    data = reports_service.generate_export_excel(docs)
                else:
                    raise ValueError(f"Reporte desconocido: {rid}")
                with open(path, "wb") as f:
                    f.write(data)
                ui.en_ui(self, lambda: self._on_excel_done(rid, path, title))
            except Exception as exc:
                logger.exception("Error generando %s", rid)
                err = str(exc)
                ui.en_ui(self, lambda: self._on_excel_error(rid, err))

        threading.Thread(target=worker, daemon=True).start()

    def _on_excel_done(self, rid: str, path: str, title: str) -> None:
        self._busy_id = None
        card = self._excel_cards[rid]
        card["last_path"] = path
        card["btn"].configure(state="normal", text="⬇  Descargar")
        card["lbl"].configure(text=f"✓  {os.path.basename(path)}  ·  {_fmt_size(path)}",
                              text_color=theme.GREEN)
        self.lbl_status.configure(text=f"✓  {title} guardado en {path}", text_color=theme.GREEN)
        ans = messagebox.askyesnocancel(
            "Archivo generado",
            f"{title} guardado correctamente.\n\n📂 {path}\n\n"
            "¿Abrir el archivo ahora? (No: abrir carpeta · Cancelar: nada)",
        )
        if ans is True:
            _open_path(path)
        elif ans is False:
            _open_path(str(Path(path).parent))

    def _on_excel_error(self, rid: str, msg: str) -> None:
        self._busy_id = None
        card = self._excel_cards[rid]
        card["btn"].configure(state="normal", text="⬇  Descargar")
        card["lbl"].configure(text=f"✗  {msg}", text_color=theme.RED)
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)
        messagebox.showerror("Error generando reporte", msg)
