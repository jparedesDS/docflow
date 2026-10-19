"""Vista Usuarios y permisos — solo para el administrador.

A la izquierda las cuentas; a la derecha la ficha de la elegida, con cada
sección del menú (mismo nombre e icono, agrupadas por departamento) y su
nivel: «Sin acceso» (no le sale en el menú), «Ver» (entra y consulta) o
«Gestionar» (además envía, procesa y modifica).

Atajos para no ir sección a sección: el nivel de todo un departamento, el de
todas a la vez, o copiar los permisos de otra cuenta. Nada se guarda hasta
pulsar «Guardar cambios»; la persona ve el menú nuevo la próxima vez que entra.
"""

from __future__ import annotations

import logging
from datetime import datetime

import customtkinter as ctk
from tkinter import messagebox

from core import auth, session
from gui import navegacion, theme
from gui.widgets import ui
from gui.widgets.scrollframe import ScrollFrame

logger = logging.getLogger(__name__)

NIVELES = [("none", "Sin acceso"), ("ver", "Ver"), ("gestionar", "Gestionar")]
_TEXTO = dict(NIVELES)
_NIVEL = {texto: clave for clave, texto in NIVELES}
_COLOR = {"none": theme.BORDER_STRONG, "ver": theme.BLUE, "gestionar": theme.GREEN}
LISTA_ANCHO = 260


def resumen(permisos: dict) -> str:
    """«Ve 7 · Gestiona 3» (contando solo las secciones que existen)."""
    n = {k: 0 for k, _ in NIVELES}
    for clave in auth.SECTION_KEYS:
        n[permisos.get(clave, "none") if permisos.get(clave) in n else "none"] += 1
    partes = []
    if n["ver"]:
        partes.append(f"Ve {n['ver']}")
    if n["gestionar"]:
        partes.append(f"Gestiona {n['gestionar']}")
    return " · ".join(partes) or "Sin acceso a ninguna sección"


def permisos_completos(permisos: dict | None) -> dict:
    """Un nivel para cada sección; lo que falte o no se entienda, sin acceso."""
    permisos = permisos or {}
    return {k: permisos.get(k) if permisos.get(k) in _TEXTO else "none" for k in auth.SECTION_KEYS}


def ultimo_acceso(iso: str | None) -> str:
    if not iso:
        return "Todavía no ha entrado"
    try:
        return "Último acceso: " + datetime.fromisoformat(iso).astimezone().strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return "Último acceso: —"


def _entry(parent, value="", placeholder="", show=None):
    kw = dict(placeholder_text=placeholder, height=theme.HEIGHT_INPUT, corner_radius=theme.RADIUS_MD,
              fg_color=theme.BG_INPUT, border_color=theme.BORDER, text_color=theme.TEXT_MAIN,
              font=theme.FONT_SMALL)
    if show:
        kw["show"] = show
    e = ctk.CTkEntry(parent, **kw)
    if value:
        e.insert(0, value)
    return e


def _clic(widget, accion) -> None:
    """Toda la tarjeta (y lo que lleva dentro) responde al clic."""
    widget.bind("<Button-1>", lambda _e: accion(), add="+")
    for hijo in widget.winfo_children():
        _clic(hijo, accion)


class UsuariosView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_PAGE, corner_radius=0, **kwargs)
        self._usuarios: list[dict] = []
        self._sel: str | None = None          # iniciales de la cuenta abierta
        self._nueva = False                   # la ficha es la de una cuenta nueva
        self._borrador: dict = {}             # permisos tal como están en pantalla
        self._segs: dict[str, ctk.CTkSegmentedButton] = {}
        self._segs_grupo: list[tuple[ctk.CTkSegmentedButton, list[str]]] = []

        cab = ui.page_header(self, "Usuarios y permisos",
                             "Quién entra en DocFlow y qué secciones ve cada cuenta",
                             icon="👥", help_key="usuarios")
        if not session.is_admin():
            ui.empty_state(self, "Solo el administrador gestiona las cuentas", icon="🔒")
            return
        ui.button(cab.actions, "+ Nueva cuenta", "primary", size="sm",
                  command=self._nueva_cuenta).pack(side="right")

        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=theme.SPACE_6, pady=(theme.SPACE_3, theme.SPACE_5))
        cuerpo.grid_columnconfigure(1, weight=1)
        cuerpo.grid_rowconfigure(0, weight=1)

        izq = ctk.CTkFrame(cuerpo, fg_color="transparent", width=LISTA_ANCHO)
        izq.grid(row=0, column=0, sticky="nsw", padx=(0, theme.SPACE_4))
        izq.grid_propagate(False)
        izq.pack_propagate(False)
        self.lbl_cuentas = ctk.CTkLabel(izq, text="", font=theme.FONT_LABEL,
                                        text_color=theme.TEXT_MUTED, anchor="w")
        self.lbl_cuentas.pack(fill="x", pady=(0, theme.SPACE_1))
        self.lista = ScrollFrame(izq)
        self.lista.pack(fill="both", expand=True)

        self.ficha = ctk.CTkFrame(cuerpo, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_LG,
                                  border_width=1, border_color=theme.BORDER)
        self.ficha.grid(row=0, column=1, sticky="nsew")

        self._cargar()

    # ── Datos ────────────────────────────────────────────────────────────────

    def _cargar(self, elegir: str | None = None) -> None:
        usuarios = auth.list_users()
        usuarios.sort(key=lambda u: (not u.get("is_admin"), (u.get("nombre") or u["initials"]).lower()))
        self._usuarios = usuarios
        n = len(usuarios)
        self.lbl_cuentas.configure(text=f"{n} CUENTA{'S' if n != 1 else ''}")
        inis = [u["initials"] for u in usuarios]
        if elegir not in inis:
            elegir = self._sel if self._sel in inis else None
        if elegir is None:
            elegir = next((u["initials"] for u in usuarios if not u.get("is_admin")), inis[0] if inis else None)
        self._abrir(elegir)

    def _usuario(self, ini: str | None) -> dict | None:
        return next((u for u in self._usuarios if u["initials"] == ini), None)

    # ── Lista de cuentas ─────────────────────────────────────────────────────

    def _pintar_lista(self) -> None:
        for w in self.lista.winfo_children():
            w.destroy()
        for u in self._usuarios:
            self._tarjeta(u)
        if self._nueva:
            nueva = ctk.CTkFrame(self.lista, fg_color=theme.ACCENT_SOFT, corner_radius=theme.RADIUS_MD,
                                 border_width=1, border_color=theme.ACCENT)
            nueva.pack(fill="x", pady=(0, theme.SPACE_2))
            ctk.CTkLabel(nueva, text="+  Cuenta nueva (sin guardar)", font=theme.FONT_SMALL_BOLD,
                         text_color=theme.TEXT_MAIN, anchor="w").pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_3)

    def _tarjeta(self, u: dict) -> None:
        elegida = u["initials"] == self._sel and not self._nueva
        card = ctk.CTkFrame(self.lista, fg_color=theme.ACCENT_SOFT if elegida else theme.BG_CARD,
                            corner_radius=theme.RADIUS_MD, border_width=1,
                            border_color=theme.ACCENT if elegida else theme.BORDER)
        card.pack(fill="x", pady=(0, theme.SPACE_2))
        fila = ctk.CTkFrame(card, fg_color="transparent")
        fila.pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_2)
        av = ctk.CTkFrame(fila, width=34, height=34, corner_radius=17, fg_color=ui.avatar_color(u["initials"]))
        av.pack(side="left", padx=(0, theme.SPACE_2))
        av.pack_propagate(False)
        ctk.CTkLabel(av, text=u["initials"], font=theme.font(11, "bold"),
                     text_color=theme.TEXT_ON_ACCENT).pack(expand=True)
        info = ctk.CTkFrame(fila, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info, text=u.get("nombre") or u["initials"], font=theme.FONT_SMALL_BOLD,
                     text_color=theme.TEXT_MAIN, anchor="w").pack(fill="x")
        if u.get("is_admin"):
            detalle, color = "Administrador · acceso total", theme.ACCENT
        else:
            detalle, color = resumen(u.get("permisos") or {}), theme.TEXT_MUTED
        ctk.CTkLabel(info, text=detalle, font=theme.FONT_TINY, text_color=color, anchor="w").pack(fill="x")
        if u.get("must_change_password") and not u.get("is_admin"):
            ctk.CTkLabel(info, text="Debe cambiar la contraseña al entrar", font=theme.FONT_TINY,
                         text_color=theme.AMBER, anchor="w").pack(fill="x")
        _clic(card, lambda i=u["initials"]: self._pedir(i))

    def _pedir(self, ini: str) -> None:
        if (ini != self._sel or self._nueva) and self._puede_salir():
            self._abrir(ini)

    def _nueva_cuenta(self) -> None:
        if self._nueva or not self._puede_salir():
            return
        self._nueva = True
        self._borrador = {k: "none" for k in auth.SECTION_KEYS}
        self._pintar_lista()
        self._pintar_ficha(None)

    def _puede_salir(self) -> bool:
        if not self._hay_cambios():
            return True
        return ui.confirm(self, "Cambios sin guardar",
                          "Hay cambios sin guardar en esta cuenta. ¿Descartarlos?")

    def _abrir(self, ini: str | None) -> None:
        self._nueva = False
        self._sel = ini
        u = self._usuario(ini)
        self._borrador = permisos_completos((u or {}).get("permisos"))
        self._pintar_lista()
        self._pintar_ficha(u)

    # ── Ficha de la cuenta ───────────────────────────────────────────────────

    def _pintar_ficha(self, u: dict | None) -> None:
        for w in self.ficha.winfo_children():
            w.destroy()
        self._segs, self._segs_grupo = {}, []
        self._u = u
        if u is None and not self._nueva:
            ui.empty_state(self.ficha, "No hay cuentas", "Crea una con «+ Nueva cuenta».", icon="👥")
            return
        pad = theme.SPACE_5

        # Pie fijo (se empaqueta antes que el contenido para que nunca se corte)
        pie = ctk.CTkFrame(self.ficha, fg_color="transparent")
        pie.pack(side="bottom", fill="x", padx=pad, pady=(theme.SPACE_2, pad))
        ctk.CTkFrame(self.ficha, height=1, fg_color=theme.BORDER).pack(side="bottom", fill="x")

        cont = ScrollFrame(self.ficha, fg_color=theme.BG_CARD)
        cont.pack(fill="both", expand=True, padx=2, pady=2)

        # Cabecera
        cab = ctk.CTkFrame(cont, fg_color="transparent")
        cab.pack(fill="x", padx=pad, pady=(pad, theme.SPACE_3))
        if u is not None:
            av = ctk.CTkFrame(cab, width=48, height=48, corner_radius=24, fg_color=ui.avatar_color(u["initials"]))
            av.pack(side="left", padx=(0, theme.SPACE_3))
            av.pack_propagate(False)
            ctk.CTkLabel(av, text=u["initials"], font=theme.font(15, "bold"),
                         text_color=theme.TEXT_ON_ACCENT).pack(expand=True)
        txt = ctk.CTkFrame(cab, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(txt, text="Cuenta nueva" if u is None else (u.get("nombre") or u["initials"]),
                     font=theme.FONT_HEADING, text_color=theme.TEXT_MAIN, anchor="w").pack(fill="x")
        if u is not None:
            linea = f"{u['initials']}  ·  {ultimo_acceso(u.get('last_login'))}"
            ctk.CTkLabel(txt, text=linea, font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                         anchor="w").pack(fill="x")
            if not u.get("is_admin"):
                acciones = ctk.CTkFrame(txt, fg_color="transparent")
                acciones.pack(fill="x", pady=(theme.SPACE_2, 0))
                ui.button(acciones, "Restablecer contraseña", "outline", size="xs", font=theme.FONT_TINY_BOLD,
                          text_color=theme.TEXT_SUB, command=self._restablecer).pack(side="left")
                ui.button(acciones, "Eliminar cuenta", "outline", size="xs", font=theme.FONT_TINY_BOLD,
                          text_color=theme.RED, border_color=theme.RED,
                          command=self._eliminar).pack(side="left", padx=(theme.SPACE_2, 0))

        # Datos
        datos = ctk.CTkFrame(cont, fg_color="transparent")
        datos.pack(fill="x", padx=pad)
        datos.grid_columnconfigure((1, 3), weight=1)
        self.e_ini = self.e_pwd = None
        fila = 0
        if u is None:
            self.e_ini = self._campo(datos, fila, 0, "Iniciales", "", "p. ej. AC")
            self.e_pwd = self._campo(datos, fila, 2, "Contraseña", "", "vacía = la de por defecto", show="•")
            fila += 1
        self.e_nombre = self._campo(datos, fila, 0, "Nombre", (u or {}).get("nombre", ""), "Nombre y apellido")
        self.e_email = self._campo(datos, fila, 2, "Email", (u or {}).get("email", ""), "opcional")
        if u is None:
            ctk.CTkLabel(datos, text="Con la contraseña vacía entra con la de por defecto y el programa le "
                                     "obliga a cambiarla la primera vez.",
                         font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, anchor="w", justify="left",
                         wraplength=560).grid(row=fila + 1, column=0, columnspan=4, sticky="w", pady=(2, 0))

        if u is not None and u.get("is_admin"):
            aviso = ctk.CTkFrame(cont, fg_color=theme.ACCENT_SOFT, corner_radius=theme.RADIUS_MD)
            aviso.pack(fill="x", padx=pad, pady=(theme.SPACE_4, 0))
            ctk.CTkLabel(aviso, text="Administrador: ve y gestiona todas las secciones, Ajustes y esta "
                                     "misma. Sus permisos no se pueden recortar.",
                         font=theme.FONT_SMALL, text_color=theme.TEXT_MAIN, anchor="w", justify="left",
                         wraplength=600).pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_3)
        else:
            self._pintar_permisos(cont, pad)

        self._pintar_pie(pie, u)
        self._refrescar()

    def _campo(self, parent, fila, col, texto, valor, placeholder, show=None):
        ctk.CTkLabel(parent, text=texto, font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
                     anchor="w").grid(row=fila, column=col, sticky="w", padx=(0 if col == 0 else theme.SPACE_4,
                                                                                theme.SPACE_2), pady=3)
        e = _entry(parent, valor, placeholder, show=show)
        e.grid(row=fila, column=col + 1, sticky="ew", pady=3)
        e.bind("<KeyRelease>", lambda _e: self._refrescar(), add="+")
        return e

    def _pintar_permisos(self, cont, pad) -> None:
        ui.section_header(cont, "Secciones que ve").pack(fill="x", padx=pad, pady=(theme.SPACE_5, theme.SPACE_1))
        ctk.CTkLabel(cont, text="Ver: entra y consulta.   Gestionar: además envía, procesa y modifica.   "
                                "Sin acceso: no le sale en el menú.",
                     font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, anchor="w", justify="left",
                     wraplength=380).pack(fill="x", padx=pad)

        barra = ctk.CTkFrame(cont, fg_color="transparent")
        barra.pack(fill="x", padx=pad, pady=(theme.SPACE_3, theme.SPACE_2))
        ctk.CTkLabel(barra, text="Todas:", font=theme.FONT_SMALL_BOLD,
                     text_color=theme.TEXT_SUB).pack(side="left", padx=(0, theme.SPACE_2))
        for clave, texto in NIVELES:
            ui.button(barra, texto, "outline", size="xs", width=86, font=theme.FONT_TINY_BOLD,
                      text_color=theme.TEXT_SUB,
                      command=lambda c=clave: self._poner(auth.SECTION_KEYS, c)).pack(side="left", padx=(0, 4))
        otras = [u for u in self._usuarios
                 if not u.get("is_admin") and (self._nueva or u["initials"] != self._sel)]
        if otras:
            copia = ctk.CTkFrame(cont, fg_color="transparent")
            copia.pack(fill="x", padx=pad, pady=(0, theme.SPACE_2))
            nombres = {f"{u.get('nombre') or u['initials']} ({u['initials']})": u for u in otras}
            menu = ctk.CTkOptionMenu(copia, values=list(nombres), width=240, height=28, font=theme.FONT_TINY,
                                     dropdown_font=theme.FONT_SMALL, fg_color=theme.BG_INPUT,
                                     button_color=theme.BORDER_STRONG, button_hover_color=theme.TEXT_MUTED,
                                     text_color=theme.TEXT_MAIN,
                                     command=lambda n: self._copiar(nombres[n], menu))
            menu.set("Copiar de otra cuenta…")
            menu.pack(side="left")
        self.lbl_resumen = ctk.CTkLabel(cont, text="", font=theme.FONT_SMALL_BOLD,
                                        text_color=theme.TEXT_MAIN, anchor="w")
        self.lbl_resumen.pack(fill="x", padx=pad, pady=(0, theme.SPACE_2))

        for titulo, items in navegacion.grupos_de_permisos():
            claves = [it["key"] for it in items if it["key"] in auth.SECTION_KEYS]
            if not claves:
                continue
            caja = ctk.CTkFrame(cont, fg_color=theme.BG_PAGE, corner_radius=theme.RADIUS_MD,
                                border_width=1, border_color=theme.BORDER)
            caja.pack(fill="x", padx=pad, pady=(0, theme.SPACE_2))
            cab = ctk.CTkFrame(caja, fg_color="transparent")
            cab.pack(fill="x", padx=theme.SPACE_3, pady=(theme.SPACE_2, 0))
            ctk.CTkLabel(cab, text=titulo.upper(), font=theme.FONT_LABEL,
                         text_color=theme.TEXT_MUTED, anchor="w").pack(side="left")
            if len(claves) > 1:
                seg = self._selector(cab, lambda texto, cs=claves: self._poner(cs, _NIVEL[texto]), pequeno=True)
                seg.pack(side="right")
                self._segs_grupo.append((seg, claves))
            filas = [self._fila_seccion(caja, it) for it in items if it["key"] in claves]
            filas[-1].pack_configure(pady=(2, theme.SPACE_2))

    def _fila_seccion(self, caja, it: dict) -> ctk.CTkFrame:
        fila = ctk.CTkFrame(caja, fg_color="transparent")
        fila.pack(fill="x", padx=theme.SPACE_3, pady=2)
        ctk.CTkLabel(fila, text=it.get("icon", "•"), width=24, font=theme.FONT_BODY,
                     text_color=theme.TEXT_SUB).pack(side="left")
        ctk.CTkLabel(fila, text=it["label"], font=theme.FONT_BODY, text_color=theme.TEXT_MAIN,
                     anchor="w").pack(side="left", padx=(theme.SPACE_1, 0))
        seg = self._selector(fila, lambda texto, k=it["key"]: self._poner([k], _NIVEL[texto]))
        seg.pack(side="right")
        self._segs[it["key"]] = seg
        return fila

    def _selector(self, parent, accion, pequeno: bool = False) -> ctk.CTkSegmentedButton:
        return ctk.CTkSegmentedButton(
            parent, values=[t for _, t in NIVELES], command=accion,
            height=24 if pequeno else 28, font=theme.FONT_TINY if pequeno else theme.FONT_SMALL,
            corner_radius=theme.RADIUS_SM, fg_color=theme.BG_INPUT,
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.BG_INPUT, unselected_hover_color=theme.BORDER,
            text_color=theme.TEXT_MAIN)

    def _pintar_pie(self, pie, u: dict | None) -> None:
        # Los botones primero: con la ventana estrecha encoge el aviso, no ellos
        self.btn_guardar = ui.button(pie, "Crear cuenta" if u is None else "Guardar cambios", "primary",
                                     size="lg", command=self._guardar)
        self.btn_guardar.pack(side="right")
        ui.button(pie, "Descartar" if u is not None else "Cancelar", "secondary", size="lg", width=100,
                  text_color=theme.TEXT_SUB, command=self._descartar).pack(side="right", padx=(0, theme.SPACE_2))
        self.lbl_cambios = ctk.CTkLabel(pie, text="", font=theme.FONT_TINY, text_color=theme.TEXT_MUTED,
                                        anchor="w", justify="left", wraplength=220)
        self.lbl_cambios.pack(side="left", fill="x", expand=True, padx=(0, theme.SPACE_2))

    # ── Cambios en pantalla ──────────────────────────────────────────────────

    def _poner(self, claves, nivel: str) -> None:
        for k in claves:
            self._borrador[k] = nivel
        self._refrescar()

    def _copiar(self, otra: dict, menu) -> None:
        self._borrador = permisos_completos(otra.get("permisos"))
        menu.set("Copiar de otra cuenta…")
        self._refrescar()
        ui.toast(self, "Permisos copiados", f"Los de {otra.get('nombre') or otra['initials']}. "
                                            "Revisa y pulsa «Guardar cambios».", kind="info")

    def _refrescar(self) -> None:
        """Pone cada selector como está el borrador y avisa de lo pendiente."""
        for k, seg in self._segs.items():
            nivel = self._borrador.get(k, "none")
            seg.set(_TEXTO[nivel])
            seg.configure(selected_color=_COLOR[nivel], selected_hover_color=_COLOR[nivel])
        for seg, claves in self._segs_grupo:
            niveles = {self._borrador.get(k, "none") for k in claves}
            nivel = niveles.pop() if len(niveles) == 1 else None
            seg.set(_TEXTO[nivel] if nivel else "")
            if nivel:
                seg.configure(selected_color=_COLOR[nivel], selected_hover_color=_COLOR[nivel])
        if getattr(self, "lbl_resumen", None) is not None and self._segs:
            try:
                self.lbl_resumen.configure(text=resumen(self._borrador))
            except Exception:  # noqa: BLE001 — la ficha de admin no lo tiene
                pass
        if getattr(self, "btn_guardar", None) is None:
            return
        cambios = self._hay_cambios()
        self.btn_guardar.configure(state="normal" if (cambios or self._nueva) else "disabled")
        if self._nueva:
            texto = "No existe hasta que pulses\n«Crear cuenta»."
        elif cambios:
            texto = "● Cambios sin guardar.\nSe aplican cuando vuelva a entrar."
        else:
            texto = "Sin cambios."
        self.lbl_cambios.configure(text=texto, text_color=theme.AMBER if cambios else theme.TEXT_MUTED)

    def _hay_cambios(self) -> bool:
        if self._nueva:
            return any(v != "none" for v in self._borrador.values()) or any(
                e is not None and e.winfo_exists() and e.get().strip()
                for e in (self.e_ini, self.e_nombre, self.e_email, self.e_pwd))
        u = getattr(self, "_u", None)
        if u is None:
            return False
        try:
            if self.e_nombre.get().strip() != (u.get("nombre") or "").strip():
                return True
            if self.e_email.get().strip() != (u.get("email") or "").strip():
                return True
        except Exception:  # noqa: BLE001 — la ficha ya no existe
            return False
        return not u.get("is_admin") and self._borrador != permisos_completos(u.get("permisos"))

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _guardar(self) -> None:
        nombre, email = self.e_nombre.get().strip(), self.e_email.get().strip()
        if self._nueva:
            ini = self.e_ini.get().strip().upper()
            ok, err = auth.create_user(ini, nombre, email, password=self.e_pwd.get().strip() or None,
                                       permisos=dict(self._borrador))
            if not ok:
                messagebox.showerror("No se pudo crear", err, parent=self)
                return
            ui.toast(self, "Cuenta creada", f"{nombre or ini} ({ini}) · {resumen(self._borrador)}", kind="success")
            self._nueva = False
            self._cargar(elegir=ini)
            return
        u = self._u
        permisos = None if u.get("is_admin") else dict(self._borrador)
        ok, err = auth.update_user(u["initials"], nombre=nombre or u["initials"], email=email, permisos=permisos)
        if not ok:
            messagebox.showerror("No se pudo guardar", err, parent=self)
            return
        ui.toast(self, "Guardado", f"{nombre or u['initials']}: los cambios se verán en su próximo acceso.",
                 kind="success")
        self._cargar(elegir=u["initials"])

    def _descartar(self) -> None:
        if self._nueva:
            self._nueva = False
        self._abrir(self._sel)

    def _restablecer(self) -> None:
        UserPasswordDialog(self, self._u, on_done=lambda: self._cargar(elegir=self._sel))

    def _eliminar(self) -> None:
        u = self._u
        if not ui.confirm(self, "Eliminar cuenta",
                          f"¿Eliminar la cuenta de {u.get('nombre') or u['initials']} ({u['initials']})?\n\n"
                          "Dejará de poder entrar en DocFlow."):
            return
        ok, err = auth.delete_user(u["initials"])
        if not ok:
            messagebox.showerror("No se pudo eliminar", err, parent=self)
            return
        ui.toast(self, "Cuenta eliminada", u["initials"], kind="success")
        self._sel = None
        self._cargar()


class UserPasswordDialog(ctk.CTkToplevel):
    """Poner una contraseña nueva a una cuenta; la tendrá que cambiar al entrar."""

    def __init__(self, master, user, on_done=None):
        super().__init__(master, fg_color=theme.BG_PAGE)
        self._user = user
        self._on_done = on_done
        self.title(f"Restablecer contraseña · {user['initials']}")
        self.geometry("440x220")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        ctk.CTkLabel(self, text=f"Contraseña nueva para {user.get('nombre') or user['initials']}",
                     font=theme.font(14, "bold"), text_color=theme.TEXT_MAIN).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(self, text="Mínimo 6 caracteres. Tendrá que cambiarla la próxima vez que entre.",
                     font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, wraplength=400,
                     justify="left").pack(anchor="w", padx=20, pady=(0, 8))
        self.e = _entry(self, placeholder="contraseña nueva", show="•")
        self.e.pack(fill="x", padx=20)
        self.e.focus_set()
        self.e.bind("<Return>", lambda _e: self._save())
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=20)
        ui.button(foot, "Cancelar", "secondary", size="lg", text_color=theme.TEXT_SUB,
                  command=self.destroy).pack(side="right", padx=(8, 0))
        ui.button(foot, "Guardar", "primary", size="lg", command=self._save).pack(side="right")

    def _save(self) -> None:
        ok, err = auth.reset_password(self._user["initials"], self.e.get().strip())
        if not ok:
            messagebox.showerror("Error", err, parent=self)
            return
        ui.toast(self.master, "Contraseña restablecida",
                 f"{self._user['initials']} deberá cambiarla al entrar.", kind="success")
        if self._on_done:
            self._on_done()
        self.destroy()
