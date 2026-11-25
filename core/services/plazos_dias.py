"""Días de Plazos: calendario laboral, qué suministros no cuentan y los días
laborables de cada paso. Lo usan los dos Excel de Plazos (`seguimiento_excel`
y `plazos_fabrica_excel`).

Días laborables: sin sábados, domingos, festivos (nacionales y de la Comunidad
de Madrid) ni agosto, que la empresa cierra. Un pedido activado el 29/07 y
pasado a fábrica el 02/09 cuenta 4 días, no 35.

No cuentan los suministros «R» (regularizaciones: en el ERP o, si el ERP no la
puso, en el nombre de su carpeta) ni los anulados en el ERP.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

from core.services.seguimiento import PASOS_PERSONA, TRAMOS, _dia, _persona, _vale, resumen

# Festivos que no salen de las reglas fijas: los que la Comunidad de Madrid
# pone o traslada cada año. Revisar con el calendario oficial al cambiar de año.
FESTIVOS_AÑO = {
    2024: [(7, 25, "Santiago Apóstol")],
    2025: [(7, 25, "Santiago Apóstol")],
    2026: [(11, 2, "Todos los Santos (trasladado)"), (12, 7, "Constitución (trasladado)")],
}
FIJOS = [(1, 1, "Año Nuevo"), (1, 6, "Reyes"), (5, 1, "Fiesta del Trabajo"), (5, 2, "Comunidad de Madrid"),
         (10, 12, "Fiesta Nacional"), (11, 1, "Todos los Santos"), (12, 6, "Constitución"),
         (12, 8, "Inmaculada"), (12, 25, "Navidad")]


def pascua(año: int) -> date:
    """Domingo de Pascua (algoritmo de Meeus/Butcher, calendario gregoriano)."""
    a, b, c = año % 19, año // 100, año % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(año, mes, dia)


def no_laborables(años) -> dict[date, str]:
    """{día: motivo} de los festivos y de todo agosto de esos años (sin fines de semana: ya no cuentan)."""
    out: dict[date, str] = {}
    for año in sorted(set(años)):
        domingo = pascua(año)
        lista = FIJOS + FESTIVOS_AÑO.get(año, [])
        for mes, dia, motivo in lista:
            out[date(año, mes, dia)] = motivo
        out[domingo - timedelta(days=3)] = "Jueves Santo"
        out[domingo - timedelta(days=2)] = "Viernes Santo"
        d = date(año, 8, 1)
        while d.month == 8:
            out.setdefault(d, "Vacaciones de agosto")
            d += timedelta(days=1)
    return {d: m for d, m in sorted(out.items()) if d.weekday() < 5}


def laborables(desde: date, hasta: date, cerrado) -> int:
    """Días laborables en (desde, hasta], como restar fechas; 0 si `hasta` no es posterior."""
    n, d = 0, desde
    while d < hasta:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in cerrado:
            n += 1
    return n


def fuera(f: dict) -> str:
    """Por qué un suministro no cuenta: «R» (regularización), «anulado» o "" si cuenta.

    Regularización: acaba en «R» en el ERP o, si el ERP no la puso, en el nombre de
    su carpeta (`seguimiento_carpetas.regularizaciones`)."""
    if (f.get("pedido") or "").strip().upper().endswith("R") or f.get("regularizacion"):
        return "R"
    return "anulado" if f.get("anulado") else ""


def pendiente(f: dict) -> bool:
    """Sin planos y todavía en marcha: sin enviar, sin cerrar y sin fabricar."""
    return not (f["hitos"]["envio"]["fecha"] or f.get("cerrado") or (f.get("porc_taller") or 0) >= 99
                or f.get("estado") == "fabricado_sin_planos")


def calendario(datos: dict, hoy: date | None = None) -> dict[date, str]:
    """Los días no laborables de todos los años que tocan los pedidos, hasta hoy."""
    hoy = hoy or (datos.get("generado") or datetime.now()).date()
    años = {hoy.year}
    for f in datos.get("filas") or []:
        for h in f["hitos"].values():
            d = _dia(h.get("fecha"))
            if d:
                años.add(d.year)
    return no_laborables(range(min(años), max(años) + 1))


def quitar(datos: dict) -> tuple[dict, dict]:
    """Los datos sin regularizaciones ni anulados (resumen recalculado) y cuántos se quitaron."""
    quitados = {"R": 0, "anulado": 0}
    filas = []
    for f in datos["filas"]:
        motivo = fuera(f)
        if motivo:
            quitados[motivo] += 1
        else:
            filas.append(f)
    cola = [c for c in datos.get("cola") or [] if not fuera(c)]
    return {**datos, "filas": filas, "resumen": resumen(filas), "cola": cola}, quitados


def laborables_tramo(f: dict, tramo: str, cerrado) -> int | None:
    """Los días laborables de un paso, si cuenta (las mismas reglas que `seguimiento._vale`)."""
    if _vale(f, tramo) is None:
        return None
    h = f["hitos"]
    desde_h, hasta_h = TRAMOS[tramo]
    # Sin el correo de la orden de compra, Compras cuenta desde la activación (como en `seguimiento`)
    ini = h["activacion"] if tramo == "compras_pedir" and not h["oc"]["fecha"] else h[desde_h]
    a, b = _dia(ini["fecha"]), _dia(h[hasta_h]["fecha"])
    return laborables(a, b, cerrado) if a and b else None


def mediana_laborables(filas: list[dict], tramo: str, cerrado) -> int | None:
    xs = [x for x in (laborables_tramo(f, tramo, cerrado) for f in filas) if x is not None]
    return round(statistics.median(xs)) if xs else None


def espera(f: dict, hoy: date, cerrado, normal: int | None) -> tuple[int, bool] | None:
    """(días laborables esperando los planos, ¿con retraso?) de un pedido en marcha sin planos; None si no.

    Retraso: lleva más que `normal` (lo normal de todos en pasar los planos)."""
    if _dia(f["hitos"]["planos"]["fecha"]) or not pendiente(f):
        return None
    activado = _dia(f["hitos"]["activacion"]["fecha"])
    if not activado:
        return None
    n = laborables(activado, hoy, cerrado)
    return n, normal is not None and n > normal


def texto_espera(n: int, retraso: bool, normal: int | None) -> str:
    if retraso:
        return f"Retraso: {n - normal} días más de lo normal"
    return f"Esperando: {n} día" if n == 1 else f"Esperando: {n} días"


def por_persona(datos: dict, cerrado, pasos: list[tuple[str, str]]) -> list[dict]:
    """[{persona, paso, que, n, naturales, laborables}]: la mediana de cada uno en su paso.

    Las mismas reglas que `seguimiento.resumen`, sin los suministros «R» ni los
    anulados, y con los días laborables al lado. `pasos`: [(paso, «qué hace»)]."""
    que = dict(pasos)
    out = []
    filas_ok = [f for f in datos["filas"] if not fuera(f)]
    for paso, (tramo, hito) in PASOS_PERSONA.items():
        if paso not in que:
            continue
        grupos: dict[str, dict] = {}
        for f in filas_ok:
            v = _vale(f, tramo)
            clave, mostrar = _persona(f["hitos"][hito]["persona"])
            if v is None or not clave:
                continue
            g = grupos.setdefault(clave, {"persona": mostrar, "nat": [], "lab": []})
            g["nat"].append(v)
            g["lab"].append(laborables_tramo(f, tramo, cerrado))
        for g in sorted(grupos.values(), key=lambda g: -len(g["nat"])):
            out.append({"persona": g["persona"], "paso": paso, "que": que[paso], "n": len(g["nat"]),
                        "naturales": round(statistics.median(g["nat"])),
                        "laborables": round(statistics.median(g["lab"]))})
    return out
