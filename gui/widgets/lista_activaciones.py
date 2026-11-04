"""Las activaciones pendientes de «Nuevo pedido», dibujadas en un solo Canvas.

Cada fila es una activación de Comercial: arriba el pedido y el cliente, con
quién y cuándo la mandó a la derecha; debajo la PO, la entrega y qué
documentación pide. Pulsar una fila la elige (y rellena el formulario). Un
lienzo y no un marco por fila: por escritorio remoto cada ventana se paga.

Uso:
    lista = ListaActivaciones(padre, al_elegir=lambda tarea: …)
    lista.poner(tareas)  ·  lista.elegir(id_tarea)
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime

from gui import theme
from gui.widgets import texto
from gui.widgets.casillas import rect_redondo
from gui.widgets.globo import Globo
from gui.widgets.ui import fondo_de

_ALTO = 46            # alto de una fila, a escala 100 %
_AIRE_X = 10
_HUECO = 4            # entre filas


def _fecha_es(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d-%m-%Y")
    except (TypeError, ValueError):
        return ""


def lineas_de(t: dict) -> tuple[str, str, str]:
    """(título, a la derecha, detalle) de la fila de una tarea de activación."""
    act = t.get("activacion") or {}
    pedido = t.get("pedido", "") + (f"-{t['supp']}" if t.get("supp") else "")
    titulo = pedido + (f"  ·  {t['cliente']}" if t.get("cliente") else "")
    if act.get("proyecto"):
        titulo += f" / {act['proyecto']}"
    derecha = " · ".join(x for x in (t.get("remitente", ""), t.get("fecha_limite", "")) if x)
    detalle = []
    if act.get("po"):
        detalle.append(f"PO {act['po']}")
    if act.get("entrega"):
        detalle.append(f"entrega {_fecha_es(act['entrega'])}"
                       + (f" ({act['plazo']})" if act.get("plazo") else ""))
    if act.get("documentacion"):
        detalle.append(f"Doc.: {act['documentacion']}")
    notas = t.get("notas") or []
    if notas:
        detalle.append(notas[0] + (f" (+{len(notas) - 1})" if len(notas) > 1 else ""))
    return titulo, derecha, "  ·  ".join(detalle)


class ListaActivaciones(tk.Canvas):
    def __init__(self, master, al_elegir=None):
        super().__init__(master, bg=fondo_de(master), highlightthickness=0, bd=0, height=1)
        self._escala = texto.escala_de(self)
        self._f_titulo = texto.fuente_ctk(theme.FONT_BODY_BOLD, self)
        self._f_detalle = texto.fuente_ctk(theme.FONT_SMALL, self)
        self._al_elegir = al_elegir
        self._tareas: list[dict] = []
        self._elegida: str | None = None
        self._encima: int | None = None
        self._ancho = 0
        self._globo = Globo(self)
        self.bind("<Configure>", self._recolocar)
        self.bind("<Button-1>", self._clic)
        self.bind("<Motion>", self._mover)
        self.bind("<Leave>", self._fuera)

    # ── API ──────────────────────────────────────────────────────────────────

    def poner(self, tareas: list[dict]) -> None:
        self._tareas = list(tareas)
        if self._elegida not in {t.get("id") for t in self._tareas}:
            self._elegida = None
        self._encima = None
        n = len(self._tareas)
        self.configure(height=max(1, n * self._px(_ALTO + _HUECO) - self._px(_HUECO)))
        self._pintar()

    def elegir(self, tarea_id: str | None) -> None:
        self._elegida = tarea_id
        self._pintar()

    @property
    def tareas(self) -> list[dict]:
        return list(self._tareas)

    # ── Dibujo ───────────────────────────────────────────────────────────────

    def _px(self, n: float) -> int:
        return round(n * self._escala)

    def _recolocar(self, e) -> None:
        if e.width != self._ancho:
            self._ancho = e.width
            self._pintar()

    def _pintar(self) -> None:
        self.delete("all")
        if self._ancho <= 1:
            return
        alto, hueco, aire = self._px(_ALTO), self._px(_HUECO), self._px(_AIRE_X)
        for i, t in enumerate(self._tareas):
            y0 = i * (alto + hueco)
            elegida = t.get("id") == self._elegida
            fondo = theme.ACCENT_SOFT if elegida else (theme.ROW_HOVER if i == self._encima else theme.BG_INPUT)
            borde = theme.ACCENT if elegida else theme.BORDER
            rect_redondo(self, 1, y0 + 1, self._ancho - 1, y0 + alto - 1, self._px(theme.RADIUS_SM),
                         fill=fondo, outline=borde)
            titulo, derecha, detalle = lineas_de(t)
            ancho_der = self._f_detalle.measure(derecha) if derecha else 0
            libre = self._ancho - 2 * aire
            self.create_text(self._ancho - aire, y0 + alto * 0.3, text=derecha, anchor="e",
                             font=self._f_detalle, fill=theme.TEXT_MUTED)
            self.create_text(aire, y0 + alto * 0.3, anchor="w", font=self._f_titulo, fill=theme.TEXT_MAIN,
                             text=texto.cortar(titulo, libre - ancho_der - aire, self._f_titulo))
            self.create_text(aire, y0 + alto * 0.7, anchor="w", font=self._f_detalle, fill=theme.TEXT_SUB,
                             text=texto.cortar(detalle, libre, self._f_detalle))

    # ── Ratón ────────────────────────────────────────────────────────────────

    def _en(self, y: int) -> int | None:
        paso = self._px(_ALTO + _HUECO)
        i = int(y // paso) if y >= 0 else -1
        if 0 <= i < len(self._tareas) and y - i * paso <= self._px(_ALTO):
            return i
        return None

    def _mover(self, e) -> None:
        i = self._en(e.y)
        if i != self._encima:
            self._encima = i
            self._pintar()
        self.configure(cursor="hand2" if i is not None else "")
        if i is None:
            self._globo.quitar()
            return
        t = self._tareas[i]
        entero = "\n".join(x for x in (t.get("titulo", ""), *(t.get("notas") or [])) if x)
        self._globo.pedir(t.get("id"), entero, e.x_root + 4, e.y_root + 18)

    def _fuera(self, _e=None) -> None:
        self._globo.quitar()
        if self._encima is not None:
            self._encima = None
            self._pintar()

    def _clic(self, e) -> None:
        i = self._en(e.y)
        if i is None:
            return
        self._elegida = self._tareas[i].get("id")
        self._pintar()
        if self._al_elegir:
            self._al_elegir(self._tareas[i])
