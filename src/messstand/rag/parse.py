"""PDF-Parser in drei Stufen: naiv, schnell, strukturiert.

Die drei Stufen sind der Kern der Vorfuehrung: dieselbe Datei, drei
Lesarten, sichtbar unterschiedliche Ergebnisse, besonders bei Tabellen.
"""

from __future__ import annotations

import contextlib
import io
import time
from dataclasses import dataclass, field
from pathlib import Path

PARSER_NAMEN = {
    "naiv": "Naiv (pypdf, Rohtext)",
    "schnell": "Schnell (PyMuPDF, Markdown)",
    "strukturiert": "Strukturiert (Docling)",
}


class ParserFehler(RuntimeError):
    """Meldung in Klartext, wenn eine Datei nicht gelesen werden kann."""


@dataclass
class Seite:
    nummer: int
    text: str


@dataclass
class Dokument:
    name: str
    pfad: str
    parser: str
    seiten: list[Seite] = field(default_factory=list)
    markdown: str = ""
    dauer_s: float = 0.0

    @property
    def zeichen(self) -> int:
        return len(self.markdown)


def parser_verfuegbar(parser: str) -> bool:
    """Prueft, ob die noetige Bibliothek installiert ist."""
    try:
        if parser == "naiv":
            import pypdf  # noqa: F401
        elif parser == "schnell":
            import pymupdf4llm  # noqa: F401
        elif parser == "strukturiert":
            import docling  # noqa: F401
        else:
            return False
    except ImportError:
        return False
    return True


def parsen(pfad: str | Path, parser: str) -> Dokument:
    """Liest eine PDF mit dem gewaehlten Parser."""
    p = Path(pfad)
    if not p.is_file():
        raise ParserFehler(f"Die Datei wurde nicht gefunden: {p.name}")
    start = time.perf_counter()
    if parser == "naiv":
        seiten, markdown = _naiv(p)
    elif parser == "schnell":
        seiten, markdown = _schnell(p)
    elif parser == "strukturiert":
        seiten, markdown = _strukturiert(p)
    else:
        raise ParserFehler(f"Unbekannter Parser: {parser}")
    if not markdown.strip():
        raise ParserFehler(
            f"Aus {p.name} konnte mit dem Parser „{PARSER_NAMEN.get(parser, parser)}“ "
            "kein Text gelesen werden. Ist die PDF nur ein Scan ohne Textebene?"
        )
    return Dokument(
        name=p.name,
        pfad=str(p),
        parser=parser,
        seiten=seiten,
        markdown=markdown,
        dauer_s=time.perf_counter() - start,
    )


def _naiv(p: Path) -> tuple[list[Seite], str]:
    """pypdf: nur Rohtext, keine Struktur, Tabellen zerfallen."""
    try:
        from pypdf import PdfReader
    except ImportError as fehler:  # pragma: no cover
        raise ParserFehler("pypdf ist nicht installiert.") from fehler
    leser = PdfReader(str(p))
    seiten = [
        Seite(nummer=i + 1, text=(seite.extract_text() or "").strip())
        for i, seite in enumerate(leser.pages)
    ]
    return seiten, "\n\n".join(s.text for s in seiten if s.text)


def _schnell(p: Path) -> tuple[list[Seite], str]:
    """PyMuPDF: Markdown mit Ueberschriften und einfachen Tabellen."""
    try:
        import pymupdf4llm
    except ImportError as fehler:  # pragma: no cover
        raise ParserFehler("pymupdf4llm ist nicht installiert.") from fehler
    # PyMuPDF schreibt Hinweise auf die Standardausgabe. Die Konsole des
    # Messstands soll im Workshop ruhig bleiben.
    with contextlib.redirect_stdout(io.StringIO()):
        teile = pymupdf4llm.to_markdown(str(p), page_chunks=True)
    seiten: list[Seite] = []
    for i, teil in enumerate(teile):
        text = (teil.get("text") if isinstance(teil, dict) else str(teil)) or ""
        nummer = i + 1
        if isinstance(teil, dict):
            nummer = int((teil.get("metadata") or {}).get("page", nummer) or nummer)
        seiten.append(Seite(nummer=nummer, text=text.strip()))
    return seiten, "\n\n".join(s.text for s in seiten if s.text)


def _strukturiert(p: Path) -> tuple[list[Seite], str]:
    """Docling: erkennt Tabellen als Tabellen. Optionale Abhaengigkeit."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as fehler:
        raise ParserFehler(
            "Der strukturierte Parser braucht Docling. Installation: "
            "uv sync --extra docling"
        ) from fehler
    dokument = DocumentConverter().convert(str(p)).document
    markdown = dokument.export_to_markdown()
    # Docling liefert ein Markdown fuer das ganze Dokument. Die Seitenzahlen
    # kommen aus einem zweiten, schnellen Durchlauf und werden ueber
    # Textvergleich zugeordnet (siehe seiten_zuordnen).
    try:
        seiten, _ = _schnell(p)
    except ParserFehler:
        seiten = []
    return seiten, markdown


def seite_finden(text: str, seiten: list[Seite]) -> int | None:
    """Ordnet einem Textstueck eine Seitenzahl zu, so gut es geht."""
    probe = _normalisieren(text)[:60]
    if not probe or not seiten:
        return None
    for seite in seiten:
        if probe in _normalisieren(seite.text):
            return seite.nummer
    # Zweiter Versuch mit einem kuerzeren Stueck
    kurz = probe[:30]
    for seite in seiten:
        if kurz and kurz in _normalisieren(seite.text):
            return seite.nummer
    return None


def _normalisieren(text: str) -> str:
    return " ".join(text.split()).lower()
