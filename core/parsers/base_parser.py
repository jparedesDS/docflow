import re
import pandas as pd
from datetime import datetime

from core import organizacion
from core.utils.excel import read_excel_fast

# ═══════════════════════════════════════════════════════
#  MAPPINGS COMPARTIDOS (migrados de DocuControl)
# ═══════════════════════════════════════════════════════

# Lo que dice cada portal -> nuestro N Pedido. Las tres tablas son la MISMA:
# las claves no se pisan entre portales y asi se rellena una sola en Ajustes.
PRODOC_PO_MAP = organizacion.portales
# Flujo de SENDOC -> N Pedido
SENDOC_PO_MAP = organizacion.portales
# Paquete de ACONEX -> N Pedido
ACONEX_PO_MAP = organizacion.portales

# AYESA: referencia del asunto ("Documentos de <ref>") -> N PO del ERP.
# El portal usa su propia numeracion, que NO esta en data_erp; este mapa enlaza
# esa referencia con el PO real, y de ahi se resuelve el pedido via ERP.
AYESA_REF_PO_MAP = organizacion.refs

# AYESA: código de tipo (en el código de doc de cliente, p.ej. ...-DL-001) →
# valor de "Tipo Doc." del ERP, para emparejar el documento del email con el
# documento del pedido y rellenar su Nº Doc. EIPSA.
AYESA_DOC_TYPE_TO_ERP = {
    "DL": "VDDL", "LIS": "VDDL", "VDDL": "VDDL", "IND": "VDDL",
    "ITP": "PPI", "PLN": "PPI", "PPI": "PPI",
    "PLA": "Programa", "PRG": "Programa",
    "CAL": "Cálculos", "ESP": "Cálculos",
    "PLG": "Planos", "DWG": "Planos",
    "CER": "Certificados", "NACE": "Certificados",
    "DOS": "Dossier", "DD": "Dossier",
    "PRC": "Procedimientos", "NDE": "Procedimientos",
    "PRC0": "Packing",
}

# Project key de Document Space (HEC) -> N Pedido
DOCSPACE_PO_MAP = organizacion.portales
DOCSPACE_SUPP_MAP = {
    "PRY&001": "S00",
}
# Lo que dice el portal -> familia de producto. Una sola tabla para los cuatro:
# las claves no se pisan y asi se rellena una vez en Ajustes > Organizacion.
DOCSPACE_MATERIAL_MAP = organizacion.materiales
PRODOC_MATERIAL_MAP = organizacion.materiales
SENDOC_MATERIAL_MAP = organizacion.materiales
GAIA_MATERIAL_MAP = organizacion.materiales

# Doc type code → Nombre español
DOC_TYPE_MAP = {
    "PLG": "Planos", "DWG": "Planos", "DRAWINGS": "Planos",
    "CAL": "Cálculos", "ESP": "Cálculos y Planos",
    "CER": "Certificado", "NACE": "Certificado",
    "DOS": "Dossier", "DD": "Dossier",
    "LIS": "Listado", "LIST": "Listado", "VDB": "Listado",
    "VDDL": "Listado", "DL": "Listado",
    "ITP": "PPI", "PLN": "PPI",
    "PLA": "Programa", "PRG": "Programa",
    "PRC": "Procedimientos", "NDE": "Procedimientos", "PH": "Procedimientos",
    "MAN": "Manual", "PLD": "Nameplate",
    "CAT": "Catalogo", "SPL": "Repuestos",
    "WD": "Soldadura", "IND": "Indice",
}

# Tipo doc → Crítico
CRITICO_MAP = {
    "Planos": "Sí", "Cálculos": "Sí", "Cálculos y Planos": "Sí",
    "Manual": "Sí", "PPI": "Sí", "Catalogo": "Sí", "Listado": "Sí",
    "Certificado": "No", "Dossier": "No", "Procedimientos": "No",
    "Nameplate": "No", "Repuestos": "No", "Indice": "No",
    "Soldadura": "No",
}

# Status mappings por plataforma
ACONEX_STATUS_MAP = {
    "A - REJECTED": "Rechazado",
    "1 - WITH COMMENTS": "Com. Mayores",
    "1R - WITH COMMENTS - REJECTED": "Rechazado",
    "2 - WITHOUT COMMENTS": "Aprobado",
    "2I - FOR INFORMATION ONLY": "Informativo",
    "3 - WITH MINOR COMMENTS": "Com. Menores",
}

SENDOC_STATUS_MAP = {
    "(COD 5)": "Rechazado",
    "2-REVIEW WITH COMMENTS (COD 2)": "Com. Menores",
    "1-NO COMMENTS (COD 1)": "Aprobado",
    "(COD 3)": "Com. Mayores",
    "4-INF ONLY (COD 4)": "Informativo",
}

GAIA_STATUS_MAP = {
    "Code 1": "Com. Mayores",
    "Code 2": "Com. Menores",
    "Code 3": "Aprobado",
    "Code 4": "Informativo",
    "Code 5": "Rechazado",
}

# PO (primeros 5 digitos) -> cliente o proyecto
PO_CLIENT_MAP = organizacion.clientes

# N Pedido -> email del responsable, para los pedidos que el ERP no resuelve.
# La fuente principal es el comercial del ERP (ver `get_responsable_email`);
# esto queda como respaldo para pedidos antiguos y para cuando el comercial es
# alguien de quien no tenemos email.
RESPONSABLE_PEDIDO_MAP = organizacion.pedidos
# Email -> iniciales para la columna Responsable
EMAIL_TO_INITIALS = organizacion.iniciales

# Reasignaciones que el ERP no puede saber (alguien que se fue y cuyos pedidos
# lleva otro). Esta SI manda sobre lo que diga el ERP.
ERP_INITIALS_OVERRIDE = organizacion.reasignados
# Iniciales del comercial EN EL ERP -> email, por si el ERP no contesta.
#
# El email lo da el propio ERP (users_data.registration), asi que un comercial
# nuevo funciona sin tocar nada; esto es solo el respaldo, y las reasignaciones
# que el ERP no puede saber (alguien que se fue y cuyos pedidos lleva otro).
# OJO: NO son las iniciales que usa EIPSA para el equipo.
ERP_INITIALS_EMAIL = organizacion.comerciales

# Codigo de tipo de documento -> email del tecnico que va en CC
DOC_TYPE_EMAIL_MAP = organizacion.tipos_correo

# Destinatarios fijos de las reclamaciones (Ajustes > Organizacion)
DEFAULT_TO = organizacion.correo_para
DEFAULT_CC = organizacion.correo_cc


# ═══════════════════════════════════════════════════════
#  FUNCIONES COMPARTIDAS
# ═══════════════════════════════════════════════════════

def apply_po_mapping(df, po_col, mapping):
    df["Nº Pedido"] = df[po_col].astype(str).str.strip().map(mapping).fillna(df[po_col])
    return df


def apply_material_mapping(df, po_col, mapping):
    df["Material"] = df[po_col].astype(str).str.strip().map(mapping).fillna(df[po_col])
    return df


def apply_doc_type(df, code_col):
    df["Tipo de documento"] = df[code_col].map(DOC_TYPE_MAP)
    return df


def apply_critico(df):
    df["Crítico"] = df["Tipo de documento"].map(CRITICO_MAP).fillna("No")
    return df


def apply_fecha(df, received_time_str):
    df["Fecha"] = pd.to_datetime(received_time_str, dayfirst=True)
    return df


def fill_supp_nulls(df):
    if "Supp." in df.columns:
        df["Supp."] = df["Supp."].fillna("S00")
    else:
        df["Supp."] = "S00"
    return df


def identify_client(po: str) -> str:
    """Identifica cliente a partir de los primeros 5 caracteres del PO."""
    if not po or len(po) < 5:
        return ""
    return PO_CLIENT_MAP.get(po[:5], "")


def _comercial_email(numero_pedido: str) -> str | None:
    """Email del comercial del pedido según el ERP ('' si no lo sabe)."""
    pedido = str(numero_pedido or "").split("-S")[0].strip()
    if not pedido:
        return None
    try:
        from core.services import erp   # import perezoso: evita ciclos parsers↔services
        iniciales = erp.comercial_por_pedido().get(pedido, "")
    except Exception:  # noqa: BLE001 — sin ERP se sigue con el mapa
        return None
    if not iniciales:
        return None
    if iniciales in ERP_INITIALS_OVERRIDE:
        return ERP_INITIALS_OVERRIDE[iniciales]
    try:
        from core.services import erp_db
        email = erp_db.emails_por_iniciales().get(iniciales)
    except Exception:  # noqa: BLE001
        email = None
    return email or ERP_INITIALS_EMAIL.get(iniciales)


def get_responsable_email(numero_pedido: str) -> str | None:
    """Email de quien recibe la devolución de ese pedido.

    Manda el comercial que tiene el ERP, que es dato vivo: coincide con el mapa
    en el 96% de los pedidos de 2021-2024 y cubre 3.143 pedidos, mientras que el
    mapa se quedó en unos pocos cientos. El mapa se usa cuando el ERP no sabe de
    ese pedido o cuando el comercial es alguien sin email conocido.
    """
    email = _comercial_email(numero_pedido)
    if email:
        return email
    for key, mapped in RESPONSABLE_PEDIDO_MAP.items():
        if key in str(numero_pedido):
            return mapped
    return None


def get_responsable_initials(numero_pedido: str) -> str:
    """Iniciales de quien recibe la devolución (columna Responsable).

    Salen del email y no del ERP directamente: así, cuando una inicial está
    reasignada (SS → Luis Bravo), la columna enseña a quien de verdad le llega.
    """
    email = get_responsable_email(numero_pedido)
    if not email:
        return ""
    if email in EMAIL_TO_INITIALS:
        return EMAIL_TO_INITIALS[email]
    try:
        from core.services import erp_db
        for iniciales, correo in erp_db.emails_por_iniciales().items():
            if correo.lower() == email.lower():
                return iniciales
    except Exception:  # noqa: BLE001
        pass
    # Sin ERP, por la tabla de respaldo (LB va antes que SS, así que un pedido
    # reasignado de Sandra sale como LB, que es quien lo lleva).
    for iniciales, correo in ERP_INITIALS_EMAIL.items():
        if correo.lower() == email.lower():
            return iniciales
    return ""


def get_doc_type_cc(doc_type_code: str) -> str | None:
    """Devuelve email CC del responsable técnico por código de tipo doc."""
    if not doc_type_code:
        return None
    return DOC_TYPE_EMAIL_MAP.get(doc_type_code.upper(), None)


def compute_recipients(df) -> tuple[list[str], list[str]]:
    """Calcula To y CC dinámicos basándose en Nº Pedido y tipo doc."""
    to_set = set(DEFAULT_TO)
    cc_set = set(DEFAULT_CC)

    if len(df) > 0:
        first = df.iloc[0]
        n_pedido = str(first.get("Nº Pedido", ""))
        resp_email = get_responsable_email(n_pedido)
        if resp_email:
            to_set.add(resp_email)

        # Buscar CC por tipo de documento (invertir DOC_TYPE_MAP)
        tipo_to_codes = {}
        for code, nombre in DOC_TYPE_MAP.items():
            tipo_to_codes.setdefault(nombre, []).append(code)

        for _, row in df.iterrows():
            # Intentar con _doc_code primero, luego buscar por Tipo de documento
            doc_code = str(row.get("_doc_code", ""))
            if doc_code:
                cc_email = get_doc_type_cc(doc_code)
                if cc_email:
                    cc_set.add(cc_email)
                    continue
            tipo = str(row.get("Tipo de documento", ""))
            for code in tipo_to_codes.get(tipo, []):
                cc_email = get_doc_type_cc(code)
                if cc_email:
                    cc_set.add(cc_email)
                    break

    return sorted(to_set), sorted(cc_set)


def _is_dark_color(hex_color: str) -> bool:
    """Devuelve True si el color hex tiene luminancia baja (fondo oscuro)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return False
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return False
    # Luminancia perceptual (rec. 709)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return lum < 128


def _load_logo_b64(bg_color: str | None = None) -> str | None:
    """Carga el logo EIPSA como base64 (PNG), profesional sobre cualquier fondo.

    Estrategia:
    1. Carga el PNG con alpha.
    2. Elimina fondo blanco/casi-blanco → transparente (limpia el halo).
    3. Si `bg_color` es oscuro: convierte la silueta del logo a BLANCO
       (convención corporativa estándar — version 'reverse' del logo).
       Esto garantiza máximo contraste sobre header navy/dark.
       Si `bg_color` es claro o None: preserva los colores originales.
    4. Compone sobre `bg_color` si se proporciona, devolviendo PNG opaco.
    """
    import base64, os, io
    try:
        from PIL import Image
    except ImportError:
        Image = None

    candidates = [
        r"M:\Comunes\JOSE\07 LOGOTIPOS\EIPSA NEW LOGO, CORTADO.png",
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", "eipsa_logo.png"),
    ]
    TARGET_HEIGHT = 80

    invert_to_white = bool(bg_color and _is_dark_color(bg_color))

    for path in candidates:
        try:
            with open(path, "rb") as f:
                raw = f.read()

            if Image is None:
                return base64.b64encode(raw).decode()

            img = Image.open(io.BytesIO(raw)).convert("RGBA")

            # 1. Limpiar fondo blanco/casi-blanco + (opcional) invertir silueta a blanco
            WHITE_THRESH = 230
            data = img.getdata()
            new_data = []
            for r, g, b, a in data:
                if r > WHITE_THRESH and g > WHITE_THRESH and b > WHITE_THRESH:
                    # Fondo blanco → transparente
                    new_data.append((255, 255, 255, 0))
                elif invert_to_white and a > 0:
                    # Sobre fondo oscuro: mapear cualquier color del logo a blanco
                    # preservando el alpha del original (mantiene anti-aliasing limpio)
                    new_data.append((255, 255, 255, a))
                else:
                    new_data.append((r, g, b, a))
            img.putdata(new_data)

            # 2. Redimensionar manteniendo proporción
            ratio = TARGET_HEIGHT / img.height
            new_size = (max(1, int(img.width * ratio)), TARGET_HEIGHT)
            img = img.resize(new_size, Image.LANCZOS)

            # 3. Composite sobre color del header (sin alpha)
            if bg_color:
                bg = Image.new("RGB", img.size, bg_color)
                bg.paste(img, mask=img.split()[3])
                img = bg

            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            continue
    return None


# Datos del pedido que ocupan la fila entera en el correo, en vez de una
# tarjeta de un tercio: las rutas de las carpetas no caben en 33%.
ANCHO_COMPLETO = {"Guardado en"}


def build_notification_html(df_info_dict, df_docs, deadline_date):
    """Genera el HTML del email de notificación — diseño corporativo EIPSA."""
    from collections import Counter

    # ── Paleta EIPSA ──
    NAVY   = "#1B3A5C"   # azul corporativo EIPSA
    CYAN   = "#00AEEF"   # azul claro del logo

    # Colores por estado
    STATUS_BG   = {"Rechazado": "#FFEBEE", "Com. Menores": "#FFF3E0", "Com. Mayores": "#FCE4EC",
                   "Aprobado": "#E8F5E9", "Comentado": "#F3E5F5", "Informativo": "#E3F2FD", "Eliminado": "#F5F5F5", "VOID": "#F5F5F5"}
    STATUS_TEXT = {"Rechazado": "#C62828", "Com. Menores": "#E65100", "Com. Mayores": "#AD1457",
                   "Aprobado": "#2E7D32", "Comentado": "#6A1B9A", "Informativo": "#1565C0", "Eliminado": "#757575", "VOID": "#757575"}
    STATUS_DOT  = {"Rechazado": "#E53935", "Com. Menores": "#FB8C00", "Com. Mayores": "#EC407A",
                   "Aprobado": "#43A047", "Comentado": "#AB47BC", "Informativo": "#1E88E5", "Eliminado": "#BDBDBD", "VOID": "#BDBDBD"}

    # ── Fecha límite ──
    deadline_str = deadline_date.strftime("%d de %B de %Y").replace(
        "January","enero").replace("February","febrero").replace("March","marzo").replace("April","abril").replace(
        "May","mayo").replace("June","junio").replace("July","julio").replace("August","agosto").replace(
        "September","septiembre").replace("October","octubre").replace("November","noviembre").replace("December","diciembre")

    # ── Logo: compuesto sobre el navy del header en backend (PIL), sin caja ──
    logo_b64 = _load_logo_b64(bg_color=NAVY)
    if logo_b64:
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" alt="EIPSA" '
            f'style="display:block;height:34px;width:auto;border:0;outline:0;" />'
        )
    else:
        # Fallback texto si no hay logo disponible
        logo_html = (
            f'<span style="font-size:18px;font-weight:800;color:#FFFFFF;'
            f'letter-spacing:1.2px;">EIPSA</span>'
        )

    # ── Info del pedido: tarjetas en grid 3 columnas ──
    def _tarjeta(k, v, ancho="33%", colspan=1):
        return (
            f'<td colspan="{colspan}" style="padding:0 6px 12px;width:{ancho};">'
            f'<table cellpadding="0" cellspacing="0" style="width:100%;background:#F8FAFF;'
            f'border:1px solid #DDE3F5;border-radius:6px;">'
            f'<tr><td style="padding:10px 14px;border-left:3px solid {CYAN};">'
            f'<p style="margin:0;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;'
            f'letter-spacing:0.06em;">{k}</p>'
            f'<p style="margin:3px 0 0;font-size:13px;font-weight:700;color:{NAVY};">{v}</p>'
            f'</td></tr></table></td>'
        )

    # «Guardado en» lleva rutas largas (y a veces varias): ocupa la fila entera,
    # debajo de las seis tarjetas de datos del pedido.
    items = [(k, v) for k, v in df_info_dict.items() if v and k not in ANCHO_COMPLETO]
    anchos = [(k, v) for k, v in df_info_dict.items() if v and k in ANCHO_COMPLETO]
    info_rows_html = ""
    for i in range(0, len(items), 3):
        chunk = items[i:i+3]
        cells = "".join(_tarjeta(k, v) for k, v in chunk)
        # Rellenar celdas vacías si el chunk es < 3
        cells += '<td style="padding:0 6px 12px;width:33%;"></td>' * (3 - len(chunk))
        info_rows_html += f'<tr>{cells}</tr>'
    for k, v in anchos:
        info_rows_html += f'<tr>{_tarjeta(k, v, ancho="100%", colspan=3)}</tr>'

    # ── Tabla de documentos ──
    cols = ["Doc. Cliente", "Título", "Rev.", "Estado"]
    available_cols = [c for c in cols if c in df_docs.columns]

    th_style = (f"background:{NAVY};color:#FFFFFF;padding:10px 14px;font-size:10px;font-weight:700;"
                f"letter-spacing:0.06em;text-transform:uppercase;text-align:left;")
    header_cells = "".join(f'<th style="{th_style}">{c}</th>' for c in available_cols)

    doc_rows = ""
    for i, (_, row) in enumerate(df_docs.iterrows()):
        estado = str(row.get("Estado", ""))
        bg_row = "#F8FAFF" if i % 2 == 0 else "#FFFFFF"
        cells = ""
        for c in available_cols:
            val = str(row.get(c, "") or "—")
            if c == "Estado":
                sbg  = STATUS_BG.get(estado, "#F5F5F5")
                stxt = STATUS_TEXT.get(estado, "#424242")
                sdot = STATUS_DOT.get(estado, "#BDBDBD")
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;">'
                    f'<span style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;'
                    f'border-radius:20px;background:{sbg};color:{stxt};font-size:11px;font-weight:700;">'
                    f'<span style="width:6px;height:6px;border-radius:50%;background:{sdot};flex-shrink:0;"></span>'
                    f'{val}</span></td>'
                )
            elif c == "Rev.":
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;text-align:center;">'
                    f'<span style="color:#E53935;font-size:12px;font-weight:700;">{val}</span></td>'
                )
            elif c == "Doc. Cliente":
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;'
                    f'font-family:\'Courier New\',monospace;font-size:11px;color:#37474F;white-space:nowrap;">{val}</td>'
                )
            else:
                cells += (
                    f'<td style="padding:10px 14px;border-bottom:1px solid #EEF2F7;'
                    f'font-size:12px;color:#37474F;line-height:1.5;">{val}</td>'
                )
        doc_rows += f'<tr style="background:{bg_row};">{cells}</tr>'

    # ── Resumen de estados ──
    estado_counts = Counter(str(row.get("Estado", "")) for _, row in df_docs.iterrows())
    summary_badges = ""
    for estado, count in estado_counts.items():
        sbg  = STATUS_BG.get(estado, "#F5F5F5")
        stxt = STATUS_TEXT.get(estado, "#424242")
        sdot = STATUS_DOT.get(estado, "#BDBDBD")
        summary_badges += (
            f'<span style="display:inline-flex;align-items:center;gap:5px;padding:5px 12px;'
            f'border-radius:20px;background:{sbg};color:{stxt};font-size:12px;font-weight:700;margin-right:8px;">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{sdot};"></span>'
            f'{count} {estado}</span>'
        )

    n_docs = len(df_docs)
    doc_label = "Documento devuelto" if n_docs == 1 else "Documentos devueltos"

    # ── Preheader (preview text en Outlook) ──
    _pedido = df_info_dict.get("Nº Pedido", "") or ""
    _cliente = df_info_dict.get("Cliente", "") or ""
    _estado_principal = estado_counts.most_common(1)[0][0] if estado_counts else ""
    preheader_text = " · ".join(x for x in [_pedido, _cliente, f"{n_docs} doc(s)", _estado_principal] if x)

    # ── Aviso de plazo: solo si hay algún documento NO aprobado ──
    # Si todos están "Aprobado", no procede plazo de respuesta (no hay nada que
    # corregir). Basta con un único documento distinto de Aprobado para mostrarlo.
    all_aprobado = bool(estado_counts) and all(
        str(e).strip().lower() == "aprobado" for e in estado_counts)
    deadline_block = "" if all_aprobado else f"""
      <!-- Aviso plazo -->
      <table cellpadding="0" cellspacing="0" style="width:100%;border-radius:8px;overflow:hidden;margin-bottom:28px;">
        <tr>
          <td style="background:#FFF8E1;border:1px solid #FFE082;border-radius:8px;padding:14px 18px;">
            <table cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td style="vertical-align:top;width:28px;font-size:18px;padding-top:1px;">&#9888;</td>
                <td>
                  <p style="margin:0;font-size:13px;font-weight:700;color:#BF6C00;">
                    Plazo de respuesta:
                    <span style="color:#C62828;">{deadline_str}</span>
                  </p>
                  <p style="margin:4px 0 0;font-size:12px;color:#795548;">
                    La documentación debe ser revisada, actualizada en ERP y subida antes de esta fecha.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#EEF2F9;font-family:Arial,Helvetica,sans-serif;">

<!-- Preheader oculto: visible en la línea de preview de Outlook -->
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#EEF2F9;">{preheader_text}</div>

<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F9;padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(30,45,125,0.12);">

  <!-- ═══ HEADER ═══ -->
  <tr>
    <td style="background:{NAVY};padding:14px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:middle;">{logo_html}</td>
          <td style="vertical-align:middle;text-align:right;">
            <p style="margin:0;font-size:14px;font-weight:700;color:#FFFFFF;letter-spacing:0.02em;">
              Devolución de Documentación
            </p>
            <p style="margin:4px 0 0;font-size:11px;color:{CYAN};letter-spacing:0.04em;text-transform:uppercase;">
              Notificación Automática
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- ═══ CUERPO ═══ -->
  <tr>
    <td style="padding:20px 28px 0;">

      <!-- Info del pedido -->
      <p style="margin:0 0 10px;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;letter-spacing:0.08em;">
        Datos del pedido
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;table-layout:fixed;">
        {info_rows_html}
      </table>

      <!-- Resumen estados -->
      <p style="margin:0 0 10px;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;letter-spacing:0.08em;">
        Resumen
      </p>
      <div style="margin-bottom:24px;">{summary_badges}</div>

      <!-- Tabla documentos -->
      <p style="margin:0 0 10px;font-size:10px;font-weight:700;color:{CYAN};text-transform:uppercase;letter-spacing:0.08em;">
        {doc_label} ({n_docs})
      </p>
      <table cellpadding="0" cellspacing="0" style="width:100%;border-radius:8px;overflow:hidden;border:1px solid #DDE3F5;margin-bottom:28px;">
        <thead><tr>{header_cells}</tr></thead>
        <tbody>{doc_rows}</tbody>
      </table>

      {deadline_block}

    </td>
  </tr>

  <!-- ═══ FOOTER ═══ -->
  <tr>
    <td style="background:#F4F7FC;border-top:3px solid {CYAN};padding:18px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td>
            <p style="margin:0;font-size:12px;font-weight:700;color:{NAVY};">
              Document Control
            </p>
            <p style="margin:3px 0 0;font-size:11px;color:#90A4AE;">
              DocFlow &nbsp;·&nbsp; © 2026 jparedesDS &nbsp;·&nbsp; Todos los derechos reservados
            </p>
          </td>
          <td style="text-align:right;vertical-align:middle;">
            <p style="margin:0;font-size:10px;color:#B0BEC5;">
              {datetime.now().strftime("%d/%m/%Y")}
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>

</body>
</html>"""
    return html


def _data_erp_path() -> str:
    """Ruta efectiva del data_erp.xlsx (respeta el vínculo configurado).

    Antes importaba `utils.config` (módulo del DocFlow grande, inexistente en
    lite) y reventaba. Ahora resuelve la ruta vía data_source con fallback a la
    ruta por defecto de core.config.
    """
    try:
        from core import data_source
        return data_source.get_effective_path("data_erp")
    except Exception:
        try:
            from core.config import DATA_ERP_PATH
            return DATA_ERP_PATH
        except Exception:
            return ""


def lookup_erp(numero_pedido: str) -> dict:
    """Busca en data_erp.xlsx por Nº Pedido y devuelve Cliente, Material, etc."""
    import os
    path = _data_erp_path()
    if not numero_pedido or not path or not os.path.exists(path):
        return {}
    try:
        df = read_excel_fast(path)
    except Exception:
        return {}

    mask = df["Nº Pedido"].astype(str).str.strip().str.contains(
        re.escape(numero_pedido), case=False, na=False
    )
    if mask.any():
        row = df[mask].iloc[0]
        return {k: str(row[k]) if pd.notna(row.get(k)) else ""
                for k in ("Cliente", "Material", "Nº PO")}
    return {}


def lookup_erp_by_npo(npo: str) -> dict:
    """Busca en data_erp.xlsx por Nº PO y devuelve Nº Pedido, Cliente, Material."""
    import os
    path = _data_erp_path()
    if not npo or not path or not os.path.exists(path):
        return {}
    try:
        df = read_excel_fast(path)
    except Exception:
        return {}

    if "Nº PO" not in df.columns:
        return {}

    mask = df["Nº PO"].astype(str).str.strip().str.contains(
        re.escape(npo), case=False, na=False
    )
    if mask.any():
        row = df[mask].iloc[0]
        return {k: str(row[k]) if pd.notna(row.get(k)) else ""
                for k in ("Nº Pedido", "Cliente", "Material")}
    return {}


# ═══════════════════════════════════════════════════════
#  RED DE SEGURIDAD: resolver por Nº Doc. Cliente contra el ERP
#  Común a TODOS los portales. Si un parser no consigue Nº Pedido / Cliente /
#  Material / PO / Doc. EIPSA, se emparejan los códigos de doc del email
#  (Doc. Cliente) con la columna Nº Doc. Cliente del ERP y se rellenan los
#  huecos. SOLO rellena celdas vacías; nunca pisa lo que el parser ya resolvió.
# ═══════════════════════════════════════════════════════

_BLANK_VALUES = {"", "nan", "none", "nat", "-"}


# Un documento anulado por el cliente. Técnicas Reunidas lo llama «M - VOID» y
# así se deja escrito, que es como lo nombra todo el mundo aquí; pero en los
# datos viejos (y en el ERP) está guardado como «Eliminado», y algunos portales
# lo mandan en inglés, así que hay que reconocer las cuatro formas.
_ANULADO = ("void", "elimin", "deleted", "borrado")


def es_anulado(estado) -> bool:
    """¿Este estado dice que el documento está anulado?"""
    texto = str(estado or "").strip().lower()
    return any(p in texto for p in _ANULADO)


def norm_doc_code(code) -> str:
    """Normaliza un código de doc de cliente para comparar sin ruido: sin
    espacios (internos incluidos) y en mayúsculas. Mantiene los guiones."""
    return re.sub(r"\s+", "", str(code or "")).upper()


def _is_blank(value) -> bool:
    return str(value).strip().lower() in _BLANK_VALUES


def erp_client_code_index() -> dict:
    """Índice {Nº Doc. Cliente normalizado → fila del ERP} sobre todo el
    monitoring. Import perezoso para evitar ciclos parsers↔services."""
    from core.services import monitoring
    idx: dict = {}
    for d in monitoring.get_monitoring_data():
        key = norm_doc_code(d.get("Nº Doc. Cliente"))
        if key and key not in idx:
            idx[key] = d
    return idx


def erp_header_from_row(row: dict) -> dict:
    """Extrae Nº Pedido / Supp. / Cliente / Material / PO de una fila del ERP.

    Separa el sufijo de suministro (-S00) del Nº Pedido.
    """
    out = {"n_pedido": "", "supp": "S00", "cliente": "", "material": "", "po": ""}
    ped = str(row.get("Nº Pedido", "")).strip()
    m = re.search(r"-(S\d{2})$", ped)
    if m:
        out["n_pedido"], out["supp"] = ped[:m.start()], m.group(1)
    else:
        out["n_pedido"] = ped
    out["cliente"] = str(row.get("Cliente", "") or "")
    out["material"] = str(row.get("Material", "") or "")
    out["po"] = str(row.get("Nº PO", "") or "").strip()
    return out


def _fill_blanks(df, col: str, value: str) -> None:
    """Pone `value` en las celdas vacías de `col` (si la columna existe)."""
    if value and col in df.columns:
        df[col] = [value if _is_blank(cur) else cur for cur in df[col]]


def _erp_value(row: dict, col: str) -> str:
    val = str(row.get(col, "") or "").strip()
    return "" if (_is_blank(val) or val.lower() == "no hay datos") else val


def erp_header_by_pedido(pedido: str) -> dict:
    """Cliente / Material / PO de un pedido a partir del ERP.

    · Cliente: de la consulta del ERP (base de datos). Es el cliente FINAL /
      planta (p. ej. NORDIC, OMEGA, ACME), igual que en `PO_CLIENT_MAP`; la
      ingeniería contratante (Técnicas Reunidas, Ayesa…) solo se usa si el ERP
      no tiene cliente final.
    · Material y PO: de data_erp.
    Devuelve solo los campos con valor.
    """
    pedido = str(pedido or "").strip()
    out: dict = {}
    if not pedido:
        return out
    try:
        from core.services import erp   # import perezoso: evita ciclos parsers↔services
        rows = erp.consulta(pedido)
        if rows:
            cliente = _erp_value(rows[0], "Cl. Final / Planta") or _erp_value(rows[0], "Cliente")
            if cliente:
                out["cliente"] = cliente
    except Exception:  # noqa: BLE001 — la consulta es un extra, no un requisito
        pass
    try:
        found = lookup_erp(pedido)
    except Exception:  # noqa: BLE001
        found = {}
    for key, col in (("material", "Material"), ("po", "Nº PO")):
        val = _erp_value(found, col)
        if val:
            out[key] = val
    return out


def enrich_missing_from_erp(df):
    """Red de seguridad para cualquier portal. Rellena los huecos que deje el
    parser (Nº Pedido / Cliente / Material / PO / Supp. / Doc. EIPSA /
    Responsable) con los datos del ERP, en dos pasadas:

      1. Por Nº Doc. Cliente: cada 'Doc. Cliente' del email contra la columna
         Nº Doc. Cliente del ERP (resuelve incluso el Nº Pedido).
      2. Por Nº Pedido: si ya se conoce el pedido pero faltan Cliente / Material
         / PO, se toman de la consulta del ERP y de data_erp.

    Sólo rellena celdas vacías: si el parser ya resolvió un campo, se respeta.
    """
    if df is None or getattr(df, "empty", True):
        return df

    # ── 1) Por Nº Doc. Cliente ────────────────────────────────────────────────
    matched = []
    if "Doc. Cliente" in df.columns:
        idx = erp_client_code_index()
        if idx:
            matched = [idx.get(norm_doc_code(c)) for c in df["Doc. Cliente"]]

    # Cabecera del pedido: de la primera fila emparejada (todos los docs de una
    # devolución pertenecen al mismo pedido).
    hit = next((m for m in matched if m is not None), None)
    if hit is not None:
        header = erp_header_from_row(hit)
        for col, val in (
            ("Nº Pedido", header["n_pedido"]),
            ("Cliente", header["cliente"]),
            ("Material", header["material"]),
            ("PO", header["po"]),
            ("Supp.", header["supp"]),
        ):
            _fill_blanks(df, col, val)

        # Doc. EIPSA: por fila, de su propia coincidencia exacta.
        if "Doc. EIPSA" in df.columns:
            df["Doc. EIPSA"] = [
                (str(m.get("Nº Doc. EIPSA", "") or "") or cur)
                if (_is_blank(cur) and m is not None) else cur
                for cur, m in zip(df["Doc. EIPSA"], matched)
            ]

    # ── 2) Por Nº Pedido ──────────────────────────────────────────────────────
    if "Nº Pedido" in df.columns:
        pedido = next((str(p).strip() for p in df["Nº Pedido"] if not _is_blank(p)), "")
        needs = [c for c in ("Cliente", "Material", "PO") if c in df.columns and any(_is_blank(v) for v in df[c])]
        if pedido and needs:
            header = erp_header_by_pedido(pedido)
            _fill_blanks(df, "Cliente", header.get("cliente", ""))
            _fill_blanks(df, "Material", header.get("material", ""))
            _fill_blanks(df, "PO", header.get("po", ""))

    # Responsable: si quedó vacío y ya conocemos el Nº Pedido.
    if "Responsable" in df.columns and "Nº Pedido" in df.columns:
        df["Responsable"] = [
            get_responsable_initials(ped) if (_is_blank(resp) and not _is_blank(ped)) else resp
            for resp, ped in zip(df["Responsable"], df["Nº Pedido"])
        ]

    return df


FINAL_COLUMNS = [
    "Nº Pedido", "Supp.", "Responsable", "Cliente", "Material", "PO",
    "Doc. EIPSA", "Doc. Cliente", "Título", "Rev.", "Estado",
    "Tipo de documento", "Crítico", "Nº Transmittal", "Fecha",
]
