# ---- Base image ----
FROM python:3.11-slim

# ---- System deps (curl for Ollama install + health checks) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates zstd bash \
 && rm -rf /var/lib/apt/lists/*

# ---- Install Ollama ----
RUN curl -fsSL https://ollama.com/install.sh | sh

# ---- App setup ----
WORKDIR /app
COPY . /app

ENV PYTHONPATH="/app/src"

# ---- Python deps ----
RUN pip install --no-cache-dir -r requirements.txt

# ---- HF Spaces port ----
EXPOSE 7860

# ---- Start script ----
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
