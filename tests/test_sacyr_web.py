# -*- coding: utf-8 -*-
"""SACYR desde su SharePoint: el enlace del correo, dónde se busca el paquete y
cuándo se baja. Sin red: la descarga se sustituye por una de mentira.

    .venv\\Scripts\\python.exe tests\\test_sacyr_web.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import sacyr, sacyr_web

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg.encode("cp1252", "replace").decode("cp1252"))


# ── El enlace de «Comments» ─────────────────────────────────────────────────
WF = "4000079-PRY001-627-J-C.181752/01-SP-OBTS-000009"
CARPETA = sacyr.folder_name(WF)
RUTA = f"/sites/Proyectos/Documentos Compartidos/Cliente (123)/Outbound/{CARPETA}"

enlace = ("https://contoso.sharepoint.com/:f:/r/sites/Proyectos/Documentos%20Compartidos/"
          f"Cliente%20(123)/Outbound/{CARPETA}?d=w0123abcd&csf=1&web=1&e=AbCdEf")
ok(sacyr_web.carpeta_del_enlace(enlace) ==
   ("https://contoso.sharepoint.com", "/sites/Proyectos", RUTA),
   f"el enlace del correo da sitio y carpeta: {sacyr_web.carpeta_del_enlace(enlace)}")

vista = ("https://contoso.sharepoint.com/sites/Proyectos/Documentos%20Compartidos/Forms/"
         "AllItems.aspx?id=%2Fsites%2FProyectos%2FDocumentos%20Compartidos%2FCliente%20%28123%29"
         f"%2FOutbound%2F{CARPETA}")
ok(sacyr_web.carpeta_del_enlace(vista) == ("https://contoso.sharepoint.com", "/sites/Proyectos", RUTA),
   f"y la vista de la biblioteca, por su «id»: {sacyr_web.carpeta_del_enlace(vista)}")

for malo in ("", "https://ejemplo.com/:f:/r/sites/X/Y/Z",
             "https://contoso.sharepoint.com/sites/Proyectos/Forms/AllItems.aspx",
             "https://contoso.sharepoint.com/:f:/r/personal"):
    ok(sacyr_web.carpeta_del_enlace(malo) is None, f"no es una carpeta: {malo!r}")

ok(sacyr_web._alias("/sites/X/Rock 'n' roll") == "'/sites/X/Rock%20%27%27n%27%27%20roll'",
   f"la comilla se dobla y se codifica: {sacyr_web._alias(chr(39))}")

# ── Dónde se busca y cuándo se baja ─────────────────────────────────────────
DOCS = [{"Doc. Cliente": "PRY001-627-J-C.181752/01-00002", "Rev.": "0"}]
PDF = "V-PRY001-627-J-C.181752_01-002_R0_A.pdf"

tmp = Path(tempfile.mkdtemp())
reales = sacyr.local_root, sacyr_web.cache, sacyr_web.descargar, sacyr_web.disponible
# traer() apunta el último enlace en las preferencias: aquí, en ningún sitio
guardar_real = sacyr.preferences.set_value
guardado = {}
llamadas = []


def descargar_falso(url, nombre):
    llamadas.append((url, nombre))
    destino = sacyr_web.cache() / nombre
    destino.mkdir(parents=True)
    (destino / PDF).write_bytes(b"%PDF-sharepoint")
    return destino


try:
    local, bajado = tmp / "OneDrive", tmp / "sacyr_descargas"
    local.mkdir()
    sacyr.local_root = lambda: local
    sacyr_web.cache = lambda: bajado
    sacyr_web.descargar = descargar_falso
    sacyr_web.disponible = lambda: True
    sacyr.preferences.set_value = guardado.__setitem__

    # Sin paquete en disco, se baja con el enlace del correo
    paquete = sacyr.traer(WF, enlace, DOCS)
    ok(llamadas == [(enlace, CARPETA)], f"se baja una vez, con su nombre: {llamadas}")
    ok(paquete == bajado / CARPETA, f"y queda en la carpeta de la app: {paquete}")
    ok(guardado == {"sacyr_enlace": enlace}, f"y el enlace queda para iniciar sesión: {guardado}")
    ok(sacyr.find_package(WF, DOCS) == bajado / CARPETA, "donde después se encuentra")
    ok(sacyr.file_map(WF, DOCS).get(PDF, {}).get("vendor_number") == DOCS[0]["Doc. Cliente"],
       "y su PDF se empareja con el documento del correo")
    ok(sacyr.docs_con_estado(WF, [dict(DOCS[0])])[0].get("Estado") == "Aprobado",
       "con el estado que dice su nombre (R0_A)")

    # Ya bajado, no se vuelve a pedir
    sacyr.traer(WF, enlace, DOCS)
    ok(len(llamadas) == 1, f"lo que ya está no se vuelve a bajar: {llamadas}")

    # Lo que haya en la carpeta local se usa antes que bajar nada
    shutil.rmtree(bajado)
    llamadas.clear()
    (local / CARPETA).mkdir()
    (local / CARPETA / PDF).write_bytes(b"%PDF-local")
    ok(sacyr.traer(WF, enlace, DOCS) == local / CARPETA and not llamadas,
       f"la carpeta local manda: {llamadas}")

    # Una bajada a medias no pasa por un paquete
    shutil.rmtree(local / CARPETA)
    parcial = bajado / f".{CARPETA}.parcial"
    parcial.mkdir(parents=True)
    (parcial / PDF).write_bytes(b"%PDF-a-medias")
    ok(sacyr.find_package(WF, DOCS) is None, "la carpeta «.parcial» no cuenta")

    # Sin enlace o sin Playwright no se intenta nada
    ok(sacyr.traer(WF, "", DOCS) is None and not llamadas, "sin enlace, nada que bajar")
    sacyr_web.disponible = lambda: False
    ok(sacyr.traer(WF, enlace, DOCS) is None and not llamadas, "sin Playwright, tampoco")

    # Y está configurado con cualquiera de los dos caminos
    sacyr.local_root = lambda: None
    ok(not sacyr.is_configured(), "sin carpeta ni Playwright no hay de dónde sacarlo")
    sacyr_web.disponible = lambda: True
    ok(sacyr.is_configured(), "con Playwright basta, aunque no haya carpeta")
finally:
    sacyr.local_root, sacyr_web.cache, sacyr_web.descargar, sacyr_web.disponible = reales
    sacyr.preferences.set_value = guardar_real
    shutil.rmtree(tmp, ignore_errors=True)

# La excepción de sesión se ve como un error normal de la descarga
ok(issubclass(sacyr_web.SesionNecesaria, RuntimeError), "SesionNecesaria es un RuntimeError")

print("FALLOS:", fallos)
