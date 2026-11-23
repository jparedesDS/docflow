"""Expediente de un cliente que no paga: los datos de cada PO, en un sitio.

Cuando un cliente retiene pagos con la excusa de la documentación, hay que
contar PO a PO qué falta y de qué lado está, qué nos deben, qué se ha
reclamado y con quién hablar. Este módulo junta eso sin interfaz: devuelve
diccionarios planos que leen las salidas (Excel, Word) y la pantalla de
revisión. Ver docs/superpowers/specs/2026-11-23-expediente-cliente-design.md.

Un **PO** es el pedido del cliente; en el ERP agrupa varios pedidos nuestros
(P-99/048, P-99/080…) y sus suplementos. La relación está en
`orders.num_ref_order`, escrita de muchas formas para el mismo PO
(`109901071`, `1099010710-00`, `1099010710 Sup.04`, a veces con un dígito de
menos): se agrupa por los 9 primeros dígitos y lo que no encaje lo corrige JP.

Todo es lectura: ERP, DocFlow, buzón.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime

from core.services.administration import money
from core.services.erp_common import as_date, clean, norm_order

_NO_DIGITO = re.compile(r"\D")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_HIST = re.compile(r"(\d{2}[/-]\d{2}[/-]\d{4})\s+(.+?)\s+Rev\.?\s*(\w+)")
_CITA_FACTURA = re.compile(r"\bF-\d{2}/\d{3}\b")
DIAS_RECIENTE = 90


def _fecha(v) -> date | None:
    """date, datetime, 'aaaa-mm-dd', 'dd/mm/aaaa' o 'dd-mm-aaaa' → date."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = _ISO.match(str(v or "").strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return as_date(v)


def _rev(v) -> str:
    s = clean(v)
    return s[:-2] if s.endswith(".0") else s


def _digitos(ref) -> str:
    return _NO_DIGITO.sub("", str(ref or ""))


def clave_po(ref: str | None, pedido: str) -> str:
    """Clave de agrupación: los 9 primeros dígitos de la referencia del PO.

    Sin una referencia con al menos 9 dígitos, el pedido (sin sufijo de
    suministro) hace de clave: así un pedido sin PO no se pierde."""
    d = _digitos(ref)
    if len(d) >= 9:
        return d[:9]
    return norm_order(pedido) or str(pedido or "").strip()


def agrupar(ordenes: list[dict], extra: dict[str, list[str]] | None = None) -> dict[str, dict]:
    """{clave: {"po", "pedidos", "ordenes"}} a partir de las filas de pedidos.

    `extra` = {po: [pedido]} guardado por JP: esos pedidos van a ese PO aunque
    su referencia diga otra cosa."""
    destino = {}
    for po, peds in (extra or {}).items():
        k = clave_po(po, po)
        for p in peds:
            destino[norm_order(p) or p] = (k, po)

    grupos: dict[str, dict] = {}
    candidatos: dict[str, Counter] = {}
    forzado: dict[str, str] = {}
    for o in ordenes:
        pedido = norm_order(o.get("num_order")) or str(o.get("num_order") or "")
        if pedido in destino:
            k, po = destino[pedido]
            forzado.setdefault(k, po)
        else:
            k = clave_po(o.get("num_ref_order"), o.get("num_order"))
        g = grupos.setdefault(k, {"po": k, "pedidos": [], "ordenes": []})
        g["ordenes"].append(o)
        if pedido and pedido not in g["pedidos"]:
            g["pedidos"].append(pedido)
        d = _digitos(o.get("num_ref_order"))
        if len(d) >= 10 and d[:9] == k:
            candidatos.setdefault(k, Counter())[d[:10]] += 1

    for k, g in grupos.items():
        g["pedidos"].sort()
        if candidatos.get(k):
            g["po"] = candidatos[k].most_common(1)[0][0]
        elif len(_digitos(forzado.get(k))) >= 10:
            g["po"] = _digitos(forzado[k])[:10]
    return grupos


# ── Documentos ────────────────────────────────────────────────────────────────

def _pedido_de(fila: dict) -> str:
    return norm_order(fila.get("Nº Pedido")) or ""


def documentos(filas: list[dict], pedidos: list[str], hoy: date) -> dict:
    """Documentos de los pedidos del PO, separados por quién los tiene.

    `Enviado` lo tiene el cliente; cualquier otro estado no aprobado (comentarios,
    rechazado) lo tiene EIPSA. «Veces enviado» y «primer envío» salen del
    historial de revisiones: son mínimos, el historial antiguo está incompleto."""
    peds = set(pedidos)
    out = {"total": 0, "aprobados": 0, "cliente": [], "eipsa": []}
    for f in filas:
        if _pedido_de(f) not in peds:
            continue
        out["total"] += 1
        estado = clean(f.get("Estado"))
        if estado.lower().startswith("aprobado"):
            out["aprobados"] += 1
            continue
        enviado = _fecha(f.get("Fecha Env. Doc."))
        envios, fechas = 0, [enviado] if enviado else []
        for tok in str(f.get("Historial Rev.") or "").split("//"):
            m = _HIST.search(tok)
            if not m:
                continue
            d = _fecha(m.group(1))
            if d:
                fechas.append(d)
            if "envi" in m.group(2).lower():
                envios += 1
        doc = {"pedido": clean(f.get("Nº Pedido")), "doc_cliente": clean(f.get("Nº Doc. Cliente")),
               "doc_eipsa": clean(f.get("Nº Doc. EIPSA")), "titulo": clean(f.get("Título")), "estado": estado,
               "rev": _rev(f.get("Nº Revisión")), "enviado": enviado,
               "dias": (hoy - enviado).days if enviado else None, "envios": max(envios, 1),
               "primer_envio": min(fechas) if fechas else None, "seguimiento": clean(f.get("Seguimiento"))}
        out["cliente" if estado == "Enviado" else "eipsa"].append(doc)
    out["cliente"].sort(key=lambda d: -(d["dias"] or 0))
    return out


# ── Facturas y avales ─────────────────────────────────────────────────────────

def _concepto(lineas: list[dict], obs: str) -> str:
    texto = clean(lineas[0].get("description")) if lineas else ""
    texto = re.sub(r"^\s*EXCEL\s*", "", texto, flags=re.I)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or clean(obs)


def facturas(cabeceras: list[dict], detalles: list[dict], hoy: date) -> tuple[list[dict], list[dict]]:
    """(pendientes, verificar) de unas cabeceras de factura.

    Pendiente = sin cobro y no anulada por un abono que la cite. Un abono nunca
    es pendiente. Las reemisiones para confirming sin fecha de cobro van aparte,
    para que Administración confirme si están cobradas."""
    lineas: dict = {}
    for d in detalles:
        lineas.setdefault(d.get("invoice_header_id"), []).append(d)

    def importe(c) -> float:
        if clean(c.get("base")):
            return money(c.get("base"))          # money() conserva el signo
        return round(sum(money(d.get("total")) for d in lineas.get(c.get("id"), [])), 2)

    anuladas, abonos = set(), set()
    for c in cabeceras:
        if importe(c) < 0:
            abonos.add(c.get("num_invoice"))
            textos = [clean(c.get("obs_delivnote"))] + [clean(d.get("description")) for d in lineas.get(c.get("id"), [])]
            for t in textos:
                if "abono" in t.lower():
                    anuladas.update(x for x in _CITA_FACTURA.findall(t) if x != c.get("num_invoice"))

    pendientes, verificar = [], []
    for c in cabeceras:
        num = c.get("num_invoice")
        pagada = bool(c.get("pay_date")) or clean(c.get("invoice_state")).lower() == "pagada"
        if pagada or num in abonos or num in anuladas:
            continue
        emitida = _fecha(c.get("date_invoice"))
        base = importe(c)
        try:
            iva = float(str(c.get("iva") or 0).replace(",", "."))
        except ValueError:
            iva = 0.0
        dias = (hoy - emitida).days if emitida else 0
        fac = {"numero": num, "pedido": clean(c.get("our_ref")), "su_ref": clean(c.get("their_ref")), "fecha": emitida,
               "dias": dias, "concepto": _concepto(lineas.get(c.get("id"), []), c.get("obs_delivnote")),
               "base": base, "iva": iva, "total": round(base * (1 + iva / 100), 2), "reciente": dias < DIAS_RECIENTE}
        (verificar if "confirming" in clean(c.get("obs_delivnote")).lower() else pendientes).append(fac)
    pendientes.sort(key=lambda f: f["fecha"] or date.max)
    return pendientes, verificar


def avales(ordenes: list[dict]) -> list[dict]:
    """Avales de EIPSA en vigor en esos pedidos."""
    out = []
    for o in ordenes:
        if clean(o.get("warranty_bond_state")).upper() != "EN VIGOR":
            continue
        try:
            imp = float(str(o.get("warranty_bond_amount") or 0).replace(",", "."))
        except ValueError:
            imp = money(o.get("warranty_bond_amount"))
        out.append({"pedido": clean(o.get("num_order")), "importe": imp, "banco": clean(o.get("warranty_bond_bank")),
                    "vence": clean(o.get("warranty_bond_expiring_date")), "ref": clean(o.get("warranty_bond_reference"))})
    return out


# ── El expediente montado ─────────────────────────────────────────────────────

def _cliente_norm(v) -> str:
    return re.sub(r"\s+", " ", clean(v).upper())


def _correos_de_po(correos: list[dict], pedidos: list[str], po: str) -> list[dict]:
    from core.services.expediente_correos import carpetas_pedido
    nueve = _digitos(po)[:9]
    out = []
    for c in correos:
        asunto = c.get("asunto", "")
        if (carpetas_pedido(pedidos, [c.get("carpeta", "")])
                or (len(nueve) == 9 and nueve in asunto.replace(" ", ""))
                or any(p in asunto for p in pedidos)):
            out.append(c)
    return out


def construir(cliente: str, ordenes: list[dict], docs: list[dict], cabeceras: list[dict], detalles: list[dict],
              correos: list[dict], log: dict, hoy: date, pos: list[str] | None = None,
              extra: dict | None = None, dominio: str = "", propio: str = "",
              avisos: list[str] | None = None) -> dict:
    """El expediente de un cliente con los datos ya leídos (función pura).

    Sin `pos`, entran los PO con documentación no aprobada o facturas sin cobrar."""
    from core.services import expediente_correos as ec
    cli = _cliente_norm(cliente)
    propias = [o for o in ordenes if "client" not in o or _cliente_norm(o.get("client")) == cli]
    propio_dom = propio.split("@")[-1] if "@" in propio else ""
    salida: dict[str, dict] = {}
    for g in agrupar(propias, extra).values():
        po, pedidos = g["po"], g["pedidos"]
        if pos is not None and po not in pos:
            continue
        nueve = _digitos(po)[:9]
        mias = [c for c in cabeceras
                if any(p in clean(c.get("our_ref")) for p in pedidos)
                or (len(nueve) == 9 and nueve in _digitos(c.get("their_ref")))]
        ids = {c.get("id") for c in mias}
        pend, verif = facturas(mias, [d for d in detalles if d.get("invoice_header_id") in ids], hoy)
        dd = documentos(docs, pedidos, hoy)
        if pos is None and not (dd["cliente"] or dd["eipsa"] or pend or verif):
            continue
        ords = sorted(g["ordenes"], key=lambda o: _fecha(o.get("order_date")) or date.max)
        entregas = [_fecha(o.get("last_date_deliveries")) for o in ords]
        cs = [{**c, "automatico": ec.es_automatico(c, propio)} for c in _correos_de_po(correos, pedidos, po)]
        cs.sort(key=lambda c: c["fecha"], reverse=True)
        historial = [h for p in pedidos for h in (log or {}).get(p, {}).get("history", [])]
        e_rec, c_rec = ec.reclamaciones(cs, pedidos + [po], propio_dom, historial)
        salida[po] = {
            "po": po, "pedidos": pedidos,
            "proyecto": clean(ords[0].get("project")) if ords else "",
            "equipo": clean(ords[0].get("material")) if ords else "",
            "importe": round(sum(money(o.get("order_amount")) for o in ords), 2),
            "ultima_entrega": max([d for d in entregas if d], default=None),
            "suministros": [{"pedido": clean(o.get("num_order")), "su_ref": clean(o.get("num_ref_order")),
                             "fecha": _fecha(o.get("order_date")), "importe": money(o.get("order_amount")),
                             "entregado": o.get("porc_deliveries"),
                             "ultima_entrega": _fecha(o.get("last_date_deliveries")),
                             "cerrado": clean(o.get("closed")).upper() == "OK"} for o in ords],
            "docs": dd, "facturas": pend, "verificar": verif,
            "deuda_base": round(sum(f["base"] for f in pend), 2),
            "deuda_total": round(sum(f["total"] for f in pend), 2),
            "avales": avales(ords), "correos": cs, "recl_eipsa": e_rec, "recl_cliente": c_rec,
        }
    unicos = {c["msgid"]: c for p in salida.values() for c in p["correos"]}
    contactos = ec.contactos(list(unicos.values()), dominio, hoy)
    for k in contactos:
        k["pos"] = [po for po, p in salida.items()
                    if any(k["email"] in " ".join([c.get("de_email", ""), str(c.get("para", "")),
                                                   str(c.get("cc", ""))]).lower() for c in p["correos"])]
    return {"cliente": cliente, "hoy": hoy, "avisos": list(avisos or []), "pos": dict(sorted(salida.items())),
            "contactos": contactos}


# ── Lectura real (ERP, DocFlow, buzón) ────────────────────────────────────────

_SQL_PEDIDOS = """
    SELECT o.num_order, o.num_ref_order, o.order_date, o.order_amount, o.porc_deliveries, o.last_date_deliveries,
           o.closed, o.warranty_bond_state, o.warranty_bond_amount, o.warranty_bond_bank,
           o.warranty_bond_expiring_date, o.warranty_bond_reference, f.payment_term, f.material,
           f.client, f.project, f.buyer
    FROM public.orders o LEFT JOIN public.offers f ON f.num_offer = o.num_offer
    WHERE upper(trim(f.client)) = %s
"""
_SQL_FACTURAS = """
    SELECT i.id, i.num_invoice, i.our_ref, i.their_ref, i.date_invoice, i.pay_date, i.invoice_state,
           i.tax_base_amount::text AS base, i.iva, i.obs_delivnote
    FROM purch_fact.invoice_header i
    WHERE i.our_ref ILIKE ANY(%s) OR i.their_ref ILIKE ANY(%s)
"""
_SQL_DETALLE = """
    SELECT invoice_header_id, description, total_price::text AS total
    FROM purch_fact.invoice_detail WHERE invoice_header_id = ANY(%s)
"""


def clientes() -> list[str]:
    """Clientes con algún pedido con documentación no aprobada o factura sin cobrar."""
    from core.services import monitoring
    from core.services.erp_common import safe_query
    con_docs = {norm_order(d.get("Nº Pedido")) for d in monitoring.get_monitoring_data()
                if not clean(d.get("Estado")).lower().startswith("aprobado")}
    pend = {norm_order(r.get("our_ref")) for r in safe_query(
        "SELECT our_ref FROM purch_fact.invoice_header WHERE pay_date IS NULL", label="expediente facturas")}
    filas = safe_query("SELECT o.num_order, f.client FROM public.orders o JOIN public.offers f ON f.num_offer = o.num_offer",
                       label="expediente clientes")
    out = {_cliente_norm(r.get("client")) for r in filas
           if r.get("client") and norm_order(r.get("num_order")) in (con_docs | pend)}
    return sorted(c for c in out if c)


def slug(t: str) -> str:
    """Nombre de archivo seguro para un cliente: minúsculas, sin tildes, [a-z0-9-]."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or ""))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "cliente"


def cargar(cliente: str, pos: list[str] | None = None, progreso=None) -> dict:
    """Lee ERP, DocFlow, reclamaciones y buzón y monta el expediente (solo lectura)."""
    from core.config import IMAP_USER
    from core.paths import state_dir
    from core.services import expediente_correos as ec, monitoring
    from core.services.erp_common import safe_query
    from core.utils.json_store import read_json
    try:
        from core.services.expediente_texto import cargar_texto
        guardado = cargar_texto(cliente)
    except ImportError:
        guardado = {}

    hoy = date.today()
    aviso = []
    if progreso:
        progreso("Leyendo pedidos del ERP")
    ordenes = safe_query(_SQL_PEDIDOS, (_cliente_norm(cliente),), label="expediente pedidos")
    if not ordenes:
        aviso.append("El ERP no devuelve pedidos de este cliente (¿sin conexión?).")
    grupos = agrupar(ordenes, guardado.get("pedidos_extra"))
    pedidos = sorted({p for g in grupos.values() for p in g["pedidos"]})
    nueves = sorted({_digitos(g["po"])[:9] for g in grupos.values() if len(_digitos(g["po"])) >= 9})
    if progreso:
        progreso("Leyendo facturas")
    cabs = safe_query(_SQL_FACTURAS, ([f"%{p[2:]}%" for p in pedidos], [f"%{n}%" for n in nueves] or ["-"]),
                      label="expediente facturas") if pedidos else []
    dets = safe_query(_SQL_DETALLE, ([c["id"] for c in cabs],), label="expediente detalle") if cabs else []
    if progreso:
        progreso("Leyendo documentación de DocFlow")
    docs = monitoring.get_monitoring_data()
    log = read_json(str(state_dir() / "claims_log.json"), default={}) or {}

    correos, av_buzon = [], []
    try:
        from core.services import imap
        conn = imap._connect("INBOX")
        try:
            todas = imap._all_folders(conn)
        finally:
            conn.logout()
        carpetas = ec.carpetas_pedido(pedidos, todas) + list(guardado.get("carpetas", []))
        correos, av_buzon = ec.leer(carpetas, nueves, state_dir() / "expediente_correos" / f"{slug(cliente)}.json",
                                    progreso=progreso)
    except Exception as exc:  # noqa: BLE001
        av_buzon = [f"Sin buzón: {exc}"]
    propio = (IMAP_USER or "").lower()
    propio_dom = propio.split("@")[-1]
    dominios = Counter(c["de_email"].split("@")[-1] for c in correos
                       if "@" in c.get("de_email", "") and c["de_email"].split("@")[-1] != propio_dom)
    dominio = dominios.most_common(1)[0][0] if dominios else ""
    return construir(cliente, ordenes, docs, cabs, dets, correos, log, hoy, pos=pos,
                     extra=guardado.get("pedidos_extra"), dominio=dominio, propio=propio, avisos=aviso + av_buzon)
