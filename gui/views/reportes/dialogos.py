"""Diálogos del Centro de Reportes.

Elegir destinatarios de un informe ejecutivo o de un resumen personal, y editar
un envío programado.
"""

from __future__ import annotations

import logging
import threading

import customtkinter as ctk
from tkinter import messagebox

from core.config import USERS
from core.services import scheduled_reports as sched_service
from core.services import weekly_summary as weekly_service
from gui import theme
from gui.widgets import ui

logger = logging.getLogger(__name__)


class SendExecutiveDialog(ctk.CTkToplevel):
    def __init__(self, master, on_sent=None):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self.title("Enviar Resumen Monitoring Report")
        self.geometry("560x340")
        self.minsize(440, 280)
        self.transient(master); self.grab_set()
        self._on_sent = on_sent

        ctk.CTkLabel(
            self, text="Enviar a", font=theme.font(10, "bold"),
            text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(anchor="w", padx=22, pady=(18, 4))
        self.ent_to = ctk.CTkEntry(
            self, placeholder_text="alguien@tuempresa.com, otro@tuempresa.com",
            height=34, corner_radius=8,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_to.pack(fill="x", padx=22, pady=(0, 8))

        ctk.CTkLabel(
            self, text="Copia (Cc)", font=theme.font(10, "bold"),
            text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(anchor="w", padx=22, pady=(8, 4))
        self.ent_cc = ctk.CTkEntry(
            self, placeholder_text="opcional",
            height=34, corner_radius=8,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_cc.pack(fill="x", padx=22, pady=(0, 8))

        ctk.CTkLabel(
            self, text="Sin To se usa la variable WEEKLY_EXECUTIVE_RECIPIENTS del .env.",
            font=theme.font(10), text_color=theme.TEXT_MUTED,
        ).pack(anchor="w", padx=22, pady=(4, 12))

        self.lbl_status = ctk.CTkLabel(self, text="", font=theme.FONT_BODY,
                                       text_color=theme.TEXT_MUTED, anchor="w")
        self.lbl_status.pack(fill="x", padx=22)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=14, side="bottom")
        ui.button(footer, "Cancelar", "secondary", command=self.destroy).pack(side="right", padx=(8, 0))
        self.btn_send = ui.button(footer, "Enviar  →", "primary", command=self._send)
        self.btn_send.pack(side="right")

    def _send(self) -> None:
        to = [s.strip() for s in self.ent_to.get().split(",") if s.strip()]
        cc = [s.strip() for s in self.ent_cc.get().split(",") if s.strip()]
        self.btn_send.configure(state="disabled", text="Enviando…")
        self.lbl_status.configure(text="⏳  Enviando…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                res = weekly_service.send_executive_email(to=to or None, cc=cc or None)
                ui.en_ui(self, lambda: self._done(res))
            except Exception as exc:
                logger.exception("Error envío ejecutivo")
                err = str(exc)
                ui.en_ui(self, lambda: self._error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, res: dict) -> None:
        if res.get("status") == "skipped":
            messagebox.showwarning("No enviado", f"No hay destinatarios configurados.\nIndica al menos un email en 'To'.")
            self.btn_send.configure(state="normal", text="Enviar  →")
            self.lbl_status.configure(text="", text_color=theme.TEXT_MUTED)
            return
        recipients = res.get("recipients", [])
        messagebox.showinfo(
            "Enviado",
            f"✓ Resumen ejecutivo enviado a {len(recipients)} destinatario(s).\n\n"
            f"{', '.join(recipients)}",
        )
        if self._on_sent:
            self._on_sent()
        self.destroy()

    def _error(self, msg: str) -> None:
        self.btn_send.configure(state="normal", text="Enviar  →")
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)
        messagebox.showerror("Error", msg)


class SendPersonalDialog(ctk.CTkToplevel):
    def __init__(self, master, on_sent=None):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self.title("Enviar Monitoring Report Personal")
        self.geometry("560x420")
        self.minsize(440, 320)
        self.transient(master); self.grab_set()
        self._on_sent = on_sent

        ctk.CTkLabel(
            self, text="A quién enviar", font=theme.font(10, "bold"),
            text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(anchor="w", padx=22, pady=(18, 4))

        self.mode = ctk.StringVar(value="all")
        ctk.CTkRadioButton(
            self, text="Todo el equipo (los que tengan docs asignados)",
            variable=self.mode, value="all",
            font=theme.FONT_BODY, text_color=theme.TEXT_MAIN,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self._on_mode_change,
        ).pack(anchor="w", padx=22, pady=2)
        ctk.CTkRadioButton(
            self, text="Solo a usuarios específicos (por iniciales)",
            variable=self.mode, value="filter",
            font=theme.FONT_BODY, text_color=theme.TEXT_MAIN,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self._on_mode_change,
        ).pack(anchor="w", padx=22, pady=2)

        self.ent_filter = ctk.CTkEntry(
            self, placeholder_text="JP, AC, JM",
            height=34, corner_radius=8,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
            state="disabled",
        )
        self.ent_filter.pack(fill="x", padx=46, pady=(0, 8))

        ctk.CTkLabel(
            self, text="Copia adicional (Cc)", font=theme.font(10, "bold"),
            text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(anchor="w", padx=22, pady=(8, 4))
        self.ent_cc = ctk.CTkEntry(
            self, placeholder_text="opcional, se añade a cada email enviado",
            height=34, corner_radius=8,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_cc.pack(fill="x", padx=22, pady=(0, 8))

        # Lista de iniciales disponibles
        users_label = ", ".join(sorted(USERS.keys()))
        ctk.CTkLabel(
            self, text=f"Iniciales disponibles: {users_label}",
            font=theme.font(10), text_color=theme.TEXT_MUTED,
            anchor="w", justify="left", wraplength=500,
        ).pack(anchor="w", padx=22, pady=(4, 12))

        self.lbl_status = ctk.CTkLabel(self, text="", font=theme.FONT_BODY,
                                       text_color=theme.TEXT_MUTED, anchor="w")
        self.lbl_status.pack(fill="x", padx=22)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=14, side="bottom")
        ui.button(footer, "Cancelar", "secondary", command=self.destroy).pack(side="right", padx=(8, 0))
        self.btn_send = ui.button(footer, "Enviar  →", "primary", command=self._send)
        self.btn_send.pack(side="right")

    def _on_mode_change(self) -> None:
        if self.mode.get() == "filter":
            self.ent_filter.configure(state="normal")
        else:
            self.ent_filter.configure(state="disabled")

    def _send(self) -> None:
        cc = [s.strip() for s in self.ent_cc.get().split(",") if s.strip()]
        if self.mode.get() == "all":
            user_filter = "all"
        else:
            raw = self.ent_filter.get().strip()
            if not raw:
                messagebox.showwarning("Sin filtro", "Indica iniciales separadas por coma (ej: JP, AC).")
                return
            user_filter = [s.strip().upper() for s in raw.split(",") if s.strip()]

        confirm = messagebox.askyesno(
            "Confirmar envío",
            f"¿Enviar Monitoring Report Personal?\n\n"
            f"Filtro: {user_filter if user_filter != 'all' else 'Todo el equipo'}\n"
            f"Cc: {', '.join(cc) or '—'}\n\n"
            "Solo se enviará a usuarios que tengan documentos asignados.",
        )
        if not confirm:
            return

        self.btn_send.configure(state="disabled", text="Enviando…")
        self.lbl_status.configure(text="⏳  Enviando…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                res = weekly_service.send_personal_emails(to_cc=cc or None, user_filter=user_filter)
                ui.en_ui(self, lambda: self._done(res))
            except Exception as exc:
                logger.exception("Error envío personal")
                err = str(exc)
                ui.en_ui(self, lambda: self._error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, res: dict) -> None:
        sent_to = res.get("sent_to", [])
        skipped = res.get("skipped", [])
        skipped_line = f"\n\nOmitidos (sin docs): {', '.join(skipped)}" if skipped else ""
        messagebox.showinfo(
            "Enviado",
            f"✓ {len(sent_to)} resumen(es) personal(es) enviado(s).\n\n"
            f"{chr(10).join('  · ' + e for e in sent_to)}"
            f"{skipped_line}",
        )
        if self._on_sent:
            self._on_sent()
        self.destroy()

    def _error(self, msg: str) -> None:
        self.btn_send.configure(state="normal", text="Enviar  →")
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)
        messagebox.showerror("Error", msg)


class EditScheduleDialog(ctk.CTkToplevel):
    def __init__(self, master, sched: dict, on_save=None):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self.title(f"Editar — {sched['title']}")
        self.geometry("560x560")
        self.minsize(440, 460)
        self.transient(master); self.grab_set()

        self._sched = sched
        self._on_save = on_save

        ctk.CTkLabel(
            self, text=sched["title"],
            font=theme.font(16, "bold"),
            text_color=theme.TEXT_MAIN, anchor="w",
        ).pack(anchor="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(
            self, text=sched.get("description") or "",
            font=theme.FONT_BODY, text_color=theme.TEXT_SUB,
            anchor="w", wraplength=500,
        ).pack(anchor="w", padx=22, pady=(0, 14))

        # Frecuencia (read-only de momento)
        schedule = sched.get("schedule") or {}
        self._frequency = sched.get("frequency", "weekly")

        if self._frequency == "monthly":
            # Día del mes (1-28)
            ctk.CTkLabel(self, text="Día del mes (1-28)",
                         font=theme.font(10, "bold"),
                         text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w", padx=22, pady=(0, 4))
            self.cmb_day = None
            self.ent_dom = ctk.CTkEntry(
                self, height=34, corner_radius=8, width=120,
                fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
            )
            self.ent_dom.insert(0, str(schedule.get("day_of_month", 1)))
            self.ent_dom.pack(anchor="w", padx=22, pady=(0, 10))
        else:
            # Día de la semana
            ctk.CTkLabel(self, text="Día de la semana",
                         font=theme.font(10, "bold"),
                         text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w", padx=22, pady=(0, 4))
            self.ent_dom = None
            day_options = list(sched_service.DAY_LABELS.values())
            current_day = sched_service.DAY_LABELS.get(schedule.get("day_of_week", "mon"), "Lunes")
            self.cmb_day = ctk.CTkOptionMenu(
                self, values=day_options, width=180, height=34, corner_radius=8,
                fg_color=theme.BG_INPUT, button_color=theme.BG_INPUT,
                button_hover_color=theme.BG_CARD, text_color=theme.TEXT_MAIN,
                font=theme.FONT_BODY, dropdown_font=theme.FONT_BODY,
            )
            self.cmb_day.set(current_day)
            self.cmb_day.pack(anchor="w", padx=22, pady=(0, 10))

        # Hora
        time_row = ctk.CTkFrame(self, fg_color="transparent")
        time_row.pack(anchor="w", padx=22, fill="x")
        ctk.CTkLabel(time_row, text="Hora",
                     font=theme.font(10, "bold"),
                     text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
        sub = ctk.CTkFrame(time_row, fg_color="transparent")
        sub.pack(anchor="w", fill="x", pady=(2, 12))
        self.ent_hour = ctk.CTkEntry(
            sub, height=34, corner_radius=8, width=80,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_hour.insert(0, f"{schedule.get('hour', 8):02d}")
        self.ent_hour.pack(side="left")
        ctk.CTkLabel(sub, text=":", font=theme.FONT_TITLE,
                     text_color=theme.TEXT_MAIN).pack(side="left", padx=4)
        self.ent_min = ctk.CTkEntry(
            sub, height=34, corner_radius=8, width=80,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_min.insert(0, f"{schedule.get('minute', 0):02d}")
        self.ent_min.pack(side="left")

        # Recipients (executive / interactive usan To/Cc)
        recipients = sched.get("recipients") or {}
        if sched["type"] in ("executive", "interactive", "interactive_executive"):
            ctk.CTkLabel(self, text="Destinatarios To",
                         font=theme.font(10, "bold"),
                         text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w", padx=22, pady=(0, 4))
            self.ent_to = ctk.CTkEntry(
                self, height=34, corner_radius=8,
                fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
            )
            self.ent_to.insert(0, ", ".join(recipients.get("to") or []))
            self.ent_to.pack(fill="x", padx=22, pady=(0, 6))

            # Botones rápidos: añadir el email de cada compañero al To
            tqa = ctk.CTkFrame(self, fg_color="transparent")
            tqa.pack(fill="x", padx=22, pady=(0, 10))
            tbtns = [("Limpiar", lambda: self._set_to(""))]
            tbtns += [(ini, (lambda e=(info.get("emails") or [""])[0]: self._add_email_to_to(e)))
                      for ini, info in sorted(USERS.items())]
            for c in range(5):
                tqa.grid_columnconfigure(c, weight=1, uniform="tqa")
            for i, (lbl, cmd) in enumerate(tbtns):
                ui.button(tqa, lbl, "chip", size="xs", height=26, font=theme.FONT_TINY,
                          command=cmd).grid(row=i // 5, column=i % 5, sticky="ew", padx=2, pady=2)

            ctk.CTkLabel(self, text="Cc",
                         font=theme.font(10, "bold"),
                         text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w", padx=22, pady=(0, 4))
            self.ent_cc = ctk.CTkEntry(
                self, height=34, corner_radius=8,
                fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
            )
            self.ent_cc.insert(0, ", ".join(recipients.get("cc") or []))
            self.ent_cc.pack(fill="x", padx=22, pady=(0, 12))
            self.ent_filter = None
        else:
            # Personal: filtro de usuarios
            options = sched.get("options") or {}
            uf = options.get("user_filter", "all")
            ctk.CTkLabel(self, text="Filtro de usuarios",
                         font=theme.font(10, "bold"),
                         text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w", padx=22, pady=(0, 4))
            self.ent_filter = ctk.CTkEntry(
                self, placeholder_text="all (todo el equipo) o JP, AC, JM",
                height=34, corner_radius=8,
                fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
            )
            if isinstance(uf, list):
                self.ent_filter.insert(0, ", ".join(uf))
            else:
                self.ent_filter.insert(0, str(uf))
            self.ent_filter.pack(fill="x", padx=22, pady=(0, 6))
            self.ent_to = None

            # Botones rápidos para añadir compañeros / todo el equipo
            qa = ctk.CTkFrame(self, fg_color="transparent")
            qa.pack(fill="x", padx=22, pady=(0, 10))
            btns = [("Todo el equipo", lambda: self._set_filter("all")),
                    ("Limpiar", lambda: self._set_filter(""))]
            btns += [(ini, (lambda x=ini: self._add_to_filter(x)))
                     for ini in sorted(USERS)]
            cols = 5
            for c in range(cols):
                qa.grid_columnconfigure(c, weight=1, uniform="qa")
            for i, (lbl, cmd) in enumerate(btns):
                ui.button(qa, lbl, "chip", size="xs", height=26, font=theme.FONT_TINY,
                          command=cmd).grid(row=i // cols, column=i % cols, sticky="ew", padx=2, pady=2)

            if sched["type"] == "teams_personal":
                # Teams se publica en el chat privado de cada persona: no hay Cc.
                ctk.CTkLabel(
                    self, text="Cada persona recibe sus pendientes en su chat privado de Teams.",
                    font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, anchor="w",
                    justify="left", wraplength=500).pack(anchor="w", padx=22, pady=(0, 12))
                self.ent_cc = None
            else:
                ctk.CTkLabel(self, text="Cc (añadido a cada email)",
                             font=theme.font(10, "bold"),
                             text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w", padx=22, pady=(0, 4))
                self.ent_cc = ctk.CTkEntry(
                    self, height=34, corner_radius=8,
                    fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                    text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
                )
                self.ent_cc.insert(0, ", ".join(recipients.get("cc") or []))
                self.ent_cc.pack(fill="x", padx=22, pady=(0, 12))

        # Footer
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=14, side="bottom")
        ui.button(footer, "Cancelar", "secondary", command=self.destroy).pack(side="right", padx=(8, 0))
        ui.button(footer, "Guardar", "primary", command=self._save).pack(side="right")

    def _set_to(self, value: str) -> None:
        self.ent_to.delete(0, "end")
        if value:
            self.ent_to.insert(0, value)

    def _add_email_to_to(self, email: str) -> None:
        if not email:
            return
        cur = self.ent_to.get().strip()
        parts = [p.strip() for p in cur.split(",") if p.strip()]
        if email not in parts:
            parts.append(email)
        self._set_to(", ".join(parts))

    def _set_filter(self, value: str) -> None:
        self.ent_filter.delete(0, "end")
        if value:
            self.ent_filter.insert(0, value)

    def _add_to_filter(self, initials: str) -> None:
        cur = self.ent_filter.get().strip()
        parts = ([] if not cur or cur.lower() == "all"
                 else [p.strip().upper() for p in cur.split(",") if p.strip()])
        if initials.upper() not in parts:
            parts.append(initials.upper())
        self._set_filter(", ".join(parts))

    def _save(self) -> None:
        try:
            hour = int(self.ent_hour.get())
            minute = int(self.ent_min.get())
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Hora/minuto fuera de rango")
        except ValueError:
            messagebox.showwarning("Hora inválida", "Indica hora (0-23) y minutos (0-59) numéricos.")
            return

        if self._frequency == "monthly":
            try:
                dom = int(self.ent_dom.get())
                if not (1 <= dom <= 28):
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Día inválido", "Indica un día del mes entre 1 y 28.")
                return
            schedule_changes = {"day_of_month": dom, "hour": hour, "minute": minute}
        else:
            day_label = self.cmb_day.get()
            day_key = sched_service.LABEL_TO_DAY.get(day_label, "mon")
            schedule_changes = {"day_of_week": day_key, "hour": hour, "minute": minute}

        changes: dict = {"schedule": schedule_changes}
        cc = ([s.strip() for s in self.ent_cc.get().split(",") if s.strip()]
              if self.ent_cc is not None else [])

        if self.ent_to is not None:  # executive / interactive
            to = [s.strip() for s in self.ent_to.get().split(",") if s.strip()]
            changes["recipients"] = {"to": to, "cc": cc}
        else:  # personal
            raw = self.ent_filter.get().strip()
            if not raw or raw.lower() == "all":
                user_filter = "all"
            else:
                user_filter = [s.strip().upper() for s in raw.split(",") if s.strip()]
            changes["recipients"] = {"to": [], "cc": cc}
            changes["options"] = {"user_filter": user_filter}

        sched_service.update_schedule(self._sched["id"], changes)
        if self._on_save:
            self._on_save()
        self.destroy()
