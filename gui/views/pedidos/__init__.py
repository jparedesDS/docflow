"""Pedidos: la ficha de un pedido de un vistazo.

La vista vive en `vista`, la ficha de cabecera y los bloques de estado en
`ficha`, la tabla de equipos en `tags`, el detalle de un equipo en
`detalle_tag` y la descarga de comentados del portal en `finales`.
"""

from gui.views.pedidos.detalle_tag import TagDetailWindow
from gui.views.pedidos.finales import FinalesWindow
from gui.views.pedidos.vista import PedidosView

__all__ = ["FinalesWindow", "PedidosView", "TagDetailWindow"]
