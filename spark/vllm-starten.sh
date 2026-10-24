#!/bin/bash
# vLLM für Station 3 (DGX Spark) des Messstands starten, im NVIDIA-Container.
# Gemma 4 26B A4B als NVFP4 (4 Bit, ~19 GB) auf Port 8004. Dieses eine Gemma
# bedient im Modus „alles“ drei Abnehmer: den Vergleich „Ollama gegen vLLM“
# und den Lasttest, die Notizen im Reiter „Sprache“ und den Prüfer und
# Zweitleser des OCR-Werkzeugs LawAI (statt dessen Qwen3.8 27B, das 39 GB
# zusätzlich bräuchte). Darum Bild-Eingabe und 16k Kontext.
# Port 8004, weil LawAIs LightOnOCR auf 8000 läuft.
# --kv-cache-memory-bytes legt den Cache fest, statt vLLM den Rest von
# --gpu-memory-utilization füllen zu lassen; der Anteil ist dann nur noch die
# Prüfung beim Start, ob so viel Speicher frei ist.
# Stoppen: docker stop messstand-vllm
# Ohne Netz startfähig: Modelle nur aus dem lokalen Cache. Für den ersten
# Download einmal mit ONLINE=1 starten.
OFFLINE=1; [ "${ONLINE:-0}" = 1 ] && OFFLINE=0
docker rm -f messstand-vllm >/dev/null 2>&1
exec docker run --rm --name messstand-vllm --gpus all --ipc=host \
  -p 127.0.0.1:8004:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e HF_HUB_OFFLINE=$OFFLINE -e TRANSFORMERS_OFFLINE=$OFFLINE \
  nvcr.io/nvidia/vllm:26.09-py3 \
  vllm serve nvidia/Gemma-4-26B-A4B-NVFP4 \
    --served-model-name google/gemma-4-26b-a4b-it \
    --host 0.0.0.0 --port 8000 \
    --gpu-memory-utilization 0.25 \
    --kv-cache-memory-bytes 6G \
    --max-model-len 16384 \
    --max-num-seqs 16 \
    --limit-mm-per-prompt '{"image": 1}'
