"""La pestaña de informes interactivos.

El semanal, el mensual, el ejecutivo y el de un pedido: se generan, se abren, se
mandan por correo o se publican en Teams.
"""

from __future__ import annotations

import logging
import os
import threading
import webbrowser
from datetime import datetime

import customtkinter as ctk

from gui import theme
from gui.widgets import ui
from gui.widgets.scrollframe import ScrollFrame

logger = logging.getLogger(__name__)


class InteractivosMixin:
    """La pestaña de informes interactivos: el HTML que se manda al cliente."""

    def _build_tab_interactive(self, tab, container=None) -> None:
        from core.services import interactive_report as ir
        self._ir = ir
        self._ir_mode = "period"          # "period" | "pedido"
        self._ir_period = "weekly"
        self._ir_periods: dict[str, str] = {}
        self._ir_pedidos: dict[str, str] = {}
        self._ir_last_path = None

        wrap = container or ScrollFrame(tab)
        if container is None:
            wrap.pack(fill="both", expand=True, padx=theme.SPACE_2, pady=theme.SPACE_2)

        ctk.CTkLabel(
            wrap, text="Genera un informe web interactivo (un único archivo .html con "
            "gráficos y resumen IA), listo para abrir, archivar o enviar por email.",
            font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
            anchor="w", justify="left", wraplength=720).pack(
            anchor="w", pady=(theme.SPACE_2, theme.SPACE_3))

        card = ctk.CTkFrame(wrap, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", pady=(0, theme.SPACE_3))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=theme.SPACE_4, pady=theme.SPACE_4)

        ctk.CTkLabel(inner, text="PERIODO", font=theme.FONT_TINY,
                     text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
        self._ir_seg = ctk.CTkSegmentedButton(
            inner, values=["Semanal", "Mensual", "Análisis", "Ejecutivo", "Por pedido"],
            command=self._on_ir_period,
            height=theme.HEIGHT_BUTTON_SM, font=theme.FONT_SMALL_BOLD,
            corner_radius=theme.RADIUS_MD, fg_color=theme.BG_PAGE,
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.BG_PAGE, unselected_hover_color=theme.BG_INPUT,
            text_color=theme.TEXT_MAIN)
        self._ir_seg.set("Semanal")
        self._ir_seg.pack(anchor="w", pady=(theme.SPACE_1, theme.SPACE_3))

        self._ir_sel_label = ctk.CTkLabel(inner, text="SEMANA / MES", font=theme.FONT_TINY,
                                          text_color=theme.TEXT_MUTED, anchor="w")
        self._ir_sel_label.pack(anchor="w")
        self._ir_menu = ctk.CTkOptionMenu(
            inner, values=["—"], width=380, height=theme.HEIGHT_INPUT,
            font=theme.FONT_SMALL, fg_color=theme.BG_INPUT, button_color=theme.ACCENT,
            button_hover_color=theme.ACCENT_HOVER, text_color=theme.TEXT_MAIN)
        self._ir_menu.pack(anchor="w", pady=(theme.SPACE_1, theme.SPACE_3))

        ctk.CTkLabel(inner, text="DESTINATARIOS · para enviar por email (separa con coma)",
                     font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
        self._ir_to = ctk.CTkEntry(inner, width=440, height=theme.HEIGHT_INPUT,
                                    placeholder_text="nombre@empresa.com, otro@empresa.com",
                                    font=theme.FONT_SMALL)
        self._ir_to.pack(anchor="w", pady=(theme.SPACE_1, theme.SPACE_4))

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(anchor="w")
        ui.button(btns, "Generar y abrir", "primary", command=self._ir_generate).pack(side="left")
        ui.button(btns, "Abrir carpeta", "secondary",
                  command=self._ir_open_folder).pack(side="left", padx=(theme.SPACE_2, 0))
        ui.button(btns, "Enviar por email", "secondary",
                  command=self._ir_send).pack(side="left", padx=(theme.SPACE_2, 0))
        ui.button(btns, "Enviar a Teams", "secondary",
                  command=self._ir_teams).pack(side="left", padx=(theme.SPACE_2, 0))

        self._ir_status = ctk.CTkLabel(wrap, text="", font=theme.FONT_SMALL,
                                       text_color=theme.TEXT_MUTED, anchor="w", justify="left")
        self._ir_status.pack(anchor="w", pady=(theme.SPACE_2, 0))

        self._ir_refresh_periods()

    def _on_ir_period(self, value: str) -> None:
        if value == "Por pedido":
            self._ir_mode = "pedido"
            self._ir_sel_label.configure(text="PEDIDO")
            self._ir_refresh_pedidos()
        elif value == "Análisis":
            # Un informe por cada pestaña de Analítica, con la misma lectura que
            # la pantalla pero en un archivo que se puede mandar y archivar.
            from core.services import analysis_reports as ar
            self._ir_mode = "analisis"
            self._ir_sel_label.configure(text="INFORME")
            self._ir_analisis = {ar.NOMBRES[k]: k for k in ar.INFORMES}
            nombres = list(self._ir_analisis)
            self._ir_menu.configure(values=nombres)
            self._ir_menu.set(nombres[0])
        elif value == "Ejecutivo":
            self._ir_mode = "executive"
            self._ir_sel_label.configure(text="ALCANCE")
            self._ir_menu.configure(values=["Cartera completa · estado actual"])
            self._ir_menu.set("Cartera completa · estado actual")
        else:
            self._ir_mode = "period"
            self._ir_period = "monthly" if value == "Mensual" else "weekly"
            self._ir_sel_label.configure(text="SEMANA / MES")
            self._ir_refresh_periods()

    def _ir_refresh_pedidos(self) -> None:
        self._ir_menu.configure(values=["Cargando…"])
        self._ir_menu.set("Cargando…")

        def worker():
            try:
                rows = self._ir.list_pedidos()
            except Exception:
                logger.exception("No se pudieron listar pedidos")
                rows = []
            ui.en_ui(self, lambda: self._ir_set_pedidos(rows))

        threading.Thread(target=worker, daemon=True).start()

    def _ir_set_pedidos(self, rows) -> None:
        self._ir_pedidos = {}
        labels = []
        for r in rows:
            cli = (r.get("cliente") or "").strip()
            label = f"{r['pedido']} · {cli}" if cli else r["pedido"]
            self._ir_pedidos[label] = r["pedido"]
            labels.append(label)
        labels = labels or ["—"]
        self._ir_menu.configure(values=labels)
        self._ir_menu.set(labels[0])

    def _ir_refresh_periods(self) -> None:
        try:
            periods = self._ir.get_available_periods(self._ir_period, n=8)
        except Exception:
            logger.exception("No se pudieron calcular los periodos")
            periods = []
        self._ir_periods = {label: iso for label, iso in periods}
        labels = list(self._ir_periods.keys()) or ["—"]
        self._ir_menu.configure(values=labels)
        self._ir_menu.set(labels[0])

    def _ir_refdate(self):
        iso = self._ir_periods.get(self._ir_menu.get())
        return datetime.fromisoformat(iso) if iso else None

    def _ir_target(self):
        """('pedido', p) | ('analisis', clave) | ('executive', None) | ('period', …) | None."""
        if self._ir_mode == "pedido":
            pedido = self._ir_pedidos.get(self._ir_menu.get())
            return ("pedido", pedido) if pedido else None
        if self._ir_mode == "analisis":
            clave = getattr(self, "_ir_analisis", {}).get(self._ir_menu.get())
            return ("analisis", clave) if clave else None
        if self._ir_mode == "executive":
            return ("executive", None)
        return ("period", (self._ir_period, self._ir_refdate()))

    def _ir_generate(self) -> None:
        target = self._ir_target()
        if target is None:
            self._ir_status.configure(text="✗  Elige qué informe generar", text_color=theme.RED)
            return
        self._ir_status.configure(text="⏳  Generando informe…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                if target[0] == "pedido":
                    path, _ = self._ir.generate_pedido(target[1])
                elif target[0] == "analisis":
                    from core.services import analysis_reports as ar
                    path, _ = ar.generate(target[1])
                elif target[0] == "executive":
                    path, _ = self._ir.generate_executive()
                else:
                    period, ref = target[1]
                    path, _ = self._ir.generate(period, ref)
                ui.en_ui(self, lambda: self._ir_generated(path))
            except Exception as exc:
                logger.exception("Error generando informe interactivo")
                msg = str(exc)
                ui.en_ui(self, lambda: self._ir_status.configure(text=f"✗  {msg}", text_color=theme.RED))

        threading.Thread(target=worker, daemon=True).start()

    def _ir_generated(self, path) -> None:
        self._ir_last_path = path
        self._ir_status.configure(text=f"✓  Informe generado: {path.name}", text_color=theme.GREEN)
        try:
            webbrowser.open(path.as_uri())
        except Exception:
            logger.debug("No se pudo abrir el navegador", exc_info=True)
        ui.toast(self, "Informe listo", path.name, kind="success")

    def _ir_open_folder(self) -> None:
        try:
            os.startfile(str(self._ir.reports_dir()))  # noqa: S606 (Windows)
        except Exception as exc:
            ui.toast(self, "No se pudo abrir la carpeta", str(exc), kind="info")

    def _ir_send(self) -> None:
        raw = self._ir_to.get().strip()
        to = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
        if not to:
            ui.toast(self, "Sin destinatarios", "Indica al menos un email.", kind="info")
            return
        target = self._ir_target()
        if target is None:
            self._ir_status.configure(text="✗  Elige qué informe generar", text_color=theme.RED)
            return
        self._ir_status.configure(text="⏳  Enviando informe…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                if target[0] == "pedido":
                    self._ir.send_pedido_email(pedido=target[1], to=to)
                elif target[0] == "analisis":
                    from core.services import analysis_reports as ar
                    ar.send_email(target[1], to=to)
                elif target[0] == "executive":
                    self._ir.send_executive_html_email(to=to)
                else:
                    period, ref = target[1]
                    self._ir.send_email(period=period, to=to, ref_date=ref)
                ui.en_ui(self, lambda: self._ir_sent(to))
            except Exception as exc:
                logger.exception("Error enviando informe interactivo")
                msg = str(exc)
                ui.en_ui(self, lambda: self._ir_status.configure(text=f"✗  {msg}", text_color=theme.RED))

        threading.Thread(target=worker, daemon=True).start()

    def _ir_sent(self, to) -> None:
        self._ir_status.configure(
            text=f"✓  Informe enviado a {len(to)} destinatario(s).", text_color=theme.GREEN)
        ui.toast(self, "Enviado", ", ".join(to), kind="success")

    def _ir_teams(self) -> None:
        target = self._ir_target()
        if target is None:
            self._ir_status.configure(text="✗  Elige qué informe generar", text_color=theme.RED)
            return
        from core.services import teams
        if not teams.is_configured():
            ui.toast(self, "Teams no configurado",
                     "Pega la URL del webhook en Ajustes ▸ Fuentes de datos.", kind="info")
            return
        self._ir_status.configure(text="⏳  Publicando resumen en Teams…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                if target[0] == "pedido":
                    res = self._ir.post_pedido_to_teams(target[1])
                elif target[0] == "analisis":
                    from core.services import analysis_reports as ar
                    res = ar.post_to_teams(target[1])
                elif target[0] == "executive":
                    res = self._ir.post_executive_to_teams()
                else:
                    period, ref = target[1]
                    res = self._ir.post_period_to_teams(period, ref)
                ui.en_ui(self, lambda: self._ir_teams_done(res))
            except Exception as exc:
                logger.exception("Error publicando en Teams")
                msg = str(exc)
                ui.en_ui(self, lambda: self._ir_status.configure(text=f"✗  {msg}", text_color=theme.RED))

        threading.Thread(target=worker, daemon=True).start()

    def _ir_teams_done(self, res: dict) -> None:
        if res.get("ok"):
            self._ir_status.configure(text="✓  Resumen publicado en Teams.", text_color=theme.GREEN)
            ui.toast(self, "Teams", "Resumen publicado en el canal.", kind="success")
        else:
            msg = res.get("error", "Error desconocido")
            self._ir_status.configure(text=f"✗  {msg}", text_color=theme.RED)
            ui.toast(self, "No se pudo publicar en Teams", msg, kind="info")

    def _build_tab_informes(self, tab) -> None:
        """Pestaña única «Informes»: Excel + informe web, en un solo scroll."""
        scroll = ScrollFrame(tab)
        scroll.pack(fill="both", expand=True, padx=theme.SPACE_2, pady=theme.SPACE_2)
        self._build_tab_excels(tab, container=scroll)
        ui.section_header(scroll, "Informe web interactivo").pack(fill="x", pady=(theme.SPACE_5, theme.SPACE_1))
        self._build_tab_interactive(tab, container=scroll)
