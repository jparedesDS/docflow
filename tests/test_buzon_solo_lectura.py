# -*- coding: utf-8 -*-
"""Los buzones se abren en solo lectura (EXAMINE). Solo escriben las dos cosas
que se marcan a propósito: abrir un correo en Correo (y su «no leído») y el
aviso de una devolución ya enviada. Ofertas, que lee buzones de comercial, no
marca nada. Sin servidor: un IMAP falso que apunta cómo se abre cada carpeta.

    .venv\\Scripts\\python.exe tests\\test_buzon_solo_lectura.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import imap as I  # noqa: E402
from core.services import inbox as B  # noqa: E402
from core.services import ofertas as O  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


CORREO = (b"Subject: P-99/001 prueba\r\nFrom: alguien@ejemplo.test\r\n"
          b"Date: Mon, 02 Nov 2026 09:00:00 +0100\r\n\r\nHola")


class ImapFalso:
    aperturas: list[tuple[str, bool]] = []      # (carpeta, readonly)
    escrituras: list[tuple] = []

    def __init__(self, *_a, **_k):
        self._readonly = True

    def login(self, *_a):
        return "OK", [b""]

    def select(self, carpeta="INBOX", readonly=False):
        ImapFalso.aperturas.append((carpeta, readonly))
        self._readonly = readonly
        return "OK", [b"1"]

    def search(self, *_a):
        return "OK", [b"1"]

    def fetch(self, _uid, _partes):
        return "OK", [(b"1 (FLAGS (\\Seen) BODY[] {10}", CORREO), b")"]

    def store(self, *args):
        if self._readonly:
            raise RuntimeError("STORE en una carpeta abierta con EXAMINE")
        ImapFalso.escrituras.append(args)
        return "OK", [b""]

    def close(self):
        pass

    def logout(self):
        pass


I.imaplib.IMAP4_SSL = ImapFalso
B.imaplib.IMAP4_SSL = ImapFalso


def abiertas_en_escritura():
    return [c for c, solo_lectura in ImapFalso.aperturas if not solo_lectura]


# ── Leer no abre nada en escritura ───────────────────────────────────────────
I.list_all()
I.list_unread()
I.list_since(7)
I.fetch_email("1")
I.fetch_raw("1")
B.list_emails()
B.get_email_detail("1")
ok(len(ImapFalso.aperturas) >= 7, f"se abrió el buzón en cada lectura: {ImapFalso.aperturas}")
ok(not abiertas_en_escritura(), f"y siempre en solo lectura: {ImapFalso.aperturas}")
ok(not ImapFalso.escrituras, "sin escribir nada")

# ── Las dos marcas que se mantienen sí escriben ──────────────────────────────
ImapFalso.aperturas.clear()
I.mark_as_read("1")           # Correo al abrir · Devoluciones tras el aviso
B.mark_unread("1")            # «Marcar no leído» de Correo
ok(len(abiertas_en_escritura()) == 2 and len(ImapFalso.escrituras) == 2,
   f"marcar leído / no leído abre en escritura y escribe: {ImapFalso.aperturas}")

# ── Ofertas no marca nada ────────────────────────────────────────────────────
ok(not hasattr(O, "mark_read"), "Ofertas ya no tiene «marcar como leído»")

print("FALLOS:", fallos)
