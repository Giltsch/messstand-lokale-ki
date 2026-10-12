"""FastAPI-App, Start und CLI des Messstands.

Bindet ausschliesslich an 127.0.0.1. Es gibt keinen Schalter, der das aendert.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config as konfig
from .backends import backend_bauen, params_aus_config
from .backends.base import (
    Backend,
    DenkEvent,
    FehlerEvent,
    GenParams,
    MessungEvent,
    TextEvent,
)
from .measure import SPALTEN, Messreihe

HOST = "127.0.0.1"
def _wurzel() -> Path:
    """Projektwurzel finden, auch wenn das Paket installiert liegt."""
    kandidaten = [Path(__file__).resolve().parents[2], Path.cwd()]
    for kandidat in kandidaten:
        if (kandidat / "static" / "index.html").is_file():
            return kandidat
    return kandidaten[0]


WURZEL = _wurzel()
STATIC = WURZEL / "static"
PRESETS = WURZEL / "presets"
RESULTS = WURZEL / "results"
DOCS = WURZEL / "docs"


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------


def schreiben(*teile) -> None:
    """Ausgabe sofort rausschreiben, damit Start-Skripte sie zeigen."""
    print(*teile, flush=True)


def sse(daten: dict) -> str:
    """Ein Server-Sent-Event als Zeile."""
    return "data: " + json.dumps(daten, ensure_ascii=False, default=str) + "\n\n"


SSE_KOPF = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def strom(erzeuger: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(erzeuger, media_type="text/event-stream", headers=SSE_KOPF)


class Zustand:
    """Alles, was der Server zur Laufzeit mit sich herumtraegt."""

    def __init__(self, cfg: konfig.StationConfig) -> None:
        self.cfg = cfg
        self.backends: dict[str, Backend] = {b.id: backend_bauen(b) for b in cfg.backends}
        self.embedding: Backend | None = (
            backend_bauen(cfg.embedding) if cfg.embedding else None
        )
        self.messreihe = Messreihe(station=cfg.stationsschluessel)
        self.verfuegbar: dict[str, list[str]] = {}
        self.online: dict[str, bool] = {}
        self.warm: dict[str, set[str]] = {b.id: set() for b in cfg.backends}
        self.indizes: dict[str, Any] = {}
        self.aufgabenkarte: dict = {}
        self.beispieltext: str = ""

    async def pruefen(self) -> None:
        """Backends anpingen und Modell-Listen holen."""

        async def eines(backend: Backend) -> None:
            self.online[backend.id] = await backend.health()
            self.verfuegbar[backend.id] = (
                await backend.list_models() if self.online[backend.id] else []
            )

        await asyncio.gather(*(eines(b) for b in self.backends.values()))
        if self.embedding is not None:
            self.online["__embedding__"] = await self.embedding.health()
            self.verfuegbar["__embedding__"] = (
                await self.embedding.list_models()
                if self.online["__embedding__"]
                else []
            )

    def modell_vorhanden(self, backend_id: str, modell_id: str) -> bool:
        liste = self.verfuegbar.get(backend_id)
        if not liste:
            return False
        return modell_id in liste or f"{modell_id}:latest" in liste

    def backend_oder_fehler(self, backend_id: str) -> tuple[Backend, konfig.BackendCfg]:
        cfg = self.cfg.backend(backend_id)
        backend = self.backends.get(backend_id)
        if cfg is None or backend is None:
            raise HTTPException(404, f"Unbekanntes Backend: {backend_id}")
        return backend, cfg

    def beschreibung(self) -> dict:
        """Die Konfiguration, wie die Oberflaeche sie braucht."""
        backends = []
        for b in self.cfg.backends:
            backends.append(
                {
                    "id": b.id,
                    "label": b.label,
                    "typ": b.typ,
                    "url": b.url,
                    "online": self.online.get(b.id, False),
                    "modelle": [
                        {
                            **m.model_dump(),
                            "vorhanden": self.modell_vorhanden(b.id, m.id),
                            "warm": m.id in self.warm.get(b.id, set()),
                        }
                        for m in b.modelle
                    ],
                }
            )
        embedding = None
        if self.cfg.embedding:
            embedding = {
                **self.cfg.embedding.model_dump(exclude={"api_key"}),
                "online": self.online.get("__embedding__", False),
                "vorhanden": self.modell_vorhanden(
                    "__embedding__", self.cfg.embedding.modell
                ),
            }
        return {
            "version": __version__,
            "station": self.cfg.station.model_dump(),
            "backends": backends,
            "embedding": embedding,
            "parser": self.cfg.parser,
            "vergleiche": [v.model_dump() for v in self.cfg.vergleiche],
            "lasttest": self.cfg.lasttest.model_dump(),
            "generierung": self.cfg.generierung.model_dump(),
            "aufgabenkarte": self.aufgabenkarte,
            "beispieltext": self.beispieltext,
            "quelle": Path(self.cfg.quelle).name,
        }

    async def aufraeumen(self) -> None:
        for backend in self.backends.values():
            schliessen = getattr(backend, "aclose", None)
            if schliessen:
                await schliessen()
        if self.embedding is not None:
            await self.embedding.aclose()  # type: ignore[attr-defined]


def presets_laden(zustand: Zustand) -> None:
    karte = PRESETS / "aufgabenkarte.yaml"
    text = PRESETS / "beispieltext.md"
    if karte.is_file():
        zustand.aufgabenkarte = yaml.safe_load(karte.read_text(encoding="utf-8")) or {}
    if text.is_file():
        zustand.beispieltext = text.read_text(encoding="utf-8").strip()


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------


def app_bauen(cfg: konfig.StationConfig) -> FastAPI:
    zustand = Zustand(cfg)
    presets_laden(zustand)

    @asynccontextmanager
    async def lebenslauf(app: FastAPI):
        await zustand.pruefen()
        bericht(zustand)
        yield
        await zustand.aufraeumen()

    app = FastAPI(title="Messstand", version=__version__, lifespan=lebenslauf)
    app.state.zustand = zustand

    if STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def startseite() -> FileResponse:
        return FileResponse(
            STATIC / "index.html", headers={"Cache-Control": "no-store"}
        )

    @app.get("/api/station")
    async def station() -> dict:
        return zustand.beschreibung()

    @app.get("/api/status")
    async def status() -> dict:
        await zustand.pruefen()
        return zustand.beschreibung()

    @app.post("/api/warmup")
    async def warmup(rumpf: dict) -> dict:
        backend_id = rumpf.get("backend", "")
        modell_id = rumpf.get("modell", "")
        backend, _cfg = zustand.backend_oder_fehler(backend_id)
        try:
            await backend.warmup(modell_id)
        except Exception as fehler:
            return JSONResponse(
                status_code=200,
                content={
                    "ok": False,
                    "nachricht": f"Modell '{modell_id}' konnte nicht geladen werden.",
                    "detail": f"{type(fehler).__name__}: {fehler}",
                },
            )
        zustand.warm.setdefault(backend_id, set()).add(modell_id)
        return {"ok": True, "nachricht": f"Modell '{modell_id}' ist geladen."}

    @app.post("/api/chat")
    async def chat(rumpf: dict, anfrage: Request) -> StreamingResponse:
        backend_id = rumpf.get("backend", "")
        modell_id = rumpf.get("modell", "")
        backend, backend_cfg = zustand.backend_oder_fehler(backend_id)
        modell_cfg = backend_cfg.modell(modell_id)
        prompt = (rumpf.get("prompt") or "").strip()
        system = (rumpf.get("system") or "").strip()
        reiter = rumpf.get("reiter") or "Aufgabe"
        notiz = rumpf.get("notiz") or ""
        thinking = bool(rumpf.get("thinking", cfg.generierung.thinking))
        if not prompt:
            raise HTTPException(400, "Es wurde kein Text zum Verarbeiten geschickt.")

        nachrichten: list[dict] = []
        if system:
            nachrichten.append({"role": "system", "content": system})
        nachrichten.append({"role": "user", "content": prompt})

        params = params_aus_config(cfg.generierung)
        params.thinking = thinking

        async def erzeugen() -> AsyncIterator[str]:
            yield sse(
                {
                    "art": "start",
                    "backend": backend_id,
                    "modell": modell_id,
                    "warm": modell_id in zustand.warm.get(backend_id, set()),
                }
            )
            async for ereignis in backend.chat_stream(modell_id, nachrichten, params):
                if await anfrage.is_disconnected():
                    break
                if isinstance(ereignis, TextEvent):
                    yield sse({"art": "text", "text": ereignis.text})
                elif isinstance(ereignis, DenkEvent):
                    yield sse({"art": "denken", "text": ereignis.text})
                elif isinstance(ereignis, FehlerEvent):
                    yield sse(
                        {
                            "art": "fehler",
                            "nachricht": ereignis.nachricht,
                            "detail": ereignis.detail,
                        }
                    )
                elif isinstance(ereignis, MessungEvent):
                    zustand.warm.setdefault(backend_id, set()).add(modell_id)
                    ergebnis = zustand.messreihe.hinzufuegen(
                        reiter=reiter,
                        backend_id=backend_id,
                        backend_label=backend_cfg.label,
                        modell_id=modell_id,
                        modell_label=modell_cfg.label if modell_cfg else modell_id,
                        messung=ereignis.messung,
                        notiz=notiz,
                    )
                    yield sse(
                        {
                            "art": "messung",
                            "messung": ereignis.messung.dict(),
                            "ergebnis": ergebnis.fuer_oberflaeche(),
                        }
                    )
            yield sse({"art": "ende"})

        return strom(erzeugen())

    @app.get("/api/ergebnisse")
    async def ergebnisse() -> dict:
        return {
            "spalten": [titel for _, titel in SPALTEN],
            "eintraege": zustand.messreihe.alle(),
            "dateiname": zustand.messreihe.dateiname(),
        }

    @app.post("/api/ergebnisse/csv")
    async def ergebnisse_csv() -> dict:
        if not zustand.messreihe.eintraege:
            return {"ok": False, "nachricht": "Es gibt noch keine Messwerte zum Speichern."}
        ziel = zustand.messreihe.speichern(RESULTS)
        return {"ok": True, "pfad": str(ziel), "nachricht": f"Gespeichert: {ziel}"}

    @app.delete("/api/ergebnisse")
    async def ergebnisse_leeren() -> dict:
        zustand.messreihe.leeren()
        return {"ok": True}

    return app


def bericht(zustand: Zustand) -> None:
    """Kurzer Startbericht auf der Konsole."""
    cfg = zustand.cfg
    schreiben(f"\n  {cfg.station.name} — {cfg.station.geraet}")
    for b in cfg.backends:
        zeichen = "ok  " if zustand.online.get(b.id) else "AUS "
        schreiben(f"  [{zeichen}] {b.label}  ({b.url})")
        for m in b.modelle:
            da = zustand.modell_vorhanden(b.id, m.id)
            schreiben(f"        {'+' if da else '-'} {m.label}" + ("" if da else "  (fehlt)"))
    if cfg.embedding:
        da = zustand.modell_vorhanden("__embedding__", cfg.embedding.modell)
        zeichen = "ok  " if zustand.online.get("__embedding__") else "AUS "
        schreiben(f"  [{zeichen}] Einbettung: {cfg.embedding.modell}" + ("" if da else "  (fehlt)"))
    schreiben()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cli(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(
        prog="messstand", description="Messstand: lokale KI vergleichen."
    )
    zerleger.add_argument(
        "--config",
        "-c",
        required=True,
        help="Pfad zur Stations-YAML, z. B. stations/macmini.yaml",
    )
    zerleger.add_argument("--port", "-p", type=int, default=8765, help="Port (Standard 8765)")
    zerleger.add_argument(
        "--no-browser", action="store_true", help="Browser nicht automatisch oeffnen"
    )
    args = zerleger.parse_args(argv)

    try:
        cfg = konfig.laden(args.config)
    except konfig.KonfigFehler as fehler:
        print(f"\nStart abgebrochen.\n{fehler}\n", file=sys.stderr, flush=True)
        return 2

    import uvicorn

    adresse = f"http://{HOST}:{args.port}/"
    schreiben(f"\n  Messstand {__version__}")
    schreiben(f"  Konfiguration: {args.config}")
    schreiben(f"  Oberflaeche:   {adresse}")

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(adresse)).start()

    uvicorn.run(
        app_bauen(cfg),
        host=HOST,
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
