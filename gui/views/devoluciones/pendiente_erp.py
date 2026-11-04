"""«Pendiente en el ERP»: lo devuelto que el ERP todavía no dice.

Una fila por documento con lo que hay que poner (estado, fecha y NUESTRA
revisión) y lo que dice ahora el ERP. Ordenadas por estado y fecha, las que se
ponen igual quedan juntas: en la edición de documentos del ERP se seleccionan y
se pega el valor de una vez (Ctrl+V pega un mismo valor en todas las celdas
seleccionadas). La revisión del cliente se enseña entre paréntesis, solo para
reconocer el documento: no se compara con la nuestra.

Solo lee el ERP. Una fila desaparece sola cuando el ERP ya cuadra.
"""

import logging
import os
import threading
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.services import registro_erp
from gui import theme
from gui.widgets import ui
from gui.widgets.pilltable import PillTable

logger = logging.getLogger(__name__)

# En el orden en que se mete en la línea del documento: fecha, estado y, en la
# primera devolución, el 1er envío. La revisión no se toca al recibir: se
# enseña para reconocer el documento.
COLUMNS = [
    {"key": "Pedido",    "label": "Pedido",        "min": 120, "anchor": "w"},
    {"key": "Documento", "label": "Documento",     "min": 230, "anchor": "w", "floor": 140},
    {"key": "Título",    "label": "Título",        "min": 200, "anchor": "w", "stretch": True, "floor": 100},
    {"key": "Fecha",     "label": "Fecha",         "min": 100, "anchor": "center"},
    {"key": "Estado",    "label": "Estado",        "min": 130, "anchor": "center"},
    {"key": "Primer",    "label": "1er envío",     "min": 110, "anchor": "center"},
    {"key": "Rev",       "label": "Rev.",          "min": 90,  "anchor": "center"},
    {"key": "ERP",       "label": "El ERP dice",   "min": 200, "anchor": "w", "floor": 120},
]

_COLOR = {registro_erp.APROBADO: theme.GREEN, registro_erp.INFORMACION: theme.GREEN,
          registro_erp.COM_MENORES: theme.AMBER, registro_erp.COMENTADO: theme.AMBER,
          registro_erp.COM_MAYORES: theme.ROSE,
          registro_erp.RECHAZADO: theme.RED, registro_erp.ELIMINADO: theme.TEXT_MUTED}


def celdas(f: dict) -> dict:
    """Las celdas de una fila pendiente (lo que falta, en negrita)."""
    falta = set(f.get("falta") or ())
    erp = f.get("erp") or {}
    rev = f.get("nuestra") or "?"
    if f.get("cliente"):
        rev += f"  (cli {f['cliente']})"
    if "documento" in falta:
        dice = "— no está en el ERP"
    else:
        partes = [erp.get("fecha") or "(sin fecha)", erp.get("estado") or "(sin estado)"]
        if erp.get("revision") not in (None, ""):
            partes.append(f"rev {erp['revision']}")
        dice = " · ".join(partes)
    if "primer_envio" in falta:
        # Sin la fecha a la vista (el ERP ya no dice «Enviado» en rev 0): a mano
        primer = {"text": f.get("primer_envio") or "? búscalo", "bold": True,
                  "fg": theme.TEXT_MAIN if f.get("primer_envio") else theme.AMBER}
    else:
        primer = {"text": "", "fg": theme.TEXT_MUTED}
    color = _COLOR.get(f.get("estado"), theme.TEXT_MAIN)
    return {
        "Pedido": {"text": f.get("pedido", "")},
        "Documento": {"text": f.get("doc_eipsa") or f.get("doc_cliente", "")},
        "Título": {"text": f.get("titulo", "")},
        "Fecha": {"text": f.get("fecha", ""), "bold": "fecha" in falta,
                  "fg": theme.TEXT_MAIN if "fecha" in falta else theme.TEXT_MUTED},
        "Estado": {"text": f.get("estado", ""), "pill": True, "fg": color,
                   "bold": "estado" in falta},
        "Primer": primer,
        "Rev": {"text": rev, "fg": theme.TEXT_MUTED},
        "ERP": {"text": dice, "fg": theme.TEXT_MUTED},
    }


class PendienteErpWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self.title("Pendiente en el ERP")
        self.geometry("1240x720")
        self.minsize(900, 480)
        self.transient(master)
        self._filas: list[dict] = []
        self._build()
        self.recargar()

    def _build(self) -> None:
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=theme.SPACE_5, pady=(theme.SPACE_5, theme.SPACE_1))
        ctk.CTkLabel(cab, text="Pendiente en el ERP", font=theme.FONT_TITLE,
                     text_color=theme.TEXT_MAIN, anchor="w").pack(side="left")
        ui.button(cab, "⤓  Exportar Excel", "outline", size="sm",
                  command=self._exportar).pack(side="right")
        self.btn_recargar = ui.button(cab, "↻  Recargar", "outline", size="sm", command=self.recargar)
        self.btn_recargar.pack(side="right", padx=(0, theme.SPACE_2))
        ctk.CTkLabel(
            self, anchor="w", justify="left", font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
            text=("Lo que el cliente ha devuelto (y la app ha archivado) y el ERP aún no dice, en el orden en que "
                  "se mete: fecha, estado y, si es la primera devolución, el 1er envío (la fecha de la rev 0).\n"
                  "La revisión no se toca: va para reconocer el documento (la nuestra y, entre paréntesis, la del "
                  "cliente). En negrita, lo que falta. Las que llevan la misma fecha y estado van juntas para "
                  "pegarlas de una vez. Clic derecho para copiar."),
        ).pack(fill="x", padx=theme.SPACE_5)
        self.lbl_estado = ctk.CTkLabel(self, text="", anchor="w", font=theme.FONT_SMALL_BOLD,
                                       text_color=theme.TEXT_MUTED)
        self.lbl_estado.pack(fill="x", padx=theme.SPACE_5, pady=(theme.SPACE_2, 0))
        self.table = PillTable(self, columns=COLUMNS, multiselect=True, rowheight=36,
                               on_double_click=self._abrir_carpeta)
        self.table.pack(fill="both", expand=True, padx=theme.SPACE_5, pady=theme.SPACE_3)
        self.table.set_context_menu(self._menu)

    # ── Datos ────────────────────────────────────────────────────────────────

    def recargar(self) -> None:
        self.btn_recargar.configure(state="disabled")
        self.lbl_estado.configure(text="Comparando con el ERP…")

        def work():
            try:
                res = registro_erp.pendientes()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Pendiente en el ERP")
                res = {"ok": False, "motivo": str(exc), "filas": [], "total": 0}
            ui.en_ui(self, lambda: self._pintar(res))

        threading.Thread(target=work, daemon=True).start()

    def _pintar(self, res: dict) -> None:
        self.btn_recargar.configure(state="normal")
        # La columna ERP de la lista de Devoluciones dice lo mismo: que se entere
        if hasattr(self.master, "_cargar_erp"):
            self.master._cargar_erp()
        if not res["ok"]:
            self._filas = []
            self.table.set_rows([])
            self.lbl_estado.configure(text=f"⚠ {res['motivo']}", text_color=theme.AMBER)
            return
        # Como se trabaja en el ERP: se busca el pedido y, dentro, cada línea
        filas = sorted(res["filas"], key=lambda f: ("documento" in f["falta"], f.get("pedido", ""),
                                                     f.get("doc_eipsa") or f.get("doc_cliente", "")))
        self._filas = filas
        self.table.set_rows([(f["clave"], celdas(f)) for f in filas])
        if not filas:
            self.lbl_estado.configure(
                text=f"✓ El ERP cuadra con las {res['total']} devoluciones archivadas que se siguen.",
                text_color=theme.GREEN)
            return
        resumen = [f"{len(g['filas'])} → {g['fecha']} {g['estado']}" for g in registro_erp.grupos(filas)[:5]]
        sin = sum(1 for f in filas if "documento" in f["falta"])
        texto = f"{len(filas)} por registrar  ·  " + "   ·   ".join(resumen)
        if sin:
            texto += f"   ·   {sin} no están en el ERP"
        self.lbl_estado.configure(text=texto, text_color=theme.TEXT_MAIN)

    def _sel(self, iid: str) -> list[dict]:
        ids = set(self.table.selected_ids()) | {iid}
        return [f for f in self._filas if f["clave"] in ids]

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _menu(self, iid: str):
        filas = self._sel(iid)
        if not filas:
            return None
        f = next(x for x in filas if x["clave"] == iid)
        copiar = self.table.copy_to_clipboard
        n = len(filas)
        docs = "\n".join(x.get("doc_eipsa") or x.get("doc_cliente", "") for x in filas)
        items = [
            (f"Copiar fecha {f['fecha']}", lambda: copiar(f["fecha"])),
            (f"Copiar estado «{f['estado']}»", lambda: copiar(f["estado"])),
        ]
        if "primer_envio" in f["falta"] and f.get("primer_envio"):
            items.append((f"Copiar 1er envío {f['primer_envio']}", lambda: copiar(f["primer_envio"])))
        return items + [
            (f"Copiar Nº de documento{'s' if n > 1 else ''} ({n})", lambda: copiar(docs)),
            ("-", None),
            ("📂  Abrir la carpeta de la devolución", lambda: self._abrir_carpeta(iid)),
            ("-", None),
            (f"No registrar {'estas' if n > 1 else 'esta'} (ocultar)", lambda: self._ignorar(filas)),
        ]

    def _abrir_carpeta(self, iid: str) -> None:
        f = next((x for x in self._filas if x["clave"] == iid), None)
        carpeta = Path(f.get("carpeta", "")) if f else None
        if carpeta and carpeta.is_dir():
            os.startfile(str(carpeta))  # type: ignore[attr-defined]
        elif f:
            messagebox.showwarning("Carpeta no encontrada", f"No encuentro:\n{carpeta}", parent=self)

    def _ignorar(self, filas: list[dict]) -> None:
        if not messagebox.askyesno(
                "No registrar", f"¿Ocultar {len(filas)} devolución(es)? No vuelven a salir.", parent=self):
            return
        for f in filas:
            registro_erp.ignorar(f["clave"])
        self.recargar()

    def _exportar(self) -> None:
        if not self._filas:
            ui.toast(self.master, "Nada que exportar", "El ERP cuadra con todo lo archivado.", kind="info")
            return
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Exportar lo pendiente en el ERP", defaultextension=".xlsx",
            initialfile=f"Pendiente ERP {date.today():%Y-%m-%d}.xlsx",
            filetypes=[("Excel", "*.xlsx")])
        if not ruta:
            return
        try:
            registro_erp.exportar_excel(self._filas, ruta)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("No se pudo exportar", str(exc), parent=self)
            return
        ui.toast(self.master, "Exportado", ruta, kind="success")
