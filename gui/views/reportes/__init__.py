"""Centro de Reportes: los Excel, los informes web y lo que sale solo.

La vista vive en `vista` y cada pestaña en su módulo: `interactivos`, `excels`,
`resumenes` y `programados`. Los diálogos de envío y de edición, en `dialogos`.
"""


from gui.views.reportes.comun import (
    EXCEL_REPORTS,
)
from gui.views.reportes.dialogos import (
    EditScheduleDialog,
    SendExecutiveDialog,
    SendPersonalDialog,
)
from gui.views.reportes.vista import (
    ReportesView,
)

__all__ = [
    "EXCEL_REPORTS",
    "EditScheduleDialog",
    "ReportesView",
    "SendExecutiveDialog",
    "SendPersonalDialog",
]
