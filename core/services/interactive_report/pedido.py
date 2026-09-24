"""Informe interactivo de un pedido.

Documentos, avance, predicción de cierre y el detalle de lo que falta.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime

from core.services import monitoring as monitoring_service
from core.services.interactive_report.comun import (
    ACCENT,
    AMBER,
    BLUE,
    GREEN,
    RED,
    SLATE,
    _TABLE_CSS,
    _TABLE_JS,
    _ask_haiku,
    _chartjs_source,
    _es_critico,
    _esc,
    _num,
    reports_dir,
)

logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


_ESTADO_CHIP = {
    "aprobado": ("Aprobado", GREEN),
    "rechazado": ("Rechazado", RED),
    "com. menores": ("Com. menores", AMBER),
    "com. mayores": ("Com. mayores", AMBER),
    "comentado": ("Comentado", AMBER),
    "enviado": ("Enviado", BLUE),
}


def _estado_label_color(estado: str) -> tuple[str, str]:
    e = (estado or "").lower().strip()
    if not e or e == "sin enviar":
        return ("Sin enviar", SLATE)
    for k, (lbl, col) in _ESTADO_CHIP.items():
        if k in e:
            return (lbl, col)
    return (str(estado).strip().title(), SLATE)


def list_pedidos() -> list[dict]:
    """[{pedido, cliente, total}, …] para poblar selectores (orden pedido desc)."""
    rows = monitoring_service.get_status_global()
    out = [{"pedido": r["pedido"], "cliente": r["cliente"], "total": r["total"]} for r in rows]
    out.sort(key=lambda r: r["pedido"], reverse=True)
    return out


def _pedido_prediction(base: str) -> dict | None:
    try:
        from core.services import erp
        for x in erp.get_seguimiento():
            if monitoring_service._normalize_pedido(str(x.get("pedido", ""))) == base:
                return x
    except Exception:
        logger.debug("Predicción de pedido no disponible", exc_info=True)
    return None


def build_pedido_report_data(pedido: str, with_ai: bool = True) -> dict:
    base = monitoring_service._normalize_pedido(pedido)
    all_docs = monitoring_service.get_monitoring_data()
    docs = [d for d in all_docs
            if monitoring_service._normalize_pedido(str(d.get("Nº Pedido", ""))) == base]

    first = docs[0] if docs else {}
    info = {
        "cliente": str(first.get("Cliente", "") or ""),
        "po": str(first.get("Nº PO", "") or ""),
        "oferta": str(first.get("Nº Oferta", "") or ""),
        "material": str(first.get("Material", "") or ""),
        "comercial": str(first.get("Responsable", "") or ""),
        "fecha_pedido": monitoring_service.fmt_date_ddmmyyyy(first.get("Fecha Pedido")),
        "fecha_prevista": monitoring_service.fmt_date_ddmmyyyy(first.get("Fecha Prevista")),
    }

    ap = en = dev = sin = crit = 0
    dias_max = 0
    tipo_counter: Counter = Counter()
    table = []
    for d in docs:
        est = str(d.get("Estado", "") or "").lower().strip()
        if "aprobado" in est:
            ap += 1
            ekey = "aprobado"
        elif est == "enviado":
            en += 1
            ekey = "enviado"
        elif any(s in est for s in ("rechazado", "com.", "comentado", "devuel")):
            dev += 1
            ekey = "devuelto"
        else:
            sin += 1
            ekey = "sin"
        if _es_critico(d) and "aprobado" not in est:
            crit += 1
        de = _num(d.get("Días Envío"))
        if de and de > dias_max:
            dias_max = de
        tipo_counter[str(d.get("Tipo Doc.", "") or "—").strip() or "—"] += 1
        dd = _num(d.get("Días Devolución"))
        lbl, col = _estado_label_color(d.get("Estado", ""))
        ms = monitoring_service.revision_milestones(d)
        table.append({
            "doc": str(d.get("Nº Doc. EIPSA", "") or ""),
            "titulo": str(d.get("Título", "") or ""),
            "tipo": str(d.get("Tipo Doc.", "") or ""),
            "rev": str(d.get("Nº Revisión", "") or ""),
            "estado_label": lbl, "estado_color": col, "estado_key": ekey,
            "fecha": monitoring_service.fmt_date_ddmmyyyy(d.get("Fecha Env. Doc.")),
            "first_send": monitoring_service.fmt_date_ddmmyyyy(ms["first_send"]),
            "first_appr": monitoring_service.fmt_date_ddmmyyyy(ms["first_approval"]),
            "dias": int(dd) if (dd and dd > 0) else 0,
            "dias_envio": int(de) if de else None,
            "info": str(d.get("Info/Review", "") or ""),
            "historial": str(d.get("Historial Rev.", "") or ""),
            "critico": _es_critico(d),
        })
    table.sort(key=lambda r: r["doc"])

    total = len(docs)
    pct = round(ap / total * 100) if total else 0
    tipo_top = tipo_counter.most_common(8)

    data = {
        "meta": {
            "title": f"Informe del pedido {base}",
            "pedido": base,
            "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "prepared_by": "jparedesDS",
            "key": base.replace("/", "-").replace(" ", ""),
        },
        "info": info,
        "kpis": {"total": total, "aprobados": ap, "pct": pct, "enviados": en,
                 "devoluciones": dev, "sin_enviar": sin, "criticos": crit, "dias_max": dias_max},
        "estado": {"labels": ["Aprobado", "Enviado", "Devuelto", "Sin enviar"],
                   "values": [ap, en, dev, sin], "colors": [GREEN, BLUE, AMBER, SLATE]},
        "tipo": {"labels": [t for t, _ in tipo_top], "values": [v for _, v in tipo_top]},
        "prediction": _pedido_prediction(base),
        "table": table,
    }
    data["narrative"] = _pedido_narrative(data, with_ai=with_ai)
    return data


def _pedido_fallback(d: dict) -> str:
    k, info = d["kpis"], d["info"]
    pred = d["prediction"] or {}
    plazo = ""
    if pred.get("en_plazo") is True:
        plazo = " Según la curva-S, el pedido avanza en plazo."
    elif pred.get("en_plazo") is False:
        plazo = " Atención: la previsión indica riesgo de retraso respecto a la fecha prevista."
    cli = f" ({info['cliente']})" if info["cliente"] else ""
    return (
        f"El pedido {d['meta']['pedido']}{cli} reúne {k['total']} documentos, de los cuales "
        f"{k['aprobados']} están aprobados ({k['pct']}%). Quedan {k['enviados']} en revisión del "
        f"cliente, {k['devoluciones']} con comentarios y {k['sin_enviar']} sin enviar, con "
        f"{k['criticos']} crítico(s) pendiente(s).{plazo}"
    )


def _pedido_ai_prompt(d: dict) -> str:
    k, info = d["kpis"], d["info"]
    pred = d["prediction"] or {}
    return f"""Eres un asistente de Document Control. Redacta un PÁRRAFO EJECUTIVO BREVE
(2-3 frases, español, profesional) sobre el estado del pedido {d['meta']['pedido']}
(cliente {info['cliente'] or 'n/d'}) con estos datos:
- Documentos totales: {k['total']}
- Aprobados: {k['aprobados']} ({k['pct']}%)
- Enviados (en revisión del cliente): {k['enviados']}
- Con devoluciones/comentarios: {k['devoluciones']}
- Sin enviar: {k['sin_enviar']}
- Críticos pendientes: {k['criticos']}
- Avance esperado (curva-S): {pred.get('pct_esperado')}% · ¿en plazo?: {pred.get('en_plazo')} · fecha prevista: {pred.get('fecha_prevista')}

Menciona el avance global, el riesgo principal y una acción recomendada. Sin HTML ni markdown."""


def _pedido_narrative(d: dict, with_ai: bool = True) -> str:
    if with_ai:
        txt = _ask_haiku(_pedido_ai_prompt(d))
        if txt:
            return txt
    return _pedido_fallback(d)


def _pedido_table_html(rows: list[dict]) -> str:
    if not rows:
        return ('<tr><td colspan="9" class="empty">Este pedido no tiene documentos '
                'registrados.</td></tr>')
    out = []
    for r in rows:
        dias = r["dias"]
        dcol = RED if dias > 15 else (AMBER if dias > 7 else SLATE)
        crit = ' <span class="crit">crítico</span>' if r["critico"] else ""
        out.append(
            f'<tr class="expandable" data-estado="{r.get("estado_key", "")}">'
            f'<td class="mono">{_esc(r["doc"])}</td>'
            f'<td class="muted">{_esc(r["titulo"][:52])}{crit}</td>'
            f'<td>{_esc(r["tipo"])}</td>'
            f'<td style="text-align:center">{_esc(r["rev"])}</td>'
            f'<td><span class="chip" style="background:{r["estado_color"]}">{_esc(r["estado_label"])}</span></td>'
            f'<td>{_esc(r["fecha"]) or "—"}</td>'
            f'<td>{_esc(r["first_send"]) or "—"}</td>'
            f'<td>{_esc(r["first_appr"]) or "—"}</td>'
            f'<td style="text-align:center;color:{dcol};font-weight:600">{dias or "—"}</td></tr>'
            f'<tr class="detail" hidden><td colspan="9">{_pedido_detail_html(r)}</td></tr>'
        )
    return "".join(out)


def _pedido_detail_html(r: dict) -> str:
    de = r.get("dias_envio")
    items = [
        ("Título completo", r.get("titulo") or "—"),
        ("Info / Review", r.get("info") or "—"),
        ("Días desde envío", de if de not in ("", None) else "—"),
        ("Crítico", "Sí" if r.get("critico") else "No"),
    ]
    grid = "".join(
        f'<div><p class="lab">{_esc(lab)}</p><p class="val">{_esc(val)}</p></div>'
        for lab, val in items)
    hist = (r.get("historial") or "").strip()
    hist_html = (
        f'<div style="margin-top:10px"><p class="lab">Historial de revisiones</p>'
        f'<p class="detail-hist">{_esc(hist)}</p></div>'
        if hist else "")
    return f'<div class="detail-grid">{grid}</div>{hist_html}'


def _pedido_prediction_html(pred: dict | None) -> str:
    if not pred or pred.get("pct_esperado") is None:
        return ""
    real = pred.get("pct", 0)
    esp = pred.get("pct_esperado", 0)
    en_plazo = pred.get("en_plazo")
    if en_plazo is True:
        badge = f'<span class="chip" style="background:{GREEN}">En plazo</span>'
    elif en_plazo is False:
        badge = f'<span class="chip" style="background:{RED}">En riesgo</span>'
    else:
        badge = ""
    return (
        '<div class="card" style="margin-top:16px"><h3>Predicción · curva-S</h3>'
        '<div class="info-grid">'
        f'<div><p class="lab">Avance real</p><p class="val">{real}%</p></div>'
        f'<div><p class="lab">Avance esperado</p><p class="val">{esp}%</p></div>'
        f'<div><p class="lab">Fecha prevista</p><p class="val">{_esc(pred.get("fecha_prevista") or "—")}</p></div>'
        f'<div><p class="lab">Predicción fin</p><p class="val">{_esc(pred.get("prediccion_fecha") or "—")}</p></div>'
        f'<div><p class="lab">Situación</p><p class="val">{badge or "—"}</p></div>'
        '</div></div>'
    )


def render_pedido_html(data: dict) -> str:
    meta, info, k = data["meta"], data["info"], data["kpis"]
    chartjs = _chartjs_source()
    chart_tag = (f"<script>{chartjs}</script>" if chartjs else
                 '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>')
    payload = json.dumps({"estado": data["estado"], "tipo": data["tipo"], "accent": ACCENT},
                         ensure_ascii=False)
    pred_html = _pedido_prediction_html(data["prediction"])
    table_html = _pedido_table_html(data["table"])

    def field(lab, val):
        return f'<div><p class="lab">{lab}</p><p class="val">{_esc(val or "—")}</p></div>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(meta['title'])}</title>
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
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; }}
  .card h3 {{ margin:0 0 14px; font-size:14px; }}
  .info-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px 24px; }}
  .info-grid .lab {{ margin:0; font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
  .info-grid .val {{ margin:3px 0 0; font-size:14px; font-weight:600; }}
  .kpis {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
  .kpi-label {{ margin:0; font-size:11px; color:var(--sub); }}
  .kpi-value {{ margin:5px 0 0; font-size:26px; font-weight:700; line-height:1; }}
  .prog {{ margin:14px 0 0; }}
  .prog-track {{ height:10px; border-radius:5px; background:var(--line); overflow:hidden; }}
  .prog-fill {{ height:10px; border-radius:5px; background:{GREEN}; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:10px; font-size:12px; color:var(--sub); }}
  .legend i {{ width:10px; height:10px; border-radius:2px; display:inline-block; margin-right:5px; vertical-align:middle; }}
  .chart-box {{ position:relative; height:230px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.04em;
        color:var(--muted); font-weight:600; padding:8px 10px; border-bottom:1px solid var(--line); }}
  td {{ padding:8px 10px; border-top:1px solid var(--line); }}
  td.mono {{ font-family:'Consolas',monospace; white-space:nowrap; }}
  td.muted {{ color:var(--sub); }}
  .chip {{ display:inline-block; padding:2px 9px; border-radius:6px; font-size:11px; font-weight:600; color:#fff; }}
  .crit {{ color:{RED}; font-size:11px; font-weight:600; }}
  .empty {{ text-align:center; color:var(--muted); padding:18px; }}
  footer {{ margin-top:34px; padding-top:16px; border-top:1px solid var(--line);
            display:flex; justify-content:space-between; color:var(--muted); font-size:12px; }}
  footer a {{ color:var(--accent); text-decoration:none; }}
  @media (max-width:720px) {{ .kpis {{ grid-template-columns:repeat(3,1fr); }} .grid2 {{ grid-template-columns:1fr; }} }}
  @media print {{ body {{ background:#fff; }} .wrap {{ max-width:none; }}
    .card,.kpi {{ break-inside:avoid; }} h2 {{ break-after:avoid; }}
    .pagebreak {{ break-before:page; }} }}
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
        <p class="sub">{_esc(info['cliente'] or 'Cliente n/d')} · generado {_esc(meta['generated'])}</p>
      </div>
    </div>
    <div class="hd-actions">
      <button class="dl-btn no-print" onclick="window.print()">⤓ Descargar PDF</button>
      <span class="badge">Pedido</span>
    </div>
  </header>

  <div class="narr">{_esc(data['narrative'])}</div>

  <h2>Ficha del pedido</h2>
  <div class="card">
    <div class="info-grid">
      {field("Cliente", info['cliente'])}
      {field("Nº PO", info['po'])}
      {field("Nº Oferta", info['oferta'])}
      {field("Material", info['material'])}
      {field("Comercial", info['comercial'])}
      {field("Fecha pedido", info['fecha_pedido'])}
      {field("Fecha prevista", info['fecha_prevista'])}
    </div>
  </div>

  <h2>Estado del pedido</h2>
  <div class="kpis">
    <div class="kpi"><p class="kpi-label">Documentos</p><p class="kpi-value">{k['total']}</p></div>
    <div class="kpi"><p class="kpi-label">Aprobado</p><p class="kpi-value" style="color:{GREEN}">{k['pct']}%</p></div>
    <div class="kpi"><p class="kpi-label">Enviados</p><p class="kpi-value" style="color:{BLUE}">{k['enviados']}</p></div>
    <div class="kpi"><p class="kpi-label">Devoluciones</p><p class="kpi-value" style="color:{AMBER}">{k['devoluciones']}</p></div>
    <div class="kpi"><p class="kpi-label">Sin enviar</p><p class="kpi-value" style="color:{SLATE}">{k['sin_enviar']}</p></div>
    <div class="kpi"><p class="kpi-label">Críticos</p><p class="kpi-value" style="color:{RED if k['criticos'] else GREEN}">{k['criticos']}</p></div>
  </div>
  <div class="prog"><div class="prog-track"><div class="prog-fill" style="width:{k['pct']}%"></div></div></div>

  <div class="grid2" style="margin-top:18px">
    <div class="card">
      <h3>Distribución por estado</h3>
      <div class="legend">
        <span><i style="background:{GREEN}"></i>Aprobado</span>
        <span><i style="background:{BLUE}"></i>Enviado</span>
        <span><i style="background:{AMBER}"></i>Devuelto</span>
        <span><i style="background:{SLATE}"></i>Sin enviar</span>
      </div>
      <div class="chart-box"><canvas id="estadoChart"></canvas></div>
    </div>
    <div class="card">
      <h3>Por tipo de documento</h3>
      <div class="chart-box"><canvas id="tipoChart"></canvas></div>
    </div>
  </div>
  {pred_html}

  <div class="pagebreak"></div>
  <h2>Estado de toda la documentación · {k['total']} documentos</h2>
  <div class="tbl-panel card" style="padding:14px 16px">
    <div class="tbl-tools">
      <input class="tbl-search" type="text" placeholder="Buscar Nº doc, título o tipo…">
      <select class="tbl-status">
        <option value="all">Todos los estados</option>
        <option value="aprobado">Aprobado</option>
        <option value="enviado">Enviado</option>
        <option value="devuelto">Devuelto</option>
        <option value="sin">Sin enviar</option>
      </select>
      <span class="tbl-count"></span>
      <span class="tbl-hint">· clic en una fila para ver el detalle</span>
    </div>
    <table>
      <thead><tr><th>Nº Doc. EIPSA</th><th>Título</th><th>Tipo</th><th>Rev.</th>
        <th>Estado</th><th>Fecha env.</th><th>1ª Env. (Rev.0)</th><th>1ª Aprob.</th><th>Días</th></tr></thead>
      <tbody>{table_html}</tbody>
    </table>
  </div>

  <footer>
    <span>DocFlow · Informe de pedido {_esc(meta['pedido'])}</span>
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
  new Chart(document.getElementById("tipoChart"), {{
    type: "bar",
    data: {{ labels: D.tipo.labels, datasets: [{{ data: D.tipo.values,
             backgroundColor: D.accent, borderRadius: 4 }}] }},
    options: {{ indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: noLegend,
               scales: {{ x: {{ beginAtZero: true, ticks: {{ precision: 0 }} }} }} }}
  }});
}})();
</script>
<script>{_TABLE_JS}</script>
</body>
</html>"""


def _pedido_email_body(data: dict) -> str:
    meta, info = data["meta"], data["info"]
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;color:#0F172A;font-size:14px;line-height:1.6">'
        f'<p>Hola,</p>'
        f'<p>Adjunto el <b>{_esc(meta["title"])}</b>'
        + (f' (cliente <b>{_esc(info["cliente"])}</b>)' if info["cliente"] else '')
        + '. Ábrelo en el navegador para ver los KPIs, la predicción y la tabla completa '
        'de toda la documentación del pedido.</p>'
        '<p style="color:#475569">Generado automáticamente por DocFlow.</p>'
        '<p style="color:#94A3B8;font-size:12px">© jparedesDS</p>'
        '</div>'
    )


def generate_pedido(pedido: str, with_ai: bool = True):
    """Genera el informe HTML de un pedido y lo guarda. Devuelve (Path, data)."""
    data = build_pedido_report_data(pedido, with_ai=with_ai)
    html_str = render_pedido_html(data)
    path = reports_dir() / f"Informe_Pedido_{data['meta']['key']}.html"
    path.write_text(html_str, encoding="utf-8")
    logger.info("Informe de pedido generado: %s", path)
    return path, data


def send_pedido_email(pedido: str, to: list[str] | None = None,
                      cc: list[str] | None = None) -> dict:
    if not to:
        return {"status": "skipped", "reason": "Sin destinatarios"}
    from core.services.smtp import send_html_email

    data = build_pedido_report_data(pedido)
    html_str = render_pedido_html(data)
    fname = f"Informe_Pedido_{data['meta']['key']}.html"
    subject = f"{data['meta']['title']}" + (f" — {data['info']['cliente']}" if data['info']['cliente'] else "")
    result = send_html_email(
        to=to, cc=cc or [], subject=subject, html_body=_pedido_email_body(data),
        attachment_eml=html_str.encode("utf-8"), attachment_name=fname)
    try:
        (reports_dir() / fname).write_text(html_str, encoding="utf-8")
    except Exception:
        logger.debug("No se pudo guardar copia local del informe de pedido", exc_info=True)
    result["status"] = "sent"
    result["recipients"] = to
    return result


def post_pedido_to_teams(pedido: str) -> dict:
    data = build_pedido_report_data(pedido, with_ai=False)
    k = data["kpis"]
    facts = [
        ("Cliente", data["info"]["cliente"] or "—"),
        ("Documentos", k["total"]),
        ("Aprobado", f"{k['pct']}%"),
        ("Enviados", k["enviados"]),
        ("Devoluciones", k["devoluciones"]),
        ("Sin enviar", k["sin_enviar"]),
        ("Críticos", k["criticos"]),
    ]
    from core.services import teams
    return teams.post_card(data["meta"]["title"], data["info"]["cliente"],
                           data["narrative"], facts)
