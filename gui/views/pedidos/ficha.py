"""La ficha del pedido: cabecera, lo que requiere acción y el avance.

Todo lo que se pinta por encima de la tabla de equipos. Son métodos de
PedidosView, agrupados aquí para poder tocarlos sin cruzarse con la tabla.
"""

import logging
import threading

import customtkinter as ctk

from core.services import erp as erp_service
from gui import theme
from gui.views.documentos import _fmt, _status_color, _trunc
from gui.widgets import ui

from gui.views.pedidos.comun import (
    _card,
    _date,
    _fields_grid,
    _num,
    _phase_color,
    _rule,
    _section_header,
    _to_int,
)

logger = logging.getLogger(__name__)


class FichaMixin:
    """La ficha del pedido: cabecera, lo que requiere acción y el avance."""

    def _status_verdict(self, kpis: dict, seg: dict) -> dict:
        total = kpis.get("total", 0)
        if total == 0:
            return {"label": "SIN DOCUMENTOS", "color": theme.TEXT_MUTED,
                    "reason": "Este pedido aún no tiene documentos registrados."}
        aprob = kpis.get("aprobados", 0)
        if aprob >= total:
            return {"label": "COMPLETADO", "color": theme.GREEN,
                    "reason": "Todos los documentos están aprobados."}
        c15 = kpis.get("criticos_15d", 0)
        if c15 > 0:
            return {"label": "EN RIESGO", "color": theme.RED,
                    "reason": f"{c15} documento(s) crítico(s) llevan +15 días sin respuesta del cliente."}
        if seg.get("en_plazo") is False:
            return {"label": "EN RIESGO", "color": theme.RED,
                    "reason": "Ritmo por debajo de lo previsto: el cierre estimado supera la fecha prevista."}
        dev = kpis.get("devoluciones", 0)
        if dev > 0:
            return {"label": "REQUIERE ACCIÓN", "color": theme.AMBER,
                    "reason": f"{dev} documento(s) devueltos con comentarios pendientes de resolver."}
        if aprob == 0 and kpis.get("enviados", 0) == 0:
            return {"label": "SIN INICIAR", "color": theme.TEXT_MUTED,
                    "reason": "Documentación creada pero aún sin enviar al cliente."}
        return {"label": "EN CURSO", "color": theme.ACCENT,
                "reason": f"{kpis.get('pct_completado', 0)}% aprobado · "
                          f"{kpis.get('enviados', 0)} pendiente(s) de revisión del cliente."}

    @staticmethod
    def _erp_fields(pedido: str) -> list:
        """Lo que otros departamentos tienen abierto en este pedido, como
        (etiqueta, valor, color). Lo que avisa de algo va coloreado."""
        out = []
        try:
            from core.services import purchases
            compras = purchases.for_pedido(pedido)
            if compras:
                tarde = sum(1 for c in compras if c["retraso"] > 0)
                txt = f"{len(compras)} línea(s)" + (f" · {tarde} con retraso" if tarde else "")
                out.append(("Compras pendientes", txt, theme.AMBER if tarde else theme.TEXT_MAIN))
        except Exception:  # noqa: BLE001 — sin ERP la ficha se pinta igual
            pass
        try:
            from core.services import quality
            ncs = quality.nc_for_pedido(pedido)
            if ncs:
                abiertas = sum(1 for n in ncs if not n["cerrada"])
                txt = f"{len(ncs)}" + (f" · {abiertas} sin cerrar" if abiertas else " · todas cerradas")
                out.append(("No conformidades", txt,
                            theme.AMBER if abiertas else theme.GREEN))
        except Exception:  # noqa: BLE001
            pass
        try:
            from core.services import production
            h = production.hours_for_pedido(pedido)
            if h and h["horas"] >= 1:      # menos de una hora no dice nada
                out.append(("Horas de taller", f"{h['horas']:,.0f} h".replace(",", "."),
                            theme.TEXT_MAIN))
        except Exception:  # noqa: BLE001
            pass
        try:
            from core.services import administration as adm
            facturas = adm.invoices_for_pedido(pedido)
            if facturas:
                pend = [f for f in facturas if not f["pagada"]]
                txt = f"{len(facturas)} · {adm.euros(sum(f['importe'] for f in facturas))}"
                if pend:
                    txt += f" · {len(pend)} sin cobrar"
                out.append(("Facturado", txt, theme.AMBER if pend else theme.GREEN))
            avales = adm.bonds_for_pedido(pedido)
            if avales:
                vencidos = sum(1 for a in avales if a["vencido"])
                prox = min((a["vence"] for a in avales if a["vence"]), default=None)
                txt = f"{len(avales)}"
                if prox:
                    txt += f" · vence {prox:%d-%m-%Y}"
                if vencidos:
                    txt += f" · {vencidos} pasado(s) de fecha"
                out.append(("Avales", txt, theme.RED if vencidos else theme.TEXT_MAIN))
        except Exception:  # noqa: BLE001
            pass
        return out

    @staticmethod
    def _almacen_field(pedido: str):
        """('Días en almacén', valor, color) del ERP: lo que esperó (o lleva
        esperando) el material entre el aviso de entrega y el envío. None si no
        aplica. En rojo si sigue parado y ya lleva más de un mes."""
        try:
            from core.services import warehouse
            r = warehouse.for_pedido(pedido)
        except Exception:  # noqa: BLE001 — sin ERP la ficha se pinta igual
            return None
        if not r:
            return None
        if r["en_almacen"]:
            color = theme.RED if r["dias"] >= 30 else theme.AMBER
            return ("Días en almacén", f"{r['dias']} d · esperando salida", color)
        salida = r["transporte"] or "enviado"
        return ("Días en almacén", f"{r['dias']} d · {salida}", theme.TEXT_MAIN)

    def _build_ficha(self, parent, pedido: str, dash: dict) -> None:
        consulta = dash.get("consulta") or {}
        docs = dash.get("documents") or []
        first = docs[0] if docs else {}
        hdr = (getattr(self, "_bundle", {}) or {}).get("header") or {}

        datos = []
        for lab, val in (
            ("PO", str(first.get("Nº PO", "") or "").strip()),
            ("Material", str(first.get("Material", "")
                             or consulta.get("Tipo Equipo", "") or "").strip()),
            ("Nº equipos", _num(consulta.get("Nº Equipos"))),
            ("Comercial", str(consulta.get("Responsable", "") or "").strip()),
            ("Nº oferta", str(consulta.get("Nº Oferta", "") or "").strip()),
            ("Fecha de pedido", _date(consulta.get("Fecha Pedido"))),
            ("Fecha prevista", _date(consulta.get("Fecha Prevista"))),
        ):
            if val:
                datos.append((lab, val, theme.TEXT_MAIN))

        entrega = []
        for lab in ("Prev. taller", "Recep. taller", "Aviso entrega",
                    "Material disponible", "Cerrado"):
            val = str(hdr.get(lab, "") or "").strip()
            if val:
                entrega.append((lab, val, theme.TEXT_MAIN))
        alm = self._almacen_field(pedido)
        if alm:
            entrega.append(alm)

        otros = list(self._erp_fields(pedido))
        # El «Aval» de la cabecera solo si administración no ha dado los suyos:
        # ese campo dice «No Aplica» en pedidos que sí tienen aval, así que el
        # recuento real manda sobre él.
        aval = str(hdr.get("Aval", "") or "").strip()
        if aval and not any(lab == "Avales" for lab, _, _ in otros):
            otros.append(("Aval", aval, theme.TEXT_MAIN))

        for titulo, campos in (("Ficha del pedido", datos),
                               ("Fabricación y entrega", entrega),
                               ("Otros departamentos", otros)):
            if not campos:
                continue
            _section_header(parent, titulo).pack(fill="x", pady=(0, theme.SPACE_2))
            card = _card(parent)
            card.pack(fill="x", pady=(0, theme.SPACE_3))
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=theme.SPACE_4, pady=theme.SPACE_3)
            _fields_grid(inner, campos, ncols=2 if len(campos) > 3 else 1)

    def _build_header_card(self, parent, pedido, dash, consulta, docs, kpis, verdict) -> None:
        """Cabecera: identidad, veredicto, las cifras que importan y el reparto
        de la documentación en una sola barra. Los datos del pedido van aparte,
        en la columna de la ficha, para no empujar todo esto hacia abajo."""
        cli = dash.get("cliente", "") or consulta.get("Cliente", "")
        directo = str(consulta.get("Cliente", "") or "").strip()
        proyecto = str(consulta.get("Proyecto", "") or "").strip()

        card = _card(parent)
        card.pack(fill="x", pady=(0, theme.SPACE_3))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=theme.SPACE_5, pady=theme.SPACE_4)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        # Identidad
        left = ctk.CTkFrame(top, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        title = ctk.CTkFrame(left, fg_color="transparent")
        title.pack(anchor="w")
        ctk.CTkLabel(title, text=pedido, font=theme.font(32, "bold"),
                     text_color=theme.TEXT_MAIN).pack(side="left")
        if cli:
            ctk.CTkLabel(title, text=cli, font=theme.font(17, "bold"),
                         text_color=theme.ACCENT).pack(side="left", padx=(theme.SPACE_3, 0),
                                                       pady=(theme.SPACE_2, 0))
        if directo and directo.upper() != str(cli).upper():
            ctk.CTkLabel(title, text=f"vía {directo}", font=theme.FONT_SMALL,
                         text_color=theme.TEXT_MUTED).pack(side="left", padx=(theme.SPACE_2, 0),
                                                           pady=(theme.SPACE_2, 0))
        if proyecto:
            ctk.CTkLabel(left, text=proyecto, font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
                         anchor="w", justify="left", wraplength=680).pack(anchor="w", pady=(4, 0))

        # Veredicto
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right", padx=(theme.SPACE_4, 0))
        col = verdict["color"]
        ctk.CTkLabel(right, text=f"  {verdict['label']}  ", font=theme.font(14, "bold"),
                     text_color=theme.TEXT_ON_ACCENT if col != theme.TEXT_MUTED else theme.TEXT_MAIN,
                     fg_color=col, corner_radius=theme.RADIUS_MD, height=34).pack(anchor="e")
        ctk.CTkLabel(right, text=verdict["reason"], font=theme.FONT_TINY,
                     text_color=theme.TEXT_SUB, anchor="e", justify="right",
                     wraplength=320).pack(anchor="e", pady=(theme.SPACE_1, 0))

        # Las cifras, en grande
        _rule(inner, pady=theme.SPACE_4)
        total = kpis.get("total", 0)
        pct = kpis.get("pct_completado", 0)
        crit = kpis.get("criticos_15d", 0) or kpis.get("criticos", 0)
        stats = [
            (f"{_num(pct)}%", "aprobado", theme.GREEN if pct >= 100 else theme.ACCENT, ""),
            (str(total), "documentos", theme.TEXT_MAIN, ""),
            (str(kpis.get("aprobados", 0)), "aprobados", theme.GREEN, ""),
            (str(kpis.get("enviados", 0)), "en revisión", theme.BLUE, "pendientes del cliente"),
            (str(kpis.get("devoluciones", 0)), "devoluciones",
             theme.AMBER if kpis.get("devoluciones") else theme.TEXT_MUTED, "con comentarios"),
            (str(crit), "críticos", theme.RED if crit else theme.TEXT_MUTED,
             f"{kpis.get('criticos_15d', 0)} con +15 días" if kpis.get("criticos_15d") else ""),
            (f"{_to_int(round(float(dash.get('avg_dias_respuesta') or 0)))} d",
             "respuesta media", theme.TEXT_SUB, "del cliente"),
        ]
        ui.stat_strip(inner, stats)

        # Reparto de la documentación, en una sola barra
        segs = [
            ("Aprobados", kpis.get("aprobados", 0), theme.GREEN),
            ("En revisión", kpis.get("enviados", 0), theme.BLUE),
            ("Devoluciones", kpis.get("devoluciones", 0), theme.AMBER),
            ("Sin enviar", kpis.get("sin_enviar", 0), theme.BORDER_STRONG),
        ]
        if total:
            track = ctk.CTkFrame(inner, fg_color=theme.BG_INPUT, height=18,
                                 corner_radius=theme.RADIUS_SM)
            track.pack(fill="x", pady=(theme.SPACE_4, theme.SPACE_2))
            track.pack_propagate(False)
            x = 0.0
            for _, count, color in segs:
                if count <= 0:
                    continue
                w = count / total
                ctk.CTkFrame(track, fg_color=color, corner_radius=0).place(
                    relx=min(x, 0.999), rely=0, relheight=1, relwidth=min(w, 1 - x))
                x += w
            leg = ctk.CTkFrame(inner, fg_color="transparent")
            leg.pack(fill="x")
            for label, count, color in segs:
                if count <= 0:
                    continue
                chip = ctk.CTkFrame(leg, fg_color="transparent")
                chip.pack(side="left", padx=(0, theme.SPACE_4))
                ctk.CTkFrame(chip, fg_color=color, width=10, height=10,
                             corner_radius=3).pack(side="left", pady=(1, 0))
                ctk.CTkLabel(chip, text=f" {label} ", font=theme.FONT_SMALL,
                             text_color=theme.TEXT_SUB).pack(side="left")
                ctk.CTkLabel(chip, text=str(count), font=theme.FONT_BODY_BOLD,
                             text_color=theme.TEXT_MAIN).pack(side="left")

    def _generate_pedido_report(self, pedido: str, btn=None) -> None:
        if btn is not None:
            btn.configure(state="disabled", text="Generando…")

        def worker():
            try:
                from core.services import interactive_report as ir
                path, _ = ir.generate_pedido(pedido)
                ui.en_ui(self, lambda: self._pedido_report_done(path, btn))
            except Exception as exc:
                logger.exception("Error generando informe del pedido")
                msg = str(exc)
                ui.en_ui(self, lambda: self._pedido_report_fail(msg, btn))

        threading.Thread(target=worker, daemon=True).start()

    def _restore_report_btn(self, btn) -> None:
        if btn is not None and btn.winfo_exists():
            btn.configure(state="normal", text="Informe del pedido  →")

    def _pedido_report_done(self, path, btn) -> None:
        import webbrowser
        try:
            webbrowser.open(path.as_uri())
        except Exception:
            logger.debug("No se pudo abrir el navegador", exc_info=True)
        ui.toast(self, "Informe listo", path.name, kind="success")
        self._restore_report_btn(btn)

    def _pedido_report_fail(self, msg, btn) -> None:
        ui.toast(self, "No se pudo generar el informe", msg, kind="info")
        self._restore_report_btn(btn)

    def _build_atencion(self, parent, docs: list[dict]) -> None:
        _section_header(parent, "Requiere atención").pack(fill="x", pady=(0, theme.SPACE_2))

        items = []
        for d in docs:
            est = str(d.get("Estado", "") or "").lower().strip()
            if "aprobado" in est:
                continue
            crit = str(d.get("Crítico", "") or "").lower().strip() in ("sí", "si")
            dd = _to_int(d.get("Días Devolución"))
            is_dev = any(s in est for s in ("com.", "comentado", "menores", "mayores", "rechaz"))
            atrasado = (est == "enviado" and dd >= 15)
            if not (crit or is_dev or atrasado):
                continue
            score = (2 if (crit and dd >= 15) else 0) + (1 if crit else 0) + (1 if is_dev else 0)
            items.append((score, dd, crit, d))

        card = _card(parent)
        card.pack(fill="x", pady=(0, theme.SPACE_3))

        if not items:
            ctk.CTkLabel(card, text="✓  Sin acciones pendientes — nada crítico, devuelto ni atrasado.",
                         font=theme.FONT_BODY, text_color=theme.GREEN, anchor="w").pack(
                fill="x", padx=theme.SPACE_4, pady=theme.SPACE_4)
        else:
            items.sort(key=lambda x: (x[0], x[1]), reverse=True)
            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="x", padx=theme.SPACE_3, pady=(theme.SPACE_3, 0))
            for i, (score, dd, crit, d) in enumerate(items[:8]):
                estado = str(d.get("Estado", "") or "Sin enviar")
                ecol = _status_color(estado)
                # Banda alterna: separa las filas sin gastar aire entre ellas
                r = ctk.CTkFrame(body, fg_color=theme.ROW_STRIPE if i % 2 else "transparent",
                                 corner_radius=theme.RADIUS_SM, height=34)
                r.pack(fill="x")
                r.pack_propagate(False)
                ctk.CTkLabel(r, text="⚠" if crit else "•", font=theme.FONT_BODY_BOLD,
                             text_color=theme.RED if crit else theme.TEXT_MUTED,
                             width=22).pack(side="left")
                ctk.CTkLabel(r, text=_fmt(d.get("Nº Doc. EIPSA")), font=theme.FONT_BODY_BOLD,
                             text_color=theme.ACCENT, width=170, anchor="w").pack(side="left")
                dcol = theme.RED if dd >= 15 else theme.TEXT_MUTED
                ctk.CTkLabel(r, text=(f"{dd} d" if dd > 0 else "—"), font=theme.FONT_BODY_BOLD,
                             text_color=dcol, width=52).pack(side="right", padx=(0, theme.SPACE_2))
                ctk.CTkLabel(r, text=f" {estado} ", font=theme.FONT_SMALL, text_color=ecol,
                             fg_color=ui.blend(ecol, theme.BG_CARD, 0.20), corner_radius=8,
                             height=22).pack(side="right", padx=(0, theme.SPACE_2))
                ctk.CTkLabel(r, text=_trunc(d.get("Título"), 52), font=theme.FONT_BODY,
                             text_color=theme.TEXT_MAIN, anchor="w").pack(
                    side="left", fill="x", expand=True)

        # Pie: aviso + botón que salta a Documentos filtrando este pedido
        rest = len(items) - 8
        hint = (f"+ {rest} más · " if rest > 0 else "") + "Documentación completa en la sección Documentos."
        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.pack(fill="x", padx=theme.SPACE_4, pady=(theme.SPACE_2, theme.SPACE_3))
        ctk.CTkLabel(foot, text=hint, font=theme.FONT_TINY, text_color=theme.TEXT_MUTED,
                     anchor="w").pack(side="left", fill="x", expand=True)
        if self._on_open_documentos and self._pedido_current:
            ui.button(foot, "Ver en Documentos  →", "primary", size="xs", corner_radius=theme.RADIUS_MD,
                      command=lambda p=self._pedido_current: self._on_open_documentos(p)).pack(side="right")

    def _build_seguimiento_block(self, parent, seg: dict) -> None:
        if not seg or not seg.get("total"):
            return
        _section_header(parent, "Plazo · Curva-S").pack(fill="x", pady=(0, theme.SPACE_2))
        card = _card(parent)
        card.pack(fill="x", pady=(0, theme.SPACE_3))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=theme.SPACE_4, pady=theme.SPACE_3)

        pct = seg.get("pct", 0)
        pct_esp = seg.get("pct_esperado")

        ctk.CTkLabel(inner, text="Avance real vs. esperado", font=theme.FONT_BODY_BOLD,
                     text_color=theme.TEXT_MAIN).pack(anchor="w")
        track = ctk.CTkFrame(inner, fg_color=theme.BG_INPUT, height=14, corner_radius=7)
        track.pack(fill="x", pady=(theme.SPACE_2, theme.SPACE_1))
        if pct_esp is not None:
            exp = ctk.CTkFrame(track, fg_color=theme.TEXT_MUTED, corner_radius=6)
            exp.place(relx=0, rely=0, relheight=1, relwidth=max(0.01, min(1.0, pct_esp / 100)))
        real = ctk.CTkFrame(track, fg_color=theme.ACCENT, corner_radius=6)
        real.place(relx=0, rely=0, relheight=1, relwidth=max(0.01, min(1.0, pct / 100)))

        leg = ctk.CTkFrame(inner, fg_color="transparent")
        leg.pack(fill="x", pady=(0, theme.SPACE_2))
        for txt, col in (("Real", theme.ACCENT), ("Esperado", theme.TEXT_MUTED)):
            chip = ctk.CTkFrame(leg, fg_color="transparent")
            chip.pack(side="left", padx=(0, theme.SPACE_3))
            ctk.CTkFrame(chip, fg_color=col, width=10, height=10, corner_radius=2).pack(side="left")
            ctk.CTkLabel(chip, text=txt, font=theme.FONT_TINY, text_color=theme.TEXT_MUTED).pack(
                side="left", padx=(4, 0))

        desv = (pct - pct_esp) if pct_esp is not None else None
        en_plazo = seg.get("en_plazo")
        chips = [
            ("% Real", f"{pct}%", theme.ACCENT),
            ("% Esperado", f"{pct_esp}%" if pct_esp is not None else "—", theme.TEXT_SUB),
            ("Desviación", (f"+{desv}pp" if (desv is not None and desv >= 0)
                            else (f"{desv}pp" if desv is not None else "—")),
             (theme.GREEN if (desv is not None and desv >= 0) else theme.RED)
             if desv is not None else theme.TEXT_MUTED),
            ("Fecha prevista", seg.get("fecha_prevista") or "—", theme.TEXT_SUB),
            ("Cierre estimado", seg.get("prediccion_fecha") or "—",
             theme.GREEN if en_plazo is True else (theme.RED if en_plazo is False else theme.TEXT_SUB)),
        ]
        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x")
        ncols = 2                      # la columna de la ficha es estrecha
        for c in range(ncols):
            grid.grid_columnconfigure(c, weight=1, uniform="seg")
        for i, (label, val, col) in enumerate(chips):
            cell = ctk.CTkFrame(grid, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_MD,
                                border_width=1, border_color=theme.BORDER)
            cell.grid(row=i // ncols, column=i % ncols, sticky="ew",
                      padx=(0 if i % ncols == 0 else theme.SPACE_2, 0), pady=(0, theme.SPACE_2))
            ctk.CTkLabel(cell, text=str(val), font=theme.font(17, "bold"), text_color=col,
                         anchor="w").pack(anchor="w", padx=theme.SPACE_3, pady=(theme.SPACE_2, 0))
            ctk.CTkLabel(cell, text=label.upper(), font=theme.FONT_LABEL,
                         text_color=theme.TEXT_MUTED, anchor="w").pack(
                anchor="w", padx=theme.SPACE_3, pady=(0, theme.SPACE_2))

    def _build_fase_erp(self, parent, consulta: dict) -> None:
        _section_header(parent, "Fabricación").pack(fill="x", pady=(0, theme.SPACE_2))
        if not consulta:
            ctk.CTkLabel(parent, text="Este pedido no figura en consulta_erp.xlsx.",
                         font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                         anchor="w").pack(fill="x", pady=(0, theme.SPACE_3))
            return
        card = _card(parent)
        card.pack(fill="x", pady=(0, theme.SPACE_3))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_3)

        phases = erp_service.consulta_phases(consulta)
        prow = ctk.CTkFrame(inner, fg_color="transparent")
        prow.pack(fill="x")
        prow.grid_rowconfigure(0, weight=1)
        for c in range(3):
            prow.grid_columnconfigure(c, weight=1, uniform="phase")
        for i, ph in enumerate(phases):
            self._phase_card(prow, ph, 0, i)

        notas = str(consulta.get("Notas Pedido", "") or "")
        if notas:
            nbox = ctk.CTkFrame(inner, fg_color=theme.BG_CARD, corner_radius=8)
            nbox.pack(fill="x", pady=(theme.SPACE_3, 0))
            ctk.CTkLabel(nbox, text="NOTAS", font=theme.FONT_LABEL, text_color=theme.TEXT_MUTED,
                         anchor="w").pack(fill="x", padx=theme.SPACE_3, pady=(theme.SPACE_2, 0))
            ctk.CTkLabel(nbox, text=notas, font=theme.FONT_SMALL, text_color=theme.TEXT_SUB,
                         anchor="w", justify="left", wraplength=820).pack(
                fill="x", padx=theme.SPACE_3, pady=(0, theme.SPACE_2))

    def _build_ots_block(self, parent, bundle: dict) -> None:
        if not bundle:
            return
        if not bundle.get("available"):
            ctk.CTkLabel(parent, text="ERP no disponible: sin equipos ni órdenes de fabricación "
                                      "(se leen del PostgreSQL local del ERP).",
                         font=theme.FONT_SMALL, text_color=theme.AMBER, anchor="w").pack(
                fill="x", pady=(0, theme.SPACE_3))
            return
        fab = bundle.get("fab_orders") or []
        tags = [t for t in (bundle.get("tags") or [])
                if t.get("_vigente", True) and not t.get("_eliminado")]
        if not fab and not tags:
            return
        _section_header(parent, "Fabricación por equipo · órdenes de trabajo").pack(
            fill="x", pady=(0, theme.SPACE_2))
        card = _card(parent)
        card.pack(fill="x", pady=(0, theme.SPACE_3))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=theme.SPACE_3, pady=theme.SPACE_3)

        fabricados = sum(1 for t in tags if t.get("Estado Fab.", "").upper() == "FABRICADO")
        con_plano = sum(1 for t in tags if t.get("Plano Dim."))
        abiertas = [o for o in fab if not o["terminada"]]
        cerradas = len(fab) - len(abiertas)
        n = len(tags)
        chips = [
            ("Equipos", str(n), theme.TEXT_MAIN),
            ("Fabricados", f"{fabricados}/{n}" if n else "—",
             theme.GREEN if n and fabricados == n else (theme.AMBER if fabricados else theme.TEXT_SUB)),
            ("Con plano", f"{con_plano}/{n}" if n else "—", theme.TEXT_SUB),
            ("OTs en curso", str(len(abiertas)), theme.AMBER if abiertas else theme.TEXT_SUB),
            ("OTs hechas", f"{cerradas}/{len(fab)}" if fab else "—",
             theme.GREEN if fab and cerradas == len(fab) else theme.TEXT_SUB),
        ]
        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x")
        for c in range(len(chips)):
            grid.grid_columnconfigure(c, weight=1, uniform="ot")
        for i, (label, val, col) in enumerate(chips):
            cell = ctk.CTkFrame(grid, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_MD,
                                border_width=1, border_color=theme.BORDER)
            cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else theme.SPACE_2, 0))
            ctk.CTkLabel(cell, text=val, font=theme.font(21, "bold"), text_color=col,
                         anchor="w").pack(anchor="w", padx=theme.SPACE_3,
                                          pady=(theme.SPACE_2, 0))
            ctk.CTkLabel(cell, text=label.upper(), font=theme.FONT_LABEL,
                         text_color=theme.TEXT_MUTED, anchor="w").pack(
                anchor="w", padx=theme.SPACE_3, pady=(0, theme.SPACE_2))

        # Qué está en taller ahora mismo (OTs abiertas, las más antiguas primero)
        if abiertas:
            body = ctk.CTkFrame(inner, fg_color="transparent")
            body.pack(fill="x", pady=(theme.SPACE_2, 0))
            for o in abiertas[:8]:
                r = ctk.CTkFrame(body, fg_color="transparent")
                r.pack(fill="x", pady=1)
                ctk.CTkLabel(r, text="•", font=theme.FONT_SMALL, text_color=theme.AMBER,
                             width=14).pack(side="left")
                ctk.CTkLabel(r, text=f"OT {o['ot']}", font=theme.FONT_SMALL_BOLD,
                             text_color=theme.ACCENT, width=90, anchor="w").pack(side="left")
                key = o["tag_key"]
                equipo = key.split("-", 4)[-1] if key.count("-") >= 4 else "Pedido"
                what = " · ".join(x for x in (equipo, o["plano"], o["elemento"]) if x)
                ctk.CTkLabel(r, text=_trunc(what, 70), font=theme.FONT_SMALL,
                             text_color=theme.TEXT_MAIN, anchor="w").pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(r, text=f"desde {o['inicio']}" if o["inicio"] else "sin fecha",
                             font=theme.FONT_TINY, text_color=theme.TEXT_MUTED).pack(side="right")
            if len(abiertas) > 8:
                ctk.CTkLabel(inner, text=f"+ {len(abiertas) - 8} OTs más en curso · "
                                         "detalle por equipo en «Equipos & Tags»",
                             font=theme.FONT_TINY, text_color=theme.TEXT_MUTED, anchor="w").pack(
                    fill="x", pady=(theme.SPACE_1, 0))

    def _phase_card(self, parent, ph: dict, r, c) -> None:
        color = _phase_color(ph["pct"])
        box = _card(parent)
        box.grid(row=r, column=c, sticky="nsew", padx=(0 if c == 0 else theme.SPACE_2, 0))
        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", padx=theme.SPACE_3, pady=(theme.SPACE_3, 0))
        ctk.CTkLabel(top, text=ph["title"], font=theme.FONT_BODY_BOLD,
                     text_color=theme.TEXT_MAIN).pack(side="left")
        date = _date((ph["date"] or "")[:10])
        if date:
            ctk.CTkLabel(top, text=date, font=theme.FONT_SMALL,
                         text_color=theme.TEXT_MUTED).pack(side="right")
        # El porcentaje, en grande: es el dato de la tarjeta
        ctk.CTkLabel(box, text=f"{ph['pct']}%", font=theme.font(28, "bold"), text_color=color,
                     anchor="w").pack(anchor="w", padx=theme.SPACE_3, pady=(theme.SPACE_1, 0))
        prog = ctk.CTkProgressBar(box, height=8, corner_radius=4,
                                  progress_color=color, fg_color=theme.BG_INPUT)
        prog.pack(fill="x", padx=theme.SPACE_3, pady=(theme.SPACE_1, 0))
        prog.set(min(ph["pct"], 100) / 100)
        obs = str(ph["obs"] or "").strip()
        if len(obs) > 130:
            obs = obs[:130].rstrip() + "…"
        ctk.CTkLabel(box, text=obs or " ", font=theme.FONT_SMALL, text_color=theme.TEXT_MUTED,
                     anchor="nw", justify="left", wraplength=230).pack(
            fill="both", expand=True, padx=theme.SPACE_3, pady=(theme.SPACE_2, theme.SPACE_3))
