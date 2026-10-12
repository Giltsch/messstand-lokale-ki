"""Lasttest: mehrere Anfragen gleichzeitig an dieselbe Laufzeit.

Jede Bahn ist eine eigene Anfrage mit leicht abgewandeltem Prompt, damit
kein Prefix-Cache das Ergebnis schoent. Alle Bahnen teilen sich den
httpx-Client des Backends.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import aclosing
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, AsyncIterator

from .backends.base import (
    Backend,
    FehlerEvent,
    GenParams,
    Messung,
    MessungEvent,
    TextEvent,
)


@dataclass
class Bahn:
    nr: int
    tokens: int = 0
    messung: Messung | None = None
    fehler: str | None = None
    fertig_s: float | None = None


@dataclass
class Lastergebnis:
    parallel: int
    wanduhr_s: float
    gesamt_tokens: int
    durchsatz_tps: float
    ttft_mittel_s: float | None
    ttft_schlechtester_s: float | None
    fertige_bahnen: int
    fehler: list[str] = field(default_factory=list)

    @property
    def satz(self) -> str:
        """Ein Satz in Klartext fuer die Leinwand."""
        wartezeit = (
            f"im Schnitt {_de(self.ttft_mittel_s, 1)} Sekunden Wartezeit"
            if self.ttft_mittel_s is not None
            else "keine Wartezeit messbar"
        )
        if self.parallel == 1:
            return (
                f"Eine einzelne Anfrage: {wartezeit}, "
                f"{_de(self.durchsatz_tps, 0)} Token pro Sekunde."
            )
        return (
            f"{self.parallel} gleichzeitige Nutzer: {wartezeit}, "
            f"{_de(self.durchsatz_tps, 0)} Token pro Sekunde für alle zusammen."
        )

    def dict(self) -> dict:
        return {
            "parallel": self.parallel,
            "wanduhr_s": self.wanduhr_s,
            "gesamt_tokens": self.gesamt_tokens,
            "durchsatz_tps": self.durchsatz_tps,
            "ttft_mittel_s": self.ttft_mittel_s,
            "ttft_schlechtester_s": self.ttft_schlechtester_s,
            "fertige_bahnen": self.fertige_bahnen,
            "fehler": self.fehler,
            "satz": self.satz,
        }


def _de(wert: float | None, stellen: int) -> str:
    if wert is None:
        return "–"
    return f"{wert:.{stellen}f}".replace(".", ",")


def prompt_fuer_bahn(vorlage: str, nr: int) -> str:
    """Nummer in den Text, damit jede Bahn einen eigenen Prompt hat."""
    return f"Anfrage Nummer {nr}. {vorlage}"


# Aufraeumarbeiten laufen eigenstaendig weiter, darum Verweise halten.
_nachraeumer: set[asyncio.Task] = set()


async def _nachraeumen(aufgaben: list[asyncio.Task], frist_s: float = 15.0) -> None:
    """Wartet, bis die Bahnen von selbst aufhoeren, und bricht Reste ab.

    Laeuft als eigene Aufgabe, damit das Aufraeumen nicht von genau der
    Cancellation unterbrochen wird, die es ausgeloest hat.
    """
    try:
        await asyncio.wait_for(
            asyncio.gather(*aufgaben, return_exceptions=True), frist_s
        )
    except (TimeoutError, asyncio.TimeoutError):
        for aufgabe in aufgaben:
            aufgabe.cancel()
        await asyncio.gather(*aufgaben, return_exceptions=True)


async def lasttest(
    backend: Backend,
    modell: str,
    vorlage: str,
    parallel: int,
    params: GenParams,
    system: str = "",
) -> AsyncIterator[dict]:
    """Fuehrt den Lasttest aus und meldet den Fortschritt je Bahn."""
    bahnen: dict[int, Bahn] = {nr: Bahn(nr=nr) for nr in range(1, parallel + 1)}
    schlange: asyncio.Queue[dict | None] = asyncio.Queue()
    halt = asyncio.Event()
    start = time.perf_counter()

    async def eine_bahn(nr: int) -> None:
        bahn = bahnen[nr]
        nachrichten: list[dict] = []
        if system:
            nachrichten.append({"role": "system", "content": system})
        nachrichten.append({"role": "user", "content": prompt_fuer_bahn(vorlage, nr)})
        try:
            async with aclosing(
                backend.chat_stream(modell, nachrichten, params)
            ) as ereignisse:
                async for ereignis in ereignisse:
                    # Abbruch: regulaer aussteigen, damit die Verbindung zur
                    # Laufzeit sauber geschlossen wird und sie zu rechnen aufhoert.
                    if halt.is_set():
                        break
                    if isinstance(ereignis, TextEvent):
                        bahn.tokens += 1
                        await schlange.put({"art": "bahn", "nr": nr, "tokens": bahn.tokens})
                    elif isinstance(ereignis, MessungEvent):
                        bahn.messung = ereignis.messung
                        bahn.fertig_s = time.perf_counter() - start
                        await schlange.put(
                            {
                                "art": "bahn_fertig",
                                "nr": nr,
                                "tokens": bahn.tokens,
                                "messung": ereignis.messung.dict(),
                            }
                        )
                    elif isinstance(ereignis, FehlerEvent):
                        bahn.fehler = ereignis.nachricht
                        await schlange.put(
                            {
                                "art": "bahn_fehler",
                                "nr": nr,
                                "nachricht": ereignis.nachricht,
                                "detail": ereignis.detail,
                            }
                        )
        except asyncio.CancelledError:
            raise
        except Exception as fehler:  # pragma: no cover - Sicherheitsnetz
            bahn.fehler = str(fehler)
            await schlange.put(
                {
                    "art": "bahn_fehler",
                    "nr": nr,
                    "nachricht": "Diese Bahn ist unerwartet gescheitert.",
                    "detail": f"{type(fehler).__name__}: {fehler}",
                }
            )

    aufgaben = [asyncio.create_task(eine_bahn(nr)) for nr in bahnen]

    async def abwarten() -> None:
        await asyncio.gather(*aufgaben, return_exceptions=True)
        await schlange.put(None)

    waechter = asyncio.create_task(abwarten())
    fertig = False
    yield {"art": "start", "parallel": parallel, "bahnen": list(bahnen)}

    try:
        while True:
            eintrag = await schlange.get()
            if eintrag is None:
                break
            yield eintrag
        fertig = True
    finally:
        if not fertig:
            # Der Browser hat abgebrochen. Bahnen anhalten und im Hintergrund
            # abwarten: hier darf nicht gewartet werden, weil dieser Pfad selbst
            # unter Cancellation laeuft.
            halt.set()
            waechter.cancel()
            nachraeumer = asyncio.create_task(_nachraeumen(aufgaben))
            _nachraeumer.add(nachraeumer)
            nachraeumer.add_done_callback(_nachraeumer.discard)

    yield {"art": "ergebnis", "ergebnis": auswerten(bahnen, parallel, start).dict()}


def auswerten(bahnen: dict[int, Bahn], parallel: int, start: float) -> Lastergebnis:
    fertige = [b for b in bahnen.values() if b.messung is not None]
    wanduhr = max((b.fertig_s or 0) for b in bahnen.values()) if bahnen else 0.0
    if wanduhr <= 0:
        wanduhr = time.perf_counter() - start
    gesamt_tokens = sum(
        (b.messung.output_tokens if b.messung and b.messung.output_tokens else b.tokens)
        for b in bahnen.values()
    )
    ttfts = [b.messung.ttft_s for b in fertige if b.messung and b.messung.ttft_s is not None]
    return Lastergebnis(
        parallel=parallel,
        wanduhr_s=wanduhr,
        gesamt_tokens=gesamt_tokens,
        durchsatz_tps=(gesamt_tokens / wanduhr) if wanduhr > 0 else 0.0,
        ttft_mittel_s=mean(ttfts) if ttfts else None,
        ttft_schlechtester_s=max(ttfts) if ttfts else None,
        fertige_bahnen=len(fertige),
        fehler=[b.fehler for b in bahnen.values() if b.fehler],
    )


def sammelmessung(daten: dict[str, Any]) -> Messung:
    """Eine Zeile fuer die Ergebnistabelle: der Lasttest als Ganzes.

    Schreibtempo ist hier der Gesamtdurchsatz aller Bahnen, Zeit bis zum
    ersten Wort der Mittelwert ueber die Bahnen.
    """
    return Messung(
        ttft_s=daten.get("ttft_mittel_s"),
        prefill_tps=None,
        decode_tps=daten.get("durchsatz_tps"),
        prompt_tokens=None,
        output_tokens=daten.get("gesamt_tokens"),
        total_s=daten.get("wanduhr_s"),
        quelle="client",
        kalt=False,
        geschaetzt=False,
    )
