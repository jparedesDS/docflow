"""Casillas — una lista de casillas de verificación dibujada en un solo Canvas.

Para cuando son muchas: cada CTkCheckBox son tres ventanas de Windows (marco,
lienzo y texto) que hay que colocar, mapear y pintar una a una, y por
escritorio remoto se nota. Las 34 subcarpetas de «Nuevo pedido» eran un tercio
de las ventanas de la vista: sin ellas abría en 119 ms en vez de 186 y se
construía en 460 ms en vez de 620. Aquí todas son un lienzo.

Se ve como las de CustomTkinter (cuadro redondeado, marca blanca sobre el
acento) y a la misma escala. Las columnas reparten el ancho que haya; el texto
que no cabe se remata con «…» y con el ratón encima se lee entero. Cada
casilla tiene su BooleanVar: cambiarla por código también la repinta.

Uso:
    c = Casillas(padre, [("clave", "Texto"), ...], columnas=3)
    c.vars["clave"].get()      ·  c.marcar_todas(False)  ·  c.marcadas()
    c.poner_texto("clave", "Otro texto")  ·  c.texto("clave")
"""
from __future__ import annotations

import tkinter as tk

from gui import theme
from gui.widgets import texto
from gui.widgets.globo import Globo
from gui.widgets.ui import fondo_de

_CUADRO = 18          # lado del cuadro, a escala 100 %
_ALTO = 26            # alto de cada fila: el cuadro y 4 px de aire
_SEPARACION = 8       # entre el cuadro y su texto
_COLUMNA_AIRE = 12    # entre columnas


class Casillas(tk.Canvas):
    def __init__(self, master, items: list[tuple[str, str]], columnas: int = 3,
                 marcadas: bool = True, fuente=None, command=None):
        super().__init__(master, bg=fondo_de(master), highlightthickness=0, bd=0)
        self._escala = texto.escala_de(self)
        self._fuente = texto.fuente_ctk(fuente or theme.FONT_BODY, self)
        self._columnas = max(1, columnas)
        self._command = command
        self._claves = [k for k, _ in items]
        self._indice = {k: i for i, k in enumerate(self._claves)}
        self._textos = dict(items)
        self._vistos: dict[str, str] = {}       # lo que se ve de cada texto (recortado o no)
        self.vars: dict[str, tk.BooleanVar] = {}
        for clave in self._claves:
            var = tk.BooleanVar(master=self, value=marcadas)
            var.trace_add("write", lambda *_a, k=clave: self._pintar(k))
            self.vars[clave] = var
        self._encima: str | None = None
        self._ancho_col = 0
        self._globo = Globo(self)

        filas = -(-len(self._claves) // self._columnas)
        # Ancho pedido pequeño: el texto largo se recorta, no ensancha la tarjeta
        self.configure(height=filas * self._px(_ALTO), width=self._px(120) * self._columnas)
        self.bind("<Configure>", self._recolocar)
        self.bind("<Button-1>", self._clic)
        self.bind("<Motion>", self._mover)
        self.bind("<Leave>", self._fuera)

    # ── API ──────────────────────────────────────────────────────────────────

    def texto(self, clave: str) -> str:
        return self._textos[clave]

    def poner_texto(self, clave: str, texto: str) -> None:
        self._textos[clave] = texto
        self._pintar(clave)

    def marcar_todas(self, valor: bool) -> None:
        for var in self.vars.values():
            var.set(valor)

    def marcadas(self) -> list[str]:
        return [k for k in self._claves if self.vars[k].get()]

    def etiqueta(self, clave: str) -> str:
        """La etiqueta de sus dibujos en el lienzo (las claves pueden llevar
        espacios, y en Tk una etiqueta no)."""
        return f"casilla{self._indice[clave]}"

    # ── Medidas ──────────────────────────────────────────────────────────────

    def _px(self, n: float) -> int:
        return round(n * self._escala)

    def _hueco_texto(self) -> int:
        """Lo que le queda al texto en una columna, tras el cuadro y el aire."""
        return self._ancho_col - self._px(_CUADRO + _SEPARACION + _COLUMNA_AIRE)

    def _celda(self, i: int) -> tuple[int, int]:
        fila, col = divmod(i, self._columnas)
        return col * self._ancho_col, fila * self._px(_ALTO)

    def _en(self, x: int, y: int) -> str | None:
        """La casilla bajo el ratón: su cuadro o lo que se ve de su texto, no el
        hueco que queda detrás hasta la columna siguiente."""
        if self._ancho_col <= 0 or x < 0 or y < 0:
            return None
        col, fila = int(x // self._ancho_col), int(y // self._px(_ALTO))
        i = fila * self._columnas + col
        if col >= self._columnas or not 0 <= i < len(self._claves):
            return None
        clave = self._claves[i]
        x0, _ = self._celda(i)
        visto = self._vistos.get(clave, self._textos[clave])
        if x - x0 > self._px(_CUADRO + _SEPARACION) + self._fuente.measure(visto):
            return None
        return clave

    def _cortar(self, cadena: str) -> str:
        return texto.cortar(cadena, self._hueco_texto(), self._fuente)

    # ── Dibujo ───────────────────────────────────────────────────────────────

    def _recolocar(self, e) -> None:
        ancho = max(1, e.width) // self._columnas
        if ancho != self._ancho_col:
            self._ancho_col = ancho
            for clave in self._claves:
                self._pintar(clave)

    def _pintar(self, clave: str) -> None:
        if self._ancho_col <= 0:
            return                       # aún sin tamaño: se pinta al colocarse
        i = self._indice[clave]
        etiqueta = self.etiqueta(clave)
        self.delete(etiqueta)
        x0, y0 = self._celda(i)
        lado = self._px(_CUADRO)
        y = y0 + (self._px(_ALTO) - lado) // 2
        g = max(2, self._px(2))
        encima = clave == self._encima
        if self.vars[clave].get():
            color = theme.ACCENT_HOVER if encima else theme.ACCENT
            rect_redondo(self, x0, y, x0 + lado, y + lado, self._px(4),
                          fill=color, outline=color, tags=etiqueta)
            self.create_line(x0 + lado * 0.25, y + lado * 0.52, x0 + lado * 0.43, y + lado * 0.70,
                             x0 + lado * 0.76, y + lado * 0.32, fill=theme.TEXT_ON_ACCENT,
                             width=g, capstyle="round", joinstyle="round", tags=etiqueta)
        else:
            borde = theme.ACCENT if encima else theme.BORDER_STRONG
            rect_redondo(self, x0 + g / 2, y + g / 2, x0 + lado - g / 2, y + lado - g / 2,
                          self._px(4), fill="", outline=borde, width=g, tags=etiqueta)
        visto = self._cortar(self._textos[clave])
        self._vistos[clave] = visto
        self.create_text(x0 + lado + self._px(_SEPARACION), y0 + self._px(_ALTO) / 2,
                         text=visto, anchor="w", font=self._fuente,
                         fill=theme.TEXT_MAIN, tags=etiqueta)

    def _resaltar(self, clave: str | None) -> None:
        if clave == self._encima:
            return
        antes, self._encima = self._encima, clave
        for k in (antes, clave):
            if k is not None:
                self._pintar(k)

    # ── Ratón ────────────────────────────────────────────────────────────────

    def _mover(self, e) -> None:
        clave = self._en(e.x, e.y)
        self._resaltar(clave)
        self.configure(cursor="hand2" if clave else "")
        if clave is not None and self._vistos.get(clave) != self._textos[clave]:
            self._globo.pedir(clave, self._textos[clave], e.x_root + 4, e.y_root + 18)
        else:
            self._globo.quitar()

    def _fuera(self, _e=None) -> None:
        self._globo.quitar()
        self._resaltar(None)

    def _clic(self, e) -> None:
        clave = self._en(e.x, e.y)
        if clave is None:
            return
        var = self.vars[clave]
        var.set(not var.get())
        if self._command:
            self._command(clave)


def rect_redondo(c: tk.Canvas, x0, y0, x1, y1, r, **kw):
    """Rectángulo de esquinas redondeadas como un polígono suavizado."""
    puntos = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
              x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(puntos, smooth=True, **kw)
