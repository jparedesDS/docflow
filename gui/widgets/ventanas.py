"""Que cada ventana del programa salga entera y centrada en el escritorio.

Las ventanas emergentes ponían su tamaño a mano y no decían dónde abrirse, así
que Windows las iba dejando en cascada: las altas acababan con el pie debajo de
la barra de tareas o fuera de la pantalla, y las que tenían más contenido que
tamaño cortaban el texto. `instalar()` hace que cualquier CTkToplevel, al
terminar de construirse, se ajuste a lo que pide su contenido (sin pasarse del
escritorio) y se centre en la pantalla donde está la app.

No se tocan los globos ni los desplegables (ventanas sin marco), que van
pegados al botón que los abre.
"""

from __future__ import annotations

import ctypes
import logging
import re

import customtkinter as ctk

logger = logging.getLogger(__name__)

MARGEN = 12        # aire entre la ventana y el borde del escritorio
MARCO_ALTO = 40    # barra de título + bordes que añade Windows (Tk mide sin ellos)
MARCO_ANCHO = 16

_instalado = False


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.c_long * 4),
                ("rcWork", ctypes.c_long * 4), ("dwFlags", ctypes.c_ulong)]


def area_trabajo(win) -> tuple[int, int, int, int]:
    """(izq, arriba, der, abajo) del escritorio útil —sin la barra de tareas—
    del monitor donde está la ventana principal."""
    try:
        user32 = ctypes.windll.user32
        hwnd = int(win.winfo_toplevel().wm_frame(), 16)
        try:
            principal = win.nametowidget(".")
            hwnd = int(principal.wm_frame(), 16) if principal.winfo_ismapped() else hwnd
        except Exception:  # noqa: BLE001
            pass
        monitor = user32.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)   # MONITOR_DEFAULTTONEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if monitor and user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
            izq, arriba, der, abajo = info.rcWork
            if der > izq and abajo > arriba:
                return izq, arriba, der, abajo
    except Exception:  # noqa: BLE001 — fuera de Windows o sin ventana aún
        pass
    try:                                    # el escritorio del monitor principal
        rect = (ctypes.c_long * 4)()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            izq, arriba, der, abajo = rect
            if der > izq and abajo > arriba:
                return izq, arriba, der, abajo
    except Exception:  # noqa: BLE001
        pass
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()


def encajar_principal(win, ancho: int, alto: int, x: int | None = None, y: int | None = None,
                      geometria=None) -> None:
    """Tamaño y posición de una ventana raíz (login, app): cabe en el escritorio
    y, si no trae posición o la traída se sale, va centrada."""
    izq, arriba, der, abajo = area_trabajo(win)
    ancho = min(ancho, der - izq - MARCO_ANCHO)
    alto = min(alto, abajo - arriba - MARCO_ALTO)
    if (x is None or y is None or x < izq or y < arriba
            or x + ancho + MARCO_ANCHO > der or y + alto + MARCO_ALTO > abajo):
        x = izq + max(0, (der - izq - ancho - MARCO_ANCHO) // 2)
        y = arriba + max(0, (abajo - arriba - alto - MARCO_ALTO) // 2)
    (geometria or win.geometry)(f"{ancho}x{alto}+{x}+{y}")


def encajar(win, repaso: bool = False) -> None:
    """Ajusta una ventana emergente a su contenido y la centra en el escritorio.

    El tamaño es el mayor entre el que puso la ventana y el que pide lo que
    lleva dentro, sin pasar del escritorio. Si la ventana no puso tamaño (se
    adapta sola al contenido), solo se coloca, para no congelarla.
    `repaso`: pasadas de después, que solo corrigen si no está como debe (el
    contenido creció, o Windows la devolvió a su sitio al terminar de pintar
    la barra de título).
    """
    try:
        if not win.winfo_exists() or win.overrideredirect():
            return
        win.update_idletasks()
        escala = win._get_window_scaling() or 1.0
        izq, arriba, der, abajo = area_trabajo(win)
        max_w = der - izq - 2 * MARGEN - MARCO_ANCHO
        max_h = abajo - arriba - 2 * MARGEN - MARCO_ALTO

        # Si su mínimo no cabe en esta pantalla, el mínimo es la pantalla
        min_w, min_h = win._min_width * escala, win._min_height * escala
        if min_w > max_w or min_h > max_h:
            win.minsize(int(min(min_w, max_w) / escala), int(min(min_h, max_h) / escala))

        natural = not getattr(win, "_encaje_tamano", False)
        req_w, req_h = win.winfo_reqwidth(), win.winfo_reqheight()
        if natural:
            w, h = req_w, req_h
        else:
            w = max(round(win._current_width * escala), req_w)
            h = max(round(win._current_height * escala), req_h)
        w, h = min(w, max_w), min(h, max_h)
        x = max(izq, izq + (der - izq - w - MARCO_ANCHO) // 2)
        y = max(arriba, arriba + (abajo - arriba - h - MARCO_ALTO) // 2)

        if repaso and win.state() == "normal" and _geometria(win) == (w, h, x, y):
            return
        if natural and (w, h) == (req_w, req_h):
            win.geometry(f"+{x}+{y}")
        else:
            win.geometry(f"{int(w / escala)}x{int(h / escala)}+{x}+{y}")
        if not repaso and win.state() == "normal":
            win.lift()
    except Exception as exc:  # noqa: BLE001 — colocar una ventana nunca debe romperla
        logger.debug("No se pudo encajar la ventana: %s", exc)


def _geometria(win) -> tuple[int, ...] | None:
    m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", win.wm_geometry())
    return tuple(int(g) for g in m.groups()) if m else None


def instalar() -> None:
    """Engancha `encajar` a todas las CTkToplevel del programa (una vez)."""
    global _instalado
    if _instalado:
        return
    _instalado = True

    init_original = ctk.CTkToplevel.__init__
    geometry_original = ctk.CTkToplevel.geometry

    def __init__(self, *args, **kwargs):
        init_original(self, *args, **kwargs)
        try:
            self.after_idle(lambda: encajar(self))
            # Repasos: CustomTkinter oculta y vuelve a mostrar la ventana al pintar
            # la barra de título (y Windows puede devolverla a la cascada), y hay
            # ventanas que crean sus widgets un instante después (CTkInputDialog).
            for ms in (60, 300):
                self.after(ms, lambda: encajar(self, repaso=True))
        except Exception:  # noqa: BLE001
            pass

    def geometry(self, geometry_string: str | None = None):
        if geometry_string and "x" in geometry_string.split("+")[0].split("-")[0]:
            self._encaje_tamano = True      # la ventana pidió un tamaño: respetarlo como mínimo
        return geometry_original(self, geometry_string)

    ctk.CTkToplevel.__init__ = __init__
    ctk.CTkToplevel.geometry = geometry
