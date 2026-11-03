"""IA — los párrafos que Claude redacta en los informes, en un solo sitio.

Es opcional: sin clave (Ajustes ▸ IA, o ANTHROPIC_API_KEY en el .env) no se
llama a nada y quien pide el texto pone el suyo de reserva. Lo mismo si la
llamada falla o el modelo no contesta: `redactar` devuelve None y el informe
sale igual, con el párrafo de reserva.

Modelo: Claude Haiku 5.5, el más barato (unos $0,10 / $0,50 por millón de
tokens de entrada / salida). Razona antes de contestar, así que:
  · la respuesta puede empezar por bloques de razonamiento: el texto se lee
    por tipo de bloque, no del primero (con `content[0].text` caería siempre
    al texto de reserva sin avisar);
  · ese razonamiento cuenta en `max_tokens`: se deja margen;
  · esfuerzo bajo: es un párrafo, no hace falta pensar más.
Sin `temperature`, `top_p` ni prefill: este modelo los rechaza.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MODELO = "claude-haiku-5-5"
ESFUERZO = "low"
MAX_TOKENS = 2048      # el párrafo y el razonamiento que haga antes


def clave() -> str:
    from core.config import ANTHROPIC_API_KEY
    return (ANTHROPIC_API_KEY or "").strip()


def disponible() -> bool:
    """¿Hay clave para usar la IA? (Sin ella no se intenta nada.)"""
    return bool(clave())


def _cliente(api_key: str):
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def redactar(prompt: str, max_tokens: int = MAX_TOKENS) -> str | None:
    """El texto que escribe Claude para `prompt`, o None si no hay clave, falla
    la llamada o no contesta entero (rechazo, se queda sin tokens): quien llama
    pone entonces su párrafo de reserva."""
    api_key = clave()
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("IA: falta el paquete anthropic; se usa el texto de reserva")
        return None
    try:
        respuesta = _cliente(api_key).messages.create(
            model=MODELO,
            max_tokens=max_tokens,
            output_config={"effort": ESFUERZO},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        logger.warning("IA: la clave de Anthropic no es válida; se usa el texto de reserva")
        return None
    except anthropic.RateLimitError:
        logger.warning("IA: límite de uso de Anthropic alcanzado; se usa el texto de reserva")
        return None
    except anthropic.APIConnectionError as exc:
        logger.warning("IA: sin conexión con Anthropic (%s); se usa el texto de reserva", exc)
        return None
    except anthropic.APIStatusError as exc:
        logger.warning("IA: Anthropic respondió %s (%s); se usa el texto de reserva",
                       exc.status_code, getattr(exc, "message", exc))
        return None
    except Exception as exc:  # noqa: BLE001 — un informe nunca debe caerse por la IA
        logger.warning("IA: fallo inesperado (%s); se usa el texto de reserva", exc)
        return None

    texto = "".join(b.text for b in (respuesta.content or [])
                    if getattr(b, "type", "") == "text").strip()
    motivo = getattr(respuesta, "stop_reason", None)
    if motivo == "refusal":
        logger.warning("IA: el modelo no quiso contestar; se usa el texto de reserva")
        return None
    if not texto:
        logger.warning("IA: respuesta sin texto (stop_reason=%s); se usa el texto de reserva", motivo)
        return None
    if motivo == "max_tokens":
        # Un párrafo cortado a medias en un informe queda peor que el de reserva
        logger.warning("IA: el texto llegó al tope de %d tokens; se usa el texto de reserva",
                       max_tokens)
        return None
    return texto
