#!/bin/bash
# vLLM für Station 3 (DGX Spark) des Messstands starten, im NVIDIA-Container.
# Gemma 4 26B A4B als NVFP4 (4 Bit, ~19 GB), damit gpt-oss:120b in Ollama daneben passt.
# Vorher die LawAI-Server anhalten:  systemctl --user stop lawai-ocr lawai-judge
# Danach wieder starten:             systemctl --user start lawai-ocr lawai-judge
# Stoppen:                           docker stop messstand-vllm
# (Der vLLM aus ~/venvs/vllm-judge geht nicht: dessen transformers 5.15 bricht
#  beim Gemma-4-Config ab, und das venv gehört LawAI.)
# Ohne Netz startfähig: Modelle nur aus dem lokalen Cache. Für den ersten
# Download einmal mit ONLINE=1 starten.
OFFLINE=1; [ "${ONLINE:-0}" = 1 ] && OFFLINE=0
docker rm -f messstand-vllm >/dev/null 2>&1
exec docker run --rm --name messstand-vllm --gpus all --ipc=host \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e HF_HUB_OFFLINE=$OFFLINE -e TRANSFORMERS_OFFLINE=$OFFLINE \
  nvcr.io/nvidia/vllm:26.09-py3 \
  vllm serve nvidia/Gemma-4-26B-A4B-NVFP4 \
    --served-model-name google/gemma-4-26b-a4b-it \
    --host 0.0.0.0 --port 8000 \
    --gpu-memory-utilization 0.25 \
    --max-model-len 8192 \
    --max-num-seqs 16
