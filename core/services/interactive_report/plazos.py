"""Informe web de Plazos: del correo de la oferta a la fábrica.

Una página HTML autónoma (sin scripts ni recursos de fuera, para que se vea
igual adjunta a un correo) con lo que tarda cada paso, la cola de planos con
su margen, los tiempos por persona y la tabla de pedidos. Los datos vienen de
`seguimiento.cargar()`; aquí solo se pinta.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from core.services.interactive_report.comun import ACCENT, AMBER, GREEN, RED, SLATE, _esc, reports_dir

logger = logging.getLogger(__name__)

TITULO = "Plazos: de la oferta a la fábrica"

# (tramo, nombre, quién) en el orden de la cadena
CADENA = [
    ("comercial", "Oferta recibida → contestada", "Comercial"),
    ("cliente", "Contestada → pedido del cliente", "Tiempo del cliente"),
    ("activar", "Pedido → activación", "Comercial"),
    ("compras_pedir", "Activación → 1.er pedido a proveedor", "Compras"),
    ("material", "Activación → material recibido", "Compras / proveedor"),
    ("tecnico", "Activación → planos a fábrica", "Técnico"),
    ("cola_taller", "1.ª OT → 1.er fichaje", "Fábrica"),
    ("taller_envio", "Planos a fábrica → envío", "Fábrica"),
]

PASOS = {"comercial": "Comercial · oferta recibida → contestada", "activar": "Comercial · pedido → activación",
         "compras": "Compras · activación → material", "tecnico": "Técnico · activación → planos a fábrica"}

FALTA = {"planos": ("Planos (el material ya está)", RED), "ambos": ("Planos y material", AMBER),
         "material": ("Material", SLATE), "nada": ("Listo para fábrica", GREEN)}


def _n(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(v)


def _f(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%d-%m-%Y")
    if isinstance(v, date):
        return v.strftime("%d-%m-%Y")
    return "—"


def _rango(s: dict) -> str:
    return f"{_n(s['p25'])}–{_n(s['p75'])}" if s.get("p25") is not None else "—"


def _cadena_html(r: dict) -> str:
    tramos = r["tramos"]
    maximo = max([tramos[t]["mediana"] or 0 for t, _n_, _q in CADENA] + [1])
    filas = []
    for t, nombre, quien in CADENA:
        s = tramos[t]
        cliente = t == "cliente"
        ancho = 0 if s["mediana"] is None else max(2, round(100 * max(s["mediana"], 0) / maximo))
        color = "#CBD5E1" if cliente else ACCENT
        filas.append(
            f'<tr class="{"cli" if cliente else ""}"><td><b>{_esc(nombre)}</b><br><span class="q">{_esc(quien)}</span></td>'
            f'<td class="num">{_n(s["mediana"])} d</td><td class="num">{_rango(s)}</td><td class="num">{s["n"]}</td>'
            f'<td class="bar"><div style="width:{ancho}%;background:{color}"></div></td></tr>')
    return ('<table class="cadena"><thead><tr><th>Paso</th><th>Típico</th><th>La mitad, entre</th>'
            '<th>Pedidos</th><th></th></tr></thead><tbody>' + "".join(filas) + "</tbody></table>")


def _margen(c: dict) -> str:
    m = c.get("margen")
    if not m:
        return "—"
    base = f'{c.get("margen_n")} pedidos' + (f' ({_esc(c["margen_de"])})' if c.get("margen_de") else "")
    color = RED if m[0] < 0 else (AMBER if m[0] < 15 else GREEN)
    return f'<span style="color:{color};font-weight:600">entre {m[0]} y {m[1]} días</span><br><span class="q">{base}</span>'


def _cola_html(cola: list[dict]) -> str:
    if not cola:
        return '<p class="vacio">No hay pedidos activados esperando a pasar a fábrica.</p>'
    filas = []
    for i, c in enumerate(cola, start=1):
        texto, color = FALTA.get(c["falta"], (c["falta"], SLATE))
        filas.append(
            f'<tr><td class="num">{i}</td><td><span class="pill" style="background:{color}">{_esc(texto)}</span></td>'
            f'<td><b>{_esc(c["pedido"])}</b></td><td>{_esc(c["cliente"])}</td><td>{_esc(c["equipo"])}</td>'
            f'<td>{_f(c["hitos"]["activacion"]["fecha"])}</td><td>{_f(c["hitos"]["entrega"]["fecha"])}</td>'
            f'<td>{_margen(c)}</td></tr>')
    return ('<table><thead><tr><th>#</th><th>Qué falta</th><th>Pedido</th><th>Cliente</th><th>Equipo</th>'
            '<th>Activación</th><th>Entrega</th><th>Margen</th></tr></thead><tbody>' + "".join(filas)
            + "</tbody></table>")


def _personas_html(r: dict) -> str:
    if not r["por_persona"]:
        return '<p class="vacio">Sin datos.</p>'
    filas = "".join(
        f'<tr><td>{_esc(PASOS.get(p["paso"], p["paso"]))}</td><td><b>{_esc(p["persona"])}</b></td>'
        f'<td class="num">{p["n"]}</td><td class="num">{_n(p["mediana"])} d</td><td class="num">{_rango(p)}</td></tr>'
        for p in r["por_persona"])
    return ('<table><thead><tr><th>Paso</th><th>Persona</th><th>Pedidos</th><th>Típico</th><th>La mitad, entre</th>'
            '</tr></thead><tbody>' + filas + "</tbody></table>"
            '<p class="q">Con pocos pedidos, una cifra dice poco: mira siempre la columna «Pedidos».</p>')


def _pedidos_html(filas: list[dict]) -> str:
    if not filas:
        return '<p class="vacio">Sin pedidos.</p>'
    cab = "".join(f"<th>{_esc(n.split(' → ')[-1])}</th>" for _t, n, _q in CADENA)
    out = []
    for f in sorted(filas, key=lambda x: x["pedido"], reverse=True):
        celdas = "".join(f'<td class="num{" cli" if t == "cliente" else ""}">{_n(f["tramos"].get(t))}</td>'
                         for t, _n_, _q in CADENA)
        out.append(f'<tr><td><b>{_esc(f["pedido"])}</b><br><span class="q">{_esc(f["cliente"])}</span></td>'
                   f'<td>{_esc(f["equipo"])}</td>{celdas}</tr>')
    return (f'<div class="scroll"><table><thead><tr><th>Pedido</th><th>Equipo</th>{cab}</tr></thead><tbody>'
            + "".join(out) + "</tbody></table></div>")


def render_plazos_html(datos: dict) -> str:
    r = datos["resumen"]
    generado = datos.get("generado") or datetime.now()
    años = ", ".join(str(a) for a in datos.get("años") or ())
    avisos = "".join(f'<div class="aviso">⚠ {_esc(a)}</div>' for a in datos.get("avisos") or [])
    con_hora = r["con_hora"]
    hora = (f'{con_hora["rfq"]} de {con_hora["total"]} ofertas tienen la hora real del correo; '
            "el resto, el día que apunta el ERP.")
    primeros = sum(1 for c in datos["cola"] if c["falta"] == "planos")
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(TITULO)}</title>
<style>
  body {{ margin:0; background:#EEF1F8; color:#0F172A; font-family:'Segoe UI',system-ui,Arial,sans-serif; line-height:1.45; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:28px 18px 48px; }}
  header {{ border-bottom:2px solid {ACCENT}; padding-bottom:14px; }}
  h1 {{ font-size:22px; margin:0; }} .sub {{ color:#475569; font-size:13px; margin:4px 0 0; }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:{ACCENT}; margin:28px 0 10px; }}
  .card {{ background:#fff; border:1px solid #E2E8F0; border-radius:12px; padding:16px 18px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; color:#475569; border-bottom:1px solid #E2E8F0; padding:6px; }}
  td {{ border-bottom:1px solid #F1F5F9; padding:7px 6px; vertical-align:top; }}
  .num {{ text-align:right; white-space:nowrap; }} .q {{ color:#64748B; font-size:12px; }}
  .bar {{ width:32%; }} .bar div {{ height:12px; border-radius:6px; }}
  tr.cli td, td.cli {{ color:#94A3B8; }}
  .pill {{ color:#fff; border-radius:999px; padding:2px 9px; font-size:12px; white-space:nowrap; }}
  .aviso {{ background:#FEF3C7; border:1px solid #FCD34D; border-radius:8px; padding:8px 12px; margin:12px 0 0; }}
  .nota {{ background:#F5F3FF; border-left:4px solid {ACCENT}; padding:12px 16px; border-radius:0 10px 10px 0; margin-top:16px; font-size:14px; }}
  .vacio {{ color:#64748B; }} .scroll {{ overflow-x:auto; }}
</style></head><body><div class="wrap">
<header><h1>{_esc(TITULO)}</h1>
<p class="sub">Pedidos de {_esc(años)} · generado el {generado:%d-%m-%Y %H:%M}</p></header>
{avisos}
<div class="nota">Cada paso dice cuántos días suele tardar (la mediana) y entre cuántos días cae la mitad de los
pedidos. <b>El tiempo del cliente</b>, entre que se contesta la oferta y llega el pedido, va en gris: no depende de
nadie de la casa. Compras y planos arrancan a la vez con la activación. {_esc(hora)}</div>
<h2>Lo que tarda cada paso</h2><div class="card">{_cadena_html(r)}</div>
<h2>Cola de planos · {len(datos["cola"])} pedidos, {primeros} con el material listo y sin planos</h2>
<div class="card">{_cola_html(datos["cola"])}
<p class="q">Margen = entrega contractual − hoy − lo que suelen tardar desde los planos hasta el envío los pedidos del
mismo tipo. Es una horquilla, no una fecha: en rojo, en riesgo.</p></div>
<h2>Por persona</h2><div class="card">{_personas_html(r)}</div>
<h2>Pedidos (días de cada paso)</h2><div class="card">{_pedidos_html(datos["filas"])}</div>
</div></body></html>"""


def _nombre(generado: datetime, ext: str) -> str:
    return f"Plazos_{generado:%Y-%m-%d}.{ext}"


def generate_plazos(datos: dict | None = None) -> Path:
    """Genera el HTML en la carpeta de informes y devuelve su ruta."""
    from core.services import seguimiento
    datos = datos or seguimiento.cargar()
    ruta = reports_dir() / _nombre(datos["generado"], "html")
    ruta.write_text(render_plazos_html(datos), encoding="utf-8")
    return ruta


def _cuerpo_correo(datos: dict) -> str:
    t = datos["resumen"]["tramos"]
    primeros = [c for c in datos["cola"] if c["falta"] == "planos"][:5]
    lista = "".join(f"<li><b>{_esc(c['pedido'])}</b> · {_esc(c['cliente'])} · entrega {_f(c['hitos']['entrega']['fecha'])}"
                    "</li>" for c in primeros)
    return (f"<p>Adjunto el informe de plazos (ábrelo en el navegador) y el Excel con el detalle.</p>"
            f"<p>Típico: comercial {_n(t['comercial']['mediana'])} d · técnico {_n(t['tecnico']['mediana'])} d · "
            f"material {_n(t['material']['mediana'])} d · cliente {_n(t['cliente']['mediana'])} d (no es nuestro).</p>"
            + (f"<p>Con el material listo y sin planos:</p><ul>{lista}</ul>" if lista else ""))


def send_plazos_email(to: list[str], cc: list[str] | None = None) -> dict:
    """Envía el informe (HTML) y el Excel. Lee el correo de Ofertas antes, para tener las horas."""
    if not to:
        return {"status": "skipped", "reason": "Sin destinatarios"}
    from core.services import seguimiento, seguimiento_excel
    from core.services.smtp import send_html_email

    datos = seguimiento.cargar()
    html = render_plazos_html(datos)
    ruta_html = reports_dir() / _nombre(datos["generado"], "html")
    ruta_xlsx = reports_dir() / _nombre(datos["generado"], "xlsx")
    try:
        ruta_html.write_text(html, encoding="utf-8")
    except OSError:
        logger.debug("No se pudo guardar la copia local del informe de plazos", exc_info=True)
    seguimiento_excel.exportar(datos, ruta_xlsx)
    lunes = datos["generado"].date() - timedelta(days=datos["generado"].weekday())
    result = send_html_email(
        to=to, cc=cc or [], subject=f"{TITULO} — semana del {lunes:%d-%m-%Y}",
        html_body=_cuerpo_correo(datos), attachment_eml=html.encode("utf-8"), attachment_name=ruta_html.name,
        extra_attachments=[(ruta_xlsx.name, ruta_xlsx.read_bytes())])
    result = result if isinstance(result, dict) else {}
    result["status"] = "sent"
    result["recipients"] = to
    return result
