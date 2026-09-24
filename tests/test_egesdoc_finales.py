# -*- coding: utf-8 -*-
"""Documentos en Final de eGesDoc: lista, nombre del fichero y reanudación.

    docflow_env\\Scripts\\python.exe tests\\test_egesdoc_finales.py

Sin tocar el portal: se le pone delante una sesión de mentira que contesta lo
que contesta el de verdad. Lo que se comprueba aquí es lo que costó descubrir —
que sin `naReturned` la tabla vuelve vacía sin decir nada, que el fichero hay
que renombrarlo porque el portal lo bautiza con su id interno, y que una
segunda pasada no vuelve a pedir lo que ya está bajado.
"""
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

import finales_egesdoc as finales_cli  # noqa: E402  (el guion de tools/)

from core.services import egesdoc  # noqa: E402

fallos = 0


def comprobar(condicion: bool, texto: str) -> None:
    global fallos
    if condicion:
        print(f"  OK    {texto}")
    else:
        fallos += 1
        print(f"  FALLO {texto}")


class Respuesta:
    def __init__(self, *, json=None, headers=None, contenido=b"", status=200):
        self._json = json
        self.headers = headers or {}
        self._contenido = contenido
        self.status_code = status
        self.ok = status < 400

    def json(self):
        if self._json is None:
            raise ValueError("no es json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, _n):
        yield self._contenido

    def close(self):
        pass


class Sesion:
    """Sesión de mentira: apunta lo que se le pide y contesta lo que se le diga."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.peticiones = []

    def post(self, url, data=None, **kw):
        self.peticiones.append((url, dict(data or {})))
        return self.respuestas[url.rsplit("/", 1)[-1]]

    def get(self, url, **kw):
        self.peticiones.append((url, {}))
        return self.respuestas[url.rsplit("/", 1)[-1]]


FILA = {"Id": 870886, "DocumentId": 413929, "VendorNumber": " 26-001-DOS-0001 ",
        "TrNumber": "", "VendorTitle": "WELDING DOSSIER", "TypeDocCode": "DOS-0001",
        "DocumentStatus": "Final", "ReturnStatus": "F - REVIEWED WITHOUT COMMENTS",
        "ReturnDate": "/Date(1774911600000)/"}

# ── La lista ─────────────────────────────────────────────────────────────────
s = Sesion({"GetPagedVddlRecordsFromView": Respuesta(json={"data": [FILA]})})
docs = egesdoc.list_documents(s)
enviado = s.peticiones[0][1]

comprobar(str(enviado.get("naReturned")) == "2",
          "se manda naReturned=2, sin lo cual el portal contesta una tabla vacía")
comprobar(enviado.get("SummaryFilter") == "Finals", "se pide el recuadro «Finals»")
comprobar(len(docs) == 1 and docs[0]["code"] == "26-001-DOS-0001",
          "el código viene sin los espacios que mete el portal")
comprobar(docs[0]["document_id"] == 413929,
          "el id de la descarga es DocumentId, no el de la línea del VDDL")
comprobar(docs[0]["return_date"] is not None and docs[0]["return_date"].year == 2026,
          "la fecha de devolución se entiende")

# ── La descarga ──────────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp())
s = Sesion({"DownloadCommentedDocumentAjax": Respuesta(json={"result": True}),
            "DownloadExportedDocumentFromPath": Respuesta(
                headers={"Content-Disposition": 'attachment; filename=V-1000100010-0111.pdf',
                         "Content-Type": "application/octet-stream"},
                contenido=b"%PDF-1.7\nfalso")})
ruta = egesdoc.download_commented_file(s, 413929, tmp, "26-001-DOS-0001")
comprobar(ruta is not None and ruta.name == "26-001-DOS-0001.pdf",
          "el fichero se guarda con el código, no con el id interno de TR")

# Sin comentado: el portal dice result=false y no hay nada que bajar
s = Sesion({"DownloadCommentedDocumentAjax": Respuesta(json={"result": False})})
comprobar(egesdoc.download_commented_file(s, 1, tmp) is None,
          "un documento sin fichero comentado devuelve None, no un error")

# Sesión caída: el portal contesta su página de entrada con un 200 tan tranquilo
s = Sesion({"DownloadCommentedDocumentAjax": Respuesta(json={"result": True}),
            "DownloadExportedDocumentFromPath": Respuesta(
                headers={"Content-Type": "text/html; charset=utf-8"},
                contenido=b"<html>login</html>")})
try:
    egesdoc.download_commented_file(s, 2, tmp)
    comprobar(False, "una página HTML en vez del fichero se detecta")
except egesdoc.SesionCaducada:
    comprobar(True, "una página HTML en vez del fichero se detecta")
comprobar(not list(tmp.glob("*.html")) and len(list(tmp.iterdir())) == 1,
          "y no deja en la carpeta un «PDF» que era la página de entrada")

# ── La reanudación ───────────────────────────────────────────────────────────
(tmp / "26-001-ESP-0001 (2).pdf").write_bytes(b"%PDF-")
(tmp / "26-001-ESP-00010.pdf").write_bytes(b"%PDF-")
comprobar(egesdoc.ya_bajado(tmp, "26-001-DOS-0001") is not None,
          "lo ya bajado no se vuelve a pedir")
comprobar(egesdoc.ya_bajado(tmp, "26-001-ESP-0001") is not None,
          "tampoco la copia «(2)» que deja la regla de no pisar nada")
comprobar(egesdoc.ya_bajado(tmp, "26-001-ESP-0002") is None,
          "pero el documento de al lado sigue pendiente")
comprobar(egesdoc.ya_bajado(tmp, "26-001-ESP-0001").name != "26-001-ESP-00010.pdf",
          "un código más largo no se confunde con el corto")

# ── El nombre del fichero ────────────────────────────────────────────────────
# Guardar y buscar tienen que coincidir: si uno mira por el código y el otro
# guardó «documento-413929», lo bajado se daría por pendiente para siempre.
sin_codigo = {"code": "", "document_id": 413929}
comprobar(egesdoc.nombre_de(sin_codigo) == "documento-413929",
          "un documento sin código del proveedor se guarda por su id")
(tmp / "documento-413929.pdf").write_bytes(b"%PDF-")
comprobar(egesdoc.ya_bajado(tmp, egesdoc.nombre_de(sin_codigo)) is not None,
          "y se le reconoce después con ese mismo nombre")

# Un código con una barra no puede acabar en una ruta imposible
s = Sesion({"DownloadCommentedDocumentAjax": Respuesta(json={"result": True}),
            "DownloadExportedDocumentFromPath": Respuesta(
                headers={"Content-Disposition": "attachment; filename=V-1.pdf",
                         "Content-Type": "application/octet-stream"},
                contenido=b"%PDF-1.7\nfalso")})
ruta = egesdoc.download_commented_file(s, 9, tmp, "P-26/004-PRO-001")
comprobar(ruta is not None and ruta.name == "P-26_062-PRO-001.pdf",
          f"la barra del código se sustituye, no se corta: {ruta and ruta.name}")

# ── El bucle: reintentos, errores que dejan de serlo y la sesión perdida ─────
GUARDADO = (egesdoc.find_project_for_po, egesdoc.enter_po, egesdoc.list_documents,
            egesdoc.download_commented_file, egesdoc.login, time.sleep)
DOCS = [{"code": "26-001-ESP-0001", "document_id": 1, "title": "UNO"},
        {"code": "26-001-ESP-0002", "document_id": 2, "title": "DOS"}]
try:
    egesdoc.find_project_for_po = lambda *a, **k: "10002"
    egesdoc.enter_po = lambda *a, **k: None
    egesdoc.list_documents = lambda *a, **k: list(DOCS)
    egesdoc.time.sleep = lambda _s: None

    # Falla un intento y el siguiente dice que no hay comentado: no es un error
    intentos = []

    def falla_y_luego_nada(_s, document_id, dest, name=""):
        intentos.append(document_id)
        if intentos.count(document_id) == 1:
            raise egesdoc.PortalOcupado("eGesDoc da error 500 al preparar el comentado")
        return None

    egesdoc.download_commented_file = falla_y_luego_nada
    vacia = Path(tempfile.mkdtemp())
    filas = egesdoc.download_final_documents("1000100010", vacia, session=object())
    comprobar([f["error"] for f in filas] == ["", ""],
              f"un fallo que luego se resuelve no queda como problema: {[f['error'] for f in filas]}")
    comprobar([f["file"] for f in filas] == ["", ""],
              "y sin fichero comentado tampoco se inventa uno")

    # La sesión se cae y no se puede volver a entrar: se para y se devuelve lo hecho
    def sesion_perdida(_s, document_id, dest, name=""):
        raise egesdoc.SesionCaducada("eGesDoc devolvió una página en vez del fichero")

    def no_deja_entrar(_s=None):
        raise egesdoc.PortalOcupado("eGesDoc está caído (HTTP 503)")

    egesdoc.download_commented_file = sesion_perdida
    egesdoc.login = no_deja_entrar
    filas = egesdoc.download_final_documents("1000100010", vacia, session=object())
    comprobar(len(filas) == 1, f"se corta en el primero en vez de insistir 345 veces: {len(filas)}")
    comprobar("no se pudo volver a entrar" in filas[0]["error"],
              f"y dice por qué: {filas[0]['error']}")
finally:
    (egesdoc.find_project_for_po, egesdoc.enter_po, egesdoc.list_documents,
     egesdoc.download_commented_file, egesdoc.login, egesdoc.time.sleep) = GUARDADO


# ── La línea de comandos ─────────────────────────────────────────────────────
opts = finales_cli.opciones(["1000100010"])
comprobar(opts["po"] == "1000100010" and opts["limite"] == 0, "el PO solo")
opts = finales_cli.opciones(["1000100010", "--max", "5"])
comprobar(opts["limite"] == 5, "«--max 5» son cinco documentos")
opts = finales_cli.opciones(["1000100010", "--max", r"M:\pedidos\comentados"])
comprobar(str(opts["destino"]) == r"M:\pedidos\comentados",
          f"«--max» sin número no se come la carpeta destino: {opts['destino']}")
opts = finales_cli.opciones(["1000100010", "--listar"])
comprobar(opts["listar"] and not opts["limite"], "«--listar» solo mira")


print(f"FALLOS: {fallos}")
sys.exit(1 if fallos else 0)
