"""Globo con el texto entero de una celda recortada con «…».

Las tablas recortan lo que no cabe; con el ratón encima medio segundo, sale el
texto completo debajo de la celda. Uno por tabla, ligero (tk puro, sin marco).
"""

from __future__ import annotations

import tkinter as tk

from gui import theme

RETARDO_MS = 450


class Globo:
    def __init__(self, dueno):
        self._dueno = dueno
        self._win: tk.Toplevel | None = None
        self._job = None
        self._clave = None

    def pedir(self, clave, texto: str, x: int, y: int) -> None:
        """Mostrar `texto` en (x, y) de pantalla tras el retardo; `clave` evita
        reprogramarlo con cada movimiento del ratón sobre la misma celda."""
        if clave == self._clave:
            return
        self.quitar()
        if not texto:
            return
        self._clave = clave
        try:
            self._job = self._dueno.after(RETARDO_MS, lambda: self._mostrar(texto, x, y))
        except tk.TclError:
            self._job = None

    def _mostrar(self, texto: str, x: int, y: int) -> None:
        self._job = None
        try:
            win = tk.Toplevel(self._dueno)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            marco = tk.Frame(win, bg=theme.BG_CARD, highlightthickness=1,
                             highlightbackground=theme.BORDER_STRONG)
            marco.pack()
            tk.Label(marco, text=texto, bg=theme.BG_CARD, fg=theme.TEXT_MAIN, font=theme.FONT_SMALL,
                     justify="left", wraplength=520, padx=8, pady=4).pack()
            win.update_idletasks()
            # Que no se salga de la pantalla por la derecha ni por abajo
            ancho, alto = win.winfo_reqwidth(), win.winfo_reqheight()
            x = max(0, min(x, win.winfo_screenwidth() - ancho - 8))
            if y + alto > win.winfo_screenheight() - 48:
                y = max(0, y - alto - 40)
            win.geometry(f"+{x}+{y}")
            self._win = win
        except tk.TclError:
            self._win = None

    def quitar(self, _e=None) -> None:
        self._clave = None
        if self._job is not None:
            try:
                self._dueno.after_cancel(self._job)
            except Exception:  # noqa: BLE001
                pass
            self._job = None
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._win = None
