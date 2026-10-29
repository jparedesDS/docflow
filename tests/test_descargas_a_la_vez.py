# -*- coding: utf-8 -*-
"""Dos ventanas de la app no descargan la misma devolución a la vez.

Puede haber dos abiertas (una en una sesión de escritorio remoto que se quedó
desconectada) y las dos lanzan la descarga automática cada 10 minutos: el
10571-TRSEI-V-15258 se bajó dos veces en el mismo segundo. Ahora la descarga
va de una en una entre procesos y, con el turno, si la otra ya la bajó, solo
se reparte. No toca ningún portal ni el buzón: todo simulado.

    .venv\\Scripts\\python.exe tests\\test_descargas_a_la_vez.py
"""
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.services import portal_downloads as pd  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


tmp = Path(tempfile.mkdtemp(prefix="descargas_"))
pd.PORTAL_DOWNLOADS_FILE = str(tmp / "portal_downloads.json")

# ── Dos hilos: una detrás de otra ────────────────────────────────────────────
tramos = []


def descargar_lento(uid, folder="INBOX", *, session=None):
    ini = time.monotonic()
    time.sleep(0.3)
    tramos.append((ini, time.monotonic()))
    return {"uid": uid}


real = pd._descargar
pd._descargar = descargar_lento
hilos = [threading.Thread(target=pd.download_for_email, args=(str(i),)) for i in range(2)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
tramos.sort()
ok(len(tramos) == 2 and tramos[0][1] <= tramos[1][0], f"una detrás de otra, sin solaparse: {tramos}")

# ── Dos procesos: el segundo espera a que el primero acabe ──────────────────
otro = subprocess.Popen(
    [sys.executable, "-c",
     "import sys, time; sys.path.insert(0, r'%s')\n"
     "from core.services import portal_downloads as pd\n"
     "pd.PORTAL_DOWNLOADS_FILE = r'%s'\n"
     "with pd._de_una_en_una():\n"
     "    print('dentro', flush=True); time.sleep(1.5)\n" % (RAIZ, pd.PORTAL_DOWNLOADS_FILE)],
    stdout=subprocess.PIPE, text=True)
ok(otro.stdout.readline().strip() == "dentro", "el otro proceso tiene el turno")
t0 = time.monotonic()
with pd._de_una_en_una():
    espera = time.monotonic() - t0
otro.wait(timeout=20)
ok(espera >= 0.8, f"y este espera a que lo suelte: {espera:.2f}s")

# ── Con el turno: si la otra ventana ya la bajó, solo se reparte ────────────
pd._descargar = real
from core.services import transmittal  # noqa: E402

transmittal.preview_email = lambda uid, folder="INBOX": {"subject": "x", "from": "y", "documents": []}
pd.describe_email = lambda frm, subject: {"portal": "egesdoc", "code": "X-1", "po": "1"}
pd.portal_ready = lambda portal: (True, "")
pd._pedido_de = lambda docs: "P-99/001"
pd.is_downloaded = lambda code: True
repartida = []
pd.archive_pending = lambda uid, folder="INBOX", session=None: repartida.append(uid) or {"already": True}
pd.imap_service.fetch_raw = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no se descarga"))
res = pd.download_for_email("7")
ok(res == {"already": True} and repartida == ["7"], f"ya descargada por otra: solo se reparte: {res}")

print("FALLOS:", fallos)
