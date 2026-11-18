"""Plazos en Excel: Pedidos, Cola, Por persona y Resumen.

Lo pinta a partir de `seguimiento.cargar()`; no calcula nada.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

# Hitos que se enseñan, con su nombre en el Excel. Los que pueden venir del
# correo o de la carpeta llevan además su fuente.
HITOS_XL = [
    ("rfq", "Oferta recibida", True),
    ("contestada", "Oferta contestada", True),
    ("pedido", "Pedido del cliente", False),
    ("activacion", "Activación", True),
    ("compra_1", "1.er pedido a proveedor", False),
    ("material", "Material recibido", False),
    ("planos", "Planos a fábrica", True),
    ("fabrica", "Pasado a fábrica (1.ª OT)", False),
    ("fichaje_1", "1.er fichaje", False),
    ("envio", "Envío", False),
    ("entrega", "Entrega contractual", False),
]

PERSONAS_XL = [("contestada", "Comercial"), ("activacion", "Activa"), ("planos", "Técnico")]

TRAMOS_XL = {
    "comercial": "Días comercial (recibida → contestada)",
    "cliente": "Días cliente (contestada → pedido)",
    "activar": "Días activar (pedido → activación)",
    "compras_pedir": "Días compras (activación → 1.er pedido proveedor)",
    "material": "Días material (activación → recibido)",
    "tecnico": "Días técnico (activación → planos a fábrica)",
    "a_fabrica": "Días planos a fábrica → 1.ª OT (negativo: la OT se lanzó antes)",
    "cola_taller": "Días cola taller (1.ª OT → 1.er fichaje)",
    "taller_envio": "Días planos a fábrica → envío",
    "total": "Días total (oferta recibida → planos a fábrica)",
}

PASOS_XL = {"comercial": "Comercial: oferta recibida → contestada", "activar": "Comercial: pedido → activación",
            "compras": "Compras: activación → material recibido", "tecnico": "Técnico: activación → planos a fábrica"}

ESTADOS_XL = {"ok": "", "sin_carpeta": "Sin carpeta", "fabricado_sin_planos": "Fabricado sin correo de envío en Envíos",
              "planos_antes": "Planos antes del pedido", "pendiente_planos": "Pendiente de planos"}

FALTA_XL = {"planos": "Planos (el material ya está)", "ambos": "Planos y material",
            "material": "Material", "nada": "Listo para fábrica"}

_CAB = Font(bold=True, color="FFFFFF")
_RELLENO = PatternFill("solid", fgColor="334155")


def _xl(v):
    """Excel no admite horas con zona: se pasa a la hora local."""
    if isinstance(v, datetime) and v.tzinfo is not None:
        return v.astimezone().replace(tzinfo=None)
    return v


def _hoja(wb, titulo: str, cabecera: list[str], filas: list[list]):
    ws = wb.create_sheet(titulo)
    ws.append(cabecera)
    for c in ws[1]:
        c.font, c.fill = _CAB, _RELLENO
    for f in filas:
        ws.append([_xl(v) for v in f])
    for i, nombre in enumerate(cabecera, start=1):
        largo = max([len(str(nombre))] + [len(str(f[i - 1])) for f in filas if f[i - 1] is not None][:200])
        ws.column_dimensions[get_column_letter(i)].width = min(max(largo + 2, 10), 45)
        for fila in ws.iter_rows(min_row=2, min_col=i, max_col=i):
            v = fila[0].value
            if isinstance(v, datetime):
                fila[0].number_format = "dd-mm-yyyy hh:mm" if (v.hour or v.minute) else "dd-mm-yyyy"
            elif hasattr(v, "year"):
                fila[0].number_format = "dd-mm-yyyy"
    ws.freeze_panes = "B2"
    return ws


def _pedidos(filas: list[dict]):
    cab = ["Pedido", "Cliente", "Equipo", "Oferta"]
    for _k, nombre, con_fuente in HITOS_XL:
        cab.append(nombre)
        if con_fuente:
            cab.append(f"Fuente {nombre.lower()}")
    cab += [n for _h, n in PERSONAS_XL] + list(TRAMOS_XL.values()) + ["Estado", "Avisos"]
    out = []
    for f in filas:
        h = f["hitos"]
        fila = [f["pedido"], f["cliente"], f["equipo"], f["oferta"]]
        for k, _nombre, con_fuente in HITOS_XL:
            fila.append(h[k]["fecha"])
            if con_fuente:
                fila.append(h[k]["fuente"])
        fila += [h[k]["persona"] for k, _n in PERSONAS_XL]
        fila += [f["tramos"].get(k) for k in TRAMOS_XL]
        estado = ESTADOS_XL.get(f["estado"], f["estado"])
        if f.get("compartido"):
            estado = (estado + " · " if estado else "") + "compras/OTs compartidas con otros suministros"
        fila += [estado, " · ".join(f["avisos"])]
        out.append(fila)
    return cab, out


def _cola(cola: list[dict]):
    cab = ["Prioridad", "Qué falta", "Pedido", "Cliente", "Equipo", "Activación", "Entrega contractual",
           "Margen desde (días)", "Margen hasta (días)", "Basado en (pedidos)", "Histórico de", "Carpeta Envíos"]
    out = []
    for i, c in enumerate(cola, start=1):
        m = c.get("margen")
        out.append([i, FALTA_XL.get(c["falta"], c["falta"]), c["pedido"], c["cliente"], c["equipo"],
                    c["hitos"]["activacion"]["fecha"], c["hitos"]["entrega"]["fecha"],
                    m[0] if m else None, m[1] if m else None, c.get("margen_n") or None,
                    c.get("margen_de") or "", c.get("ruta") or ""])
    return cab, out


def _stats_fila(s: dict) -> list:
    return [s["n"], s["mediana"], s["p25"], s["p75"]]


def exportar(datos: dict, ruta) -> str:
    """Escribe el Excel y devuelve su ruta."""
    wb = Workbook()
    wb.remove(wb.active)
    _hoja(wb, "Pedidos", *_pedidos(datos["filas"]))
    _hoja(wb, "Cola", *_cola(datos["cola"]))
    r = datos["resumen"]
    _hoja(wb, "Por persona", ["Paso", "Persona", "Casos", "Mediana (días)", "p25", "p75"],
          [[PASOS_XL.get(p["paso"], p["paso"]), p["persona"], p["n"], p["mediana"], p["p25"], p["p75"]]
           for p in r["por_persona"]])
    filas = [["Todos", TRAMOS_XL[t], *_stats_fila(s)] for t, s in r["tramos"].items()]
    for eq, tramos in r["por_equipo"].items():
        filas += [[f"Equipo: {eq}", TRAMOS_XL[t], *_stats_fila(s)] for t, s in tramos.items() if s["n"]]
    for mes, tramos in r["por_mes"].items():
        filas += [[f"Mes del pedido: {mes}", TRAMOS_XL[t], *_stats_fila(s)] for t, s in tramos.items() if s["n"]]
    _hoja(wb, "Resumen", ["Grupo", "Paso", "Casos", "Mediana (días)", "p25", "p75"], filas)
    ruta = Path(ruta)
    wb.save(ruta)
    return str(ruta)
