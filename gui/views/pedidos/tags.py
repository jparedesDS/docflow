"""La tabla de equipos del pedido.

Cada fila es un tag con sus documentos, su fabricación y sus órdenes de
taller. Son métodos de PedidosView, agrupados aparte de la ficha.
"""

import logging
from collections import Counter

import customtkinter as ctk

from gui import theme
from gui.views.documentos import _trunc
from gui.widgets import ui
from gui.widgets.pilltable import PillTable

from gui.views.pedidos.comun import (
    TAGS_PAGE_SIZE,
    TAG_COLS,
    _DOC_SYM_COLOR,
    _norm_doc,
    _section_header,
    _tag_state_color,
)
from gui.views.pedidos.detalle_tag import (
    TagDetailWindow,
)

logger = logging.getLogger(__name__)


class TagsMixin:
    """La tabla de equipos del pedido."""

    def _render_tags_block(self, parent, tags: list[dict]) -> None:
        _section_header(parent, "Equipos & Tags").pack(fill="x", pady=(0, theme.SPACE_2))
        bundle = getattr(self, "_bundle", {}) or {}
        if not bundle.get("available", True) and not tags:
            ui.empty_state(parent, "ERP no disponible",
                           hint="Los equipos se leen del ERP (PostgreSQL local). Ábrelo y vuelve a intentarlo.",
                           icon="▦", pady=30)
            return
        if not tags:
            ui.empty_state(parent, "Este pedido no tiene equipos registrados en el ERP.",
                           icon="▦", pady=30)
            return
        self._tags_current = tags

        # KPIs del bloque (solo revisiones vigentes, sin eliminados)
        activos = [t for t in tags if t.get("_vigente", True) and not t.get("_eliminado")]
        n = len(activos)
        fabricados = sum(1 for t in activos if t.get("Estado Fab.", "").upper() == "FABRICADO")
        con_plano = sum(1 for t in activos if t.get("Plano Dim."))
        ots_abiertas = sum(t.get("_ot_abiertas", 0) for t in activos)
        docs_ok, docs_tot = self._docs_progress(activos)
        familias = Counter(t.get("Familia", "") for t in activos)
        summ = ctk.CTkFrame(parent, fg_color="transparent")
        summ.pack(fill="x", pady=(0, theme.SPACE_1))
        ctk.CTkLabel(summ, text=f"{n} equipos", font=theme.FONT_SMALL_BOLD,
                     text_color=theme.TEXT_MAIN).pack(side="left", padx=(0, theme.SPACE_3))
        for txt, col in (
            (f"Fabricados {fabricados}/{n}", theme.GREEN if n and fabricados == n else theme.AMBER),
            (f"Con plano {con_plano}/{n}", theme.TEXT_SUB),
            (f"OTs en curso {ots_abiertas}", theme.AMBER if ots_abiertas else theme.TEXT_SUB),
            (f"Docs aprobados {docs_ok}/{docs_tot}" if docs_tot else "Sin docs enlazados",
             theme.GREEN if docs_tot and docs_ok == docs_tot else theme.TEXT_SUB),
        ):
            ui.badge(summ, txt, col).pack(side="left", padx=(0, theme.SPACE_1))
        if len(familias) > 1:
            ctk.CTkLabel(summ, text="  ·  " + " · ".join(f"{f} {c}" for f, c in familias.most_common()),
                         font=theme.FONT_TINY, text_color=theme.TEXT_MUTED).pack(side="left")

        # Toolbar: búsqueda + familia + estado de fabricación
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", pady=(theme.SPACE_1, theme.SPACE_1))
        self._tags_search = ctk.CTkEntry(
            toolbar, placeholder_text="Buscar TAG, tipo, tamaño, plano, documento…",
            height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD, fg_color=theme.BG_INPUT,
            border_color=theme.BORDER, text_color=theme.TEXT_MAIN, font=theme.FONT_SMALL)
        self._tags_search.pack(side="left", fill="x", expand=True, padx=(0, theme.SPACE_2))
        self._tags_search.bind("<KeyRelease>", lambda e: self._refilter_tags())
        opt_kw = dict(height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD, font=theme.FONT_SMALL,
                      fg_color=theme.BG_INPUT, button_color=theme.BORDER_STRONG,
                      button_hover_color=theme.TEXT_MUTED, text_color=theme.TEXT_MAIN,
                      command=lambda _v: self._refilter_tags())
        self._tags_familia = ctk.CTkOptionMenu(
            toolbar, values=["Todas"] + [f for f, _ in familias.most_common()], width=140, **opt_kw)
        self._tags_familia.set("Todas")
        self._tags_familia.pack(side="left", padx=(0, theme.SPACE_2))
        self._tags_estado = ctk.CTkOptionMenu(
            toolbar, values=["Todos", "Fabricado", "Pendiente", "Eliminado"], width=140, **opt_kw)
        self._tags_estado.set("Todos")
        self._tags_estado.pack(side="left", padx=(0, theme.SPACE_2))
        # Revisiones superadas (tag_state SUPERADO): ocultas por defecto
        self._tags_superados = ctk.BooleanVar(value=False)
        n_sup = sum(1 for t in tags if not t.get("_vigente", True))
        if n_sup:
            ctk.CTkCheckBox(toolbar, text=f"Incluir superados ({n_sup})",
                            variable=self._tags_superados, font=theme.FONT_TINY,
                            text_color=theme.TEXT_SUB, checkbox_width=18, checkbox_height=18,
                            command=self._refilter_tags).pack(side="left", padx=(0, theme.SPACE_2))
        self._tags_count = ctk.CTkLabel(toolbar, text="", font=theme.FONT_SMALL,
                                        text_color=theme.TEXT_MUTED)
        self._tags_count.pack(side="left")

        # Paginación: un pedido puede traer cientos de equipos y pintarlos todos
        # de golpe deja a Tk sin terminar el layout (la tabla salía en blanco).
        pager = ctk.CTkFrame(toolbar, fg_color="transparent")
        pager.pack(side="right")
        self._tags_page = 0
        self._btn_tag_prev = ui.button(pager, "‹", "outline", size="xs", width=30,
                                       font=theme.FONT_BUTTON, text_color=theme.TEXT_SUB,
                                       command=lambda: self._goto_tags_page(self._tags_page - 1))
        self._btn_tag_prev.pack(side="left", padx=theme.SPACE_1)
        self._lbl_tag_page = ctk.CTkLabel(pager, text="—", font=theme.FONT_SMALL,
                                          text_color=theme.TEXT_SUB, width=92)
        self._lbl_tag_page.pack(side="left", padx=theme.SPACE_1)
        self._btn_tag_next = ui.button(pager, "›", "outline", size="xs", width=30,
                                       font=theme.FONT_BUTTON, text_color=theme.TEXT_SUB,
                                       command=lambda: self._goto_tags_page(self._tags_page + 1))
        self._btn_tag_next.pack(side="left", padx=theme.SPACE_1)

        ctk.CTkLabel(parent, text="doble-click en un equipo: ficha completa, documentación "
                                  "enlazada y órdenes de fabricación",
                     font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, anchor="w").pack(
            fill="x", pady=(0, theme.SPACE_1))

        h = min(max(len(tags), 5), TAGS_PAGE_SIZE) * 40 + 70
        host = ctk.CTkFrame(parent, fg_color="transparent", height=h)
        host.pack(fill="x", pady=(0, theme.SPACE_3))
        host.pack_propagate(False)
        self._tags_sort: tuple[str, bool] = ("TAG", True)
        self._tags_table = PillTable(
            host, columns=TAG_COLS, on_double_click=self._open_tag_detail,
            on_sort=self._on_tags_sort, rowheight=40)
        self._tags_table.pack(fill="both", expand=True)
        self._populate_tags_table()

    # Símbolo por estado documental (docs enlazados a un equipo)
    _DOC_SYM = (("aprobado", "✓"), ("rechaz", "✕"), ("com", "⚠"), ("enviado", "⏳"))

    def _doc_state(self, num: str) -> tuple[str, str, str]:
        """(símbolo, estado, Nº Doc. EIPSA) del documento `num` —nº EIPSA o del
        cliente— según Documentos; ('?', '', '') si no figura."""
        d = (self._doc_index or {}).get(_norm_doc(num))
        if not d:
            return "?", "", ""
        eipsa = str(d.get("Nº Doc. EIPSA", "") or "").strip()
        est = str(d.get("Estado", "") or "").strip()
        low = est.lower()
        for key, sym in self._DOC_SYM:
            if key in low:
                return sym, est, eipsa
        return "○", est or "Sin enviar", eipsa

    def _docs_cell(self, t: dict) -> dict:
        """Celda «Docs»: 'CAL ✓  PLG ⚠', coloreada por el peor de los dos."""
        parts, simbolos = [], []
        for lab, num in (("CAL", t.get("Doc EIPSA Calc.", "")), ("PLG", t.get("Doc EIPSA Plano", ""))):
            if num:
                sym = self._doc_state(num)[0]
                parts.append(f"{lab} {sym}")
                simbolos.append(sym)
        if not parts:
            return {"text": "—", "fg": theme.TEXT_MUTED}
        # Manda el más grave: rechazado > comentado > pendiente > sin datos > ok
        for peor in ("✕", "⚠", "⏳", "○", "?", "✓"):
            if peor in simbolos:
                return {"text": "  ".join(parts), "fg": _DOC_SYM_COLOR[peor], "bold": True}
        return {"text": "  ".join(parts)}

    def _docs_progress(self, tags: list[dict]) -> tuple[int, int]:
        """(aprobados, total) de los documentos enlazados a los equipos (sin repetir)."""
        ok = tot = 0
        seen: set[str] = set()
        for t in tags:
            for num in (t.get("Doc EIPSA Calc.", ""), t.get("Doc EIPSA Plano", "")):
                if not num or num in seen:
                    continue
                seen.add(num)
                sym = self._doc_state(num)[0]
                if sym == "?":
                    continue
                tot += 1
                ok += sym == "✓"
        return ok, tot

    @staticmethod
    def _fab_cell(t: dict) -> dict:
        """Celda «Fabricación»: pill verde/roja, como el Estado de Documentos."""
        if t.get("_eliminado"):
            return {"text": "✕  Eliminado", "pill": True, "fg": theme.RED,
                    "pill_bg": ui.blend(theme.RED, theme.BG_CARD, 0.20)}
        if t.get("Estado Fab.", "").upper() == "FABRICADO":
            return {"text": "✓  Fabricado", "pill": True, "fg": theme.GREEN,
                    "pill_bg": ui.blend(theme.GREEN, theme.BG_CARD, 0.20)}
        return {"text": "○  Pendiente", "fg": theme.TEXT_MUTED}

    def _ots_cell(self, t: dict) -> dict:
        """Celda «OTs»: «2/3» cerradas — verde si todas, ámbar si queda alguna.

        El texto del ERP es «2/3 terminadas»; en la columna solo cabe la cifra.
        """
        txt = str(t.get("OTs", "") or "").split(" ")[0]
        if not txt:
            return {"text": "—", "fg": theme.TEXT_MUTED}
        abiertas = t.get("_ot_abiertas", 0)
        return {"text": txt, "bold": True,
                "fg": theme.AMBER if abiertas else theme.GREEN}

    def _build_tag_cells(self, t: dict) -> dict:
        """Celdas con estilo de un equipo (mismo lenguaje visual que Documentos)."""
        vigente = t.get("_vigente", True)
        eliminado = bool(t.get("_eliminado"))
        estado = str(t.get("Estado", "") or "")
        ecol = _tag_state_color(estado, vigente, eliminado)
        plano = t.get("Plano Dim.", "")
        if plano and t.get("Rev. Plano Dim."):
            plano = f"{plano}  r{t['Rev. Plano Dim.']}"
        insp = str(t.get("Inspección", "") or "")
        return {
            "Familia":    {"text": t.get("Familia", ""), "fg": theme.TEXT_SUB},
            # El TAG es la identidad de la fila: en acento, como el Nº de documento
            "TAG":        {"text": t.get("TAG", ""), "fg": theme.ACCENT, "bold": True},
            "Tipo":       {"text": _trunc(t.get("Tipo", ""), 40)},
            "Tamaño":     {"text": t.get("Tamaño", "")},
            "Rating":     {"text": t.get("Rating", "")},
            "Facing":     {"text": t.get("Facing", "")},
            "Estado":     {"text": estado or "—", "pill": bool(estado), "fg": ecol,
                           "pill_bg": ui.blend(ecol, theme.BG_CARD, 0.20)},
            "Fab.":       self._fab_cell(t),
            "Insp.":      {"text": insp or "—",
                           "fg": theme.TEXT_MAIN if insp else theme.TEXT_MUTED},
            "Plano Dim.": {"text": plano or "—",
                           "fg": theme.TEXT_MAIN if plano else theme.TEXT_MUTED},
            "OTs":        self._ots_cell(t),
            "Docs":       self._docs_cell(t),
        }

    def _on_tags_sort(self, key: str) -> None:
        col, asc = getattr(self, "_tags_sort", ("TAG", True))
        self._tags_sort = (key, not asc if key == col else True)
        self._refilter_tags()

    def _refilter_tags(self) -> None:
        """Cambió el filtro o el orden: se vuelve a la primera página."""
        self._tags_page = 0
        self._populate_tags_table()

    def _populate_tags_table(self) -> None:
        """Rellena la tabla aplicando búsqueda + familia + estado de fabricación.

        El id de cada fila conserva el índice en self._tags_current para que el
        doble-click abra el equipo correcto aunque la lista esté filtrada.
        """
        table = getattr(self, "_tags_table", None)
        if table is None:
            return
        q = self._tags_search.get().strip().lower()
        familia = self._tags_familia.get()
        estado = self._tags_estado.get()
        superados = bool(self._tags_superados.get())

        visibles = []
        total = 0
        for idx, t in enumerate(self._tags_current):
            if not t.get("_vigente", True) and not superados:
                continue
            total += 1
            if familia != "Todas" and t.get("Familia") != familia:
                continue
            fab = "Eliminado" if t.get("_eliminado") else (
                "Fabricado" if t.get("Estado Fab.", "").upper() == "FABRICADO" else "Pendiente")
            if estado != "Todos" and fab != estado:
                continue
            if q and not any(q in str(v).lower() for k, v in t.items() if not k.startswith("_")):
                continue
            visibles.append((idx, t))

        col, asc = getattr(self, "_tags_sort", ("TAG", True))
        clave = {"Fab.": lambda t: self._fab_cell(t)["text"],
                 "Docs": lambda t: self._docs_cell(t)["text"]}.get(
            col, lambda t, c=col: str(t.get(c, "") or ""))
        visibles.sort(key=lambda p: clave(p[1]).lower(), reverse=not asc)
        table.set_sort_arrow(col, asc)

        paginas = max(1, -(-len(visibles) // TAGS_PAGE_SIZE))
        self._tags_page = max(0, min(self._tags_page, paginas - 1))
        ini = self._tags_page * TAGS_PAGE_SIZE
        pagina = visibles[ini:ini + TAGS_PAGE_SIZE]

        table.set_rows([(f"tag_{idx}", self._build_tag_cells(t)) for idx, t in pagina])
        hasta = ini + len(pagina)
        self._tags_count.configure(
            text=(f"{ini + 1}-{hasta} de {len(visibles)}" if visibles else "sin resultados")
                 + (f"  ·  {total} en el pedido" if len(visibles) != total else ""))
        self._lbl_tag_page.configure(text=f"Pág {self._tags_page + 1} / {paginas}")
        self._btn_tag_prev.configure(state="normal" if self._tags_page > 0 else "disabled")
        self._btn_tag_next.configure(
            state="normal" if self._tags_page < paginas - 1 else "disabled")

    def _goto_tags_page(self, page: int) -> None:
        self._tags_page = max(0, page)
        self._populate_tags_table()

    def _open_tag_detail(self, rowid: str) -> None:
        if not rowid or not str(rowid).startswith("tag_"):
            return
        try:
            tag = self._tags_current[int(str(rowid).split("_", 1)[1])]
        except (ValueError, IndexError):
            return
        TagDetailWindow(self, tag, doc_state=self._doc_state,
                        on_open_documento=self._on_open_documento)
