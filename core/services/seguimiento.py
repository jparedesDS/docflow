"""Plazos: del correo de la oferta a la fábrica, pedido a pedido y persona a persona.

La cadena de un pedido tiene dos tramos en paralelo desde la activación:

    correo RFQ ─► oferta contestada ─► (cliente) pedido ─► ACTIVACIÓN
                                                         ├─► compras: 1.er pedido a proveedor ─► material
                                                         └─► técnico: planos a fábrica (correo de Envíos)
                                       planos a fábrica ─► 1.ª OT ─► 1.er fichaje ─► envío

Aquí solo se calcula: los lectores (`seguimiento_erp`, `seguimiento_carpetas`,
`seguimiento_correos`) traen los datos y este módulo los convierte en filas,
tiempos típicos y la cola de planos. Así se prueba sin ERP, sin correo y sin M:.

Los días son naturales y se cuentan entre fechas: una hora de correo se reduce
a su día antes de restar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

# Días antes de la activación de un suministro en que una compra u OT del pedido
# (sin suministro) todavía se le atribuye
MARGEN_BASE = 7

HITOS = ("rfq", "contestada", "pedido", "activacion", "compra_1", "material", "planos",
         "listo", "fabrica", "fichaje_1", "envio", "entrega")

TRAMOS = {
    "comercial": ("rfq", "contestada"),
    "cliente": ("contestada", "pedido"),
    "activar": ("pedido", "activacion"),
    "compras_pedir": ("activacion", "compra_1"),
    "material": ("activacion", "material"),
    "tecnico": ("activacion", "planos"),
    "a_fabrica": ("planos", "fabrica"),
    "cola_taller": ("fabrica", "fichaje_1"),
    "taller_envio": ("planos", "envio"),
    "listo": ("activacion", "listo"),       # hasta que la fábrica tiene planos y material
    "total": ("rfq", "listo"),
}


def _dia(v) -> date | None:
    """El día aquí: una hora con zona (la del remitente) se pasa antes a la hora local."""
    if isinstance(v, datetime):
        return (v.astimezone() if v.tzinfo else v).date()
    return v if isinstance(v, date) else None


def _dias(a, b) -> int | None:
    a, b = _dia(a), _dia(b)
    return (b - a).days if a and b else None


def _hito(fecha=None, fuente: str = "", persona: str = "") -> dict:
    return {"fecha": fecha, "fuente": fuente if fecha or fuente == "sin_compras" else "", "persona": persona}


def _listo(h: dict) -> tuple[dict, str]:
    """Cuándo la fábrica puede empezar (tiene planos y material) y qué llegó último.

    Compras y planos van a la vez desde la activación: manda el último. Sin
    compras, solo cuentan los planos. Con material pendiente, todavía no."""
    planos, material = h["planos"]["fecha"], h["material"]
    if not planos:
        return _hito(), ""
    if material["fuente"] == "sin_compras":
        return _hito(planos, "calculo"), "planos"
    if not material["fecha"]:
        return _hito(), ""
    dp, dm = _dia(planos), _dia(material["fecha"])
    if dm > dp:
        return _hito(material["fecha"], "calculo"), "material"
    return _hito(planos, "calculo"), ("planos" if dp > dm else "los dos")


def _cuello(filas: list[dict]) -> dict:
    """Lo que llegó último, en los pedidos con compras (sin compras no hay elección)."""
    out = {"material": 0, "planos": 0, "los dos": 0}
    for f in filas:
        if f["retraso_por"] and f["hitos"]["material"]["fuente"] != "sin_compras":
            out[f["retraso_por"]] += 1
    out["total"] = sum(out.values())
    return out


def _fabricado(p: dict) -> bool:
    try:
        porc = int(p.get("porc_taller") or 0)
    except (TypeError, ValueError):
        porc = 0
    return porc >= 99 or bool(p.get("cerrado"))


def construir_filas(pedidos: list[dict], compras: dict[str, dict], ots: dict[str, dict],
                    planos: dict[str, dict], correos: dict[str, dict],
                    activaciones: dict[str, dict]) -> list[dict]:
    """Una fila por pedido-suministro con sus hitos, sus tramos y su estado."""
    por_base: dict[str, int] = {}
    for p in pedidos:
        por_base[p.get("base") or ""] = por_base.get(p.get("base") or "", 0) + 1

    filas = []
    for p in pedidos:
        pedido, base = p.get("pedido") or "", p.get("base") or ""
        correo = correos.get(p.get("oferta") or "") if p.get("oferta") else None
        act = activaciones.get(pedido)
        pl = planos.get(pedido)
        # Lo apuntado al propio suministro manda. Lo apuntado al pedido sin
        # suministro, si el pedido tiene varios, solo vale para el suministro
        # cuando no es de antes de su activación (sería de uno anterior).
        activado = _dia(act.get("recibido")) if act and act.get("recibido") else _dia(p.get("order_date"))
        varios = por_base.get(base, 0) > 1

        def _suyo(datos: dict, campo: str):
            if pedido in datos:
                return datos[pedido], False
            d = datos.get(base)
            if d and varios:
                cuando = _dia(d.get(campo))
                if activado and cuando and cuando < activado - timedelta(days=MARGEN_BASE):
                    return None, False
            return d, bool(d) and varios

        cp, cp_compartido = _suyo(compras, "primer_pedido")
        ot, ot_compartido = _suyo(ots, "primera_ot")
        responsable = p.get("responsable") or ""

        h = {}
        if correo and correo.get("recibido"):
            h["rfq"] = _hito(correo["recibido"], "correo", responsable)
        else:
            h["rfq"] = _hito(p.get("recep_date"), "erp", responsable)
        if correo and correo.get("contestado"):
            h["contestada"] = _hito(correo["contestado"], "correo", correo.get("contesta") or responsable)
        else:
            h["contestada"] = _hito(p.get("presentation_date"), "erp", responsable)
        h["pedido"] = _hito(p.get("order_date"), "erp")
        if act and act.get("recibido"):
            h["activacion"] = _hito(act["recibido"], "correo", act.get("remitente") or "")
        else:
            h["activacion"] = _hito(p.get("order_date"), "erp")
        if cp:
            h["compra_1"] = _hito(cp.get("primer_pedido"), "erp", "Compras")
            listo = cp.get("ultima_recepcion") if not cp.get("pendiente") else None
            h["material"] = _hito(listo, "erp", "Compras")
        else:
            h["compra_1"] = _hito()
            h["material"] = _hito(None, "sin_compras")
        if pl and pl.get("creado"):
            h["planos"] = _hito(pl["creado"], pl.get("fuente") or "carpeta", pl.get("autor") or "")
        else:
            h["planos"] = _hito()
        h["fabrica"] = _hito(ot.get("primera_ot") if ot else None, "erp")
        h["fichaje_1"] = _hito(ot.get("primer_fichaje") if ot else None, "erp")
        h["envio"] = _hito(p.get("envio"), "erp")
        h["entrega"] = _hito(p.get("expected_date"), "erp")
        h["listo"], retraso_por = _listo(h)

        tramos = {k: _dias(h[a]["fecha"], h[b]["fecha"]) for k, (a, b) in TRAMOS.items()}
        if h["activacion"]["fuente"] != "correo":
            tramos["activar"] = None        # sin el correo, activación = pedido: no es un 0 de verdad

        avisos = []
        ent, ped_d = _dia(p.get("expected_date")), _dia(p.get("order_date"))
        if ent and ped_d and ent < ped_d:
            avisos.append("La entrega del ERP es anterior al pedido")

        estado_pl = (pl or {}).get("estado") or "sin_carpeta"
        if estado_pl == "sin_carpeta":
            estado = "sin_carpeta"
        elif estado_pl == "vacia":
            estado = "fabricado_sin_planos" if _fabricado(p) else "pendiente_planos"
        elif tramos["tecnico"] is not None and tramos["tecnico"] < 0:
            estado = "planos_antes"
        else:
            estado = "ok"

        filas.append({
            "pedido": pedido, "base": base, "oferta": p.get("oferta") or "",
            "cliente": p.get("cliente") or "", "equipo": p.get("equipo") or "",
            "hitos": h, "tramos": tramos, "estado": estado, "avisos": avisos,
            "compartido": cp_compartido or ot_compartido, "retraso_por": retraso_por,
            "ruta": (pl or {}).get("ruta") or "", "envios": (pl or {}).get("envios") or 0,
            "porc_taller": p.get("porc_taller"), "cerrado": bool(p.get("cerrado")),
        })
    return filas


# ── Tiempos típicos ───────────────────────────────────────────────────────────

# Paso de cada persona: (tramo que mide, hito del que sale la persona). El
# tramo del cliente no es de nadie de la casa y no aparece.
PASOS_PERSONA = {
    "comercial": ("comercial", "contestada"),
    "activar": ("activar", "activacion"),
    "compras": ("material", "material"),
    "tecnico": ("tecnico", "planos"),
}


def _stats(xs: list[int]) -> dict:
    """n, mediana y, con 4 casos o más, p25 y p75."""
    import statistics
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0, "mediana": None, "p25": None, "p75": None}
    if len(xs) < 4:
        return {"n": len(xs), "mediana": statistics.median(xs), "p25": None, "p75": None}
    q = statistics.quantiles(xs, n=4)
    return {"n": len(xs), "mediana": statistics.median(xs), "p25": q[0], "p75": q[2]}


def _persona(raw: str) -> tuple[str, str]:
    """(clave, cómo se enseña). La misma persona llega escrita de varias formas
    —«luis-x» del correo, «luis.x» de Windows, «Luís X»—: se agrupan por la
    clave sin tildes ni signos. Las iniciales («AC») se quedan tal cual."""
    import re
    import unicodedata
    raw = (raw or "").strip()
    if raw.isupper() and len(raw) <= 4:
        return raw, raw
    sin = "".join(c for c in unicodedata.normalize("NFD", raw) if not unicodedata.combining(c)).lower()
    palabras = []
    for w in re.split(r"[\s.\-_]+", sin):
        if w and w not in palabras:
            palabras.append(w)
    clave = " ".join(palabras)
    return clave, " ".join(w.capitalize() for w in palabras)


def _vale(fila: dict, tramo: str) -> int | None:
    """El valor del tramo si cuenta para las medianas."""
    if tramo == "tecnico" and fila["estado"] in ("planos_antes", "sin_carpeta"):
        return None
    return fila["tramos"].get(tramo)


def _por_tramo(filas: list[dict]) -> dict:
    return {t: _stats([_vale(f, t) for f in filas]) for t in TRAMOS}


def resumen(filas: list[dict]) -> dict:
    """Mediana y p25–p75 de cada tramo: en total, por persona, por tipo de equipo y por mes."""
    por_persona = []
    for paso, (tramo, hito) in PASOS_PERSONA.items():
        grupos: dict[str, list[int]] = {}
        nombres: dict[str, str] = {}
        for f in filas:
            v = _vale(f, tramo)
            clave, mostrar = _persona(f["hitos"][hito]["persona"])
            if v is not None and clave:
                grupos.setdefault(clave, []).append(v)
                nombres.setdefault(clave, mostrar)
        for clave, xs in sorted(grupos.items()):
            por_persona.append({"paso": paso, "persona": nombres[clave], **_stats(xs)})

    por_equipo: dict[str, list[dict]] = {}
    por_mes: dict[str, list[dict]] = {}
    for f in filas:
        por_equipo.setdefault(f["equipo"] or "Sin tipo", []).append(f)
        d = _dia(f["hitos"]["pedido"]["fecha"])
        if d:
            por_mes.setdefault(f"{d:%Y-%m}", []).append(f)

    return {
        "tramos": _por_tramo(filas),
        "por_persona": por_persona,
        "por_equipo": {k: _por_tramo(v) for k, v in sorted(por_equipo.items())},
        "por_mes": {k: _por_tramo(v) for k, v in sorted(por_mes.items())},
        "cuello": _cuello(filas),
        # «puede empezar» mezcla dos casos que no se parecen: separados
        "listo": {
            "con_compras": _stats([f["tramos"]["listo"] for f in filas
                                   if f["hitos"]["material"]["fuente"] != "sin_compras"]),
            "sin_compras": _stats([f["tramos"]["listo"] for f in filas
                                   if f["hitos"]["material"]["fuente"] == "sin_compras"]),
        },
        "con_hora": {"rfq": sum(1 for f in filas if f["hitos"]["rfq"]["fuente"] == "correo"),
                     "total": sum(1 for f in filas if f["hitos"]["rfq"]["fecha"])},
    }


# ── La cola de planos ────────────────────────────────────────────────────────

MIN_TIPO = 5          # pedidos del mismo tipo para fiarse de su propio histórico
DIAS_ZOMBI = 180      # entrega vencida hace más que esto, sin envío: no es cola, es un pedido sin cerrar

# (falta, grupo): 1 = la fábrica podría empezar y espera al técnico
_GRUPO = {"planos": 1, "ambos": 2, "material": 3, "nada": 4}


def _margen(f: dict, hoy: date, por_tipo: dict[str, list[int]], todos: list[int]):
    """(margen, n, de dónde) — margen = (pesimista, optimista) o None."""
    entrega = _dia(f["hitos"]["entrega"]["fecha"])
    if not entrega or f["avisos"]:
        return None, 0, ""
    xs, de = por_tipo.get(f["equipo"], []), f["equipo"]
    if len(xs) < MIN_TIPO:
        xs, de = todos, "todos los tipos"
    st = _stats(xs)
    if st["p25"] is None:
        return None, st["n"], de
    quedan = (entrega - hoy).days
    return (quedan - int(round(st["p75"])), quedan - int(round(st["p25"]))), st["n"], de


def cola(filas: list[dict], historico: list[dict], hoy: date) -> list[dict]:
    """Pedidos activados a los que les falta algo para que la fábrica trabaje:
    los planos (el correo a fábrica de Envíos), el material o las dos cosas.

    La OT no cuenta: se lanza antes de mandar los planos. Primero los que tienen
    el material y no los planos; dentro de cada grupo, el de margen más corto
    (extremo pesimista) y luego la entrega."""
    por_tipo: dict[str, list[int]] = {}
    todos: list[int] = []
    for h in historico:
        v = h["tramos"].get("taller_envio")
        if v is not None and v >= 0 and not h["avisos"]:
            por_tipo.setdefault(h["equipo"], []).append(v)
            todos.append(v)

    out = []
    caducado = hoy - timedelta(days=DIAS_ZOMBI)
    for f in filas:
        h = f["hitos"]
        if not h["pedido"]["fecha"] or h["envio"]["fecha"]:
            continue
        if f["estado"] == "fabricado_sin_planos" or f["cerrado"] or (f["porc_taller"] or 0) >= 99:
            continue
        entrega = _dia(h["entrega"]["fecha"])
        if entrega and entrega < caducado:
            continue            # sin envío y la entrega pasó hace meses: zombi del ERP
        con_planos = bool(h["planos"]["fecha"])
        material_listo = bool(h["material"]["fecha"]) or h["material"]["fuente"] == "sin_compras"
        if con_planos and material_listo:
            continue            # la fábrica ya tiene planos y material
        falta = "material" if con_planos else ("planos" if material_listo else "ambos")
        margen, n, de = (None, 0, "") if con_planos else _margen(f, hoy, por_tipo, todos)
        out.append({**f, "falta": falta, "grupo": _GRUPO[falta], "margen": margen,
                    "margen_n": n, "margen_de": de})
    out.sort(key=lambda x: (x["grupo"], x["margen"] is None, x["margen"][0] if x["margen"] else 0,
                            _dia(x["hitos"]["entrega"]["fecha"]) or date.max))
    return out


# ── Todo junto ───────────────────────────────────────────────────────────────

AÑO_HISTORICO = 2024     # desde aquí se mide lo que suele tardar el taller


def cargar(años: tuple[int, ...] = (2025, 2026), hoy: date | None = None, correo: bool = True,
           base_dir=None) -> dict:
    """Lee ERP, carpetas y correo y calcula filas, resumen y cola.

    Si una fuente falla, su parte queda vacía y se avisa; nunca lanza. Con
    `correo=False` usa lo ya enlazado en la caché, sin abrir los buzones."""
    import logging
    from pathlib import Path

    from core.services import apertura, seguimiento_carpetas, seguimiento_correos, seguimiento_erp

    log = logging.getLogger(__name__)
    hoy = hoy or date.today()
    base_dir = Path(base_dir) if base_dir else apertura.DEFAULT_BASE_DIR
    todos_años = list(range(min(AÑO_HISTORICO, min(años)), max(años) + 1))
    desde = date(todos_años[0] - 1, 1, 1)
    avisos: list[str] = []

    def leer(fn, aviso, vacio):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — cada fuente puede caerse por su lado
            log.info("Plazos: %s (%s)", aviso, exc)
            log.debug("Plazos: %s", aviso, exc_info=True)
            if aviso not in avisos:
                avisos.append(aviso)
            return vacio

    pedidos = leer(lambda: seguimiento_erp.pedidos(todos_años), "Sin ERP", [])
    compras = leer(lambda: seguimiento_erp.compras(desde), "Sin ERP", {}) if pedidos else {}
    ots = leer(lambda: seguimiento_erp.ots(desde), "Sin ERP", {}) if pedidos else {}
    if not base_dir.exists():
        avisos.append("Sin acceso a M:")
        planos = {}
    else:
        planos = leer(lambda: seguimiento_carpetas.leer_planos([p["pedido"] for p in pedidos], base_dir=base_dir),
                      "Sin acceso a M:", {})
    if correo:
        correos = leer(seguimiento_correos.actualizar, "Sin correo", None)
        if correos is None:
            correos = leer(seguimiento_correos.cache, "Sin correo", {})
    else:
        correos = leer(seguimiento_correos.cache, "Sin correo", {})
    activaciones = leer(seguimiento_correos.activaciones_por_pedido, "Sin correo", {})

    historico = construir_filas(pedidos, compras, ots, planos, correos, activaciones)
    filas = [f for f in historico
             if (_dia(f["hitos"]["pedido"]["fecha"]) or date.min).year in años]
    return {"filas": filas, "resumen": resumen(filas), "cola": cola(filas, historico, hoy),
            "generado": datetime.now(), "avisos": avisos, "años": tuple(años)}
