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
    dokument,
    ziel: int = ZIEL,
    ueberlappung: int = UEBERLAPPUNG,
) -> list[Abschnitt]:
    """Baut Abschnitte aus dem geparsten Dokument, Tabellen bleiben zusammen.

    Setzt sich das Markdown aus den Seitentexten zusammen (naiv, schnell),
    wird die Seitenzahl je Block mitgefuehrt und ist damit genau. Bei Docling
    ist das Markdown eigenstaendig, dort wird die Seite ueber Textvergleich
    geschaetzt und bleibt im Zweifel leer.
    """
    from .parse import seite_finden

    seiten = getattr(dokument, "seiten", None) or []
    aus_seiten = getattr(dokument, "markdown_aus_seiten", True) and any(
        s.text.strip() for s in seiten
    )

    bloecke: list[tuple[str, bool, int | None]] = []
    if aus_seiten:
        for seite in seiten:
            for text, ist_tabelle in bloecke_bilden(seite.text):
                bloecke.append((text, ist_tabelle, seite.nummer))
    else:
        for text, ist_tabelle in bloecke_bilden(dokument.markdown):
            bloecke.append((text, ist_tabelle, None))

    abschnitte: list[Abschnitt] = []
    laufend: list[str] = []
    laufend_tabelle = False
    laufend_seite: int | None = None
    # Steht nur die Ueberlappung des Vorgaengers im Puffer, darf daraus kein
    # eigener Abschnitt werden. Sonst landen Dubletten ohne Seite im Index.
    eigener_inhalt = False

    def abschliessen() -> None:
        nonlocal laufend, laufend_tabelle, laufend_seite, eigener_inhalt
        if not eigener_inhalt:
            return
        text = "\n\n".join(laufend).strip()
        if not text:
            laufend, laufend_tabelle, laufend_seite = [], False, None
            eigener_inhalt = False
            return
        seite = laufend_seite
        if seite is None and not aus_seiten:
            seite = seite_finden(text, seiten)
        abschnitte.append(
            Abschnitt(
                nr=len(abschnitte) + 1,
                text=text,
                seite=seite,
                ist_tabelle=laufend_tabelle,
            )
        )
        # Ueberlappung: das Ende des Abschnitts beginnt den naechsten.
        schwanz = text[-ueberlappung:] if ueberlappung > 0 else ""
        laufend = [schwanz.strip()] if schwanz.strip() else []
        laufend_tabelle = False
        # Die Seite des naechsten Abschnitts setzt der naechste Block.
        laufend_seite = None
        eigener_inhalt = False

    def anhaengen(text: str, ist_tabelle: bool, seite: int | None) -> None:
        nonlocal laufend_tabelle, laufend_seite, eigener_inhalt
        laufend.append(text)
        laufend_tabelle = laufend_tabelle or ist_tabelle
        eigener_inhalt = True
        if laufend_seite is None:
            laufend_seite = seite

    for text, ist_tabelle, seite in bloecke:
        laenge = sum(len(t) for t in laufend) + len(text)
        if laufend and laenge > ziel:
            abschliessen()
        if len(text) > ziel and not ist_tabelle:
            # Sehr langer Absatz: an Satzgrenzen aufteilen.
            for stueck in _saetze_stapeln(text, ziel):
                if laufend and sum(len(t) for t in laufend) + len(stueck) > ziel:
                    abschliessen()
                anhaengen(stueck, False, seite)
            continue
        anhaengen(text, ist_tabelle, seite)
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
