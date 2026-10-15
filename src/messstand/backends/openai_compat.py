"""OpenAI-kompatibles Backend: vLLM, LM Studio, mlx_lm.server, llama.cpp-server.

Diese Server liefern keine Server-Zeitmessung. Alle Tempowerte entstehen
hier clientseitig, darum quelle = "client".
"""

from __future__ import annotations

import json
import re
from contextlib import aclosing
from typing import Any, AsyncIterator

import httpx

from .base import (
    nachrichten_openai,
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

DENK_AUF = re.compile(r"<(think|thinking|reasoning)>", re.IGNORECASE)
DENK_ZU = re.compile(r"</(think|thinking|reasoning)>", re.IGNORECASE)


class DenkFilter:
    """Trennt <think>-Bloecke aus einem Textstrom heraus.

    Puffert nur so viel, wie ein halb angekommenes Tag lang sein kann.
    Gibt (sichtbarer_text, denktext) je Happen zurueck.
    """

    def __init__(self) -> None:
        self.puffer = ""
        self.im_denken = False

    def schieben(self, stueck: str) -> tuple[str, str]:
        self.puffer += stueck
        sichtbar: list[str] = []
        denken: list[str] = []
        while self.puffer:
            muster = DENK_ZU if self.im_denken else DENK_AUF
            treffer = muster.search(self.puffer)
            if treffer:
                vorne = self.puffer[: treffer.start()]
                (denken if self.im_denken else sichtbar).append(vorne)
                self.puffer = self.puffer[treffer.end() :]
                self.im_denken = not self.im_denken
                continue
            # Kein Tag gefunden: ein moeglicher Tag-Anfang am Ende bleibt im Puffer.
            schnitt = len(self.puffer)
            offen = self.puffer.rfind("<")
            if offen != -1 and len(self.puffer) - offen <= 12:
                schnitt = offen
            (denken if self.im_denken else sichtbar).append(self.puffer[:schnitt])
            self.puffer = self.puffer[schnitt:]
            break
        return "".join(sichtbar), "".join(denken)

    def rest(self) -> tuple[str, str]:
        rest, self.puffer = self.puffer, ""
        return ("", rest) if self.im_denken else (rest, "")


class OpenAICompatBackend(HttpBackend):
    typ = "openai"

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        if not self.url.endswith("/v1"):
            self.url = f"{self.url}/v1"

    async def health(self) -> bool:
        try:
            antwort = await self.client.get(f"{self.url}/models", timeout=3.0)
            return antwort.status_code < 500
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            antwort = await self.client.get(f"{self.url}/models", timeout=10.0)
            antwort.raise_for_status()
            daten = antwort.json()
        except Exception:
            return []
        return [m.get("id") for m in daten.get("data", []) if m.get("id")]

    async def warmup(self, model: str, params: GenParams | None = None) -> None:
        """Kein Standardendpunkt. Eine kurze Anfrage laedt das Modell.

        Die Kontextlaenge legt bei diesen Servern der Server selbst fest.
        """
        antwort = await self.client.post(
            f"{self.url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Hallo"}],
                "max_tokens": 1,
                "stream": False,
            },
            timeout=httpx.Timeout(10.0, read=600.0, connect=5.0),
        )
        antwort.raise_for_status()

    def _nutzdaten(
        self,
        model: str,
        messages: list[dict],
        params: GenParams,
        *,
        mit_template_kwargs: bool,
    ) -> dict:
        nutzdaten: dict[str, Any] = {
            "model": model,
            "messages": nachrichten_openai(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": params.temperatur,
            "seed": params.seed,
            "max_tokens": params.max_tokens,
        }
        if mit_template_kwargs and not params.thinking:
            # vLLM und einige llama.cpp-Builds schalten Denkschritte so ab.
            nutzdaten["chat_template_kwargs"] = {"enable_thinking": False}
        return nutzdaten

    async def chat_stream(
        self, model: str, messages: list[dict], params: GenParams
    ) -> AsyncIterator[StreamEvent]:
        # Nicht jeder Server kennt chat_template_kwargs. Bei Ablehnung ohne senden.
        for mit_kwargs in (not params.thinking, False):
            fehler_event: FehlerEvent | None = None
            etwas_gesendet = False
            async with aclosing(
                self._lauf(model, messages, params, mit_template_kwargs=mit_kwargs)
            ) as ereignisse:
                async for ereignis in ereignisse:
                    if isinstance(ereignis, FehlerEvent) and not etwas_gesendet:
                        fehler_event = ereignis
                        break
                    etwas_gesendet = True
                    yield ereignis
            if fehler_event is None:
                return
            if not mit_kwargs:
                yield fehler_event
                return

    async def _lauf(
        self,
        model: str,
        messages: list[dict],
        params: GenParams,
        *,
        mit_template_kwargs: bool,
    ) -> AsyncIterator[StreamEvent]:
        uhr = Stoppuhr()
        filter_ = DenkFilter()
        denk_chunks = 0
        usage: dict[str, Any] = {}
        try:
            async with self.client.stream(
                "POST",
                f"{self.url}/chat/completions",
                json=self._nutzdaten(
                    model, messages, params, mit_template_kwargs=mit_template_kwargs
                ),
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
                    if not zeile.startswith("data:"):
                        continue
                    rumpf = zeile[5:].strip()
                    if rumpf == "[DONE]":
                        break
                    try:
                        daten = json.loads(rumpf)
                    except json.JSONDecodeError:
                        continue
                    if daten.get("usage"):
                        usage = daten["usage"]
                    wahlen = daten.get("choices") or []
                    if not wahlen:
                        continue
                    delta = wahlen[0].get("delta") or {}
                    denktext = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if denktext:
                        denk_chunks += 1
                        yield DenkEvent(text=denktext)
                    inhalt = delta.get("content") or ""
                    if inhalt:
                        sichtbar, denken = filter_.schieben(inhalt)
                        if denken:
                            denk_chunks += 1
                            yield DenkEvent(text=denken)
                        if sichtbar:
                            uhr.token()
                            yield TextEvent(text=sichtbar)
                sichtbar, denken = filter_.rest()
                if denken:
                    yield DenkEvent(text=denken)
                if sichtbar:
                    uhr.token()
                    yield TextEvent(text=sichtbar)
        except Exception as fehler:
            yield klartext_fehler(fehler, self.url, self.label)
            return

        yield MessungEvent(messung=self._messung(usage, uhr, denk_chunks))

    def _messung(self, usage: dict, uhr: Stoppuhr, denk_chunks: int) -> Messung:
        prompt_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        geschaetzt = not bool(usage)
        if output_tokens is None:
            # Ohne usage: Delta-Chunks zaehlen. In der Oberflaeche "geschaetzt".
            output_tokens = uhr.tokens or None
            geschaetzt = True
        elif denk_chunks:
            output_tokens = max(0, int(output_tokens) - denk_chunks)
            geschaetzt = True

        decode = None
        if uhr.decode_s and output_tokens and output_tokens > 1:
            decode = (output_tokens - 1) / uhr.decode_s
        elif uhr.decode_s and uhr.tokens > 1:
            decode = (uhr.tokens - 1) / uhr.decode_s
        prefill = None
        if prompt_tokens and uhr.ttft_s:
            prefill = prompt_tokens / uhr.ttft_s

        return Messung(
            ttft_s=uhr.ttft_s,
            prefill_tps=prefill,
            decode_tps=decode,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_s=uhr.total_s,
            quelle="client",
            kalt=False,
            load_s=None,
            geschaetzt=geschaetzt,
            decode_s=uhr.decode_s,
            denk_tokens=denk_chunks,
        )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        antwort = await self.client.post(
            f"{self.url}/embeddings",
            json={"model": model, "input": texts},
            timeout=httpx.Timeout(10.0, read=300.0, connect=5.0),
        )
        antwort.raise_for_status()
        daten = antwort.json().get("data", [])
        return [eintrag.get("embedding", []) for eintrag in daten]


_: type[Backend] = OpenAICompatBackend  # Interface-Abgleich
