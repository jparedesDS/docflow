"""Devolución escrita a mano.

Para los portales que no mandan un correo que se pueda interpretar: se teclean
el pedido y los documentos, y la notificación sale igual que las automáticas.
"""

import logging
import threading

import customtkinter as ctk
from tkinter import messagebox

from core.services import transmittal
from gui import theme
from gui.widgets import ui
from gui.widgets.scrollframe import ScrollFrame

from gui.views.devoluciones.comun import (
    _lookup_pedido,
    _open_html_preview,
    _today_dmy,
)
from gui.views.devoluciones.preview import (
    VALID_STATUSES,
)

logger = logging.getLogger(__name__)


class ManualDevolucionWindow(ctk.CTkToplevel):
    """Ventana para crear una devolución 100% manual.

    Replica la plantilla del email automático pero con todos los campos editables
    a mano. Útil cuando recibes la información por canales no parseables (Teams,
    WhatsApp, llamada, etc.) y aún quieres enviar la notificación con el mismo
    diseño corporativo.
    """

    def __init__(self, master, on_sent=None):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self.title("Devolución manual")
        self.geometry("1000x820")
        self.minsize(820, 680)
        self.transient(master)
        self.grab_set()

        self._on_sent = on_sent
        self._doc_rows: list[dict] = []  # cada item = {frame, ent_doc, ent_titulo, ent_rev, cmb_estado}

        self._build_layout()
        # Una fila vacía inicial para que el usuario empiece a escribir
        self._add_doc_row()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=theme.SPACE_5, pady=(theme.SPACE_5, theme.SPACE_1))
        ctk.CTkLabel(
            header, text="Devolución manual",
            font=theme.FONT_TITLE, text_color=theme.TEXT_MAIN, anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Rellena los campos a mano · usa la misma plantilla que las automáticas",
            font=theme.FONT_SUBTITLE, text_color=theme.TEXT_SUB, anchor="w",
        ).pack(anchor="w", pady=(theme.SPACE_1, 0))

        # Footer (packeado primero con side=bottom)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=theme.SPACE_5, pady=theme.SPACE_4)
        ui.button(footer, "Cancelar", "outline",
                  command=self.destroy).pack(side="right", padx=(theme.SPACE_2, 0))

        self.btn_send = ui.button(footer, "Enviar  →", "primary", command=self._send)
        self.btn_send.pack(side="right")

        self.btn_preview = ui.button(footer, "👁  Preview email", "outline", command=self._preview)
        self.btn_preview.pack(side="left")

        # Status line encima del footer
        self.lbl_status = ctk.CTkLabel(
            self, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, anchor="w",
        )
        self.lbl_status.pack(side="bottom", fill="x", padx=theme.SPACE_5,
                              pady=(0, theme.SPACE_1))

        # Scroll wrapper para que el contenido crezca sin romper el footer
        scroll = ScrollFrame(self)
        scroll.pack(side="top", fill="both", expand=True,
                     padx=theme.SPACE_5, pady=(theme.SPACE_3, theme.SPACE_2))

        # ── Sección: Información del pedido ──────────────────────────────
        self._section_label(scroll, "INFORMACIÓN DEL PEDIDO")
        ctk.CTkLabel(
            scroll, text="Escribe el Nº de pedido (P-26/029) y pulsa Enter para autocompletar "
                         "cliente, material y PO desde el ERP.",
            font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, anchor="w",
            justify="left", wraplength=620).pack(anchor="w", pady=(0, theme.SPACE_2))

        info_grid = ctk.CTkFrame(scroll, fg_color="transparent")
        info_grid.pack(fill="x", pady=(0, theme.SPACE_3))
        for col in range(3):
            info_grid.grid_columnconfigure(col, weight=1, uniform="info")

        self.ent_pedido   = self._field(info_grid, 0, 0, "Nº Pedido *", "P-26/029")
        self.ent_po       = self._field(info_grid, 0, 1, "PO",          "1000100040")
        self.ent_supp     = self._field(info_grid, 0, 2, "Supp.",       "S00")
        self.ent_cliente  = self._field(info_grid, 1, 0, "Cliente *",   "")
        self.ent_material = self._field(info_grid, 1, 1, "Material",    "")
        self.ent_fecha    = self._field(info_grid, 1, 2, "Fecha (DD-MM-YYYY)", _today_dmy())

        # Autocompletar cliente/material/PO al escribir el pedido (Enter o salir)
        self.ent_pedido.bind("<Return>", self._autofill_from_pedido)
        self.ent_pedido.bind("<FocusOut>", self._autofill_from_pedido)

        # ── Sección: Documentos ──────────────────────────────────────────
        docs_head = ctk.CTkFrame(scroll, fg_color="transparent")
        docs_head.pack(fill="x", pady=(theme.SPACE_3, theme.SPACE_1))
        ctk.CTkLabel(
            docs_head, text="DOCUMENTOS DEVUELTOS",
            font=theme.FONT_LABEL, text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(side="left")
        ui.button(docs_head, "+ Añadir fila", "outline", size="xs", width=110,
                  text_color=theme.ACCENT, command=self._add_doc_row).pack(side="right")

        # Cabecera de la tabla (para alinear con los campos)
        head_row = ctk.CTkFrame(scroll, fg_color="transparent")
        head_row.pack(fill="x", pady=(theme.SPACE_1, 0))
        self._docs_header(head_row)

        # Container donde se acumulan las filas
        self.docs_container = ctk.CTkFrame(scroll, fg_color="transparent")
        self.docs_container.pack(fill="x", pady=(theme.SPACE_1, theme.SPACE_4))

        # ── Sección: Destinatarios ────────────────────────────────────────
        self._section_label(scroll, "DESTINATARIOS")

        addr = ctk.CTkFrame(scroll, fg_color="transparent")
        addr.pack(fill="x", pady=(0, theme.SPACE_4))

        ctk.CTkLabel(addr, text="Para (To) *", font=theme.FONT_TINY_BOLD,
                     text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
        self.ent_to = ctk.CTkEntry(
            addr, placeholder_text="email1@cliente.com, email2@cliente.com",
            height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_to.pack(fill="x", pady=(theme.SPACE_1, theme.SPACE_2))

        ctk.CTkLabel(addr, text="Copia (Cc)", font=theme.FONT_TINY_BOLD,
                     text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
        self.ent_cc = ctk.CTkEntry(
            addr, placeholder_text="opcional",
            height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_cc.pack(fill="x", pady=(theme.SPACE_1, 0))

    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent, text=text, font=theme.FONT_LABEL,
            text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(anchor="w", pady=(0, theme.SPACE_2))

    def _set_entry(self, ent: ctk.CTkEntry, value: str) -> None:
        if value:
            ent.delete(0, "end")
            ent.insert(0, value)

    def _autofill_from_pedido(self, _event=None) -> None:
        info = _lookup_pedido(self.ent_pedido.get().strip())
        if not info:
            return
        self._set_entry(self.ent_cliente, info["cliente"])
        self._set_entry(self.ent_material, info["material"])
        self._set_entry(self.ent_po, info.get("po", ""))

    def _field(self, grid, row: int, col: int, label: str, placeholder: str) -> ctk.CTkEntry:
        box = ctk.CTkFrame(grid, fg_color="transparent")
        box.grid(row=row, column=col, sticky="ew",
                  padx=(0 if col == 0 else theme.SPACE_2, 0),
                  pady=(0, theme.SPACE_2))
        ctk.CTkLabel(
            box, text=label, font=theme.FONT_TINY_BOLD,
            text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(anchor="w")
        ent = ctk.CTkEntry(
            box, placeholder_text=placeholder,
            height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        ent.pack(fill="x", pady=(theme.SPACE_1, 0))
        return ent

    def _docs_header(self, parent) -> None:
        """Cabecera con los nombres de columna de la tabla de docs."""
        cols = [
            ("Doc. Cliente", 240),
            ("Título",       380),
            ("Rev.",         60),
            ("Estado",       150),
        ]
        for i, (name, w) in enumerate(cols):
            ctk.CTkLabel(
                parent, text=name.upper(), font=theme.FONT_LABEL,
                text_color=theme.TEXT_MUTED, anchor="w", width=w,
            ).pack(side="left", padx=(0 if i == 0 else theme.SPACE_1, 0))
        # Espacio para el botón delete
        ctk.CTkLabel(parent, text="", width=32).pack(side="left")

    # ── Filas de documento ───────────────────────────────────────────────────

    def _add_doc_row(self, prefill: dict | None = None) -> None:
        prefill = prefill or {}
        row = ctk.CTkFrame(self.docs_container, fg_color="transparent")
        row.pack(fill="x", pady=(0, theme.SPACE_1))

        ent_doc = self._row_entry(row, prefill.get("Doc. Cliente", ""), width=240)
        ent_titulo = self._row_entry(row, prefill.get("Título", ""), width=380)
        ent_rev = self._row_entry(row, prefill.get("Rev.", ""), width=60)

        cmb_estado = ctk.CTkOptionMenu(
            row, values=VALID_STATUSES, width=150,
            height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
            fg_color=theme.BG_INPUT, button_color=theme.BG_INPUT,
            button_hover_color=theme.BG_CARD, text_color=theme.TEXT_MAIN,
            font=theme.FONT_BODY, dropdown_font=theme.FONT_BODY,
        )
        cmb_estado.set(prefill.get("Estado") or "Com. Menores")
        cmb_estado.pack(side="left", padx=(theme.SPACE_1, 0))

        # Botón delete (se construye con el item ya en la lista)
        item: dict = {
            "frame": row,
            "ent_doc": ent_doc,
            "ent_titulo": ent_titulo,
            "ent_rev": ent_rev,
            "cmb_estado": cmb_estado,
        }
        btn_del = ui.button(row, "🗑", "danger", size="xs", width=32, height=theme.HEIGHT_INPUT,
                            font=theme.FONT_BUTTON, command=lambda it=item: self._remove_doc_row(it))
        btn_del.pack(side="left", padx=(theme.SPACE_1, 0))

        self._doc_rows.append(item)

    def _row_entry(self, parent, value: str, width: int) -> ctk.CTkEntry:
        ent = ctk.CTkEntry(
            parent, width=width,
            height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        if value:
            ent.insert(0, value)
        ent.pack(side="left", padx=(0, 0))
        return ent

    def _remove_doc_row(self, item: dict) -> None:
        if len(self._doc_rows) <= 1:
            # No permitir quedarse sin filas — al menos limpiar
            item["ent_doc"].delete(0, "end")
            item["ent_titulo"].delete(0, "end")
            item["ent_rev"].delete(0, "end")
            return
        try:
            self._doc_rows.remove(item)
            item["frame"].destroy()
        except (ValueError, Exception):
            pass

    # ── Recogida de datos ────────────────────────────────────────────────────

    def _collect_info_dict(self) -> dict:
        return {
            "Nº Pedido": self.ent_pedido.get().strip(),
            "Cliente":   self.ent_cliente.get().strip(),
            "Material":  self.ent_material.get().strip(),
            "Supp.":     self.ent_supp.get().strip() or "S00",
            "PO":        self.ent_po.get().strip(),
            "Fecha":     self.ent_fecha.get().strip(),
        }

    def _collect_docs(self) -> list[dict]:
        docs = []
        fecha = self.ent_fecha.get().strip()
        for item in self._doc_rows:
            titulo = item["ent_titulo"].get().strip()
            doc_cli = item["ent_doc"].get().strip()
            rev = item["ent_rev"].get().strip()
            estado = item["cmb_estado"].get()
            # Saltar filas completamente vacías
            if not titulo and not doc_cli:
                continue
            docs.append({
                "Doc. Cliente": doc_cli,
                "Título":       titulo,
                "Rev.":         rev,
                "Estado":       estado,
                "Fecha":        fecha,
            })
        return docs

    def _validate(self) -> tuple[bool, str]:
        info = self._collect_info_dict()
        if not info["Nº Pedido"]:
            return False, "El Nº Pedido es obligatorio."
        if not info["Cliente"]:
            return False, "El Cliente es obligatorio."
        docs = self._collect_docs()
        if not docs:
            return False, "Añade al menos un documento (con Título o Doc. Cliente)."
        for i, d in enumerate(docs, 1):
            if not d["Título"] and not d["Doc. Cliente"]:
                return False, f"Fila {i}: indica Título o Doc. Cliente."
        return True, ""

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _preview(self) -> None:
        ok, err = self._validate()
        if not ok:
            messagebox.showwarning("Faltan datos", err, parent=self)
            return
        info = self._collect_info_dict()
        docs = self._collect_docs()
        self.lbl_status.configure(text="⏳  Generando preview…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                res = transmittal.generate_manual_notification_html(info, docs)
                ui.en_ui(self, lambda: _open_html_preview(res["html"], "devolucion_manual"))
                ui.en_ui(self, lambda: self.lbl_status.configure(
                    text=f"✓  Preview abierto en navegador ({res['documents_count']} docs)",
                    text_color=theme.GREEN,
                ))
            except Exception as exc:
                logger.exception("Error generando preview manual")
                err = str(exc)
                ui.en_ui(self, lambda: self.lbl_status.configure(
                    text=f"✗  {err}", text_color=theme.RED,
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _send(self) -> None:
        from core import session
        if not session.can_manage("devoluciones"):
            ui.toast(self, "Solo lectura", "No tienes permiso para enviar devoluciones.", kind="warn")
            return
        ok, err = self._validate()
        if not ok:
            messagebox.showwarning("Faltan datos", err, parent=self)
            return

        to = [s.strip() for s in self.ent_to.get().split(",") if s.strip()]
        cc = [s.strip() for s in self.ent_cc.get().split(",") if s.strip()]
        if not to:
            messagebox.showwarning("Destinatarios", "Indica al menos un destinatario en 'To'.",
                                    parent=self)
            return

        info = self._collect_info_dict()
        docs = self._collect_docs()

        confirm = messagebox.askyesno(
            "Confirmar envío",
            f"¿Enviar devolución manual?\n\n"
            f"Pedido: {info['Nº Pedido']}\n"
            f"Cliente: {info['Cliente']}\n"
            f"Documentos: {len(docs)}\n"
            f"To: {', '.join(to)}\n"
            f"Cc: {', '.join(cc) or '—'}",
            parent=self,
        )
        if not confirm:
            return

        self.btn_send.configure(state="disabled", text="Enviando…")
        self.btn_preview.configure(state="disabled")
        self.lbl_status.configure(text="📤  Enviando email…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                res = transmittal.send_manual_notification(info, docs, to, cc)
                ui.en_ui(self, lambda: self._send_done(res))
            except Exception as exc:
                logger.exception("Error enviando devolución manual")
                err = str(exc)
                ui.en_ui(self, lambda: self._send_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _send_done(self, res: dict) -> None:
        n = res.get("documents_count", 0)
        ui.toast(self.master, "Devolución enviada",
                 f"{n} documento(s) · {res.get('subject', '')}", kind="success")
        if self._on_sent:
            self._on_sent()
        self.destroy()

    def _send_error(self, msg: str) -> None:
        self.btn_send.configure(state="normal", text="Enviar  →")
        self.btn_preview.configure(state="normal")
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)
        messagebox.showerror("Error de envío", msg, parent=self)
