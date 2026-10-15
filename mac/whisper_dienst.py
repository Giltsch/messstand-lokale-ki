"""Spracherkennung für den Reiter „Sprache“ auf dem Mac (Apple Silicon).

Gegenstück zu spark/whisper-starten.sh: dasselbe Modell (Whisper
large-v3-turbo), hier über MLX auf der Apple-GPU statt vLLM auf CUDA. Der
Messstand merkt keinen Unterschied, er spricht dieselbe OpenAI-Schnittstelle.

Einmal einrichten (lädt rund 1,6 GB, braucht Netz):
    uv sync --extra whisper-mac
    ONLINE=1 uv run python mac/whisper_dienst.py
Danach ohne Netz:
    uv run python mac/whisper_dienst.py          # Port 8002

GET  /v1/models
POST /v1/audio/transcriptions   (file, language, prompt, temperature, response_format)
"""

from __future__ import annotations

import os
import tempfile
import threading

# Ohne Netz startfähig: Modell nur aus dem lokalen Cache (ONLINE=1 für den ersten Download).
if os.environ.get("ONLINE") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

import mlx_whisper  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, File, Form, UploadFile  # noqa: E402

MODELL = os.environ.get("WHISPER_MODELL", "mlx-community/whisper-large-v3-turbo")
PORT = int(os.environ.get("WHISPER_PORT", "8002"))
# MLX rechnet ein Stück nach dem anderen; parallele Aufrufe warten.
SPERRE = threading.Lock()

app = FastAPI()


def erkennen(pfad: str, **optionen) -> dict:
    with SPERRE:
        return mlx_whisper.transcribe(pfad, path_or_hf_repo=MODELL, **optionen)


@app.get("/v1/models")
def modelle() -> dict:
    return {"object": "list", "data": [{"id": MODELL, "object": "model"}]}


@app.post("/v1/audio/transcriptions")
def transkribieren(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    temperature: float = Form(0.0),
    response_format: str = Form("json"),
    model: str | None = Form(None),  # wird ignoriert, es gibt nur eines
) -> dict:
    endung = os.path.splitext(file.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=endung) as tmp:
        tmp.write(file.file.read())
        tmp.flush()
        ergebnis = erkennen(tmp.name, language=language, initial_prompt=prompt or None, temperature=temperature)
    text = (ergebnis.get("text") or "").strip()
    if response_format != "verbose_json":
        return {"text": text}
    return {
        "text": text,
        "language": ergebnis.get("language"),
        "segments": [
            {"id": i, "start": s["start"], "end": s["end"], "text": s["text"]}
            for i, s in enumerate(ergebnis.get("segments") or [])
        ],
    }


if __name__ == "__main__":
    # Modell vorab laden, damit die erste Aufnahme nicht wartet.
    print(f"Lade {MODELL} …", flush=True)
    import numpy as np

    erkennen(np.zeros(16000, dtype=np.float32), language="de")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
