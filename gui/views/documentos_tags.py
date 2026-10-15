"""Ficha de un tag en la sección Documentos: en qué documentos aparece.

Se enseña bajo el buscador solo cuando lo escrito es un tag del ERP. La
búsqueda va en segundo plano (`tags_documentos.donde_esta`) y los resultados
salen según se encuentran, porque leer los PDF de un pedido grande la primera
vez lleva su rato. Si se escribe otra cosa entretanto, la búsqueda anterior se
abandona.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path

import customtkinter as ctk

from core.services import tags_documentos
from gui import theme
from gui.widgets import ui

logger = logging.getLogger(__name__)

MAX_ALTO = 230          # px de la lista de resultados antes de hacer scroll


class _Cancelado(Exception):
    """La búsqueda ya no es la que se está mirando."""


def tag_legible(tag: str) -> str:
    """«1234-FE    -0567» → «1234-FE-0567»; «ABFE   0110» → «ABFE 0110»."""
    return re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", str(tag or "").strip()))


def ruta_corta(fichero: Path) -> str:
    """La ruta desde «2-Tecnico», que es lo que distingue dos PDF que se llaman igual."""
    partes = fichero.parts
    for i, p in enumerate(partes):
        if p.lower() == "2-tecnico":
            return "\\".join(partes[i + 1:])
    return "\\".join(partes[-3:])


class FichaTag(ctk.CTkFrame):
    """Panel con la ficha del tag y dónde aparece.

    `colocar(visible)`: lo muestra u oculta en la vista.
    `on_docs(lista | None)`: los documentos a enseñar en la tabla (None = el
    buscador vuelve a ser el normal).
    `on_pick(texto)`: buscar otro texto (al elegir un tag propuesto).
    """

    def __init__(self, master, *, colocar, on_docs, on_pick):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_MD,
                         border_width=1, border_color=theme.BORDER)
        self._colocar = colocar
        self._on_docs = on_docs
        self._on_pick = on_pick
        self._q: str | None = None
        self._gen = 0
        self._pintados = -1

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=theme.SPACE_4, pady=(theme.SPACE_3, 0))
        self.lbl_tag = ctk.CTkLabel(cab, text="", font=theme.FONT_SECTION,
                                    text_color=theme.ACCENT, anchor="w")
        self.lbl_tag.pack(side="left")
        self.lbl_info = ctk.CTkLabel(cab, text="", font=theme.FONT_SMALL,
                                     text_color=theme.TEXT_SUB, anchor="w")
        self.lbl_info.pack(side="left", padx=(theme.SPACE_3, 0))
        self.lbl_estado = ctk.CTkLabel(self, text="", font=theme.FONT_SMALL,
                                       text_color=theme.TEXT_MUTED, anchor="w", justify="left")
        self.lbl_estado.pack(fill="x", padx=theme.SPACE_4, pady=(theme.SPACE_1, 0))
        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent", height=40)
        self.lista.pack(fill="x", padx=theme.SPACE_2, pady=(theme.SPACE_1, theme.SPACE_3))
        ui.rueda_por_puntero(self.lista)

    # ── Búsqueda ─────────────────────────────────────────────────────────────

    def reiniciar(self) -> None:
        """Olvida la última búsqueda (los documentos se han recargado)."""
        self._q = None

    def buscar(self, q: str, docs: list[dict]) -> None:
        """Busca `q` como tag si lo parece. No hace nada si ya es la de ahora."""
        q = (q or "").strip()
        if q == self._q:
            return
        self._q = q
        self._gen += 1
        gen = self._gen
        if not tags_documentos.parece_tag(q):
            self._ocultar()
            return

        def work():
            try:
                filas, parecidos = tags_documentos.buscar(q)
            except Exception as exc:  # noqa: BLE001 — sin ERP, el buscador normal
                logger.info("Tags: el ERP no responde: %s", exc)
                ui.en_ui(self, lambda: self._sin_erp(gen))
                return
            if not filas:
                ui.en_ui(self, lambda: self._parecidos(gen, q, parecidos))
                return
            ui.en_ui(self, lambda: self._empezar(gen, filas))

            def progreso(n, total, nombre, hallazgos):
                if gen != self._gen:
                    raise _Cancelado
                ui.en_ui(self, lambda: self._avance(gen, n, total, nombre, hallazgos))

            try:
                res = tags_documentos.donde_esta(filas, docs, progreso=progreso)
            except _Cancelado:
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("Tags: la búsqueda de %s falló", q)
                msg = str(exc)          # «exc» deja de existir al salir del except
                ui.en_ui(self, lambda: self._fallo(gen, msg))
                return
            ui.en_ui(self, lambda: self._fin(gen, res))

        threading.Thread(target=work, daemon=True).start()

    # ── Estados del panel ────────────────────────────────────────────────────

    def _vigente(self, gen: int) -> bool:
        return gen == self._gen and self.winfo_exists()

    def _ocultar(self) -> None:
        self._colocar(False)
        self._on_docs(None)

    def _sin_erp(self, gen: int) -> None:
        if self._vigente(gen):
            self._ocultar()          # sin ERP no se sabe si es un tag: búsqueda normal

    def _parecidos(self, gen: int, q: str, parecidos: list[str]) -> None:
        if not self._vigente(gen):
            return
        if not parecidos:
            self._ocultar()          # no es un tag: es un código de documento, un título…
            return
        self._on_docs(None)
        self.lbl_tag.configure(text=f"«{q}» no es un tag exacto")
        self.lbl_info.configure(text="")
        self.lbl_estado.configure(text="¿Buscabas alguno de estos? Pulsa para buscarlo.")
        self._limpiar_lista()
        fila = ctk.CTkFrame(self.lista, fg_color="transparent")
        fila.pack(fill="x", padx=theme.SPACE_2, pady=theme.SPACE_1)
        for tag in parecidos:
            limpio = tag_legible(tag)
            ui.button(fila, limpio, "chip", size="xs",
                      command=lambda t=limpio: self._on_pick(t)).pack(side="left", padx=(0, theme.SPACE_1))
        self._alto(40)
        self._colocar(True)

    def _empezar(self, gen: int, filas: list[dict]) -> None:
        if not self._vigente(gen):
            return
        self._pintados = -1
        self.lbl_tag.configure(text=tag_legible(filas[0]["tag"]))
        self.lbl_info.configure(text=_resumen_erp(filas))
        self.lbl_estado.configure(text="⏳  Buscando en el ERP y en los PDF enviados del pedido…")
        self._limpiar_lista()
        self._alto(40)
        self._on_docs([])
        self._colocar(True)

    def _avance(self, gen: int, n: int, total: int, nombre: str, hallazgos: list[dict]) -> None:
        if not self._vigente(gen):
            return
        self.lbl_estado.configure(text=f"⏳  Leyendo los PDF enviados: {n} de {total}  ·  {nombre}")
        if len(hallazgos) != self._pintados:
            self._pintar(hallazgos)

    def _fin(self, gen: int, res: dict) -> None:
        if not self._vigente(gen):
            return
        self._pintar(res["hallazgos"])
        leidos, sin_texto = res["leidos"], res["sin_texto"]
        lectura = f"{leidos} PDF enviados leídos" if leidos else "El pedido no tiene PDF enviados"
        if sin_texto:
            lectura += f" ({sin_texto} son imagen y no se pueden leer)"
        if not res["hallazgos"]:
            texto = f"No aparece en ningún documento. {lectura}."
        elif res["por_pedido"]:
            texto = (f"No aparece escrito en ningún PDF. {lectura}. "
                     "Estos son los cálculos y planos de su pedido.")
        else:
            n = len(res["hallazgos"])
            texto = f"Aparece en {n} sitio{'s' if n != 1 else ''}. {lectura}."
        self.lbl_estado.configure(text=texto)

    def _fallo(self, gen: int, msg: str) -> None:
        if self._vigente(gen):
            self.lbl_estado.configure(text=f"✗  No se pudo terminar la búsqueda: {msg}",
                                      text_color=theme.RED)

    # ── Lista de resultados ──────────────────────────────────────────────────

    def _alto(self, px: int) -> None:
        """Alto de la lista. La barra de desplazamiento de CTk pide 200 px por su
        cuenta, así que se ajustan las dos: si no, una sugerencia ocupaba medio panel."""
        self.lista.configure(height=px)
        self.lista._scrollbar.configure(height=px)

    def _limpiar_lista(self) -> None:
        self.lbl_estado.configure(text_color=theme.TEXT_MUTED)
        for w in self.lista.winfo_children():
            w.destroy()

    def _pintar(self, hallazgos: list[dict]) -> None:
        self._pintados = len(hallazgos)
        self._limpiar_lista()
        docs = []
        lineas = 0
        for h in hallazgos:
            doc = h["doc"]
            if doc is not None:
                docs.append(doc)
            lineas += 1 + len(h["pruebas"])
            self._hallazgo(h)
        self._alto(min(MAX_ALTO, max(40, lineas * 26)))
        self._on_docs(docs)

    def _hallazgo(self, h: dict) -> None:
        caja = ctk.CTkFrame(self.lista, fg_color="transparent")
        caja.pack(fill="x", padx=theme.SPACE_2, pady=(theme.SPACE_1, 0))
        doc = h["doc"]
        if doc is not None:
            titulo = str(doc.get("Título", "") or "")
            ctk.CTkLabel(caja, text=str(doc.get("Nº Doc. EIPSA", "") or "—"),
                         font=theme.FONT_BODY_BOLD, text_color=theme.ACCENT,
                         anchor="w").pack(side="left")
            ctk.CTkLabel(caja, text=f"  {titulo[:70]}{'…' if len(titulo) > 70 else ''}"
                                    f"  ·  {doc.get('Nº Pedido', '')}",
                         font=theme.FONT_SMALL, text_color=theme.TEXT_SUB, anchor="w").pack(side="left")
        else:
            ctk.CTkLabel(caja, text="PDF sin código de documento", font=theme.FONT_BODY_BOLD,
                         text_color=theme.TEXT_SUB, anchor="w").pack(side="left")
            ctk.CTkLabel(caja, text=f"  ·  {h['pedido']}", font=theme.FONT_SMALL,
                         text_color=theme.TEXT_MUTED, anchor="w").pack(side="left")
        for prueba in h["pruebas"]:
            self._prueba(prueba)

    def _prueba(self, prueba: dict) -> None:
        fila = ctk.CTkFrame(self.lista, fg_color="transparent")
        fila.pack(fill="x", padx=(theme.SPACE_6, theme.SPACE_2))
        fichero = prueba["fichero"]
        texto = f"• {prueba['que']}"
        if fichero is not None:
            texto += f"   —   {ruta_corta(fichero)}"
        ctk.CTkLabel(fila, text=texto, font=theme.FONT_SMALL, text_color=theme.TEXT_MAIN,
                     anchor="w").pack(side="left")
        if fichero is not None:
            b = ui.button(fila, "Abrir", "outline", size="xs", width=56, text_color=theme.TEXT_SUB,
                          command=lambda f=fichero: self._abrir(f))
            b.pack(side="left", padx=(theme.SPACE_2, 0))
            ui.tooltip(b, str(fichero))

    def _abrir(self, fichero: Path) -> None:
        try:
            os.startfile(str(fichero))  # type: ignore[attr-defined]
        except OSError as exc:
            ui.toast(self, "No se pudo abrir", str(exc), kind="error")


def _resumen_erp(filas: list[dict]) -> str:
    """«P-26/001-S01 · pos. 1, 2 · Caudal · PURCHASED» de las filas del ERP."""
    con_pedido = [f for f in filas if f["pedido"]] or filas
    partes = []
    for pedido in dict.fromkeys(f["pedido"] for f in con_pedido):
        suyas = [f for f in con_pedido if f["pedido"] == pedido]
        pos = ", ".join(sorted(dict.fromkeys(f["posicion"] for f in suyas if f["posicion"]),
                                key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else 0, x)))
        estados = ", ".join(dict.fromkeys(f["estado"] for f in suyas if f["estado"]))
        trozo = " · ".join(x for x in (pedido or "sin pedido", f"pos. {pos}" if pos else "",
                                       suyas[0]["familia"], estados) if x)
        partes.append(trozo)
    return "   |   ".join(partes)
