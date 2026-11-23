# -*- coding: utf-8 -*-
"""Expediente de cliente: correos (lectura con caché, automáticos,
reclamaciones y contactos). No se conecta al buzón: un doble hace de IMAP.

Datos inventados (P-99/…, PO 1099…, @ejemplo.test, @eipsa.test).

    .venv\\Scripts\\python.exe tests\\test_expediente_correos.py
"""
import sys
import tempfile
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import expediente_correos as ec  # noqa: E402

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", str(msg).encode("cp1252", "replace").decode("cp1252"))


def raw(msgid, de, asunto, cuerpo="hola", fecha="Mon, 18 Nov 2099 11:14:00 +0100", para="doc@eipsa.test", cc=""):
    m = EmailMessage()
    m["Message-ID"], m["From"], m["To"], m["Subject"], m["Date"] = msgid, de, para, asunto, fecha
    if cc:
        m["Cc"] = cc
    m.set_content(cuerpo)
    return bytes(m)


class Doble:
    """Fuente de correo falsa: {carpeta: [bytes]}; una carpeta que no está falla."""

    def __init__(self, carpetas):
        self.carpetas = carpetas
        self.bajados = 0

    def ids(self, carpeta, asunto=None):
        if carpeta not in self.carpetas:
            raise RuntimeError(f"No se pudo abrir la carpeta «{carpeta}»")
        out = []
        for i, b in enumerate(self.carpetas[carpeta]):
            mid = [ln for ln in b.decode().splitlines() if ln.startswith("Message-ID:")][0].split(":", 1)[1].strip()
            out.append((str(i), mid))
        return out

    def bajar(self, carpeta, uid):
        self.bajados += 1
        return self.carpetas[carpeta][int(uid)]


class DobleQueFallaSiDescarga(Doble):
    def bajar(self, carpeta, uid):
        raise AssertionError("no debería descargar: está en caché")


def correo(de, asunto, cuerpo="", dia=date(2099, 11, 1), nombre="", para="", cc=""):
    return {"msgid": f"<{de}-{asunto}-{dia}>", "fecha": datetime(dia.year, dia.month, dia.day, 10, 0),
            "de_nombre": nombre, "de_email": de.lower(), "para": para, "cc": cc, "asunto": asunto, "cuerpo": cuerpo,
            "adjuntos": [], "carpeta": "INBOX"}


def test_carpetas():
    ok(ec.carpetas_pedido(["P-99/048"], ["INBOX/P. 2099/P-99-048", "INBOX/P. 2099/P-99-049"]) == ["INBOX/P. 2099/P-99-048"],
       "carpeta del pedido")


def test_leer_cache():
    tmp = Path(tempfile.mkdtemp())
    m1 = raw("<m1@ejemplo.test>", "Ana Ejemplo <ana@ejemplo.test>", "RE: estado")
    m2 = raw("<m2@ejemplo.test>", "Luis Ejemplo <luis@ejemplo.test>", "RE: otro", fecha="Tue, 19 Nov 2099 09:00:00 +0100")
    d = Doble({"A": [m1], "B": [m1, m2]})
    cs, av = ec.leer(["A", "B"], [], tmp / "c.json", fuente=d)
    ok(len(cs) == 2 and av == [], (len(cs), av))                      # el mismo msgid en dos carpetas → una vez
    ok(d.bajados == 2, f"descarga cada correo una vez ({d.bajados})")
    c1 = [c for c in cs if c["msgid"] == "<m1@ejemplo.test>"][0]
    ok(c1["de_email"] == "ana@ejemplo.test" and c1["de_nombre"] == "Ana Ejemplo" and c1["asunto"] == "RE: estado", c1)
    ok(isinstance(c1["fecha"], datetime) and c1["fecha"].date() == date(2099, 11, 18), c1["fecha"])
    cs2, _ = ec.leer(["A", "B"], [], tmp / "c.json", fuente=DobleQueFallaSiDescarga({"A": [m1], "B": [m1, m2]}))
    ok(len(cs2) == 2, "segunda lectura sale de la caché")
    _, av = ec.leer(["NO-EXISTE"], [], tmp / "d.json", fuente=Doble({}))
    ok(av and "NO-EXISTE" in av[0], av)


def test_automatico():
    ok(ec.es_automatico(correo("x@ejemplo.test", "DEV: P-99/048 [eGesdoc]"), "doc@eipsa.test"), "DEV:")
    ok(ec.es_automatico(correo("egesdoc@ejemplo.test", "eGesdoc - New transmittal registered (X)"), "doc@eipsa.test"), "eGesdoc")
    ok(ec.es_automatico(correo("doc@eipsa.test", "P-99/048 / PO: 109901071 // DOCUMENTS PENDING REVIEW"), "doc@eipsa.test"),
       "recordatorio de DocFlow")
    ok(not ec.es_automatico(correo("ana@ejemplo.test", "RE: P-99/048 / PO: 109901071 // DOCUMENTS PENDING REVIEW"), "doc@eipsa.test"),
       "la respuesta del cliente no es automática")


def test_reclamaciones():
    e, c = ec.reclamaciones(
        [correo("doc@eipsa.test", "RE: RECLAIMS: P-99/048 / PO: 109901071 // DOC. UNDER REVIEW",
                cuerpo="De: Ana <ana@ejemplo.test>\nEnviado el: jueves, 27 de noviembre de 2098 15:17\n"
                       "Para: doc@eipsa.test\nAsunto: RE: RECLAIMS: P-99/048 / PO: 109901071 // DOC. UNDER REVIEW",
                dia=date(2099, 5, 13)),
         correo("ana@ejemplo.test", "Comida de navidad", dia=date(2099, 5, 14))],
        ["P-99/048", "1099010710"], "eipsa.test", [{"sent_at": "2099-06-01T10:00:00+00:00"}])
    ok(e == [date(2099, 5, 13), date(2099, 6, 1)] and c == [date(2098, 11, 27)], (e, c))
    e2, _ = ec.reclamaciones([correo("doc@eipsa.test", "RE: x", cuerpo="From: Ana <ana@ejemplo.test>\n"
                                     "Sent: Thursday, January 29, 2099 11:29 AM\nSubject: RE: RECLAIMS: P-99/048 // DOC")],
                             ["P-99/048"], "eipsa.test", [])
    ok(e2 == [], "el correo propio sin asunto de reclamación no cuenta")


def test_contactos():
    k = ec.contactos([correo("sofia@ejemplo.test", "x", dia=date(2099, 11, 9), nombre="Sofía Ejemplo",
                             cuerpo="Gracias.\nSofía Ejemplo\nEJEMPLO ENGINEERING\nDocumentation Expediting\n"
                                    "Calle Falsa 1\nTel. +34 600 000 000"),
                      correo("luis@ejemplo.test", "y", dia=date(2099, 11, 18), nombre="Luis Ejemplo",
                             cc="Marta Ejemplo <marta@ejemplo.test>"),
                      correo("luis@ejemplo.test", "z", dia=date(2099, 11, 2), nombre="Luis Ejemplo",
                             cc="Marta Ejemplo <marta@ejemplo.test>"),
                      correo("doc@eipsa.test", "w", dia=date(2099, 11, 19), nombre="Documentación")],
                     "ejemplo.test", date(2099, 11, 20))
    ok([x["email"] for x in k] == ["luis@ejemplo.test", "sofia@ejemplo.test", "marta@ejemplo.test"], k)
    ok(k[0]["ultimo"] == date(2099, 11, 18) and k[0]["asunto"] == "y" and k[0]["enviados"] == 2, k[0])
    ok(k[0]["msgid"] == "<luis@ejemplo.test-y-2099-11-18>" and k[2]["msgid"] == "", "msgid del último correo enviado")
    ok(k[1]["cargo"] == "Documentation Expediting" and k[1]["telefono"] == "+34 600 000 000", k[1])
    ok(k[2]["ultimo"] is None and k[2]["nombre"] == "Marta Ejemplo" and k[2]["enviados"] == 0, k[2])
    ok(ec.firma("sin firma", "Nadie") == ("", ""), "sin firma")


def test_cita_sin_direccion():
    e, c = ec.reclamaciones([correo("doc@eipsa.test", "RE: x", cuerpo="De: Pepe Ejemplo\nEnviado el: lunes, 2 de marzo de 2099 10:00\n"
                                    "Asunto: RE: RECLAIMS: P-99/048 // DOC. UNDER REVIEW")], ["P-99/048"], "eipsa.test", [])
    ok(e == [] and c == [], f"remitente citado sin dirección: no se sabe de quién es, no cuenta ({e}, {c})")


test_cita_sin_direccion()
test_carpetas()
test_leer_cache()
test_automatico()
test_reclamaciones()
test_contactos()

print("FALLOS:", fallos)
sys.exit(1 if fallos else 0)
