# -*- coding: utf-8 -*-
"""Expediente de cliente: datos por PO (agrupar pedidos, documentos, facturas,
avales y el expediente montado). Funciones puras: no se conecta al ERP ni al
buzón.

Datos inventados (P-99/…, PO 1099…, @ejemplo.test).

    .venv\\Scripts\\python.exe tests\\test_expediente_datos.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import expediente as ex  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


def fila(pedido, ref, **kw):
    base = {"num_order": pedido, "num_ref_order": ref, "order_date": date(2099, 1, 10), "order_amount": "1.000,00 €",
            "porc_deliveries": 100, "last_date_deliveries": "20/06/2099", "closed": "OK", "warranty_bond_state": None,
            "warranty_bond_amount": None, "warranty_bond_bank": None, "warranty_bond_expiring_date": None,
            "warranty_bond_reference": None, "payment_term": "90_10", "material": "Niveles"}
    base.update(kw)
    return base


# ── Task 1: agrupar pedidos en PO ────────────────────────────────────────────
def test_agrupar():
    ok(ex.clave_po("1099010710-00", "P-99/048-S00") == "109901071", "sufijo -00")
    ok(ex.clave_po("109901071", "P-99/048-S01") == "109901071", "9 dígitos")
    ok(ex.clave_po("1099010710 Sup.04", "P-99/048-S04") == "109901071", "Sup.")
    ok(ex.clave_po("N/A", "P-99/074-S02R") == "P-99/074", "sin dígitos → pedido")
    ok(ex.clave_po(None, "P-99/074-S00") == "P-99/074", "vacío → pedido")
    g = ex.agrupar([fila("P-99/048-S00", "109901071"), fila("P-99/048-S01", "1099010710-01"),
                    fila("P-99/080-S00", "10990107-02")],            # errata: un dígito de menos
                   extra={"1099010710": ["P-99/080"]})
    ok(list(g) == ["109901071"] and g["109901071"]["po"] == "1099010710", g)
    ok(g["109901071"]["pedidos"] == ["P-99/048", "P-99/080"], g)
    ok(len(g["109901071"]["ordenes"]) == 3, "las tres filas van al PO")
    # un pedido sin referencia no se pierde: va con su propio número
    g2 = ex.agrupar([fila("P-99/074-S00", None), fila("P-99/074-S01", "")])
    ok(list(g2) == ["P-99/074"] and g2["P-99/074"]["po"] == "P-99/074" and g2["P-99/074"]["pedidos"] == ["P-99/074"], g2)


def doc(pedido, estado, enviado, historial, cliente="5099_20-1099010710-00003"):
    return {"Nº Pedido": pedido, "Nº Doc. Cliente": cliente, "Nº Doc. EIPSA": "99-048-DOS-0001", "Título": "WELDING DOSSIER",
            "Estado": estado, "Nº Revisión": 7.0, "Fecha Env. Doc.": enviado, "Historial Rev.": historial,
            "Seguimiento": "nota"}


def cab(i, numero, ref, base, obs="", desc="", pagada=False, su_ref="1099010610", fecha="2099-02-20"):
    return {"id": i, "num_invoice": numero, "our_ref": ref, "their_ref": su_ref, "date_invoice": fecha,
            "pay_date": "2099-03-01" if pagada else None, "invoice_state": "Pagada" if pagada else None,
            "base": (f"{base:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") if base is not None else None),
            "iva": "21", "obs_delivnote": obs, "_desc": desc}


def det(i, desc, total):
    return {"invoice_header_id": i, "description": desc, "total": total}


# ── Task 2: documentos, facturas y avales ────────────────────────────────────
def test_documentos():
    d = ex.documentos([doc("P-99/048-S00", "Enviado", "15/09/2099",
                           "15/09/2099 Enviado Rev. 7 // 03-09-2099 Com. Menores Rev. 6 // 05-10-2097 Enviado Rev. 0"),
                       doc("P-99/048-S00", "Com. Mayores", "23/10/2099", ""),
                       doc("P-99/048-S00", "Aprobado", "01/01/2099", ""),
                       doc("P-99/050-S00", "Enviado", "01/01/2099", "")],          # otro pedido: fuera
                      ["P-99/048"], date(2099, 11, 19))
    ok(d["total"] == 3 and d["aprobados"] == 1 and len(d["cliente"]) == 1 and len(d["eipsa"]) == 1, d)
    c = d["cliente"][0]
    ok(c["dias"] == 65 and c["envios"] == 2 and c["primer_envio"] == date(2097, 10, 5), c)   # formatos mezclados
    ok(c["rev"] == "7" and c["enviado"] == date(2099, 9, 15), c)
    ok(d["eipsa"][0]["envios"] == 1, "sin historial → mínimo 1 envío")


def test_facturas():
    cabs = [cab(1, "F-99/209", "P-99/028", 2469.58, obs="10%"),
            cab(2, "F-99/059", "P-99/028", -2469.58),
            cab(3, "F-99/061", "P-99/028", 3095.58, obs="10%"),
            cab(4, "F-99/191", "P-99/079", None, obs="fra. Nueva confirming"),
            cab(5, "F-99/111", "P-99/079", None, pagada=True),
            cab(6, "F-99/300", "P-99/079", None, obs="", fecha="2099-10-01"),     # sin base ni detalle, reciente
            cab(7, "F-99/301", "P-99/079", -50.0)]                                # abono huérfano
    dets = [det(2, "ABONO DE NUESTRA FACTURA F-99/209 DE 28/06/99", "-2469.58"),
            det(3, "10% DOCUMENTACION FINAL", "3095.58"),
            det(4, "EXCEL\r\n\r\nTAG.: 99FE-001", "176698.37"),
            det(7, "ABONO DE NUESTRA FACTURA F-99/999", "-50")]
    p, v = ex.facturas(cabs, dets, date(2099, 11, 19))
    ok([f["numero"] for f in p] == ["F-99/061", "F-99/300"], p)
    ok([f["numero"] for f in v] == ["F-99/191"] and v[0]["base"] == 176698.37, v)
    ok(p[1]["base"] == 0.0 and p[1]["reciente"] and not p[0]["reciente"], "sin base ni detalle → 0; reciente < 90 días")
    ok(p[0]["concepto"] == "10% DOCUMENTACION FINAL" and p[0]["dias"] == 272, p[0])
    ok(abs(p[0]["total"] - 3745.65) < 0.01 and p[0]["iva"] == 21.0, p[0])
    ok(v[0]["concepto"].startswith("TAG.: 99FE-001"), "sin «EXCEL» ni saltos de línea")


def test_avales():
    a = ex.avales([fila("P-99/037-S00", "1", warranty_bond_state="EN VIGOR", warranty_bond_amount="7048.21",
                        warranty_bond_bank="BANCO", warranty_bond_expiring_date="30/01/2100", warranty_bond_reference="R1"),
                   fila("P-99/037-S01", "1", warranty_bond_state="en vigor", warranty_bond_amount="6900.94"),
                   fila("P-99/037-S02", "1", warranty_bond_state="No ampliado", warranty_bond_amount="10")])
    ok([x["pedido"] for x in a] == ["P-99/037-S00", "P-99/037-S01"] and a[0]["importe"] == 7048.21, a)
    ok(a[0]["banco"] == "BANCO" and a[0]["vence"] == "30/01/2100" and a[0]["ref"] == "R1", a[0])


# ── Task 4: montar el expediente ─────────────────────────────────────────────
ORD = [fila("P-99/023-S00", "1099010610-00", client="CLIENTE FICTICIO", project="PROYECTO UNO", material="Termómetros",
            order_date=date(2099, 5, 12)),
       fila("P-99/064-S00", "1099010610-03", client="CLIENTE FICTICIO", project="PROYECTO UNO", material="Termómetros",
            order_date=date(2099, 9, 2)),
       fila("P-99/090-S00", "1099020910", client="CLIENTE FICTICIO", project="PROYECTO DOS", material="Placas")]
DOCS = [doc("P-99/023-S00", "Enviado", "14/09/2099", ""), doc("P-99/090-S00", "Aprobado", "01/01/2099", "")]
CABS = [cab(1, "F-99/061", "P-99/023", 3095.58, obs="10%", su_ref="1099010610 SUP.00")]
DETS = [det(1, "10% DOCUMENTACION FINAL", "3095.58")]


def mail(msgid, de, asunto, carpeta, dia, para="", cc=""):
    return {"msgid": msgid, "fecha": __import__("datetime").datetime(dia.year, dia.month, dia.day, 9, 0), "de_nombre": "",
            "de_email": de, "para": para, "cc": cc, "asunto": asunto, "cuerpo": "", "adjuntos": [], "carpeta": carpeta}


CORREOS = [mail("<a>", "doc@eipsa.test", "P-99/023 / PO: 1099010610-00 // DOCUMENTS PENDING REVIEW",
                "INBOX/P. 2099/P-99-023", date(2099, 10, 1)),
           mail("<b>", "doc@eipsa.test", "DEV: P-99/023 [eGesdoc]", "INBOX/P. 2099/P-99-023", date(2099, 10, 2)),
           mail("<c>", "ana@ejemplo.test", "RE: estado", "INBOX/P. 2099/P-99-023", date(2099, 10, 3),
                cc="Luis <luis@ejemplo.test>"),
           mail("<d>", "luis@ejemplo.test", "1099010610 // Item nuevo", "INBOX", date(2099, 10, 4)),
           mail("<e>", "eva@ejemplo.test", "Otro pedido", "INBOX/P. 2099/P-99-090", date(2099, 10, 5))]
LOG = {"P-99/023": {"history": [{"sent_at": "2099-06-01T10:00:00+00:00"}]}}


def test_construir():
    e = ex.construir("CLIENTE FICTICIO", ORD, DOCS, CABS, DETS, CORREOS, LOG, date(2099, 11, 19),
                     dominio="ejemplo.test", propio="doc@eipsa.test")
    ok(list(e["pos"]) == ["1099010610"], f"sin pos= → solo los que tienen algo pendiente: {list(e['pos'])}")
    ok(e["propio"] == "doc@eipsa.test", "el expediente sabe cuál es la cuenta propia")
    po = e["pos"]["1099010610"]
    ok(po["pedidos"] == ["P-99/023", "P-99/064"] and po["proyecto"] == "PROYECTO UNO" and po["equipo"] == "Termómetros", po)
    ok(po["deuda_base"] == 3095.58 and abs(po["deuda_total"] - 3745.65) < 0.01 and po["docs"]["cliente"], po)
    ok(po["recl_eipsa"] == [date(2099, 6, 1), date(2099, 10, 1)], po["recl_eipsa"])
    ids = [c["msgid"] for c in po["correos"]]
    ok(set(ids) == {"<a>", "<b>", "<c>", "<d>"}, f"correos del PO por carpeta y por asunto: {ids}")
    auto = {c["msgid"]: c["automatico"] for c in po["correos"]}
    ok(auto["<a>"] and auto["<b>"] and not auto["<c>"], auto)
    ok([c["email"] for c in e["contactos"]] == ["luis@ejemplo.test", "ana@ejemplo.test"], e["contactos"])
    ok(e["contactos"][0]["pos"] == ["1099010610"], e["contactos"][0])
    e1 = ex.construir("CLIENTE FICTICIO", ORD, DOCS, CABS, DETS, CORREOS, LOG, date(2099, 11, 19), pos=["1099020910"])
    ok(list(e1["pos"]) == ["1099020910"], "pos= elige aunque no tenga nada pendiente")


def test_construir_sin_buzon():
    e2 = ex.construir("CLIENTE FICTICIO", ORD, DOCS, CABS, DETS, [], {}, date(2099, 11, 19), avisos=["Sin buzón: timeout"])
    ok(e2["avisos"] == ["Sin buzón: timeout"] and e2["pos"]["1099010610"]["correos"] == [], e2["avisos"])
    ok(e2["contactos"] == [] and e2["pos"]["1099010610"]["recl_eipsa"] == [], "sin correos ni log")


def test_pedido_entero_en_un_po():
    # un suplemento con la referencia de otro PO (o con erratas) no parte el pedido
    g = ex.agrupar([fila("P-99/028-S00", "109901061"), fila("P-99/028-S01", "1099010640"),
                    fila("P-99/027-S00", "109901064"), fila("P-99/094-S00", "1099110920"),
                    fila("P-99/094-S01", "1099119200"), fila("P-99/094-S02", "1099011092")])
    ok(sorted(g) == ["109901061", "109901064", "109911092"], sorted(g))
    ok(g["109901061"]["pedidos"] == ["P-99/028"] and len(g["109901061"]["ordenes"]) == 2, g["109901061"])
    ok(g["109901064"]["pedidos"] == ["P-99/027"], g["109901064"])
    ok(len(g["109911092"]["ordenes"]) == 3, "las erratas de P-99/094 no crean PO nuevos")


def test_facturas_antiguas():
    viejas = [cab(1, "F-96/010", "P-96/052", 12105.0, fecha="2096-03-01"), cab(2, "F-99/061", "P-99/028", 3095.58)]
    p, _ = ex.facturas(viejas, [], date(2099, 11, 19))
    ok([f["numero"] for f in p] == ["F-99/061"], f"solo las de los últimos {ex.ANIOS_FACTURAS} años: {p}")


def test_revision_final():
    # 2: los correos de las carpetas generales del cliente entran en todos sus PO
    gen = CORREOS + [mail("<g>", "pepa@ejemplo.test", "Reunión de cierre", "INBOX/zPROYECTO", date(2099, 10, 6))]
    e = ex.construir("CLIENTE FICTICIO", ORD, DOCS, CABS, DETS, gen, LOG, date(2099, 11, 19),
                     dominio="ejemplo.test", propio="doc@eipsa.test", generales=["INBOX/zPROYECTO"])
    ok("<g>" in [c["msgid"] for c in e["pos"]["1099010610"]["correos"]], "correo de carpeta general")
    ok("pepa@ejemplo.test" in [k["email"] for k in e["contactos"]], "y cuenta para contactos")
    # 3: el nombre del cliente se compara con los espacios juntados también en el SQL
    ok("regexp_replace" in ex._SQL_PEDIDOS, "SQL junta espacios como _cliente_norm")
    # 4: el dominio del cliente no sale de avisos automáticos ni noreply
    cs = [mail(f"<p{i}>", "noreply@portal.test", "eGesdoc - New transmittal registered (X)", "A", date(2099, 1, i + 1))
          for i in range(5)] + [mail("<q>", "no-reply@otro.test", "aviso", "A", date(2099, 2, 1))] +          [mail("<r>", "ana@ejemplo.test", "RE: estado", "A", date(2099, 2, 2))]
    ok(ex.dominio_cliente(cs, "doc@eipsa.test") == "ejemplo.test", ex.dominio_cliente(cs, "doc@eipsa.test"))
    # 7: se sabe si el 10 % está cobrado
    pagada = [cab(9, "F-99/050", "P-99/023", 300.0, obs="10%", pagada=True, fecha="2099-03-01")]
    e2 = ex.construir("CLIENTE FICTICIO", ORD, DOCS, CABS + pagada, DETS + [det(9, "10% DOCUMENTACION FINAL", "300")],
                      [], {}, date(2099, 11, 19))
    ok(e2["pos"]["1099010610"]["cobrado_10"] is True, "10 % cobrado")
    ok(e["pos"]["1099010610"]["cobrado_10"] is False, "10 % no cobrado")


test_agrupar()
test_revision_final()
test_pedido_entero_en_un_po()
test_facturas_antiguas()
test_construir()
test_construir_sin_buzon()
test_documentos()
test_facturas()
test_avales()

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
