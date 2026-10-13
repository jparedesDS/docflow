# -*- coding: utf-8 -*-
"""Elegir destinatarios de un clic, de la gente registrada en Organización.

Los campos «Para» y «Copia» de las devoluciones y de las reclamaciones son
texto libre separado por comas, y escribir a mano «carlos-crespohor@eipsa.es»
es lento y se presta a erratas. Al lado de cada campo va un botón 👥 que abre
esta lista con el equipo (`organizacion.equipo`, que se rellena en
**Ajustes ▸ Organización**): un clic en una persona la añade al campo, otro la
quita, y el campo se ve cambiar al momento.

No valida ni reescribe lo que ya hubiera en el campo —puede venir del ERP o de
la matriz de comunicación, y a veces como «Ana Calvo <ana-calvo@eipsa.es>»—:
solo reconoce por el correo si esa persona ya está, para no duplicarla.
"""

from __future__ import annotations

import re
import unicodedata

import customtkinter as ctk

from gui import theme
from gui.widgets import ui

_EMAIL_RE = re.compile(r"[^\s<>,;]+@[^\s<>,;]+")


def _fold(s) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if not unicodedata.combining(c))
    return s.lower().strip()


def _trozos(texto) -> list[str]:
    """Los destinatarios del campo, tal como están escritos."""
    return [t.strip() for t in str(texto or "").replace(";", ",").split(",") if t.strip()]


def _correo_de(trozo: str) -> str:
    """El correo de «Ana Calvo <ana@x.es>» y el de «ana@x.es» dan lo mismo."""
    m = _EMAIL_RE.search(trozo or "")
    return (m.group(0) if m else trozo).strip().lower()


# Los campos de destinatarios son unas veces una línea (`CTkEntry`, en
# devoluciones y reclamaciones) y otras un cuadro de varias (`CTkTextbox`, en la
# Communication Matrix del pedido nuevo), y se leen y escriben distinto.

def _leer(campo) -> str:
    if isinstance(campo, ctk.CTkTextbox):
        return campo.get("1.0", "end")
    return campo.get()


def _escribir(campo, texto: str) -> None:
    if isinstance(campo, ctk.CTkTextbox):
        campo.delete("1.0", "end")
        campo.insert("1.0", texto)
    else:
        campo.delete(0, "end")
        campo.insert(0, texto)


def contactos() -> list[dict]:
    """[{ini, nombre, email}] del equipo, por nombre. Sin correo no entra."""
    from core import organizacion

    salida = []
    for ini, datos in (organizacion.equipo or {}).items():
        correos = datos.get("emails") or []
        if correos:
            salida.append({"ini": ini, "nombre": datos.get("nombre") or ini,
                           "email": correos[0]})
    return sorted(salida, key=lambda c: _fold(c["nombre"]))


class SelectorContactos(ctk.CTkToplevel):
    """La lista desplegable, colgada del botón que la abre."""

    W, H = 330, 380

    def __init__(self, boton, entry, titulo: str = "Contactos"):
        super().__init__(boton.winfo_toplevel(), fg_color=theme.BG_CARD)
        self.entry = entry
        self._gente = contactos()
        self._filas: list[dict] = []

        self.title(titulo)
        self.transient(boton.winfo_toplevel())
        self.resizable(False, False)
        self.overrideredirect(True)        # cuelga del botón, como un desplegable
        self._build(titulo)
        self._colocar(boton)
        self._pintar("")

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(60, self._foco)
        try:
            self.grab_set()
        except Exception:  # noqa: BLE001 — sin grab también se usa
            pass

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build(self, titulo: str) -> None:
        marco = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_MD,
                             border_width=1, border_color=theme.BORDER)
        marco.pack(fill="both", expand=True)

        cab = ctk.CTkFrame(marco, fg_color="transparent")
        cab.pack(fill="x", padx=theme.SPACE_3, pady=(theme.SPACE_3, 0))
        ctk.CTkLabel(cab, text=titulo, font=theme.FONT_SECTION,
                     text_color=theme.TEXT_MUTED).pack(side="left")
        ui.icon_button(cab, "✕", command=self.destroy).pack(side="right")

        self.busca = ctk.CTkEntry(
            marco, placeholder_text="Buscar por nombre, iniciales o correo…",
            height=32, corner_radius=theme.RADIUS_MD, font=theme.FONT_BODY,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER, text_color=theme.TEXT_MAIN,
        )
        self.busca.pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_2)
        self.busca.bind("<KeyRelease>", lambda _e: self._pintar(self.busca.get()))
        self.busca.bind("<Return>", lambda _e: self._primero())

        self.lista = ctk.CTkScrollableFrame(marco, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=theme.SPACE_2)

        pie = ctk.CTkFrame(marco, fg_color="transparent")
        pie.pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_2)
        ui.button(pie, "Todo el equipo", "chip", command=self._todos).pack(side="left")
        ui.button(pie, "Limpiar", "chip", command=self._limpiar).pack(side="left",
                                                                     padx=(theme.SPACE_2, 0))
        ui.button(pie, "Listo", "secondary", command=self.destroy).pack(side="right")
        ctk.CTkLabel(marco, text="clic añade o quita  ·  Esc cierra",
                     font=theme.FONT_TINY, text_color=theme.TEXT_MUTED).pack(
            pady=(0, theme.SPACE_2))

    def _colocar(self, boton) -> None:
        """Debajo del botón, y si no cabe, encima o pegado al borde."""
        try:
            x, y = boton.winfo_rootx(), boton.winfo_rooty() + boton.winfo_height() + 4
            ancho, alto = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(0, min(x, ancho - self.W))
            if y + self.H > alto:
                y = max(0, boton.winfo_rooty() - self.H - 4)
        except Exception:  # noqa: BLE001
            x, y = 300, 200
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _foco(self) -> None:
        try:
            self.lift()
            self.busca.focus_set()
        except Exception:  # noqa: BLE001
            pass

    # ── Lista ────────────────────────────────────────────────────────────────

    def _coinciden(self, texto: str) -> list[dict]:
        q = _fold(texto)
        if not q:
            return self._gente
        return [c for c in self._gente
                if q in _fold(c["nombre"]) or q in _fold(c["ini"]) or q in _fold(c["email"])]

    def _pintar(self, texto: str) -> None:
        for w in self.lista.winfo_children():     # también el estado vacío
            w.destroy()
        self._filas = []
        gente = self._coinciden(texto)
        if not gente:
            ui.empty_state(self.lista,
                           "Nadie con ese nombre" if texto
                           else "Nadie registrado: Ajustes ▸ Organización",
                           compact=True, pady=theme.SPACE_4)
            return
        for c in gente:
            self._filas.append(self._fila(c))
        self._marcar()

    def _fila(self, c: dict) -> dict:
        frame = ctk.CTkFrame(self.lista, fg_color="transparent", corner_radius=theme.RADIUS_SM)
        frame.pack(fill="x", pady=1)
        tick = ctk.CTkLabel(frame, text="", width=16, font=theme.FONT_BODY,
                            text_color=theme.GREEN)
        tick.pack(side="left")
        ctk.CTkLabel(frame, text=c["ini"], width=38, font=theme.FONT_TINY_BOLD,
                     text_color=ui.avatar_color(c["ini"])).pack(side="left")
        textos = ctk.CTkFrame(frame, fg_color="transparent")
        textos.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(textos, text=c["nombre"], font=theme.FONT_BODY,
                     text_color=theme.TEXT_MAIN, anchor="w").pack(fill="x")
        ctk.CTkLabel(textos, text=c["email"], font=theme.FONT_TINY,
                     text_color=theme.TEXT_MUTED, anchor="w").pack(fill="x")

        for w in (frame, tick, textos, *textos.winfo_children(), *frame.winfo_children()):
            w.bind("<Button-1>", lambda _e, email=c["email"]: self._alternar(email))
        return {"frame": frame, "tick": tick, "email": c["email"]}

    def _marcar(self) -> None:
        puestos = {_correo_de(t) for t in _trozos(_leer(self.entry))}
        for fila in self._filas:
            fila["tick"].configure(text="✓" if fila["email"].lower() in puestos else "")

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _poner(self, destinatarios: list[str]) -> None:
        _escribir(self.entry, ", ".join(destinatarios))
        self._marcar()

    def _alternar(self, email: str) -> None:
        trozos = _trozos(_leer(self.entry))
        quedan = [t for t in trozos if _correo_de(t) != email.lower()]
        if len(quedan) == len(trozos):
            quedan.append(email)
        self._poner(quedan)

    def _todos(self) -> None:
        trozos = _trozos(_leer(self.entry))
        puestos = {_correo_de(t) for t in trozos}
        trozos += [c["email"] for c in self._gente if c["email"].lower() not in puestos]
        self._poner(trozos)

    def _limpiar(self) -> None:
        self._poner([])

    def _primero(self) -> None:
        if self._filas:
            self._alternar(self._filas[0]["email"])


def boton_contactos(parent, entry, titulo: str = "Contactos",
                    **overrides) -> ctk.CTkButton:
    """Botón 👥 que abre el selector sobre `entry`.

    Se abre y se cierra con el mismo botón. Si no hay nadie registrado el botón
    sale apagado, con la pista de dónde se rellena.
    """
    estado = {"abierto": None}

    def abrir() -> None:
        actual = estado["abierto"]
        if actual is not None and actual.winfo_exists():
            actual.destroy()
            estado["abierto"] = None
            return
        estado["abierto"] = SelectorContactos(boton, entry, titulo)

    boton = ui.icon_button(parent, "👥", command=abrir, **overrides)
    if contactos():
        ui.tooltip(boton, f"Elegir {titulo.lower()} de la gente registrada en Organización")
    else:
        boton.configure(state="disabled")
        ui.tooltip(boton, "No hay nadie registrado todavía: se rellena en Ajustes ▸ Organización")
    return boton
