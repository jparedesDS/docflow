"""La pestaña de envíos programados."""

from __future__ import annotations

import logging
import threading
from datetime import datetime

import customtkinter as ctk
from tkinter import messagebox

from core.config import APP_NAME
from core.services import scheduled_reports as sched_service
from gui import theme
from gui.widgets import ui
from gui.widgets.scrollframe import ScrollFrame

from gui.views.reportes.dialogos import (
    EditScheduleDialog,
)

logger = logging.getLogger(__name__)


class ProgramadosMixin:
    """La pestaña de envíos programados: qué sale solo, cuándo y a quién."""

    def _build_tab_scheduled(self, parent) -> None:
        # Aviso
        info = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=10,
                            border_width=1, border_color=theme.BORDER)
        info.pack(fill="x", pady=(8, 12))
        ctk.CTkLabel(
            info,
            text=("ℹ  Los reportes programados se ejecutan en segundo plano mientras "
                  f"{APP_NAME} está abierto. Si cierras la app, los envíos se pausan."),
            font=theme.FONT_BODY, text_color=theme.TEXT_SUB,
            anchor="w", justify="left", wraplength=700,
        ).pack(fill="x", padx=14, pady=10)

        # Toolbar
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 8))
        ui.button(toolbar, "↻ Recargar", "secondary", height=32,
                  command=self._reload_schedules).pack(side="left")

        # Lista
        self.schedules_scroll = ScrollFrame(parent)
        self.schedules_scroll.pack(fill="both", expand=True)

        self._reload_schedules()

    def _reload_schedules(self) -> None:
        for w in self.schedules_scroll.winfo_children():
            w.destroy()
        self._schedule_rows.clear()
        for sched in sched_service.list_schedules():
            self._render_schedule_card(sched)

    def _render_schedule_card(self, sched: dict) -> None:
        enabled = bool(sched.get("enabled"))
        card = ctk.CTkFrame(
            self.schedules_scroll,
            fg_color=theme.BG_CARD, corner_radius=10,
            border_width=1, border_color=theme.ACCENT if enabled else theme.BORDER,
        )
        card.pack(fill="x", pady=4)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 4))

        # Toggle enabled
        var = ctk.BooleanVar(value=enabled)
        sw = ctk.CTkSwitch(
            top, text="", variable=var, width=44,
            progress_color=theme.ACCENT,
            command=lambda sid=sched["id"], v=var, c=card: self._toggle_enabled(sid, v.get(), c),
        )
        sw.pack(side="left", padx=(0, 12))

        # Titulo + descripción
        title_box = ctk.CTkFrame(top, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            title_box, text=sched["title"],
            font=theme.font(13, "bold"),
            text_color=theme.TEXT_MAIN, anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, text=sched.get("description") or "",
            font=theme.font(11), text_color=theme.TEXT_SUB, anchor="w",
        ).pack(anchor="w")

        # Acciones
        ui.button(top, "✏ Editar", "outline", size="xs", width=80, height=30,
                  font=theme.FONT_BUTTON, text_color=theme.TEXT_SUB,
                  command=lambda s=sched: self._open_edit_dialog(s)).pack(side="right", padx=4)
        ui.button(top, "▶ Ejecutar ahora", "primary", size="xs", width=130, height=30,
                  font=theme.FONT_BUTTON,
                  command=lambda sid=sched["id"]: self._run_now(sid)).pack(side="right", padx=4)

        # Footer: horario + last_run
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            footer, text=f"⏰  {sched_service.format_next_run(sched)}",
            font=theme.font(11),
            text_color=theme.TEXT_MAIN if enabled else theme.TEXT_MUTED,
            anchor="w",
        ).pack(side="left", padx=(56, 0))

        last_run = sched.get("last_run")
        if last_run:
            ts = last_run.get("timestamp", "")
            status = last_run.get("status", "")
            try:
                dt = datetime.fromisoformat(ts)
                ts_label = dt.strftime("%d %b %H:%M")
            except Exception:
                ts_label = ts[:16]
            icon = "✓" if status == "success" else "✗"
            color = theme.GREEN if status == "success" else theme.RED
            ctk.CTkLabel(
                footer, text=f"  ·  Último: {icon} {ts_label}",
                font=theme.font(11), text_color=color, anchor="w",
            ).pack(side="left")

        # Recipients
        recipients = sched.get("recipients") or {}
        to = recipients.get("to") or []
        cc = recipients.get("cc") or []
        if sched["type"] in ("executive", "interactive",
                              "interactive_executive") and (to or cc):
            recip_text = f"To: {', '.join(to)}" + (f" · Cc: {', '.join(cc)}" if cc else "")
            ctk.CTkLabel(
                footer, text=f"  ·  {recip_text}",
                font=theme.font(10), text_color=theme.TEXT_MUTED, anchor="w",
            ).pack(side="left")
        elif sched["type"] in ("personal", "teams_personal"):
            uf = (sched.get("options") or {}).get("user_filter", "all")
            filter_text = "Todo el equipo" if uf == "all" else f"Filtro: {uf}"
            ctk.CTkLabel(
                footer, text=f"  ·  {filter_text}",
                font=theme.font(10), text_color=theme.TEXT_MUTED, anchor="w",
            ).pack(side="left")

        self._schedule_rows[sched["id"]] = {"card": card, "switch": sw, "var": var}

    def _toggle_enabled(self, schedule_id: str, enabled: bool, card_widget) -> None:
        sched_service.update_schedule(schedule_id, {"enabled": enabled})
        card_widget.configure(border_color=theme.ACCENT if enabled else theme.BORDER)
        self.lbl_status.configure(
            text=f"{'Activado' if enabled else 'Desactivado'} schedule '{schedule_id}'",
            text_color=theme.GREEN if enabled else theme.TEXT_MUTED,
        )

    def _run_now(self, schedule_id: str) -> None:
        if not messagebox.askyesno("Ejecutar ahora", f"¿Ejecutar el reporte '{schedule_id}' ahora?"):
            return

        self.lbl_status.configure(text=f"⏳  Ejecutando {schedule_id}…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                res = sched_service.execute_schedule(schedule_id)
                ui.en_ui(self, lambda: self._on_run_done(schedule_id, res))
            except Exception as exc:
                err = str(exc)
                ui.en_ui(self, lambda: self._on_run_error(schedule_id, err))

        threading.Thread(target=worker, daemon=True).start()

    def _on_run_done(self, schedule_id: str, res: dict) -> None:
        if res.get("status") == "success":
            self.lbl_status.configure(text=f"✓  {schedule_id} ejecutado", text_color=theme.GREEN)
            messagebox.showinfo("Ejecutado", f"✓ {schedule_id} ejecutado correctamente.\n\n{res.get('result', '')}")
        else:
            self.lbl_status.configure(text=f"✗  {res.get('error')}", text_color=theme.RED)
            messagebox.showerror("Error", res.get("error", "Error desconocido"))
        self._reload_schedules()

    def _on_run_error(self, schedule_id: str, msg: str) -> None:
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)
        messagebox.showerror("Error", msg)

    def _open_edit_dialog(self, sched: dict) -> None:
        EditScheduleDialog(self, sched=sched, on_save=self._reload_schedules)
