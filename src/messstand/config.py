"""Laden und Validieren der Stations-Konfiguration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


class ModellCfg(BaseModel):
    id: str
    label: str
    architektur: Literal["dense", "moe"] = "dense"
    parameter_gesamt_mrd: float | None = None
    parameter_aktiv_mrd: float | None = None
    # Belegter Speicher in Gigabyte. Treibt die Vorhersage, wenn zwei Modelle
    # gleich viele aktive Parameter haben, aber unterschiedlich quantisiert
    # sind: je Token muss die ganze Datei einmal gelesen werden.
    groesse_gb: float | None = None


class BackendCfg(BaseModel):
    id: str
    label: str
    typ: Literal["ollama", "openai"]
    url: str
    api_key: str | None = None
    modelle: list[ModellCfg] = Field(default_factory=list)
    # Nur Ollama: so viele GB duerfen geladene Modelle zusammen belegen. Passt
    # ein neues Modell nicht mehr hinein, entlaedt der Messstand vorher die am
    # laengsten nicht benutzten. Ohne Angabe entscheidet Ollama allein.
    speicher_budget_gb: float | None = None

    def modell(self, modell_id: str) -> ModellCfg | None:
        return next((m for m in self.modelle if m.id == modell_id), None)


class StationInfo(BaseModel):
    name: str
    geraet: str
    speicher_gb: float | None = None
    bandbreite_gbs: float | None = None


class EmbeddingCfg(BaseModel):
    typ: Literal["ollama", "openai"] = "ollama"
    url: str
    modell: str
    api_key: str | None = None


class VergleichSeite(BaseModel):
    backend: str
    modell: str


class VergleichCfg(BaseModel):
    name: str
    a: VergleichSeite
    b: VergleichSeite


class LasttestCfg(BaseModel):
    erlaubt: bool = True
    stufen: list[int] = Field(default_factory=lambda: [1, 4, 8, 15])
    standard: int = 4
    hinweis_parallelitaet: str | None = None


class OcrBeispiel(BaseModel):
    """Ein Dokument, das im OCR-Reiter als Schnellwahl erscheint."""

    datei: str  # Dateiname, wie das OCR-Werkzeug ihn kennt
    titel: str
    zeigt: str = ""
    quelle: str = ""  # Herkunft und Lizenz, erscheint unter dem Scan


class OcrCfg(BaseModel):
    """Verbindung zum eigenen OCR-Werkzeug (LawAI), optional."""

    url: str = "http://127.0.0.1:8080"
    # Passwort fuer HTTP Basic. Vorrang hat die Umgebungsvariable
    # LAWAI_PASSWORD, sonst die Zeile LAWAI_PASSWORD=... in dieser Datei.
    passwort_datei: str | None = None
    beispiele: list[OcrBeispiel] = Field(default_factory=list)
    # Am Beamer nur die Beispiele und hier hochgeladene Dateien zeigen, nie
    # den Rest des OCR-Werkzeugs (dort koennen interne Dokumente liegen).
    nur_freigegebene: bool = True


class SpracheCfg(BaseModel):
    """Spracherkennung fuer den Reiter „Sprache", OpenAI-kompatibel (vLLM)."""

    url: str = "http://127.0.0.1:8002/v1"
    modell: str = "openai/whisper-large-v3-turbo"
    label: str = "Whisper large-v3-turbo"
    sprache: str = "de"
    api_key: str | None = None
    # Stimmabdruecke fuer die Sprecherzuordnung (../sprecher_dienst.py), optional.
    sprecher_url: str | None = None


class GenerierungCfg(BaseModel):
    """Faire Vergleichsbedingungen. Gilt fuer alle Backends gleich."""

    temperatur: float = 0.2
    seed: int = 42
    max_tokens: int = 300
    num_ctx: int = 8192
    thinking: bool = False
    timeout_s: float = 120.0
    timeout_lasttest_s: float = 300.0
    kalt_schwelle_s: float = 0.5


class StationConfig(BaseModel):
    station: StationInfo
    backends: list[BackendCfg]
    embedding: EmbeddingCfg | None = None
    parser: list[Literal["naiv", "schnell", "strukturiert"]] = Field(
        default_factory=lambda: ["naiv", "schnell"]
    )
    vergleiche: list[VergleichCfg] = Field(default_factory=list)
    lasttest: LasttestCfg = Field(default_factory=LasttestCfg)
    generierung: GenerierungCfg = Field(default_factory=GenerierungCfg)
    ocr: OcrCfg | None = None
    sprache: SpracheCfg | None = None

    # nicht aus der YAML, sondern vom Laden gesetzt
    quelle: str = ""

    @model_validator(mode="after")
    def _pruefen(self) -> StationConfig:
        if not self.backends:
            raise ValueError("Mindestens ein Backend muss konfiguriert sein.")
        gesehen: set[str] = set()
        for b in self.backends:
            if b.id in gesehen:
                raise ValueError(f"Backend-ID '{b.id}' kommt mehrfach vor.")
            gesehen.add(b.id)
            modell_ids: set[str] = set()
            for m in b.modelle:
                if m.id in modell_ids:
                    raise ValueError(
                        f"Modell '{m.id}' kommt im Backend '{b.id}' mehrfach vor."
                    )
                modell_ids.add(m.id)
        for v in self.vergleiche:
            for seite, name in ((v.a, "a"), (v.b, "b")):
                backend = self.backend(seite.backend)
                if backend is None:
                    raise ValueError(
                        f"Vergleich '{v.name}', Seite {name}: "
                        f"Backend '{seite.backend}' ist nicht konfiguriert."
                    )
                if backend.modell(seite.modell) is None:
                    raise ValueError(
                        f"Vergleich '{v.name}', Seite {name}: Modell "
                        f"'{seite.modell}' fehlt im Backend '{seite.backend}'."
                    )
        if self.lasttest.standard not in self.lasttest.stufen:
            self.lasttest.stufen = sorted({*self.lasttest.stufen, self.lasttest.standard})
        return self

    def backend(self, backend_id: str) -> BackendCfg | None:
        return next((b for b in self.backends if b.id == backend_id), None)

    @property
    def stationsschluessel(self) -> str:
        """Dateinamens-taugliche Kurzform des Stationsnamens."""
        roh = Path(self.quelle).stem if self.quelle else self.station.name
        erlaubt = [z if (z.isalnum() or z in "-_") else "-" for z in roh.lower()]
        return "".join(erlaubt).strip("-") or "station"


class KonfigFehler(RuntimeError):
    """Konfiguration ist unbrauchbar. Meldung ist fuer Menschen gedacht."""


def laden(pfad: str | Path) -> StationConfig:
    p = Path(pfad).expanduser()
    if not p.is_file():
        raise KonfigFehler(f"Konfigurationsdatei nicht gefunden: {p}")
    try:
        rohdaten = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as fehler:
        raise KonfigFehler(f"YAML in {p} ist fehlerhaft:\n{fehler}") from fehler
    if not isinstance(rohdaten, dict):
        raise KonfigFehler(f"{p} enthaelt keine Zuordnung auf oberster Ebene.")
    rohdaten["quelle"] = str(p)
    try:
        return StationConfig.model_validate(rohdaten)
    except ValidationError as fehler:
        zeilen = [
            "  - " + " / ".join(str(t) for t in f["loc"] if t != "quelle") + ": " + f["msg"]
            for f in fehler.errors()
        ]
        raise KonfigFehler(
            f"Konfiguration {p} ist nicht gueltig:\n" + "\n".join(zeilen)
        ) from fehler
