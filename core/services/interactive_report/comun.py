"""Piezas compartidas por los tres informes interactivos.

Colores, escape de HTML, Chart.js embebido, el estilo y el guion de
las tablas, las tarjetas de KPI y la llamada a Claude.
"""

from __future__ import annotations

import html
import logging

from core.config import ANTHROPIC_API_KEY
from core.paths import resource_path, state_dir
from core.services import monitoring as monitoring_service

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


_MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
          "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


_MESES_ABBR = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago",
               "sep", "oct", "nov", "dic"]


# Paleta del informe (fija, indigo — coherente con los emails, independiente del
# tema de la app para que el informe se vea igual archivado o reenviado).
ACCENT = "#4F46E5"


GREEN = "#16A34A"


AMBER = "#D97706"


RED = "#DC2626"


BLUE = "#2563EB"


SLATE = "#64748B"


# Placeholders de responsable que no representan personas reales.
_OCULTAR_RESP = {"", "SI", "ES", "Sin Asignar", "Sin asignar"}


def _num(v):
    return monitoring_service._try_int(v)


def _es_critico(d) -> bool:
    return str(d.get("Crítico", "") or "").lower().strip() in ("sí", "si")


def _ask_haiku(prompt: str) -> str | None:
    """Llama a Claude Haiku; devuelve el texto o None (sin key / fallo de red)."""
    if not (ANTHROPIC_API_KEY or "").strip():
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY.strip())
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.warning("Haiku falló, usando fallback: %s", exc)
        return None


def _esc(v) -> str:
    return html.escape(str(v), quote=True)


def _chartjs_source() -> str:
    """Devuelve el código de Chart.js para inyectarlo inline (offline). Si no se
    encuentra el vendor, devuelve un <script src> a jsdelivr como último recurso."""
    path = resource_path("assets/vendor/chart.umd.min.js")
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        logger.warning("Chart.js vendor no encontrado en %s; usando CDN", path)
        return ""


# Búsqueda + filtro por estado + orden por columna + filas expandibles.
# CSS y JS vanilla (sin dependencias), inyectados en los informes con tablas.
_TABLE_CSS = """
  .tbl-tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px;}
  .tbl-search,.tbl-status{font:inherit;font-size:13px;padding:7px 11px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);}
  .tbl-search{flex:1;min-width:170px;}
  .tbl-status{cursor:pointer;}
  .tbl-count{font-size:12px;color:var(--muted);font-weight:600;}
  .tbl-hint{font-size:12px;color:var(--muted);}
  th.sortable{cursor:pointer;user-select:none;white-space:nowrap;}
  th.sortable:hover{color:var(--accent);}
  th[data-dir=asc]::after{content:' \\25B2';font-size:9px;}
  th[data-dir=desc]::after{content:' \\25BC';font-size:9px;}
  tr.expandable{cursor:pointer;}
  tr.expandable:hover{background:#F8FAFC;}
  tr.expandable.open{background:#F5F3FF;}
  tr.expandable td:first-child::before{content:'\\25B8';color:var(--muted);margin-right:7px;font-size:10px;display:inline-block;}
  tr.expandable.open td:first-child::before{content:'\\25BE';}
  tr.detail td{background:#F8FAFC;padding:14px 16px;border-top:0;}
  .detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px 20px;}
  .detail-grid .lab{margin:0;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);}
  .detail-grid .val{margin:2px 0 0;font-size:13px;word-break:break-word;}
  .detail-hist{margin:3px 0 0;font-family:'Consolas',monospace;font-size:12px;color:var(--sub);white-space:pre-wrap;word-break:break-word;}
  .hd-actions{display:flex;align-items:center;gap:10px;}
  .dl-btn{font:inherit;font-size:13px;font-weight:600;cursor:pointer;color:#fff;background:var(--accent);border:0;border-radius:8px;padding:8px 14px;display:inline-flex;align-items:center;gap:6px;}
  .dl-btn:hover{filter:brightness(1.08);}
  @media print{.tbl-tools,.no-print{display:none!important;}tr.detail{display:none!important;}}
"""


_TABLE_JS = """
(function(){
  function norm(s){return (s||'').toString().toLowerCase();}
  function bodyRows(t){return Array.prototype.slice.call(t.tBodies[0].rows);}
  function dataRows(t){return bodyRows(t).filter(function(r){return !r.classList.contains('detail');});}
  function applyFilter(panel){
    var t=panel.querySelector('table'); if(!t||!t.tBodies.length) return;
    var s=panel.querySelector('.tbl-search'); var q=norm(s?s.value:'');
    var sel=panel.querySelector('.tbl-status'); var st=sel?sel.value:'';
    var shown=0,total=0;
    bodyRows(t).forEach(function(tr){
      if(tr.classList.contains('detail')) return;
      total++;
      var okQ=!q||norm(tr.textContent).indexOf(q)>=0;
      var okS=!st||st==='all'||tr.getAttribute('data-estado')===st;
      var show=okQ&&okS; tr.hidden=!show;
      var d=tr.nextElementSibling;
      if(d&&d.classList.contains('detail')&&!show){d.hidden=true;tr.classList.remove('open');}
      if(show) shown++;
    });
    var c=panel.querySelector('.tbl-count'); if(c) c.textContent=shown+' / '+total;
  }
  function wireSort(t){
    t.querySelectorAll('th[data-sort]').forEach(function(th){
      th.classList.add('sortable');
      th.addEventListener('click',function(){
        var idx=Array.prototype.indexOf.call(th.parentNode.children,th);
        var num=th.getAttribute('data-sort')==='num';
        var dir=th.getAttribute('data-dir')==='asc'?-1:1;
        th.parentNode.querySelectorAll('th').forEach(function(o){o.removeAttribute('data-dir');});
        th.setAttribute('data-dir',dir===1?'asc':'desc');
        var b=t.tBodies[0]; var rows=dataRows(t);
        rows.sort(function(a,c){
          var x=a.cells[idx].textContent.trim(),y=c.cells[idx].textContent.trim();
          if(num){x=parseFloat(x.replace(/[^0-9.-]/g,''))||0;y=parseFloat(y.replace(/[^0-9.-]/g,''))||0;return (x-y)*dir;}
          return x.localeCompare(y,'es')*dir;
        });
        rows.forEach(function(r){b.appendChild(r);});
      });
    });
  }
  function wireExpand(t){
    bodyRows(t).forEach(function(tr){
      if(!tr.classList.contains('expandable')) return;
      tr.addEventListener('click',function(){
        var d=tr.nextElementSibling;
        if(d&&d.classList.contains('detail')){d.hidden=!d.hidden;tr.classList.toggle('open');}
      });
    });
  }
  document.querySelectorAll('.tbl-panel').forEach(function(panel){
    var t=panel.querySelector('table'); if(!t) return;
    var s=panel.querySelector('.tbl-search'); if(s) s.addEventListener('input',function(){applyFilter(panel);});
    var sel=panel.querySelector('.tbl-status'); if(sel) sel.addEventListener('change',function(){applyFilter(panel);});
    if(t.querySelector('th[data-sort]')) wireSort(t);
    wireExpand(t);
    applyFilter(panel);
  });
})();
"""


def _kpi_card_html(k: dict) -> str:
    d = k["delta"]
    diff = d["diff"]
    if diff == 0 or d["pct"] is None and diff == 0:
        delta_html = '<span class="delta flat">— sin cambios</span>'
    else:
        up = diff > 0
        good = up if k["good_up"] else not up
        cls = "up" if good else "down"
        arrow = "▲" if up else "▼"
        pct = f" ({'+' if up else ''}{d['pct']}%)" if d["pct"] is not None else ""
        delta_html = f'<span class="delta {cls}">{arrow} {"+" if up else ""}{diff}{pct}</span>'
    return (
        f'<div class="kpi"><p class="kpi-label">{_esc(k["label"])}</p>'
        f'<p class="kpi-value">{_esc(k["value"])}</p>{delta_html}</div>'
    )


def reports_dir():
    p = state_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pct_color(p) -> str:
    try:
        p = float(p)
    except (TypeError, ValueError):
        return SLATE
    return GREEN if p >= 75 else (AMBER if p >= 50 else RED)


def _score_color(s) -> str:
    try:
        s = float(s)
    except (TypeError, ValueError):
        return SLATE
    return GREEN if s >= 80 else (AMBER if s >= 50 else RED)
