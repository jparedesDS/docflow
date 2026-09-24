"""Los datos de tu empresa, fuera del código.

El repositorio es público y aquí no pinta nada quién trabaja contigo, para qué
clientes ni qué pedidos lleva cada uno. Todo eso vive en
``state/organizacion.json`` —que git ignora— y se rellena desde
**Ajustes ▸ Organización**, así que una instalación nueva arranca en blanco y
cada cual pone lo suyo. Sin nada puesto la app funciona: lo que hace el ERP
sigue saliendo del ERP, y estas tablas son el respaldo y los nombres bonitos.

Qué guarda cada una:

``equipo``        iniciales → {nombre, emails}. Quién recibe los avisos y de
                  dónde salen las cuentas de la app.
``clientes``      los 5 primeros dígitos del PO → cliente o proyecto: lo que
                  convierte «1000100010» en algo legible.
``pedidos``       Nº de pedido → email del responsable. **Respaldo**: lo normal
                  es que el comercial salga del ERP.
``portales``      lo que dice el portal (PO de PRODOC, flujo de SENDOC, paquete
                  de ACONEX) → nuestro Nº de pedido.
``refs``          referencia de AYESA → PO. Ese portal numera a su manera y su
                  referencia no está en el ERP.
``comerciales``   iniciales del comercial EN EL ERP → email, por si el ERP no
                  está disponible. OJO: no son las iniciales del equipo.
``reasignados``   iniciales del ERP → email de quien lleva ahora sus pedidos.
                  Esto SÍ manda sobre el ERP: es alguien que se fue.
``iniciales``     email → iniciales para la columna «Responsable».
``docspace``      clave de proyecto de Document Space → «pedido | suministro |
                  familia», que ahí vienen los tres juntos.
``materiales``    lo que dice el portal → familia de producto (REF016,
                  REF034…), que el correo del portal no trae.
``tipos_correo``  código de tipo de documento → email del técnico que va en CC.
``correo_para``   destinatarios fijos de las reclamaciones.
``correo_cc``     copias fijas.
``correo_direccion``  a quién se avisa en el escalado más alto.

Los diccionarios se cargan una vez y se **modifican en el sitio** al guardar:
media app hace ``from core.config import USERS`` o
``from core.parsers.base_parser import DEFAULT_TO``, y rebindear dejaría a esos
módulos con la copia vieja.
"""

from __future__ import annotations

import logging

from core.paths import state_dir
from core.utils.json_store import read_json, write_json

logger = logging.getLogger(__name__)

ORGANIZACION_FILE = str(state_dir() / "organizacion.json")

# Tablas de texto → texto (las que el editor de Ajustes pinta como dos columnas)
TABLAS_TEXTO = ("clientes", "pedidos", "portales", "refs", "comerciales",
                "reasignados", "iniciales", "materiales", "docspace",
                "tipos_correo")
LISTAS = ("correo_para", "correo_cc", "correo_direccion")
CLAVES = ("equipo", *TABLAS_TEXTO, *LISTAS)

equipo: dict[str, dict] = {}
clientes: dict[str, str] = {}
pedidos: dict[str, str] = {}
portales: dict[str, str] = {}
refs: dict[str, str] = {}
comerciales: dict[str, str] = {}
reasignados: dict[str, str] = {}
iniciales: dict[str, str] = {}
materiales: dict[str, str] = {}
docspace: dict[str, str] = {}
tipos_correo: dict[str, str] = {}
correo_para: list[str] = []
correo_cc: list[str] = []
correo_direccion: list[str] = []

_TABLAS = {"clientes": clientes, "pedidos": pedidos, "portales": portales, "refs": refs,
           "comerciales": comerciales, "reasignados": reasignados, "iniciales": iniciales, "materiales": materiales, "docspace": docspace,
           "tipos_correo": tipos_correo}
_LISTAS = {"correo_para": correo_para, "correo_cc": correo_cc,
           "correo_direccion": correo_direccion}


def _correos(valor) -> list[str]:
    """«a@x.com, b@x.com» y ["a@x.com"] dan lo mismo."""
    if isinstance(valor, str):
        valor = valor.replace(";", ",").split(",")
    return [str(v).strip() for v in (valor or []) if str(v).strip()]


def _normaliza_equipo(datos) -> dict:
    """Acepta {iniciales: {nombre, emails}} y también {iniciales: "correo"}."""
    salida = {}
    for clave, valor in (datos or {}).items():
        ini = str(clave).strip().upper()
        if not ini:
            continue
        if isinstance(valor, (str, list)):
            salida[ini] = {"nombre": ini, "emails": _correos(valor)}
            continue
        salida[ini] = {"nombre": str(valor.get("nombre") or ini).strip(),
                       "emails": _correos(valor.get("emails"))}
    return salida


def _normaliza_tabla(datos) -> dict:
    return {str(k).strip(): str(v).strip()
            for k, v in (datos or {}).items() if str(k).strip()}


def _aplicar(datos: dict) -> None:
    equipo.clear()
    equipo.update(_normaliza_equipo(datos.get("equipo")))
    for clave, tabla in _TABLAS.items():
        tabla.clear()
        tabla.update(_normaliza_tabla(datos.get(clave)))
    for clave, lista in _LISTAS.items():
        lista.clear()
        lista.extend(_correos(datos.get(clave)))


def cargar() -> None:
    """Relee el fichero y deja cada tabla como esté allí."""
    _aplicar(read_json(ORGANIZACION_FILE, default=None) or {})
    logger.info("Organización: %d del equipo, %d clientes, %d pedidos",
                len(equipo), len(clientes), len(pedidos))


def como_dict() -> dict:
    datos = {"equipo": {k: dict(v) for k, v in equipo.items()}}
    datos.update({clave: dict(tabla) for clave, tabla in _TABLAS.items()})
    datos.update({clave: list(lista) for clave, lista in _LISTAS.items()})
    return datos


def guardar(**tablas) -> None:
    """Guarda las tablas que se le pasen y deja las demás como están.

        guardar(equipo={...})                 solo el equipo
        guardar(clientes={}, correo_cc=[])    dos de golpe
    """
    datos = como_dict()
    for clave, valor in tablas.items():
        if clave not in CLAVES:
            raise KeyError(f"«{clave}» no es una tabla de la organización ({', '.join(CLAVES)})")
        datos[clave] = valor
    write_json(ORGANIZACION_FILE, datos)
    _aplicar(datos)


def email_de(ini: str) -> str:
    """El primer correo de esa persona del equipo, o cadena vacía."""
    correos = equipo.get(str(ini).strip().upper(), {}).get("emails") or []
    return correos[0] if correos else ""


def hay_datos() -> bool:
    return bool(equipo or clientes or pedidos or portales or refs)


cargar()
