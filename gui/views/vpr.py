"""Vista VPR — el informe mensual de avance que pide el cliente.

La pantalla separa dos cosas que no se mezclan:

· **Lo medido** — equipos, documentos, subpedidos, fabricación e inspección —
  sale del ERP y se enseña ya calculado. No se toca.
· **Lo que se promete** — nº de informe, fechas y los textos de cada apartado —
  llega escrito para repasar, y es lo único editable: son compromisos con el
  cliente, no datos.

Al generar se escribe el Word del propio cliente con sus casillas rellenas; la
plantilla no se toca y el informe nunca pisa a otro anterior.
"""

import logging
import threading
from datetime import date
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.services import monitoring as monitoring_service
from core.services import vpr as vpr_service
from gui import theme
from gui.widgets import ui

logger = logging.getLogger(__name__)

ANCHO_ETIQUETA = 190
ANCHO_FECHA = 110


class VprView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_PAGE, **kwargs)
        self._pedidos: list[str] = []
        self._cliente = ""
        self._plantilla = ""
        self._datos: dict = {}
        self._campos: dict = {}          # nombre → StringVar de la cabecera
        self._plan: dict = {}            # área → {inicio, fin, planificado}
        self._previstas: dict = {}       # grupo → StringVar
        self._textos: dict = {}          # apartado → CTkTextbox
        self._build()
        self.after(80, self._cargar_pedidos)

    # ── Construcción ──────────────────────────────────────────────────────────

    def _build(self) -> None:
        cab = ui.page_header(
            self, "VPR", "Informe mensual de avance con los datos del ERP",
            icon="📈", help_key="vpr")
        self.btn_generar = ui.button(cab.actions, "Generar VPR", "primary",
                                     command=self._generar, state="disabled")
        self.btn_generar.pack(side="right")
        self.btn_plantilla = ui.button(cab.actions, "Plantilla…", "outline",
                                       command=self._elegir_plantilla)
        self.btn_plantilla.pack(side="right", padx=(0, theme.SPACE_2))

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=theme.SPACE_6, pady=(0, theme.SPACE_3))
        ctk.CTkLabel(barra, text="Pedido", font=theme.FONT_SMALL_BOLD,
                     text_color=theme.TEXT_SUB).pack(side="left", padx=(0, theme.SPACE_2))
        self.cmb_pedido = ctk.CTkComboBox(barra, values=["—"], width=260, state="readonly",
                                          command=lambda _v: self._cargar_datos())
        self.cmb_pedido.pack(side="left")
        self.lbl_estado = ctk.CTkLabel(barra, text="", font=theme.FONT_SMALL,
                                       text_color=theme.TEXT_MUTED, anchor="w")
        self.lbl_estado.pack(side="left", padx=(theme.SPACE_4, 0), fill="x", expand=True)

        self.cuerpo = ctk.CTkScrollableFrame(self, fg_color=theme.BG_CARD,
                                             corner_radius=theme.RADIUS_MD)
        self.cuerpo.pack(fill="both", expand=True, padx=theme.SPACE_6, pady=(0, theme.SPACE_5))
        ui.rueda_por_puntero(self.cuerpo)

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _cargar_pedidos(self) -> None:
        def trabajo():
            docs = monitoring_service.get_monitoring_data()
            pedidos = sorted({str(d.get("Nº Pedido", "")).strip()
                              for d in docs if str(d.get("Nº Pedido", "")).strip()}, reverse=True)
            self.after(0, lambda: self._pinta_pedidos(pedidos))
        threading.Thread(target=trabajo, daemon=True).start()

    def _pinta_pedidos(self, pedidos: list[str]) -> None:
        self._pedidos = pedidos
        self.cmb_pedido.configure(values=pedidos or ["—"])
        if pedidos:
            self.cmb_pedido.set(pedidos[0])
            self._cargar_datos()

    def _cargar_datos(self) -> None:
        pedido = self.cmb_pedido.get()
        self.lbl_estado.configure(text="⏳  Leyendo el ERP…")
        self.btn_generar.configure(state="disabled")

        def trabajo():
            try:
                docs = monitoring_service.get_monitoring_data()
                cliente = next((str(d.get("Cliente", "")).strip() for d in docs
                                if str(d.get("Nº Pedido", "")).strip() == pedido), "")
                datos = vpr_service.datos(pedido)
                self.after(0, lambda: self._pinta(datos, cliente))
            except Exception as exc:  # noqa: BLE001 — el ERP puede no estar
                logger.exception("VPR: datos de %s", pedido)
                aviso = str(exc)
                self.after(0, lambda: self.lbl_estado.configure(text=f"✗  {aviso}"))
        threading.Thread(target=trabajo, daemon=True).start()

    def _pinta(self, datos: dict, cliente: str) -> None:
        self._datos, self._cliente = datos, cliente
        self._plantilla = vpr_service.plantilla_de(cliente)
        propuesta = vpr_service.propuesta(datos)

        for w in self.cuerpo.winfo_children():
            w.destroy()
        self._campos, self._plan, self._previstas, self._textos = {}, {}, {}, {}

        if not datos["equipos"]:
            ui.empty_state(self.cuerpo, "Este pedido no tiene equipos en el ERP",
                           "Sin tags no se puede medir el avance.", icon="○")
            self._refresca_estado()
            return

        self._bloque_informe(propuesta)
        self._bloque_avance(propuesta)
        self._bloque_equipos(propuesta)
        self._bloque_subpedidos()
        self._bloque_textos(propuesta)
        self._refresca_estado()

    def _refresca_estado(self) -> None:
        plantilla = Path(self._plantilla).name if self._plantilla else "sin plantilla"
        d = self._datos
        resumen = (f"{d['equipos']} equipos · {d['documentos']['aprobados']}/"
                   f"{d['documentos']['total']} documentos aprobados · "
                   f"{len(d['subpedidos'])} subpedidos") if d else ""
        self.lbl_estado.configure(text=f"{self._cliente or '—'} · {plantilla} · {resumen}")
        self.btn_generar.configure(state="normal" if (self._plantilla and d) else "disabled")

    # ── Bloques de la pantalla ────────────────────────────────────────────────

    def _seccion(self, titulo: str, nota: str = ""):
        caja = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        caja.pack(fill="x", padx=theme.SPACE_4, pady=(theme.SPACE_3, 0))
        ctk.CTkLabel(caja, text=titulo, font=theme.FONT_BODY_BOLD,
                     text_color=theme.TEXT_MAIN, anchor="w").pack(fill="x")
        if nota:
            ctk.CTkLabel(caja, text=nota, font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                         anchor="w", justify="left").pack(fill="x", pady=(0, theme.SPACE_1))
        return caja

    def _campo(self, padre, etiqueta: str, valor: str, ancho: int = 320) -> ctk.StringVar:
        fila = ctk.CTkFrame(padre, fg_color="transparent")
        fila.pack(fill="x", pady=1)
        ctk.CTkLabel(fila, text=etiqueta, font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
                     width=ANCHO_ETIQUETA, anchor="w").pack(side="left")
        var = ctk.StringVar(value=valor)
        ctk.CTkEntry(fila, textvariable=var, width=ancho).pack(side="left")
        return var

    def _bloque_informe(self, p: dict) -> None:
        caja = self._seccion("Informe", "El nº y la fecha los pone el cliente; el resto viene "
                                        "del pedido.")
        self._campos["numero"] = self._campo(caja, "Nº de informe (VPR)", p["numero"], 420)
        self._campos["fecha"] = self._campo(caja, "Fecha del informe", p["fecha"], ANCHO_FECHA)
        self._campos["po"] = self._campo(caja, "Nº de pedido del cliente", p["po"])
        self._campos["fecha_po"] = self._campo(caja, "Fecha del pedido", p["fecha_po"],
                                               ANCHO_FECHA)
        self._campos["contractual"] = self._campo(caja, "Entrega contractual", p["contractual"],
                                                  ANCHO_FECHA)
        ctk.CTkLabel(caja, text="Ninguna fecha del informe debe ser posterior a esta.",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                     anchor="w").pack(fill="x", pady=(0, theme.SPACE_1))
        self._campos["prometida"] = self._texto(caja, "Entrega prometida",
                                                p["prometida"], altura=58)
        self._campos["material"] = self._texto(caja, "Descripción del material",
                                               p["material"], altura=100)
        self._campos["lugar"] = self._texto(caja, "Lugar de fabricación e inspección",
                                            p["lugar"], altura=58)

    def _texto(self, padre, etiqueta: str, lineas, altura: int = 90) -> ctk.CTkTextbox:
        fila = ctk.CTkFrame(padre, fg_color="transparent")
        fila.pack(fill="x", pady=1)
        ctk.CTkLabel(fila, text=etiqueta, font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
                     width=ANCHO_ETIQUETA, anchor="nw").pack(side="left", fill="y")
        caja = ctk.CTkTextbox(fila, height=altura, font=theme.FONT_SMALL, wrap="word")
        caja.pack(side="left", fill="x", expand=True)
        caja.insert("1.0", "\n".join(lineas) if isinstance(lineas, list) else str(lineas))
        return caja

    def _bloque_avance(self, p: dict) -> None:
        caja = self._seccion("1 · Avance por áreas",
                             "El % real lo mide el ERP. El planificado sale de las fechas y se "
                             "puede corregir.")
        cab = ctk.CTkFrame(caja, fg_color="transparent")
        cab.pack(fill="x")
        for texto, ancho in (("Área", ANCHO_ETIQUETA), ("Inicio", ANCHO_FECHA),
                             ("Fin", ANCHO_FECHA), ("% plan.", 70), ("% real", 70)):
            ctk.CTkLabel(cab, text=texto, font=theme.FONT_SMALL_BOLD, width=ancho, anchor="w",
                         text_color=theme.TEXT_SUB).pack(side="left", padx=(0, theme.SPACE_2))

        for clave, etiqueta in vpr_service.AREAS:
            linea = p["resumen"][clave]
            fila = ctk.CTkFrame(caja, fg_color="transparent")
            fila.pack(fill="x", pady=1)
            ctk.CTkLabel(fila, text=etiqueta, font=theme.FONT_SMALL, width=ANCHO_ETIQUETA,
                         anchor="w", text_color=theme.TEXT_MAIN).pack(side="left",
                                                                      padx=(0, theme.SPACE_2))
            variables = {}
            for campo, ancho in (("inicio", ANCHO_FECHA), ("fin", ANCHO_FECHA),
                                 ("planificado", 70)):
                var = ctk.StringVar(value=str(linea[campo]))
                ctk.CTkEntry(fila, textvariable=var, width=ancho).pack(side="left",
                                                                       padx=(0, theme.SPACE_2))
                variables[campo] = var
            ctk.CTkLabel(fila, text=f"{linea['real']} %", font=theme.FONT_SMALL_BOLD, width=70,
                         anchor="w", text_color=ui.pct_color(linea["real"])).pack(side="left")
            variables["real"] = linea["real"]
            self._plan[clave] = variables

        ui.button(caja, "Recalcular el planificado con estas fechas", "ghost",
                  command=self._recalcular).pack(anchor="w", pady=(theme.SPACE_1, 0))

    def _recalcular(self) -> None:
        hoy = date.today()
        for variables in self._plan.values():
            variables["planificado"].set(str(vpr_service._planificado(
                variables["inicio"].get(), variables["fin"].get(), hoy)))

    def _bloque_equipos(self, p: dict) -> None:
        caja = self._seccion("2 · Equipos", "Ingeniería, subpedidos, fabricación e inspección "
                                            "medidos equipo a equipo.")
        cab = ctk.CTkFrame(caja, fg_color="transparent")
        cab.pack(fill="x")
        for texto, ancho in (("Grupo", 230), ("Ing.", 55), ("Sub.", 55), ("Fabr.", 55),
                             ("Insp.", 55), ("Entrega prevista", ANCHO_FECHA)):
            ctk.CTkLabel(cab, text=texto, font=theme.FONT_SMALL_BOLD, width=ancho, anchor="w",
                         text_color=theme.TEXT_SUB).pack(side="left", padx=(0, theme.SPACE_2))

        for g in self._datos["grupos"]:
            fila = ctk.CTkFrame(caja, fg_color="transparent")
            fila.pack(fill="x", pady=1)
            ctk.CTkLabel(fila, text=g["nombre"], font=theme.FONT_SMALL, width=230, anchor="w",
                         text_color=theme.TEXT_MAIN).pack(side="left", padx=(0, theme.SPACE_2))
            for clave in ("ingenieria", "subpedidos", "fabricacion", "inspeccion"):
                ctk.CTkLabel(fila, text=f"{g[clave]} %", font=theme.FONT_SMALL, width=55,
                             anchor="w", text_color=ui.pct_color(g[clave])).pack(
                                 side="left", padx=(0, theme.SPACE_2))
            var = ctk.StringVar(value=p["previstas"].get(g["nombre"], p["contractual"]))
            ctk.CTkEntry(fila, textvariable=var, width=ANCHO_FECHA).pack(side="left")
            self._previstas[g["nombre"]] = var

    def _bloque_subpedidos(self) -> None:
        subs = self._datos["subpedidos"]
        caja = self._seccion(f"3 · Subpedidos ({len(subs)})",
                             "Tal como están en Compras; se escriben en el informe.")
        if not subs:
            ctk.CTkLabel(caja, text="Este pedido no tiene subpedidos en el ERP.",
                         font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                         anchor="w").pack(fill="x")
            return
        for s in subs:
            fila = ctk.CTkFrame(caja, fg_color="transparent")
            fila.pack(fill="x", pady=1)
            pendiente = bool(s["pendientes"])
            for texto, ancho in ((s["numero"], 90), (s["proveedor"][:28], 200),
                                 (s["material"][:44], 300), (s["contractual"], ANCHO_FECHA)):
                ctk.CTkLabel(fila, text=texto, font=theme.FONT_SMALL, width=ancho, anchor="w",
                             text_color=theme.TEXT_MAIN).pack(side="left", padx=(0, theme.SPACE_2))
            ctk.CTkLabel(fila, text=s["estado"], font=theme.FONT_SMALL, anchor="w",
                         text_color=theme.RED if pendiente else theme.TEXT_MUTED).pack(
                             side="left")

    def _bloque_textos(self, p: dict) -> None:
        caja = self._seccion("Apartados en texto", "Escritos con lo que dice el ERP; corrige lo "
                                                   "que haga falta antes de generar.")
        for clave, etiqueta in (("subpedidos", "3.1 Subpedidos y acopio"),
                                ("fabricacion", "4 Situación de fabricación"),
                                ("inspeccion", "5 Actividades de inspección"),
                                ("siguiente", "8 Actividades del mes siguiente")):
            self._textos[clave] = self._texto(caja, etiqueta, p["textos"][clave])

    # ── Plantilla y generación ────────────────────────────────────────────────

    def _elegir_plantilla(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Plantilla de VPR del cliente",
            filetypes=[("Documento de Word", "*.docx")],
            initialfile=self._plantilla or "")
        if not ruta:
            return
        if vpr_service.formato_de(ruta) is None:
            ui.toast(self, "Plantilla no reconocida",
                     "Ese Word no es un formulario de VPR de los que se saben rellenar.",
                     kind="error")
            return
        self._plantilla = ruta
        if self._cliente:
            vpr_service.guardar_plantilla(self._cliente, ruta)
        self._refresca_estado()

    def _ajustes(self) -> dict:
        def lineas(caja) -> list:
            return [x for x in caja.get("1.0", "end").splitlines() if x.strip()]

        return {
            "numero": self._campos["numero"].get().strip(),
            "fecha": self._campos["fecha"].get().strip(),
            "po": self._campos["po"].get().strip(),
            "fecha_po": self._campos["fecha_po"].get().strip(),
            "contractual": self._campos["contractual"].get().strip(),
            "vendor": vpr_service.VENDOR,
            "prometida": lineas(self._campos["prometida"]),
            "material": lineas(self._campos["material"]),
            "lugar": lineas(self._campos["lugar"]),
            "resumen": {clave: {"inicio": v["inicio"].get().strip(),
                                "fin": v["fin"].get().strip(),
                                "planificado": v["planificado"].get().strip().rstrip("% "),
                                "real": v["real"]}
                        for clave, v in self._plan.items()},
            "previstas": {nombre: var.get().strip() for nombre, var in self._previstas.items()},
            "textos": {clave: lineas(caja) for clave, caja in self._textos.items()},
        }

    def _avisos(self, ajustes: dict) -> list[str]:
        """Lo que conviene mirar antes de mandarlo: fechas raras o posteriores al pedido."""
        avisos = []
        if not ajustes["numero"]:
            avisos.append("el informe no lleva número")
        tope = ajustes["contractual"]
        from core.services.erp_common import as_date

        limite = as_date(tope)
        for nombre, valor in ajustes["previstas"].items():
            fecha = as_date(valor)
            if valor and not vpr_service.fecha_valida(valor):
                avisos.append(f"«{valor}» ({nombre}) no es una fecha DD-MM-AAAA")
            elif limite and fecha and fecha > limite:
                avisos.append(f"{nombre} promete {valor}, después de la entrega ({tope})")
        return avisos

    def _generar(self) -> None:
        ajustes = self._ajustes()
        avisos = self._avisos(ajustes)
        if avisos and not ui.confirm(self, "Generar el VPR de todas formas",
                                     "· " + "\n· ".join(avisos[:6])):
            return
        pedido = self._datos["pedido"]
        destino = vpr_service.destino_sugerido(pedido, ajustes["numero"])
        if destino is None:
            ui.toast(self, "No se localiza el pedido",
                     f"No encuentro la carpeta 2-Tecnico de {pedido}.", kind="error")
            return
        self.btn_generar.configure(state="disabled", text="Generando…")
        plantilla, datos = self._plantilla, self._datos

        def trabajo():
            try:
                final = vpr_service.generar(plantilla, destino, datos, ajustes)
                self.after(0, lambda: self._fin(final, ""))
            except Exception as exc:  # noqa: BLE001 — se enseña tal cual
                logger.exception("VPR: generar %s", pedido)
                fallo = str(exc)
                self.after(0, lambda: self._fin(None, fallo))
        threading.Thread(target=trabajo, daemon=True).start()

    def _fin(self, destino, error: str) -> None:
        self.btn_generar.configure(state="normal", text="Generar VPR")
        if error:
            ui.toast(self, "VPR · error", error, kind="error")
            return
        ui.toast(self, "VPR generado", f"{destino.name}\n{destino.parent}", kind="success")
        self.lbl_estado.configure(text=f"✓  {destino}")
        try:
            import os

            os.startfile(destino.parent)          # noqa: S606 — abrir la carpeta en el Explorador
        except OSError:
            logger.debug("No se pudo abrir la carpeta del VPR", exc_info=True)
