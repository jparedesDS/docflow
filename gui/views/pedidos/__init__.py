"""Pedidos: la ficha de un pedido de un vistazo.

La vista vive en `vista`, la ficha de cabecera y los bloques de estado en
`ficha`, la tabla de equipos en `tags` y el detalle de un equipo en
`detalle_tag`.
"""

from gui.views.pedidos.detalle_tag import TagDetailWindow
from gui.views.pedidos.vista import PedidosView

__all__ = ["PedidosView", "TagDetailWindow"]
