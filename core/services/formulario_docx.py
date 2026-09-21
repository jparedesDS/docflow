"""Escribir en un formulario de Word sin estropearlo.

Los formularios que mandan los clientes (el VPR de SACYR, por ejemplo)
son un Word hecho a mano: tablas con la altura de fila clavada, cuadros de
texto dibujados, logos, marcos de líneas. Aquí se escribe **dentro de sus
casillas**, dejando todo lo demás byte a byte como estaba — el mismo trato que
la plantilla de Planning o las portadas del cliente.

Tres formas de escribir, que son las tres que aparecen en estos formularios:

· `escribir_celda`  — una casilla de una tabla.
· `escribir_caja`   — un cuadro de texto de verdad (el hueco para comentarios).
· `escribir_tras_dibujo` — debajo de un recuadro que es solo un dibujo de
  líneas y no admite texto dentro; es donde escribiría una persona.

Y `altura_flexible`, porque estas plantillas fijan la altura exacta de las
filas: sin eso, cualquier texto de más de dos líneas sale cortado por la mitad.
"""

from __future__ import annotations

import copy
import logging
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from core.services.plantilla_docx import _registrar_prefijos, _serializar

logger = logging.getLogger(__name__)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ESPACIO = "{http://www.w3.org/XML/1998/namespace}space"
ET.register_namespace("w", W)


def w(tag: str) -> str:
    return "{%s}%s" % (W, tag)


class Formulario:
    """Un .docx abierto para rellenar. Se guarda con `guardar(destino)`."""

    def __init__(self, plantilla: Path | str) -> None:
        with zipfile.ZipFile(plantilla) as z:
            self.orden = z.namelist()
            self.partes = {n: z.read(n) for n in self.orden}
        # Los prefijos, antes de parsear: si no, al guardar salen como ns0:,
        # ns5:… y Word dice que el fichero está dañado.
        _registrar_prefijos(self.partes["word/document.xml"])
        self.raiz = ET.fromstring(self.partes["word/document.xml"])
        self.cuerpo = self.raiz.find(w("body"))
        self.tablas = {i: h for i, h in enumerate(self.cuerpo) if h.tag == w("tbl")}
        self.parrafos = {i: h for i, h in enumerate(self.cuerpo) if h.tag == w("p")}

    # ── Escribir ──────────────────────────────────────────────────────────────

    def escribir_celda(self, tabla: int, fila: int, col: int, texto) -> None:
        """Texto en una casilla; se usa su primer párrafo y se quitan los demás."""
        celda = self.tablas[tabla].findall(w("tr"))[fila].findall(w("tc"))[col]
        parrafos = celda.findall(w("p"))
        for extra in parrafos[1:]:
            celda.remove(extra)
        _escribir_parrafo(parrafos[0], texto)

    def escribir_parrafo(self, indice: int, texto) -> None:
        _escribir_parrafo(self.parrafos[indice], texto)

    def escribir_caja(self, indice: int, texto) -> None:
        """Texto DENTRO del cuadro del formulario, no encima de él.

        Escribir en el párrafo que sostiene el cuadro lo borraría. Word guarda
        el mismo cuadro dos veces (la versión moderna y la de respaldo para
        versiones antiguas), así que se escribe en las dos.
        """
        cajas = self.parrafos[indice].findall(".//" + w("txbxContent"))
        if not cajas:
            raise ValueError(f"el párrafo {indice} no lleva ningún cuadro de texto")
        for caja in cajas:
            parrafos = caja.findall(w("p"))
            for extra in parrafos[1:]:
                caja.remove(extra)
            _escribir_parrafo(parrafos[0], texto)

    def escribir_tras_dibujo(self, indice: int, texto) -> None:
        """Texto debajo de un recuadro dibujado, sin borrarlo.

        Algunos recuadros no son cuadros de texto sino un dibujo de líneas y no
        admiten texto dentro. Como el dibujo ocupa la línea entera, lo que se
        añade detrás cae justo debajo: donde lo escribiría una persona.
        """
        parrafo = self.parrafos[indice]
        lineas = texto.split("\n") if isinstance(texto, str) else list(texto)
        primero = parrafo.find(w("r"))
        rpr = _copia_rpr(primero)
        run = ET.SubElement(parrafo, w("r"))
        if rpr is not None:
            run.append(rpr)
        for linea in lineas:
            ET.SubElement(run, w("br"))
            _texto(run, linea)

    def altura_flexible(self, tabla: int, filas) -> None:
        """Deja que esas filas crezcan con su contenido (`hRule=atLeast`)."""
        todas = self.tablas[tabla].findall(w("tr"))
        for i in filas:
            trpr = todas[i].find(w("trPr"))
            if trpr is None:
                continue
            for alto in trpr.findall(w("trHeight")):
                alto.set(w("hRule"), "atLeast")

    # ── Guardar ───────────────────────────────────────────────────────────────

    def guardar(self, destino: Path | str) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        partes = dict(self.partes)
        partes["word/document.xml"] = _serializar(self.raiz, self.partes["word/document.xml"])
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            for nombre in self.orden:
                z.writestr(nombre, partes[nombre])
        logger.debug("Formulario Word escrito: %s", destino.name)
        return destino


# ── Interioridades ────────────────────────────────────────────────────────────

def _copia_rpr(run):
    """La letra de un run, para que lo escrito salga como lo de al lado."""
    if run is not None and run.find(w("rPr")) is not None:
        return copy.deepcopy(run.find(w("rPr")))
    return None


def _texto(run, linea: str) -> None:
    t = ET.SubElement(run, w("t"))
    t.text = linea
    t.set(ESPACIO, "preserve")


def _escribir_parrafo(parrafo, texto) -> None:
    """Deja `texto` en el párrafo conservando su letra y su sangría.

    Varias líneas van con salto dentro del mismo párrafo (`<w:br/>`): así se
    respetan el interlineado y los bordes de la casilla.
    """
    lineas = texto.split("\n") if isinstance(texto, str) else list(texto)
    rpr = _copia_rpr(parrafo.find(w("r")))
    if rpr is None:
        ppr = parrafo.find(w("pPr"))
        if ppr is not None and ppr.find(w("rPr")) is not None:
            rpr = copy.deepcopy(ppr.find(w("rPr")))
    for hijo in list(parrafo):
        if hijo.tag != w("pPr"):
            parrafo.remove(hijo)
    run = ET.SubElement(parrafo, w("r"))
    if rpr is not None:
        run.append(rpr)
    for i, linea in enumerate(lineas):
        if i:
            ET.SubElement(run, w("br"))
        _texto(run, linea)
