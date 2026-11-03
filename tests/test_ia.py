# -*- coding: utf-8 -*-
"""La IA de los informes (core.services.ia) sin gastar nada: un cliente falso
de Anthropic que contesta lo que le digamos y apunta cómo se le llamó.

    .venv\\Scripts\\python.exe tests\\test_ia.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from core.services import ia  # noqa: E402
from core.services import weekly_summary as W  # noqa: E402
from core.services.interactive_report import comun as C  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


class ClienteFalso:
    """Lo mínimo de anthropic.Anthropic: messages.create."""

    def __init__(self, respuesta=None, error=None):
        self.llamadas = []
        self._respuesta, self._error = respuesta, error
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.llamadas.append(kw)
        if self._error:
            raise self._error
        return self._respuesta


def respuesta(*bloques, stop="end_turn"):
    return NS(content=list(bloques), stop_reason=stop)


PENSADO = NS(type="thinking", thinking="", signature="firma")
TEXTO = NS(type="text", text="  La semana va bien.  ")

# ── La clave se lee en el momento (guardarla en Ajustes vale sin reiniciar) ─
from core import credentials  # noqa: E402

leer_real, cliente_real = credentials.get, ia._cliente
credentials.get = lambda k, env_fallback=None: "  guardada-ahora  " if k == "anthropic_api_key" else ""
ok(ia.clave() == "guardada-ahora", f"la clave recién guardada se usa ya: {ia.clave()!r}")
credentials.get = leer_real
real = cliente_real("clave-falsa")
ok(real.timeout == ia.TIEMPO_MAX and real.max_retries == 2,
   f"con tiempo máximo, para que una red atascada no lo cuelgue: {real.timeout}, {real.max_retries}")

cliente = None
ia._cliente = lambda _key: cliente
ia.clave = lambda: "clave-de-prueba"           # nunca una de verdad

# ── Sin clave no se llama a nada ─────────────────────────────────────────────
cliente = ClienteFalso(respuesta(TEXTO))
ia.clave = lambda: ""
ok(ia.redactar("hola") is None and not cliente.llamadas, "sin clave, ni se intenta")
ok(not ia.disponible(), "y la IA consta como no disponible")
ia.clave = lambda: "clave-de-prueba"
ok(ia.disponible(), "con clave, sí")

# ── Haiku 5.5 razona primero: el texto se lee por tipo, no del primer bloque ─
cliente = ClienteFalso(respuesta(PENSADO, TEXTO))
ok(ia.redactar("resume") == "La semana va bien.",
   "el texto sale aunque la respuesta empiece por el razonamiento")
kw = cliente.llamadas[0]
ok(kw["model"] == "claude-haiku-5-5", f"con el Haiku actual: {kw['model']}")
ok(kw["output_config"] == {"effort": "low"}, f"esfuerzo bajo: {kw.get('output_config')}")
ok(kw["max_tokens"] >= 1024, f"con margen para pensar y escribir: {kw['max_tokens']}")
ok(not {"temperature", "top_p", "top_k", "thinking"} & set(kw),
   f"sin parámetros que este modelo rechaza: {sorted(kw)}")
ok(kw["messages"] == [{"role": "user", "content": "resume"}], "y el prompt tal cual, sin prefill")

# ── Lo que no es una respuesta entera da None (y el informe pone la suya) ────
for nombre, r in [("un rechazo", respuesta(TEXTO, stop="refusal")),
                  ("cortado por max_tokens", respuesta(PENSADO, TEXTO, stop="max_tokens")),
                  ("solo razonamiento", respuesta(PENSADO, stop="max_tokens")),
                  ("vacía", respuesta())]:
    cliente = ClienteFalso(r)
    ok(ia.redactar("x") is None, f"{nombre} → texto de reserva")

# ── Ningún fallo de la API tumba el informe ──────────────────────────────────
peticion = anthropic._base_client.httpx.Request("POST", "https://ejemplo.test/v1/messages")
for nombre, error in [("sin conexión", anthropic.APIConnectionError(request=peticion)),
                      ("algo raro", RuntimeError("boom"))]:
    cliente = ClienteFalso(error=error)
    ok(ia.redactar("x") is None, f"{nombre} → texto de reserva")

# ── Los dos sitios que la usan ───────────────────────────────────────────────
cliente = ClienteFalso(respuesta(PENSADO, TEXTO))
ok(C._ask_haiku("x") == "La semana va bien.", "los informes interactivos reciben el texto")
datos = {"fecha": "02-11-2026", "total": 1, "pendientes": 0, "criticos": 0, "riesgo": 0,
         "a_vencer_3d": 0}
W._build_ai_prompt = lambda d: "prompt"
W._fallback_paragraph = lambda d: "Párrafo de reserva."
ok(W._generate_ai_paragraph(datos) == "La semana va bien.", "y el resumen ejecutivo también")
cliente = ClienteFalso(respuesta(stop="refusal"))
ok(W._generate_ai_paragraph(datos) == "Párrafo de reserva.", "sin texto, el de reserva")
ok(C._ask_haiku("x") is None, "y el interactivo recibe None para poner el suyo")

print("FALLOS:", fallos)
