"""La pestaña de resúmenes por persona."""

from __future__ import annotations

import logging
import tempfile
import threading
import webbrowser

import customtkinter as ctk
from tkinter import messagebox

from core.config import USERS
from core.services import weekly_summary as weekly_service
from gui import theme
from gui.widgets import ui

from gui.views.reportes.dialogos import (
    SendExecutiveDialog,
    SendPersonalDialog,
)

logger = logging.getLogger(__name__)


class ResumenesMixin:
    """La pestaña de resúmenes por persona, con su preview y su envío."""

    def _build_tab_summaries(self, parent) -> None:
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="both", expand=True, pady=8)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="cols")

        self._build_summary_card(
            grid, 0, 0,
            title="Resumen Monitoring Report",
            icon="📈", color=theme.ACCENT,
            desc="Email ejecutivo semanal con KPIs y párrafo narrativo. Sin la API key de Claude se usa un fallback textual.",
            kind="executive",
        )
        self._build_summary_card(
            grid, 0, 1,
            title="Monitoring Report (Personal)",
            icon="✉", color=theme.GREEN,
            desc="Email individual por doc controller con sus pendientes (Com. Menores/Mayores · Comentado · Rechazado · Sin Enviar) y KPIs. También se puede publicar en Teams por persona.",
            kind="personal",
        )

    def _build_summary_card(self, parent, row: int, col: int, *,
                            title: str, icon: str, color: str, desc: str, kind: str) -> None:
        card = ctk.CTkFrame(
            parent, fg_color=theme.BG_CARD, corner_radius=12,
            border_width=1, border_color=theme.BORDER,
        )
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=18)

        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text=icon,
                     font=theme.font(22), text_color=color).pack(side="left")
        ctk.CTkLabel(title_row, text=title,
                     font=theme.font(15, "bold"),
                     text_color=theme.TEXT_MAIN, anchor="w").pack(side="left", padx=(8, 0))

        ctk.CTkLabel(inner, text=desc, wraplength=380,
                     font=theme.FONT_BODY, text_color=theme.TEXT_SUB,
                     justify="left", anchor="w").pack(anchor="w", pady=(8, 14), fill="x")

        # Selector de usuario sólo para el reporte personal
        preview_user_var: ctk.StringVar | None = None
        if kind == "personal":
            picker_row = ctk.CTkFrame(inner, fg_color="transparent")
            picker_row.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(
                picker_row, text="Previsualizar para:",
                font=theme.font(10, "bold"),
                text_color=theme.TEXT_MUTED,
            ).pack(side="left")
            preview_user_var = ctk.StringVar(value="JP")
            options = [f"{k} — {v['nombre']}" for k, v in sorted(USERS.items())]
            picker = ctk.CTkOptionMenu(
                picker_row, values=options, variable=None,
                width=200, height=28, corner_radius=6,
                fg_color=theme.BG_INPUT, button_color=theme.BG_INPUT,
                button_hover_color=theme.BG_CARD, text_color=theme.TEXT_MAIN,
                font=theme.font(11), dropdown_font=theme.font(11),
                command=lambda selected, var=preview_user_var: var.set(selected.split(" — ")[0]),
            )
            picker.set("JP — el administrador")
            picker.pack(side="left", padx=(8, 0))

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(fill="x", side="bottom")
        ui.button(actions, "👁  Preview", "chip", size="lg",
                  command=lambda v=preview_user_var: self._open_preview(kind, v.get() if v else "JP"),
                  ).pack(side="left", fill="x", expand=True)
        ui.button(actions, "📤  Enviar", "primary", size="lg", fg_color=color,
                  command=lambda: self._open_send_dialog(kind),
                  ).pack(side="left", fill="x", expand=True, padx=(8, 0))
        if kind == "personal":
            ui.button(actions, "Teams", "chip", size="lg",
                      command=lambda v=preview_user_var: self._teams_personal(v.get() if v else "JP"),
                      ).pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _open_preview(self, kind: str, initials: str = "JP") -> None:
        label = "Resumen Ejecutivo" if kind == "executive" else f"Personal de {initials}"
        self.lbl_status.configure(text=f"⏳  Generando preview ({label})…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                if kind == "executive":
                    html = weekly_service.get_executive_preview()
                else:
                    html = weekly_service.get_personal_preview(initials)
                ui.en_ui(self, lambda: self._show_preview_html(html, kind, initials))
            except Exception as exc:
                logger.exception("Error preview")
                err = str(exc)
                ui.en_ui(self, lambda: self._show_preview_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _show_preview_html(self, html: str, kind: str, initials: str = "") -> None:
        suffix = f"_{kind}_{initials}_preview.html" if initials else f"_{kind}_preview.html"
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=suffix, delete=False,
        )
        tmp.write(html)
        tmp.close()
        webbrowser.open(f"file://{tmp.name}")
        label = f"({initials})" if initials and kind == "personal" else ""
        self.lbl_status.configure(
            text=f"✓  Preview {label} abierto en navegador",
            text_color=theme.GREEN,
        )

    def _show_preview_error(self, msg: str) -> None:
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)
        messagebox.showerror("Error preview", msg)

    def _open_send_dialog(self, kind: str) -> None:
        if kind == "executive":
            SendExecutiveDialog(self, on_sent=lambda: self._on_sent(kind))
        else:
            SendPersonalDialog(self, on_sent=lambda: self._on_sent(kind))

    def _on_sent(self, kind: str) -> None:
        label = "Resumen ejecutivo" if kind == "executive" else "Resúmenes personales"
        self.lbl_status.configure(text=f"✓  {label} enviados", text_color=theme.GREEN)

    def _teams_personal(self, initials: str) -> None:
        from core.services import teams
        if not teams.is_configured():
            messagebox.showinfo(
                "Teams no configurado",
                "Pega la URL del webhook en Ajustes ▸ Fuentes de datos.")
            return
        self.lbl_status.configure(
            text=f"⏳  Publicando pendientes de {initials} en Teams…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                res = weekly_service.post_personal_to_teams(initials)
                ui.en_ui(self, lambda: self._teams_personal_done(res, initials))
            except Exception as exc:
                logger.exception("Error Teams personal")
                err = str(exc)
                ui.en_ui(self, lambda: self.lbl_status.configure(text=f"✗  {err}", text_color=theme.RED))

        threading.Thread(target=worker, daemon=True).start()

    def _teams_personal_done(self, res: dict, initials: str) -> None:
        if res.get("ok"):
            self.lbl_status.configure(
                text=f"✓  Pendientes de {initials} publicados en Teams.", text_color=theme.GREEN)
        else:
            self.lbl_status.configure(
                text=f"✗  {res.get('error', 'Error')}", text_color=theme.RED)
