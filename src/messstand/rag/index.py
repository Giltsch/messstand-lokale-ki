"""Einbettungen und Aehnlichkeitssuche im Speicher (numpy)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..backends.base import Backend
from .chunk import Abschnitt


class IndexFehler(RuntimeError):
    """Meldung in Klartext, wenn das Einbetten scheitert."""


@dataclass
class Treffer:
    abschnitt: Abschnitt
    aehnlichkeit: float

    def dict(self) -> dict:
        return {**self.abschnitt.dict(), "aehnlichkeit": self.aehnlichkeit}


@dataclass
class Index:
    id: str
    datei: str
    parser: str
    abschnitte: list[Abschnitt]
    vektoren: np.ndarray
    modell: str = ""
    dauer_s: float = 0.0
    seiten: int = 0
    markdown: str = ""
    parse_dauer_s: float = 0.0

    async def suchen(
        self, backend: Backend, frage: str, top: int = 4
    ) -> list[Treffer]:
        vektor = (await backend.embed(self.modell, [frage]))[0]
        if not vektor:
            raise IndexFehler("Das Einbettungsmodell hat keinen Vektor geliefert.")
        frage_vektor = _normieren(np.asarray(vektor, dtype=np.float32)[None, :])
        aehnlichkeiten = (self.vektoren @ frage_vektor.T).ravel()
        beste = np.argsort(-aehnlichkeiten)[:top]
        return [
            Treffer(abschnitt=self.abschnitte[i], aehnlichkeit=float(aehnlichkeiten[i]))
            for i in beste
        ]

    def kopf(self) -> dict:
        """Kurzbeschreibung fuer die Oberflaeche."""
        tabellen = sum(1 for a in self.abschnitte if a.ist_tabelle)
        return {
            "id": self.id,
            "datei": self.datei,
            "parser": self.parser,
            "abschnitte": len(self.abschnitte),
            "tabellen_abschnitte": tabellen,
            "seiten": self.seiten,
            "zeichen": len(self.markdown),
            "modell": self.modell,
            "parse_dauer_s": self.parse_dauer_s,
            "einbetten_dauer_s": self.dauer_s,
            "erste_tabelle": self.erste_tabelle(),
        }

    def erste_tabelle(self) -> str:
        """Markdown der ersten erkannten Tabelle, fuer den Parser-Vergleich."""
        zeilen = [z for z in self.markdown.splitlines()]
        gesammelt: list[str] = []
        for zeile in zeilen:
            if zeile.lstrip().startswith("|"):
                gesammelt.append(zeile)
            elif gesammelt:
                break
        if gesammelt:
            return "\n".join(gesammelt[:14])
        # Kein Markdown-Tabellenblock gefunden: Anfang des Textes zeigen.
        return "\n".join(z for z in zeilen if z.strip())[:600]


def _normieren(matrix: np.ndarray) -> np.ndarray:
    laengen = np.linalg.norm(matrix, axis=1, keepdims=True)
    laengen[laengen == 0] = 1.0
    return matrix / laengen


async def index_bauen(
    backend: Backend,
    modell: str,
    abschnitte: list[Abschnitt],
    *,
    id: str,
    datei: str,
    parser: str,
    seiten: int,
    markdown: str,
    parse_dauer_s: float,
    stapel: int = 32,
) -> Index:
    """Bettet alle Abschnitte ein und baut den Index im Speicher."""
    if not abschnitte:
        raise IndexFehler("Das Dokument enthält keine Abschnitte zum Einbetten.")
    start = time.perf_counter()
    vektoren: list[list[float]] = []
    for i in range(0, len(abschnitte), stapel):
        teil = [a.text for a in abschnitte[i : i + stapel]]
        try:
            antwort = await backend.embed(modell, teil)
        except Exception as fehler:
            raise IndexFehler(
                f"Das Einbettungsmodell „{modell}“ hat die Anfrage nicht "
                f"beantwortet: {type(fehler).__name__}"
            ) from fehler
        if len(antwort) != len(teil):
            raise IndexFehler(
                "Das Einbettungsmodell hat weniger Vektoren geliefert als "
                "Abschnitte geschickt wurden."
            )
        vektoren.extend(antwort)
    matrix = _normieren(np.asarray(vektoren, dtype=np.float32))
    return Index(
        id=id,
        datei=datei,
        parser=parser,
        abschnitte=abschnitte,
        vektoren=matrix,
        modell=modell,
        dauer_s=time.perf_counter() - start,
        seiten=seiten,
        markdown=markdown,
        parse_dauer_s=parse_dauer_s,
    )
