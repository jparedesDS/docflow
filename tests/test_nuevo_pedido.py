# -*- coding: utf-8 -*-
"""La pantalla «Nuevo pedido»: que esté entera y en el orden de los pasos.

    .venv\\Scripts\\python.exe tests\\test_nuevo_pedido.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from gui.views.apertura import AperturaView
from gui.widgets.scrollframe import ScrollFrame

fallos = 0


def ok(cond, msg):
    global fallos
    etiqueta = "  OK   " if cond else "  FALLO"
    if not cond:
        fallos += 1
    # La consola de Windows es cp1252: un ✓ o un emoji del texto la tumbarían.
    print(etiqueta, str(msg).encode("cp1252", "replace").decode("cp1252"))


def textos(widget) -> list[str]:
    """Los textos de los widgets de dentro, en orden de colocación.

    Cada CTkLabel repite su texto en el Label de Tk que lleva dentro, y al
    aplanar sale pegado al del padre: se quitan los repetidos seguidos.
    """
    def recoger(w):
        for hijo in w.winfo_children():
            try:
                t = hijo.cget("text")
            except Exception:  # noqa: BLE001
                t = ""
            if t:
                yield str(t)
            yield from recoger(hijo)

    salida: list[str] = []
    for t in recoger(widget):
        if not salida or salida[-1] != t:
            salida.append(t)
    return salida


root = ctk.CTk()
root.geometry("1280x800")
try:
    vista = AperturaView(root)
    vista.pack(fill="both", expand=True)
    root.update()

    # ── Nada se ha quedado por el camino al reordenar ────────────────────────
    ATRIBUTOS = [
        "btn_create", "btn_locate", "btn_open", "lbl_cm_status", "txt_cm_cc",
        "txt_cm_to", "txt_result", "var_base_dir", "var_cliente",
        "var_copy_template", "var_create_if_missing", "var_do_comm_matrix",
        "var_do_planning", "var_do_subfolders", "var_do_vddl", "var_erp_tpl",
        "var_f_entrada", "var_f_prevista", "var_material", "var_overwrite",
        "var_pedido", "var_planning_tpl", "var_sref", "var_subfolders",
        "var_suffix", "var_template_dir", "var_vddl_lang",
        "_subfolder_checkboxes",
    ]
    faltan = [a for a in ATRIBUTOS if not hasattr(vista, a)]
    ok(not faltan, f"están los {len(ATRIBUTOS)} widgets y variables de la vista: faltan {faltan}")

    # ── Los cuatro pasos, numerados y en orden ───────────────────────────────
    todos = textos(vista)
    pasos = [t for t in todos if t[:2] in ("1 ", "2 ", "3 ", "4 ") and "·" in t]
    ok(pasos == ["1 · Datos del pedido", "2 · Qué se va a crear",
                 "3 · Subcarpetas de 2-Tecnico", "4 · Destinatarios de reclamaciones"],
       f"los pasos salen numerados y en orden: {pasos}")

    # ── La botonera y el resultado, fuera del scroll ─────────────────────────
    def dentro_del_scroll(widget) -> bool:
        w = widget
        while w is not None and w is not vista:
            if isinstance(w, ScrollFrame):
                return True
            w = w.master
        return False

    ok(not dentro_del_scroll(vista.btn_create),
       "«Procesar pedido» no se va con el scroll")
    ok(not dentro_del_scroll(vista.txt_result), "ni el resultado")
    ok(not dentro_del_scroll(vista.btn_open), "ni «Abrir carpeta del pedido»")
    ok(dentro_del_scroll(vista.btn_locate),
       "«Localizar pedido» va dentro, con los datos del pedido que rellena")

    # ── El resultado está debajo de los pasos, no en medio ───────────────────
    root.update_idletasks()
    ok(vista.txt_result.winfo_rooty() > vista.btn_locate.winfo_rooty(),
       "el resultado queda por debajo del formulario, no entre las tarjetas")

    # ── Las subcarpetas, todas y marcadas ────────────────────────────────────
    from core.services import apertura as servicio
    ok(len(vista.var_subfolders) == len(servicio.SUBFOLDER_CATALOG),
       f"hay un check por subcarpeta del catálogo: {len(vista.var_subfolders)}")
    ok(all(v.get() for v in vista.var_subfolders.values()),
       "y vienen todas marcadas")
    vista._set_all_subfolders(False)
    ok(not any(v.get() for v in vista.var_subfolders.values()), "«Ninguna» las desmarca")
    vista._set_all_subfolders(True)
    ok(all(v.get() for v in vista.var_subfolders.values()), "«Todas» las vuelve a marcar")

    # El idioma cambia los títulos que se verán en el VDDL
    vista.var_vddl_lang.set("en")
    vista._refresh_subfolder_labels()
    ingles = [ck.cget("text") for ck in vista._subfolder_checkboxes.values()]
    vista.var_vddl_lang.set("es")
    vista._refresh_subfolder_labels()
    espanol = [ck.cget("text") for ck in vista._subfolder_checkboxes.values()]
    ok(ingles != espanol, "el selector de idioma cambia lo que dicen los checks")

    # ── Los destinatarios, con su botón de contactos ─────────────────────────
    vista._set_cm_textboxes(["a@eipsa.es"], ["b@eipsa.es", "c@eipsa.es"])
    vista._refresh_cm_status()
    ok("1" in vista.lbl_cm_status.cget("text") and "2" in vista.lbl_cm_status.cget("text"),
       f"el contador de destinatarios cuenta: {vista.lbl_cm_status.cget('text')!r}")
    ok("👥" in todos, "y los cuadros TO/CC tienen el botón de contactos")

    # ── Limpiar deja el formulario como estaba ───────────────────────────────
    vista.var_pedido.set("P-26-999")
    vista.var_cliente.set("CLIENTE")
    vista._on_clear()
    ok(vista.var_pedido.get() == "P-26-" and not vista.var_cliente.get(),
       f"«Limpiar formulario» lo deja en blanco: {vista.var_pedido.get()!r}")
finally:
    root.update_idletasks()
    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
