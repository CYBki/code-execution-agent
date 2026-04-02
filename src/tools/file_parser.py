"""Local file parser tool — fast schema inspection without sandbox round-trip."""

from __future__ import annotations

import io
import os
from typing import Any

import streamlit as st
from langchain_core.tools import tool


MAX_PREVIEW_ROWS = 100


def _parse_csv(file_bytes: bytes, filename: str, sep: str = ",") -> dict[str, Any]:
    import pandas as pd

    df = pd.read_csv(io.BytesIO(file_bytes), nrows=MAX_PREVIEW_ROWS, sep=sep)
    total_rows = file_bytes.count(b'\n') - 1  # minus header

    return {
        "type": "csv",
        "filename": filename,
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "preview_rows": len(df),
        "total_rows": total_rows,
        "file_size_mb": round(len(file_bytes) / (1024 * 1024), 2),
        "preview": df.head(10).to_string(),
    }


def _parse_tsv(file_bytes: bytes, filename: str) -> dict[str, Any]:
    return _parse_csv(file_bytes, filename, sep='\t')


def _parse_excel(file_bytes: bytes, filename: str) -> dict[str, Any]:
    import pandas as pd

    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet_names = xls.sheet_names
    sheets_info = {}
    for sheet in sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, nrows=MAX_PREVIEW_ROWS)
        sheets_info[sheet] = {
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "preview_rows": len(df),
            "preview": df.head(5).to_string(),
        }

    return {
        "type": "excel",
        "filename": filename,
        "sheets": sheet_names,
        "sheet_count": len(sheet_names),
        "file_size_mb": round(len(file_bytes) / (1024 * 1024), 2),
        "sheets_info": sheets_info,
    }


def _parse_json(file_bytes: bytes, filename: str) -> dict[str, Any]:
    import pandas as pd

    try:
        df = pd.read_json(io.BytesIO(file_bytes), lines=True, nrows=MAX_PREVIEW_ROWS)
    except ValueError:
        df = pd.read_json(io.BytesIO(file_bytes))
    return {
        "type": "json",
        "filename": filename,
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "total_rows": len(df),
        "file_size_mb": round(len(file_bytes) / (1024 * 1024), 2),
        "preview": df.head(10).to_string(),
    }


def _parse_pdf(file_bytes: bytes, filename: str) -> dict[str, Any]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages_info = []
        text_preview = ""
        tables_found = 0

        for i, page in enumerate(pdf.pages[:5]):  # First 5 pages
            page_text = page.extract_text() or ""
            page_tables = page.extract_tables() or []
            tables_found += len(page_tables)
            pages_info.append({
                "page": i + 1,
                "text_length": len(page_text),
                "tables": len(page_tables),
            })
            if i == 0:
                text_preview = page_text[:500]

        return {
            "type": "pdf",
            "filename": filename,
            "total_pages": len(pdf.pages),
            "pages_previewed": len(pages_info),
            "tables_found": tables_found,
            "file_size_mb": round(len(file_bytes) / (1024 * 1024), 2),
            "pages_info": pages_info,
            "text_preview": text_preview,
        }


PARSERS = {
    ".csv": _parse_csv,
    ".tsv": _parse_tsv,
    ".xlsx": _parse_excel,
    ".xls": _parse_excel,
    ".xlsm": _parse_excel,
    ".json": _parse_json,
    ".pdf": _parse_pdf,
}


def make_parse_file_tool(uploaded_files: list | None = None):
    """Factory: create the parse_file tool with access to uploaded files.

    Args:
        uploaded_files: List of uploaded file objects (from st.file_uploader).
                       If None, falls back to st.session_state (for backwards compat).
    """
    # Capture uploaded_files in closure to avoid st.session_state access in agent thread
    _files = uploaded_files if uploaded_files is not None else st.session_state.get("uploaded_files", [])

    @tool
    def parse_file(filename: str) -> str:
        """Parse an uploaded file and return its schema summary.

        Returns column names, data types, row count, file size, and a preview.
        Use this FIRST before analyzing any file — it's fast (runs locally).

        Args:
            filename: Name of the uploaded file (e.g., "sales.xlsx")
        """
        # Use captured _files from closure (thread-safe, no st.session_state access)
        uploaded_files = _files
        target = None
        for f in uploaded_files:
            if f.name == filename:
                target = f
                break

        if target is None:
            available = [f.name for f in uploaded_files] if uploaded_files else []
            return f"File '{filename}' not found. Available files: {available}"

        ext = os.path.splitext(filename)[1].lower()
        parser = PARSERS.get(ext)
        if parser is None:
            return f"Unsupported file type: {ext}. Supported: {list(PARSERS.keys())}"

        try:
            target.seek(0)
            data = target.getvalue()
            result = parser(data, filename)
            size_mb = len(data) / (1024 * 1024)
            output = str(result)

            # Add explicit next-step instruction to prevent ls/parse_file loops
            output += f"\n\n{'='*70}\n"
            output += "✅ PARSE BAŞARILI. SONRAKI ADIM:\n\n"
            output += "❌ YAPMA: ls, cat, os.listdir, parse_file tekrar çağırma\n"
            output += "✅ YAP:\n"
            output += f"1. DÜŞÜNCE yaz: 'Schema alındı. Dosya /home/sandbox/{filename}. Şimdi pd.read_excel ile okuyacağım.'\n"
            output += "2. execute() çağır:\n"
            output += f"   df = pd.read_excel('/home/sandbox/{filename}')\n"
            output += "   print(f'✅ {{len(df)}} satır yüklendi')\n"
            output += f"\n⚠️ SONRAKİ TOOL: execute (BAŞKA HİÇBİR TOOL ÇAĞIRMA!)\n"
            output += "{'='*70}"

            if size_mb >= 40:
                output += (
                    f"\n\n⚠️ BÜYÜK DOSYA ({size_mb:.1f} MB ≥ 40MB) — DUCKDB STRATEJİSİ ZORUNLU. "
                    "pandas ile pd.read_excel() KULLANMA (çok yavaş/bellek sorunu). "
                    "Doğru strateji: "
                    "① df = pd.read_excel(path) ile CSV'ye çevir: df.to_csv('/home/sandbox/temp.csv', index=False); del df "
                    "② duckdb.sql(\"SELECT ... FROM read_csv_auto('/home/sandbox/temp.csv')\").df() "
                    "Threshold: file_size_mb >= 40 → DuckDB, < 40 → pandas."
                )
            return output
        except Exception as e:
            return f"Error parsing '{filename}': {e}"

    return parse_file
