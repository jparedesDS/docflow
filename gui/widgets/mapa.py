"""Editor de tablas de dos columnas, para los datos de la organización.

Casi todo lo que la app necesita saber de tu empresa es una correspondencia:
este PO es de este cliente, este pedido lo lleva esta persona, lo que dice el
portal es este pedido nuestro. Aquí se editan esas tablas sin tocar un fichero
a mano: se escribe arriba, se pulsa «Añadir», y al guardar se vuelca entera.

`MapaEditor` es la tabla clave → valor y `ListaEditor` la lista suelta (los
destinatarios fijos de un correo).
"""

import customtkinter as ctk

from gui import theme
from gui.widgets import ui
from gui.widgets.table import DataTable


def _entry(parent, placeholder: str, width: int = 200):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, width=width,
                        height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
                        fg_color=theme.BG_INPUT, border_color=theme.BORDER,
                        text_color=theme.TEXT_MAIN, font=theme.FONT_BODY)


class MapaEditor(ctk.CTkFrame):
    """Tabla clave → valor con añadir, cambiar y quitar.

    `on_change(dict)` se llama con la tabla entera cada vez que cambia algo, y
    quien la use decide cuándo guardarla.
    """

    def __init__(self, master, col_clave: str, col_valor: str, datos: dict | None = None,
                 on_change=None, ayuda: str = "", alto: int = 200, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change
        self._datos: dict[str, str] = dict(datos or {})

        if ayuda:
            ctk.CTkLabel(self, text=ayuda, font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                         anchor="w", justify="left", wraplength=760).pack(fill="x",
                                                                         pady=(0, theme.SPACE_2))

        self.tabla = DataTable(self, columns=[col_clave, col_valor], height=alto)
        self.tabla.pack(fill="both", expand=True)
        self.tabla.tree.bind("<<TreeviewSelect>>", self._al_elegir)

        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", pady=(theme.SPACE_2, 0))
        self.ent_clave = _entry(fila, col_clave, width=190)
        self.ent_clave.pack(side="left", padx=(0, theme.SPACE_2))
        self.ent_valor = _entry(fila, col_valor, width=280)
        self.ent_valor.pack(side="left", padx=(0, theme.SPACE_2))
        ui.button(fila, "Añadir", "outline", size="sm", command=self._anadir).pack(
            side="left", padx=(0, theme.SPACE_2))
        ui.button(fila, "Quitar", "outline", size="sm", text_color=theme.RED,
                  command=self._quitar).pack(side="left")
        self.lbl_cuenta = ctk.CTkLabel(fila, text="", font=theme.FONT_SMALL,
                                       text_color=theme.TEXT_MUTED)
        self.lbl_cuenta.pack(side="right")

        self._pintar()

    # ── Datos ────────────────────────────────────────────────────────────────

    def valores(self) -> dict:
        return dict(self._datos)

    def poner(self, datos: dict) -> None:
        self._datos = dict(datos or {})
        self._pintar()

    def _aviso(self) -> None:
        self.lbl_cuenta.configure(text=f"{len(self._datos)} línea(s)")
        if self._on_change:
            self._on_change(self.valores())

    def _pintar(self) -> None:
        self.tabla.clear()
        for clave in sorted(self._datos):
            self.tabla.add_row([clave, self._datos[clave]], iid=clave)
        self.lbl_cuenta.configure(text=f"{len(self._datos)} línea(s)")

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _al_elegir(self, _e=None) -> None:
        iid = self.tabla.selected_iid()
        if iid is None:
            return
        clave, valor = self.tabla.row_values(iid)[:2]
        self.ent_clave.delete(0, "end")
        self.ent_clave.insert(0, clave)
        self.ent_valor.delete(0, "end")
        self.ent_valor.insert(0, valor)

    def _anadir(self) -> None:
        clave = self.ent_clave.get().strip()
        valor = self.ent_valor.get().strip()
        if not clave:
            ui.toast(self, "Falta la clave", "Escribe la primera columna.", kind="warn")
            return
        self._datos[clave] = valor
        self._pintar()
        self._aviso()
        self._limpiar()

    def _limpiar(self) -> None:
        self.ent_clave.delete(0, "end")
        self.ent_valor.delete(0, "end")

    def _quitar(self) -> None:
        clave = (self.tabla.selected_iid() or self.ent_clave.get().strip())
        if clave in self._datos:
            del self._datos[clave]
            self._pintar()
            self._aviso()
        self._limpiar()


class EquipoEditor(ctk.CTkFrame):
    """Quién es quién: iniciales, nombre y sus correos.

    Las iniciales son la clave con la que el resto de la app se refiere a cada
    persona (el responsable de un documento, quien recibe un aviso, la cuenta
    con la que entra). El primer correo es el que se usa para escribirle.
    """

    def __init__(self, master, datos: dict | None = None, on_change=None, alto: int = 220, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change
        self._datos: dict[str, dict] = {k: dict(v) for k, v in (datos or {}).items()}

        self.tabla = DataTable(self, columns=["Iniciales", "Nombre", "Correos"], height=alto)
        self.tabla.pack(fill="both", expand=True)
        self.tabla.set_columns_width({"Iniciales": 90, "Nombre": 200})
        self.tabla.tree.bind("<<TreeviewSelect>>", self._al_elegir)

        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", pady=(theme.SPACE_2, 0))
        self.ent_ini = _entry(fila, "JP", width=80)
        self.ent_ini.pack(side="left", padx=(0, theme.SPACE_2))
        self.ent_nombre = _entry(fila, "Nombre y apellido", width=180)
        self.ent_nombre.pack(side="left", padx=(0, theme.SPACE_2))
        self.ent_correos = _entry(fila, "correo@tuempresa.com, otro@tuempresa.com", width=280)
        self.ent_correos.pack(side="left", fill="x", expand=True, padx=(0, theme.SPACE_2))
        ui.button(fila, "Añadir", "outline", size="sm", command=self._anadir).pack(
            side="left", padx=(0, theme.SPACE_2))
        ui.button(fila, "Quitar", "outline", size="sm", text_color=theme.RED,
                  command=self._quitar).pack(side="left")
        self._pintar()

    def valores(self) -> dict:
        return {k: dict(v) for k, v in self._datos.items()}

    def _pintar(self) -> None:
        self.tabla.clear()
        for ini in sorted(self._datos):
            info = self._datos[ini]
            self.tabla.add_row([ini, info.get("nombre", ""),
                                ", ".join(info.get("emails") or [])], iid=ini)

    def _al_elegir(self, _e=None) -> None:
        iid = self.tabla.selected_iid()
        if iid is None:
            return
        ini, nombre, correos = self.tabla.row_values(iid)[:3]
        for entrada, valor in ((self.ent_ini, ini), (self.ent_nombre, nombre),
                               (self.ent_correos, correos)):
            entrada.delete(0, "end")
            entrada.insert(0, valor)

    def _anadir(self) -> None:
        ini = self.ent_ini.get().strip().upper()
        if not ini:
            ui.toast(self, "Faltan las iniciales", "Son la clave de cada persona.", kind="warn")
            return
        correos = [c.strip() for c in self.ent_correos.get().replace(";", ",").split(",")
                   if c.strip()]
        self._datos[ini] = {"nombre": self.ent_nombre.get().strip() or ini, "emails": correos}
        self._pintar()
        if self._on_change:
            self._on_change(self.valores())
        self._limpiar()

    def _limpiar(self) -> None:
        for entrada in (self.ent_ini, self.ent_nombre, self.ent_correos):
            entrada.delete(0, "end")

    def _quitar(self) -> None:
        ini = (self.tabla.selected_iid() or self.ent_ini.get().strip().upper())
        if ini in self._datos:
            del self._datos[ini]
            self._pintar()
            if self._on_change:
                self._on_change(self.valores())
        self._limpiar()


class ListaEditor(ctk.CTkFrame):
    """Una lista de correos en una caja: uno por línea, o separados por comas."""

    def __init__(self, master, etiqueta: str, valores=None, ayuda: str = "", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=etiqueta, font=theme.FONT_SMALL_BOLD,
                     text_color=theme.TEXT_SUB, anchor="w").pack(fill="x")
        if ayuda:
            ctk.CTkLabel(self, text=ayuda, font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                         anchor="w").pack(fill="x")
        self.ent = _entry(self, "alguien@tuempresa.com, otro@tuempresa.com", width=520)
        self.ent.pack(fill="x", pady=(theme.SPACE_1, 0))
        self.poner(valores or [])

    def valores(self) -> list[str]:
        crudo = self.ent.get().replace(";", ",")
        return [c.strip() for c in crudo.split(",") if c.strip()]

    def poner(self, valores) -> None:
        self.ent.delete(0, "end")
        self.ent.insert(0, ", ".join(valores or []))
