"""Vista Docusign — Contratos & Firmas (DocuSign eSignature).

Distribución profesional master-detail (sin pop-ups):
  • Cabecera con estado de API + última sync + botón actualizar.
  • KPIs: Pendientes · Completados · Rechazados · Expirados · Total.
  • Filtros: estado · rango de días · búsqueda.
  • Master-detail:
      - Izquierda  → lista de sobres (tarjetas: asunto, remitente, firmantes,
                     estado y fecha).
      - Derecha    → detalle EN LÍNEA del sobre seleccionado: Información,
                     Firmantes y Historial de eventos + descarga del PDF.
  • Estado "no configurado" con las variables .env necesarias.

Las llamadas a la API de DocuSign corren en hilos.
"""

import logging
import threading
import tkinter as tk
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.services import docusign as ds
from gui import theme
from gui.widgets import texto, ui
from gui.widgets.casillas import rect_redondo

logger = logging.getLogger(__name__)

ACCENT_DS = "#2563EB"

DAYS_OPTIONS = [
    ("Sin límite (todos)", 0), ("Últimos 7 días", 7), ("Últimos 14 días", 14),
    ("Últimos 30 días", 30), ("Últimos 60 días", 60), ("Últimos 90 días", 90),
    ("Últimos 180 días", 180), ("Últimos 365 días", 365),
]


def _fmt_date(s) -> str:
    return str(s)[:10] if s else "—"


def _initials(name: str) -> str:
    parts = [w[0] for w in str(name or "").split() if w]
    return "".join(parts)[:2].upper() or "?"


def _signer_color(status: str) -> str:
    st = (status or "").lower()
    if st == "completed":
        return theme.GREEN
    if st == "declined":
        return theme.RED
    return ACCENT_DS


def _avatar(parent, r: dict, size: int = 24):
    col = _signer_color(r.get("status"))
    circle = ctk.CTkFrame(parent, width=size, height=size, corner_radius=size // 2,
                          fg_color=theme.BG_INPUT, border_width=2, border_color=col)
    circle.pack_propagate(False)
    ctk.CTkLabel(circle, text=_initials(r.get("name", "")), font=theme.font(9, "bold"),
                 text_color=col).pack(expand=True)
    return circle


def _badge(parent, status: str):
    col = ds.status_color(status)
    return ctk.CTkLabel(parent, text=f"  {ds.status_label(status)}  ",
                        font=theme.FONT_TINY, text_color=col,
                        fg_color=theme.BG_INPUT, corner_radius=8, height=22)


def _section(parent, text: str):
    return ui.section_header(parent, text, ACCENT_DS)


class _ListaSobres(ctk.CTkFrame):
    """La lista de sobres, dibujada en un solo lienzo.

    Antes cada sobre era una tarjeta de CTkFrames y CTkLabels (con un círculo
    por firmante): unas 25 ventanas de Windows por sobre, más de mil con la
    bandeja normal, y volver a DocuSign tardaba ~600 ms en pintarlas. Aquí se
    ven igual —asunto, estado, remitente, fecha y firmantes— pero son trazos.
    """

    _ALTO_TEXTO = 18
    _ALTO_SUB = 16
    _AVATAR = 22
    _PAD = 10
    _HUECO = 8

    def __init__(self, master, on_select):
        super().__init__(master, fg_color="transparent")
        self._on_select = on_select
        self._escala = texto.escala_de(self)
        self._f_asunto = texto.fuente_ctk(theme.FONT_SMALL_BOLD, self)
        self._f_sub = texto.fuente_ctk(theme.FONT_TINY, self)
        self._f_ini = texto.fuente_ctk(theme.font(9, "bold"), self)
        self._sobres: list[dict] = []
        self._cajas: list[tuple[int, int, str]] = []     # (y0, y1, id) de cada tarjeta
        self._seleccionado: str | None = None
        self._encima: str | None = None
        self._vacio = ""
        self._ancho = 0

        self.canvas = tk.Canvas(self, bg=theme.BG_PAGE, highlightthickness=0, bd=0,
                                yscrollincrement=20)
        # La de CustomTkinter, como el resto de la app (la de Tk sale blanca)
        barra = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=barra.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        c = self.canvas
        c.bind("<Configure>", self._al_redimensionar)
        c.bind("<MouseWheel>", lambda e: c.yview_scroll(int(-e.delta / 120) * 2, "units"))
        c.bind("<Button-1>", self._clic)
        c.bind("<Motion>", self._mover)
        c.bind("<Leave>", lambda _e: self._resaltar(None))

    # ── API ──────────────────────────────────────────────────────────────────

    def mostrar(self, sobres: list[dict], seleccionado: str | None, vacio: str = "") -> None:
        self._sobres, self._seleccionado, self._vacio = list(sobres), seleccionado, vacio
        self.canvas.yview_moveto(0)
        self._pintar()

    def seleccionar(self, id_sobre: str | None) -> None:
        antes, self._seleccionado = self._seleccionado, id_sobre
        self._repintar(antes, id_sobre)

    # ── Dibujo ───────────────────────────────────────────────────────────────

    def _px(self, n: float) -> int:
        return round(n * self._escala)

    def _al_redimensionar(self, e) -> None:
        if e.width != self._ancho:
            self._ancho = e.width
            self._pintar()

    def _pintar(self) -> None:
        """La lista entera: al mostrarla y al cambiar de ancho."""
        c = self.canvas
        c.delete("all")
        self._cajas = []
        ancho = self._ancho or c.winfo_width()
        if ancho <= 20:
            return
        if not self._sobres:
            c.create_text(ancho / 2, self._px(60), text=f"✒\n{self._vacio}", justify="center",
                          font=self._f_asunto, fill=theme.TEXT_MUTED)
            c.configure(scrollregion=(0, 0, ancho, self._px(120)))
            return
        y = 0
        for i, env in enumerate(self._sobres):
            y1 = self._tarjeta(env, y, ancho, f"t{i}")
            self._cajas.append((y, y1, env.get("id")))
            y = y1 + self._px(self._HUECO)
        c.configure(scrollregion=(0, 0, ancho, y))

    def _repintar(self, *ids) -> None:
        """Solo las tarjetas que cambian (hover, selección): con toda la lista
        cada movimiento del ratón volvía a medir y dibujar todos los sobres."""
        ancho = self._ancho or self.canvas.winfo_width()
        for i, (y0, _y1, ident) in enumerate(self._cajas):
            if ident is not None and ident in ids:
                self.canvas.delete(f"t{i}")
                self._tarjeta(self._sobres[i], y0, ancho, f"t{i}")

    def _tarjeta(self, env: dict, y0: int, ancho: int, tag: str) -> int:
        c, px = self.canvas, self._px
        pad = px(self._PAD)
        firmantes = env.get("recipients") or []
        alto = (pad + px(self._ALTO_TEXTO) + px(2) + px(self._ALTO_SUB)
                + (px(8) + px(self._AVATAR) if firmantes else 0) + pad)
        y1 = y0 + alto
        ident = env.get("id")
        sel, encima = ident == self._seleccionado, ident == self._encima
        rect_redondo(c, 1, y0 + 1, ancho - 2, y1, px(10), tags=tag, width=1,
                     fill=theme.ACCENT_SOFT if sel else theme.BG_CARD,
                     outline=ACCENT_DS if sel else (theme.BORDER_STRONG if encima else theme.BORDER))
        x0, x1 = pad + 2, ancho - pad - 2

        # Línea 1: asunto + estado
        estado = env.get("status", "")
        etiqueta = f"  {ds.status_label(estado)}  "
        ancho_eti = self._f_sub.measure(etiqueta)
        yl = y0 + pad + px(self._ALTO_TEXTO) / 2
        rect_redondo(c, x1 - ancho_eti, yl - px(11), x1, yl + px(11), px(8), tags=tag,
                     fill=theme.BG_INPUT, outline=theme.BG_INPUT)
        c.create_text(x1 - ancho_eti / 2, yl, text=etiqueta.strip(), font=self._f_sub,
                      fill=ds.status_color(estado), tags=tag)
        asunto = env.get("subject") or "Sin asunto"
        c.create_text(x0, yl, anchor="w", font=self._f_asunto, fill=theme.TEXT_MAIN, tags=tag,
                      text=texto.cortar(asunto, x1 - ancho_eti - px(8) - x0, self._f_asunto))

        # Línea 2: remitente + fecha
        y2 = y0 + pad + px(self._ALTO_TEXTO) + px(2) + px(self._ALTO_SUB) / 2
        fecha = _fmt_date(env.get("sent_at"))
        ancho_fecha = self._f_sub.measure(fecha)
        c.create_text(x1, y2, anchor="e", text=fecha, font=self._f_sub, fill=theme.TEXT_MUTED,
                      tags=tag)
        remitente = env.get("sender_name") or env.get("sender") or "—"
        c.create_text(x0, y2, anchor="w", font=self._f_sub, fill=theme.TEXT_MUTED, tags=tag,
                      text=texto.cortar(remitente, x1 - ancho_fecha - px(8) - x0, self._f_sub))

        # Línea 3: firmantes
        if firmantes:
            d = px(self._AVATAR)
            ya = y0 + pad + px(self._ALTO_TEXTO) + px(2) + px(self._ALTO_SUB) + px(8)
            x = x0
            for r in firmantes[:6]:
                col = _signer_color(r.get("status"))
                # Borde fino: Tk no suaviza, y con 2 px el círculo sale dentado
                c.create_oval(x + 1, ya + 1, x + d - 1, ya + d - 1, fill=theme.BG_INPUT,
                              outline=col, width=1, tags=tag)
                c.create_text(x + d / 2, ya + d / 2, text=_initials(r.get("name", "")),
                              font=self._f_ini, fill=col, tags=tag)
                x += d + px(3)
            if len(firmantes) > 6:
                c.create_text(x + px(2), ya + d / 2, anchor="w", text=f"+{len(firmantes) - 6}",
                              font=self._f_sub, fill=theme.TEXT_MUTED, tags=tag)
        return y1

    # ── Ratón ────────────────────────────────────────────────────────────────

    def _sobre_en(self, e) -> dict | None:
        y = self.canvas.canvasy(e.y)
        for (y0, y1, _ident), env in zip(self._cajas, self._sobres):
            if y0 <= y <= y1:
                return env
        return None

    def _clic(self, e) -> None:
        env = self._sobre_en(e)
        if env is not None:
            self._on_select(env)

    def _mover(self, e) -> None:
        env = self._sobre_en(e)
        self.canvas.configure(cursor="hand2" if env else "")
        self._resaltar(env.get("id") if env else None)

    def _resaltar(self, ident: str | None) -> None:
        if ident != self._encima:
            antes, self._encima = self._encima, ident
            self._repintar(antes, ident)


# ════════════════════════════════════════════════════════════════════════════
#  Vista principal
# ════════════════════════════════════════════════════════════════════════════

class DocusignView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_PAGE, **kwargs)
        self._envelopes: list[dict] = []
        self._status_filter = ""
        self._days = 30
        self._selected_id: str | None = None
        self._build_header()
        if not ds.deps_available():
            self._render_missing_deps()
        elif not ds.is_configured():
            self._render_not_configured()
        else:
            self._build_body()
            self.after(80, self._fetch)

    # ── Cabecera ─────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ui.page_header(self, "DocuSign",
                             "Sobres de firma electrónica: estado, firmantes y descarga del PDF firmado.",
                             icon="✒", icon_color=ACCENT_DS, pad_bottom=theme.SPACE_2, help_key="docusign")
        actions = hdr.actions
        self.lbl_api = ctk.CTkLabel(actions, text="", font=theme.FONT_SMALL_BOLD)
        self.lbl_api.pack(side="left", padx=(0, theme.SPACE_2))
        self.lbl_sync = ctk.CTkLabel(actions, text="", font=theme.FONT_TINY,
                                     text_color=theme.TEXT_MUTED)
        self.lbl_sync.pack(side="left", padx=(0, theme.SPACE_2))
        self.btn_refresh = ui.button(actions, "↻  Actualizar", "outline", size="sm", width=120,
                                     text_color=theme.TEXT_SUB, command=self._fetch)
        self.btn_refresh.pack(side="left")

    # ── Estado no configurado ────────────────────────────────────────────────

    def _render_not_configured(self) -> None:
        box = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=14,
                           border_width=1, border_color=theme.BORDER)
        box.pack(fill="x", padx=theme.SPACE_6, pady=theme.SPACE_5)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(padx=theme.SPACE_6, pady=theme.SPACE_6)
        ctk.CTkLabel(inner, text="✒", font=theme.font(34, "bold"), text_color=ACCENT_DS).pack()
        ctk.CTkLabel(inner, text="DocuSign no configurado", font=theme.font(16, "bold"),
                     text_color=theme.TEXT_MAIN).pack(pady=(theme.SPACE_2, theme.SPACE_1))
        ctk.CTkLabel(inner, text="Para activar la integración añade estas variables al .env del proyecto:",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                     wraplength=520, justify="center").pack(pady=(0, theme.SPACE_3))
        env_block = (
            "DOCUSIGN_INTEGRATION_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n"
            "DOCUSIGN_USER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n"
            "DOCUSIGN_ACCOUNT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n"
            "DOCUSIGN_BASE_URL=https://demo.docusign.net\n"
            "DOCUSIGN_RSA_PRIVATE_KEY_PATH=docusign_private.pem"
        )
        code = ctk.CTkFrame(inner, fg_color=theme.BG_PAGE, corner_radius=10,
                            border_width=1, border_color=theme.BORDER)
        code.pack(fill="x")
        ctk.CTkLabel(code, text=env_block, font=theme.mfont(11), text_color="#A5F3FC",
                     justify="left", anchor="w").pack(fill="x", padx=theme.SPACE_4, pady=theme.SPACE_3)

    def _render_missing_deps(self) -> None:
        """Dependencias de DocuSign ausentes (PyJWT/requests) — aviso, sin romper."""
        box = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=14,
                           border_width=1, border_color=theme.BORDER)
        box.pack(fill="x", padx=theme.SPACE_6, pady=theme.SPACE_5)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(padx=theme.SPACE_6, pady=theme.SPACE_6)
        ctk.CTkLabel(inner, text="✒", font=theme.font(34, "bold"), text_color=ACCENT_DS).pack()
        ctk.CTkLabel(inner, text="Faltan dependencias de DocuSign", font=theme.font(16, "bold"),
                     text_color=theme.TEXT_MAIN).pack(pady=(theme.SPACE_2, theme.SPACE_1))
        ctk.CTkLabel(inner, text="Esta sección necesita PyJWT y requests. Instálalos y reinicia:",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                     wraplength=520, justify="center").pack(pady=(0, theme.SPACE_3))
        code = ctk.CTkFrame(inner, fg_color=theme.BG_PAGE, corner_radius=10,
                            border_width=1, border_color=theme.BORDER)
        code.pack(fill="x")
        ctk.CTkLabel(code, text="pip install pyjwt requests", font=theme.mfont(11),
                     text_color="#A5F3FC", justify="left", anchor="w").pack(
            fill="x", padx=theme.SPACE_4, pady=theme.SPACE_3)

    # ── Cuerpo: KPIs + filtros + master-detail ───────────────────────────────

    def _build_body(self) -> None:
        # KPIs
        kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        kpi_row.pack(fill="x", padx=theme.SPACE_6, pady=(theme.SPACE_2, theme.SPACE_2))
        self._kpi_labels: dict[str, ctk.CTkLabel] = {}
        kdefs = [("Pendientes", "sent", theme.AMBER), ("Completados", "completed", theme.GREEN),
                 ("Rechazados", "declined", theme.RED), ("Expirados", "timed_out", theme.AMBER),
                 ("Total", "total", ACCENT_DS)]
        for i, (label, key, col) in enumerate(kdefs):
            kpi_row.grid_columnconfigure(i, weight=1, uniform="k")
            card = ctk.CTkFrame(kpi_row, fg_color=theme.BG_CARD, corner_radius=10,
                                border_width=1, border_color=theme.BORDER)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else theme.SPACE_2, 0))
            ctk.CTkLabel(card, text=label.upper(), font=theme.FONT_LABEL,
                         text_color=theme.TEXT_MUTED, anchor="w").pack(
                anchor="w", padx=theme.SPACE_3, pady=(theme.SPACE_3, 0))
            v = ctk.CTkLabel(card, text="…", font=theme.font(22, "bold"), text_color=col, anchor="w")
            v.pack(anchor="w", padx=theme.SPACE_3, pady=(0, theme.SPACE_3))
            self._kpi_labels[key] = v

        # Filtros
        filters = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=10,
                               border_width=1, border_color=theme.BORDER)
        filters.pack(fill="x", padx=theme.SPACE_6, pady=(0, theme.SPACE_2))
        fin = ctk.CTkFrame(filters, fg_color="transparent")
        fin.pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_2)

        estados = ["Todos los estados"] + [m["label"] for m in ds.STATUS_META.values()]
        self._estado_label_to_key = {m["label"]: k for k, m in ds.STATUS_META.items()}
        self.opt_estado = ctk.CTkOptionMenu(
            fin, values=estados, width=180, height=theme.HEIGHT_INPUT,
            corner_radius=theme.RADIUS_MD, font=theme.FONT_SMALL,
            fg_color=theme.BG_INPUT, button_color=theme.BORDER_STRONG,
            button_hover_color=theme.TEXT_MUTED, text_color=theme.TEXT_MAIN, command=self._on_estado)
        self.opt_estado.pack(side="left", padx=(0, theme.SPACE_2))

        self.opt_days = ctk.CTkOptionMenu(
            fin, values=[d[0] for d in DAYS_OPTIONS], width=170, height=theme.HEIGHT_INPUT,
            corner_radius=theme.RADIUS_MD, font=theme.FONT_SMALL,
            fg_color=theme.BG_INPUT, button_color=theme.BORDER_STRONG,
            button_hover_color=theme.TEXT_MUTED, text_color=theme.TEXT_MAIN, command=self._on_days)
        self.opt_days.set("Últimos 30 días")
        self.opt_days.pack(side="left", padx=(0, theme.SPACE_2))

        self.ent_search = ctk.CTkEntry(
            fin, placeholder_text="Buscar asunto o remitente…",
            height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_MAIN, font=theme.FONT_SMALL)
        self.ent_search.pack(side="left", fill="x", expand=True)
        self.ent_search.bind("<KeyRelease>", lambda e: self._render_list())

        # Master-detail
        split = ctk.CTkFrame(self, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=theme.SPACE_6, pady=(0, theme.SPACE_5))

        left = ctk.CTkFrame(split, fg_color="transparent", width=520)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.list_status = ctk.CTkLabel(left, text="", font=theme.FONT_TINY,
                                        text_color=theme.TEXT_MUTED, anchor="w")
        self.list_status.pack(fill="x", pady=(0, theme.SPACE_1))
        self.lista = _ListaSobres(left, on_select=self._select)
        self.lista.pack(fill="both", expand=True)

        self.detail = ctk.CTkFrame(split, fg_color=theme.BG_CARD, corner_radius=12,
                                   border_width=1, border_color=theme.BORDER)
        self.detail.pack(side="left", fill="both", expand=True, padx=(theme.SPACE_4, 0))
        self._detail_placeholder()

    # ── Filtros ──────────────────────────────────────────────────────────────

    def _on_estado(self, label: str) -> None:
        # Filtro de estado en cliente — no requiere volver a llamar a la API.
        self._status_filter = self._estado_label_to_key.get(label, "")
        self._render_list()

    def _on_days(self, label: str) -> None:
        # Cambiar el periodo sí cambia la consulta al servidor → re-fetch.
        self._days = dict(DAYS_OPTIONS).get(label, 30)
        self._fetch()

    # ── Fetch ────────────────────────────────────────────────────────────────

    def _fetch(self) -> None:
        self.btn_refresh.configure(text="Actualizando…")
        self.list_status.configure(text="⏳  Cargando sobres…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                svc = ds.get_service()
                effective = 3650 if self._days == 0 else self._days
                # Una sola llamada de red: todos los estados del periodo.
                envelopes = svc.list_envelopes(days=effective)
                kpis = ds.kpis_from_envelopes(envelopes)
                ui.en_ui(self, lambda: self._on_fetched(envelopes, kpis))
            except Exception as exc:
                logger.exception("Error DocuSign fetch")
                msg = str(exc)
                ui.en_ui(self, lambda: self._on_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _on_error(self, msg: str) -> None:
        self.lbl_api.configure(text="✗ Error de API", text_color=theme.RED)
        self.btn_refresh.configure(text="↻  Actualizar")
        self.list_status.configure(text=f"✗  {msg}", text_color=theme.RED)

    def _on_fetched(self, envelopes: list[dict], kpis: dict) -> None:
        self._envelopes = envelopes
        self.lbl_api.configure(text="● API conectada", text_color=theme.GREEN)
        self.lbl_sync.configure(text=f"Sync: {datetime.now().strftime('%H:%M')}")
        self.btn_refresh.configure(text="↻  Actualizar")
        by = kpis.get("by_status", {})
        for key, lbl in self._kpi_labels.items():
            lbl.configure(text=str(kpis.get("total", 0) if key == "total" else by.get(key, 0)))
        self._render_list()

    # ── Lista (master) ───────────────────────────────────────────────────────

    def _filtered(self) -> list[dict]:
        rows = self._envelopes
        if self._status_filter:
            rows = [e for e in rows if e.get("status") == self._status_filter]
        q = self.ent_search.get().strip().lower()
        if q:
            rows = [e for e in rows
                    if q in str(e.get("subject", "")).lower()
                    or q in str(e.get("sender_name", "")).lower()
                    or q in str(e.get("sender", "")).lower()]
        return rows

    def _render_list(self) -> None:
        rows = self._filtered()
        self.lista.mostrar(rows, self._selected_id, vacio="No se encontraron sobres")
        self.list_status.configure(text=f"{len(rows)} sobre(s)" if rows else "0 sobres",
                                   text_color=theme.TEXT_MUTED)

    # ── Detalle (inline) ─────────────────────────────────────────────────────

    def _detail_placeholder(self) -> None:
        for w in self.detail.winfo_children():
            w.destroy()
        box = ctk.CTkFrame(self.detail, fg_color="transparent")
        box.pack(expand=True, pady=70)
        ctk.CTkLabel(box, text="✒", font=theme.font(34, "bold"),
                     text_color=theme.BORDER_STRONG).pack()
        ctk.CTkLabel(box, text="Selecciona un sobre", font=theme.FONT_BODY_BOLD,
                     text_color=theme.TEXT_SUB).pack(pady=(theme.SPACE_2, 0))
        ctk.CTkLabel(box, text="Haz clic en un sobre para ver su información,\nfirmantes e historial.",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, justify="center").pack(pady=(2, 0))

    def _select(self, env: dict) -> None:
        new_id = env.get("id")
        if new_id == self._selected_id:
            return
        self._selected_id = new_id
        self.lista.seleccionar(new_id)
        self._show_detail_loading()

        def worker():
            try:
                full = ds.get_service().get_envelope(self._selected_id)
                ui.en_ui(self, lambda: self._render_detail(env, full))
            except Exception as exc:
                # Si el detalle falla, mostramos al menos lo que ya tenemos del listado
                logger.warning("Detalle DocuSign no disponible: %s", exc)
                ui.en_ui(self, lambda: self._render_detail(env, env))

        threading.Thread(target=worker, daemon=True).start()

    def _show_detail_loading(self) -> None:
        for w in self.detail.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.detail, text="⏳  Cargando detalle…", font=theme.FONT_BODY,
                     text_color=theme.TEXT_MUTED).pack(pady=50)

    def _render_detail(self, env: dict, data: dict) -> None:
        if env.get("id") != self._selected_id:
            return
        for w in self.detail.winfo_children():
            w.destroy()

        # Cabecera del detalle
        head = ctk.CTkFrame(self.detail, fg_color="transparent")
        head.pack(fill="x", padx=theme.SPACE_4, pady=(theme.SPACE_3, theme.SPACE_2))
        bar = ctk.CTkFrame(head, fg_color="transparent")
        bar.pack(fill="x")
        title_wrap = ctk.CTkFrame(bar, fg_color="transparent")
        title_wrap.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_wrap, text=data.get("subject") or "Detalle del sobre",
                     font=theme.font(15, "bold"), text_color=theme.TEXT_MAIN,
                     anchor="w", justify="left", wraplength=620).pack(anchor="w")
        _badge(title_wrap, data.get("status", "")).pack(anchor="w", pady=(theme.SPACE_2, 0))
        if data.get("status") == "completed":
            ui.button(bar, "⤓  Descargar PDF", "chip", size="sm", width=140, height=32,
                      text_color=theme.GREEN, border_width=0,
                      command=lambda: self._download(env)).pack(side="right")
        ctk.CTkFrame(head, fg_color=theme.BORDER, height=1).pack(fill="x", pady=(theme.SPACE_3, 0))

        body = ctk.CTkScrollableFrame(self.detail, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=theme.SPACE_3, pady=(0, theme.SPACE_3))

        # Información
        _section(body, "Información").pack(fill="x", pady=(theme.SPACE_1, theme.SPACE_2))
        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x", pady=(0, theme.SPACE_3))
        for c in range(2):
            grid.grid_columnconfigure(c, weight=1, uniform="i")
        info = [("Remitente", data.get("sender_name") or data.get("sender") or "—"),
                ("Enviado", _fmt_date(data.get("sent_at"))),
                ("Completado", _fmt_date(data.get("completed_at"))),
                ("Expira", _fmt_date(data.get("expires_at")))]
        for i, (label, val) in enumerate(info):
            cell = ctk.CTkFrame(grid, fg_color=theme.BG_PAGE, corner_radius=8,
                                border_width=1, border_color=theme.BORDER)
            cell.grid(row=i // 2, column=i % 2, sticky="ew",
                      padx=(0 if i % 2 == 0 else theme.SPACE_2, 0), pady=(0, theme.SPACE_2))
            ctk.CTkLabel(cell, text=label.upper(), font=theme.FONT_TINY,
                         text_color=theme.TEXT_MUTED, anchor="w").pack(
                anchor="w", padx=theme.SPACE_3, pady=(theme.SPACE_2, 0))
            ctk.CTkLabel(cell, text=str(val), font=theme.FONT_SMALL_BOLD,
                         text_color=theme.TEXT_MAIN, anchor="w").pack(
                anchor="w", padx=theme.SPACE_3, pady=(0, theme.SPACE_2))

        # Firmantes
        recips = data.get("recipients") or []
        if recips:
            _section(body, f"Firmantes ({len(recips)})").pack(fill="x", pady=(0, theme.SPACE_2))
            for r in recips:
                rrow = ctk.CTkFrame(body, fg_color=theme.BG_PAGE, corner_radius=8,
                                    border_width=1, border_color=theme.BORDER)
                rrow.pack(fill="x", pady=(0, theme.SPACE_1))
                _avatar(rrow, r, size=26).pack(side="left", padx=theme.SPACE_2, pady=theme.SPACE_2)
                mid = ctk.CTkFrame(rrow, fg_color="transparent")
                mid.pack(side="left", fill="x", expand=True, pady=theme.SPACE_2)
                ctk.CTkLabel(mid, text=r.get("name", "—"), font=theme.FONT_SMALL_BOLD,
                             text_color=theme.TEXT_MAIN, anchor="w").pack(anchor="w")
                ctk.CTkLabel(mid, text=r.get("email", ""), font=theme.FONT_TINY,
                             text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
                _badge(rrow, r.get("status", "")).pack(side="right", padx=theme.SPACE_3)

        # Historial
        history = data.get("history") or []
        if history:
            _section(body, "Historial de eventos").pack(fill="x", pady=(theme.SPACE_2, theme.SPACE_2))
            tl = ctk.CTkFrame(body, fg_color="transparent")
            tl.pack(fill="x")
            for h in history:
                hrow = ctk.CTkFrame(tl, fg_color="transparent")
                hrow.pack(fill="x", pady=2)
                ctk.CTkFrame(hrow, fg_color=ACCENT_DS, width=8, height=8, corner_radius=4).pack(
                    side="left", padx=(theme.SPACE_1, theme.SPACE_3))
                txt = ctk.CTkFrame(hrow, fg_color="transparent")
                txt.pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(txt, text=h.get("event") or "Evento", font=theme.FONT_SMALL,
                             text_color=theme.TEXT_SUB, anchor="w").pack(anchor="w")
                if h.get("user"):
                    ctk.CTkLabel(txt, text=h.get("user"), font=theme.FONT_TINY,
                                 text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
                if h.get("date"):
                    ctk.CTkLabel(hrow, text=_fmt_date(h.get("date")), font=theme.mfont(9),
                                 text_color=theme.TEXT_MUTED).pack(side="right", padx=theme.SPACE_2)

    # ── Descarga ─────────────────────────────────────────────────────────────

    def _download(self, env: dict) -> None:
        env_id = env.get("id")
        path = filedialog.asksaveasfilename(
            parent=self, title="Guardar PDF firmado", defaultextension=".pdf",
            initialfile=f"sobre_{env_id}.pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return

        def worker():
            try:
                data = ds.get_service().download_combined_pdf(env_id)
                with open(path, "wb") as f:
                    f.write(data)
                import os as _os
                ui.en_ui(self, lambda: ui.toast(
                    self, "PDF descargado", _os.path.basename(path), kind="success"))
            except Exception as exc:
                msg = str(exc)
                ui.en_ui(self, lambda: messagebox.showerror(
                    "Error", f"No se pudo descargar:\n{msg}", parent=self))

        threading.Thread(target=worker, daemon=True).start()
