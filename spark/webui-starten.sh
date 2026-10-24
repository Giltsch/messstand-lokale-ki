#!/bin/bash
# Open WebUI für Station 3: ein Chat zum freien Ausprobieren neben dem Messstand.
# Nur unter http://127.0.0.1:3001, ohne Anmeldung, ohne Internetzugriffe
# (OFFLINE_MODE, keine Websuche, keine Update-Prüfung). Spricht mit Ollama
# (:11434) und vLLM-Gemma (:8004); angeboten werden nur die Modelle aus
# stations/spark.yaml (spark/webui_einrichten.py).
# Braucht keine GPU, rund 1,5 GB Arbeitsspeicher.
# Chats liegen im Docker-Volume messstand-webui. Der ältere Container
# „open-webui“ (Port 3000, Qwen auf :8001) bleibt davon unberührt.
# Stoppen: docker stop messstand-webui
set -euo pipefail
HIER="$(cd "$(dirname "$0")" && pwd)"
if docker container inspect messstand-webui >/dev/null 2>&1; then
  docker start messstand-webui >/dev/null
else
  # --network host: Ollama und vLLM lauschen auf 127.0.0.1 des Spark.
  docker run -d --name messstand-webui --network host \
    -e HOST=127.0.0.1 -e PORT=3001 -e WEBUI_AUTH=False \
    -e OFFLINE_MODE=true -e HF_HUB_OFFLINE=1 \
    -e ENABLE_OLLAMA_API=true -e OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    -e ENABLE_OPENAI_API=true -e OPENAI_API_BASE_URL=http://127.0.0.1:8004/v1 -e OPENAI_API_KEY=lokal \
    -e ENABLE_VERSION_UPDATE_CHECK=false -e ENABLE_EVALUATION_ARENA_MODELS=false -e ENABLE_WEB_SEARCH=false \
    -e ENABLE_COMMUNITY_SHARING=false -e ENABLE_DIRECT_CONNECTIONS=false \
    -v messstand-webui:/app/backend/data ghcr.io/open-webui/open-webui:main >/dev/null
fi
for _ in $(seq 90); do curl -sf -o /dev/null http://127.0.0.1:3001/health && break; sleep 2; done
cd "$HIER/.." && uv run python spark/webui_einrichten.py
