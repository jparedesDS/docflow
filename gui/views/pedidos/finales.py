"""Los comentados del cliente, bajados de golpe.

Un pedido cerrado tiene cientos de documentos en Final, y cada PDF comentado
está a cuatro clics en el portal. Esto los baja todos seguidos: se puede cerrar
a medias y volver otro día, porque lo que ya está en la carpeta no se vuelve a
pedir.

De momento solo eGesDoc (Técnicas Reunidas). El botón sale en todos los pedidos
—para que se sepa que existe— pero apagado y diciendo por qué en los demás.
"""

import logging
import os
import re
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import preferences
from core.services import egesdoc
from gui import theme
from gui.widgets import ui

logger = logging.getLogger(__name__)

# El PO de TR son diez dígitos; en los documentos aparece a veces con el
# sufijo del suministro detrás («1000100010-03») y el portal solo quiere el base.
_PO_RE = re.compile(r"\b(\d{10})\b")


def po_del_pedido(docs: list[dict]) -> str:
    """El PO del cliente, sacado de los documentos del pedido."""
    for d in docs or []:
        m = _PO_RE.search(str(d.get("Nº PO", "") or ""))
        if m:
            return m.group(1)
    return ""


def boton(parent, pedido: str, dash: dict):
    """El botón de la barra de acciones, ya con su estado y su explicación.

    Sale siempre: si este pedido no se puede bajar, más vale decir por qué que
    esconder la función.
    """
    consulta = dash.get("consulta") or {}
    cliente = str(consulta.get("Cliente", "") or "").strip()
    po = po_del_pedido(dash.get("documents") or [])

    motivo = ""
    if not egesdoc.is_tr_client(cliente):
        motivo = (f"De momento solo se baja de eGesDoc (Técnicas Reunidas), y este pedido "
                  f"es de {cliente or 'otro cliente'}.\nLos demás portales, más adelante.")
    elif not po:
        motivo = "Este pedido no tiene número de PO del cliente en el ERP."
    elif not egesdoc.is_configured():
        motivo = "Falta el usuario o la contraseña de eGesDoc: Ajustes ▸ Portales."

    b = ui.button(parent, "⤓  Comentados del cliente", "outline",
                  corner_radius=theme.RADIUS_MD)
    if motivo:
        b.configure(state="disabled")
        ui.tooltip(b, motivo)
    else:
        b.configure(command=lambda: FinalesWindow(parent.winfo_toplevel(), pedido, po))
        ui.tooltip(b, f"Baja de eGesDoc el PDF comentado de cada documento en Final "
                      f"del PO {po}.")
    return b


def carpeta_por_defecto(po: str) -> Path:
    """Dónde dejar los comentados de este PO.

    La que ya se eligió para él, si la hubo: es lo que hace que al volver otro
    día se vean los que ya están y solo se pidan los que faltan. Para un PO
    nuevo, al lado de la última carpeta usada, y si no, en Descargas. Nunca
    dentro del repositorio, que es público.
    """
    propia = str((preferences.get("egesdoc_finales_dirs") or {}).get(str(po)) or "").strip()
    if propia:
        return Path(propia)
    ultima = str(preferences.get("egesdoc_finales_dir") or "").strip()
    if ultima and Path(ultima).parent.is_dir():
        return Path(ultima).parent / f"eGesDoc {po}"
    for nombre in ("Downloads", "Descargas"):
        carpeta = Path.home() / nombre
        if carpeta.is_dir():
            return carpeta / f"eGesDoc {po}"
    return Path.home() / f"eGesDoc {po}"


def recordar_carpeta(po: str, carpeta: Path) -> None:
    """Apunta la carpeta de este PO (y la última usada, para el siguiente)."""
    dirs = dict(preferences.get("egesdoc_finales_dirs") or {})
    dirs[str(po)] = str(carpeta)
    preferences.set_value("egesdoc_finales_dirs", dirs)
    preferences.set_value("egesdoc_finales_dir", str(carpeta))


class FinalesWindow(ctk.CTkToplevel):
    """Buscar en el portal los documentos en Final del PO y bajar sus comentados."""

    def __init__(self, master, pedido: str, po: str, buscar: bool = True):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self.title(f"Comentados del cliente · {pedido}")
        self.geometry("720x560")
        self.minsize(620, 480)
        self.transient(master)

        self._pedido = pedido
        self._po = po
        self._carpeta = carpeta_por_defecto(po)
        self._sesion = None
        self._proyecto = ""
        self._docs: list[dict] = []
        self._parar = False
        self._bajando = False

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        # `buscar=False` la levanta sin llamar al portal: lo que hace la prueba
        # de humo, que monta todas las ventanas para ver que no se caen.
        if buscar:
            self.after(120, self._buscar)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=theme.SPACE_5, pady=(theme.SPACE_5, theme.SPACE_1))
        ctk.CTkLabel(cab, text="Comentados del cliente", font=theme.FONT_TITLE,
                     text_color=theme.TEXT_MAIN, anchor="w").pack(anchor="w")
        ctk.CTkLabel(cab, text=f"{self._pedido}  ·  PO {self._po}  ·  "
                               f"eGesDoc (Técnicas Reunidas)",
                     font=theme.FONT_SUBTITLE, text_color=theme.TEXT_SUB,
                     anchor="w").pack(anchor="w", pady=(theme.SPACE_1, 0))

        pie = ctk.CTkFrame(self, fg_color="transparent")
        pie.pack(side="bottom", fill="x", padx=theme.SPACE_5, pady=theme.SPACE_4)
        self.btn_cerrar = ui.button(pie, "Cerrar", "outline", command=self._cerrar,
                                    size="lg")
        self.btn_cerrar.pack(side="right", padx=(theme.SPACE_2, 0))
        self.btn_bajar = ui.button(pie, "⤓  Descargar", "primary", command=self._descargar,
                                   size="lg", state="disabled")
        self.btn_bajar.pack(side="right")
        self.btn_carpeta = ui.button(pie, "📂  Abrir carpeta", "outline",
                                     command=self._abrir_carpeta, size="lg")
        self.btn_carpeta.pack(side="left")

        cuerpo = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_MD,
                              border_width=1, border_color=theme.BORDER)
        cuerpo.pack(fill="both", expand=True, padx=theme.SPACE_5,
                    pady=(theme.SPACE_3, 0))
        dentro = ctk.CTkFrame(cuerpo, fg_color="transparent")
        dentro.pack(fill="both", expand=True, padx=theme.SPACE_4, pady=theme.SPACE_4)

        fila = ctk.CTkFrame(dentro, fg_color="transparent")
        fila.pack(fill="x")
        ctk.CTkLabel(fila, text="Carpeta", font=theme.FONT_SMALL_BOLD,
                     text_color=theme.TEXT_SUB, width=54, anchor="w").pack(side="left")
        self.lbl_carpeta = ctk.CTkLabel(fila, text=str(self._carpeta), font=theme.FONT_SMALL,
                                        text_color=theme.TEXT_MAIN, anchor="w")
        self.lbl_carpeta.pack(side="left", fill="x", expand=True, padx=(0, theme.SPACE_2))
        ui.button(fila, "Cambiar…", "outline", size="sm",
                  command=self._elegir_carpeta).pack(side="right")

        self.lbl_estado = ctk.CTkLabel(dentro, text="Entrando en el portal…",
                                       font=theme.FONT_BODY_BOLD, text_color=theme.TEXT_MAIN,
                                       anchor="w")
        self.lbl_estado.pack(fill="x", pady=(theme.SPACE_4, theme.SPACE_2))

        self.barra = ctk.CTkProgressBar(dentro, height=8, corner_radius=4,
                                        fg_color=theme.BG_INPUT, progress_color=theme.ACCENT)
        self.barra.set(0)
        self.barra.pack(fill="x", pady=(0, theme.SPACE_3))

        self.log = ctk.CTkTextbox(dentro, font=theme.FONT_MONO, fg_color=theme.BG_INPUT,
                                  text_color=theme.TEXT_SUB, border_width=0,
                                  corner_radius=theme.RADIUS_MD, activate_scrollbars=True)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    # ── Pintar ───────────────────────────────────────────────────────────────

    def _escribir(self, texto: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _estado(self, texto: str, color: str | None = None) -> None:
        self.lbl_estado.configure(text=texto, text_color=color or theme.TEXT_MAIN)

    def _elegir_carpeta(self) -> None:
        elegida = filedialog.askdirectory(parent=self, title="Dónde dejar los comentados",
                                          initialdir=str(self._carpeta.parent))
        if not elegida:
            return
        self._carpeta = Path(elegida)
        recordar_carpeta(self._po, self._carpeta)
        self.lbl_carpeta.configure(text=str(self._carpeta))
        if self._docs:
            self._resumen_inicial()

    def _abrir_carpeta(self) -> None:
        try:
            self._carpeta.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self._carpeta))          # noqa: S606 — Explorador de Windows
        except OSError as exc:
            ui.toast(self, "No se pudo abrir la carpeta", str(exc), "error")

    # ── Buscar en el portal ──────────────────────────────────────────────────

    def _buscar(self) -> None:
        def worker():
            try:
                s = egesdoc.login()
                proyecto = egesdoc.find_project_for_po(s, self._po)
                egesdoc.enter_po(s, proyecto, self._po)
                docs = egesdoc.list_documents(s, summary="Finals")
                ui.en_ui(self, lambda: self._encontrados(s, proyecto, docs))
            except Exception as exc:                  # noqa: BLE001 — se enseña tal cual
                logger.exception("eGesDoc: no se pudo listar los finales del PO %s", self._po)
                msg = str(exc).splitlines()[0]
                ui.en_ui(self, lambda: self._estado(f"✗  {msg}", theme.RED))
        threading.Thread(target=worker, daemon=True).start()

    def _encontrados(self, sesion, proyecto: str, docs: list[dict]) -> None:
        self._sesion = sesion
        self._proyecto = proyecto
        self._docs = docs
        if not docs:
            self._estado("Este PO no tiene ningún documento en Final.", theme.TEXT_SUB)
            return
        self._resumen_inicial()

    def _pendientes(self) -> int:
        if not self._carpeta.is_dir():
            return len(self._docs)
        return sum(1 for d in self._docs
                   if egesdoc.ya_bajado(self._carpeta, egesdoc.nombre_de(d)) is None)

    def _resumen_inicial(self) -> None:
        total, faltan = len(self._docs), self._pendientes()
        ya = total - faltan
        texto = f"{total} documentos en Final"
        if ya:
            texto += f"  ·  {ya} ya están en la carpeta"
        self._estado(texto)
        self.barra.set(ya / total if total else 0)
        if faltan:
            self.btn_bajar.configure(state="normal", text=f"⤓  Descargar {faltan}")
        else:
            self.btn_bajar.configure(state="disabled", text="⤓  Descargar")
            self._escribir("Ya está todo bajado.")

    # ── Descargar ────────────────────────────────────────────────────────────

    def _descargar(self) -> None:
        self._parar = False
        self._bajando = True
        self.btn_bajar.configure(text="Cancelar", command=self._cancelar)
        self.btn_cerrar.configure(state="disabled")
        self._escribir(f"— {len(self._docs)} documentos · {self._carpeta}")

        def progreso(n, total, doc, estado):
            ui.en_ui(self, lambda: self._paso(n, total, doc, estado))
            return not self._parar

        sesion = self._sesion

        def worker():
            try:
                filas = egesdoc.download_final_documents(
                    self._po, self._carpeta, project_hint=self._proyecto,
                    session=sesion, docs=self._docs, progreso=progreso)
                ui.en_ui(self, lambda: self._terminado(filas))
            except Exception as exc:                  # noqa: BLE001
                logger.exception("eGesDoc: falló la descarga de finales del PO %s", self._po)
                msg = str(exc).splitlines()[0]
                ui.en_ui(self, lambda: self._fallo(msg))
            finally:
                # Si mientras tanto se cerró la ventana, la sesión es de nadie:
                # este hilo es el último que la tiene y la cierra él.
                if self._sesion is None:
                    try:
                        sesion.close()
                    except Exception:                 # noqa: BLE001
                        pass
        threading.Thread(target=worker, daemon=True).start()

    def _paso(self, n: int, total: int, doc: dict, estado: str) -> None:
        nombre = egesdoc.nombre_de(doc)
        self.barra.set(n / total if total else 0)
        self._estado(f"{n} de {total}  ·  {nombre}")
        if estado != "ya estaba":
            self._escribir(f"{nombre:<28} {estado}")

    def _cancelar(self) -> None:
        self._parar = True
        self.btn_bajar.configure(state="disabled", text="Parando…")
        self._escribir("Parando al terminar el documento que está en marcha…")

    def _fallo(self, msg: str) -> None:
        self._bajando = False
        self._estado(f"✗  {msg}", theme.RED)
        self.btn_cerrar.configure(state="normal")
        self.btn_bajar.configure(state="normal", text="⤓  Reintentar",
                                 command=self._descargar)

    def _terminado(self, filas: list[dict]) -> None:
        self._bajando = False
        self.btn_cerrar.configure(state="normal")
        bajados = [f for f in filas if f["file"]]
        fallos = [f for f in filas if f["error"]]
        sin = [f for f in filas if not f["file"] and not f["error"]]

        try:
            resumen = egesdoc.write_summary(filas, self._carpeta)
            self._escribir(f"Resumen: {resumen.name}")
        except OSError as exc:
            logger.info("No se pudo escribir el resumen: %s", exc)

        if sin:
            self._escribir(f"{len(sin)} sin fichero comentado en el portal: "
                           + ", ".join(f["code"] for f in sin[:6])
                           + ("…" if len(sin) > 6 else ""))
        if fallos:
            for f in fallos[:6]:
                self._escribir(f"✗ {f['code']}: {f['error']}")

        faltan = self._pendientes()
        if self._parar:
            self._estado(f"Parado: {len(bajados)} de {len(filas)} · quedan {faltan}",
                         theme.AMBER)
        elif fallos:
            self._estado(f"{len(fallos)} se quedaron por el camino · quedan {faltan}",
                         theme.AMBER)
        else:
            self._estado(f"Listo: {len(bajados)} documentos en la carpeta", theme.GREEN)
        self.barra.set(1 - (faltan / len(self._docs)) if self._docs else 1)

        if faltan:
            self.btn_bajar.configure(state="normal", text=f"⤓  Reintentar {faltan}",
                                     command=self._descargar)
        else:
            self.btn_bajar.configure(state="disabled", text="⤓  Descargar")

    # ── Cerrar ───────────────────────────────────────────────────────────────

    def _cerrar(self) -> None:
        """Se cierra sin esperar: el hilo termina el documento que tenga entre
        manos, cierra la sesión y se calla (lo que ya bajó se queda)."""
        self._parar = True
        sesion, self._sesion = self._sesion, None
        if sesion is not None and not self._bajando:
            try:
                sesion.close()
            except Exception:                         # noqa: BLE001
                pass
        self.destroy()
