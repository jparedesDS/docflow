"""Configuración global — IMAP/SMTP, paths y mapeos de equipo."""

import logging
import os

from dotenv import load_dotenv

from core.paths import app_root, data_dir, state_dir

# Cargar .env desde la raíz del proyecto si existe
load_dotenv(app_root() / ".env")

logger = logging.getLogger(__name__)

# ── Rutas a Excels ────────────────────────────────────────────────────────────
DATA_ERP_PATH = os.getenv("DATA_ERP_PATH") or str(data_dir() / "data_erp.xlsx")
CONSULTA_ERP_PATH = os.getenv("CONSULTA_ERP_PATH") or str(data_dir() / "consulta_erp.xlsx")
TAGS_PATH = os.getenv("TAGS_PATH") or str(data_dir() / "data_tags.xlsx")

# ── IMAP ──────────────────────────────────────────────────────────────────────
IMAP_HOST = os.getenv("IMAP_HOST", "imap.tuservidor.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "buzon@tuempresa.com")
IMAP_PASS = os.getenv("IMAP_PASS", "")

# ── SMTP ──────────────────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.tuservidor.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "buzon@tuempresa.com")
SMTP_PASS = os.getenv("SMTP_PASS", "")

# ── Anthropic (Claude) — para Bandeja AI y otros asistentes ───────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Estado runtime ────────────────────────────────────────────────────────────
PROCESSED_EMAILS_FILE = str(state_dir() / "processed_emails.json")

# ── Carpeta de pedidos en red (opcional, para guardar EML enviados) ───────────
PEDIDOS_BASE_PATH = os.getenv("PEDIDOS_BASE_PATH", "")

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
