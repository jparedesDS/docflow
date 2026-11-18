# -*- coding: utf-8 -*-
"""Plazos: la hora del correo de la oferta (y de su respuesta) enlazada a la
oferta del ERP, y la hora del correo de ACTIVACIÓN.

Datos inventados (O-99/…, dominio ejemplo.test): no lee buzones ni el ERP.

    .venv\\Scripts\\python.exe tests\\test_plazos_correos.py
"""
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import seguimiento_correos as scor  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


def local(iso):
    """La hora en local y sin zona, como la guarda el enlace."""
    return datetime.fromisoformat(iso).astimezone().replace(tzinfo=None)


def correo(fecha, de="rfq@cliente.ejemplo.test", asunto="Request for quotation", mid=None, resp=None):
    return {"date": fecha, "from_email": de, "subject": asunto, "message_id": mid or f"<{fecha}@ejemplo.test>",
            "answered_at": resp or "", "answered_from": "Pepa Ruiz" if resp else ""}


def oferta(num, recep, mails="rfq@cliente.ejemplo.test copia:pepa@casa.ejemplo.test", ref="RFQ-7001234"):
    return {"num_offer": num, "recep_date": recep, "mails": mails, "num_ref_offer": ref}


# Remitente + ventana de −3 a +1 días
r = scor.enlazar([correo("2099-01-09T10:15:00+01:00", resp="2099-01-12T09:00:00+01:00")],
                 [oferta("O-99/010", date(2099, 1, 10), ref="-")])
ok(r.get("O-99/010", {}).get("recibido") == local("2099-01-09T10:15:00+01:00"), f"enlaza: {r}")
ok(r["O-99/010"]["contestado"] == local("2099-01-12T09:00:00+01:00")
   and r["O-99/010"]["contesta"] == "Pepa Ruiz", "con su respuesta")
ok(scor.enlazar([correo("2099-01-05T10:00:00")], [oferta("O-99/010", date(2099, 1, 10), ref="-")]) == {},
   "5 días antes: fuera de la ventana")
ok(scor.enlazar([correo("2099-01-12T10:00:00")], [oferta("O-99/010", date(2099, 1, 10), ref="-")]) == {},
   "2 días después: fuera de la ventana")
ok(scor.enlazar([correo("2099-01-10T10:00:00", de="pepa@casa.ejemplo.test")],
                [oferta("O-99/010", date(2099, 1, 10), ref="-")]) == {}, "las direcciones en copia no enlazan")

# Referencia del cliente en el asunto
r = scor.enlazar([correo("2099-01-10T10:00:00", de="otro@ejemplo.test", asunto="RE: rfq-7001234 caudalímetros")],
                 [oferta("O-99/010", date(2099, 1, 10), mails="*")])
ok("O-99/010" in r, "la referencia del cliente en el asunto enlaza")
for ref in ("PO 110", "EMAIL", "-", "*", "", "A12"):
    ok(not scor.ref_util(ref), f"referencia genérica: {ref!r}")
ok(scor.ref_util("RFQ-7001234") and scor.ref_util("HEC/KDOF KWT MR-022"), "referencias útiles")
r = scor.enlazar([correo("2099-01-10T10:00:00", de="otro@ejemplo.test", asunto="PO 110 urgente")],
                 [oferta("O-99/010", date(2099, 1, 10), mails="*", ref="PO 110")])
ok(r == {}, "una referencia genérica no enlaza")

# Un correo, dos ofertas candidatas: solo la más cercana
r = scor.enlazar([correo("2099-01-10T10:00:00")],
                 [oferta("O-99/010", date(2099, 1, 11), ref="-"), oferta("O-99/011", date(2099, 1, 10), ref="-")])
ok(list(r) == ["O-99/011"], f"solo la más cercana: {list(r)}")
# Dos correos, una oferta: el más cercano
r = scor.enlazar([correo("2099-01-08T10:00:00", mid="<a@x>"), correo("2099-01-10T08:00:00", mid="<b@x>")],
                 [oferta("O-99/010", date(2099, 1, 10), ref="-")])
ok(r["O-99/010"]["message_id"] == "<b@x>", "dos correos: el más cercano")
# Dos ofertas del mismo cliente el mismo día, dos correos: cada uno a una
r = scor.enlazar([correo("2099-01-10T08:00:00", mid="<a@x>"), correo("2099-01-10T09:00:00", mid="<b@x>")],
                 [oferta("O-99/010", date(2099, 1, 10), ref="-"), oferta("O-99/011", date(2099, 1, 10), ref="-")])
ok(len(r) == 2 and r["O-99/010"]["message_id"] != r["O-99/011"]["message_id"], "un correo no sirve a dos ofertas")

# actualizar(): acumula en la caché
tmp = Path(tempfile.mkdtemp(prefix="plazos_correos_"))
cache = tmp / "correos.json"
buzon = [correo("2099-01-09T10:15:00+01:00")]
scor._buzon = lambda dias: [dict(c) for c in buzon]
scor._ofertas_erp = lambda desde: [oferta("O-99/010", date(2099, 1, 10), ref="-")]
a = scor.actualizar(60, cache_file=cache)
ok(a["O-99/010"]["contestado"] is None, "primera pasada: sin respuesta")
buzon[:] = []
b = scor.actualizar(60, cache_file=cache)
ok(b.get("O-99/010", {}).get("recibido") == a["O-99/010"]["recibido"], "fuera del buzón: el enlace se conserva")
buzon[:] = [correo("2099-01-09T10:15:00+01:00", resp="2099-01-12T09:00:00+01:00")]
c = scor.actualizar(60, cache_file=cache)
ok(c["O-99/010"]["contestado"] == local("2099-01-12T09:00:00+01:00"), "la respuesta se rellena después")
buzon[:] = [correo("2099-01-10T23:00:00+01:00", mid="<otro@x>")]
d = scor.actualizar(60, cache_file=cache)
ok(d["O-99/010"]["recibido"] == a["O-99/010"]["recibido"], "no se pisa un recibido anterior")
ok(scor.cache(cache) == d, "cache() lee lo guardado")

# Revisión final: si el correo sigue en el buzón, su enlace se recalcula; un
# correo no queda en dos ofertas
cache2 = tmp / "correos2.json"
buzon[:] = [correo("2099-03-10T10:00:00+01:00", mid="<e@x>")]
scor._ofertas_erp = lambda desde: [oferta("O-99/020", date(2099, 3, 9), ref="-")]
scor.actualizar(60, cache_file=cache2)
scor._ofertas_erp = lambda desde: [oferta("O-99/020", date(2099, 3, 9), ref="-"),
                                   oferta("O-99/021", date(2099, 3, 10), ref="-")]
e = scor.actualizar(60, cache_file=cache2)
ok(e.get("O-99/021", {}).get("message_id") == "<e@x>" and "O-99/020" not in e,
   f"el enlace se corrige y el correo no queda en dos ofertas: {sorted(e)}")

# Una hora sin zona y otra con zona no rompen las activaciones
scor.agenda.get_tareas = lambda owner=None: [
    {"origen": "activacion", "pedido": "P-99/001", "supp": "S04", "recibido": "2099-02-26T08:00:00+01:00",
     "remitente": "A"},
    {"origen": "activacion", "pedido": "P-99/001", "supp": "S04", "recibido": "2099-02-27T08:00:00",
     "remitente": "B"},
]
act = scor.activaciones_por_pedido()
ok(act.get("P-99/001-S04", {}).get("remitente") == "A", f"horas con y sin zona: {act}")

# Buzones de Ofertas: correos con fecha con zona, sin zona y sin fecha se ordenan sin romper
from core.services import ofertas  # noqa: E402

mezcla = [{"date": "2099-01-09T10:15:00+01:00"}, {"date": "2099-01-09T12:00:00"}, {"date": ""},
          {"date": "2099-01-08T09:00:00-05:00"}]
try:
    orden = sorted(mezcla, key=lambda x: ofertas._parse_dt(x.get("date", "")), reverse=True)
    ok([o["date"] for o in orden][-1] == "", f"sin fecha, al final: {orden}")
except TypeError as exc:
    ok(False, f"fechas con y sin zona no se pueden ordenar: {exc}")

# Activaciones desde la Agenda
scor.agenda.get_tareas = lambda owner=None: [
    {"origen": "activacion", "pedido": "P-99/001", "supp": "S04", "recibido": "2099-02-26T08:00:00+01:00",
     "remitente": "Pepa Ruiz", "estado": "completada"},
    {"origen": "activacion", "pedido": "P-99/002", "supp": "", "recibido": "2099-02-27T08:00:00", "remitente": "X"},
    {"origen": "otra", "pedido": "P-99/003", "supp": "", "recibido": "2099-02-27T08:00:00"},
]
act = scor.activaciones_por_pedido()
ok(set(act) == {"P-99/001-S04", "P-99/002-S00"}, f"claves: {set(act)}")
ok(act["P-99/001-S04"]["remitente"] == "Pepa Ruiz"
   and act["P-99/001-S04"]["recibido"] == local("2099-02-26T08:00:00+01:00"), "hora y remitente")

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
