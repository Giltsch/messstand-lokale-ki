#!/bin/bash
# Spracherkennung für den Reiter „Sprache“ des Messstands: Whisper large-v3-turbo
# über vLLM im NVIDIA-Container, OpenAI-kompatibel (/v1/audio/transcriptions).
# Port 8002, damit es neben LawAI (8000, 8001) und vLLM-Gemma (8000) nicht kollidiert.
# Braucht rund 10 GB; passt neben GPT-OSS 120B.
# Stoppen: docker stop messstand-whisper
# Ohne Netz startfähig: Modelle nur aus dem lokalen Cache. Für den ersten
# Download einmal mit ONLINE=1 starten.
OFFLINE=1; [ "${ONLINE:-0}" = 1 ] && OFFLINE=0
docker rm -f messstand-whisper >/dev/null 2>&1
exec docker run --rm --name messstand-whisper --gpus all --ipc=host \
  -p 127.0.0.1:8002:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e HF_HUB_OFFLINE=$OFFLINE -e TRANSFORMERS_OFFLINE=$OFFLINE \
  nvcr.io/nvidia/vllm:26.09-py3 \
  vllm serve openai/whisper-large-v3-turbo \
    --host 0.0.0.0 --port 8000 \
    --gpu-memory-utilization 0.08 \
    --max-num-seqs 8
