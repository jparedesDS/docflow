# -*- coding: utf-8 -*-
"""Los correos «ACTIVACIÓN P-26/…» de Comercial: se leen (pedido, suministro,
PO, cliente, entrega, plazo, apartados), se convierten en «Abrir pedido …» en
la Agenda, rellenan «Nuevo pedido» y se cierran al abrir el pedido.

Datos inventados (pedidos P-99/…, dominio ejemplo.test): nada de clientes reales.

    .venv\\Scripts\\python.exe tests\\test_activaciones.py
"""
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import activaciones as act_srv  # noqa: E402
from core.services import agenda, avisos_calculos as av  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


COMERCIAL = '"Pepa Ruiz" <pepa-ruiz@ejemplo.test>'
BUZON = "documentacion@ejemplo.test"
PERSONAL = "yo@ejemplo.test"


def cuerpo(po="4500012345-04", de="CLIENTE FICTICIO / OBRA / FASE 2", pedido="P-99/001-S04",
           entrega="30-04-2099", plazo="26/28 semanas", extras="PMI\nLíquidos Penetrantes",
           doc="Según VDDL acordada"):
    return (
        "Hola a todos,\n\n"
        f"Hemos recibido la orden de compra {po} de {de}.\n\n"
        f"Nuestro pedido es {pedido}.\n\n"
        "Los equipos correspondientes ya se encuentran en el ERP.\n\n"
        f"La fecha de entrega contractual es {entrega}.\n\n"
        f"El plazo de entrega acordado es {plazo}.\n\n"
        "Mas detalle del pedido en su carpeta correspondiente.\n\n"
        "INFORMACIÓN ADICIONAL:\nALCANCE: Dos parejas de bridas\nIgual que el suplemento 03\n\n"
        f"EXTRAS:\n{extras}\n\n"
        f"DOCUMENTACIÓN:\n{doc}\n\n"
        "Un saludo.\n\nEMPRESA FICTICIA S.A\nCommercial Department\n\n"
        "NOTA LEGAL: Este mensaje… DOCUMENTACIÓN: no es un apartado.\n"
    )


# ── Leer una activación ───────────────────────────────────────────────────────
a = act_srv.analizar("ACTIVACIÓN P-99/001-S04 / CLIENTE FICTICIO", cuerpo(), COMERCIAL,
                     "2099-03-10T09:20:00+01:00", "<a@ejemplo.test>")
ok(a is not None, "es una activación")
ok(a["pedido"] == "P-99/001" and a["supp"] == "S04" and a["pedido_completo"] == "P-99/001-S04",
   f"pedido y suministro: {a}")
ok(a["po"] == "4500012345-04", f"PO: {a['po']}")
ok(a["cliente"] == "CLIENTE FICTICIO" and a["proyecto"] == "OBRA / FASE 2",
   f"cliente y proyecto: {a['cliente']!r} / {a['proyecto']!r}")
ok(a["entrega"] == "2099-04-30" and a["plazo"] == "26/28 semanas", f"entrega y plazo: {a}")
ok(a["info"] == ["ALCANCE: Dos parejas de bridas", "Igual que el suplemento 03"], f"información: {a['info']}")
ok(a["extras"] == ["PMI", "Líquidos Penetrantes"], f"extras: {a['extras']}")
ok(a["documentacion"] == "Según VDDL acordada", f"documentación, sin el pie legal: {a['documentacion']!r}")
ok(a["remitente"] == "Pepa Ruiz" and a["fecha"] == "10-03-2099", f"quién y cuándo: {a}")

t = act_srv.tarea_de(a)
ok(t["titulo"] == "Abrir pedido P-99/001-S04 · CLIENTE FICTICIO", f"título: {t['titulo']}")
ok(t["origen"] == "activacion" and t["fecha_limite"] == "10-03-2099", f"tarea: {t}")
ok("PO 4500012345-04" in t["descripcion"] and "entrega 30-04-2099 (26/28 semanas)" in t["descripcion"]
   and "Extras: PMI, Líquidos Penetrantes" in t["descripcion"], f"descripción: {t['descripcion']}")
ok(t["activacion"]["po"] == "4500012345-04" and t["activacion"]["entrega"] == "2099-04-30",
   f"lo que rellena Nuevo pedido: {t['activacion']}")

# Sin proyecto («CLIENTE / .»), PO con «PO» delante, PA sin suministro, apartados vacíos
b = act_srv.analizar("ACTIVACIÓN PA-99/125 / OTRO CLIENTE",
                     cuerpo(po="PO 110", de="OTRO CLIENTE / ", pedido="PA-99/125", extras="", doc="No aplica"),
                     COMERCIAL)
ok(b and b["pedido_completo"] == "PA-99/125" and b["supp"] == "", f"PA: {b}")
ok(b["po"] == "110" and b["cliente"] == "OTRO CLIENTE" and b["proyecto"] == "", f"sin proyecto: {b}")
ok(b["extras"] == [] and b["documentacion"] == "No aplica", f"apartados: {b}")
c = act_srv.analizar("ACTIVACIÓN P-99/001-S04 / CLIENTE X", "sin la plantilla", COMERCIAL)
ok(c["pedido_completo"] == "P-99/001-S04" and c["cliente"] == "CLIENTE X",
   f"sin plantilla: el pedido y el cliente salen del asunto: {c}")
ok(act_srv.analizar("RE: ACTIVACIÓN P-99/001-S04 / X", cuerpo(), COMERCIAL) is None,
   "una respuesta no es otra activación")
ok(act_srv.analizar("RV: ACTIVACION P-99/001-S04 / X", cuerpo(), COMERCIAL) is not None,
   "reenviada, y sin tilde, sí")
ok(act_srv.analizar("P-99/001 - Cálculos realizados", cuerpo(), COMERCIAL) is None, "otro asunto: no")
ok(av.BUSQUEDA("ACTIVACIÓN P-99/001-S04 / X") and av.BUSQUEDA("P-99/001 - Cálculos realizados")
   and not av.BUSQUEDA("Oferta 123"), "la búsqueda del buzón coge los dos tipos de aviso")

# ── La pasada por el buzón ────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="activaciones_"))
agenda.AGENDA_FILE = str(tmp / "agenda_data.json")
av.REGISTRO_FILE = str(tmp / "avisos_calculos.json")
base = tmp / "pedidos"
(base / "Año 2099" / "2099 Pedidos" / "P-99-001-S04 - CLIENTE FICTICIO - BRIDAS" / "2-Tecnico").mkdir(parents=True)

hoy = datetime.now().replace(microsecond=0)


def correo(mid, asunto, texto, de=COMERCIAL, cuando=hoy):
    return {"message_id": mid, "subject": asunto, "texto": texto, "from": de,
            "date": cuando.isoformat(), "carpeta": "INBOX"}


ACT = correo("<act@x>", "ACTIVACIÓN P-99/001-S04 / CLIENTE FICTICIO", cuerpo())
BUZONES = {
    BUZON: [ACT, correo("<cal@x>", "P-99/002 - Cálculos realizados", "M:/p/P-99-002-S00 - X - Y/rev 0\n",
                        de="tecnico@ejemplo.test")],
    # Me pusieron en copia: el mismo correo en el buzón personal
    PERSONAL: [ACT, correo("<pa@x>", "ACTIVACIÓN PA-99/125 / OTRO CLIENTE",
                           cuerpo(pedido="PA-99/125", de="OTRO CLIENTE / ", doc="No aplica")),
               correo("<cli@x>", "ACTIVACIÓN P-99/003 / CLIENTE", cuerpo(pedido="P-99/003"),
                      de="alguien@cliente.test")],
}
CUENTAS = [{"user": BUZON}, {"user": PERSONAL, "password": "x"}]


def buscar(texto, days, carpetas, saltar, imap_user=None, imap_pass=None):
    return [c for c in BUZONES[imap_user] if c["message_id"] not in saltar and texto(c["subject"])]


res = av.revisar(owner="JP", docs=[], buscar=buscar, cuentas=CUENTAS, base_pedidos=base)
titulos = sorted(x["titulo"] for x in res["activaciones"])
ok(titulos == ["Abrir pedido P-99/001-S04 · CLIENTE FICTICIO", "Abrir pedido PA-99/125 · OTRO CLIENTE"],
   f"una tarea por activación, aunque llegue a los dos buzones; ninguna de fuera: {titulos}")
ok([x["titulo"] for x in res["nuevas"]] == ["Subir cálculos P-99/002-S00 · rev 0"],
   f"los avisos de cálculos siguen igual: {[x['titulo'] for x in res['nuevas']]}")
ok(res["abiertas"] == [], f"ninguna abierta todavía: {res['abiertas']}")
pend = act_srv.pendientes("JP")
ok(len(pend) == 2, f"dos pendientes: {[x['titulo'] for x in pend]}")

# Segunda pasada: nada nuevo; una activación reenviada (otro Message-ID) tampoco
BUZONES[BUZON].append(correo("<act2@x>", "RV: ACTIVACIÓN P-99/001-S04 / CLIENTE FICTICIO", cuerpo()))
res = av.revisar(owner="JP", docs=[], buscar=buscar, cuentas=CUENTAS, base_pedidos=base)
ok(res["activaciones"] == [], f"reenviada: no es tarea nueva: {res['activaciones']}")

# Borrada a mano: no vuelve
pa = next(x for x in act_srv.pendientes("JP") if x["pedido"] == "PA-99/125")
agenda.delete("tareas", pa["id"])
res = av.revisar(owner="JP", docs=[], buscar=buscar, cuentas=CUENTAS, base_pedidos=base)
ok(res["activaciones"] == [] and len(act_srv.pendientes("JP")) == 1, "la borrada a mano no vuelve")

# Abierto por otro lado: un Planning de antes del correo no cuenta, uno de después sí
doc = base / "Año 2099" / "2099 Pedidos" / "P-99-001-S04 - CLIENTE FICTICIO - BRIDAS" / "2-Tecnico" / "00 DOCUMENTACIÓN"
doc.mkdir()
viejo = doc / "03 PLANNING - P-99-001.xlsm"
viejo.write_bytes(b"x")
antes = time.mktime((hoy - timedelta(days=30)).timetuple())
os.utime(viejo, (antes, antes))
(doc / "01 IMPORTAR DOCUMENTOS - ERP - sin enviar.xlsx").write_bytes(b"x")   # la plantilla tampoco
ok(act_srv.cerrar_abiertas("JP", base_dir=base) == [], "un Planning de antes del correo no la cierra")
(doc / "01 IMPORTAR DOCUMENTOS - ERP - P-99-001.xlsx").write_bytes(b"x")
cerradas = act_srv.cerrar_abiertas("JP", base_dir=base)
ok([x["titulo"] for x in cerradas] == ["Abrir pedido P-99/001-S04 · CLIENTE FICTICIO"],
   f"un VDDL de hoy la cierra: {[x['titulo'] for x in cerradas]}")
ok(cerradas and cerradas[0]["estado"] == "completada" and cerradas[0].get("cerrada_sola"), "completada y dice cuándo")

# Cerrar al procesar en Nuevo pedido: solo ese suministro
for sup in ("S05", "S06"):
    agenda.create_tarea("JP", act_srv.tarea_de(act_srv.analizar(
        f"ACTIVACIÓN P-99/004-{sup} / X", cuerpo(pedido=f"P-99/004-{sup}"), COMERCIAL,
        hoy.isoformat(), f"<{sup}@x>")))
cerradas = act_srv.cerrar("P-99-004", "S05", owner="JP")
ok([x["supp"] for x in cerradas] == ["S05"], f"se cierra el suministro procesado, no el otro: {cerradas}")
ok([x["supp"] for x in act_srv.pendientes("JP")] == ["S06"], "S06 sigue pendiente")

# ── Nuevo pedido se rellena con la activación ────────────────────────────────
import customtkinter as ctk  # noqa: E402

from core.services import erp_tags  # noqa: E402
from gui.views.apertura import AperturaView  # noqa: E402

erp_tags.order_basics = lambda *a, **k: None          # sin ERP
agenda.create_tarea("JP", act_srv.tarea_de(act_srv.analizar(
    "ACTIVACIÓN P-99/001-S04 / CLIENTE FICTICIO", cuerpo(), COMERCIAL, "2099-03-10T09:20:00+01:00", "<v@x>")))
# Una segunda carpeta del mismo pedido, la de S00, que va antes por orden: con la
# activación de S04 no se tiene que elegir esa
(base / "Año 2099" / "2099 Pedidos" / "P-99-001-S00 - CLIENTE FICTICIO - BRIDAS" / "2-Tecnico").mkdir(parents=True)

root = ctk.CTk()
root.withdraw()
vista = AperturaView(root)
vista.pack(fill="both", expand=True)
vista.var_base_dir.set(str(base))
root.update()
lista = vista.lista_act.tareas
ok([x["pedido"] + "-" + x["supp"] for x in lista] == ["P-99/001-S04", "P-99/004-S06"],
   f"la lista de pendientes, la más reciente primero: {[x['titulo'] for x in lista]}")
vista.usar_activacion(next(x for x in lista if x["supp"] == "S04"))
root.update()
ok(vista.var_pedido.get() == "P-99-001" and vista.var_suffix.get() == "S04", "pedido y suministro")
ok(vista.var_sref.get() == "4500012345-04", f"S.REF = PO: {vista.var_sref.get()}")
ok(vista.var_f_entrada.get() == "2099-03-10" and vista.var_f_prevista.get() == "2099-04-30",
   f"fechas: {vista.var_f_entrada.get()} → {vista.var_f_prevista.get()}")
resultado = vista.txt_result.get("1.0", "end")
ok("P-99-001-S04 - CLIENTE FICTICIO" in resultado, f"localiza la carpeta de S04, no la de S00: {resultado}")
ok("✉ Activación de Pepa Ruiz" in resultado and "Extras: PMI" in resultado, "y enseña lo del correo")

# Entrega que no es posterior a la entrada: no se pone y avisa
agenda.create_tarea("JP", act_srv.tarea_de(act_srv.analizar(
    "ACTIVACIÓN P-99/001-S07 / X", cuerpo(pedido="P-99/001-S07", entrega="13-05-2098"), COMERCIAL,
    "2099-03-10T09:20:00+01:00", "<s7@x>")))
vista.recargar_activaciones()
vista.var_f_prevista.set("2099-12-31")
vista.usar_activacion(next(x for x in vista.lista_act.tareas if x["supp"] == "S07"))
ok(vista.var_f_prevista.get() == "2099-12-31", f"la entrega anterior no se pone: {vista.var_f_prevista.get()}")
ok("no es posterior" in vista.txt_result.get("1.0", "end"), "y lo dice")

# Una activación de Almacén (PA): también rellena y localiza su carpeta
(base / "Año 2099" / "2099 Pedidos Almacen" / "PA-99-125 - OTRO CLIENTE - VAINAS" / "2-Tecnico").mkdir(parents=True)
agenda.create_tarea("JP", act_srv.tarea_de(act_srv.analizar(
    "ACTIVACIÓN PA-99/125 / OTRO CLIENTE", cuerpo(pedido="PA-99/125", de="OTRO CLIENTE / ", po="PO 110"),
    COMERCIAL, "2099-03-10T09:20:00+01:00", "<pa2@x>")))
vista.recargar_activaciones()
vista.usar_activacion(next(x for x in vista.lista_act.tareas if x["pedido"] == "PA-99/125"))
resultado = vista.txt_result.get("1.0", "end")
ok(vista.var_pedido.get() == "PA-99-125" and vista.var_suffix.get() == "", "PA: pedido y sin suministro")
ok(vista.var_sref.get() == "110" and vista.var_material.get() == "VAINAS",
   f"PA: S.REF y material de la carpeta: {vista.var_sref.get()} / {vista.var_material.get()}")
ok("2099 Pedidos Almacen" in resultado and "PA-99-125 - OTRO CLIENTE" in resultado,
   f"PA: localiza su carpeta de Almacén: {resultado}")

# Procesado: su activación se cierra y sale de la lista
vista._procesando = ("P-99-001", "S04")
cerradas = vista._cerrar_activacion()
ok([x["supp"] for x in cerradas] == ["S04"], f"al procesar se cierra la suya: {cerradas}")
ok(all(x["supp"] != "S04" for x in vista.lista_act.tareas), "y sale de la lista")
root.destroy()

# ── Abrir un pedido de Almacén y un suministro con carpeta propia ────────────
from openpyxl import Workbook, load_workbook  # noqa: E402

from core.services import apertura as ap  # noqa: E402

ent, prev = datetime(2099, 3, 10), datetime(2099, 4, 30)
pa = ap.OrderSpec(pedido="PA-99/125", fecha_entrada=ent, fecha_prevista=prev, año=2099)
ok(pa.pedido == "PA-99-125" and pa.suffix == "" and pa.es_pa, f"PA normalizado y sin suministro: {pa}")
ok(pa.n_ref == "PA-99/125" and pa.n_ref_short == "PA-99/125", f"N.REF de un PA, como el ERP: {pa.n_ref}")
ok(pa.eipsa_prefix == "PA-99-125", f"los documentos de un PA llevan el PA delante: {pa.eipsa_prefix}")
p = ap.OrderSpec(pedido="P-99-001", suffix="S04", fecha_entrada=ent, fecha_prevista=prev, año=2099)
ok(p.n_ref == "P-99/001-S04" and p.eipsa_prefix == "99-001", f"los P no cambian: {p.n_ref} {p.eipsa_prefix}")
ok(ap.año_de_pedido("PA-99/125") == 2099 and ap.año_de_pedido("P-98-001-S00") == 2098, "año del código")
ok(ap.parse_folder_meta("PA-99-125 - OTRO CLIENTE - VAINAS")
   == {"folder_id": "PA-99-125", "suffix": None, "cliente": "OTRO CLIENTE", "material": "VAINAS"},
   "carpeta de Almacén: cliente y material")

pdir, tdir, ddir = ap.create_folder_structure(pa, base_dir=base, create_if_missing=False)
ok(pdir.name == "PA-99-125 - OTRO CLIENTE - VAINAS" and ddir.is_dir(), f"PA: su carpeta de Almacén: {pdir}")
pdir, _, _ = ap.create_folder_structure(p, base_dir=base, create_if_missing=False)
ok(pdir.name.startswith("P-99-001-S04"), f"S04 se procesa en la carpeta de S04, no en la de S00: {pdir.name}")

plantilla = tmp / "plantilla_erp.xlsx"
wb = Workbook()
wb.active.append(["Nº Doc. EIPSA", "Nº Doc. Cliente", "Nº Pedido", "Título", "Tipo", "Crítico"])
wb.save(plantilla)
vddl, _ = ap.generate_vddl(pa, ddir, selected_folders=[ap.ALL_SUBFOLDERS[0]], erp_template=plantilla)
ws = load_workbook(vddl).active
codigo = ap.SUBFOLDER_INDEX[ap.ALL_SUBFOLDERS[0]].get("eipsa_code")
ok(vddl.name == "01 IMPORTAR DOCUMENTOS - ERP - PA-99-125.xlsx", f"VDDL del PA: {vddl.name}")
ok(ws["C2"].value == "PA-99/125" and (not codigo or ws["A2"].value == f"PA-99-125-{codigo}"),
   f"VDDL del PA: pedido y Nº de documento: {ws['C2'].value} / {ws['A2'].value}")

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
