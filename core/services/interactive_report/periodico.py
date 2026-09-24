"""Informe interactivo semanal y mensual.

El periodo se calcula sobre los eventos datados del documento: las
entradas de `Historial Rev.` más el envío de la revisión actual. Los
KPIs de cartera y la tabla de riesgo son una foto del estado de hoy.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.services import monitoring as monitoring_service
from core.services.interactive_report.comun import (
    ACCENT,
    AMBER,
    BLUE,
    GREEN,
    RED,
    _MESES,
    _MESES_ABBR,
    _OCULTAR_RESP,
    _TABLE_CSS,
    _TABLE_JS,
    _ask_haiku,
    _chartjs_source,
    _es_critico,
    _esc,
    _kpi_card_html,
    _num,
    reports_dir,
)

logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


@dataclass
class Window:
    start: datetime
    end: datetime          # exclusivo
    label: str
    key: str               # p.ej. "2026-S25" o "2026-06"


def _period_window(period: str, ref: datetime) -> Window:
    ref = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "monthly":
        start = ref.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        label = f"{_MESES[start.month]} {start.year}"
        key = start.strftime("%Y-%m")
    else:  # weekly
        start = ref - timedelta(days=ref.weekday())  # lunes
        end = start + timedelta(days=7)
        last = end - timedelta(days=1)
        iso = start.isocalendar()
        label = (f"Semana {iso.week} · {start.day} {_MESES_ABBR[start.month]} – "
                 f"{last.day} {_MESES_ABBR[last.month]} {last.year}")
        key = f"{iso.year}-S{iso.week:02d}"
    return Window(start, end, label, key)


def _previous_window(period: str, cur_start: datetime) -> Window:
    prev_ref = cur_start - timedelta(days=1 if period == "monthly" else 7)
    return _period_window(period, prev_ref)


def get_available_periods(period: str, n: int = 8) -> list[tuple[str, str]]:
    """[(label, ref_date_iso), …] para los últimos `n` periodos (incluye el actual)."""
    out: list[tuple[str, str]] = []
    win = _period_window(period, datetime.now())
    for _ in range(n):
        out.append((win.label, win.start.isoformat()))
        win = _previous_window(period, win.start)
    return out


def _classify(estado: str) -> str | None:
    e = (estado or "").lower().strip()
    if "aprobado" in e:
        return "aprobado"
    if any(s in e for s in ("rechazado", "com.", "comentado", "devuel")):
        return "devuelto"
    if "enviado" in e:
        return "enviado"
    return None


def _doc_events(doc: dict) -> list[tuple[datetime, str]]:
    """Eventos (fecha, tipo) del documento. tipo ∈ {enviado, aprobado, devuelto}."""
    events: list[tuple[datetime, str]] = []
    seen: set[tuple] = set()
    hist = str(doc.get("Historial Rev.", "") or "")
    for tok in hist.split("//"):
        m = monitoring_service._REV_HIST_RE.search(tok)
        if not m:
            continue
        d = monitoring_service._parse_date(m.group(1))
        kind = _classify(m.group(2))
        if d is None or kind is None:
            continue
        key = (d.date(), kind)
        if key not in seen:
            seen.add(key)
            events.append((d, kind))

    # Envío de la revisión actual (no siempre figura en el historial)
    cur = monitoring_service._parse_date(doc.get("Fecha Env. Doc.") or doc.get("Fecha"))
    if cur is not None and (cur.date(), "enviado") not in seen:
        events.append((cur, "enviado"))
    return events


def _delta(cur: int, prev: int) -> dict:
    diff = cur - prev
    pct = round(diff / prev * 100) if prev else None
    return {"diff": diff, "pct": pct}


def _series(cur_ev: list, win: Window, period: str) -> dict:
    if period == "monthly":
        ndays = (win.end - win.start).days
        labels = [str(i + 1) for i in range(ndays)]
        values = [0] * ndays
        for dt, *_ in cur_ev:
            idx = (dt.date() - win.start.date()).days
            if 0 <= idx < ndays:
                values[idx] += 1
        return {"labels": labels, "values": values}
    names = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    values = [0] * 7
    for dt, *_ in cur_ev:
        idx = (dt.date() - win.start.date()).days
        if 0 <= idx < 7:
            values[idx] += 1
    return {"labels": names, "values": values}


def _by_responsable(cur_ev_docs: list) -> dict:
    c: Counter = Counter()
    for _, _, doc in cur_ev_docs:
        resp = str(doc.get("Repsonsable", "") or "").strip()
        if resp in _OCULTAR_RESP:
            continue
        c[resp] += 1
    top = c.most_common(10)
    return {"labels": [k for k, _ in top], "values": [v for _, v in top]}


def _aging(docs: list, limit: int = 12) -> list[dict]:
    rows = []
    for d in docs:
        estado = str(d.get("Estado", "") or "").lower().strip()
        if "aprobado" in estado or estado == "enviado":
            continue
        dias = _num(d.get("Días Devolución"))
        if dias is None or dias <= 0:
            continue
        rows.append({
            "pedido": str(d.get("Nº Pedido", "") or ""),
            "doc": str(d.get("Nº Doc. EIPSA", "") or "") or str(d.get("Título", "") or ""),
            "resp": str(d.get("Repsonsable", "") or ""),
            "estado": str(d.get("Estado", "") or "Sin enviar"),
            "dias": int(dias),
            "critico": _es_critico(d),
        })
    rows.sort(key=lambda r: r["dias"], reverse=True)
    return rows[:limit]


def build_report_data(period: str = "weekly", ref_date: datetime | None = None,
                      with_ai: bool = True) -> dict:
    """Agrega todos los datos del informe para `period` ∈ {weekly, monthly}."""
    period = "monthly" if period == "monthly" else "weekly"
    docs = monitoring_service.get_monitoring_data()
    win = _period_window(period, ref_date or datetime.now())
    prev = _previous_window(period, win.start)

    cur_ev_docs, prev_ev = [], []
    for d in docs:
        for dt, kind in _doc_events(d):
            if win.start <= dt < win.end:
                cur_ev_docs.append((dt, kind, d))
            elif prev.start <= dt < prev.end:
                prev_ev.append((dt, kind))

    def _counts(evs) -> dict:
        c = {"movimientos": len(evs), "enviado": 0, "aprobado": 0, "devuelto": 0}
        for item in evs:
            kind = item[1]
            c[kind] = c.get(kind, 0) + 1
        return c

    cc = _counts(cur_ev_docs)
    pc = _counts(prev_ev)

    kpis = [
        {"label": "Movimientos", "value": cc["movimientos"],
         "delta": _delta(cc["movimientos"], pc["movimientos"]), "good_up": True},
        {"label": "Enviados", "value": cc["enviado"],
         "delta": _delta(cc["enviado"], pc["enviado"]), "good_up": True},
        {"label": "Aprobados", "value": cc["aprobado"],
         "delta": _delta(cc["aprobado"], pc["aprobado"]), "good_up": True},
        {"label": "Devoluciones", "value": cc["devuelto"],
         "delta": _delta(cc["devuelto"], pc["devuelto"]), "good_up": False},
    ]

    snap = monitoring_service.compute_kpis(docs)
    snapshot = {
        "total": snap["total"],
        "pct_global": snap["pct_completado"],
        "criticos": snap["criticos"],
        "riesgo": snap["criticos_15d"],
        "media_dias": snap["media_dias_devolucion"],
    }

    estado_donut = {
        "labels": ["Enviado", "Aprobado", "Devuelto"],
        "values": [cc["enviado"], cc["aprobado"], cc["devuelto"]],
        "colors": [BLUE, GREEN, AMBER],
    }

    data = {
        "meta": {
            "title": f"Informe {'mensual' if period == 'monthly' else 'semanal'} de documentación",
            "period_label": win.label,
            "period_kind": period,
            "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "prepared_by": "jparedesDS",
            "key": win.key,
        },
        "kpis": kpis,
        "series": _series(cur_ev_docs, win, period),
        "estado": estado_donut,
        "resp": _by_responsable(cur_ev_docs),
        "snapshot": snapshot,
        "aging": _aging(docs),
    }
    data["narrative"] = _narrative(data, with_ai=with_ai)
    return data


def _fallback_narrative(d: dict) -> str:
    k = {x["label"]: x for x in d["kpis"]}
    mov = k["Movimientos"]
    diff = mov["delta"]["diff"]
    tend = ("se mantuvo estable" if diff == 0 else
            (f"creció en {diff}" if diff > 0 else f"bajó en {abs(diff)}"))
    resp = d["resp"]
    top_resp = f" El responsable con más actividad fue {resp['labels'][0]}." if resp["labels"] else ""
    return (
        f"Durante {d['meta']['period_label'].split('·')[0].strip().lower()} se registraron "
        f"{mov['value']} movimientos (la actividad {tend} respecto al periodo anterior): "
        f"{k['Enviados']['value']} envíos, {k['Aprobados']['value']} aprobaciones y "
        f"{k['Devoluciones']['value']} devoluciones. La cartera mantiene un "
        f"{d['snapshot']['pct_global']}% de aprobación global, con "
        f"{d['snapshot']['riesgo']} documento(s) crítico(s) en riesgo (+15 días sin respuesta)."
        f"{top_resp}"
    )


def _build_ai_prompt(d: dict) -> str:
    k = {x["label"]: x for x in d["kpis"]}
    def line(lbl):
        x = k[lbl]
        dd = x["delta"]["diff"]
        return f"- {lbl}: {x['value']} (Δ {'+' if dd >= 0 else ''}{dd} vs periodo anterior)"
    return f"""Eres un asistente ejecutivo de un equipo de Document Control (documentación técnica de ingeniería).
Redacta un PÁRRAFO EJECUTIVO BREVE (2-3 frases, español, tono profesional) para el
informe del periodo «{d['meta']['period_label']}» con estos datos:

{line('Movimientos')}
{line('Enviados')}
{line('Aprobados')}
{line('Devoluciones')}
- Aprobación global de la cartera: {d['snapshot']['pct_global']}%
- Documentos críticos en riesgo (+15 días): {d['snapshot']['riesgo']}
- Velocidad media de respuesta: {d['snapshot']['media_dias']} días

Menciona la tendencia, el punto de atención más crítico y una acción recomendada.
Solo un párrafo, sin HTML ni markdown, directo y accionable."""


def _narrative(d: dict, with_ai: bool = True) -> str:
    if with_ai:
        txt = _ask_haiku(_build_ai_prompt(d))
        if txt:
            return txt
    return _fallback_narrative(d)


def _aging_rows_html(rows: list[dict]) -> str:
    if not rows:
        return ('<tr><td colspan="4" class="empty">Sin documentos pendientes con '
                'antigüedad registrada.</td></tr>')
    mx = max((r["dias"] for r in rows), default=1) or 1
    out = []
    for r in rows:
        dias = r["dias"]
        col = RED if dias > 15 else (AMBER if dias > 7 else GREEN)
        pct = min(100, round(dias / mx * 100))
        crit = ' <span class="crit">crítico</span>' if r["critico"] else ""
        out.append(
            f'<tr><td class="mono">{_esc(r["pedido"])}</td>'
            f'<td class="muted">{_esc(r["doc"][:42])}{crit}</td>'
            f'<td>{_esc(r["resp"])}</td>'
            f'<td><div class="bar-wrap"><div class="bar-track">'
            f'<div class="bar-fill" style="width:{pct}%;background:{col}"></div></div>'
            f'<span style="color:{col};font-weight:600">{dias}</span></div></td></tr>'
        )
    return "".join(out)


def render_html(data: dict) -> str:
    meta = data["meta"]
    kpis_html = "".join(_kpi_card_html(k) for k in data["kpis"])
    aging_html = _aging_rows_html(data["aging"])
    chartjs = _chartjs_source()
    chart_tag = (f"<script>{chartjs}</script>" if chartjs else
                 '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>')

    payload = json.dumps({
        "series": data["series"],
        "estado": data["estado"],
        "resp": data["resp"],
        "accent": ACCENT,
    }, ensure_ascii=False)

    snap = data["snapshot"]
    is_month = meta["period_kind"] == "monthly"

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
          font-family:'Segoe UI',system-ui,-apple-system,Roboto,Arial,sans-serif;
          line-height:1.5; }}
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
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  .kpi-label {{ margin:0; font-size:12px; color:var(--sub); }}
  .kpi-value {{ margin:6px 0 4px; font-size:30px; font-weight:700; line-height:1; }}
  .delta {{ font-size:12px; font-weight:600; }}
  .delta.up {{ color:{GREEN}; }} .delta.down {{ color:{RED}; }} .delta.flat {{ color:var(--muted); }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; }}
  .card h3 {{ margin:0 0 14px; font-size:14px; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:10px; font-size:12px; color:var(--sub); }}
  .legend i {{ width:10px; height:10px; border-radius:2px; display:inline-block; margin-right:5px; vertical-align:middle; }}
  .chart-box {{ position:relative; height:230px; }}
  .snap {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
  .snap .kpi-value {{ font-size:26px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.04em;
        color:var(--muted); font-weight:600; padding:8px 10px; }}
  td {{ padding:9px 10px; border-top:1px solid var(--line); }}
  td.mono {{ font-family:'Consolas',monospace; }}
  td.muted {{ color:var(--sub); }}
  .crit {{ color:{RED}; font-size:11px; font-weight:600; }}
  .empty {{ text-align:center; color:var(--muted); padding:18px; }}
  .bar-wrap {{ display:flex; align-items:center; gap:9px; }}
  .bar-track {{ flex:1; height:6px; border-radius:3px; background:#EEF1F8; overflow:hidden; }}
  .bar-fill {{ height:6px; border-radius:3px; }}
  footer {{ margin-top:34px; padding-top:16px; border-top:1px solid var(--line);
            display:flex; justify-content:space-between; color:var(--muted); font-size:12px; }}
  footer a {{ color:var(--accent); text-decoration:none; }}
  @media (max-width:720px) {{ .kpis,.snap {{ grid-template-columns:repeat(2,1fr); }} .grid2 {{ grid-template-columns:1fr; }} }}
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
      <span class="badge">{'Mensual' if is_month else 'Semanal'}</span>
    </div>
  </header>

  <div class="narr">{_esc(data['narrative'])}</div>

  <h2>KPIs del periodo</h2>
  <div class="kpis">{kpis_html}</div>

  <h2>Análisis del periodo</h2>
  <div class="grid2">
    <div class="card">
      <h3>Distribución de actividad por estado</h3>
      <div class="legend">
        <span><i style="background:{BLUE}"></i>Enviado</span>
        <span><i style="background:{GREEN}"></i>Aprobado</span>
        <span><i style="background:{AMBER}"></i>Devuelto</span>
      </div>
      <div class="chart-box"><canvas id="estadoChart"></canvas></div>
    </div>
    <div class="card">
      <h3>Actividad por responsable</h3>
      <div class="chart-box"><canvas id="respChart"></canvas></div>
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <h3>Actividad {'diaria' if not is_month else 'por día del mes'}</h3>
    <div class="chart-box"><canvas id="dailyChart"></canvas></div>
  </div>

  <h2>Estado actual de la cartera</h2>
  <div class="snap">
    <div class="kpi"><p class="kpi-label">Documentos totales</p><p class="kpi-value">{snap['total']}</p></div>
    <div class="kpi"><p class="kpi-label">Aprobación global</p><p class="kpi-value" style="color:{GREEN}">{snap['pct_global']}%</p></div>
    <div class="kpi"><p class="kpi-label">Críticos</p><p class="kpi-value" style="color:{RED if snap['criticos'] else GREEN}">{snap['criticos']}</p></div>
    <div class="kpi"><p class="kpi-label">En riesgo (+15d)</p><p class="kpi-value" style="color:{RED if snap['riesgo'] else GREEN}">{snap['riesgo']}</p></div>
  </div>

  <h2>Documentos en riesgo · mayor antigüedad sin movimiento</h2>
  <div class="tbl-panel card" style="padding:14px 16px">
    <div class="tbl-tools">
      <input class="tbl-search" type="text" placeholder="Buscar pedido, documento o responsable…">
      <span class="tbl-count"></span>
    </div>
    <table>
      <thead><tr><th data-sort="text">Pedido</th><th data-sort="text">Documento</th>
        <th data-sort="text">Resp.</th><th data-sort="num" style="width:160px">Días sin mover</th></tr></thead>
      <tbody>{aging_html}</tbody>
    </table>
  </div>

  <footer>
    <span>DocFlow · Informe de documentación</span>
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
    options: {{ responsive: true, maintainAspectRatio: false, cutout: "62%",
               plugins: noLegend }}
  }});
  new Chart(document.getElementById("respChart"), {{
    type: "bar",
    data: {{ labels: D.resp.labels, datasets: [{{ data: D.resp.values,
             backgroundColor: D.accent, borderRadius: 4 }}] }},
    options: {{ indexAxis: "y", responsive: true, maintainAspectRatio: false,
               plugins: noLegend, scales: {{ x: {{ beginAtZero: true,
               ticks: {{ precision: 0 }} }} }} }}
  }});
  new Chart(document.getElementById("dailyChart"), {{
    type: "line",
    data: {{ labels: D.series.labels, datasets: [{{ data: D.series.values,
             borderColor: D.accent, backgroundColor: "rgba(79,70,229,.14)",
             fill: true, tension: .35, pointRadius: 3,
             pointBackgroundColor: D.accent }}] }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: noLegend,
               scales: {{ y: {{ beginAtZero: true, ticks: {{ precision: 0 }} }} }} }}
  }});
}})();
</script>
<script>{_TABLE_JS}</script>
</body>
</html>"""


def default_filename(data: dict) -> str:
    kind = "Mensual" if data["meta"]["period_kind"] == "monthly" else "Semanal"
    return f"Informe_{kind}_{data['meta']['key']}.html"


def generate(period: str = "weekly", ref_date: datetime | None = None,
             with_ai: bool = True):
    """Construye los datos, renderiza el HTML y lo guarda en state/reports/.
    Devuelve (Path, data)."""
    data = build_report_data(period, ref_date, with_ai=with_ai)
    html_str = render_html(data)
    path = reports_dir() / default_filename(data)
    path.write_text(html_str, encoding="utf-8")
    logger.info("Informe generado: %s", path)
    return path, data


def _email_body(data: dict) -> str:
    meta = data["meta"]
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;color:#0F172A;font-size:14px;line-height:1.6">'
        f'<p>Hola,</p>'
        f'<p>Adjunto el <b>{_esc(meta["title"])}</b> correspondiente a '
        f'<b>{_esc(meta["period_label"])}</b>. Ábrelo en el navegador para ver los '
        f'gráficos interactivos (KPIs, actividad, responsables y documentos en riesgo).</p>'
        '<p style="color:#475569">Generado automáticamente por DocFlow.</p>'
        '<p style="color:#94A3B8;font-size:12px">© jparedesDS</p>'
        '</div>'
    )


def send_email(period: str = "weekly", to: list[str] | None = None,
               cc: list[str] | None = None, ref_date: datetime | None = None) -> dict:
    """Genera el informe y lo envía adjunto (.html) por SMTP."""
    if not to:
        return {"status": "skipped", "reason": "Sin destinatarios"}
    from core.services.smtp import send_html_email

    data = build_report_data(period, ref_date)
    html_str = render_html(data)
    fname = default_filename(data)
    subject = f"{data['meta']['title']} — {data['meta']['period_label']}"
    result = send_html_email(
        to=to, cc=cc or [], subject=subject, html_body=_email_body(data),
        attachment_eml=html_str.encode("utf-8"), attachment_name=fname)
    # Guarda también copia local
    try:
        (reports_dir() / fname).write_text(html_str, encoding="utf-8")
    except Exception:
        logger.debug("No se pudo guardar copia local del informe", exc_info=True)
    result["status"] = "sent"
    result["recipients"] = to
    return result


def post_period_to_teams(period: str = "weekly", ref_date: datetime | None = None) -> dict:
    data = build_report_data(period, ref_date, with_ai=False)
    k = {x["label"]: x["value"] for x in data["kpis"]}
    facts = [
        ("Movimientos", k.get("Movimientos")),
        ("Enviados", k.get("Enviados")),
        ("Aprobados", k.get("Aprobados")),
        ("Devoluciones", k.get("Devoluciones")),
        ("Aprobación global", f"{data['snapshot']['pct_global']}%"),
        ("En riesgo (+15d)", data["snapshot"]["riesgo"]),
    ]
    from core.services import teams
    return teams.post_card(data["meta"]["title"], data["meta"]["period_label"],
                           data["narrative"], facts)
