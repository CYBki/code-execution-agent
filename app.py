"""Streamlit entry point — Data Analysis Agent with LangChain + OpenSandbox."""

import logging
import os

import streamlit as st
from dotenv import load_dotenv

from src.storage.db import init_db
from src.ui.chat import render_chat
from src.ui.components import render_sidebar
from src.ui.session import init_session
from src.ui.styles import CUSTOM_CSS
from src.utils.config import get_secret

# Configure logging
log_level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Console handler (INFO+)
logging.basicConfig(level=log_level, format=LOG_FORMAT)

# File handler (WARNING+ → persistent, rotating)
from logging.handlers import RotatingFileHandler

_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "app.log"),
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setLevel(logging.WARNING)
_file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logging.getLogger().addHandler(_file_handler)

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="Data Analysis Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Validate early so sandbox init doesn't start with missing credentials
try:
    get_secret("ANTHROPIC_API_KEY")
    get_secret("OPEN_SANDBOX_API_KEY")
except ValueError as e:
    st.error(f"⚠️ {e}")
    st.info(
        "API anahtarlarını `.env` dosyasına veya Streamlit secrets'a ekleyin.\n\n"
        "```\n"
        "ANTHROPIC_API_KEY=sk-ant-...\n"
        "OPEN_SANDBOX_API_KEY=local-sandbox-key-2024\n"
        "```"
    )
    st.stop()

# Initialize SQLite DB (creates tables if not exist)
init_db()

# Initialize session state (pre-warms sandbox in background)
init_session()

# Render UI
render_sidebar()
render_chat()
