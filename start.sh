#!/usr/bin/env bash
set -e

echo "🚀 Starting Ollama..."
ollama serve &

# Wait for Ollama API to be ready
echo "⏳ Waiting for Ollama API..."
for i in {1..60}; do
  if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "✅ Ollama is ready"
    break
  fi
  sleep 1
done

PRIMARY_MODEL="${PRIMARY_MODEL:-llama3.1:latest}"
SECONDARY_MODEL="${SECONDARY_MODEL:-gemma3:1b}"
SUPREME_COURT_MODEL="${SUPREME_COURT_MODEL:-phi3:mini}"

echo "📌 Models:"
echo "  - PRIMARY_MODEL=$PRIMARY_MODEL"
echo "  - SECONDARY_MODEL=$SECONDARY_MODEL"
echo "  - SUPREME_COURT_MODEL=$SUPREME_COURT_MODEL"

echo "🔽 Pulling models (first boot can take time)..."
ollama pull "$PRIMARY_MODEL" || true
ollama pull "$SECONDARY_MODEL" || true
ollama pull "$SUPREME_COURT_MODEL" || true

echo "🌐 Starting Streamlit on port 7860..."
exec streamlit run app.py --server.port 7860 --server.address 0.0.0.0
