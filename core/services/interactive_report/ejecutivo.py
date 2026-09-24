"""Informe ejecutivo: la foto de la empresa en una página.

Cartera, avance por pedido, comercial y un cuadro de mando con notas
por área. Sin periodo: es el estado actual.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from core.services import analytics as analytics_service
from core.utils.fmt import eur as _eur
from core.services.interactive_report.comun import (
    ACCENT,
    AMBER,
    BLUE,
    GREEN,
    RED,
    SLATE,
    _MESES,
    _TABLE_CSS,
    _TABLE_JS,
    _ask_haiku,
    _chartjs_source,
    _esc,
    _pct_color,
    _score_color,
    reports_dir,
)

logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


def build_executive_report_data(ref_date: datetime | None = None,
                                with_ai: bool = True) -> dict:
    """Datos del reporte ejecutivo (foto global de la cartera).

    Lleva lo mismo que la Analítica de la app: el tiempo real que tarda el
    cliente (del historial de revisiones, no de la foto fija de «Días
    Devolución»), el retrabajo, el avance de cada pedido con la pelota repartida
    y el embudo comercial con importes. Si el ERP no responde, la parte comercial
    se queda fuera y el resto se genera igual.
    """
    from core.services import analytics_erp as erp_analytics

    summary = analytics_service.get_summary()
    ranking = analytics_service.get_ranking()
    score = analytics_service.get_scorecard()
    eventos = analytics_service.doc_events()
    ciclo = analytics_service.get_ciclo_respuesta(eventos)
    retrabajo = analytics_service.get_retrabajo(eventos)
    actividad = analytics_service.get_actividad_mensual(12, eventos)
    avance = analytics_service.get_avance_pedidos()
    ref = ref_date or datetime.now()

    try:
        comercial = erp_analytics.comercial()
        cartera = erp_analytics.cartera()
    except Exception:  # noqa: BLE001 — sin ERP, informe sin la parte comercial
        comercial, cartera = {"por_anio": []}, {}

    total = (summary["total_aprobados"] + summary["total_enviados"]
             + summary["total_devoluciones"] + summary["total_sin_enviar"])
    pct = round(summary["total_aprobados"] / total * 100) if total else 0

    top_cli = summary["por_cliente"][:8]
    atrasados = [r for r in avance if r["riesgo"] != "ok"]
    nuestros = sum(r["en_nuestro_tejado"] for r in avance)
    del_cliente = sum(r["en_cliente"] for r in avance)

    kpis = [
        {"label": "Documentos", "value": total, "color": ACCENT, "sub": "en seguimiento"},
        {"label": "Aprobación global", "value": f"{pct}%", "color": GREEN,
         "sub": f"{summary['total_aprobados']} aprobados"},
        {"label": "Respuesta del cliente", "value": f"{ciclo['mediana']}d", "color": BLUE,
         "sub": f"mediana · {ciclo['dentro_15']}% dentro de 15 días"},
        {"label": "Aprobado a la primera", "value": f"{retrabajo['pct_primera']}%",
         "color": _pct_color(retrabajo["pct_primera"]),
         "sub": f"{retrabajo['media_envios']} envíos por documento"},
        {"label": "En riesgo", "value": summary["docs_riesgo"],
         "color": RED if summary["docs_riesgo"] else GREEN, "sub": "críticos +15d"},
        {"label": "Pedidos atrasados", "value": len(atrasados),
         "color": RED if atrasados else GREEN,
         "sub": f"de {len(avance)} con documentación abierta"},
    ]

    data = {
        "meta": {
            "title": "Reporte ejecutivo de documentación",
            "period_label": f"{_MESES[ref.month]} {ref.year}",
            "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "prepared_by": "jparedesDS",
            "key": ref.strftime("%Y-%m"),
        },
        "totals": {"total": total, "pct": pct,
                   "aprobados": summary["total_aprobados"],
                   "enviados": summary["total_enviados"],
                   "devoluciones": summary["total_devoluciones"],
                   "sin_enviar": summary["total_sin_enviar"]},
        "kpis": kpis,
        "estado": {"labels": ["Aprobado", "Enviado", "Devoluciones", "Sin enviar"],
                   "values": [summary["total_aprobados"], summary["total_enviados"],
                              summary["total_devoluciones"], summary["total_sin_enviar"]],
                   "colors": [GREEN, BLUE, AMBER, SLATE]},
        "clientes": {"labels": [str(c["cliente"])[:18] for c in top_cli],
                     "values": [c["media_dias"] for c in top_cli]},
        "actividad": actividad,
        "ranking": ranking,
        "avance": atrasados[:14],
        "pelota": {"total": len(avance), "atrasados": len(atrasados),
                   "nuestros": nuestros, "cliente": del_cliente},
        "ciclo": {"mediana": ciclo["mediana"], "media": ciclo["media"], "p90": ciclo["p90"],
                  "dentro_15": ciclo["dentro_15"], "n": ciclo["n"]},
        "retrabajo": {"pct_primera": retrabajo["pct_primera"],
                      "media_envios": retrabajo["media_envios"],
                      "aprobados": retrabajo["aprobados"]},
        "comercial": comercial.get("por_anio", [])[-5:],
        "cartera": cartera,
        "scorecard": score[:18],
    }
    data["narrative"] = _executive_narrative(data, with_ai=with_ai)
    return data


def _executive_fallback(d: dict) -> str:
    t, c, r, p = d["totals"], d["ciclo"], d["retrabajo"], d["pelota"]
    riesgo = next((k["value"] for k in d["kpis"] if k["label"] == "En riesgo"), 0)
    texto = (
        f"La cartera reúne {t['total']} documentos con un {t['pct']}% de aprobación global "
        f"({t['aprobados']} aprobados, {t['enviados']} en revisión del cliente y "
        f"{t['devoluciones']} con comentarios). El cliente tarda {c['mediana']} días de mediana "
        f"en contestar y solo el {c['dentro_15']}% lo hace dentro de 15; se aprueba a la primera "
        f"el {r['pct_primera']}%, con {r['media_envios']} envíos de media por documento. "
        f"Hay {riesgo} documento(s) crítico(s) en riesgo y {p['atrasados']} pedido(s) con la "
        f"documentación atrasada: de lo pendiente, {p['nuestros']} documentos están en nuestro "
        f"tejado y {p['cliente']} esperan respuesta del cliente."
    )
    if d.get("comercial"):
        a = d["comercial"][-1]
        texto += (f" En lo comercial, {a['anio']} lleva {a['ofertas']} ofertas con un "
                  f"{a['tasa']:.0f}% de adjudicación sobre las resueltas y {a['pedidos']} pedidos "
                  f"por {_eur(a['importe'])}.")
    return texto


def _executive_ai_prompt(d: dict) -> str:
    t, c, r, p = d["totals"], d["ciclo"], d["retrabajo"], d["pelota"]
    riesgo = next((k["value"] for k in d["kpis"] if k["label"] == "En riesgo"), 0)
    top_resp = ", ".join(f"{x['responsable']} ({x['pct']}%)" for x in d["ranking"][:3])
    comercial = ""
    if d.get("comercial"):
        a = d["comercial"][-1]
        comercial = (f"\n- Comercial {a['anio']}: {a['ofertas']} ofertas, {a['ganadas']} ganadas y "
                     f"{a['perdidas']} perdidas ({a['tasa']:.0f}% de adjudicación sobre resueltas), "
                     f"{a['vivas']} aún vivas; {a['pedidos']} pedidos por {_eur(a['importe'])}"
                     f"\n- Cartera abierta: {_eur(d.get('cartera', {}).get('importe', 0))} "
                     f"en {d.get('cartera', {}).get('pedidos', 0)} pedidos")
    return f"""Eres un asistente ejecutivo de Document Control. Redacta un PÁRRAFO EJECUTIVO
(3-4 frases, español, profesional) para la dirección, con la foto global de la cartera
de documentación técnica ({d['meta']['period_label']}):
- Documentos totales: {t['total']} · aprobación global: {t['pct']}%
- Aprobados: {t['aprobados']} · enviados (en cliente): {t['enviados']} · devoluciones: {t['devoluciones']} · sin enviar: {t['sin_enviar']}
- Respuesta del cliente: {c['mediana']} días de mediana (media {c['media']}, p90 {c['p90']}); {c['dentro_15']}% dentro de 15 días, sobre {c['n']} respuestas medidas
- Aprobado a la primera: {r['pct_primera']}% · {r['media_envios']} envíos de media por documento aprobado
- Documentos críticos en riesgo (+15 días): {riesgo}
- Pedidos con la documentación atrasada: {p['atrasados']} de {p['total']} abiertos
- Reparto de lo pendiente: {p['nuestros']} documentos en nuestro tejado (sin enviar o devueltos con comentarios) y {p['cliente']} esperando al cliente
- Mejores responsables por % aprobación: {top_resp or 'n/d'}{comercial}

Resume el estado general, di si el cuello de botella está en nuestro lado o en el del
cliente según el reparto de lo pendiente, y propón una acción. Sin HTML ni markdown."""


def _executive_narrative(d: dict, with_ai: bool = True) -> str:
    if with_ai:
        txt = _ask_haiku(_executive_ai_prompt(d))
        if txt:
            return txt
    return _executive_fallback(d)


def _exec_kpi_html(k: dict) -> str:
    return (
        f'<div class="kpi"><p class="kpi-label">{_esc(k["label"])}</p>'
        f'<p class="kpi-value" style="color:{k["color"]}">{_esc(k["value"])}</p>'
        f'<p class="kpi-sub">{_esc(k["sub"])}</p></div>'
    )


def _exec_ranking_html(ranking: list[dict]) -> str:
    if not ranking:
        return '<tr><td colspan="8" class="empty">Sin datos de equipo.</td></tr>'
    out = []
    for i, r in enumerate(ranking):
        col = _pct_color(r["pct"])
        out.append(
            f'<tr><td style="text-align:center;color:var(--muted)">#{i + 1}</td>'
            f'<td>{_esc(r["responsable"])}</td>'
            f'<td style="text-align:center">{r["total"]}</td>'
            f'<td style="text-align:center">{r["aprobados"]}</td>'
            f'<td style="text-align:center;color:{col};font-weight:600">{r["pct"]}%</td>'
            f'<td style="text-align:center">{r["devoluciones"]}</td>'
            f'<td style="text-align:center">{r["tasa_devolucion"]}%</td>'
            f'<td style="text-align:center">{r["criticos"]}</td></tr>'
        )
    return "".join(out)


def _exec_avance_html(filas: list[dict]) -> str:
    """Pedidos con la documentación atrasada, con la pelota repartida."""
    if not filas:
        return ('<tr><td colspan="9" class="empty">Ningún pedido con la documentación '
                'atrasada.</td></tr>')
    out = []
    for r in filas:
        col = RED if r["riesgo"] == "fuera" else AMBER
        dias = r["dias_al_plazo"]
        plazo = "—" if dias is None else (f"{abs(dias)} d tarde" if dias < 0
                                          else f"faltan {dias} d")
        out.append(
            f'<tr><td class="mono">{_esc(r["pedido"])}</td>'
            f'<td>{_esc(str(r["cliente"])[:28])}</td>'
            f'<td style="text-align:center">{r["aprobados"]}/{r["total"]}</td>'
            f'<td style="text-align:center">{r["pct"]}%</td>'
            f'<td style="text-align:center;color:var(--muted)">{r["pct_esperado"]}%</td>'
            f'<td style="text-align:center;color:{col};font-weight:600">{r["desviacion"]:+d} pp</td>'
            f'<td style="text-align:center">{r["en_nuestro_tejado"] or "—"}</td>'
            f'<td style="text-align:center">{r["en_cliente"] or "—"}</td>'
            f'<td style="text-align:center;color:{col}">{_esc(plazo)}</td></tr>'
        )
    return "".join(out)


def _exec_comercial_html(filas: list[dict]) -> str:
    """Embudo comercial por año: ofertas, adjudicación e importe de pedidos."""
    if not filas:
        return ('<tr><td colspan="7" class="empty">Sin conexión con el ERP: no se ha podido '
                'traer la parte comercial.</td></tr>')
    out = []
    for r in filas:
        col = _pct_color(r["tasa"])
        out.append(
            f'<tr><td class="mono">{r["anio"]}</td>'
            f'<td style="text-align:center">{r["ofertas"]}</td>'
            f'<td style="text-align:center">{r["ganadas"]}</td>'
            f'<td style="text-align:center">{r["perdidas"]}</td>'
            f'<td style="text-align:center;color:var(--muted)">{r["vivas"] or "—"}</td>'
            f'<td style="text-align:center;color:{col};font-weight:600">{r["tasa"]:.0f}%</td>'
            f'<td style="text-align:center">{r["pedidos"]} · {_esc(_eur(r["importe"]))}</td></tr>'
        )
    return "".join(out)


def _exec_scorecard_html(score: list[dict]) -> str:
    if not score:
        return '<tr><td colspan="6" class="empty">Sin datos de scorecard.</td></tr>'
    out = []
    for r in score:
        sc = round(r["score"])
        col = _score_color(sc)
        out.append(
            f'<tr><td>{_esc(r["client"])}</td>'
            f'<td><div class="bar-wrap"><div class="bar-track">'
            f'<div class="bar-fill" style="width:{min(100, sc)}%;background:{col}"></div></div>'
            f'<span style="color:{col};font-weight:600">{sc}</span></div></td>'
            f'<td style="text-align:center">{round(r["approval_rate_first_rev"])}%</td>'
            f'<td style="text-align:center">{r["avg_response_days"]}</td>'
            f'<td style="text-align:center">{r["critical_docs_count"]}</td>'
            f'<td style="text-align:center">{r["total_docs"]}</td></tr>'
        )
    return "".join(out)


def render_executive_html(data: dict) -> str:
    meta = data["meta"]
    chartjs = _chartjs_source()
    chart_tag = (f"<script>{chartjs}</script>" if chartjs else
                 '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>')
    payload = json.dumps({"estado": data["estado"], "clientes": data["clientes"],
                          "actividad": data["actividad"], "accent": ACCENT,
                          "verde": GREEN, "azul": BLUE, "ambar": AMBER}, ensure_ascii=False)
    kpis_html = "".join(_exec_kpi_html(k) for k in data["kpis"])
    p = data["pelota"]
    reparto = (f"De los {p['nuestros'] + p['cliente']} documentos pendientes en pedidos abiertos, "
               f"<b>{p['nuestros']} están en nuestro tejado</b> (sin enviar o devueltos con "
               f"comentarios) y <b>{p['cliente']} esperan respuesta del cliente</b>.")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(meta['title'])} · {_esc(meta['period_label'])}</title>
<style>
  :root {{ --accent:{ACCENT}; --ink:#0F172A; --sub:#475569; --muted:#94A3B8;
           --line:#E2E8F0; --card:#FFFFFF; --bg:#EEF1F8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
          font-family:'Segoe UI',system-ui,-apple-system,Roboto,Arial,sans-serif; line-height:1.5; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:32px 20px 56px; }}
  header {{ display:flex; align-items:center; justify-content:space-between; gap:16px;
            flex-wrap:wrap; border-bottom:2px solid var(--accent); padding-bottom:18px; }}
  .brand {{ display:flex; align-items:center; gap:14px; }}
  .logo {{ width:44px; height:44px; border-radius:10px; background:var(--accent);
           display:flex; align-items:center; justify-content:center; color:#fff;
           font-size:22px; font-weight:700; }}
  h1 {{ font-size:21px; margin:0; letter-spacing:-.01em; }}
  .sub {{ color:var(--sub); font-size:13px; margin:3px 0 0; }}
  .badge {{ background:var(--accent); color:#fff; font-size:13px; font-weight:600;
            padding:7px 16px; border-radius:8px; white-space:nowrap; }}
  .narr {{ background:#F5F3FF; border-left:4px solid var(--accent); border-radius:0 10px 10px 0;
           padding:16px 20px; margin:22px 0; font-size:14.5px; color:#1e293b; }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--accent);
        margin:30px 0 12px; font-weight:700; }}
  .kpis {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
  .kpi-label {{ margin:0; font-size:11px; color:var(--sub); }}
  .kpi-value {{ margin:5px 0 2px; font-size:25px; font-weight:700; line-height:1; }}
  .kpi-sub {{ margin:0; font-size:11px; color:var(--muted); }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; }}
  .card h3 {{ margin:0 0 14px; font-size:14px; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:10px; font-size:12px; color:var(--sub); }}
  .legend i {{ width:10px; height:10px; border-radius:2px; display:inline-block; margin-right:5px; vertical-align:middle; }}
  .chart-box {{ position:relative; height:240px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.04em;
        color:var(--muted); font-weight:600; padding:8px 10px; border-bottom:1px solid var(--line); }}
  td {{ padding:8px 10px; border-top:1px solid var(--line); }}
  td.mono {{ font-family:'Consolas',monospace; white-space:nowrap; }}
  .empty {{ text-align:center; color:var(--muted); padding:18px; }}
  .bar-wrap {{ display:flex; align-items:center; gap:9px; }}
  .bar-track {{ flex:1; height:6px; border-radius:3px; background:#EEF1F8; overflow:hidden; max-width:120px; }}
  .bar-fill {{ height:6px; border-radius:3px; }}
  footer {{ margin-top:34px; padding-top:16px; border-top:1px solid var(--line);
            display:flex; justify-content:space-between; color:var(--muted); font-size:12px; }}
  footer a {{ color:var(--accent); text-decoration:none; }}
  @media (max-width:720px) {{ .kpis {{ grid-template-columns:repeat(3,1fr); }} .grid2 {{ grid-template-columns:1fr; }} }}
  @media print {{ body {{ background:#fff; }} .wrap {{ max-width:none; }}
    .card,.kpi {{ break-inside:avoid; }} h2 {{ break-after:avoid; }} }}
{_TABLE_CSS}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <div class="logo">◆</div>
      <div>
        <h1>{_esc(meta['title'])}</h1>
        <p class="sub">{_esc(meta['period_label'])} · generado {_esc(meta['generated'])}</p>
      </div>
    </div>
    <div class="hd-actions">
      <button class="dl-btn no-print" onclick="window.print()">⤓ Descargar PDF</button>
      <span class="badge">Ejecutivo</span>
    </div>
  </header>

  <div class="narr">{_esc(data['narrative'])}</div>

  <h2>Indicadores clave</h2>
  <div class="kpis">{kpis_html}</div>

  <h2>Distribución y clientes</h2>
  <div class="grid2">
    <div class="card">
      <h3>Distribución por estado</h3>
      <div class="legend">
        <span><i style="background:{GREEN}"></i>Aprobado</span>
        <span><i style="background:{BLUE}"></i>Enviado</span>
        <span><i style="background:{AMBER}"></i>Devoluciones</span>
        <span><i style="background:{SLATE}"></i>Sin enviar</span>
      </div>
      <div class="chart-box"><canvas id="estadoChart"></canvas></div>
    </div>
    <div class="card">
      <h3>Top clientes · días medios de respuesta</h3>
      <div class="chart-box"><canvas id="clientesChart"></canvas></div>
    </div>
  </div>

  <h2>Actividad mes a mes</h2>
  <div class="card">
    <div class="legend">
      <span><i style="background:{BLUE}"></i>Enviados</span>
      <span><i style="background:{GREEN}"></i>Aprobados</span>
      <span><i style="background:{AMBER}"></i>Devueltos</span>
      <span style="color:var(--muted)">· el mes en curso va incompleto</span>
    </div>
    <div class="chart-box"><canvas id="actividadChart"></canvas></div>
  </div>

  <h2>Ranking de equipo</h2>
  <div class="tbl-panel card" style="padding:14px 16px">
    <div class="tbl-tools">
      <input class="tbl-search" type="text" placeholder="Buscar responsable…">
      <span class="tbl-count"></span>
      <span class="tbl-hint">· clic en una columna para ordenar</span>
    </div>
    <table>
      <thead><tr><th data-sort="num">#</th><th data-sort="text">Responsable</th>
        <th data-sort="num">Total</th><th data-sort="num">Aprob.</th>
        <th data-sort="num">% Compl.</th><th data-sort="num">Devol.</th>
        <th data-sort="num">Tasa Dev.</th><th data-sort="num">Críticos</th></tr></thead>
      <tbody>{_exec_ranking_html(data['ranking'])}</tbody>
    </table>
  </div>

  <h2>Pedidos con la documentación atrasada</h2>
  <p class="sub" style="margin:-6px 0 12px">{reparto}</p>
  <div class="tbl-panel card" style="padding:14px 16px">
    <div class="tbl-tools">
      <input class="tbl-search" type="text" placeholder="Buscar pedido o cliente…">
      <span class="tbl-count"></span>
      <span class="tbl-hint">· clic en una columna para ordenar</span>
    </div>
    <table>
      <thead><tr><th data-sort="text">Pedido</th><th data-sort="text">Cliente</th>
        <th data-sort="text">Aprob/Total</th><th data-sort="num">% Real</th>
        <th data-sort="num">% Esper.</th><th data-sort="num">Desv.</th>
        <th data-sort="num">Nuestros</th><th data-sort="num">En cliente</th>
        <th data-sort="text">Plazo</th></tr></thead>
      <tbody>{_exec_avance_html(data['avance'])}</tbody>
    </table>
  </div>

  <h2>Comercial</h2>
  <div class="tbl-panel card" style="padding:14px 16px">
    <div class="tbl-tools">
      <span class="tbl-count"></span>
      <span class="tbl-hint">· la adjudicación se calcula sobre las ofertas resueltas
        (ganadas frente a perdidas); las vivas van aparte</span>
    </div>
    <table>
      <thead><tr><th data-sort="num">Año</th><th data-sort="num">Ofertas</th>
        <th data-sort="num">Ganadas</th><th data-sort="num">Perdidas</th>
        <th data-sort="num">Vivas</th><th data-sort="num">Adjudicación</th>
        <th data-sort="text">Pedidos</th></tr></thead>
      <tbody>{_exec_comercial_html(data['comercial'])}</tbody>
    </table>
  </div>

  <h2>Scorecard de clientes</h2>
  <div class="tbl-panel card" style="padding:14px 16px">
    <div class="tbl-tools">
      <input class="tbl-search" type="text" placeholder="Buscar cliente…">
      <span class="tbl-count"></span>
      <span class="tbl-hint">· clic en una columna para ordenar</span>
    </div>
    <table>
      <thead><tr><th data-sort="text">Cliente</th><th data-sort="num">Score</th>
        <th data-sort="num">% Aprob. 1ªRev</th><th data-sort="num">Días resp.</th>
        <th data-sort="num">Crít. +30d</th><th data-sort="num">Total</th></tr></thead>
      <tbody>{_exec_scorecard_html(data['scorecard'])}</tbody>
    </table>
  </div>

  <footer>
    <span>DocFlow · Reporte ejecutivo</span>
    <span>© 2026 <a href="https://github.com/jparedesDS">{_esc(meta['prepared_by'])}</a></span>
  </footer>
</div>
{chart_tag}
<script>
(function() {{
  var D = {payload};
  if (typeof Chart === "undefined") return;
  Chart.defaults.font.family = "'Segoe UI',system-ui,sans-serif";
  Chart.defaults.color = "#64748B";
  var noLegend = {{ legend: {{ display: false }} }};
  new Chart(document.getElementById("estadoChart"), {{
    type: "doughnut",
    data: {{ labels: D.estado.labels, datasets: [{{ data: D.estado.values,
             backgroundColor: D.estado.colors, borderWidth: 0 }}] }},
    options: {{ responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: noLegend }}
  }});
  new Chart(document.getElementById("clientesChart"), {{
    type: "bar",
    data: {{ labels: D.clientes.labels, datasets: [{{ data: D.clientes.values,
             backgroundColor: D.accent, borderRadius: 4 }}] }},
    options: {{ indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: noLegend,
               scales: {{ x: {{ beginAtZero: true, title: {{ display: true, text: "días" }} }} }} }}
  }});
  var A = D.actividad;
  var linea = function(label, datos, color) {{
    return {{ label: label, data: datos, borderColor: color, backgroundColor: color,
              tension: .25, borderWidth: 2, pointRadius: 3 }};
  }};
  new Chart(document.getElementById("actividadChart"), {{
    type: "line",
    data: {{ labels: A.labels, datasets: [linea("Enviados", A.enviados, D.azul),
             linea("Aprobados", A.aprobados, D.verde),
             linea("Devueltos", A.devueltos, D.ambar)] }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: noLegend,
               interaction: {{ mode: "index", intersect: false }},
               scales: {{ y: {{ beginAtZero: true }} }} }}
  }});
}})();
</script>
<script>{_TABLE_JS}</script>
</body>
</html>"""


def generate_executive(ref_date: datetime | None = None, with_ai: bool = True):
    """Genera el reporte ejecutivo HTML y lo guarda. Devuelve (Path, data)."""
    data = build_executive_report_data(ref_date, with_ai=with_ai)
    html_str = render_executive_html(data)
    path = reports_dir() / f"Reporte_Ejecutivo_{data['meta']['key']}.html"
    path.write_text(html_str, encoding="utf-8")
    logger.info("Reporte ejecutivo generado: %s", path)
    return path, data


def _executive_email_body(data: dict) -> str:
    meta = data["meta"]
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;color:#0F172A;font-size:14px;line-height:1.6">'
        f'<p>Hola,</p>'
        f'<p>Adjunto el <b>{_esc(meta["title"])}</b> de <b>{_esc(meta["period_label"])}</b>: '
        f'KPIs globales, actividad mes a mes, ranking del equipo, pedidos con la documentación '
        f'atrasada (con el reparto de lo pendiente entre nosotros y el cliente), embudo comercial '
        f'y scorecard de clientes. Ábrelo en el navegador para ver los gráficos interactivos.</p>'
        '<p style="color:#475569">Generado automáticamente por DocFlow.</p>'
        '<p style="color:#94A3B8;font-size:12px">© jparedesDS</p>'
        '</div>'
    )


def send_executive_html_email(to: list[str] | None = None, cc: list[str] | None = None,
                              ref_date: datetime | None = None) -> dict:
    if not to:
        return {"status": "skipped", "reason": "Sin destinatarios"}
    from core.services.smtp import send_html_email

    data = build_executive_report_data(ref_date)
    html_str = render_executive_html(data)
    fname = f"Reporte_Ejecutivo_{data['meta']['key']}.html"
    subject = f"{data['meta']['title']} — {data['meta']['period_label']}"
    result = send_html_email(
        to=to, cc=cc or [], subject=subject, html_body=_executive_email_body(data),
        attachment_eml=html_str.encode("utf-8"), attachment_name=fname)
    try:
        (reports_dir() / fname).write_text(html_str, encoding="utf-8")
    except Exception:
        logger.debug("No se pudo guardar copia local del reporte ejecutivo", exc_info=True)
    result["status"] = "sent"
    result["recipients"] = to
    return result


def post_executive_to_teams(ref_date: datetime | None = None) -> dict:
    data = build_executive_report_data(ref_date, with_ai=False)
    t, c, p = data["totals"], data["ciclo"], data["pelota"]
    riesgo = next((k["value"] for k in data["kpis"] if k["label"] == "En riesgo"), 0)
    facts = [
        ("Documentos", t["total"]),
        ("Aprobación global", f"{t['pct']}%"),
        ("Respuesta del cliente", f"{c['mediana']} d de mediana"),
        ("En riesgo (+15d)", riesgo),
        ("Pedidos atrasados", f"{p['atrasados']} de {p['total']}"),
        ("Pendiente en nuestro tejado", f"{p['nuestros']} docs"),
    ]
    from core.services import teams
    return teams.post_card(data["meta"]["title"], data["meta"]["period_label"],
                           data["narrative"], facts)
