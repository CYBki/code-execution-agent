FROM python:3.12-slim

WORKDIR /app

# System deps for weasyprint/pdfplumber (needed by agent prompts references)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (frozen versions)
COPY requirements.txt .
COPY docker/wheels/ /tmp/wheels/
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy application code
COPY app.py .
COPY src/ src/
COPY skills/ skills/

# Persistent directories (via volume mount)
RUN mkdir -p /app/logs /app/data

# Streamlit config (under appuser home)
RUN mkdir -p /app/.streamlit
COPY .streamlit/config.toml /app/.streamlit/config.toml

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser
ENV HOME=/app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
