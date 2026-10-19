"""Cuánto ancho le toca a cada columna de una tabla.

Cada columna tiene un ancho **preferido** (el de diseño) y un **suelo** (lo
mínimo para que lo importante se lea entero). Con sitio de sobra van a su
preferido y las elásticas se reparten el resto; con menos sitio todas encogen a
la vez, cada una en proporción a lo que le sobra sobre su suelo, y el texto
largo se remata con «…» (pasando el ratón se lee entero); y solo si ni con los
suelos cabe, la tabla deja de encoger y aparece el scroll horizontal. Así
ninguna columna se queda fuera de la vista sin avisar, que es lo que pasaba con
los anchos fijos.

El suelo por defecto es lo que mide la cabecera y, del contenido, lo que mide
el valor más largo hasta `LARGO` px: códigos, fechas, estados o cantidades se
leen siempre enteros, y solo un asunto o un título larguísimo se recorta. Si
un valor corto no cabía ni en el ancho de diseño, el de diseño crece hasta él.
"""

from __future__ import annotations

LARGO = 150      # a partir de aquí un texto se puede recortar con «…»
CODIGO = 260     # tope para lo que no es texto libre (códigos, nº de documento)
MINIMO = 36      # ninguna columna baja de esto


def medidas(preferido: int, cabecera: int, contenido: int, fijo: int | None = None,
            largo: int = LARGO) -> tuple[int, int]:
    """(preferido, suelo) de una columna.

    `cabecera` y `contenido` son lo que miden su título y su valor más largo,
    ya con el margen de la celda; `fijo`, un suelo puesto a mano; `largo`, a
    partir de cuánto se deja recortar el contenido (`CODIGO` para una columna
    de códigos, que no se deben cortar).
    """
    preferido = int(preferido)
    if fijo is not None:
        suelo = max(MINIMO, int(fijo))
    else:
        suelo = max(MINIMO, int(cabecera), min(int(contenido), int(largo)))
    return max(preferido, suelo), suelo


def repartir(preferidos: list[int], suelos: list[int], disponible: int) -> list[int]:
    """Anchos que suman como mucho `disponible` (salvo que ni los suelos quepan)."""
    preferidos = [int(p) for p in preferidos]
    suelos = [min(int(s), p) for s, p in zip(suelos, preferidos)]
    total = sum(preferidos)
    if total <= disponible:
        return preferidos
    if sum(suelos) >= disponible:
        return suelos
    holguras = [p - s for p, s in zip(preferidos, suelos)]
    falta = total - disponible
    sobra = sum(holguras)
    anchos = [p - falta * h / sobra for p, h in zip(preferidos, holguras)]
    enteros = [int(a) for a in anchos]          # truncar: nunca se pasa del disponible
    # Lo que se pierde al truncar, a las que más holgura tienen
    resto = disponible - sum(enteros)
    for i in sorted(range(len(enteros)), key=lambda i: -holguras[i])[:max(0, resto)]:
        enteros[i] += 1
    return enteros
