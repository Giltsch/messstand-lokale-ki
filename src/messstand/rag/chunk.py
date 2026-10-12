"""Zerlegen in Abschnitte von etwa 800 Zeichen mit 100 Zeichen Ueberlappung.

Absatz- und Tabellengrenzen werden eingehalten: eine Tabelle wird nie
auseinandergeschnitten, sonst wird die Antwort auf eine Tabellenfrage falsch.
"""

from __future__ import annotations

from dataclasses import dataclass

ZIEL = 800
UEBERLAPPUNG = 100


@dataclass
class Abschnitt:
    nr: int
    text: str
    seite: int | None = None
    ist_tabelle: bool = False

    def dict(self) -> dict:
        return {
            "nr": self.nr,
            "text": self.text,
            "seite": self.seite,
            "ist_tabelle": self.ist_tabelle,
        }


def bloecke_bilden(markdown: str) -> list[tuple[str, bool]]:
    """Teilt Markdown in Bloecke. Zweiter Wert sagt, ob es eine Tabelle ist."""
    bloecke: list[tuple[str, bool]] = []
    tabelle: list[str] = []
    absatz: list[str] = []

    def absatz_abschliessen() -> None:
        if absatz:
            text = "\n".join(absatz).strip()
            if text:
                bloecke.append((text, False))
            absatz.clear()

    def tabelle_abschliessen() -> None:
        if tabelle:
            text = "\n".join(tabelle).strip()
            if text:
                bloecke.append((text, True))
            tabelle.clear()

    for zeile in markdown.splitlines():
        ist_tabellenzeile = zeile.lstrip().startswith("|")
        if ist_tabellenzeile:
            absatz_abschliessen()
            tabelle.append(zeile)
            continue
        tabelle_abschliessen()
        if not zeile.strip():
            absatz_abschliessen()
        else:
            absatz.append(zeile)
    absatz_abschliessen()
    tabelle_abschliessen()
    return bloecke


def zerlegen(
    markdown: str,
    seiten: list | None = None,
    ziel: int = ZIEL,
    ueberlappung: int = UEBERLAPPUNG,
) -> list[Abschnitt]:
    """Baut Abschnitte aus dem Markdown, Tabellen bleiben zusammen."""
    from .parse import seite_finden

    bloecke = bloecke_bilden(markdown)
    abschnitte: list[Abschnitt] = []
    laufend: list[str] = []
    laufend_tabelle = False

    def abschliessen() -> None:
        nonlocal laufend, laufend_tabelle
        text = "\n\n".join(laufend).strip()
        if not text:
            laufend, laufend_tabelle = [], False
            return
        abschnitte.append(
            Abschnitt(
                nr=len(abschnitte) + 1,
                text=text,
                seite=seite_finden(text, seiten or []),
                ist_tabelle=laufend_tabelle,
            )
        )
        # Ueberlappung: das Ende des Abschnitts beginnt den naechsten.
        schwanz = text[-ueberlappung:] if ueberlappung > 0 else ""
        laufend = [schwanz.strip()] if schwanz.strip() else []
        laufend_tabelle = False

    for text, ist_tabelle in bloecke:
        laenge = sum(len(t) for t in laufend) + len(text)
        if laufend and laenge > ziel:
            abschliessen()
        if len(text) > ziel and not ist_tabelle:
            # Sehr langer Absatz: an Satzgrenzen aufteilen.
            for stueck in _saetze_stapeln(text, ziel):
                if laufend and sum(len(t) for t in laufend) + len(stueck) > ziel:
                    abschliessen()
                laufend.append(stueck)
            continue
        laufend.append(text)
        laufend_tabelle = laufend_tabelle or ist_tabelle
        if sum(len(t) for t in laufend) >= ziel:
            abschliessen()
    abschliessen()
    return [a for a in abschnitte if a.text.strip()]


def _saetze_stapeln(text: str, ziel: int) -> list[str]:
    """Teilt einen zu langen Absatz an Satzgrenzen."""
    stuecke: list[str] = []
    rest = text
    while len(rest) > ziel:
        schnitt = max(
            rest.rfind(". ", 0, ziel),
            rest.rfind("! ", 0, ziel),
            rest.rfind("? ", 0, ziel),
            rest.rfind("\n", 0, ziel),
        )
        if schnitt < ziel // 3:
            schnitt = rest.rfind(" ", 0, ziel)
        if schnitt <= 0:
            schnitt = ziel
        stuecke.append(rest[: schnitt + 1].strip())
        rest = rest[schnitt + 1 :].lstrip()
    if rest.strip():
        stuecke.append(rest.strip())
    return stuecke
