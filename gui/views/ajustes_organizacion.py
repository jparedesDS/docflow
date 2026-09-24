"""Ajustes ▸ Organización — los datos de tu empresa, a mano.

El código no lleva ni un nombre, ni un correo, ni un cliente: el repositorio es
público. Todo eso se rellena aquí y se guarda en `state/organizacion.json`, que
se queda en tu máquina. Con la app recién instalada estas tablas están vacías y
la app funciona igual —lo que sabe el ERP sigue saliendo del ERP—; esto es el
respaldo, los nombres legibles y a quién se avisa.

Las tablas se agrupan en cuatro: quién eres (equipo), para quién trabajas
(clientes y pedidos), qué dicen los portales, y a quién se escribe.
"""

import logging

import customtkinter as ctk

from core import organizacion
from gui import theme
from gui.widgets import ui
from gui.widgets.mapa import EquipoEditor, ListaEditor, MapaEditor
from gui.widgets.scrollframe import ScrollFrame

logger = logging.getLogger(__name__)


class OrganizacionMixin:
    """La pestaña. Va aparte porque Ajustes ya es larga de por sí."""

    def _build_organizacion(self, parent) -> None:
        self.tabs_org = ui.tabview(parent)
        self.tabs_org.pack(fill="both", expand=True)
        ui.lazy_tabs(self.tabs_org, {
            "Equipo": self._org_equipo,
            "Clientes y pedidos": self._org_clientes,
            "Portales": self._org_portales,
            "Correo": self._org_correo,
        })

    # ── Piezas ───────────────────────────────────────────────────────────────

    @staticmethod
    def _org_scroll(parent) -> ScrollFrame:
        s = ScrollFrame(parent)
        s.pack(fill="both", expand=True)
        return s

    def _org_guardar(self, parent, texto: str, tablas) -> None:
        """Botón de guardar de cada pestaña. `tablas()` da lo que hay que salvar."""
        fila = ctk.CTkFrame(parent, fg_color="transparent")
        fila.pack(fill="x", pady=(theme.SPACE_4, theme.SPACE_2))

        def guardar():
            try:
                organizacion.guardar(**tablas())
            except Exception as exc:  # noqa: BLE001
                logger.exception("Organización: no se pudo guardar")
                ui.toast(self, "No se pudo guardar", str(exc), kind="error")
                return
            ui.toast(self, "Guardado", texto, kind="success")

        ui.button(fila, "Guardar", "primary", size="sm", height=36,
                  command=guardar).pack(side="left")
        ctk.CTkLabel(fila, text=f"Se guarda en {organizacion.ORGANIZACION_FILE}",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED).pack(
            side="left", padx=theme.SPACE_3)

    # ── Equipo ───────────────────────────────────────────────────────────────

    def _org_equipo(self, parent) -> None:
        s = self._org_scroll(parent)
        ui.section_header(s, "Equipo").pack(fill="x", pady=(theme.SPACE_2, theme.SPACE_1))
        ctk.CTkLabel(s, text="Quién es quién. Las iniciales son la clave que usa el resto de la "
                             "app —el responsable de un documento, quien recibe el aviso de una "
                             "devolución, la cuenta con la que se entra—, y el primer correo es "
                             "al que se le escribe.",
                     font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED, anchor="w",
                     justify="left", wraplength=780).pack(fill="x", pady=(0, theme.SPACE_2))
        self.org_equipo = EquipoEditor(s, datos=organizacion.equipo, alto=260)
        self.org_equipo.pack(fill="both", expand=True)
        self._org_guardar(s, "Equipo guardado. Reinicia para que lo vea toda la app.",
                          lambda: {"equipo": self.org_equipo.valores()})

    # ── Clientes y pedidos ───────────────────────────────────────────────────

    def _org_clientes(self, parent) -> None:
        s = self._org_scroll(parent)
        ui.section_header(s, "Clientes por PO").pack(fill="x", pady=(theme.SPACE_2, theme.SPACE_1))
        self.org_clientes = MapaEditor(
            s, "PO (5 primeros dígitos)", "Cliente o proyecto", organizacion.clientes,
            ayuda="Lo que convierte un PO como «1000100010» en un nombre que se entiende. "
                  "Se mira por los cinco primeros dígitos.", alto=170)
        self.org_clientes.pack(fill="both", expand=True)

        ui.section_header(s, "Responsable por pedido").pack(
            fill="x", pady=(theme.SPACE_4, theme.SPACE_1))
        self.org_pedidos = MapaEditor(
            s, "Nº de pedido", "Correo del responsable", organizacion.pedidos,
            ayuda="Respaldo: lo normal es que el comercial salga del ERP. Esto cubre los "
                  "pedidos antiguos y aquellos cuyo comercial no tiene correo en el ERP.",
            alto=170)
        self.org_pedidos.pack(fill="both", expand=True)

        self._org_guardar(s, "Clientes y pedidos guardados.",
                          lambda: {"clientes": self.org_clientes.valores(),
                                   "pedidos": self.org_pedidos.valores()})

    # ── Portales ─────────────────────────────────────────────────────────────

    def _org_portales(self, parent) -> None:
        s = self._org_scroll(parent)
        ui.section_header(s, "Lo que dice el portal → tu pedido").pack(
            fill="x", pady=(theme.SPACE_2, theme.SPACE_1))
        self.org_portales = MapaEditor(
            s, "PO, flujo o paquete", "Nº de pedido", organizacion.portales,
            ayuda="Vale para PRODOC (Wood), SENDOC, ACONEX y Document Space: cada uno manda "
                  "su clave y aquí se dice a qué pedido tuyo corresponde.", alto=150)
        self.org_portales.pack(fill="both", expand=True)

        ui.section_header(s, "Referencias de AYESA").pack(
            fill="x", pady=(theme.SPACE_4, theme.SPACE_1))
        self.org_refs = MapaEditor(
            s, "Referencia del asunto", "Nº PO", organizacion.refs,
            ayuda="AYESA numera a su manera y su referencia no está en el ERP: con el PO ya se "
                  "resuelve el pedido. Una línea por pedido nuevo de ese portal.", alto=120)
        self.org_refs.pack(fill="both", expand=True)

        ui.section_header(s, "Familia de producto").pack(
            fill="x", pady=(theme.SPACE_4, theme.SPACE_1))
        self.org_materiales = MapaEditor(
            s, "Clave del portal", "Familia (REF016, REF034…)", organizacion.materiales,
            ayuda="El correo del portal no dice de qué es el pedido; esto lo rellena.",
            alto=120)
        self.org_materiales.pack(fill="both", expand=True)

        self._org_guardar(s, "Portales guardados.",
                          lambda: {"portales": self.org_portales.valores(),
                                   "refs": self.org_refs.valores(),
                                   "materiales": self.org_materiales.valores()})

    # ── Correo ───────────────────────────────────────────────────────────────

    def _org_correo(self, parent) -> None:
        s = self._org_scroll(parent)
        ui.section_header(s, "Destinatarios fijos").pack(
            fill="x", pady=(theme.SPACE_2, theme.SPACE_1))
        self.org_para = ListaEditor(s, "Para", organizacion.correo_para,
                                    ayuda="Quién recibe siempre las reclamaciones.")
        self.org_para.pack(fill="x", pady=(0, theme.SPACE_2))
        self.org_cc = ListaEditor(s, "Copia", organizacion.correo_cc)
        self.org_cc.pack(fill="x", pady=(0, theme.SPACE_2))
        self.org_direccion = ListaEditor(
            s, "Dirección", organizacion.correo_direccion,
            ayuda="Solo en el escalado urgente (tercer aviso).")
        self.org_direccion.pack(fill="x")

        ui.section_header(s, "Técnico en copia por tipo de documento").pack(
            fill="x", pady=(theme.SPACE_4, theme.SPACE_1))
        self.org_tipos = MapaEditor(
            s, "Tipo (CER, PRC…)", "Correo", organizacion.tipos_correo, alto=120)
        self.org_tipos.pack(fill="both", expand=True)

        ui.section_header(s, "Comerciales del ERP").pack(
            fill="x", pady=(theme.SPACE_4, theme.SPACE_1))
        self.org_comerciales = MapaEditor(
            s, "Iniciales EN EL ERP", "Correo", organizacion.comerciales,
            ayuda="Respaldo por si el ERP no contesta. OJO: las iniciales del ERP no tienen "
                  "por qué ser las de tu equipo.", alto=120)
        self.org_comerciales.pack(fill="both", expand=True)

        ui.section_header(s, "Reasignaciones").pack(
            fill="x", pady=(theme.SPACE_4, theme.SPACE_1))
        self.org_reasignados = MapaEditor(
            s, "Iniciales EN EL ERP", "Correo de quien los lleva ahora",
            organizacion.reasignados,
            ayuda="Esto sí manda sobre el ERP: alguien que ya no está y cuyos pedidos ha "
                  "cogido otra persona.", alto=100)
        self.org_reasignados.pack(fill="both", expand=True)

        ui.section_header(s, "Iniciales por correo").pack(
            fill="x", pady=(theme.SPACE_4, theme.SPACE_1))
        self.org_iniciales = MapaEditor(
            s, "Correo", "Iniciales", organizacion.iniciales,
            ayuda="Para la columna «Responsable» de los documentos.", alto=100)
        self.org_iniciales.pack(fill="both", expand=True)

        self._org_guardar(s, "Correo y comerciales guardados.",
                          lambda: {"correo_para": self.org_para.valores(),
                                   "correo_cc": self.org_cc.valores(),
                                   "correo_direccion": self.org_direccion.valores(),
                                   "tipos_correo": self.org_tipos.valores(),
                                   "comerciales": self.org_comerciales.valores(),
                                   "reasignados": self.org_reasignados.valores(),
                                   "iniciales": self.org_iniciales.valores()})
