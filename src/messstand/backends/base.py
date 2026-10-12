"""Gemeinsames Interface aller Backends plus Messdatenklasse."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable

import httpx


@dataclass(slots=True)
class GenParams:
    """Faire Vergleichsbedingungen. Fuer alle Backends identisch gesetzt."""

    temperatur: float = 0.2
    seed: int = 42
    max_tokens: int = 300
    num_ctx: int = 8192
    thinking: bool = False
    timeout_s: float = 120.0
    kalt_schwelle_s: float = 0.5


@dataclass
class Messung:
    """Messwerte einer einzelnen Anfrage."""

    ttft_s: float | None = None
    prefill_tps: float | None = None
    decode_tps: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    total_s: float | None = None
    quelle: str = "client"
    kalt: bool = False
    load_s: float | None = None
    geschaetzt: bool = False
    decode_s: float | None = None
    denk_tokens: int = 0
    abgebrochen: bool = False

    def dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TextEvent:
    """Ein sichtbares Stueck Antworttext."""

    text: str
    art: str = field(default="text", init=False)


@dataclass(slots=True)
class DenkEvent:
    """Denkschritte des Modells. Zaehlen nicht als Antworttext."""

    text: str
    art: str = field(default="denken", init=False)


@dataclass(slots=True)
class MessungEvent:
    """Abschliessendes Messergebnis."""

    messung: Messung
    art: str = field(default="messung", init=False)


@dataclass(slots=True)
class FehlerEvent:
    """Klartextfehler plus technisches Detail zum Aufklappen."""

    nachricht: str
    detail: str = ""
    art: str = field(default="fehler", init=False)


StreamEvent = TextEvent | DenkEvent | MessungEvent | FehlerEvent


@runtime_checkable
class Backend(Protocol):
    id: str
    label: str
    typ: str

    async def health(self) -> bool: ...

    async def list_models(self) -> list[str]: ...

    async def warmup(self, model: str, params: GenParams | None = None) -> None: ...

    def chat_stream(
        self, model: str, messages: list[dict], params: GenParams
    ) -> AsyncIterator[StreamEvent]: ...

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]: ...


class Stoppuhr:
    """Clientseitige Zeitmessung: Start, erstes Token, letztes Token."""

    def __init__(self) -> None:
        self.start = time.perf_counter()
        self.erstes: float | None = None
        self.letztes: float | None = None
        self.tokens = 0

    def token(self) -> None:
        jetzt = time.perf_counter()
        if self.erstes is None:
            self.erstes = jetzt
        self.letztes = jetzt
        self.tokens += 1

    @property
    def ttft_s(self) -> float | None:
        return None if self.erstes is None else self.erstes - self.start

    @property
    def decode_s(self) -> float | None:
        if self.erstes is None or self.letztes is None:
            return None
        spanne = self.letztes - self.erstes
        return spanne if spanne > 0 else None

    @property
    def total_s(self) -> float:
        return time.perf_counter() - self.start


def klartext_fehler(fehler: Exception, url: str, label: str) -> FehlerEvent:
    """Uebersetzt Transportfehler in einen Satz, den Teilnehmende verstehen."""
    detail = f"{type(fehler).__name__}: {fehler}"
    if isinstance(fehler, httpx.ConnectError):
        nachricht = (
            f"{label} ist nicht erreichbar. Laeuft der Dienst unter {url}?"
        )
    elif isinstance(fehler, httpx.ReadTimeout | httpx.ConnectTimeout | httpx.WriteTimeout):
        nachricht = f"{label} hat zu lange gebraucht und wurde abgebrochen."
    elif isinstance(fehler, httpx.HTTPStatusError):
        nachricht = (
            f"{label} hat die Anfrage mit Fehlercode "
            f"{fehler.response.status_code} abgelehnt."
        )
        try:
            detail += "\n" + fehler.response.text[:1500]
        except Exception:  # pragma: no cover - Antwort schon geschlossen
            pass
    else:
        nachricht = f"{label}: unerwarteter Fehler."
    return FehlerEvent(nachricht=nachricht, detail=detail)


class HttpBackend:
    """Basis mit gemeinsam genutztem httpx-Client."""

    typ = "http"

    def __init__(self, cfg) -> None:  # cfg: BackendCfg | EmbeddingCfg
        self.cfg = cfg
        self.id = getattr(cfg, "id", "embedding")
        self.label = getattr(cfg, "label", "Einbettung")
        self.url = str(cfg.url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, read=600.0, write=30.0, connect=5.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=32),
                headers=self._headers(),
                trust_env=False,
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        kopf = {"Content-Type": "application/json"}
        schluessel = getattr(self.cfg, "api_key", None)
        if schluessel:
            kopf["Authorization"] = f"Bearer {schluessel}"
        return kopf

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
