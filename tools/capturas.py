# -*- coding: utf-8 -*-
"""Capturas de la app para el README, con datos inventados.

El repositorio es público: aquí no entra ni un pedido ni un cliente de verdad.
Se sustituyen las fuentes de datos por un juego de ejemplo y se fotografía la
ventana real de la app, con su menú y su tema.

    python tools/capturas.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

DESTINO = BASE / "docs" / "img"
DESTINO.mkdir(parents=True, exist_ok=True)

HOY = date(2026, 9, 21)
CLIENTES = [("P-26/001", "NORDIC ENERGY", "Caudal"),
            ("P-26/002", "ACME REFINING", "Temperatura"),
            ("P-26/023", "DELTA CHEMICALS", "Nivel")]
TIPOS = ["Cálculos", "Planos", "PPI", "Procedimientos", "Manual", "Certificados", "Dossier"]
ESTADOS = ["Aprobado", "Com. Menores", "Enviado", "", "Com. Mayores", "Aprobado", "Rechazado"]


def documentos() -> list[dict]:
    docs = []
    for i in range(30):
        pedido, cliente, material = CLIENTES[i % 3]
        envio = HOY - timedelta(days=(i * 3) % 40)
        docs.append({
            "Nº Pedido": pedido, "Cliente": cliente, "Material": material,
            "Nº PO": f"PO-90{i:03d}", "Nº Oferta": f"O-26/0{i:02d}",
            "Nº Doc. Cliente": f"VD-{pedido[-3:]}-{i:03d}",
            "Nº Doc. EIPSA": f"26-{pedido[-3:]}-{TIPOS[i % 7][:3].upper()}-{i:04d}",
            "Título": f"{TIPOS[i % 7].upper()} DEL EQUIPO {i % 9 + 1}",
            "Tipo Doc.": TIPOS[i % 7], "Crítico": "Sí" if i % 4 == 0 else "No",
            "Estado": ESTADOS[i % 7], "Nº Revisión": float(i % 3),
            "Responsable": ["JP", "AC", "LB"][i % 3], "Repsonsable": ["JP", "AC", "LB"][i % 3],
            "Fecha Pedido": (HOY - timedelta(days=90)).strftime("%d-%m-%Y"),
            "Fecha Prevista": (HOY + timedelta(days=30)).strftime("%d-%m-%Y"),
            "Fecha": envio.strftime("%d/%m/%Y"), "Fecha Env. Doc.": envio.strftime("%d/%m/%Y"),
            "Días Envío": (i * 3) % 40, "Días Devolución": (i * 2) % 25,
            "Info/Review": "Review", "Seguimiento": "", "Historial Rev.": "",
        })
    return docs


DATOS_VPR = {
    "pedido": "P-26/001",
    "cabecera": {"pedido": "P-26/001-S00", "po": "C.100000/01",
                 "fecha_pedido": "17-06-2026", "entrega": "30-10-2026", "items": 120,
                 "taller": 40, "montaje": 25, "entregas": 34, "obs_taller": "",
                 "obs_envios": "TRANSPORTES DEMO", "envio_parcial": "08-09-2026"},
    "equipos": 120,
    "grupos": [
        {"nombre": "Placa+bridas A105 (42)", "equipos": 42, "ingenieria": 100,
         "subpedidos": 100, "fabricacion": 100, "inspeccion": 50},
        {"nombre": "Placa+bridas F5 (8)", "equipos": 8, "ingenieria": 100,
         "subpedidos": 100, "fabricacion": 0, "inspeccion": 0},
        {"nombre": 'Vaina+termopar 1-1/2" (61)', "equipos": 61, "ingenieria": 100,
         "subpedidos": 100, "fabricacion": 0, "inspeccion": 2},
        {"nombre": 'Vaina+termopar 3/4" (8)', "equipos": 8, "ingenieria": 100,
         "subpedidos": 100, "fabricacion": 50, "inspeccion": 100},
        {"nombre": 'Meter run 1" (1)', "equipos": 1, "ingenieria": 100,
         "subpedidos": 100, "fabricacion": 0, "inspeccion": 0},
    ],
    "documentos": {"total": 9, "emitidos": 8, "aprobados": 7, "pendientes": [], "docs": []},
    "subpedidos": [
        {"numero": "2260138", "fecha": "23-06-2026", "proveedor": "Aceros del Norte, S.A.",
         "material": "Barra redonda AISI-316/316L (36 uds)", "unidades": 36, "pendientes": 0,
         "contractual": "04-09-2026", "estado": "Recibido completo el 02-09-2026"},
        {"numero": "2260147", "fecha": "28-06-2026", "proveedor": "Tornillería Industrial, S.L.",
         "material": "Juntas y espárragos B16 (351 uds)", "unidades": 351, "pendientes": 0,
         "contractual": "01-09-2026", "estado": "Recibido completo el 02-09-2026"},
        {"numero": "2260149", "fecha": "28-06-2026", "proveedor": "Forjas del Sur",
         "material": 'Bridas 6", 8" y 12" 300 WNRF A182 F5 (14 uds)', "unidades": 14,
         "pendientes": 14, "contractual": "30-10-2026", "estado": "PENDIENTE — 14 uds"},
    ],
    "fabricacion": {"fabricados": 42, "verificados": 52, "ensayados": 9, "entregados": 0},
    "avance": {"ingenieria": 95, "documentacion": 78, "subpedidos": 100, "acopio": 97,
               "fabricacion": 34, "inspeccion": 25, "transporte": 34},
}


def parchear() -> None:
    """Cambia las fuentes de datos por el juego de ejemplo."""
    from core.services import monitoring, vpr

    monitoring.get_monitoring_data = lambda *a, **k: documentos()
    vpr.datos = lambda pedido: dict(DATOS_VPR, pedido=pedido)
    vpr.plantilla_de = lambda cliente: r"C:\plantillas\VPR CLIENTE.docx"

    from core.services import portadas_lote
    portadas_lote.perfil = lambda cliente: {
        "plantillas": [r"C:\plantillas\PORTADA CLIENTE.xlsx"],
        "mapa": {"CLIENT": "NORDIC ENERGY", "PROJECT": "DEMO",
                 "VENDOR DOC. N°": "{Nº Doc. EIPSA}", "ITEM N°": "{Tag|ALL TAGS}"}}
    portadas_lote.carpeta_destino = lambda doc: r"env. Cálculos"

    from core.services import agenda
    agenda.load_all = lambda *a, **k: {"tareas": [], "notas": [], "reuniones": []}

    # Los avisos de Inicio leen otros departamentos del ERP: también de mentira
    from core.services import administration, production, purchases, quality, warehouse
    warehouse.snapshot = lambda *a, **k: {"stats": {"atascados": 2, "dias_max": 9}, "rows": []}
    purchases.stats = lambda *a, **k: {"lineas": 12, "retrasadas": 3, "retraso_max": 11,
                                       "proveedores": 5, "pedidos": 3, "pronto": 4}
    quality.nc_stats = lambda *a, **k: {"abiertas_anio": 1, "total": 4}
    quality.equipment_stats = lambda *a, **k: {"vencidos": 2, "total": 30}
    production.workshop_stats = lambda *a, **k: {"retrasados": 2, "vivos": 6, "en_curso": 4}
    administration.bond_stats = lambda *a, **k: {"vencidos": 1, "vigentes": 3}
    administration.invoice_stats = lambda *a, **k: {"pendientes": 4, "importe_pendiente": 12500.0,
                                                    "dias_max": 20}

    # Correos de devolución de ejemplo
    from core.services import transmittal
    correos = [
        {"uid": str(900 + i), "subject": asunto, "from": remite, "date": f"2{i} sep 2026 08:1{i}",
         "platform": plataforma, "parseable": True, "processed": i % 3 == 0,
         "message_id": f"<demo{i}@ejemplo>",
         "download": {"code": f"TR-00{i}", "downloadable": True, "downloaded": i % 2 == 0,
                      "folder": "", "dev_folders": []}}
        for i, (asunto, remite, plataforma) in enumerate([
            ("Transmittal registrado (1001-T-0042) - PO(1001)", "portal@cliente-a.com",
             "TÉCNICAS REUNIDAS"),
            ("Documentos revisados - P-26/002", "docs@cliente-b.com", "ACONEX"),
            ("Vendor documents returned - PO 90012", "noreply@cliente-c.com", "PRODOC"),
            ("Comentarios a planos dimensionales", "gestion@cliente-a.com", "GAIA"),
        ])]
    transmittal.fetch_all_emails = lambda *a, **k: correos
    transmittal.fetch_unread_emails = lambda *a, **k: [c for c in correos if not c["processed"]]


def foto(app, nombre: str) -> None:
    from PIL import ImageGrab

    app.lift()
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    img = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()))
    img.save(DESTINO / nombre)
    print("·", nombre, img.size)


PANTALLAS = [("home", "inicio.png"), ("documentos", "documentos.png"),
             ("devoluciones", "devoluciones.png"), ("vpr", "vpr.png")]


def main() -> None:
    parchear()
    from core import auth, session
    from gui.app import DocFlowLiteApp

    auth.initialize()
    usuario = auth.get_user("JP") or {"initials": "JP", "nombre": "el administrador"}
    session.set_user(usuario)
    app = DocFlowLiteApp(usuario)
    app.geometry("1440x900+40+20")
    app.attributes("-topmost", True)

    # Las vistas cargan sus datos en hilos y avisan con after(), que solo
    # funciona con el bucle de Tk en marcha: por eso se encadenan los pasos
    # desde el propio bucle en vez de dar vueltas con update().
    pendientes = list(PANTALLAS)

    def siguiente():
        if not pendientes:
            app.quit()
            return
        clave, nombre = pendientes.pop(0)
        app.navigate(clave)
        app.after(3000, lambda: (foto(app, nombre), siguiente()))

    app.after(1200, siguiente)
    app.mainloop()
    app.destroy()


if __name__ == "__main__":
    main()
