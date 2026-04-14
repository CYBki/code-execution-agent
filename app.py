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
from src.utils.logging_config import setup_logging

# Configure structured JSON logging
log_level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO
setup_logging(log_level)

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
