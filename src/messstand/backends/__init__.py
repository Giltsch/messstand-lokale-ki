"""Backends: Laufzeiten, die Modelle bedienen."""

from __future__ import annotations

from ..config import BackendCfg, EmbeddingCfg, GenerierungCfg
from .base import Backend, GenParams, Messung, StreamEvent
from .ollama import OllamaBackend
from .openai_compat import OpenAICompatBackend

__all__ = [
    "Backend",
    "GenParams",
    "Messung",
    "StreamEvent",
    "OllamaBackend",
    "OpenAICompatBackend",
    "backend_bauen",
    "params_aus_config",
]


def backend_bauen(cfg: BackendCfg | EmbeddingCfg) -> Backend:
    """Erzeugt das passende Backend-Objekt zur Konfiguration."""
    if cfg.typ == "ollama":
        return OllamaBackend(cfg)
    if cfg.typ == "openai":
        return OpenAICompatBackend(cfg)
    raise ValueError(f"Unbekannter Backend-Typ: {cfg.typ}")


def params_aus_config(gen: GenerierungCfg, *, im_lasttest: bool = False) -> GenParams:
    return GenParams(
        temperatur=gen.temperatur,
        seed=gen.seed,
        max_tokens=gen.max_tokens,
        num_ctx=gen.num_ctx,
        thinking=gen.thinking,
        timeout_s=gen.timeout_lasttest_s if im_lasttest else gen.timeout_s,
        kalt_schwelle_s=gen.kalt_schwelle_s,
    )
