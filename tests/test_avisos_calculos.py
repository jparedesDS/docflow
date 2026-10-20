# -*- coding: utf-8 -*-
"""Los correos de «Cálculos realizados» se convierten en tareas de la Agenda:
pedido, suministro, carpeta, revisión y notas; las respuestas se anotan en la
tarea, lo ya enviado no crea nada y lo que se envía después la cierra.

Datos inventados (pedidos P-99/…, dominio ejemplo.test): nada de clientes reales.

    .venv\\Scripts\\python.exe tests\\test_avisos_calculos.py
"""
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import agenda, avisos_calculos as av  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


TECNICO = "pepe-perez@ejemplo.test"
BUZON = "documentacion@ejemplo.test"
RUTA = "M:/pedidos/Año 2099/P-99-001-S02 - CLIENTE FICTICIO - CAUDAL/2-Tecnico/env cal/rev 1-2"
CUERPO = (
    "Hola a todos.\n\n"
    "Ya están hechos los cálculos para el pedido p-99/001-S02 y se encuentran en la siguiente carpeta:\n"
    f"{RUTA} <file:///{RUTA.replace(' ', '%20')}>\n\n"
    "Portadas hechas.\n"
    "ERP actualizado con los datos.\n"
    "OJO con el nº de documento del cliente.\n\n"
    "Si necesitáis algo, avisadme.\n"
    "Un saludo.\n"
    "NOTA LEGAL: texto que no es una nota.\n"
)

# ── Leer un aviso ─────────────────────────────────────────────────────────────
a = av.analizar("P-99/001-s02- Cálculos realizados", CUERPO, TECNICO,
                "2099-03-10T09:20:00+01:00", "<a@ejemplo.test>")
ok(a and a["tipo"] == "aviso", f"es un aviso: {a}")
ok(a["pedido"] == "P-99/001" and a["supp"] == "S02" and a["pedido_completo"] == "P-99/001-S02",
   f"pedido y suministro: {a['pedido_completo']}")
ok(a["carpeta"] == RUTA.replace("/", "\\"), f"carpeta con barras de Windows y sin el enlace: {a['carpeta']}")
ok(a["otras_carpetas"] == [], f"el enlace file:// no cuenta como otra carpeta: {a['otras_carpetas']}")
ok(a["rev"] == "1-2", f"revisión de la carpeta: {a['rev']}")
ok(a["cliente"] == "CLIENTE FICTICIO - CAUDAL", f"cliente de la carpeta: {a['cliente']}")
ok(a["notas"] == ["Portadas hechas.", "OJO con el nº de documento del cliente."],
   f"notas, sin saludo, sin la frase de siempre ni lo de después de la despedida: {a['notas']}")
ok(a["remitente"] == "Pepe Perez" and a["fecha"] == "10-03-2099", f"quién y cuándo: {a}")
t = av.tarea_de(a)
ok(t["titulo"] == "Subir cálculos P-99/001-S02 · rev 1-2", f"título: {t['titulo']}")
ok(t["fecha_limite"] == "10-03-2099" and t["origen"] == "calculos", f"tarea: {t}")

# El suministro lo dice la carpeta aunque el asunto no lo lleve
b = av.analizar("p-99/002 - Cálculos realizados // OBRA",
                "Ya están hechos los cálculos para el pedido p-99/002 y se encuentran en la siguiente carpeta:\n"
                "M:\\pedidos\\P-99-002 - S00 - OTRO CLIENTE - NIVEL\\2-Tecnico\\env cal\n", TECNICO)
ok(b and b["pedido_completo"] == "P-99/002-S00" and b["rev"] == "", f"suministro de la carpeta: {b}")
ok(b["cliente"] == "OTRO CLIENTE - NIVEL", f"cliente con «P-99-002 - S00 - …»: {b['cliente']}")
ok(av.analizar("PA-99/104 - Cálculos realizados", "", TECNICO)["pedido_completo"] == "PA-99/104",
   "pedido PA sin suministro ni carpeta")
ok(av.analizar("P-99/001 - Envío de documentación", CUERPO, TECNICO) is None, "otro asunto: no es aviso")
ok(av.analizar("Cálculos realizados", "sin pedido", TECNICO) is None, "sin pedido: no es aviso")

# Una respuesta: actualización, sin la firma ni el correo citado
r = av.analizar("RE: P-99/001 - Cálculos realizados",
                "ACTUALIZACIÓN.\nHe incluido en la carpeta de la revisión 2 los planos.\n"
                "Pepe Pérez Gómez\nTlf.: (+00) 000 000\nDe: alguien\nYa están hechos…", TECNICO)
ok(r and r["tipo"] == "actualizacion", f"RE: es una actualización: {r}")
ok(r["notas"] == ["He incluido en la carpeta de la revisión 2 los planos."], f"solo lo nuevo: {r['notas']}")
# Cuenta cuyo nombre es la dirección otra vez: el nombre sale del correo y corta la firma
r = av.analizar("RE: P-99/001 - Cálculos realizados", "Se puede enviar.\nAna Gil\nJefa de Técnico",
                '"ana-gil ana-gil" <ana-gil@ejemplo.test>')
ok(r["remitente"] == "Ana Gil" and r["notas"] == ["Se puede enviar."], f"firma de «ana-gil ana-gil»: {r}")

# ── Las carpetas que se miran ─────────────────────────────────────────────────
ano = date.today().year
mirar = av.carpetas_de_pedidos(["INBOX", f"INBOX/P. {ano}/P-99-001", f"INBOX/PA. {ano}/PA-99-104",
                                "INBOX/P. 2019/P-19-001", "Sent", "Clientes"])
ok(mirar == ["INBOX", f"INBOX/P. {ano}/P-99-001", f"INBOX/PA. {ano}/PA-99-104"],
   f"bandeja y carpetas del año: {mirar}")

# ── La pasada por el buzón ────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="avisos_"))
agenda.AGENDA_FILE = str(tmp / "agenda_data.json")
av.REGISTRO_FILE = str(tmp / "avisos_calculos.json")

hoy = datetime.now().replace(microsecond=0)
hace3 = hoy - timedelta(days=3)


def correo(mid, asunto, texto, de=TECNICO, cuando=hoy):
    return {"message_id": mid, "subject": asunto, "texto": texto, "from": de,
            "date": cuando.isoformat(), "carpeta": "INBOX"}


BUZON_FALSO = [
    correo("<r@x>", "RE: P-99/001-S02 - Cálculos realizados",
           "ACTUALIZACIÓN.\nAñadido el plano que faltaba.\nSaludos.", cuando=hoy + timedelta(minutes=5)),
    correo("<a@x>", "P-99/001-s02- Cálculos realizados", CUERPO),
    correo("<b@x>", "P-99/003 - Cálculos realizados",
           "M:/pedidos/P-99-003-S00 - X - Y/2-Tecnico/rev 0\n", cuando=hace3),
    correo("<c@x>", "P-99/004 - Cálculos realizados", "", de="cliente@otro.test"),
    correo("<d@x>", "RE: P-99/005 - Cálculos realizados", "Nada", de=BUZON),
]
llamadas = []


def buscar(texto, days, carpetas, saltar):
    llamadas.append(carpetas)
    return [c for c in BUZON_FALSO if c["message_id"] not in saltar]


DOCS = [
    # P-99/003: sus cálculos ya salieron después del aviso → no es tarea
    {"Nº Pedido": "P-99/003-S00", "Tipo Doc.": "Cálculo y plano", "Fecha Env. Doc.": hoy.strftime("%d/%m/%Y")},
    # P-99/001-S02: enviado ANTES del aviso (otra revisión) → sigue pendiente
    {"Nº Pedido": "P-99/001-S02", "Tipo Doc.": "Cálculos", "Fecha Env. Doc.": hace3.strftime("%d/%m/%Y")},
    # Un plano de P-99/001-S02 enviado hoy no cierra la de cálculos
    {"Nº Pedido": "P-99/001-S02", "Tipo Doc.": "Planos", "Fecha Env. Doc.": hoy.strftime("%d/%m/%Y")},
]

res = av.revisar(completo=False, owner="JP", docs=DOCS, buscar=buscar, buzon=BUZON)
ok(llamadas[-1] == "INBOX", f"pasada rápida: solo la bandeja: {llamadas[-1]}")
ok([x["titulo"] for x in res["nuevas"]] == ["Subir cálculos P-99/001-S02 · rev 1-2"],
   f"solo una tarea nueva (ni lo enviado, ni un cliente, ni lo propio): {[x['titulo'] for x in res['nuevas']]}")
ok(len(res["actualizadas"]) == 1, f"la respuesta se anota (aunque llegue antes en la lista): {res['actualizadas']}")
tareas = agenda.get_tareas("JP")
ok(len(tareas) == 1 and tareas[0]["actualizaciones"][0]["texto"] == "Añadido el plano que faltaba.",
   f"en la Agenda, con su actualización: {tareas}")
ok(tareas[0]["carpeta"].endswith("rev 1-2") and tareas[0]["source_msgid"] == "<a@x>", "con carpeta y Message-ID")
ok(res["cerradas"] == [], "nada que cerrar todavía")

res = av.revisar(completo=True, owner="JP", docs=DOCS, buscar=buscar, buzon=BUZON)
ok(callable(llamadas[-1]), "pasada completa: también las carpetas de los pedidos")
ok(not res["nuevas"] and not res["actualizadas"], f"lo visto no se repite: {res}")

agenda.delete("tareas", tareas[0]["id"])
res = av.revisar(completo=True, owner="JP", docs=DOCS, buscar=buscar, buzon=BUZON)
ok(not res["nuevas"] and agenda.get_tareas("JP") == [], "una tarea borrada no vuelve")

# Llega otro aviso; luego sus cálculos salen al cliente → se cierra sola
BUZON_FALSO.append(correo("<e@x>", "P-99/006 - Cálculos realizados",
                          "M:/pedidos/P-99-006-S01 - X - Y/2-Tecnico/rev 0\n"))
res = av.revisar(owner="JP", docs=DOCS, buscar=buscar, buzon=BUZON)
ok(len(res["nuevas"]) == 1 and res["nuevas"][0]["supp"] == "S01", f"aviso nuevo: {res['nuevas']}")
DOCS.append({"Nº Pedido": "P-99/006-S01", "Tipo Doc.": "Cálculos",
             "Fecha Env. Doc.": hoy.strftime("%d/%m/%Y")})
res = av.revisar(owner="JP", docs=DOCS, buscar=buscar, buzon=BUZON)
ok(len(res["cerradas"]) == 1, f"enviados al cliente: tarea cerrada: {res['cerradas']}")
t6 = agenda.get_tareas("JP")[0]
ok(t6["estado"] == "completada" and t6.get("cerrada_sola"), f"completada y se sabe por qué: {t6}")

# Sin seguimiento de documentos (docs=None) se crea igual, y no se cierra nada
BUZON_FALSO.append(correo("<f@x>", "P-99/003 - Cálculos realizados", "", cuando=hoy))
res = av.revisar(owner="JP", docs=None, buscar=buscar, buzon=BUZON)
ok(len(res["nuevas"]) == 1 and res["cerradas"] == [], f"sin seguimiento: {res}")

# ── Sincronizar con Documentos no pierde las tareas nuevas ───────────────────
agenda.AGENDA_FILE = str(tmp / "agenda_sync.json")
agenda.sync_tareas("JP", [{"Nº Pedido": "P-99/001", "Nº Doc. EIPSA": "99-001-CAL-0001", "Nº Revisión": 0,
                           "Estado": "Sin Enviar", "Título": "Uno"}])
agenda.sync_tareas("JP", [{"Nº Pedido": "P-99/001", "Nº Doc. EIPSA": "99-001-CAL-0002", "Nº Revisión": 0,
                           "Estado": "Sin Enviar", "Título": "Dos"}])
sync = agenda.get_tareas("JP")
ok(len(sync) == 2 and {x["estado"] for x in sync} == {"completada", "pendiente"},
   f"la que se completa y la que se crea en la misma sincronización, las dos: {sync}")

# ── En pantalla ───────────────────────────────────────────────────────────────
import customtkinter as ctk  # noqa: E402

from gui.views.agenda import AgendaView  # noqa: E402
from gui.widgets.notifier import NotificationManager  # noqa: E402

agenda.AGENDA_FILE = str(tmp / "agenda_data.json")
root = ctk.CTk()
root.geometry("1300x800+20+20")
vista = AgendaView(root)
vista.pack(fill="both", expand=True)
vista.var_hechas.set(True)
vista._toggle_hechas()
root.update()


def textos(w):
    out = []
    for h in w.winfo_children():
        try:
            out.append(str(h.cget("text")))
        except Exception:
            pass
        out += textos(h)
    return out


vistos = textos(vista)
ok("📁" in vistos, "la tarea de aviso tiene botón para abrir la carpeta")
ok(any(x.startswith("✉ Cálculos listos · Pepe Perez") for x in vistos), f"y dice de quién viene: {vistos}")
ok("Subir cálculos P-99/006-S01 · rev 0" in vistos, "con su título")

pulsado = []
avisos = NotificationManager(root)
avisos.notify("Cálculos listos", "prueba", native=False, on_click=lambda: pulsado.append(1))
root.update()
tarjeta = avisos._active[-1]
tarjeta._canvas.event_generate("<Button-1>", x=5, y=5)     # el clic cae en el lienzo del marco
root.update()
ok(pulsado == [1] and tarjeta not in avisos._active, "pulsar el aviso hace su acción y lo quita")
root.destroy()

print("FALLOS:", fallos)
