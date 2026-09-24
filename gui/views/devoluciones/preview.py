"""Preview de una devolución antes de avisar al responsable.

Enseña los documentos que trae el transmittal con su estado, permite
corregirlo, descarga el paquete del portal y lo archiva en las carpetas del
pedido.
"""

import logging
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from core.services import transmittal
from gui import theme
from gui.widgets import ui
from gui.widgets.table import DataTable

from gui.views.devoluciones.comun import (
    _open_html_preview,
    _open_return_folders,
    _status_tag,
)

logger = logging.getLogger(__name__)
# Preview de devolución: columnas a nivel de DOCUMENTO (varían por fila) que se
# muestran en la tabla. El resto (pedido, cliente, material, PO, transmittal…)
# son iguales en todas las filas y se muestran en la cabecera resumen.
DOC_TABLE_COLUMNS = [
    "Doc. Cliente", "Doc. EIPSA", "Título",
    "Tipo de documento", "Rev.", "Estado", "Crítico",
]


# Cabecera abreviada para algunas columnas (id = clave de datos, text = visible)
DOC_HEADER_SHORT = {
    "Tipo de documento": "Tipo",
    "Rev.": "Rev",
    "Crítico": "Crít.",
}


# Campos a nivel de PEDIDO que van a la cabecera resumen: (clave, etiqueta)
META_FIELDS = [
    ("Nº Pedido", "Pedido"),
    ("Cliente", "Cliente"),
    ("Material", "Material"),
    ("PO", "PO"),
    ("Responsable", "Resp."),
    ("Nº Transmittal", "Transmittal"),
    ("Fecha", "Recibido"),
]


# Estados válidos para edición manual desde el preview de devolución.
# Ordenados por frecuencia de uso real del Document Controller.
VALID_STATUSES = [
    "Aprobado", "Com. Menores", "Com. Mayores", "Comentado",
    "Rechazado", "Informativo", "VOID", "Enviado", "Sin Enviar",
]


class PreviewWindow(ctk.CTkToplevel):
    def __init__(self, master, uid: str, on_sent=None):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self.title("Preview de devolución")
        self.geometry("900x760")
        self.minsize(780, 640)
        self.transient(master)
        self.grab_set()

        self._uid = uid
        self._preview: dict | None = None
        self._on_sent = on_sent
        self._status_overrides: dict[str, str] = {}  # iid -> nuevo Estado
        self.docs_table: DataTable | None = None
        self._estado_col_id: str | None = None  # ej "#5"
        self._fit_after_id = None

        self._build_skeleton()
        self._load()

    def _debounce_fit(self) -> None:
        """Reajusta las columnas al redimensionar la ventana (con debounce)."""
        if self.docs_table is None:
            return
        if self._fit_after_id is not None:
            try:
                self.after_cancel(self._fit_after_id)
            except Exception:
                pass
        self._fit_after_id = self.after(150, self._fit_docs_table)

    def _build_skeleton(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 6))
        self.lbl_platform = ctk.CTkLabel(
            header, text="Cargando…", font=theme.font(18, "bold"),
            text_color=theme.TEXT_MAIN, anchor="w",
        )
        self.lbl_platform.pack(anchor="w")
        self.lbl_subject = ctk.CTkLabel(
            header, text="", font=theme.FONT_BODY, text_color=theme.TEXT_SUB,
            anchor="w", justify="left", wraplength=820,
        )
        self.lbl_subject.pack(anchor="w", pady=(2, 0))

        # Cabecera resumen del pedido (chips con datos que se repiten en todas
        # las filas). Se rellena en _render_preview.
        self.meta_host = ctk.CTkFrame(
            self, fg_color=theme.BG_CARD, corner_radius=10,
            border_width=1, border_color=theme.BORDER,
        )
        self.meta_host.pack(fill="x", padx=22, pady=(10, 2))

        # Fields
        fields = ctk.CTkFrame(self, fg_color="transparent")
        fields.pack(fill="x", padx=22, pady=(12, 8))

        ctk.CTkLabel(fields, text="Para (To)", font=theme.FONT_SECTION,
                     text_color=theme.TEXT_MUTED).grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.ent_to = ctk.CTkEntry(
            fields, height=34, corner_radius=8,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_to.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(fields, text="Copia (Cc)", font=theme.FONT_SECTION,
                     text_color=theme.TEXT_MUTED).grid(row=2, column=0, sticky="w", pady=(0, 2))
        self.ent_cc = ctk.CTkEntry(
            fields, height=34, corner_radius=8,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY,
        )
        self.ent_cc.grid(row=3, column=0, sticky="ew", pady=(0, 0))

        fields.grid_columnconfigure(0, weight=1)

        # Tabla documentos
        ctk.CTkLabel(self, text="Documentos detectados",
                     font=theme.FONT_SECTION, text_color=theme.TEXT_MUTED,
                     anchor="w").pack(fill="x", padx=22, pady=(14, 4))

        # Footer y status se packean PRIMERO con side="bottom" para garantizar
        # que el botón Enviar quede siempre visible aunque la tabla crezca.
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=22, pady=14)
        ui.button(footer, "Cancelar", "secondary", size="lg",
                  command=self.destroy).pack(side="right", padx=(8, 0))

        self.btn_send = ui.button(footer, "Enviar notificación  →", "primary", size="lg",
                                  state="disabled", command=self._send)
        self.btn_send.pack(side="right")

        self.btn_preview = ui.button(
            footer, "👁  Preview email", "chip", size="lg",
            state="disabled",
            command=self._preview_email,
        )
        self.btn_preview.pack(side="left")

        # Solo para portales con descarga (eGesDoc/TR y AYESA): baja el zip de la
        # devolución a la carpeta del pedido (se habilita en _render_preview).
        self.btn_transmittal = ui.button(
            footer, "⤓  Descargar devolución", "chip", size="lg",
            state="disabled", command=self._download_transmittal,
        )
        self.btn_transmittal.pack(side="left", padx=(8, 0))
        ui.tooltip(self.btn_transmittal,
                   "Descarga el zip de la devolución (eGesDoc o enlace de AYESA) y lo guarda\n"
                   "con el correo en 00 TRANS Y RES \\ NNN (fecha) del pedido.")

        self.lbl_status = ctk.CTkLabel(
            self, text="⏳  Parseando email…", font=theme.FONT_BODY,
            text_color=theme.TEXT_MUTED, anchor="w",
        )
        self.lbl_status.pack(side="bottom", fill="x", padx=22)

        # Tabla expansible (toma el espacio restante en el medio)
        self.table_host = ctk.CTkFrame(self, fg_color="transparent")
        self.table_host.pack(side="top", fill="both", expand=True, padx=22, pady=(0, 8))

    def _load(self) -> None:
        uid = self._uid

        def worker():
            try:
                data = transmittal.preview_email(uid)
                ui.en_ui(self, lambda: self._render_preview(data))
            except Exception as exc:
                logger.exception("Error en preview")
                err = str(exc)
                ui.en_ui(self, lambda: self._render_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _render_preview(self, pv: dict) -> None:
        self._preview = pv
        self.lbl_platform.configure(text=pv.get("platform", "—"))
        self.lbl_subject.configure(text=pv.get("subject", ""))

        self.ent_to.delete(0, "end")
        self.ent_to.insert(0, ", ".join(pv.get("suggested_to") or []))
        self.ent_cc.delete(0, "end")
        self.ent_cc.insert(0, ", ".join(pv.get("suggested_cc") or []))

        docs = pv.get("documents") or []
        all_cols = [c for c in (pv.get("columns") or (docs[0].keys() if docs else []))
                    if not str(c).startswith("_")]

        # Cabecera resumen del pedido (datos que se repiten en cada fila)
        self._render_meta(docs[0] if docs else {})

        # Columnas de la tabla: solo las de DOCUMENTO presentes en los datos
        cols = [c for c in DOC_TABLE_COLUMNS if c in all_cols]
        if not cols:  # fallback defensivo
            cols = all_cols

        for child in self.table_host.winfo_children():
            child.destroy()

        self._status_overrides.clear()
        self.docs_table = None
        self._estado_col_id = None

        if not docs:
            ctk.CTkLabel(
                self.table_host, text="No se detectaron documentos",
                font=theme.FONT_BODY, text_color=theme.TEXT_MUTED,
            ).pack(pady=20)
        else:
            self.docs_table = DataTable(self.table_host, columns=cols)
            self.docs_table.pack(fill="both", expand=True)
            # Alineación: texto a la izquierda, Rev/Estado/Crítico centrados
            self.docs_table.set_columns_anchor({
                "Rev.": "center", "Estado": "center", "Crítico": "center",
                "Tipo de documento": "center",
            })
            for idx, doc in enumerate(docs):
                values = [str(doc.get(c, "")) for c in cols]
                tag = _status_tag(doc.get("Estado", ""))
                self.docs_table.add_row(values=values, iid=str(idx), tags=(tag,) if tag else ())

            # Cabeceras abreviadas
            for col in cols:
                short = DOC_HEADER_SHORT.get(col)
                if short:
                    self.docs_table.tree.heading(col, text=short)

            # Configurar tags de coloreo
            for k, color in (
                ("status_aprobado", theme.GREEN),
                ("status_rechazado", theme.RED),
                ("status_comentado", theme.AMBER),
                ("status_enviado", theme.BLUE),
            ):
                self.docs_table.tree.tag_configure(k, foreground=color)
            self.docs_table.tree.tag_configure("status_edited", background=theme.ROW_BG_EDITED)

            # Localizar el id de columna Estado (ej "#5") para el bind
            if "Estado" in cols:
                self._estado_col_id = f"#{cols.index('Estado') + 1}"
                # Subrayar visualmente la columna Estado como editable
                self.docs_table.tree.heading("Estado", text="Estado  ✎")
                self.docs_table.tree.bind("<Button-1>", self._on_doc_click)

            # Ajustar columnas para que la tabla entre completa (sin scroll
            # lateral). Se llama tras el layout para medir el ancho real.
            self.after(80, self._fit_docs_table)
            # Reajustar si se redimensiona la ventana
            self.bind("<Configure>", lambda _e: self._debounce_fit())

        self.lbl_status.configure(
            text=f"✓  {len(docs)} documento(s) listos. Click en la columna Estado ✎ para editar manualmente.",
        )
        self.btn_send.configure(state="normal")
        self.btn_preview.configure(state="normal")
        self._setup_transmittal_button(pv)

    # ── Descarga del transmittal (eGesDoc) ────────────────────────────────────

    def _setup_transmittal_button(self, pv: dict) -> None:
        from core.services import portal_downloads

        info = portal_downloads.describe_email(pv.get("from", ""), pv.get("subject", ""))
        if info is None:
            self.btn_transmittal.pack_forget()
            return
        done = portal_downloads.downloaded_info(info["code"])
        if done and done.get("zip") and not done.get("dev_folders"):
            # Descargada pero sin repartir: los documentos no llegaron a sus
            # carpetas dev. (una revisión rara, M: caída…). Se puede reintentar
            # sin volver a pedirle el paquete al portal.
            self.btn_transmittal.configure(
                state="normal", text="🗂  Archivar en 2-Tecnico",
                command=self._archive_pending)
            self.lbl_status.configure(
                text=f"⚠  Devolución {info['code']} descargada, pero sus documentos no se "
                     f"archivaron en las carpetas dev. · pulsa «Archivar en 2-Tecnico».")
            return
        if done and done.get("folder"):
            # Ya descargada y archivada: el botón lleva directamente a la carpeta
            # para comprobarlo antes de avisar a los compañeros.
            folder, devs = done["folder"], list(done.get("dev_folders") or [])
            self.btn_transmittal.configure(
                state="normal", text="📂  Abrir carpetas de la devolución",
                command=lambda: _open_return_folders(folder, devs))
            self.lbl_status.configure(
                text=f"✓  Devolución {info['code']} ya guardada en {Path(folder).name} · "
                     f"revisa la carpeta y envía la notificación.")
            return
        ready, why = portal_downloads.portal_ready(info["portal"])
        if not ready:
            self.btn_transmittal.configure(state="disabled", text=f"⤓  Descargar ({why})")
            return
        self.btn_transmittal.configure(state="normal", text=f"⤓  Descargar {info['code']}")

    def _download_transmittal(self) -> None:
        self.btn_transmittal.configure(state="disabled", text="⤓  Descargando…")
        self.lbl_status.configure(text="⏳  Descargando la devolución del portal…")
        uid = self._uid

        def worker():
            from core.services import portal_downloads
            try:
                res = portal_downloads.download_for_email(uid)
                ui.en_ui(self, lambda: self._transmittal_done(res))
            except portal_downloads.NothingToDownload as exc:
                # No es un fallo: este correo no traía paquete, solo se archiva él.
                msg, carpeta = str(exc), exc.folder
                ui.en_ui(self, lambda: self._transmittal_empty(msg, carpeta))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Descarga de transmittal")
                msg = str(exc)
                ui.en_ui(self, lambda: self._transmittal_failed(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _archive_pending(self) -> None:
        """Reparte una devolución ya descargada que se quedó sin archivar."""
        self.btn_transmittal.configure(state="disabled", text="🗂  Archivando…")
        self.lbl_status.configure(text="⏳  Repartiendo los documentos por sus carpetas dev.…")
        uid = self._uid

        def worker():
            from core.services import portal_downloads
            try:
                res = portal_downloads.archive_pending(uid)
                ui.en_ui(self, lambda: self._transmittal_done(res))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Archivo en dev. de una devolución ya descargada")
                msg = str(exc)
                ui.en_ui(self, lambda: self._transmittal_failed(msg, archivando=True))

        threading.Thread(target=worker, daemon=True).start()

    def _transmittal_done(self, res: dict) -> None:
        folder, devs = res["folder"], list(res.get("dev_folders") or [])
        self.btn_transmittal.configure(
            state="normal", text="📂  Abrir carpetas de la devolución",
            command=lambda: _open_return_folders(folder, devs),
        )
        from core.services import dev_folders

        estado = "ya estaba descargada" if res.get("already") else "descargada"
        archive = res.get("archive") or {}
        resumen = dev_folders.summary_line(archive)
        self.lbl_status.configure(
            text=f"✓  Devolución {res['code']} {estado} en {folder.name} ({res['pedido']}). Archivo dev.: {resumen}.")
        detalle = "\n".join(f"· {f}: {why}" for f, why in archive.get("skipped", [])[:4])
        if self._on_sent:
            self._on_sent()          # refresca la lista: la fila pasa a «✓ guardada»
        ui.toast(self, "Devolución archivada" if res.get("already") else "Devolución descargada",
                 f"{res['zip'].name} → {folder.name}\nArchivo en 2-Tecnico: {resumen}" + (f"\n{detalle}" if detalle else ""),
                 kind="success" if not archive.get("skipped") else "warn")

    def _transmittal_empty(self, msg: str, folder=None) -> None:
        """El correo es una devolución, pero no trae paquete que descargar.

        El correo sí queda archivado en su carpeta del pedido, así que el botón
        pasa a abrirla en vez de a reintentar una descarga que no existe.
        """
        donde = f" El correo queda en {Path(folder).name}." if folder else ""
        self.lbl_status.configure(text=f"ℹ  {msg}.{donde}")
        if folder:
            self.btn_transmittal.configure(
                state="normal", text="📂  Abrir la carpeta de la devolución",
                command=lambda: _open_return_folders(folder, []))
        else:
            self.btn_transmittal.configure(state="disabled", text="—  Sin descarga")
        ui.toast(self, "Sin paquete que descargar", msg + donde, kind="info")
        if self._on_sent:
            self._on_sent()          # la columna Descarga deja de pedirlo

    def _transmittal_failed(self, msg: str, archivando: bool = False) -> None:
        self.btn_transmittal.configure(
            state="normal",
            text="🗂  Reintentar archivado" if archivando else "⤓  Reintentar descarga")
        verbo = "archivar" if archivando else "descargar"
        self.lbl_status.configure(text=f"✗  No se pudo {verbo} la devolución: {msg}")
        ui.toast(self, f"{'Archivado' if archivando else 'Descarga'} · error", msg, kind="error")

    def _fit_docs_table(self) -> None:
        if self.docs_table is not None:
            self.docs_table.autofit_columns(max_per={
                "Título": 360,
                "Doc. Cliente": 200, "Doc. EIPSA": 180,
            })

    def _render_meta(self, doc: dict) -> None:
        """Rellena la cabecera resumen con los datos del pedido (chips)."""
        for child in self.meta_host.winfo_children():
            child.destroy()
        if not doc:
            self.meta_host.pack_forget()
            return
        self.meta_host.pack(fill="x", padx=22, pady=(10, 2))

        grid = ctk.CTkFrame(self.meta_host, fg_color="transparent")
        grid.pack(fill="x", padx=theme.SPACE_4, pady=theme.SPACE_3)

        # Reparte los campos no vacíos en filas de 4 columnas
        items = [(lbl, str(doc.get(key, "") or "—").strip() or "—")
                 for key, lbl in META_FIELDS]
        ncols = 4
        for c in range(ncols):
            grid.grid_columnconfigure(c, weight=1, uniform="meta")

        for i, (lbl, val) in enumerate(items):
            r, c = divmod(i, ncols)
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=r, column=c, sticky="w", padx=(0, theme.SPACE_4),
                      pady=(0, theme.SPACE_1))
            ctk.CTkLabel(
                cell, text=lbl.upper(), font=theme.FONT_LABEL,
                text_color=theme.TEXT_MUTED, anchor="w",
            ).pack(anchor="w")
            ctk.CTkLabel(
                cell, text=val, font=theme.FONT_BODY_BOLD,
                text_color=theme.TEXT_MAIN, anchor="w",
            ).pack(anchor="w")

    # ── Editor de Estado por documento ────────────────────────────────────────

    def _on_doc_click(self, event) -> None:
        """Detecta click en la celda Estado y abre el menú de selección."""
        if not self.docs_table or not self._estado_col_id:
            return
        tree = self.docs_table.tree
        region = tree.identify_region(event.x, event.y)
        col = tree.identify_column(event.x)
        row_id = tree.identify_row(event.y)
        if region != "cell" or col != self._estado_col_id or not row_id:
            return
        self._open_estado_menu(row_id, event.x_root, event.y_root)

    def _open_estado_menu(self, row_id: str, x_root: int, y_root: int) -> None:
        """Menú nativo tk.Menu con la lista de estados válidos."""
        menu = tk.Menu(
            self, tearoff=False,
            bg=theme.BG_CARD, fg=theme.TEXT_MAIN,
            activebackground=theme.ACCENT, activeforeground="white",
            font=theme.font(11),
            borderwidth=1, relief="solid",
        )
        for estado in VALID_STATUSES:
            menu.add_command(
                label=f"  {estado}  ",
                command=lambda e=estado, r=row_id: self._set_estado(r, e),
            )
        menu.add_separator()
        menu.add_command(
            label="  ↺  Restaurar original  ",
            command=lambda r=row_id: self._restore_estado(r),
        )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    def _set_estado(self, row_id: str, nuevo_estado: str) -> None:
        if not self.docs_table or not self._estado_col_id:
            return
        col_idx = int(self._estado_col_id.lstrip("#")) - 1
        values = list(self.docs_table.row_values(row_id))
        if col_idx >= len(values):
            return
        values[col_idx] = nuevo_estado

        # Marcar como editado y aplicar tag de color por nuevo estado
        new_tag = _status_tag(nuevo_estado)
        tags = ("status_edited", new_tag) if new_tag else ("status_edited",)
        self.docs_table.set_values(row_id, values, tags=tags)

        self._status_overrides[row_id] = nuevo_estado
        self._refresh_overrides_status()

    def _restore_estado(self, row_id: str) -> None:
        if row_id not in self._status_overrides or not self._preview:
            return
        try:
            idx = int(row_id)
            docs = self._preview.get("documents") or []
            original_estado = docs[idx].get("Estado", "")
        except (ValueError, IndexError):
            return
        if not self.docs_table or not self._estado_col_id:
            return
        col_idx = int(self._estado_col_id.lstrip("#")) - 1
        values = list(self.docs_table.row_values(row_id))
        # Quitar tag de editado, restaurar tag por estado original
        orig_tag = _status_tag(original_estado)
        if col_idx < len(values):
            values[col_idx] = str(original_estado)
        self.docs_table.set_values(row_id, values, tags=(orig_tag,) if orig_tag else ())
        del self._status_overrides[row_id]
        self._refresh_overrides_status()

    def _refresh_overrides_status(self) -> None:
        n = len(self._status_overrides)
        if n == 0:
            self.lbl_status.configure(
                text=f"✓  {len(self._preview.get('documents') or [])} documento(s) listos. Click en Estado ✎ para editar.",
                text_color=theme.GREEN,
            )
        else:
            self.lbl_status.configure(
                text=f"✏  {n} estado(s) modificado(s) manualmente. Se aplicarán al enviar.",
                text_color=theme.AMBER,
            )

    def _render_error(self, msg: str) -> None:
        self.lbl_platform.configure(text="Error", text_color=theme.RED)
        self.lbl_subject.configure(text=msg)
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)

    def _preview_email(self) -> None:
        """Genera el HTML que se enviaría y lo abre en el navegador."""
        if not self._preview:
            return
        self.lbl_status.configure(text="⏳  Generando preview…", text_color=theme.TEXT_MUTED)
        uid = self._uid
        overrides = dict(self._status_overrides)

        def worker():
            try:
                res = transmittal.generate_notification_html(uid, status_overrides=overrides)
                ui.en_ui(self, lambda: _open_html_preview(res["html"], "devolucion"))
                extra = f" ({len(overrides)} override(s) aplicado(s))" if overrides else ""
                ui.en_ui(self, lambda: self.lbl_status.configure(
                    text=f"✓  Preview abierto en navegador{extra}", text_color=theme.GREEN,
                ))
            except Exception as exc:
                logger.exception("Error generando preview email")
                err = str(exc)
                ui.en_ui(self, lambda: self.lbl_status.configure(
                    text=f"✗  {err}", text_color=theme.RED,
                ))

        import threading as _th
        _th.Thread(target=worker, daemon=True).start()

    def _send(self) -> None:
        if not self._preview:
            return
        from core import session
        if not session.can_manage("devoluciones"):
            ui.toast(self, "Solo lectura", "No tienes permiso para enviar devoluciones.", kind="warn")
            return
        to = [s.strip() for s in self.ent_to.get().split(",") if s.strip()]
        cc = [s.strip() for s in self.ent_cc.get().split(",") if s.strip()]
        if not to:
            messagebox.showwarning("Destinatarios", "Indica al menos un destinatario en 'To'.")
            return

        overrides_line = (
            f"\nEstados modificados: {len(self._status_overrides)} doc(s)"
            if self._status_overrides else ""
        )
        confirm = messagebox.askyesno(
            "Confirmar envío",
            f"¿Enviar notificación de devolución?\n\n"
            f"Para: {', '.join(to)}\n"
            f"Cc: {', '.join(cc) or '—'}\n"
            f"Docs: {len(self._preview.get('documents', []))}"
            f"{overrides_line}",
        )
        if not confirm:
            return

        self.btn_send.configure(state="disabled", text="Enviando…")
        self.lbl_status.configure(text="📤  Enviando email…", text_color=theme.TEXT_MUTED)

        uid = self._uid
        overrides = dict(self._status_overrides)

        def worker():
            try:
                res = transmittal.process_and_notify(
                    uid, to=to, cc=cc, status_overrides=overrides,
                )
                ui.en_ui(self, lambda: self._send_done(res))
            except Exception as exc:
                logger.exception("Error enviando notificación")
                err = str(exc)
                ui.en_ui(self, lambda: self._send_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _send_done(self, res: dict) -> None:
        n = res.get("documents_count", 0)
        ui.toast(self.master, "Notificación enviada",
                 f"{n} documento(s) · {res.get('subject', '')}", kind="success")
        if self._on_sent:
            self._on_sent()
        self.destroy()

    def _send_error(self, msg: str) -> None:
        self.btn_send.configure(state="normal", text="Enviar notificación  →")
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)
        messagebox.showerror("Error de envío", msg)
