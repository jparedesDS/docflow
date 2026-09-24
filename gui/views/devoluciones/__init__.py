"""Devoluciones: los correos en los que el cliente devuelve documentación.

La sección son tres pantallas: la lista de correos (`lista`), el preview de una
devolución antes de avisar al responsable (`preview`) y la devolución escrita a
mano cuando el portal no manda correo (`manual`).
"""


from gui.views.devoluciones.lista import (
    DevolucionesView,
)
from gui.views.devoluciones.preview import (
    PreviewWindow,
)
from gui.views.devoluciones.manual import (
    ManualDevolucionWindow,
)

__all__ = [
    "DevolucionesView",
    "ManualDevolucionWindow",
    "PreviewWindow",
]
