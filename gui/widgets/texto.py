"""Texto en widgets de Tk «a pelo» (Canvas, Label) que tienen que verse como los
de CustomTkinter: la misma fuente a la misma escala, y el «…» del que no cabe.

Una sola copia para la tabla, las casillas, la lista de DocuSign y el
botón-icono: antes cada uno tenía la suya y ya empezaban a diferir.
"""
from __future__ import annotations

import tkinter.font as tkfont

import customtkinter as ctk


def escala_de(widget) -> float:
    """La escala con que CustomTkinter agranda los widgets (1.25 a 125 %)."""
    try:
        return ctk.ScalingTracker.get_widget_scaling(widget)
    except Exception:  # noqa: BLE001
        return 1.0


def fuente_ctk(fuente, widget) -> tkfont.Font:
    """La fuente de una tupla del tema (familia, tamaño[, "bold"]) tal como la
    pinta CustomTkinter: en píxeles (tamaño negativo) por la escala. Pasada tal
    cual a Tk, el tamaño se lee en puntos y sale un tercio más grande."""
    familia, tam = fuente[:2]
    peso = "bold" if any("bold" in str(x) for x in fuente[2:]) else "normal"
    return tkfont.Font(family=familia, size=-round(abs(tam) * escala_de(widget)), weight=peso)


def cortar(texto: str, ancho: int, fuente) -> str:
    """El texto que cabe en `ancho` píxeles, rematado con «…» si hace falta
    (el prefijo más largo que entra; «…» solo si no entra nada)."""
    if ancho <= 10 or not texto or fuente.measure(texto) <= ancho:
        return texto
    bajo, alto = 0, len(texto)
    while bajo < alto:
        medio = (bajo + alto + 1) // 2
        if fuente.measure(texto[:medio].rstrip() + "…") <= ancho:
            bajo = medio
        else:
            alto = medio - 1
    return (texto[:bajo].rstrip() + "…") if bajo else "…"
