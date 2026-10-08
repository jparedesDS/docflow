# -*- coding: utf-8 -*-
"""Portal PRODOC (Wood): el enlace del correo y la bajada del paquete.

Lo que se comprueba aquí es lo que el portal ha ido cambiando sin avisar: el
correo «para información» que no trae nada, el zip que todavía se está
preparando, el enlace caducado y —desde octubre de 2026— la página puente que
arma la dirección del zip con JavaScript.
"""
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.services import prodoc  # noqa: E402

fallos = 0


def ok(condicion: bool, texto: str) -> None:
    global fallos
    if condicion:
        print(f"  OK    {texto}")
    else:
        fallos += 1
        print(f"  FALLO {texto}")


# ── El asunto ─────────────────────────────────────────────────────────────────
ASUNTO = ("Wood Transmittal TL-2401HG04A-VDC-6696 -  1DD5598E - Moeve Energy Park "
          "La Rabida - Huelva  - CALCULATIONS - PO: 7011419725 - Vendor: EIPSA, S.A.")
datos = prodoc.parse_subject(ASUNTO)
ok(datos["code"] == "TL-2401HG04A-VDC-6696", f"el código sale del asunto: {datos['code']}")
ok(datos["po"] == "7011419725", f"y el PO del cliente: {datos['po']}")

# ── Los enlaces del pie del correo ────────────────────────────────────────────
BASE = ("https://Intranet.fwiberia.fwc.com/Intranet/aplicaciones/s1015/VndrDocs"
        "/DistributionVndr/vndDownloadZIPMail.cfm?")
CORREO = f"""
<table><tr><td>
  <a href="{BASE}TOKEN1ra">Download<br> All 1st Files</a>
  <a href="{BASE}TOKEN1y2">Download<br> All 1st+2nd Files</a>
</td></tr></table>"""

ok(prodoc.download_link(CORREO) == f"{BASE}TOKEN1ra",
   "se coge el «1st Files», que es el PDF devuelto y no el nativo que mandamos")
ok(prodoc.has_download(CORREO), "y el correo cuenta como descargable")

SOLO_1Y2 = f'<a href="{BASE}TOKEN1y2">Download All 1st+2nd Files</a>'
ok(prodoc.download_link(SOLO_1Y2) == f"{BASE}TOKEN1y2",
   "si solo está el «1st+2nd», se tira de ese")

ok(not prodoc.has_download("<p>2I - FOR INFORMATION ONLY</p>"),
   "el aviso «para información» no trae nada que bajar y no es un fallo")

# ── La página puente ──────────────────────────────────────────────────────────
# El portal redirige a una página cuyo script pega «https:» al ctl=, lo corta en
# «.zip» y pulsa el enlace. Sin seguirla a mano, el transmittal no bajaba
# (TL-2401HG04A-VDC-6696 y -6697, el 2026-10-08).
PUENTE = ("https://intranet.fwiberia.fwc.com/Intranet/aplicaciones/s1015/downloadDocs"
          "/vndDownloadZIPMail.htm?ctl=//intranet.fwiberia.fwc.com/Intranet/aplicaciones"
          "/s1015/DownLoadDocs/VndrDocsDownload/E20C3516%5CTL-2401HG04A-VDC-6696_1.zip")
ZIP_REAL = ("https://intranet.fwiberia.fwc.com/Intranet/aplicaciones/s1015/DownLoadDocs"
            "/VndrDocsDownload/E20C3516%5CTL-2401HG04A-VDC-6696_1.zip")

ok(prodoc._url_del_zip(PUENTE) == ZIP_REAL,
   f"la URL del zip sale del ctl=: {prodoc._url_del_zip(PUENTE)}")
ok("%5C" in prodoc._url_del_zip(PUENTE),
   "el separador del portal se deja como «%5C»: descodificarlo rompe la petición")
ok(prodoc._url_del_zip(f"{BASE}TOKEN1ra") == "",
   "una respuesta normal del .cfm no se confunde con la puente")
ok(prodoc._url_del_zip("https://x/y.htm?ctl=https://h/a.zip&z=1") == "https://h/a.zip",
   "si el ctl= ya trae protocolo, no se le pega otro")
ok(prodoc._url_del_zip("") == "" and prodoc._url_del_zip("https://x/y.htm?ctl=nada") == "",
   "y sin ctl= o sin .zip no se inventa ninguna dirección")


# ── La bajada entera, con un portal de mentira ────────────────────────────────
class Respuesta:
    def __init__(self, *, url, ctype, cuerpo=b"", status=200):
        self.url = url
        self.headers = {"Content-Type": ctype}
        self._cuerpo = cuerpo
        self.status_code = status
        self.ok = status < 400

    @property
    def text(self):
        return self._cuerpo.decode("utf-8", "replace")

    def iter_content(self, _n):
        yield self._cuerpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        pass


def zip_de_prueba() -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("V-2401HG04A-2206-300-CFFE-2002-CAL-001.PDF", b"%PDF-1.4 comentado")
    return buf.getvalue()


PAGINA_PUENTE = b"""<html><body>
<a href="ss" id="download"></a>
<script type="text/javascript">
  var myParam = location.search.split('ctl=')[1];
  var i= myParam.search(".zip");
  myParamres = myParam.substr(0,i+4);
  document.getElementById('download').href='https:'+myParamres;
  document.getElementById('download').click();
</script></body></html>"""
PAGINA_ESPERA = (b"<html><script>alert('Transmittal file process running, please try "
                 b"it again in a few minutes.')</script></html>")
PAGINA_CADUCADA = b"<html><body>Error Executing Database Query</body></html>"


class Portal:
    """Contesta lo que se le diga segun la URL que se le pida."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.pedidas = []

    def get(self, url, **kw):
        self.pedidas.append(url)
        for patron, hacer in self.respuestas:
            if patron in url:
                return hacer()
        raise AssertionError(f"el portal de prueba no sabe qué contestar a {url}")

    def close(self):
        pass


tmp = Path(tempfile.mkdtemp())
sesion_real = prodoc.http.session
dormir_real = prodoc.time.sleep
esperas = []
try:
    prodoc.time.sleep = esperas.append

    # 1) El camino de hoy: el .cfm deja en la puente y el zip está en el ctl=
    portal = Portal([
        (".cfm?", lambda: Respuesta(url=PUENTE, ctype="text/html", cuerpo=PAGINA_PUENTE)),
        ("VndrDocsDownload", lambda: Respuesta(url=ZIP_REAL, ctype="application/x-zip-compressed",
                                               cuerpo=zip_de_prueba())),
    ])
    prodoc.http.session = lambda *a, **k: portal
    ruta = prodoc.download(f"{BASE}TOKEN1ra", tmp, "TL-2401HG04A-VDC-6696")
    ok(ruta.name == "TL-2401HG04A-VDC-6696.zip", f"el paquete queda como el código: {ruta.name}")
    ok(zipfile.is_zipfile(ruta), "y es un zip de verdad")
    ok(portal.pedidas[-1] == ZIP_REAL, f"se ha seguido a la URL del zip: {portal.pedidas[-1]}")
    with zipfile.ZipFile(ruta) as zf:
        ok(zf.namelist() == ["V-2401HG04A-2206-300-CFFE-2002-CAL-001.PDF"],
           "con el PDF comentado dentro, nombrado con el código del documento")

    # 2) El zip todavía no está hecho: se insiste y acaba saliendo
    intentos = {"n": 0}

    def espera_y_luego_puente():
        intentos["n"] += 1
        if intentos["n"] == 1:
            return Respuesta(url=f"{BASE}TOKEN1ra", ctype="text/html", cuerpo=PAGINA_ESPERA)
        return Respuesta(url=PUENTE, ctype="text/html", cuerpo=PAGINA_PUENTE)

    portal = Portal([
        (".cfm?", espera_y_luego_puente),
        ("VndrDocsDownload", lambda: Respuesta(url=ZIP_REAL, ctype="application/x-zip-compressed",
                                               cuerpo=zip_de_prueba())),
    ])
    prodoc.http.session = lambda *a, **k: portal
    esperas[:] = []
    ruta = prodoc.download(f"{BASE}TOKEN1ra", tmp, "TL-2401HG04A-VDC-6680")
    ok(ruta.name == "TL-2401HG04A-VDC-6680.zip",
       f"si el portal lo está preparando, se reintenta y baja: {ruta.name}")
    ok(esperas == [prodoc.ZIP_WAIT], f"esperando entre medias: {esperas}")

    # 3) Enlace caducado: se dice en cristiano y no se guarda un HTML
    portal = Portal([(".cfm?", lambda: Respuesta(url=f"{BASE}TOKEN1ra", ctype="text/html",
                                                 cuerpo=PAGINA_CADUCADA))])
    prodoc.http.session = lambda *a, **k: portal
    try:
        prodoc.download(f"{BASE}TOKEN1ra", tmp, "TL-2401HG04A-VDC-0001")
        ok(False, "un enlace caducado tiene que fallar")
    except RuntimeError as exc:
        ok("caducan al mes" in str(exc), f"y explicar que caducan al mes: {exc}")
    ok(not (tmp / "TL-2401HG04A-VDC-0001.zip").exists(),
       "sin dejar un HTML disfrazado de zip")
finally:
    prodoc.http.session = sesion_real
    prodoc.time.sleep = dormir_real
    shutil.rmtree(tmp, ignore_errors=True)

print(f"FALLOS: {fallos}")
sys.exit(1 if fallos else 0)
