"""Ergebnisobjekte, Sitzungsspeicher und CSV-Export."""

from __future__ import annotations

import csv
import io
import itertools
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .backends.base import Messung

SPALTEN: list[tuple[str, str]] = [
    ("nr", "Nr"),
    ("zeitpunkt", "Zeit"),
    ("reiter", "Reiter"),
    ("backend_label", "Laufzeit"),
    ("modell_label", "Modell"),
    ("ttft_s", "Zeit bis zum ersten Wort (s)"),
    ("prefill_tps", "Lesetempo (Token/s)"),
    ("decode_tps", "Schreibtempo (Token/s)"),
    ("prompt_tokens", "Token rein"),
    ("output_tokens", "Token raus"),
    ("total_s", "Gesamtzeit (s)"),
    ("temperatur", "Zustand"),
    ("quelle", "Quelle"),
    ("notiz", "Notiz"),
    ("backend_id", "Laufzeit-ID"),
    ("modell_id", "Modell-ID"),
]


def _zahl_deutsch(wert: object) -> str:
    """Dezimalkomma, damit Excel in deutscher Einstellung rechnen kann."""
    if wert is None:
        return ""
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, float):
        return f"{wert:.3f}".replace(".", ",")
    return str(wert)


@dataclass
class Ergebnis:
    nr: int
    zeitpunkt: str
    reiter: str
    backend_id: str
    backend_label: str
    modell_id: str
    modell_label: str
    messung: Messung
    notiz: str = ""

    def flach(self) -> dict:
        daten = {
            "nr": self.nr,
            "zeitpunkt": self.zeitpunkt,
            "reiter": self.reiter,
            "backend_id": self.backend_id,
            "backend_label": self.backend_label,
            "modell_id": self.modell_id,
            "modell_label": self.modell_label,
            "notiz": self.notiz,
            "temperatur": "kalt" if self.messung.kalt else "warm",
            **self.messung.dict(),
        }
        return daten

    def fuer_oberflaeche(self) -> dict:
        daten = self.flach()
        daten["messung"] = self.messung.dict()
        return daten


@dataclass
class Messreihe:
    """Alle Messungen dieser Sitzung. Bewusst nur im Speicher."""

    station: str = "station"
    _zaehler: itertools.count = field(default_factory=lambda: itertools.count(1))
    eintraege: list[Ergebnis] = field(default_factory=list)

    def hinzufuegen(
        self,
        *,
        reiter: str,
        backend_id: str,
        backend_label: str,
        modell_id: str,
        modell_label: str,
        messung: Messung,
        notiz: str = "",
    ) -> Ergebnis:
        ergebnis = Ergebnis(
            nr=next(self._zaehler),
            zeitpunkt=datetime.now().strftime("%H:%M:%S"),
            reiter=reiter,
            backend_id=backend_id,
            backend_label=backend_label,
            modell_id=modell_id,
            modell_label=modell_label,
            messung=messung,
            notiz=notiz,
        )
        self.eintraege.append(ergebnis)
        return ergebnis

    def alle(self) -> list[dict]:
        return [e.fuer_oberflaeche() for e in self.eintraege]

    def leeren(self) -> None:
        self.eintraege.clear()
        self._zaehler = itertools.count(1)

    def csv_text(self) -> str:
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
        schreiber.writerow([titel for _, titel in SPALTEN])
        for eintrag in self.eintraege:
            daten = eintrag.flach()
            schreiber.writerow([_zahl_deutsch(daten.get(schluessel)) for schluessel, _ in SPALTEN])
        return puffer.getvalue()

    def dateiname(self) -> str:
        return f"{self.station}_{datetime.now():%Y-%m-%d}.csv"

    def speichern(self, verzeichnis: Path) -> Path:
        verzeichnis.mkdir(parents=True, exist_ok=True)
        ziel = verzeichnis / self.dateiname()
        # BOM, damit Excel die Umlaute richtig liest.
        ziel.write_text(self.csv_text(), encoding="utf-8-sig")
        return ziel
