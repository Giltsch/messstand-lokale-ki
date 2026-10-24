"""Stimmabdrücke für den Reiter „Sprache“ des Messstands.

NVIDIA TitaNet-large (NeMo) rechnet aus einem Stück Audio einen Vektor, der
die Stimme beschreibt, nicht das Gesagte. Gleiche Stimme ergibt ähnliche
Vektoren. Zuordnen (Sprecher 1, 2, …) tut der Messstand selbst.

Start (nutzt die Umgebung aus dem Projekt speech_to_text, dort liegen NeMo
und das Modell); spark/spark-modus.sh alles erledigt das:
    ~/Dokumente/Projekte/speech_to_text/.venv/bin/python spark/sprecher_dienst.py   # Port 8003

POST /einbettungen   {"wav_b64": "...", "abschnitte": [[start_s, ende_s], ...]}
                     → {"einbettungen": [[...192 Zahlen...] | null, ...]}
                     Ohne "abschnitte": ein Vektor für das ganze Stück.
GET  /health
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Ohne Netz startfähig: Modell nur aus dem lokalen Cache (ONLINE=1 für den ersten Download).
if os.environ.get("ONLINE") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402

PORT = 8003
ABTASTRATE = 16000
MIN_S = 0.6  # kürzer ergibt keinen brauchbaren Stimmabdruck

GERAET = "cuda" if torch.cuda.is_available() else "cpu"
SPERRE = threading.Lock()


def modell_laden():
    import nemo.collections.asr as nemo_asr

    m = nemo_asr.models.EncDecSpeakerLabelModel.from_pretrained(
        model_name="nvidia/speakerverification_en_titanet_large"
    )
    return m.to(GERAET).eval()


MODELL = modell_laden()


def wav_lesen(daten: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(daten)) as w:
        if w.getframerate() != ABTASTRATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("Erwartet 16 kHz, mono, 16 Bit.")
        roh = w.readframes(w.getnframes())
    return np.frombuffer(roh, dtype=np.int16).astype(np.float32) / 32768.0


def einbettung(audio: np.ndarray) -> list[float] | None:
    if len(audio) < MIN_S * ABTASTRATE:
        return None
    signal = torch.from_numpy(audio).float().unsqueeze(0).to(GERAET)
    laenge = torch.tensor([signal.shape[1]], device=GERAET)
    with SPERRE, torch.no_grad():
        _, emb = MODELL(input_signal=signal, input_signal_length=laenge)
    v = emb.squeeze().float().cpu().numpy()
    return (v / (np.linalg.norm(v) + 1e-9)).round(5).tolist()


class Handler(BaseHTTPRequestHandler):
    def _antwort(self, code: int, daten: dict) -> None:
        rumpf = json.dumps(daten).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rumpf)))
        self.end_headers()
        self.wfile.write(rumpf)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._antwort(200, {"ok": True, "geraet": GERAET, "modell": "titanet_large"})
        else:
            self._antwort(404, {"fehler": "unbekannt"})

    def do_POST(self) -> None:
        if self.path != "/einbettungen":
            self._antwort(404, {"fehler": "unbekannt"})
            return
        try:
            anfrage = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            audio = wav_lesen(base64.b64decode(anfrage["wav_b64"]))
            abschnitte = anfrage.get("abschnitte") or [[0, len(audio) / ABTASTRATE]]
            ergebnis = [
                einbettung(audio[int(a * ABTASTRATE) : int(e * ABTASTRATE)]) for a, e in abschnitte
            ]
        except Exception as fehler:  # Meldung geht an den Messstand
            self._antwort(400, {"fehler": f"{type(fehler).__name__}: {fehler}"})
            return
        self._antwort(200, {"einbettungen": ergebnis})

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print(f"Sprecher-Dienst auf 127.0.0.1:{PORT} ({GERAET})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
