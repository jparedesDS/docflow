"""PillTable — tabla a medida con celdas ricas (pills de color, negrita, texto
de acento, cabecera oscura ordenable). Sustituye a ttk cuando se necesita
formato por celda (que ttk.Treeview no permite).

Dibujada entera sobre un Canvas: cada fila es un rectángulo y cada celda un
texto (y su pastilla, si la lleva). Antes cada celda era un tk.Frame con un
tk.Label dentro —unas 600 ventanas de Windows por página de Documentos— y al
volver a una sección Windows tenía que mapearlas y pintarlas una a una: medio
segundo largo viendo la tabla rellenarse de arriba abajo, más aún por
escritorio remoto. Ahora se pinta de una vez.

Anchos: cada columna tiene su ancho preferido (`min`) y un suelo; la tabla los
reparte según el hueco que haya (gui/widgets/columnas.py): con poco sitio las
columnas encogen y el texto largo se remata con «…» (con el ratón encima se lee
entero), y si ni así caben, aparece el scroll horizontal (la cabecera se mueve
con las filas). Solo encoge por debajo de su contenido el texto libre: las
columnas `stretch` o con `floor` (su suelo puesto a mano); un código, una fecha
o un estado se ven siempre enteros.

Uso:
    cols = [{"key","label","min","stretch","anchor","floor"}, ...]
    t = PillTable(parent, cols, on_double_click=fn, on_sort=fn)
    t.set_rows([("row_0", {"Estado": {"text": "Enviado", "pill": True,
                                       "fg": BLUE, "pill_bg": tint}, ...}), ...])
"""

import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

from gui import theme
from gui.widgets import columnas
from gui.widgets.globo import Globo

_PADX = 8               # sangría del texto de la cabecera
_ALTO_CABECERA = 34
_MARGEN = 12            # lo que no es texto en una celda: sangría y aire
_SANGRIA = 8            # dónde empieza el texto de una celda alineada a la izquierda
_HUECO = 2              # separación entre filas (deja ver el fondo de la tarjeta)
_PILL_PADX = 7          # aire a los lados del texto dentro de una pastilla
_PILL_RADIO = 5


class PillTable(ctk.CTkFrame):
    def __init__(self, master, columns, on_double_click=None, on_select=None,
                 on_sort=None, rowheight=40, multiselect=False, **kwargs):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=12,
                         border_width=1, border_color=theme.BORDER, **kwargs)
        self._columns = columns
        self._on_double_click = on_double_click
        self._on_select = on_select
        self._on_sort = on_sort
        self._rowheight = rowheight
        self._multiselect = multiselect     # ctrl+clic suma · mayús+clic rango
        self._ctx_builder = None
        self._filas: list[dict] = []        # [{rowid, cells, base, rect, items:[{texto,visto,pill}]}]
        self._rowid_pos: dict[str, int] = {}
        self._selected: str | None = None
        self._sel: list[str] = []
        self._hover: int | None = None
        self._anchos = [int(c.get("min", 60)) for c in columns]      # los que tienen ahora
        self._total = sum(self._anchos)
        self._contenido = [0] * len(columns)    # lo que mide lo más largo que han tenido
        self._orden: str | None = None          # columna por la que se ordena (lleva flecha)
        self._orden_asc = True
        self._cabecera: list[tuple[str, str]] = []
        self._ajuste_pendiente = None
        self._ancho_lienzo = 0
        self._globo = Globo(self)               # el texto entero de una celda recortada
        self._fuentes: dict[tuple, tkfont.Font] = {}

        wrap = tk.Frame(self, bg=theme.BG_CARD)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        # Cabecera: su propio lienzo, para desplazarla en horizontal con las filas
        self._hcanvas = tk.Canvas(wrap, bg=theme.TABLE_HEADER_BG, height=_ALTO_CABECERA,
                                  highlightthickness=0, bd=0, xscrollincrement=20)
        self._hcanvas.grid(row=0, column=0, sticky="ew")
        if on_sort:
            self._hcanvas.configure(cursor="hand2")
            self._hcanvas.bind("<Button-1>", self._clic_cabecera)
        self._hcanvas.bind("<Motion>", self._encima_cabecera)
        self._hcanvas.bind("<Leave>", self._globo.quitar)

        # Cuerpo
        self._canvas = tk.Canvas(wrap, bg=theme.BG_CARD, highlightthickness=0, bd=0,
                                 yscrollincrement=20, xscrollincrement=20)
        self._vsb = tk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview)
        self._hsb = tk.Scrollbar(wrap, orient="horizontal", command=self._xview)
        self._canvas.configure(yscrollcommand=self._vsb.set, xscrollcommand=self._on_xscroll)
        self._canvas.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self._vsb.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self._hsb.grid(row=2, column=0, sticky="ew")
        self._hsb.grid_remove()             # solo sale si las columnas no caben

        c = self._canvas
        c.bind("<Configure>", self._on_canvas_configure)
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Shift-MouseWheel>", self._on_wheel_h)
        c.bind("<Button-1>", lambda e: self._clic(e, "set"))
        c.bind("<Double-Button-1>", self._doble)
        c.bind("<Button-3>", self._menu)
        c.bind("<Motion>", self._encima)
        c.bind("<Leave>", self._fuera)
        if multiselect:
            c.bind("<Control-Button-1>", lambda e: self._clic(e, "toggle"))
            c.bind("<Shift-Button-1>", lambda e: self._clic(e, "range"))

    # ── Fuentes y medidas ────────────────────────────────────────────────────

    def _fuente(self, size: int = 11, bold: bool = False) -> tkfont.Font:
        clave = (size, bold)
        f = self._fuentes.get(clave)
        if f is None:
            f = tkfont.Font(font=theme.font(size, "bold") if bold else theme.font(size))
            self._fuentes[clave] = f
        return f

    def _fuente_celda(self, spec: dict) -> tkfont.Font:
        if spec.get("pill"):
            return self._fuente(10, True)
        return self._fuente(11, bool(spec.get("bold")))

    @staticmethod
    def _cortar(texto: str, ancho: int, fuente: tkfont.Font) -> str:
        """El texto que cabe en `ancho`, rematado con «…» si hace falta."""
        if ancho <= 10 or not texto or fuente.measure(texto) <= ancho:
            return texto
        bajo, alto = 0, len(texto)
        while bajo < alto:                        # el corte más largo que entra
            medio = (bajo + alto + 1) // 2
            if fuente.measure(texto[:medio] + "…") <= ancho:
                bajo = medio
            else:
                alto = medio - 1
        return (texto[:bajo].rstrip() + "…") if bajo else "…"

    def _medir_contenido(self, i: int, spec: dict) -> None:
        """Lo que necesita la celda para verse entera (para el suelo de su columna)."""
        texto = str(spec.get("text", "") or "")
        if not texto:
            return
        fuente = self._fuente_celda(spec)
        if spec.get("pill"):
            ancho = fuente.measure(texto) + 2 * _PILL_PADX + 8
        else:
            ancho = fuente.measure(texto) + _MARGEN
        if ancho > self._contenido[i]:
            self._contenido[i] = ancho

    # ── Anchos de columna ────────────────────────────────────────────────────

    def _medidas(self) -> tuple[list[int], list[int]]:
        """(preferidos, suelos) de las columnas, según su cabecera y su contenido."""
        cabecera = self._fuente(10, True)
        preferidos, suelos = [], []
        for i, col in enumerate(self._columns):
            # La flecha de orden solo la lleva una: solo esa necesita su hueco
            flecha = 20 if col["key"] == self._orden else 0
            aire = 10 if col.get("anchor") == "center" else 2 * _PADX
            ancho_cab = cabecera.measure(col["label"].upper()) + aire + flecha
            texto_libre = bool(col.get("stretch")) or "floor" in col
            pref, suelo = columnas.medidas(col.get("min", 60), ancho_cab, self._contenido[i],
                                           col.get("floor"),
                                           columnas.LARGO if texto_libre else columnas.CODIGO)
            preferidos.append(pref)
            suelos.append(suelo)
        return preferidos, suelos

    def _pedir_ajuste(self) -> None:
        """Agrupa los reajustes: al redimensionar llegan decenas de eventos."""
        if self._ajuste_pendiente is not None:
            return
        try:
            self._ajuste_pendiente = self.after_idle(self._ajustar)
        except tk.TclError:          # la ventana se está cerrando
            self._ajuste_pendiente = None

    def _ajustar(self) -> None:
        """Reparte el ancho entre las columnas (ver gui/widgets/columnas.py) y redibuja."""
        self._ajuste_pendiente = None
        try:
            disponible = self._canvas.winfo_width()
        except tk.TclError:
            return
        if disponible <= 1:                  # aún sin pintar: ya llegará el <Configure>
            return
        preferidos, suelos = self._medidas()
        anchos = columnas.repartir(preferidos, suelos, disponible)
        total = sum(anchos)
        if total < disponible:               # lo que sobra, a las que estiran
            elasticas = [i for i, c in enumerate(self._columns) if c.get("stretch")]
            if elasticas:
                extra, resto = divmod(disponible - total, len(elasticas))
                for n, i in enumerate(elasticas):
                    anchos[i] += extra + (1 if n < resto else 0)
        self._anchos = anchos
        self._total = max(disponible, sum(anchos))
        if self._total > disponible:
            self._hsb.grid()
        else:
            self._hsb.grid_remove()
            self._xview("moveto", 0)
        self._dibujar()

    def _x(self) -> list[int]:
        xs, x = [], 0
        for ancho in self._anchos:
            xs.append(x)
            x += ancho
        return xs

    # ── Dibujo ───────────────────────────────────────────────────────────────

    def _dibujar(self) -> None:
        """Redibuja cabecera y filas con los anchos actuales."""
        self._dibujar_cabecera()
        c = self._canvas
        c.delete("all")
        xs = self._x()
        paso = self._rowheight + _HUECO
        for i, fila in enumerate(self._filas):
            y0 = i * paso + _HUECO // 2
            fila["rect"] = c.create_rectangle(0, y0, self._total, y0 + self._rowheight,
                                              fill=self._color_fila(i), width=0)
            ym = y0 + self._rowheight / 2
            fila["items"] = [
                self._dibujar_celda(fila["cells"].get(col["key"]) or {}, xs[ci], self._anchos[ci], ym,
                                    col.get("anchor", "w"))
                for ci, col in enumerate(self._columns)]
        c.configure(scrollregion=(0, 0, self._total, max(len(self._filas) * paso, 1)))

    def _dibujar_celda(self, spec: dict, x: int, ancho: int, ym: float, anchor: str) -> dict:
        c = self._canvas
        texto = str(spec.get("text", "") or "")
        celda = {"texto": texto, "pill": bool(spec.get("pill")), "visto": texto}
        if not texto:
            return celda
        fuente = self._fuente_celda(spec)
        fg = spec.get("fg", theme.TEXT_MAIN)
        if spec.get("pill"):
            w = fuente.measure(texto) + 2 * _PILL_PADX
            h = fuente.metrics("linespace") + 6
            cx = x + ancho / 2 if anchor == "center" else x + _SANGRIA + w / 2
            self._redondeado(cx - w / 2, ym - h / 2, cx + w / 2, ym + h / 2,
                             spec.get("pill_bg", theme.BG_INPUT))
            c.create_text(cx, ym, text=texto, fill=fg, font=fuente, anchor="center")
            return celda
        visto = self._cortar(texto, ancho - _MARGEN, fuente)
        celda["visto"] = visto
        if anchor == "center":
            c.create_text(x + ancho / 2, ym, text=visto, fill=fg, font=fuente, anchor="center")
        else:
            c.create_text(x + _SANGRIA, ym, text=visto, fill=fg, font=fuente, anchor="w")
        return celda

    def _redondeado(self, x0, y0, x1, y1, color) -> int:
        r = _PILL_RADIO
        puntos = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
                  x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self._canvas.create_polygon(puntos, smooth=True, fill=color, outline=color)

    def _dibujar_cabecera(self) -> None:
        h = self._hcanvas
        h.delete("all")
        h.create_rectangle(0, 0, self._total, _ALTO_CABECERA, fill=theme.TABLE_HEADER_BG, width=0)
        fuente = self._fuente(10, True)
        self._cabecera = []
        for col, x, ancho in zip(self._columns, self._x(), self._anchos):
            texto = col["label"].upper()
            if col["key"] == self._orden:
                texto = f"{texto}  {'▲' if self._orden_asc else '▼'}"
            centro = col.get("anchor") == "center"
            visto = self._cortar(texto, ancho - (10 if centro else 2 * _PADX), fuente)
            if centro:
                h.create_text(x + ancho / 2, _ALTO_CABECERA / 2, text=visto,
                              fill=theme.TABLE_HEADER_FG, font=fuente, anchor="center")
            else:
                h.create_text(x + _PADX, _ALTO_CABECERA / 2, text=visto,
                              fill=theme.TABLE_HEADER_FG, font=fuente, anchor="w")
            self._cabecera.append((texto, visto))
        h.configure(scrollregion=(0, 0, self._total, _ALTO_CABECERA))

    def _color_fila(self, i: int) -> str:
        fila = self._filas[i]
        if fila["rowid"] in self._sel:
            return theme.ACCENT_SOFT
        if i == self._hover:
            return theme.ROW_HOVER
        return fila["base"]

    def _pintar(self, i: int) -> None:
        if 0 <= i < len(self._filas) and self._filas[i].get("rect"):
            self._canvas.itemconfigure(self._filas[i]["rect"], fill=self._color_fila(i))

    # ── Scroll ───────────────────────────────────────────────────────────────

    def _on_wheel(self, event) -> str:
        self._globo.quitar()
        try:
            self._canvas.yview_scroll(int(-event.delta / 120) * 3, "units")
        except Exception:  # noqa: BLE001
            pass
        return "break"

    def _on_wheel_h(self, event) -> str:
        if self._hsb.winfo_ismapped():
            self._xview("scroll", int(-event.delta / 120) * 3, "units")
        return "break"

    def _xview(self, *args) -> None:
        self._canvas.xview(*args)
        self._hcanvas.xview(*args)

    def _on_xscroll(self, first, last) -> None:
        self._hsb.set(first, last)
        try:
            self._hcanvas.xview_moveto(first)
        except Exception:  # noqa: BLE001
            pass

    def _on_canvas_configure(self, e) -> None:
        # Sólo si el ancho cambió de verdad (Tk repite <Configure> en una ráfaga)
        if e.width != self._ancho_lienzo:
            self._ancho_lienzo = e.width
            self._pedir_ajuste()

    # ── API ───────────────────────────────────────────────────────────────────

    def set_context_menu(self, builder) -> None:
        self._ctx_builder = builder

    def set_sort_arrow(self, key: str | None, asc: bool) -> None:
        cambia_hueco = key != self._orden
        self._orden, self._orden_asc = key, asc
        if cambia_hueco:
            self._pedir_ajuste()
        else:
            self._dibujar_cabecera()

    def set_rows(self, rows: list) -> None:
        """Pinta las filas (rows = [(rowid, cells)])."""
        self._globo.quitar()
        self._filas = []
        self._rowid_pos = {}
        for i, (rowid, cells) in enumerate(rows):
            self._filas.append({"rowid": rowid, "cells": cells,
                                "base": theme.BG_CARD if i % 2 == 0 else theme.ROW_STRIPE})
            self._rowid_pos[rowid] = i
            for ci, col in enumerate(self._columns):
                self._medir_contenido(ci, cells.get(col["key"]) or {})
        self._selected = None
        self._sel = []
        self._hover = None
        self._canvas.yview_moveto(0)
        if self._canvas.winfo_width() > 1:
            self._ajustar()           # el contenido nuevo puede pedir otro reparto
        else:
            self._pedir_ajuste()

    def clear(self) -> None:
        self.set_rows([])

    def selected_id(self) -> str | None:
        return self._selected

    def selected_ids(self) -> list[str]:
        """Filas seleccionadas, en el orden en que se fueron marcando."""
        return [r for r in self._sel if r in self._rowid_pos]

    def row_values(self, rowid: str) -> list[str]:
        """Textos de las celdas de una fila (enteros, aunque se vean recortados)."""
        pos = self._rowid_pos.get(rowid)
        if pos is None:
            return []
        cells = self._filas[pos]["cells"]
        return [str((cells.get(c["key"]) or {}).get("text", "") or "").strip() for c in self._columns]

    def copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    # ── Interacción ─────────────────────────────────────────────────────────

    def _fila_en(self, event) -> int | None:
        y = self._canvas.canvasy(event.y)
        i = int(y // (self._rowheight + _HUECO))
        return i if 0 <= i < len(self._filas) else None

    def _columna_en(self, x: float) -> int | None:
        for ci, (x0, ancho) in enumerate(zip(self._x(), self._anchos)):
            if x0 <= x < x0 + ancho:
                return ci
        return None

    def _clic(self, event, modo: str) -> str | None:
        self._globo.quitar()
        i = self._fila_en(event)
        if i is not None:
            self.select(self._filas[i]["rowid"], mode=modo)
        return "break" if modo != "set" else None

    def _doble(self, event) -> None:
        i = self._fila_en(event)
        if i is not None and self._on_double_click:
            self._on_double_click(self._filas[i]["rowid"])

    def _menu(self, event) -> None:
        i = self._fila_en(event)
        if i is None:
            return
        rowid = self._filas[i]["rowid"]
        # Clic derecho sobre algo ya seleccionado: respeta la selección
        if rowid not in self._sel:
            self.select(rowid)
        if self._ctx_builder:
            self._show_menu(event, rowid)

    def _encima(self, event) -> None:
        i = self._fila_en(event)
        if i != self._hover:
            anterior, self._hover = self._hover, i
            if anterior is not None:
                self._pintar(anterior)
            if i is not None:
                self._pintar(i)
        # Globo con el texto entero si la celda sale recortada
        ci = self._columna_en(self._canvas.canvasx(event.x))
        if i is None or ci is None:
            self._globo.quitar()
            return
        items = self._filas[i].get("items") or []
        celda = items[ci] if ci < len(items) else None
        if not celda or celda["pill"] or celda["visto"] == celda["texto"]:
            self._globo.quitar()
            return
        self._globo.pedir((i, ci), celda["texto"], event.x_root + 4, event.y_root + 18)

    def _fuera(self, _e=None) -> None:
        self._globo.quitar()
        if self._hover is not None:
            anterior, self._hover = self._hover, None
            self._pintar(anterior)

    def _clic_cabecera(self, event) -> None:
        ci = self._columna_en(self._hcanvas.canvasx(event.x))
        if ci is not None and self._on_sort:
            self._on_sort(self._columns[ci]["key"])

    def _encima_cabecera(self, event) -> None:
        ci = self._columna_en(self._hcanvas.canvasx(event.x))
        if ci is None or ci >= len(self._cabecera) or self._cabecera[ci][0] == self._cabecera[ci][1]:
            self._globo.quitar()
            return
        self._globo.pedir(("h", ci), self._cabecera[ci][0], event.x_root + 4, event.y_root + 18)

    def select(self, rowid: str, mode: str = "set") -> None:
        """Selecciona una fila. `mode`: 'set' · 'toggle' (ctrl) · 'range' (mayús).

        Los dos últimos solo hacen algo con multiselect=True.
        """
        previas = list(self._sel)
        if not self._multiselect or mode == "set":
            self._sel = [rowid]
        elif mode == "toggle":
            self._sel = [r for r in self._sel if r != rowid] if rowid in self._sel \
                else self._sel + [rowid]
        elif mode == "range" and self._sel:
            ini = self._rowid_pos.get(self._sel[-1], 0)
            fin = self._rowid_pos.get(rowid, 0)
            lo, hi = (ini, fin) if ini <= fin else (fin, ini)
            entre = [r for r, pos in self._rowid_pos.items() if lo <= pos <= hi]
            self._sel = self._sel + [r for r in entre if r not in self._sel]
        else:
            self._sel = [rowid]

        self._selected = self._sel[-1] if self._sel else None
        for r in set(previas) | set(self._sel):
            if r in self._rowid_pos:
                self._pintar(self._rowid_pos[r])
        if self._on_select:
            self._on_select(self._selected)

    def _show_menu(self, event, rowid: str) -> None:
        try:
            items = self._ctx_builder(rowid)
        except Exception:
            items = None
        if not items:
            return
        menu = tk.Menu(self, tearoff=0, bg=theme.BG_CARD, fg=theme.TEXT_MAIN,
                       activebackground=theme.ACCENT, activeforeground=theme.TEXT_ON_ACCENT,
                       bd=0, relief="flat")
        for label, cmd in items:
            if label == "-" or cmd is None:
                menu.add_separator()
            else:
                menu.add_command(label=label, command=cmd)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
