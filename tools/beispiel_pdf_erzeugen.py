"""Erzeugt eine Platzhalter-PDF mit echter Tabelle fuer den Reiter „Dokumente“.

Peter ersetzt die Datei spaeter durch die eigene Preisliste. Das Skript bleibt
im Repo, damit die Platzhalter-Datei jederzeit neu gebaut werden kann:

    uv run python tools/beispiel_pdf_erzeugen.py
"""

from pathlib import Path

import pymupdf

ZIEL = Path(__file__).resolve().parents[1] / "docs" / "beispiel-preisliste-platzhalter.pdf"

KOPF = ["Leistung", "Einheit", "Preis netto", "Preis brutto"]
ZEILEN = [
    ["Fliesen verlegen, Wand", "qm", "68,00 EUR", "80,92 EUR"],
    ["Fliesen verlegen, Boden", "qm", "74,50 EUR", "88,66 EUR"],
    ["Altfliesen abschlagen", "qm", "22,00 EUR", "26,18 EUR"],
    ["Bodengleiche Dusche einbauen", "Stueck", "1.850,00 EUR", "2.201,50 EUR"],
    ["Badewanne ausbauen und entsorgen", "Stueck", "320,00 EUR", "380,80 EUR"],
    ["Waschbecken mit Unterschrank montieren", "Stueck", "390,00 EUR", "464,10 EUR"],
    ["Abdichtung nach DIN 18534", "qm", "31,00 EUR", "36,89 EUR"],
    ["Anfahrt im Umkreis von 30 km", "pauschal", "45,00 EUR", "53,55 EUR"],
]
SPALTEN_X = [50, 300, 370, 470]
SPALTEN_BREITE = [250, 70, 100, 90]


def erzeugen() -> Path:
    dokument = pymupdf.open()
    seite = dokument.new_page()
    schrift = "helv"

    seite.insert_text((50, 70), "Musterbad GmbH", fontname=schrift, fontsize=20)
    seite.insert_text(
        (50, 95),
        "Preisliste Badsanierung, gueltig ab 1. Januar 2026",
        fontname=schrift,
        fontsize=11,
    )
    seite.insert_text(
        (50, 130),
        "Die folgenden Preise gelten fuer Privatkunden im Landkreis Ansbach.",
        fontname=schrift,
        fontsize=10,
    )

    y = 170
    zeilenhoehe = 26
    # Kopfzeile
    for x, breite, titel in zip(SPALTEN_X, SPALTEN_BREITE, KOPF):
        rechteck = pymupdf.Rect(x, y, x + breite, y + zeilenhoehe)
        seite.draw_rect(rechteck, color=(0, 0, 0), fill=(0.88, 0.9, 0.93), width=0.8)
        seite.insert_text((x + 5, y + 17), titel, fontname=schrift, fontsize=10)
    y += zeilenhoehe

    for zeile in ZEILEN:
        for x, breite, zelle in zip(SPALTEN_X, SPALTEN_BREITE, zeile):
            rechteck = pymupdf.Rect(x, y, x + breite, y + zeilenhoehe)
            seite.draw_rect(rechteck, color=(0, 0, 0), width=0.6)
            seite.insert_text((x + 5, y + 17), zelle, fontname=schrift, fontsize=9)
        y += zeilenhoehe

    y += 30
    for absatz in [
        "Hinweis: Die Preise verstehen sich als Richtwerte. Verbindlich ist",
        "ausschliesslich das schriftliche Angebot nach einem Besichtigungstermin.",
        "",
        "Zahlungsbedingungen: 30 Prozent bei Auftragserteilung, Rest nach Abnahme.",
        "Zahlbar innerhalb von 14 Tagen ohne Abzug.",
        "",
        "Gewaehrleistung: 5 Jahre auf Abdichtungsarbeiten, 2 Jahre auf Montage.",
        "Ein Besichtigungstermin ist fruehestens vier Wochen nach Anfrage moeglich.",
    ]:
        if absatz:
            seite.insert_text((50, y), absatz, fontname=schrift, fontsize=10)
        y += 16

    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    dokument.save(str(ZIEL))
    dokument.close()
    return ZIEL


if __name__ == "__main__":
    print(f"geschrieben: {erzeugen()}")
