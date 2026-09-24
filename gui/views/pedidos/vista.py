"""Pedidos: elegir un pedido y montar su ficha.

Aquí está el esqueleto —buscar, elegir, cargar y repartir el cuerpo entre
la ficha y la tabla de equipos—; el contenido de cada zona vive en su
módulo.
"""

import logging
import threading

import customtkinter as ctk

from core.services import erp as erp_service
from core.services import erp_tags
from gui import theme
from gui.widgets import ui
from gui.widgets.scrollframe import ScrollFrame

from gui.views.pedidos.comun import (
    _norm_doc,
)
from gui.views.pedidos.ficha import (
    FichaMixin,
)
from gui.views.pedidos.tags import (
    TagsMixin,
)

logger = logging.getLogger(__name__)


class PedidosView(FichaMixin, TagsMixin, ctk.CTkFrame):

    def __init__(self, master, on_open_documentos=None, on_open_documento=None, **kwargs):
        super().__init__(master, fg_color=theme.BG_PAGE, **kwargs)
        self._on_open_documentos = on_open_documentos    # → Documentos filtrado por pedido
        self._on_open_documento = on_open_documento      # → Documentos por Nº de documento
        self._bundle: dict = {}
        self._doc_index: dict = {}
        self._projects: list[dict] = []
        self._label_to_pedido: dict[str, str] = {}
        self._pedido_current: str | None = None
        self._tags_current: list[dict] = []
        self._build_layout()
        self.after(60, self._load_projects)

    def _build_layout(self) -> None:
        ui.page_header(
            self, "Pedidos",
            "Elige un pedido y mira de un vistazo cómo va: documentación, fabricación, "
            "equipos y qué requiere acción.",
            help_key="pedidos")

        # ── Buscador (sin caja propia: la barra ya se lee sola) ───────────
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=theme.SPACE_6, pady=(theme.SPACE_2, theme.SPACE_3))
        self.ent_search = ctk.CTkEntry(
            row, placeholder_text="🔍   Nº de pedido o cliente…", height=theme.HEIGHT_INPUT,
            corner_radius=theme.RADIUS_MD, fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_BODY, width=320)
        self.ent_search.pack(side="left", padx=(0, theme.SPACE_2))
        self.ent_search.bind("<KeyRelease>", lambda e: self._update_matches())
        self.opt_pedido = ctk.CTkOptionMenu(
            row, values=["—"], command=self._on_pick, height=theme.HEIGHT_INPUT,
            corner_radius=theme.RADIUS_MD, font=theme.FONT_BODY, fg_color=theme.BG_INPUT,
            button_color=theme.BORDER_STRONG, button_hover_color=theme.TEXT_MUTED,
            text_color=theme.TEXT_MAIN)
        self.opt_pedido.pack(side="left", fill="x", expand=True, padx=(0, theme.SPACE_3))
        self.lbl_count = ctk.CTkLabel(row, text="", font=theme.FONT_SMALL,
                                      text_color=theme.TEXT_MUTED)
        self.lbl_count.pack(side="left")

        # ── Informe de estado (todo el ancho, scrollable) ───────────────
        self.detail = ScrollFrame(self)
        self.detail.pack(fill="both", expand=True, padx=theme.SPACE_6,
                         pady=(0, theme.SPACE_4))
        self._placeholder("Cargando pedidos…")

    def _placeholder(self, msg: str) -> None:
        for w in self.detail.winfo_children():
            w.destroy()
        box = ctk.CTkFrame(self.detail, fg_color="transparent")
        box.pack(expand=True, pady=90)
        ctk.CTkLabel(box, text="▦", font=theme.font(38, "bold"),
                     text_color=theme.BORDER_STRONG).pack()
        ctk.CTkLabel(box, text=msg, font=theme.FONT_BODY_BOLD,
                     text_color=theme.TEXT_SUB).pack(pady=(theme.SPACE_2, 0))
        ctk.CTkLabel(box, text="Elige un pedido para ver su estado: avance, plazo,\n"
                              "fabricación y los documentos que requieren acción.",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                     justify="center").pack(pady=(2, 0))

    def _load_projects(self) -> None:
        def worker():
            try:
                data = erp_service.project_list()
                ui.en_ui(self, lambda: self._on_projects(data))
            except Exception as exc:
                logger.exception("Error proyectos")
                msg = str(exc)
                ui.en_ui(self, lambda: self._placeholder(f"✗  {msg}"))
        threading.Thread(target=worker, daemon=True).start()

    def _on_projects(self, data: list[dict]) -> None:
        self._projects = data
        self._update_matches()
        if data:
            self._placeholder("Elige un pedido")

    def _update_matches(self) -> None:
        q = self.ent_search.get().strip().lower()
        matches = self._projects if not q else [
            p for p in self._projects
            if q in str(p["pedido"]).lower() or q in str(p["cliente"]).lower()]
        self._label_to_pedido = {}
        labels = []
        for p in matches[:300]:
            lab = f"{p['pedido']}  ·  {p['cliente']}"
            labels.append(lab)
            self._label_to_pedido[lab] = p["pedido"]
        self.opt_pedido.configure(values=labels or ["— sin resultados —"])
        self.lbl_count.configure(text=f"{len(matches)} pedido(s)")
        if len(matches) == 1:
            self.opt_pedido.set(labels[0])
            self._on_pick(labels[0])

    @staticmethod
    def _base_pedido(p) -> str:
        """'P-26/023-S00' → 'P-26/023' (quita el sufijo de suministro)."""
        p = str(p or "").strip()
        return p[:-4] if len(p) > 4 and p[-4:-2].upper() == "-S" and p[-2:].isdigit() else p

    def select_pedido(self, pedido: str, _tries: int = 0) -> None:
        """Selecciona un pedido por su código (salto desde la paleta Ctrl+K).

        Tolera el sufijo -Sxx (la paleta pasa 'P-26/023-S00'; la lista de
        proyectos puede ir con o sin él). Los proyectos cargan en un hilo al
        abrir la vista: si aún no están, reintenta cada 300 ms (máx. ~12 s).
        """
        if not self._projects:
            if _tries < 40:
                self.after(300, lambda: self.select_pedido(pedido, _tries + 1))
            return
        base = self._base_pedido(pedido)
        self.ent_search.delete(0, "end")
        self.ent_search.insert(0, base)
        self._update_matches()          # con 1 match ya lo selecciona solo
        cur = self._pedido_current or ""
        if cur == pedido or self._base_pedido(cur) == base:
            return
        # Varios matches (-S00/-S01…): el exacto → el de mismo base → el primero
        labels = list(self._label_to_pedido)
        exact = [lab for lab in labels if self._label_to_pedido[lab] == pedido]
        same = [lab for lab in labels if self._base_pedido(self._label_to_pedido[lab]) == base]
        pick = (exact or same or labels)[:1]
        if pick:
            self.opt_pedido.set(pick[0])
            self._on_pick(pick[0])

    def _on_pick(self, label: str) -> None:
        pedido = self._label_to_pedido.get(label)
        if not pedido or pedido == self._pedido_current:
            return
        self._pedido_current = pedido
        self._tags_current = []
        self._show_loading(pedido)

        def worker():
            try:
                dash = erp_service.project_dashboard(pedido)
                bundle = erp_tags.fetch_pedido_bundle(pedido)   # equipos + OTs + cabecera (ERP)
                ui.en_ui(self, lambda: self._render_detail(pedido, dash, bundle))
            except Exception as exc:
                logger.exception("Error ficha pedido")
                msg = str(exc)
                ui.en_ui(self, lambda: self._placeholder(f"✗  {msg}"))
        threading.Thread(target=worker, daemon=True).start()

    def _show_loading(self, pedido: str) -> None:
        for w in self.detail.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.detail, text=f"⏳  Cargando {pedido}…", font=theme.FONT_BODY,
                     text_color=theme.TEXT_MUTED).pack(pady=60)

    def _render_detail(self, pedido: str, dash: dict | None, bundle: dict | None = None) -> None:
        if pedido != self._pedido_current:
            return
        for w in self.detail.winfo_children():
            w.destroy()
        if not dash:
            ui.empty_state(self.detail, "Sin datos para este pedido.", icon="▦")
            return
        scroll = self.detail
        kpis = dash["kpis"]
        seg = dash.get("seguimiento") or {}
        consulta = dash.get("consulta") or {}
        docs = dash.get("documents") or []

        verdict = self._status_verdict(kpis, seg)
        self._dash = dash
        self._bundle = bundle or {}
        self._tags = self._bundle.get("tags") or []
        # Índice de documentos del pedido por Nº Doc. EIPSA Y por Nº Doc. Cliente:
        # el ERP guarda en calc/dwg_num_doc_eipsa unas veces el nº EIPSA y otras
        # el del cliente (p.ej. V-1000100010-0124 en TR). Así casa en ambos casos.
        self._doc_index = {}
        for d in docs:
            for key in ("Nº Doc. EIPSA", "Nº Doc. Cliente"):
                k = _norm_doc(d.get(key))
                if k and k not in self._doc_index:
                    self._doc_index[k] = d
        self._subview = "estado"

        self._build_header_card(scroll, pedido, dash, consulta, docs, kpis, verdict)

        # Barra: conmutador de subvista a la izquierda, acciones a la derecha
        n_tags = sum(1 for t in self._tags if t.get("_vigente", True))
        bar = ctk.CTkFrame(scroll, fg_color="transparent")
        bar.pack(fill="x", pady=(0, theme.SPACE_3))
        self._seg_sub = ctk.CTkSegmentedButton(
            bar, values=["Estado del pedido",
                         f"Equipos & Tags ({n_tags})" if n_tags else "Equipos & Tags"],
            command=self._on_subview, height=theme.HEIGHT_BUTTON,
            font=theme.FONT_SMALL_BOLD, corner_radius=theme.RADIUS_MD,
            fg_color=theme.BG_CARD, selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER, unselected_color=theme.BG_CARD,
            unselected_hover_color=theme.BG_INPUT, text_color=theme.TEXT_MAIN)
        self._seg_sub.set("Estado del pedido")
        self._seg_sub.pack(side="left")
        btn = ui.button(bar, "Informe del pedido  →", "primary",
                        corner_radius=theme.RADIUS_MD)
        btn.configure(command=lambda p=pedido, b=btn: self._generate_pedido_report(p, b))
        btn.pack(side="right")
        ui.tooltip(btn, "Informe web completo: ficha, KPIs, predicción y toda la documentación.")

        self._body = ctk.CTkFrame(scroll, fg_color="transparent")
        self._body.pack(fill="both", expand=True)
        self._render_body()

    def _on_subview(self, value: str) -> None:
        self._subview = "tags" if value.startswith("Equipos") else "estado"
        self._render_body()

    # Por debajo de este ancho las dos columnas se apilan (una encima de otra)
    _TWO_COL_MIN = 1180

    def _render_body(self) -> None:
        body = getattr(self, "_body", None)
        if body is None:
            return
        for w in body.winfo_children():
            w.destroy()
        self._cols = None
        dash = self._dash or {}
        if self._subview == "tags":
            self._render_tags_block(body, self._tags)
            return

        # Dos columnas: a la izquierda el trabajo (fabricación y lo accionable),
        # a la derecha la ficha y el plazo. Así se aprovecha el ancho y el
        # informe cabe casi entero sin desplazarse.
        body.grid_columnconfigure(0, weight=62, uniform="col")
        body.grid_columnconfigure(1, weight=38, uniform="col")
        left = ctk.CTkFrame(body, fg_color="transparent")
        right = ctk.CTkFrame(body, fg_color="transparent")
        self._cols = (left, right)
        self._apply_columns()

        self._build_fase_erp(left, dash.get("consulta") or {})
        self._build_ots_block(left, self._bundle)
        self._build_atencion(left, dash.get("documents") or [])

        self._build_ficha(right, self._pedido_current or "", dash)
        self._build_seguimiento_block(right, dash.get("seguimiento") or {})

        body.bind("<Configure>", self._on_body_resize)

    def _apply_columns(self, ancho: int | None = None) -> None:
        """Coloca las dos columnas en paralelo, o apiladas si no caben."""
        if not getattr(self, "_cols", None):
            return
        left, right = self._cols
        if ancho is None:
            ancho = self._body.winfo_width()
        dos = ancho >= self._TWO_COL_MIN
        if getattr(self, "_dos_cols", None) is dos:
            return
        self._dos_cols = dos
        # `columnspan` y `pady` van SIEMPRE: grid() solo cambia lo que se le
        # pasa, así que al volver a dos columnas sin repetirlos se quedaría el
        # columnspan=2 de la versión apilada y una columna taparía a la otra.
        if dos:
            left.grid(row=0, column=0, columnspan=1, sticky="nsew",
                      padx=(0, theme.SPACE_3), pady=0)
            right.grid(row=0, column=1, columnspan=1, sticky="nsew", pady=0)
        else:
            # Apiladas: cada una a todo el ancho, no al 62 % / 38 % de su columna
            left.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0, pady=0)
            right.grid(row=1, column=0, columnspan=2, sticky="nsew",
                       padx=0, pady=(theme.SPACE_3, 0))

    def _on_body_resize(self, event) -> None:
        self._apply_columns(event.width)
