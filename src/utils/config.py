"""Configuration utilities — API key resolution with Streamlit Cloud support."""

import os

import streamlit as st


def get_secret(key: str) -> str:
    """Resolve a secret value with priority: st.secrets → os.environ → raise.

    Streamlit Cloud → st.secrets (from secrets.toml or dashboard)
    Local dev       → .env (loaded via python-dotenv)
    """
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        value = os.getenv(key)
        if not value:
            raise ValueError(
                f"'{key}' not found. "
                f"Add it to .env file or Streamlit secrets."
            )
        return value
