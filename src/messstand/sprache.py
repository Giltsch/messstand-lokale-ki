"""Spracherkennung fuer den Reiter „Sprache".

Der Browser nimmt in kurzen Stuecken auf (webm/opus). Jedes Stueck wird hier
mit ffmpeg in 16-kHz-Mono-PCM umgewandelt und an einen OpenAI-kompatiblen
Transkriptions-Server geschickt (vLLM mit Whisper). Gemessen wird, wie lange
die Erkennung im Verhaeltnis zur Laenge der Aufnahme braucht.

Bewusst response_format=json und nicht verbose_json: vLLM baut bei
verbose_json auch den Text nur aus vollstaendigen Zeitstempel-Segmenten
zusammen und verliert dabei ganze Satzteile (gemessen 24.10.2026: ein
14-s-Stueck 8 statt 25 Woerter). Bei einem Stueck ganz ohne Sprache bricht es
sogar mit „tuple index out of range“ ab. Die Zeitabschnitte fuer die
Sprecherzuordnung schneiden wir darum selbst, an Sprechpausen.

Kein prompt mit dem bisherigen Text: Whisper schreibt den dann fort, statt zu
hoeren (gemessen 24.10.2026: nach einem Podcast wurde aus „Ja, gerne.“ eine
Schleife „Künstlich, ich bin ein Künstlich, …“).

Waehrend ein Stueck noch laeuft, schickt der Browser es jede Sekunde als
„vorlaeufig“: dann nur der Text, ohne Stimmabdruecke, fuer die Live-Zeile.
"""

from __future__ import annotations

import asyncio
import base64
import io
import re
import shutil
import time
import wave
import zlib

import httpx
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .config import SpracheCfg

ABTASTRATE = 16000
# Whisper sieht hoechstens 30 s auf einmal. Laengeres (hochgeladene Dateien)
# schneiden wir selbst an der laengsten Pause zwischen MIN_S und HOECHSTENS_S.
TEIL_HOECHSTENS_S = 28.0
TEIL_MIN_S = 8.0
RAHMEN_S = 0.03
PAUSE_MIN_S = 0.25
# Ohne Sprache geht ein Teil nicht an Whisper: auf Stille erfindet es sonst
# „Vielen Dank.“. Sprache heisst: mindestens SPRACHE_MIN_S deutlich ueber dem
# Grundrauschen (Faktor SPRACHE_ABSTAND, nie unter SPRACHE_BODEN, -60 dBFS) –
# relativ, weil manche Mikrofone sehr leise liefern. Durchgehend laute Sprache
# ohne Pausen hebt das Grundrauschen an; sie zaehlt ueber SPRACHE_LAUT.
SPRACHE_ABSTAND = 3.0
SPRACHE_BODEN = 0.001
SPRACHE_LAUT = 0.02
SPRACHE_MIN_S = 0.1
# Leise Mikrofone vor Whisper anheben: auf halbe Vollaussteuerung (99,9-%-Spitze),
# hoechstens 20-fach. Gemessen 24.10.2026: Aufnahme 20 dB zu leise 7 statt 25 Woerter.
ZIEL_SPITZE = 0.5
HOECHSTE_VERSTAERKUNG = 20.0
# Gegen Whisper-Schleifen („hallo, hier ist er, hallo, hier ist er, …“), wie im
# Original von OpenAI: Laenge nach Audiodauer begrenzen; laesst sich der Text
# staerker als SCHLEIFE_KOMPRESSION packen, mit hoeherer Temperatur neu erkennen;
# was dann noch dreimal hintereinander gleich ist, bleibt einmal stehen.
TOKEN_JE_S = 8
SCHLEIFE_KOMPRESSION = 2.4
ZWEITE_TEMPERATUR = "0.4"
# Was Whisper auf Stille und Rauschen erfindet (aus Untertiteln gelernt). Nur
# verworfen, wenn das Stueck kaum Sprache hat: ein echtes „Vielen Dank.“ bleibt.
STILLE_FLOSKELN = re.compile(
    r"^\W*(vielen dank|danke|danke schön|tschüss|\*?title\*?|untertitel.*|copyright.*|amara.*"
    r"|vielen dank fürs zuschauen|danke fürs zuschauen|bis zum nächsten mal)\W*$", re.IGNORECASE)
FLOSKEL_SPRECHZEIT_S = 1.0


async def _nach_pcm(daten: bytes) -> np.ndarray:
    """Beliebiges Audio (webm, ogg, m4a, mp3, wav) → 16 kHz Mono, int16."""
    if shutil.which("ffmpeg") is None:
        raise HTTPException(500, "ffmpeg fehlt auf diesem Gerät. Ohne das lässt sich Audio nicht umwandeln.")
    prozess = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
        "-ac", "1", "-ar", str(ABTASTRATE), "-f", "s16le", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    aus, fehler = await prozess.communicate(daten)
    if prozess.returncode != 0 or len(aus) < 2:
        raise HTTPException(400, "Die Aufnahme ließ sich nicht lesen: " + fehler.decode(errors="replace")[:300])
    return np.frombuffer(aus[: len(aus) // 2 * 2], dtype=np.int16)


def _wav(pcm: np.ndarray) -> bytes:
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ABTASTRATE)
        w.writeframes(pcm.tobytes())
    return puffer.getvalue()


def _pegel(pcm: np.ndarray) -> np.ndarray:
    """RMS je Rahmen von RAHMEN_S, Vollaussteuerung = 1."""
    n = int(RAHMEN_S * ABTASTRATE)
    rahmen = len(pcm) // n
    stuecke = (pcm[: rahmen * n].astype(np.float32) / 32768).reshape(rahmen, n)
    return np.sqrt(np.mean(stuecke**2, axis=1))


def _angehoben(pcm: np.ndarray) -> np.ndarray:
    spitze = float(np.percentile(np.abs(pcm.astype(np.float32)), 99.9)) / 32768
    faktor = min(HOECHSTE_VERSTAERKUNG, ZIEL_SPITZE / max(spitze, 1e-6))
    return np.clip(pcm.astype(np.float32) * faktor, -32768, 32767).astype(np.int16)


def _sprechzeit(pcm: np.ndarray) -> float:
    """Sekunden deutlich ueber dem Grundrauschen."""
    pegel = _pegel(pcm)
    if not len(pegel):
        return 0.0
    schwelle = max(SPRACHE_BODEN, SPRACHE_ABSTAND * float(np.percentile(pegel, 20)))
    ueber = np.sum(pegel >= schwelle) + np.sum(pegel >= SPRACHE_LAUT) * (schwelle > SPRACHE_LAUT)
    return float(ueber) * RAHMEN_S


def _kompression(text: str) -> float:
    roh = text.encode("utf-8")
    return len(roh) / len(zlib.compress(roh)) if roh else 0.0


def _ohne_schleifen(text: str) -> str:
    """Folgen von 1 bis 8 Woertern, die mindestens dreimal direkt hintereinander
    stehen, auf ein Vorkommen kuerzen. Verglichen ohne Satzzeichen."""
    woerter = text.split()
    for n in range(1, 9):
        schluessel = [re.sub(r"\W", "", w).lower() for w in woerter]
        aus, i = [], 0
        while i < len(woerter):
            block = schluessel[i:i + n]
            k = 1
            while len(block) == n and schluessel[i + k * n:i + (k + 1) * n] == block:
                k += 1
            if k >= 3:
                aus += woerter[i:i + n]
                i += k * n
            else:
                aus.append(woerter[i])
                i += 1
        woerter = aus
    return " ".join(woerter)


def _pausen(pcm: np.ndarray) -> list[tuple[float, float]]:
    """Leise Stellen (Beginn, Ende in s). Schwelle relativ zum Grundrauschen,
    weil jedes Mikrofon anders laut ist."""
    pegel = _pegel(pcm)
    if len(pegel) < 2:
        return []
    schwelle = max(0.003, 3 * float(np.percentile(pegel, 10)))
    leise = pegel < schwelle
    pausen, beginn = [], None
    for i, l in enumerate(np.append(leise, False)):
        if l and beginn is None:
            beginn = i
        elif not l and beginn is not None:
            if (i - beginn) * RAHMEN_S >= PAUSE_MIN_S:
                pausen.append((beginn * RAHMEN_S, i * RAHMEN_S))
            beginn = None
    return pausen


def _teile(pcm: np.ndarray) -> list[tuple[float, float]]:
    """Schnitte fuer Whisper: kurze Stuecke bleiben ganz, lange werden an der
    laengsten Pause im erlaubten Fenster geteilt (sonst hart bei HOECHSTENS_S)."""
    gesamt = len(pcm) / ABTASTRATE
    pausen = _pausen(pcm) if gesamt > TEIL_HOECHSTENS_S else []
    teile, anfang = [], 0.0
    while gesamt - anfang > TEIL_HOECHSTENS_S:
        fenster = [p for p in pausen if anfang + TEIL_MIN_S < (p[0] + p[1]) / 2 <= anfang + TEIL_HOECHSTENS_S]
        schnitt = (lambda p: (p[0] + p[1]) / 2)(max(fenster, key=lambda p: p[1] - p[0])) if fenster \
            else anfang + TEIL_HOECHSTENS_S
        teile.append((anfang, schnitt))
        anfang = schnitt
    teile.append((anfang, gesamt))
    return teile


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
            "start_hinweis": cfg.start_hinweis,
        }

    async def whisper(c: httpx.AsyncClient, wav: bytes, temperatur: str, hoechstens: int) -> str:
        felder = {"model": cfg.modell, "language": cfg.sprache, "temperature": temperatur,
                  "response_format": "json", "max_completion_tokens": str(hoechstens)}
        try:
            antwort = await c.post(
                f"{basis}/audio/transcriptions",
                headers=kopf,
                data=felder,
                files={"file": ("stueck.wav", wav, "audio/wav")},
            )
        except httpx.HTTPError as fehler:
            raise HTTPException(
                502, f"Die Spracherkennung unter {basis} antwortet nicht ({type(fehler).__name__}). "
                f"Starten mit: {cfg.start_hinweis}"
            ) from fehler
        if antwort.status_code != 200:
            raise HTTPException(502, f"Spracherkennung: Fehlercode {antwort.status_code}: {antwort.text[:300]}")
        return (antwort.json().get("text") or "").strip()

    async def transkribieren(c: httpx.AsyncClient, pcm: np.ndarray) -> str:
        sprechzeit = _sprechzeit(pcm)
        if sprechzeit < SPRACHE_MIN_S:
            return ""
        wav = _wav(_angehoben(pcm))
        hoechstens = int(TOKEN_JE_S * len(pcm) / ABTASTRATE) + 10
        text = await whisper(c, wav, "0", hoechstens)
        if _kompression(text) > SCHLEIFE_KOMPRESSION:
            text = await whisper(c, wav, ZWEITE_TEMPERATUR, hoechstens)
        text = _ohne_schleifen(text)
        if STILLE_FLOSKELN.match(text) and sprechzeit < FLOSKEL_SPRECHZEIT_S:
            return ""
        return text

    @router.post("/erkennen")
    async def erkennen(datei: UploadFile = File(...), vorlaeufig: bool = Form(False)) -> dict:
        roh = await datei.read()
        if not roh:
            raise HTTPException(400, "Die Aufnahme ist leer.")
        pcm = await _nach_pcm(roh)
        audio_s = len(pcm) / ABTASTRATE
        teile = _teile(pcm)
        start = time.perf_counter()
        # Alle Teile auf einmal: vLLM rechnet sie im selben Durchgang.
        async with httpx.AsyncClient(timeout=300.0) as c:
            texte = await asyncio.gather(*(
                transkribieren(c, pcm[int(a * ABTASTRATE):int(e * ABTASTRATE)]) for a, e in teile
            ))
        rechen_s = time.perf_counter() - start
        abschnitte = [{"start": round(a, 2), "ende": round(e, 2), "text": t} for (a, e), t in zip(teile, texte) if t]
        text = " ".join(a["text"] for a in abschnitte)
        if vorlaeufig:
            return {"text": text, "audio_s": round(audio_s, 2), "rechen_s": round(rechen_s, 3)}
        # Protokoll in der Konsole: was angekommen ist, falls die Mitschrift seltsam aussieht
        print(f"  Sprache: {audio_s:5.1f} s, {len(teile)} Teil(e), {rechen_s:.2f} s → {text[:160]!r}", flush=True)
        start_s = time.perf_counter()
        vektoren = await stimmabdruecke(_wav(pcm), [[a["start"], a["ende"]] for a in abschnitte])
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
