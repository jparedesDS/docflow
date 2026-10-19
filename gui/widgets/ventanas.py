"""Que cada ventana del programa salga entera y centrada en el escritorio.

Las ventanas emergentes ponían su tamaño a mano y no decían dónde abrirse, así
que Windows las iba dejando en cascada: las altas acababan con el pie debajo de
la barra de tareas o fuera de la pantalla, y las que tenían más contenido que
tamaño cortaban el texto. `instalar()` hace que cualquier CTkToplevel, al
terminar de construirse, se ajuste a lo que pide su contenido (sin pasarse del
escritorio) y se centre en la pantalla donde está la app.

Y que aparezcan sin saltos: CustomTkinter enseñaba la ventana, la ocultaba y la
volvía a enseñar para pintar la barra de título oscura, y luego se movía a su
sitio; se veía parpadear y saltar. Ahora nace oculta, se le pone la barra
oscura sin enseñarla, se coloca y aparece ya en su sitio con un fundido corto.
`suave()` hace lo mismo con la ventana principal, y `transicion()` cambia lo
que lleva dentro un trozo de ventana (el cambio de sección) con un fundido
cruzado: se ve el antes, que se desvanece sobre el después ya pintado, y nada a
medio montar entre medias.

No se recolocan los globos ni los desplegables (ventanas sin marco), que van
pegados al botón que los abre: solo aparecen con el fundido.
"""

from __future__ import annotations

import ctypes
import logging
import re
import tkinter
from contextlib import contextmanager

import customtkinter as ctk

logger = logging.getLogger(__name__)

MARGEN = 12        # aire entre la ventana y el borde del escritorio
MARCO_ALTO = 40    # barra de título + bordes que añade Windows (Tk mide sin ellos)
MARCO_ANCHO = 16

FUNDIDO = (0.35, 0.62, 0.82, 0.94, 1.0)   # opacidad en cada paso de ~16 ms
DESVANECER = (0.86, 0.68, 0.48, 0.3, 0.15, 0.05)   # la foto de lo de antes, al irse

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


# ── Aparecer sin saltos ─────────────────────────────────────────────────────

def barra_oscura(win) -> None:
    """Barra de título oscura (Windows 10/11) si la app va en modo oscuro."""
    try:
        if ctk.get_appearance_mode().lower() != "dark":
            return
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        valor = ctypes.c_int(1)
        for atributo in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE (y el de antes de 20H1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor)) == 0:
                return
    except Exception:  # noqa: BLE001 — fuera de Windows o sin DWM
        pass


def fundido(win, paso: int = 0) -> None:
    """Sube la opacidad de 0 a 1 en unos 80 ms."""
    try:
        if not win.winfo_exists():
            return
        win.attributes("-alpha", FUNDIDO[paso])
        if paso + 1 < len(FUNDIDO):
            win.after(16, lambda: fundido(win, paso + 1))
    except Exception:  # noqa: BLE001 — si no admite transparencia, que se vea sin más
        try:
            win.attributes("-alpha", 1.0)
        except Exception:  # noqa: BLE001
            pass


def suave(win) -> None:
    """Ventana principal: que aparezca con un fundido en vez de pintarse a trozos.

    Se llama al crearla (la deja transparente); el fundido arranca cuando el
    bucle de Tk ya ha pintado lo primero que se ve."""
    try:
        win.attributes("-alpha", 0.0)
        # after_idle: cuando arranque el bucle, tras el pintado que ya está en cola
        win.after_idle(lambda: win.after(30, lambda: fundido(win)))
    except Exception:  # noqa: BLE001
        pass


def _presentar(win) -> None:
    """Coloca la ventana (aún oculta) y la enseña con el fundido."""
    try:
        if not win.winfo_exists():
            return
        if not win.overrideredirect():
            encajar(win)
    except Exception as exc:  # noqa: BLE001
        logger.debug("No se pudo colocar la ventana: %s", exc)
    try:
        if not win.winfo_exists():
            return
        if getattr(win, "_oculta_por_codigo", False):     # la ocultó quien la creó: así se queda
            win.attributes("-alpha", 1.0)
            return
        tkinter.Toplevel.deiconify(win)
        if not win.overrideredirect():
            win.lift()
        fundido(win)
    except Exception:  # noqa: BLE001 — una ventana invisible con grab bloquearía la app
        try:
            win.attributes("-alpha", 1.0)
            tkinter.Toplevel.deiconify(win)
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def sin_parpadeo(widget):
    """Congela el pintado de `widget` (y lo que lleva dentro) mientras dura el
    bloque, y lo repinta todo de una vez al salir: sin pasos intermedios."""
    hwnd = 0
    try:
        hwnd = widget.winfo_id()
        ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 0, 0)          # WM_SETREDRAW = FALSE
    except Exception:  # noqa: BLE001 — fuera de Windows: sin congelar
        hwnd = 0
    try:
        yield
    finally:
        if hwnd:
            try:
                user32 = ctypes.windll.user32
                user32.SendMessageW(hwnd, 0x000B, 1, 0)                 # WM_SETREDRAW = TRUE
                # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME
                user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100 | 0x0400)
                # update() y no update_idletasks(): el repintado llega como
                # eventos de ventana, que update_idletasks no atiende
                widget.update()
            except Exception:  # noqa: BLE001
                pass


def transicion(ventana, zona, cambiar) -> None:
    """Ejecuta `cambiar()` (lo que cambia dentro de `zona`) con un fundido cruzado.

    Se hace una foto de lo que se ve en la zona, se pone encima en una capa sin
    marco, se cambia y se pinta todo debajo, y la foto se desvanece en ~100 ms.
    Así no se ve nunca la sección a medio pintar, ni el fondo vacío, ni un trozo
    de la anterior. Si algo falla (o la ventana aún no se ve) se cambia con el
    pintado congelado, que es casi igual de limpio pero sin fundido.
    """
    capa = None
    try:
        if ventana.winfo_viewable() and float(ventana.attributes("-alpha")) >= 0.99:
            from PIL import ImageGrab, ImageTk

            x, y = zona.winfo_rootx(), zona.winfo_rooty()
            w, h = zona.winfo_width(), zona.winfo_height()
            if w > 1 and h > 1:
                try:
                    # De la propia ventana: 2 ms, frente a ~65 ms de copiar la
                    # pantalla por escritorio remoto, y sale bien aunque algo la tape
                    imagen = ImageGrab.grab(window=zona.winfo_id())
                    if imagen.size != (w, h):
                        raise ValueError(imagen.size)
                except Exception:  # noqa: BLE001 — Pillow antiguo: de la pantalla
                    imagen = ImageGrab.grab((x, y, x + w, y + h), all_screens=True)
                foto = ImageTk.PhotoImage(imagen)
                capa = tkinter.Toplevel(ventana)
                capa.withdraw()
                capa.overrideredirect(True)
                capa.geometry(f"{w}x{h}+{x}+{y}")
                tkinter.Label(capa, image=foto, bd=0, highlightthickness=0).pack()
                capa._foto = foto               # que Python no la libere mientras se ve
                capa.deiconify()
                capa.lift(ventana)
                capa.update_idletasks()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Transición sin fundido: %s", exc)
        if capa is not None:
            try:
                capa.destroy()
            except Exception:  # noqa: BLE001
                pass
        capa = None

    if capa is None:
        with sin_parpadeo(ventana):
            cambiar()
            ventana.update_idletasks()
        return
    try:
        cambiar()
        ventana.update()                         # lo nuevo, pintado entero bajo la foto
    finally:
        _desvanecer(capa)


def _desvanecer(capa, paso: int = 0) -> None:
    try:
        if paso >= len(DESVANECER):
            capa.destroy()
            return
        capa.attributes("-alpha", DESVANECER[paso])
        capa.after(16, lambda: _desvanecer(capa, paso + 1))
    except Exception:  # noqa: BLE001
        try:
            capa.destroy()
        except Exception:  # noqa: BLE001
            pass


def instalar() -> None:
    """Engancha a todas las CTkToplevel del programa (una vez): nacen ocultas,
    se colocan y aparecen con un fundido."""
    global _instalado
    if _instalado:
        return
    _instalado = True

    # El baile de CustomTkinter para la barra oscura (ocultar, pintar, enseñar)
    # es lo que se veía parpadear; la barra se pone aquí sin enseñar la ventana.
    ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True

    init_original = ctk.CTkToplevel.__init__
    geometry_original = ctk.CTkToplevel.geometry
    withdraw_original = ctk.CTkToplevel.withdraw

    def __init__(self, *args, **kwargs):
        init_original(self, *args, **kwargs)
        try:
            tkinter.Toplevel.withdraw(self)     # nada se ve hasta estar en su sitio
            self.attributes("-alpha", 0.0)
            self.update_idletasks()             # crea la ventana de Windows, sin enseñarla
            barra_oscura(self)
            # Un instante para que termine de construirse (CTkInputDialog crea sus
            # widgets a los 10 ms) y se enseña ya colocada.
            self.after(20, lambda: _presentar(self))
            # Repaso: hay ventanas que cargan contenido al abrir y crecen.
            self.after(300, lambda: encajar(self, repaso=True))
        except Exception:  # noqa: BLE001
            try:
                self.attributes("-alpha", 1.0)
                tkinter.Toplevel.deiconify(self)
            except Exception:  # noqa: BLE001
                pass

    def geometry(self, geometry_string: str | None = None):
        if geometry_string and "x" in geometry_string.split("+")[0].split("-")[0]:
            self._encaje_tamano = True      # la ventana pidió un tamaño: respetarlo como mínimo
        return geometry_original(self, geometry_string)

    def withdraw(self):
        self._oculta_por_codigo = True      # la oculta quien la usa: no enseñarla por él
        return withdraw_original(self)

    def deiconify(self):
        self._oculta_por_codigo = False
        return tkinter.Toplevel.deiconify(self)

    ctk.CTkToplevel.__init__ = __init__
    ctk.CTkToplevel.geometry = geometry
    ctk.CTkToplevel.withdraw = withdraw
    ctk.CTkToplevel.deiconify = deiconify
