"""Spracherkennung fuer den Reiter „Sprache".

Der Browser nimmt in kurzen Stuecken auf (webm/opus). Jedes Stueck wird hier
mit ffmpeg in 16-kHz-Mono-WAV umgewandelt und an einen OpenAI-kompatiblen
Transkriptions-Server geschickt (vLLM mit Whisper). Gemessen wird, wie lange
die Erkennung im Verhaeltnis zur Laenge der Aufnahme braucht.
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import time

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .config import SpracheCfg

ABTASTRATE = 16000


async def _nach_wav(daten: bytes) -> bytes:
    """Beliebiges Audio (webm, ogg, m4a, mp3, wav) → 16 kHz Mono WAV."""
    if shutil.which("ffmpeg") is None:
        raise HTTPException(500, "ffmpeg fehlt auf diesem Gerät. Ohne das lässt sich Audio nicht umwandeln.")
    prozess = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
        "-ac", "1", "-ar", str(ABTASTRATE), "-f", "wav", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    aus, fehler = await prozess.communicate(daten)
    if prozess.returncode != 0 or len(aus) <= 44:
        raise HTTPException(400, "Die Aufnahme ließ sich nicht lesen: " + fehler.decode(errors="replace")[:300])
    return aus


def router_bauen(cfg: SpracheCfg) -> APIRouter:
    router = APIRouter(prefix="/api/sprache")
    basis = cfg.url.rstrip("/")
    kopf = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    sprecher = cfg.sprecher_url.rstrip("/") if cfg.sprecher_url else None

    async def stimmabdruecke(wav: bytes, abschnitte: list[list[float]]) -> list | None:
        """Ein Vektor je Abschnitt, oder None, wenn der Dienst nicht laeuft."""
        if not sprecher or not abschnitte:
            return None
        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                antwort = await c.post(
                    f"{sprecher}/einbettungen",
                    json={"wav_b64": base64.b64encode(wav).decode(), "abschnitte": abschnitte},
                )
            return antwort.json().get("einbettungen") if antwort.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    @router.get("/status")
    async def status() -> dict:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                antwort = await c.get(f"{basis}/models", headers=kopf)
            modelle = [m.get("id") for m in antwort.json().get("data", [])] if antwort.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            modelle = None
        sprecher_da = False
        if sprecher:
            try:
                async with httpx.AsyncClient(timeout=2.0) as c:
                    sprecher_da = (await c.get(f"{sprecher}/health")).status_code == 200
            except httpx.HTTPError:
                pass
        return {
            "sprecher": sprecher_da,
            "online": modelle is not None,
            "bereit": bool(modelle) and cfg.modell in modelle,
            "modell": cfg.modell,
            "label": cfg.label,
            "url": basis,
        }

    @router.post("/erkennen")
    async def erkennen(datei: UploadFile = File(...), vorher: str = Form("")) -> dict:
        roh = await datei.read()
        if not roh:
            raise HTTPException(400, "Die Aufnahme ist leer.")
        wav = await _nach_wav(roh)
        audio_s = (len(wav) - 44) / (2 * ABTASTRATE)
        felder = {"model": cfg.modell, "language": cfg.sprache, "temperature": "0", "response_format": "verbose_json"}
        # Das Ende des bisherigen Textes hilft Whisper ueber die Stueckgrenze.
        if vorher.strip():
            felder["prompt"] = vorher.strip()[-200:]
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=300.0) as c:
                antwort = await c.post(
                    f"{basis}/audio/transcriptions",
                    headers=kopf,
                    data=felder,
                    files={"file": ("stueck.wav", wav, "audio/wav")},
                )
        except httpx.HTTPError as fehler:
            raise HTTPException(
                502, f"Die Spracherkennung unter {basis} antwortet nicht ({type(fehler).__name__}). "
                "Starten mit: spark/spark-modus.sh sprache"
            ) from fehler
        rechen_s = time.perf_counter() - start
        if antwort.status_code != 200:
            raise HTTPException(502, f"Spracherkennung: Fehlercode {antwort.status_code}: {antwort.text[:300]}")
        daten = antwort.json()
        text = (daten.get("text") or "").strip()
        abschnitte = [
            {"start": float(a.get("start", 0)), "ende": float(a.get("end", 0)), "text": (a.get("text") or "").strip()}
            for a in daten.get("segments") or []
            if (a.get("text") or "").strip()
        ] or ([{"start": 0.0, "ende": audio_s, "text": text}] if text else [])
        start_s = time.perf_counter()
        vektoren = await stimmabdruecke(wav, [[a["start"], a["ende"]] for a in abschnitte])
        sprecher_s = time.perf_counter() - start_s
        if vektoren and len(vektoren) == len(abschnitte):
            for a, v in zip(abschnitte, vektoren):
                a["stimme"] = v
        return {
            "text": text,
            "abschnitte": abschnitte,
            "sprecher_s": round(sprecher_s, 3) if vektoren else None,
            "audio_s": round(audio_s, 2),
            "rechen_s": round(rechen_s, 3),
            "echtzeit": round(audio_s / rechen_s, 1) if rechen_s > 0 else None,
        }

    return router
