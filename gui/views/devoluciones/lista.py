"""La lista de devoluciones: un correo por fila, con su estado.

Doble clic abre el preview; el botón de recarga vuelve a leer el buzón.
"""

import logging
import threading
from datetime import datetime

import customtkinter as ctk

from core.services import transmittal
from gui import theme
from gui.widgets import ui
from gui.widgets.pilltable import PillTable

from gui.views.devoluciones.comun import (
    _dias_desde,
    _fmt_date,
    _friendly_error,
    _open_return_folders,
    _orden_descarga,
    _parse_dt,
    _remitente,
    _trunc,
)
from gui.views.devoluciones.preview import (
    PreviewWindow,
)
from gui.views.devoluciones.manual import (
    ManualDevolucionWindow,
)

logger = logging.getLogger(__name__)
# Columnas de la lista (key · cabecera · ancho mínimo · estira · alineación),
# con el mismo formato por celda que Documentos, Pedidos y Reclamaciones.
COLUMNS = [
    {"key": "Plataforma", "label": "Portal",    "min": 156, "anchor": "center"},
    {"key": "Asunto",     "label": "Asunto",    "min": 360, "anchor": "w", "stretch": True},
    {"key": "Remitente",  "label": "Remitente", "min": 214, "anchor": "w"},
    {"key": "Fecha",      "label": "Recibido",  "min": 128, "anchor": "center"},
    {"key": "Descarga",   "label": "Descarga",  "min": 126, "anchor": "center"},
    {"key": "Enviado",    "label": "Enviado",   "min": 126, "anchor": "center"},
]


# Una devolución sin notificar envejece: a partir de aquí la fecha avisa.
DIAS_AVISO, DIAS_ALERTA = 3, 7


class DevolucionesView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_PAGE, **kwargs)
        self._emails: list[dict] = []
        self._only_unread = False
        self._build_layout()
        self._reload()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # Header
        ui.page_header(
            self, "Devoluciones",
            "Correos en los que el cliente devuelve documentación (TR, GAIA, ACONEX, SENDOC, "
            "AYESA, SACYR…). Recarga, doble clic para revisar y envía la notificación.",
            help_key="devoluciones")

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=theme.SPACE_6, pady=(theme.SPACE_4, theme.SPACE_2))

        self.btn_reload = ui.button(toolbar, "↻  Recargar", "outline", size="sm", command=self._reload)
        self.btn_reload.pack(side="left", padx=(0, theme.SPACE_2))

        # Botón devolución manual (acción primary)
        ui.button(toolbar, "+  Devolución manual", "primary", size="sm",
                  command=lambda: ManualDevolucionWindow(self)).pack(side="left", padx=(0, theme.SPACE_2))

        self.var_unread = ctk.BooleanVar(value=False)
        self.chk_unread = ctk.CTkCheckBox(
            toolbar, text="Solo no leídos", variable=self.var_unread,
            font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self._on_toggle_unread,
        )
        self.chk_unread.pack(side="left", padx=theme.SPACE_2)

        self.count_label = ctk.CTkLabel(
            toolbar, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
        )
        self.count_label.pack(side="right")

        # Loading state
        self.status_label = ctk.CTkLabel(
            self, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, anchor="w",
        )
        self.status_label.pack(fill="x", padx=theme.SPACE_6)

        # Tabla con color por celda y selección múltiple (ctrl/mayús + clic)
        self.table = PillTable(
            self, columns=COLUMNS, on_double_click=self._on_row_double,
            on_sort=self._on_sort, multiselect=True, rowheight=40,
        )
        self.table.pack(fill="both", expand=True, padx=theme.SPACE_6,
                        pady=(theme.SPACE_2, theme.SPACE_6))
        self.table.set_context_menu(self._ctx_menu)
        self._sort: tuple[str, bool] = ("Fecha", False)   # lo más reciente arriba

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _on_toggle_unread(self) -> None:
        self._only_unread = bool(self.var_unread.get())
        self._reload()

    def _reload(self) -> None:
        self.status_label.configure(text="⏳  Conectando con IMAP…")
        self.btn_reload.configure(state="disabled")
        self.table.clear()

        def worker():
            try:
                if self._only_unread:
                    data = transmittal.fetch_unread_emails()
                else:
                    data = transmittal.fetch_all_emails()
                ui.en_ui(self, lambda: self._populate(data))
            except Exception as exc:
                logger.exception("Error cargando emails")
                err = str(exc)
                ui.en_ui(self, lambda: self._show_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _populate(self, emails: list[dict]) -> None:
        self._emails = emails
        self.btn_reload.configure(state="normal")
        self.table.clear()

        if not emails:
            self.count_label.configure(text="0 emails")
            self.status_label.configure(
                text="Ninguna devolución en el buzón.", text_color=theme.TEXT_MUTED)
            return

        self._render_rows()
        pendientes = sum(1 for e in emails if not e.get("processed"))
        self.count_label.configure(text=f"{len(emails)} emails")
        self.status_label.configure(
            text=(f"✓  {len(emails)} devoluciones · {pendientes} sin notificar. "
                  "Doble clic en una fila para revisarla y enviar la notificación."),
            text_color=theme.TEXT_MUTED)

    # ── Pintado de la tabla ───────────────────────────────────────────────────

    def _build_cells(self, e: dict) -> dict:
        """Celdas con estilo de un correo: color solo donde dice algo."""
        dl = e.get("download") or {}
        enviado = bool(e.get("processed"))
        descargada = bool(dl.get("downloaded"))
        dias = _dias_desde(e.get("date", ""))

        if not dl.get("downloadable"):
            # Un transmittal «solo información» no trae paquete, pero su correo sí
            # se archiva: conviene verlo para no ir a buscar una descarga que no hay.
            descarga = ({"text": "✓  solo correo", "pill": True, "fg": theme.TEXT_SUB,
                         "pill_bg": ui.blend(theme.TEXT_SUB, theme.BG_CARD, 0.16)}
                        if dl.get("only_email") else {"text": "—", "fg": theme.TEXT_MUTED})
        elif descargada:
            descarga = {"text": "✓  guardada", "pill": True, "fg": theme.GREEN,
                        "pill_bg": ui.blend(theme.GREEN, theme.BG_CARD, 0.20)}
        else:
            # «↓» y no «⤓»: la negrita del tema no trae ese glifo y sale un cuadro.
            descarga = {"text": "↓  pendiente", "pill": True, "fg": theme.AMBER,
                        "pill_bg": ui.blend(theme.AMBER, theme.BG_CARD, 0.20)}

        if enviado:
            envio = {"text": "✓  enviado", "pill": True, "fg": theme.GREEN,
                     "pill_bg": ui.blend(theme.GREEN, theme.BG_CARD, 0.20)}
        else:
            envio = {"text": "✉  pendiente", "pill": True, "fg": theme.AMBER,
                     "pill_bg": ui.blend(theme.AMBER, theme.BG_CARD, 0.20)}

        # La fecha avisa cuando una devolución lleva días sin notificar; una vez
        # enviada ya no dice nada y se queda en gris.
        fcolor = theme.TEXT_SUB
        if not enviado and dias is not None:
            if dias >= DIAS_ALERTA:
                fcolor = theme.RED
            elif dias >= DIAS_AVISO:
                fcolor = theme.AMBER

        return {
            "Plataforma": {"text": e.get("platform", "—"), "pill": True,
                           "fg": theme.TEXT_SUB, "pill_bg": theme.BG_INPUT},
            # El asunto es la identidad de la fila: en acento mientras esté por
            # notificar, apagado cuando ya se ha mandado.
            "Asunto": {"text": _trunc(e.get("subject") or "(sin asunto)", 90),
                       "fg": theme.ACCENT if not enviado else theme.TEXT_SUB,
                       "bold": not enviado},
            "Remitente": {"text": _trunc(_remitente(e.get("from", "")), 30),
                          "fg": theme.TEXT_MUTED},
            "Fecha": {"text": _fmt_date(e.get("date", "")), "fg": fcolor,
                      "bold": fcolor != theme.TEXT_SUB},
            "Descarga": descarga,
            "Enviado": envio,
        }

    _SORT_KEY = {
        "Plataforma": lambda e: str(e.get("platform", "")),
        "Asunto": lambda e: str(e.get("subject", "")).lower(),
        "Remitente": lambda e: _remitente(e.get("from", "")).lower(),
        "Fecha": lambda e: (_parse_dt(e.get("date", "")) or datetime.min).timestamp(),
        "Descarga": lambda e: _orden_descarga(e.get("download") or {}),
        "Enviado": lambda e: 1 if e.get("processed") else 0,
    }

    def _on_sort(self, key: str) -> None:
        col, asc = self._sort
        self._sort = (key, not asc if key == col else True)
        self._render_rows()

    def _render_rows(self) -> None:
        col, asc = self._sort
        key = self._SORT_KEY.get(col, self._SORT_KEY["Fecha"])
        filas = sorted(self._emails, key=key, reverse=not asc)
        self.table.set_sort_arrow(col, asc)
        self.table.set_rows([(e["uid"], self._build_cells(e)) for e in filas])

    def _show_error(self, msg: str) -> None:
        self.btn_reload.configure(state="normal")
        friendly = _friendly_error(msg)
        self.status_label.configure(text=f"✗  {friendly}", text_color=theme.RED)

    def _on_row_double(self, rowid: str) -> None:
        if rowid:
            PreviewWindow(self, uid=rowid, on_sent=self._reload)

    # ── Menú contextual ────────────────────────────────────────────────────

    def _ctx_menu(self, iid: str):
        email = next((e for e in self._emails if e.get("uid") == iid), None)
        if not email:
            return None
        dl = email.get("download") or {}
        items = [
            ("✉  Procesar / Preview",
             lambda: PreviewWindow(self, uid=iid, on_sent=self._reload)),
        ]
        if (dl.get("downloaded") or dl.get("only_email")) and dl.get("folder"):
            items.append(("📂  Abrir carpetas de la devolución (TRANS Y RES + dev.)",
                          lambda: _open_return_folders(dl["folder"], dl.get("dev_folders") or [])))
        return items + [
            ("-", None),
            ("Copiar asunto",
             lambda: self.table.copy_to_clipboard(email.get("subject", ""))),
            ("Copiar remitente",
             lambda: self.table.copy_to_clipboard(email.get("from", ""))),
        ]
