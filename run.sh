#!/usr/bin/env bash
set -e

# --- Check .env exists ---
if [ ! -f .env ]; then
    echo "❌ .env dosyası bulunamadı."
    echo "   cp .env.example .env  →  sonra ANTHROPIC_API_KEY değerini girin."
    exit 1
fi

# --- Build all images + start services ---
echo "🔨 Image'lar build ediliyor..."
docker compose build

echo "🚀 Servisler başlatılıyor..."
docker compose up -d

echo ""
echo "✅ Hazır!"
echo "   Streamlit  → http://localhost:8501"
echo "   OpenSandbox → http://localhost:8080/health"
echo ""
echo "Loglar için: docker compose logs -f"
