# -*- coding: utf-8 -*-
"""«🤖 Análisis IA» de Correo: desactivado sin clave; con ella, resume el correo
abierto y el análisis se queda al volver a él. Sin buzón ni Anthropic de
verdad: los dos se sustituyen por datos inventados.

    .venv\\Scripts\\python.exe tests\\test_correo_ia.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk  # noqa: E402

from core.services import ia  # noqa: E402
from core.services import inbox as B  # noqa: E402
from gui.views import inbox as V  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


CORREO = {"uid": "7", "subject": "P-99/001 - Comentarios al 99-001-CAL-0001",
          "from": "Cliente <docs@ejemplo.test>", "to": "docs@eipsa.ejemplo.test", "cc": "",
          "date": "2026-11-02T09:00:00+01:00", "plain_body": "",
          "html_body": "<p>Adjuntamos comentarios.</p><p>Rev. B, por favor.</p>"}
OTRO = {**CORREO, "uid": "8", "subject": "Otro correo", "html_body": "<p>Nada</p>"}

# ── El servicio: lo que se le pide a Claude ──────────────────────────────────
p = B.prompt_analisis(CORREO)
ok("P-99/001 - Comentarios al 99-001-CAL-0001" in p and "docs@ejemplo.test" in p,
   "el prompt lleva el asunto y el remitente")
ok("Adjuntamos comentarios." in p and "Rev. B, por favor." in p and "<p>" not in p,
   "y el cuerpo, pasado de HTML a texto")
ok("Cc:" not in p, "sin línea de Cc cuando no hay")
ok(all(x in p for x in ("Resumen:", "Qué piden:", "Referencias:", "Siguiente paso:")),
   "pide las cuatro líneas que se enseñan")
pedido = []
ia.redactar = lambda prompt, **_k: pedido.append(prompt) or "Resumen: comentarios."
ok(B.analizar(CORREO) == "Resumen: comentarios." and pedido == [p],
   "analizar le pasa ese prompt a la IA")

# ── La pantalla ──────────────────────────────────────────────────────────────
B.list_emails = lambda **_k: [{"uid": "7", "subject": CORREO["subject"], "from": CORREO["from"],
                               "date": CORREO["date"], "is_read": True},
                              {"uid": "8", "subject": "Otro correo", "from": CORREO["from"],
                               "date": CORREO["date"], "is_read": True}]
B.get_email_detail = lambda uid, folder="INBOX": dict(CORREO if uid == "7" else OTRO)
B.mark_read = B.mark_unread = lambda *_a, **_k: None
llamadas = []


class HiloEnElSitio:
    """Sin mainloop, Tk no admite que otro hilo le pida pintar (en la app sí):
    aquí el trabajo «de fondo» se hace en el momento y en este hilo."""

    def __init__(self, target=None, daemon=None, **_k):
        self._target = target

    def start(self):
        self._target()


V.threading.Thread = HiloEnElSitio


def esperar(cond, segundos=5.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def textos(w):
    out = []
    for h in w.winfo_children():
        try:
            t = h.cget("text")
        except Exception:  # noqa: BLE001
            t = ""
        if t:
            out.append(str(t))
        out += textos(h)
    return out


root = ctk.CTk()
root.geometry("1280x800")
try:
    # Sin clave: el botón está, pero desactivado
    ia.disponible = lambda: False
    vista = V.InboxView(root)
    vista.pack(fill="both", expand=True)
    ok(esperar(lambda: vista._emails), "la lista se carga")
    vista._open_detail_uid("7")
    ok(esperar(lambda: hasattr(vista, "btn_ia") and vista.btn_ia.winfo_exists()),
       "el detalle se abre con el botón de IA")
    ok(vista.btn_ia.cget("state") == "disabled", "sin clave, desactivado")

    # Con clave: analiza el correo abierto y lo enseña encima del mensaje
    ia.disponible = lambda: True
    B.analizar = lambda d: llamadas.append(d["uid"]) or "Resumen: piden la Rev. B."
    vista._open_detail_uid("7")
    ok(esperar(lambda: vista.btn_ia.winfo_exists() and vista.btn_ia.cget("state") == "normal"),
       "con clave, activo")
    vista.btn_ia.invoke()
    ok(esperar(lambda: "Resumen: piden la Rev. B." in textos(vista._ia_host)),
       f"el análisis aparece en el detalle: {textos(vista._ia_host)}")
    ok(llamadas == ["7"], f"del correo abierto: {llamadas}")

    # Otro correo no lo arrastra; al volver, sigue ahí sin volver a pagarlo
    vista._open_detail_uid("8")
    ok(esperar(lambda: vista._current_uid == "8" and vista._ia_host.winfo_exists()),
       "se abre el otro correo")
    ok(not textos(vista._ia_host), "el otro correo no trae el análisis del primero")
    vista._open_detail_uid("7")
    ok(esperar(lambda: "Resumen: piden la Rev. B." in textos(vista._ia_host)),
       "al volver al primero, el análisis sigue ahí")
    ok(llamadas == ["7"], f"sin llamar otra vez a la IA: {llamadas}")

    # Si la IA no contesta, el botón vuelve y no se pinta nada
    B.analizar = lambda d: None
    vista._open_detail_uid("8")
    esperar(lambda: vista._current_uid == "8" and vista.btn_ia.winfo_exists())
    vista.btn_ia.invoke()
    ok(esperar(lambda: vista.btn_ia.cget("text") == "🤖 Análisis IA"
               and vista.btn_ia.cget("state") == "normal"),
       "sin respuesta, el botón vuelve a estar listo")
    ok(not textos(vista._ia_host), "y no aparece análisis")
finally:
    root.update_idletasks()
    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass

print("FALLOS:", fallos)
