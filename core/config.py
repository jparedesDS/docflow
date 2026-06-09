"""Configuración global — IMAP/SMTP, paths y mapeos de equipo.

Resolución de valores (descendente):
  - Secretos (contraseñas, API keys): core.credentials (keyring / cifrado local)
    con fallback a .env para compatibilidad/migración.
  - Ajustes no secretos (hosts, puertos, rutas, URLs): preferences.json → .env →
    valor por defecto.
Editables desde la sección Ajustes; los cambios se aplican al reiniciar.
"""

import logging
import os

from dotenv import load_dotenv

from core import credentials
from core import preferences as _pref
from core.paths import app_root, data_dir, state_dir

# Cargar .env desde la raíz del proyecto si existe
load_dotenv(app_root() / ".env")

logger = logging.getLogger(__name__)


def _cfg(pref_key: str, env_key: str, default: str) -> str:
    """Ajuste no secreto: preferences → .env → default."""
    v = _pref.get(pref_key)
    if v:
        return str(v)
    return os.getenv(env_key, default)


# ── Rutas a Excels ────────────────────────────────────────────────────────────
DATA_ERP_PATH = os.getenv("DATA_ERP_PATH") or str(data_dir() / "data_erp.xlsx")
CONSULTA_ERP_PATH = os.getenv("CONSULTA_ERP_PATH") or str(data_dir() / "consulta_erp.xlsx")
TAGS_PATH = os.getenv("TAGS_PATH") or str(data_dir() / "data_tags.xlsx")

# ── IMAP ──────────────────────────────────────────────────────────────────────
IMAP_HOST = _cfg("imap_host", "IMAP_HOST", "imap.tuservidor.com")
IMAP_PORT = int(_cfg("imap_port", "IMAP_PORT", "993"))
IMAP_USER = _cfg("imap_user", "IMAP_USER", "buzon@tuempresa.com")
IMAP_PASS = credentials.get("imap_pass", env_fallback="IMAP_PASS")

# ── SMTP ──────────────────────────────────────────────────────────────────────
SMTP_HOST = _cfg("smtp_host", "SMTP_HOST", "smtp.tuservidor.com")
SMTP_PORT = int(_cfg("smtp_port", "SMTP_PORT", "465"))
SMTP_USER = _cfg("smtp_user", "SMTP_USER", "buzon@tuempresa.com")
SMTP_PASS = credentials.get("smtp_pass", env_fallback="SMTP_PASS")

# ── Anthropic (Claude) — para Bandeja AI y otros asistentes ───────────────────
ANTHROPIC_API_KEY = credentials.get("anthropic_api_key", env_fallback="ANTHROPIC_API_KEY")

# ── Buzones de Ofertas (unifica 3 bandejas comerciales) ───────────────────────
# Usuarios: preferences/.env. Contraseñas: almacén de secretos (keyring/cifrado).
OFERTAS_ACCOUNTS = [
    {"label": "Comercial",       "user": _cfg("ofertas_comercial_user", "OFERTAS_COMERCIAL_USER", "persona@tuempresa.com"),
     "password": credentials.get("ofertas_comercial_pass", env_fallback="OFERTAS_COMERCIAL_PASS")},
    {"label": "Dpto. Comercial", "user": _cfg("ofertas_dpto_user", "OFERTAS_DPTO_USER", "persona@tuempresa.com"),
     "password": credentials.get("ofertas_dpto_pass", env_fallback="OFERTAS_DPTO_PASS")},
    {"label": "Info",            "user": _cfg("ofertas_info_user", "OFERTAS_INFO_USER", "persona@tuempresa.com"),
     "password": credentials.get("ofertas_info_pass", env_fallback="OFERTAS_INFO_PASS")},
]

# ── Estado runtime ────────────────────────────────────────────────────────────
PROCESSED_EMAILS_FILE = str(state_dir() / "processed_emails.json")

# ── Carpeta de pedidos en red (opcional, para guardar EML enviados) ───────────
PEDIDOS_BASE_PATH = _cfg("pedidos_base_path", "PEDIDOS_BASE_PATH", "")

# ── DocuSign eSignature (JWT Server-to-Server) ───────────────────────────────
DOCUSIGN_INTEGRATION_KEY = credentials.get("docusign_integration_key", env_fallback="DOCUSIGN_INTEGRATION_KEY")
DOCUSIGN_USER_ID = credentials.get("docusign_user_id", env_fallback="DOCUSIGN_USER_ID")
DOCUSIGN_ACCOUNT_ID = credentials.get("docusign_account_id", env_fallback="DOCUSIGN_ACCOUNT_ID")
DOCUSIGN_BASE_URL = _cfg("docusign_base_url", "DOCUSIGN_BASE_URL", "https://demo.docusign.net")
DOCUSIGN_RSA_PRIVATE_KEY_PATH = _cfg(
    "docusign_rsa_path", "DOCUSIGN_RSA_PRIVATE_KEY_PATH", str(app_root() / "docusign_private.pem"))

# Mapa de claves de secreto ↔ variable .env (para la migración desde Ajustes)
SECRET_ENV_MAP = {
    "imap_pass": "IMAP_PASS", "smtp_pass": "SMTP_PASS",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "ofertas_comercial_pass": "OFERTAS_COMERCIAL_PASS",
    "ofertas_dpto_pass": "OFERTAS_DPTO_PASS",
    "ofertas_info_pass": "OFERTAS_INFO_PASS",
    "docusign_integration_key": "DOCUSIGN_INTEGRATION_KEY",
    "docusign_user_id": "DOCUSIGN_USER_ID",
    "docusign_account_id": "DOCUSIGN_ACCOUNT_ID",
}

# ── Equipo EIPSA ──────────────────────────────────────────────────────────────
USERS = {
    "JP":  {"nombre": "el administrador",      "emails": ["buzon@tuempresa.com", "persona@tuempresa.com"]},
    "AC":  {"nombre": "Ana Calvo",         "emails": ["persona@tuempresa.com"]},
    "JM":  {"nombre": "Jesus Martinez",    "emails": ["persona@tuempresa.com"]},
    "EC":  {"nombre": "Ernesto Carrillo",  "emails": ["persona@tuempresa.com"]},
    "LB":  {"nombre": "Luis Bravo",        "emails": ["persona@tuempresa.com"]},
    "SS":  {"nombre": "Santos Sanchez",    "emails": ["persona@tuempresa.com"]},
    "JV":  {"nombre": "Jorge Valtierra",   "emails": ["persona@tuempresa.com"]},
    "CCH": {"nombre": "Carlos Crespo",     "emails": ["persona@tuempresa.com"]},
    "LM":  {"nombre": "Laura Minguez",     "emails": ["persona@tuempresa.com"]},
    "DM":  {"nombre": "Daniel Marquez",    "emails": ["persona@tuempresa.com"]},
    "MS":  {"nombre": "Miguel Sahuquillo", "emails": ["persona@tuempresa.com"]},
    "ES":  {"nombre": "Enrique Serrano",   "emails": ["persona@tuempresa.com"]},
    "JZ":  {"nombre": "Javier Zofio",      "emails": ["persona@tuempresa.com"]},
    "JS":  {"nombre": "Jose A. Sanz",      "emails": ["persona@tuempresa.com"]},
    "JUZ": {"nombre": "Julio Zofio",       "emails": ["persona@tuempresa.com"]},
    "CZ":  {"nombre": "Carolina Zofio",    "emails": ["persona@tuempresa.com"]},
    "ALM": {"nombre": "Almacen",           "emails": ["persona@tuempresa.com"]},
    "MG":  {"nombre": "Mario Gil",         "emails": ["persona@tuempresa.com"]},
    "JUM": {"nombre": "Julian Martinez",   "emails": ["persona@tuempresa.com"]},
    "RM":  {"nombre": "Rosa Martin",       "emails": ["persona@tuempresa.com"]},
}


def startup_warnings():
    """Avisar de configuración mínima ausente al arrancar."""
    if not SMTP_PASS:
        logger.warning("SMTP_PASS vacío — el envío de emails fallará")
    if not IMAP_PASS:
        logger.warning("IMAP_PASS vacío — la lectura de emails fallará")
    if not os.path.exists(DATA_ERP_PATH):
        logger.warning("data_erp.xlsx no encontrado en %s — tracking no funcionará", DATA_ERP_PATH)
