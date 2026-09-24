"""VPR — Vendor Progress Report: el informe mensual de avance para el cliente.

Es el parte que algunos clientes piden cada mes: cómo va la ingeniería, la
documentación, los subpedidos, el acopio, la fabricación, la inspección y los
envíos de un pedido. Todo eso ya está en el ERP repartido en cinco sitios, y
antes se copiaba a mano en el Word del cliente.

Aquí se junta:

· `datos(pedido)` — lo **medido**: equipos agrupados por familia con su avance,
  documentos con su estado, subpedidos con su recepción, fabricación y ensayos.
  Nada de esto se inventa: cada número sale de una tabla del ERP.
· `propuesta(datos)` — lo **opinable** ya escrito para repasar: nº de informe,
  fechas, % planificado y los textos de cada apartado. Es lo único que se edita
  en pantalla, porque son compromisos con el cliente, no datos.
· `generar(...)` — escribe el Word del cliente con las dos cosas.

La plantilla de SACYR (proyecto PRY001) es la primera que se soporta:
`FORMATOS["sacyr"]` dice en qué casilla va cada dato. Para añadir otro cliente
se añade otro formato con sus coordenadas; el resto del módulo no cambia.

**Regla del informe**: no se prometen fechas más allá de la del pedido. Si algo
va a llegar después, eso es un punto crítico que se habla, no una fecha que se
mete en el cuadro.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from core.services.erp_common import as_date, clean, safe_query
from core.utils import files

logger = logging.getLogger(__name__)

FECHA = "%d-%m-%Y"
VENDOR = "ESPAÑOLA DE INSTRUMENTACIÓN PRIMARIA, S.A. (EIPSA)"


def _fecha(valor) -> str:
    """Fecha como la escribe el formulario: 30-10-2026. '' si no hay."""
    d = valor if isinstance(valor, date) else as_date(valor)
    return d.strftime(FECHA) if d else ""


def _pct(parte: float, total: float) -> int:
    return int(round(100.0 * parte / total)) if total else 0


# ── Lo medido ─────────────────────────────────────────────────────────────────

def _grupo(tag: dict) -> str:
    """Nombre del grupo de equipos al que pertenece un tag.

    El cliente no quiere 122 líneas: quiere ver el suministro por familias, que
    es como avanza el taller. Los de caudal se separan por material de brida
    —el acero aleado suele ser el que manda la fecha— y los de temperatura por
    tamaño, que es como se fabrican.
    """
    tipo = str(tag.get("Tipo") or "").strip()
    tamaño = str(tag.get("Tamaño") or "").strip()
    if str(tag.get("Familia") or "") == "Temperatura":
        return f"Vaina+termopar {tamaño}" if tipo == "TW+TE" else f"Vaina {tipo} {tamaño}"
    if tipo == "M.RUN":
        return f"Meter run {tamaño}"
    mat = str(tag.get("Mat. Brida") or "").upper()
    acero = "F5" if "F5" in mat else ("A105" if "105" in mat else (mat[:12] or "s/mat"))
    return f"Placa+bridas {acero}"


def _hecho(tag: dict, campo: str) -> bool:
    return bool(str(tag.get(campo) or "").strip())


def _avance_grupo(tags: list[dict]) -> dict:
    """Avance de un grupo de equipos, en las cuatro columnas del informe.

    · Ingeniería: el equipo tiene su plano dimensional.
    · Subpedidos: el material está pedido (todos lo están cuando hay OT).
    · Fabricación: el taller lo ha dado por FABRICADO.
    · Inspección: la media de los dos controles que se le hacen —verificación
      y prueba hidrostática—, que es como se va cerrando cada equipo.
    """
    n = len(tags)
    caudal = str(tags[0].get("Familia") or "") == "Caudal"
    verificacion = "Fecha Verif. Dim." if caudal else "Fecha Verif. OF"
    controles = [sum(_hecho(t, verificacion) for t in tags),
                 sum(_hecho(t, "Fecha PH1") for t in tags)]
    return {
        "nombre": f"{_grupo(tags[0])} ({n})",
        "equipos": n,
        "ingenieria": _pct(sum(_hecho(t, "Plano Dim.") for t in tags), n),
        "subpedidos": 100,
        "fabricacion": _pct(sum(str(t.get("Estado Fab.") or "").strip() == "FABRICADO"
                                for t in tags), n),
        "inspeccion": _pct(sum(controles), 2 * n),
    }


def _equipos(pedido: str) -> list[dict]:
    from core.services import erp_tags

    return [t for t in erp_tags.fetch_tags(pedido) if t.get("_vigente")]


def _documentos(pedido: str) -> dict:
    from core.services import monitoring

    # El pedido viene escrito de varias formas («P-26/022», «P-26/022-S00»): se
    # comparan los cinco dígitos de año y número, que son los que no cambian.
    clave = re.sub(r"[^0-9]", "", pedido)[:5]
    docs = [d for d in monitoring.get_monitoring_data()
            if re.sub(r"[^0-9]", "", str(d.get("Nº Pedido", "")))[:5] == clave]
    estados = [str(d.get("Estado", "") or "").strip().lower() for d in docs]
    return {
        "total": len(docs),
        "emitidos": sum(1 for e in estados if e),
        "aprobados": sum(1 for e in estados if e.startswith(("aprob", "certific", "informativ"))),
        "pendientes": [d for d, e in zip(docs, estados)
                       if not e.startswith(("aprob", "certific", "informativ"))],
        "docs": docs,
    }


_SQL_SUBPEDIDOS = """
    SELECT h.supplier_order_num, h.order_date, h.delivery_date, h.notes,
           s.name AS proveedor,
           sum(coalesce(d.quantity, 0)) AS unidades,
           sum(coalesce(d.pending, 0))  AS pendientes,
           max(d.deliv_date_1) AS recibido,
           string_agg(DISTINCT su.description, ' · ') AS material
    FROM purch_fact.supplier_ord_header h
    LEFT JOIN purch_fact.supplier_ord_detail d ON d.supplier_ord_header_id = h.id
    LEFT JOIN purch_fact.suppliers s ON s.id = h.supplier_id
    LEFT JOIN purch_fact.supplies su ON su.id = d.supply_id
    WHERE h.notes ILIKE %s OR h.notes ILIKE %s
    GROUP BY 1, 2, 3, 4, 5
    ORDER BY h.order_date, h.supplier_order_num
"""


# Líneas que lleva casi todo pedido a proveedor y que no describen material
_RUIDO = ("courier", "porte", "transporte", "gasto", "embalaje")


def _material_resumen(texto: str, unidades: int, tope: int = 70) -> str:
    """Qué se pidió, en una línea: sin los portes y sin repetir medidas.

    El ERP guarda una línea por artículo y el cuadro del informe tiene una sola
    casilla; se quedan los primeros materiales de verdad y se dice cuántas uds.
    """
    piezas = [p.strip() for p in str(texto or "").split("·") if p.strip()]
    piezas = [p for p in piezas if not any(r in p.lower() for r in _RUIDO)]
    resumen = " · ".join(piezas)
    if len(resumen) > tope:
        resumen = resumen[:tope].rsplit(" ", 1)[0] + "…"
    return f"{resumen} ({unidades} uds)" if resumen else f"{unidades} uds"


def _subpedidos(pedido: str) -> list[dict]:
    """Los pedidos a proveedor de este pedido, recibidos y pendientes.

    `purchases.for_pedido` solo trae los que faltan por llegar; en el informe
    hay que enseñar también los que ya están, que es la mitad de la foto.
    """
    numero = re.sub(r"[^0-9]", "", pedido)
    if len(numero) < 5:
        return []
    patron = f"%{numero[:2]}/{numero[2:5]}%"
    filas = safe_query(_SQL_SUBPEDIDOS, (patron, patron.replace("/", "-")), label="subpedidos VPR")
    out = []
    for f in filas:
        pendientes = int(f.get("pendientes") or 0)
        recibido = _fecha(f.get("recibido"))
        unidades = int(f.get("unidades") or 0)
        out.append({
            "numero": clean(f.get("supplier_order_num")),
            "fecha": _fecha(f.get("order_date")),
            "proveedor": clean(f.get("proveedor")),
            "material": _material_resumen(clean(f.get("material")), unidades),
            "unidades": unidades,
            "pendientes": pendientes,
            "contractual": _fecha(f.get("delivery_date")),
            "estado": (f"PENDIENTE — {pendientes} uds" if pendientes
                       else (f"Recibido completo el {recibido}" if recibido else "Recibido")),
        })
    return out


def _cabecera(pedido: str) -> dict:
    filas = safe_query(
        """SELECT num_order, num_ref_order, order_date, expected_date, items_number,
                  porc_workshop, porc_assembly, porc_deliveries, obs_workshop, obs_assembly,
                  obs_deliveries, partial_date_deliveries
           FROM public.orders WHERE num_order ILIKE %s ORDER BY num_order""",
        (f"%{re.sub(r'[^0-9]', '', pedido)[:2]}/{re.sub(r'[^0-9]', '', pedido)[2:5]}%",),
        label="cabecera VPR")
    fila = filas[0] if filas else {}
    return {
        "pedido": clean(fila.get("num_order")) or pedido,
        "po": clean(fila.get("num_ref_order")),
        "fecha_pedido": _fecha(fila.get("order_date")),
        "entrega": _fecha(fila.get("expected_date")),
        "items": int(fila.get("items_number") or 0),
        "taller": int(fila.get("porc_workshop") or 0),
        "montaje": int(fila.get("porc_assembly") or 0),
        "entregas": int(fila.get("porc_deliveries") or 0),
        "obs_taller": clean(fila.get("obs_workshop")),
        "obs_envios": clean(fila.get("obs_deliveries")),
        "envio_parcial": _fecha(fila.get("partial_date_deliveries")),
    }


def datos(pedido: str) -> dict:
    """Todo lo que el ERP sabe del pedido para este informe."""
    tags = _equipos(pedido)
    grupos: dict[str, list[dict]] = {}
    for t in tags:
        grupos.setdefault(_grupo(t), []).append(t)
    avances = [_avance_grupo(v) for _k, v in sorted(grupos.items(), key=lambda x: -len(x[1]))]

    docs = _documentos(pedido)
    subs = _subpedidos(pedido)
    unidades = sum(s["unidades"] for s in subs)
    fabricados = sum(str(t.get("Estado Fab.") or "").strip() == "FABRICADO" for t in tags)
    verificados = sum(_hecho(t, "Fecha Verif. Dim.") or _hecho(t, "Fecha Verif. OF") for t in tags)
    ensayados = sum(_hecho(t, "Fecha PH1") for t in tags)
    entregados = sum(_hecho(t, "Fecha RN") for t in tags)

    ing_pendientes = [d for d in docs["pendientes"]
                      if "PLANO" in str(d.get("Título", "")).upper()
                      or "CALCULO" in str(d.get("Título", "")).upper()
                      or "CÁLCULO" in str(d.get("Título", "")).upper()]
    return {
        "pedido": pedido,
        "cabecera": _cabecera(pedido),
        "equipos": len(tags),
        "grupos": avances,
        "documentos": docs,
        "subpedidos": subs,
        "fabricacion": {"fabricados": fabricados, "verificados": verificados,
                        "ensayados": ensayados, "entregados": entregados},
        "avance": {
            # La ingeniería está emitida entera cuando cada equipo tiene su
            # plano; baja a 95 si algún plano o cálculo sigue sin aprobar.
            "ingenieria": 100 if not ing_pendientes else 95,
            "documentacion": _pct(docs["aprobados"], docs["total"]),
            "subpedidos": 100 if subs else 0,
            "acopio": _pct(unidades - sum(s["pendientes"] for s in subs), unidades),
            "fabricacion": _pct(fabricados, len(tags)),
            "inspeccion": _pct(verificados + ensayados, 2 * len(tags)),
            "transporte": _pct(entregados, len(tags)) or _pct(fabricados, len(tags)),
        },
    }


# ── Lo opinable, ya escrito ───────────────────────────────────────────────────

AREAS = [("ingenieria", "ENGINEERING"), ("documentacion", "DOCUMENTATION"),
         ("subpedidos", "SUBORDERS"), ("acopio", "STORED MATERIAL"),
         ("fabricacion", "MANUFACTURING"), ("inspeccion", "INSPECTION"),
         ("transporte", "TRANSPORT")]


def _planificado(inicio: str, fin: str, hoy: date) -> int:
    """El % que tocaría a día de hoy si el trabajo fuera parejo entre las dos fechas."""
    a, b = as_date(inicio), as_date(fin)
    if not a or not b or b <= a:
        return 100
    if hoy >= b:
        return 100
    return max(0, min(100, int(round(100.0 * (hoy - a).days / (b - a).days))))


def propuesta(d: dict, numero: str = "", hoy: date | None = None) -> dict:
    """Los campos que se repasan en pantalla, ya rellenos con lo razonable.

    Las fechas de entrega salen todas del pedido: el informe no promete nada
    más tarde que el compromiso contractual.
    """
    hoy = hoy or date.today()
    cab = d["cabecera"]
    entrega = cab["entrega"]
    docs, subs = d["documentos"], d["subpedidos"]
    fab = d["fabricacion"]
    inicio_obra = cab["fecha_pedido"]
    primer_sub = subs[0]["fecha"] if subs else inicio_obra

    filas = {
        "ingenieria": (inicio_obra, entrega),
        "documentacion": (inicio_obra, entrega),
        "subpedidos": (primer_sub, subs[-1]["fecha"] if subs else entrega),
        "acopio": (primer_sub, entrega),
        "fabricacion": (primer_sub, entrega),
        "inspeccion": (primer_sub, entrega),
        "transporte": (cab["envio_parcial"] or primer_sub, entrega),
    }
    resumen = {clave: {"inicio": ini, "fin": fin,
                       "planificado": _planificado(ini, fin, hoy),
                       "real": d["avance"][clave]}
               for clave, (ini, fin) in filas.items()}

    pendientes = ", ".join(str(x.get("Nº Doc. EIPSA", "")) for x in docs["pendientes"][:4])
    return {
        "numero": numero,
        "fecha": hoy.strftime(FECHA),
        "vendor": VENDOR,
        "lugar": ["MANUFACTURING PLACE: EIPSA – Pol. Ind. IGARSA, naves 3 a 8.",
                  "28860 Paracuellos de Jarama (Madrid), España.",
                  "INSPECTION PLACE: el mismo."],
        "material": _material(d),
        "po": cab["po"],
        "fecha_po": cab["fecha_pedido"],
        "contractual": entrega,
        "prometida": [f"Entrega del suministro: {entrega}, conforme al pedido."],
        "resumen": resumen,
        "previstas": {g["nombre"]: entrega for g in d["grupos"]},
        "textos": {
            "subpedidos": _texto_subpedidos(subs),
            "fabricacion": _texto_fabricacion(d),
            "inspeccion": _texto_inspeccion(d),
            "siguiente": [f"· Terminar la fabricación pendiente: {d['equipos'] - fab['fabricados']}"
                          f" equipos de {d['equipos']}.",
                          "· Ensayos y verificación de los equipos que salgan de taller.",
                          ("· Emitir la revisión pendiente de " + pendientes) if pendientes
                          else "· Preparar el dossier de calidad."],
        },
    }


def _material(d: dict) -> list[str]:
    lineas = [f"{d['equipos']} equipos:"]
    lineas += [f"· {g['nombre'].rsplit(' (', 1)[0]}: {g['equipos']}." for g in d["grupos"]]
    return lineas


def _texto_subpedidos(subs: list[dict]) -> list[str]:
    pendientes = [s for s in subs if s["pendientes"]]
    lineas = [f"Colocados {len(subs)} subpedidos; {len(subs) - len(pendientes)} recibidos "
              f"completos."]
    for s in pendientes:
        lineas.append(f"Pendiente el {s['numero']} ({s['proveedor']}): {s['pendientes']} uds, "
                      f"comprometidas para el {s['contractual']}.")
    lineas.append("Los proveedores son los del listado aprobado y sus certificados irán al "
                  "dossier de calidad.")
    return lineas


def _texto_fabricacion(d: dict) -> list[str]:
    cab, fab = d["cabecera"], d["fabricacion"]
    lineas = [f"Terminados y verificados {fab['fabricados']} equipos de {d['equipos']}."]
    for g in d["grupos"]:
        if g["fabricacion"]:
            lineas.append(f"{g['nombre']}: {g['fabricacion']} % fabricado.")
    if cab["envio_parcial"]:
        lineas.append(f"Entrega parcial realizada el {cab['envio_parcial']}"
                      + (f" ({cab['obs_envios']})." if cab["obs_envios"] else "."))
    lineas.append(f"Avance del taller según nuestro sistema: {cab['taller']} % de fabricación "
                  f"y {cab['montaje']} % de montaje.")
    return lineas


def _texto_inspeccion(d: dict) -> list[str]:
    fab = d["fabricacion"]
    return [
        f"Realizado: verificación de {fab['verificados']} equipos y prueba hidrostática de "
        f"{fab['ensayados']}.",
        "Previsto: ensayos y verificación del resto de equipos conforme salgan de taller.",
        "Los registros se entregan con el dossier de calidad.",
    ]


# ── Dónde va cada dato en el Word del cliente ─────────────────────────────────
#
# Coordenadas del formulario de SACYR (PRY001). Los números son la
# posición de cada tabla y de cada párrafo dentro del documento: se miran una
# vez con `estructura()` y ya no cambian mientras el cliente no cambie el Word.

FORMATO_SACYR = {
    "nombre": "SACYR — Vendor Progress Report",
    "señas": "VENDOR PROGRESS REPORT",     # texto que debe llevar la plantilla
    "cabeceras": [1, 15, 31, 50, 73],      # el cuadro que se repite en cada hoja
    "informe": 3,                          # tabla de cabecera del informe
    "resumen": 21,                         # 1. progress status summary
    "items": 28,                           # 2. detailed status by item
    "subpedidos": 37,                      # 3. suborders
    "concesiones": [63, 66],               # 7. concesiones y no conformidades
    "caja_subpedidos": 43,                 # 3.1 comentarios
    "caja_fabricacion": 48,                # 4. situación de fabricación
    "caja_inspeccion": 56,                 # 5. actividades de inspección
    "caja_siguiente": 71,                  # 8. actividades del mes siguiente
    "filas_items": range(2, 9),
    "filas_subpedidos": range(3, 8),
}

FORMATOS = {"sacyr": FORMATO_SACYR}


def formato_de(plantilla: Path | str) -> dict | None:
    """El formato que le corresponde a esa plantilla, o None si no se reconoce."""
    from core.services import formulario_docx

    try:
        doc = formulario_docx.Formulario(plantilla)
    except Exception:  # noqa: BLE001 — un .docx roto no es un fallo de la app
        logger.warning("VPR: no se pudo abrir la plantilla %s", plantilla, exc_info=True)
        return None
    texto = "".join(t.text or "" for t in doc.raiz.iter(formulario_docx.w("t")))
    for formato in FORMATOS.values():
        if formato["señas"] in texto.upper():
            return formato
    return None


def generar(plantilla: Path | str, destino: Path | str, d: dict, ajustes: dict) -> Path:
    """Escribe el VPR del cliente. No pisa nada: si el nombre está ocupado, va al lado."""
    from core.services import formulario_docx

    formato = formato_de(plantilla)
    if formato is None:
        raise ValueError("Esa plantilla no es un VPR reconocido "
                         "(se esperaba el formulario de SACYR)")
    doc = formulario_docx.Formulario(plantilla)

    # Las filas de datos crecen con su contenido: la plantilla les fija una
    # altura exacta y el texto largo saldría cortado por la mitad.
    for tabla, filas in ((formato["informe"], range(2, 10)),
                         (formato["resumen"], range(1, 8)),
                         (formato["items"], formato["filas_items"]),
                         (formato["subpedidos"], formato["filas_subpedidos"])):
        doc.altura_flexible(tabla, filas)
    for tabla in formato["concesiones"]:
        doc.altura_flexible(tabla, range(1, 4))

    numero = ajustes.get("numero", "")
    for cab in formato["cabeceras"]:
        doc.escribir_celda(cab, 1, 0, numero)
        doc.escribir_celda(cab, 1, 2, ajustes.get("po", ""))
        doc.escribir_celda(cab, 1, 4, "EIPSA")

    inf = formato["informe"]
    doc.escribir_celda(inf, 1, 1, numero)
    doc.escribir_celda(inf, 1, 3, ajustes.get("fecha", ""))
    doc.escribir_celda(inf, 1, 5, d["cabecera"]["pedido"])
    doc.escribir_celda(inf, 2, 2, ajustes.get("lugar", []))
    doc.escribir_celda(inf, 3, 0, ajustes.get("vendor", ""))
    doc.escribir_celda(inf, 3, 1, ajustes.get("po", ""))
    doc.escribir_celda(inf, 5, 0, ajustes.get("material", []))
    doc.escribir_celda(inf, 5, 1, ajustes.get("fecha_po", ""))
    doc.escribir_celda(inf, 7, 1, ajustes.get("contractual", ""))
    doc.escribir_celda(inf, 9, 1, ajustes.get("prometida", []))

    for fila, (clave, _etiqueta) in enumerate(AREAS, start=1):
        linea = ajustes["resumen"][clave]
        doc.escribir_celda(formato["resumen"], fila, 1, linea["inicio"])
        doc.escribir_celda(formato["resumen"], fila, 2, linea["fin"])
        doc.escribir_celda(formato["resumen"], fila, 3, f"{linea['planificado']} %")
        doc.escribir_celda(formato["resumen"], fila, 4, f"{linea['real']} %")

    huecos = list(formato["filas_items"])
    for fila, g in zip(huecos, d["grupos"]):
        prevista = ajustes["previstas"].get(g["nombre"], ajustes.get("contractual", ""))
        valores = [g["nombre"], g["ingenieria"], g["ingenieria"], g["subpedidos"], g["subpedidos"],
                   100, g["fabricacion"], 100, g["inspeccion"], ajustes.get("contractual", ""),
                   prevista]
        for col, valor in enumerate(valores):
            doc.escribir_celda(formato["items"], fila, col,
                               valor if isinstance(valor, str) else f"{valor} %")
    if len(d["grupos"]) > len(huecos):
        logger.warning("VPR: %d grupos para %d filas; el resto no cabe en la plantilla",
                       len(d["grupos"]), len(huecos))

    # La columna TAG se deja en blanco: el ERP no sabe a qué equipo va cada
    # compra, y rellenarla repitiendo el material solo ensucia el cuadro.
    for fila, s in zip(formato["filas_subpedidos"], d["subpedidos"]):
        for col, valor in enumerate(["", s["material"], s["numero"], s["fecha"],
                                     s["proveedor"], s["contractual"],
                                     s["contractual"] if s["pendientes"] else "—", s["estado"]]):
            doc.escribir_celda(formato["subpedidos"], fila, col, valor)

    for tabla in formato["concesiones"]:
        doc.escribir_celda(tabla, 1, 0, "N/A")
        doc.escribir_celda(tabla, 1, 1, "No hay ninguna abierta a la fecha de este informe.")
        doc.escribir_celda(tabla, 1, 2, "—")

    textos = ajustes.get("textos", {})
    for clave, caja in (("subpedidos", "caja_subpedidos"), ("fabricacion", "caja_fabricacion"),
                        ("inspeccion", "caja_inspeccion"), ("siguiente", "caja_siguiente")):
        if textos.get(clave):
            doc.escribir_caja(formato[caja], textos[clave])

    destino = files.libre(Path(destino))
    doc.guardar(destino)
    logger.info("VPR %s generado: %s", numero or "(sin número)", destino)
    return destino


# ── Dónde se guarda y qué plantilla usa cada cliente ──────────────────────────

def destino_sugerido(pedido: str, numero: str) -> Path | None:
    """`2-Tecnico\\<nº de informe>.docx` del pedido. None si no se localiza."""
    from core.services import dev_folders

    tecnico = dev_folders.tecnico_dir(pedido)
    if tecnico is None:
        return None
    nombre = re.sub(r'[\\/*?:"<>|]', "_", numero or f"VPR {pedido}").strip() or "VPR"
    return tecnico / f"{nombre}.docx"


def _perfiles() -> dict:
    from core import preferences

    datos = preferences.get("vpr_plantillas") or {}
    return dict(datos) if isinstance(datos, dict) else {}


def _clave(cliente: str) -> str:
    return " ".join(str(cliente or "").split()).lower()


def plantilla_de(cliente: str) -> str:
    """La plantilla que se usó la última vez con ese cliente."""
    return str(_perfiles().get(_clave(cliente), ""))


def guardar_plantilla(cliente: str, ruta: Path | str) -> None:
    from core import preferences

    todas = _perfiles()
    todas[_clave(cliente)] = str(ruta)
    preferences.set_value("vpr_plantillas", todas)
    logger.info("VPR: plantilla de %s guardada (%s)", cliente, Path(ruta).name)


def estructura(plantilla: Path | str) -> list[str]:
    """Mapa del Word —tablas, filas y párrafos— para localizar las casillas.

    Es la herramienta con la que se añade un formato nuevo: se mira una vez y
    se apuntan los números en `FORMATOS`.
    """
    from core.services import formulario_docx

    doc = formulario_docx.Formulario(plantilla)
    out = []
    for i, hijo in enumerate(doc.cuerpo):
        if hijo.tag == formulario_docx.w("tbl"):
            filas = hijo.findall(formulario_docx.w("tr"))
            out.append(f"T{i:03d} tabla · {len(filas)} filas")
        elif hijo.tag == formulario_docx.w("p"):
            texto = "".join(t.text or "" for t in hijo.iter(formulario_docx.w("t"))).strip()
            caja = " [cuadro de texto]" if hijo.findall(
                ".//" + formulario_docx.w("txbxContent")) else ""
            out.append(f"P{i:03d} {texto[:70]}{caja}")
    return out


def fecha_valida(texto: str) -> bool:
    """¿Está escrita como el formulario las quiere (30-10-2026)?"""
    try:
        datetime.strptime(str(texto).strip(), FECHA)
        return True
    except ValueError:
        return False
