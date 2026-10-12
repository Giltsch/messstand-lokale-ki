"""Natives Ollama-Backend (/api/chat, /api/embed).

Die nativen Endpunkte liefern Serverzaehler im letzten Chunk
(prompt_eval_count, prompt_eval_duration, eval_count, eval_duration,
load_duration; alle in Nanosekunden). Darum ist hier quelle = "server".
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from .base import (
    Backend,
    DenkEvent,
    FehlerEvent,
    GenParams,
    HttpBackend,
    Messung,
    MessungEvent,
    Stoppuhr,
    StreamEvent,
    TextEvent,
    klartext_fehler,
)

NS = 1_000_000_000


def _tps(anzahl: Any, dauer_ns: Any) -> float | None:
    """Token pro Sekunde aus Zaehler und Nanosekunden-Dauer."""
    try:
        anzahl = int(anzahl)
        dauer_ns = int(dauer_ns)
    except (TypeError, ValueError):
        return None
    if anzahl <= 0 or dauer_ns <= 0:
        return None
    return anzahl / (dauer_ns / NS)


class OllamaBackend(HttpBackend):
    typ = "ollama"

    async def health(self) -> bool:
        try:
            antwort = await self.client.get(f"{self.url}/api/version", timeout=3.0)
            return antwort.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            antwort = await self.client.get(f"{self.url}/api/tags", timeout=10.0)
            antwort.raise_for_status()
            daten = antwort.json()
        except Exception:
            return []
        namen: list[str] = []
        for modell in daten.get("models", []):
            name = modell.get("name") or modell.get("model")
            if name:
                namen.append(name)
                # "modell:latest" soll auch als "modell" gefunden werden
                if name.endswith(":latest"):
                    namen.append(name.removesuffix(":latest"))
        return namen

    async def warmup(self, model: str) -> None:
        """Laedt das Modell und haelt es im Speicher (keep_alive: -1)."""
        antwort = await self.client.post(
            f"{self.url}/api/chat",
            json={"model": model, "messages": [], "keep_alive": -1},
            timeout=httpx.Timeout(10.0, read=600.0, connect=5.0),
        )
        antwort.raise_for_status()

    async def entladen(self, model: str) -> None:
        """Gibt den Speicher wieder frei (keep_alive: 0)."""
        await self.client.post(
            f"{self.url}/api/chat",
            json={"model": model, "messages": [], "keep_alive": 0},
            timeout=30.0,
        )

    def _nutzdaten(
        self, model: str, messages: list[dict], params: GenParams, *, think: bool | None
    ) -> dict:
        nutzdaten: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "options": {
                "temperature": params.temperatur,
                "seed": params.seed,
                "num_predict": params.max_tokens,
                "num_ctx": params.num_ctx,
            },
        }
        if think is not None:
            nutzdaten["think"] = think
        return nutzdaten

    async def chat_stream(
        self, model: str, messages: list[dict], params: GenParams
    ) -> AsyncIterator[StreamEvent]:
        # Manche Modelle kennen das Feld "think" nicht. Dann einmal ohne senden.
        for think in (params.thinking, None):
            versuch_ohne_think = think is None
            fehler_event: FehlerEvent | None = None
            etwas_gesendet = False
            async for ereignis in self._lauf(model, messages, params, think=think):
                if isinstance(ereignis, FehlerEvent) and not etwas_gesendet:
                    fehler_event = ereignis
                    break
                etwas_gesendet = True
                yield ereignis
            if fehler_event is None:
                return
            if versuch_ohne_think or "think" not in fehler_event.detail.lower():
                yield fehler_event
                return

    async def _lauf(
        self,
        model: str,
        messages: list[dict],
        params: GenParams,
        *,
        think: bool | None,
    ) -> AsyncIterator[StreamEvent]:
        uhr = Stoppuhr()
        denk_chunks = 0
        letzte_daten: dict[str, Any] = {}
        try:
            async with self.client.stream(
                "POST",
                f"{self.url}/api/chat",
                json=self._nutzdaten(model, messages, params, think=think),
                timeout=httpx.Timeout(10.0, read=params.timeout_s, connect=5.0),
            ) as antwort:
                if antwort.status_code >= 400:
                    rumpf = (await antwort.aread()).decode("utf-8", "replace")
                    yield FehlerEvent(
                        nachricht=(
                            f"{self.label} hat die Anfrage mit Fehlercode "
                            f"{antwort.status_code} abgelehnt."
                        ),
                        detail=rumpf[:1500],
                    )
                    return
                async for zeile in antwort.aiter_lines():
                    zeile = zeile.strip()
                    if not zeile:
                        continue
                    try:
                        daten = json.loads(zeile)
                    except json.JSONDecodeError:
                        continue
                    if daten.get("error"):
                        yield FehlerEvent(
                            nachricht=f"{self.label} meldet einen Fehler.",
                            detail=str(daten["error"])[:1500],
                        )
                        return
                    nachricht = daten.get("message") or {}
                    denktext = nachricht.get("thinking") or ""
                    if denktext:
                        denk_chunks += 1
                        yield DenkEvent(text=denktext)
                    text = nachricht.get("content") or ""
                    if text:
                        uhr.token()
                        yield TextEvent(text=text)
                    if daten.get("done"):
                        letzte_daten = daten
        except Exception as fehler:  # Transportfehler
            yield klartext_fehler(fehler, self.url, self.label)
            return

        yield MessungEvent(
            messung=self._messung(letzte_daten, uhr, params, denk_chunks)
        )

    def _messung(
        self,
        daten: dict[str, Any],
        uhr: Stoppuhr,
        params: GenParams,
        denk_chunks: int,
    ) -> Messung:
        load_s = (daten.get("load_duration") or 0) / NS or None
        prompt_tokens = daten.get("prompt_eval_count")
        output_tokens = daten.get("eval_count")
        prefill = _tps(prompt_tokens, daten.get("prompt_eval_duration"))
        decode = _tps(output_tokens, daten.get("eval_duration"))
        geschaetzt = False

        # Denktext zaehlt nicht als Antwort. Ohne Chunk-genaue Serverzahlen
        # bleibt nur das Abziehen der Denk-Chunks, darum "geschaetzt".
        if denk_chunks and not params.thinking and isinstance(output_tokens, int):
            output_tokens = max(0, output_tokens - denk_chunks)
            geschaetzt = True

        if prefill is None and prompt_tokens and uhr.ttft_s:
            prefill = prompt_tokens / uhr.ttft_s
            geschaetzt = True
        if decode is None and uhr.decode_s and uhr.tokens > 1:
            decode = (uhr.tokens - 1) / uhr.decode_s
            geschaetzt = True

        hat_serverzahlen = bool(daten.get("eval_duration") or daten.get("prompt_eval_duration"))
        return Messung(
            ttft_s=uhr.ttft_s,
            prefill_tps=prefill,
            decode_tps=decode,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens if output_tokens is not None else uhr.tokens or None,
            total_s=uhr.total_s,
            quelle="server" if hat_serverzahlen else "client",
            kalt=bool(load_s and load_s > params.kalt_schwelle_s),
            load_s=load_s,
            geschaetzt=geschaetzt or not hat_serverzahlen,
            decode_s=(int(daten["eval_duration"]) / NS) if daten.get("eval_duration") else uhr.decode_s,
            denk_tokens=denk_chunks,
        )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        antwort = await self.client.post(
            f"{self.url}/api/embed",
            json={"model": model, "input": texts},
            timeout=httpx.Timeout(10.0, read=300.0, connect=5.0),
        )
        if antwort.status_code == 404:
            # Aeltere Ollama-Versionen kennen nur /api/embeddings (ein Text).
            ergebnis: list[list[float]] = []
            for text in texts:
                einzel = await self.client.post(
                    f"{self.url}/api/embeddings",
                    json={"model": model, "prompt": text},
                    timeout=httpx.Timeout(10.0, read=300.0, connect=5.0),
                )
                einzel.raise_for_status()
                ergebnis.append(einzel.json().get("embedding", []))
            return ergebnis
        antwort.raise_for_status()
        return antwort.json().get("embeddings", [])


_: type[Backend] = OllamaBackend  # Interface-Abgleich
