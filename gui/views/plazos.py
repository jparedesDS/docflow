"""Vista Plazos — del correo de la oferta a la fábrica.

  · «Cola»: pedidos activados que aún no han pasado a fábrica, con lo que les
    falta (planos, material o las dos cosas) y su margen. Arriba, los que ya
    tienen el material y esperan los planos.
  · «Pedidos»: los días de cada paso de cada pedido; el del cliente, en gris.
  · «Por persona»: lo que suele tardar cada uno en su paso, con cuántos
    pedidos lo dicen.

Primero se pinta con lo que ya se sabía del correo (caché) y después se leen
los buzones de Ofertas y se repinta: así la sección abre rápido.
"""

import logging
import os
import threading
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.services import seguimiento, seguimiento_correos
from gui import theme
from gui.widgets import ui
from gui.widgets.table import DataTable

logger = logging.getLogger(__name__)

TAB_COLA, TAB_PEDIDOS, TAB_PERSONAS = "Cola", "Pedidos", "Por persona"

COLA_COLUMNS = ["#", "Qué falta", "Pedido", "Cliente", "Equipo", "Activación", "Entrega", "Margen", "Basado en"]
# Días de cada paso, como en el Excel: pocas columnas y con nombre claro
PED_TRAMOS = [("comercial", "Contestar"), ("tec_oc", "Orden de compra"), ("compras_pedir", "Compras"),
              ("proveedor", "Proveedor"), ("tecnico", "Planos a fábrica"), ("listo", "Puede empezar"),
              ("total", "Total")]
PED_COLUMNS = ["Pedido", "Cliente"] + [n for _t, n in PED_TRAMOS] + ["Lo que retrasó", "Técnico"]
PER_COLUMNS = ["Paso", "Persona", "Pedidos", "Típico (días)", "La mitad, entre"]
RETRASO = {"material": "Material", "planos": "Planos", "los dos": "Los dos"}

FALTA = {"planos": "Planos (material listo)", "ambos": "Planos y material", "material": "Material",
         "nada": "Listo para fábrica"}
PASOS = {"comercial": "Comercial · contestar ofertas", "activar": "Comercial · activar pedidos",
         "tec_oc": "Técnico · orden de compra", "compras": "Compras · pedir al proveedor",
         "tecnico": "Técnico · planos a fábrica"}
ORDEN_PASOS = list(PASOS)


def _f(v) -> str:
    return v.strftime("%d-%m-%Y") if hasattr(v, "strftime") else "—"


def _n(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(v)


def _dias(v) -> str:
    """Días enteros; «—» si no hay dato o sale negativo (un correo archivado tarde)."""
    return "—" if v is None or v < 0 else str(int(round(v)))


def fila_pedido(f: dict) -> list:
    """La fila de un pedido en la pestaña «Pedidos»."""
    from core.services.seguimiento import _persona
    return ([f["pedido"], f["cliente"] or "—"] + [_dias(f["tramos"].get(t)) for t, _n_ in PED_TRAMOS]
            + [RETRASO.get(f.get("retraso_por"), "—"), _persona(f["hitos"]["planos"]["persona"])[1] or "—"])


def personas_ordenadas(por_persona: list[dict]) -> list[dict]:
    """Por paso, en el orden de la cadena; dentro, la que más pedidos lleva primero."""
    return sorted(por_persona, key=lambda p: (ORDEN_PASOS.index(p["paso"]) if p["paso"] in ORDEN_PASOS
                                              else len(ORDEN_PASOS), -p["n"]))


def tarjetas(resumen: dict, cola: list[dict]) -> list[tuple]:
    """(etiqueta, valor, color, debajo) de las tarjetas de arriba: lo mismo que el resumen del Excel."""
    t = resumen["tramos"]

    def de(tramo, etiqueta, color):
        s = t[tramo]
        valor = f"{int(round(s['mediana']))} d" if s["mediana"] is not None else "—"
        return etiqueta, valor, color, f"lo normal · {s['n']} pedidos"

    esperan = sum(1 for c in cola if c["falta"] == "planos")
    return [
        de("comercial", "Contestar una oferta", theme.BLUE),
        de("tec_oc", "Técnico: orden de compra a Compras", theme.ACCENT),
        de("proveedor", "Proveedor: entrega el material", theme.AMBER),
        de("tecnico", "Técnico: planos a fábrica", theme.ACCENT),
        ("Esperan planos con el material listo", esperan, theme.RED if esperan else theme.GREEN,
         f"de {len(cola)} pedidos en cola"),
    ]


class PlazosView(ctk.CTkFrame):
    def __init__(self, master, on_open_pedido=None, **kwargs):
        super().__init__(master, fg_color=theme.BG_PAGE, **kwargs)
        self._on_open_pedido = on_open_pedido
        self._datos: dict | None = None
        self._cargando = False
        self._build_layout()
        self._reload(con_correo=False)

    def _build_layout(self) -> None:
        header = ui.page_header(
            self, "Plazos",
            "Del correo de la oferta a la fábrica: cuánto tarda cada paso y qué pedido va primero.",
            icon="⏱", help_key="plazos")
        self.btn_web = ui.button(header.actions, "🌐  Informe web", "outline", size="sm", width=120,
                                 text_color=theme.TEXT_SUB, command=self._informe)
        self.btn_web.pack(side="right", padx=(theme.SPACE_2, 0))
        self.btn_export = ui.button(header.actions, "⤓  Excel", "outline", size="sm", width=90,
                                    text_color=theme.TEXT_SUB, command=self._export)
        self.btn_export.pack(side="right", padx=(theme.SPACE_2, 0))
        self.btn_fabrica = ui.button(header.actions, "⤓  Excel a fábrica", "outline", size="sm", width=140,
                                     text_color=theme.TEXT_SUB, command=self._export_fabrica)
        self.btn_fabrica.pack(side="right", padx=(theme.SPACE_2, 0))
        self.btn_reload = ui.button(header.actions, "↻", "outline", size="sm", width=36,
                                    text_color=theme.TEXT_SUB, command=lambda: self._reload(con_correo=True))
        self.btn_reload.pack(side="right")

        self.lbl_status = ctk.CTkLabel(self, text="", font=theme.FONT_SMALL,
                                       text_color=theme.TEXT_MUTED, anchor="w", justify="left")
        self.lbl_status.pack(fill="x", padx=theme.SPACE_6)

        self.kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        self.kpi_row.pack(fill="x", padx=theme.SPACE_6, pady=(theme.SPACE_3, theme.SPACE_2))
        for c in range(5):
            self.kpi_row.grid_columnconfigure(c, weight=1, uniform="kpi")

        self.tabs = ui.tabview(self)
        self.tabs.pack(fill="both", expand=True, padx=theme.SPACE_6, pady=(0, theme.SPACE_5))
        tab_c, tab_p, tab_r = self.tabs.add(TAB_COLA), self.tabs.add(TAB_PEDIDOS), self.tabs.add(TAB_PERSONAS)

        self.t_cola = DataTable(tab_c, columns=COLA_COLUMNS, on_double_click=lambda _e=None: self._abrir(self.t_cola))
        self.t_cola.pack(fill="both", expand=True, pady=(theme.SPACE_2, 0))
        self.t_cola.set_columns_anchor({"#": "center", "Activación": "center", "Entrega": "center",
                                        "Margen": "center", "Basado en": "w"})
        self.t_cola.set_columns_floor({"Qué falta": 190, "Pedido": 130, "Margen": 110, "Basado en": 210})
        self.t_cola.tree.tag_configure("planos", foreground=theme.RED)
        self.t_cola.tree.tag_configure("riesgo", foreground=theme.AMBER)

        self.t_ped = DataTable(tab_p, columns=PED_COLUMNS, on_double_click=lambda _e=None: self._abrir(self.t_ped))
        self.t_ped.pack(fill="both", expand=True, pady=(theme.SPACE_2, 0))
        self.t_ped.set_columns_anchor({n: "center" for _t, n in PED_TRAMOS})
        self.t_ped.set_columns_anchor({"Lo que retrasó": "center"})
        self.t_ped.set_columns_floor({**{n: 118 for _t, n in PED_TRAMOS}, "Orden de compra": 150,
                                      "Planos a fábrica": 150, "Puede empezar": 140, "Lo que retrasó": 140,
                                      "Total": 75, "Compras": 100, "Pedido": 155, "Cliente": 150, "Técnico": 145})

        self.t_per = DataTable(tab_r, columns=PER_COLUMNS)
        self.t_per.pack(fill="both", expand=True, pady=(theme.SPACE_2, 0))
        self.t_per.set_columns_anchor({"Pedidos": "center", "Típico (días)": "center", "La mitad, entre": "center"})
        self.t_per.set_columns_floor({"Paso": 290, "Persona": 190})

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _reload(self, con_correo: bool) -> None:
        if self._cargando:
            return
        self._cargando = True
        self.btn_reload.configure(state="disabled")
        self.lbl_status.configure(text="⏳  Leyendo el ERP y las carpetas de los pedidos…", text_color=theme.TEXT_MUTED)

        def worker():
            try:
                datos = seguimiento.cargar(correo=con_correo)
                ui.en_ui(self, lambda: self._render(datos, seguir=not con_correo))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Plazos: error al cargar")
                msg = str(exc)
                ui.en_ui(self, lambda: self._error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _leer_correo(self) -> None:
        """Después de pintar: lee los buzones de Ofertas y repinta con las horas nuevas."""
        self.lbl_status.configure(text=self.lbl_status.cget("text") + "  ·  ⏳ leyendo el correo de Ofertas…")

        def worker():
            try:
                seguimiento_correos.actualizar()
            except Exception as exc:  # noqa: BLE001 — sin correo se queda con la caché
                logger.info("Plazos: no se pudo leer el correo: %s", exc)
                ui.en_ui(self, lambda: self._render(self._datos, seguir=False))
                return
            datos = seguimiento.cargar(correo=False)
            ui.en_ui(self, lambda: self._render(datos, seguir=False))

        self._cargando = True
        threading.Thread(target=worker, daemon=True).start()

    def _error(self, msg: str) -> None:
        self._cargando = False
        self.btn_reload.configure(state="normal")
        self.lbl_status.configure(text=f"✗  {msg}", text_color=theme.RED)

    def _render(self, datos: dict | None, seguir: bool) -> None:
        self._cargando = False
        self.btn_reload.configure(state="normal")
        if not datos:
            return
        self._datos = datos
        r = datos["resumen"]
        partes = [f"{len(datos['filas'])} pedidos de {', '.join(str(a) for a in datos['años'])}",
                  f"{r['con_hora']['rfq']} de {r['con_hora']['total']} ofertas con la hora del correo",
                  f"actualizado {datos['generado']:%d-%m-%Y %H:%M}"]
        texto, color = "  ·  ".join(partes), theme.TEXT_MUTED
        if datos["avisos"]:
            texto, color = "⚠  " + " · ".join(datos["avisos"]) + "  ·  " + texto, theme.AMBER
        self.lbl_status.configure(text=texto, text_color=color)
        self._kpis()
        self._fill()
        if seguir:
            self._leer_correo()

    def _kpis(self) -> None:
        for w in self.kpi_row.winfo_children():
            w.destroy()
        cards = tarjetas(self._datos["resumen"], self._datos["cola"])
        for col, (label, value, color, sub) in enumerate(cards):
            ui.kpi_card(self.kpi_row, label, value, color, sub).grid(
                row=0, column=col, sticky="ew", padx=(0 if col == 0 else theme.SPACE_2, 0))

    def _fill(self) -> None:
        d = self._datos
        self.t_cola.clear()
        for i, c in enumerate(d["cola"]):
            m = c.get("margen")
            margen = f"{m[0]} a {m[1]} d" if m else "—"
            base = f"{c['margen_n']} pedidos ({c['margen_de']})" if m else ""
            tag = "planos" if c["falta"] == "planos" else ("riesgo" if m and m[0] < 0 else "")
            self.t_cola.add_row([i + 1, FALTA.get(c["falta"], c["falta"]), c["pedido"], c["cliente"] or "—",
                                 c["equipo"] or "—", _f(c["hitos"]["activacion"]["fecha"]),
                                 _f(c["hitos"]["entrega"]["fecha"]), margen, base],
                                iid=f"c{i}", tags=(tag,) if tag else ())
        self.t_ped.clear()
        # El más reciente arriba, como en el Excel
        self._pedidos_orden = sorted(d["filas"], key=lambda x: (str(x["hitos"]["pedido"]["fecha"] or ""),
                                                                x["pedido"]), reverse=True)
        for i, f in enumerate(self._pedidos_orden):
            self.t_ped.add_row(fila_pedido(f), iid=f"p{i}")
        self.t_per.clear()
        for i, p in enumerate(personas_ordenadas(d["resumen"]["por_persona"])):
            rango = f"{_n(p['p25'])}–{_n(p['p75'])}" if p["p25"] is not None else "—"
            self.t_per.add_row([PASOS.get(p["paso"], p["paso"]), p["persona"], p["n"], _n(p["mediana"]), rango],
                               iid=f"r{i}")
        for t in (self.t_cola, self.t_ped, self.t_per):
            self.after(60, t.autofit_columns)

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _fila(self, tabla) -> dict | None:
        iid = tabla.selected_iid()
        if not iid or not self._datos:
            return None
        i = int(iid[1:])
        lista = self._datos["cola"] if iid[0] == "c" else getattr(self, "_pedidos_orden", [])
        return lista[i] if i < len(lista) else None

    def _abrir(self, tabla) -> None:
        """Doble clic: la carpeta Envíos del pedido; si no la hay, el pedido en Pedidos."""
        f = self._fila(tabla)
        if not f:
            return
        if f.get("ruta") and os.path.isdir(f["ruta"]):
            os.startfile(f["ruta"])  # noqa: S606 — abrir la carpeta en el Explorador
        elif self._on_open_pedido:
            self._on_open_pedido(f["base"])

    def _export(self) -> None:
        if not self._datos:
            ui.toast(self, "Plazos", "Todavía no hay datos.", kind="info")
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar a Excel", defaultextension=".xlsx",
            initialfile=f"Plazos_{datetime.now():%Y-%m-%d}.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            from core.services import seguimiento_excel
            seguimiento_excel.exportar(self._datos, path)
            ui.toast(self, "Exportado", f"{len(self._datos['filas'])} pedidos a Excel.", kind="success")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Exportar", f"No se pudo exportar:\n{exc}", parent=self)

    def _export_fabrica(self) -> None:
        """El Excel escueto: activación → planos a fábrica, en días naturales y laborables."""
        if not self._datos:
            ui.toast(self, "Plazos", "Todavía no hay datos.", kind="info")
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar plazos a fábrica", defaultextension=".xlsx",
            initialfile=f"Plazos a fábrica {datetime.now():%Y-%m-%d}.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            from core.services import plazos_fabrica_excel
            plazos_fabrica_excel.exportar(self._datos, path)
            ui.toast(self, "Exportado", "Plazos a fábrica en Excel.", kind="success")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Exportar", f"No se pudo exportar:\n{exc}", parent=self)

    def _informe(self) -> None:
        if not self._datos:
            ui.toast(self, "Plazos", "Todavía no hay datos.", kind="info")
            return
        try:
            from core.services.interactive_report import generate_plazos
            os.startfile(str(generate_plazos(self._datos)))  # noqa: S606 — abrirlo en el navegador
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Informe web", f"No se pudo generar:\n{exc}", parent=self)
