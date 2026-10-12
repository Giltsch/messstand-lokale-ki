"""Dokumente: parsen, zerlegen, einbetten, durchsuchen."""

from .chunk import Abschnitt, zerlegen
from .index import Index, index_bauen
from .parse import Dokument, ParserFehler, Seite, parsen, parser_verfuegbar

__all__ = [
    "Abschnitt",
    "Dokument",
    "Index",
    "ParserFehler",
    "Seite",
    "index_bauen",
    "parsen",
    "parser_verfuegbar",
    "zerlegen",
]
