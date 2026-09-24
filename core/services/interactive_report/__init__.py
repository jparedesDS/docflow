"""Informes interactivos en HTML: semanal/mensual, ejecutivo y por pedido.

Cada informe vive en su módulo; aquí se reexporta lo que usan las
vistas y los envíos programados, que siguen importando
`core.services.interactive_report`.
"""


from core.services.interactive_report.comun import (
    ACCENT,
    AMBER,
    BLUE,
    GREEN,
    RED,
    SLATE,
    reports_dir,
)
from core.services.interactive_report.periodico import (
    Window,
    build_report_data,
    default_filename,
    generate,
    get_available_periods,
    post_period_to_teams,
    render_html,
    send_email,
)
from core.services.interactive_report.ejecutivo import (
    build_executive_report_data,
    generate_executive,
    post_executive_to_teams,
    render_executive_html,
    send_executive_html_email,
)
from core.services.interactive_report.pedido import (
    build_pedido_report_data,
    generate_pedido,
    list_pedidos,
    post_pedido_to_teams,
    render_pedido_html,
    send_pedido_email,
)

__all__ = [
    "ACCENT",
    "AMBER",
    "BLUE",
    "GREEN",
    "RED",
    "SLATE",
    "Window",
    "build_executive_report_data",
    "build_pedido_report_data",
    "build_report_data",
    "default_filename",
    "generate",
    "generate_executive",
    "generate_pedido",
    "get_available_periods",
    "list_pedidos",
    "post_executive_to_teams",
    "post_pedido_to_teams",
    "post_period_to_teams",
    "render_executive_html",
    "render_html",
    "render_pedido_html",
    "reports_dir",
    "send_email",
    "send_executive_html_email",
    "send_pedido_email",
]
