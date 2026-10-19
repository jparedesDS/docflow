"""Las secciones del programa, tal como salen en el menú lateral.

Una sola lista para el menú, la paleta (Ctrl+K) y Ajustes ▸ Usuarios y
permisos, que así enseña cada sección con el mismo nombre e icono que el menú.

Arriba, sueltos, lo que usa todo el mundo (Inicio, Agenda, Correo); después,
Pedidos con lo que se hace con cada uno (abrirlo, seguirlo, el VPR y sus
portadas), Documentación, Comercial y, juntos en Departamentos, los que solo
tienen una pantalla cada uno (antes eran cinco grupos de una sola entrada:
cinco cabeceras que abrir para llegar a una pantalla).
"""

NAV_LAYOUT = [
    {"type": "item", "key": "home", "label": "Inicio", "icon": "⌂"},
    {"type": "item", "key": "agenda", "label": "Agenda", "icon": "▣"},
    {"type": "item", "key": "inbox", "label": "Correo", "icon": "✦"},
    {"type": "group", "id": "pedidos", "label": "Pedidos", "items": [
        {"key": "pedidos",  "label": "Seguimiento",      "icon": "▦"},
        {"key": "apertura", "label": "Nuevo pedido",     "icon": "✚"},
        {"key": "vpr",      "label": "VPR",              "icon": "📈"},
        {"key": "portadas", "label": "Generar portadas", "icon": "🖹"},
    ]},
    {"type": "group", "id": "documentacion", "label": "Documentación", "items": [
        {"key": "documentos",    "label": "Documentos",    "icon": "◫"},
        {"key": "devoluciones",  "label": "Devoluciones",  "icon": "↩"},
        {"key": "reclamaciones", "label": "Reclamaciones", "icon": "⚠"},
    ]},
    {"type": "group", "id": "comercial", "label": "Comercial", "items": [
        {"key": "ofertas",  "label": "Ofertas",  "icon": "✉"},
        {"key": "docusign", "label": "DocuSign", "icon": "✒"},
    ]},
    {"type": "group", "id": "departamentos", "label": "Departamentos", "items": [
        {"key": "compras",        "label": "Compras",        "icon": "🛒"},
        {"key": "produccion",     "label": "Producción",     "icon": "⚙"},
        {"key": "calidad",        "label": "Calidad",        "icon": "✔"},
        {"key": "administracion", "label": "Administración", "icon": "€"},
        {"key": "almacen",        "label": "Almacén",        "icon": "📦"},
    ]},
    {"type": "group", "id": "informes", "label": "Informes", "items": [
        {"key": "informes", "label": "Analítica",          "icon": "▤"},
        {"key": "reportes", "label": "Centro de Reportes", "icon": "📊"},
    ]},
]

# Solo para el administrador: va suelta al final del menú, sin permisos que dar
# (las cuentas y sus permisos están dentro, en Ajustes ▸ Usuarios y permisos).
SOLO_ADMIN = [
    {"type": "item", "key": "ajustes", "label": "Ajustes", "icon": "⚙"},
]


def grupos_de_permisos() -> list[tuple[str, list[dict]]]:
    """Las secciones a las que se da o se quita acceso, por departamento.

    Inicio no aparece: lo ve todo el mundo. Las sueltas de arriba van juntas
    en «General»."""
    sueltas = [e for e in NAV_LAYOUT if e.get("type") != "group" and e["key"] != "home"]
    grupos = [("General", sueltas)] if sueltas else []
    grupos += [(e["label"], list(e["items"])) for e in NAV_LAYOUT if e.get("type") == "group"]
    return grupos
