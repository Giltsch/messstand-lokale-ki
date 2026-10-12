"""Erzeugt Platzhalter-PDFs für den Reiter „Dokumente“.

    uv run python tools/beispiel_pdfs_erzeugen.py

Jede Datei zeigt eine andere Schwäche beim Parsen, damit der Vergleich der
Parser im Workshop etwas zu zeigen hat:

  beispiel-preisliste.pdf          eine Seite, einfache Tabelle
  beispiel-angebot-mehrseitig.pdf  vier Seiten, Tabelle über den Seitenumbruch
  beispiel-merkblatt-zweispaltig.pdf  zwei Spalten, Lesereihenfolge
  beispiel-rechnung.pdf            Rechnung mit Summenzeilen
  beispiel-hausordnung-lang.pdf    zwölf Seiten, viele Abschnitte
  beispiel-scan-ohne-textebene.pdf  Bild ohne Textebene, Parser finden nichts

Peter ersetzt die Dateien durch eigene, sobald sie da sind.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

ORDNER = Path(__file__).resolve().parents[1] / "docs"
SCHRIFT = "helv"
FETT = "hebo"


def _tabelle(seite, x0, y, spalten, zeilen, *, kopf=True, zeilenhoehe=24, schriftgroesse=9):
    """Zeichnet eine Tabelle mit Linien, damit sie wie eine Tabelle aussieht."""
    for i, zeile in enumerate(zeilen):
        x = x0
        for (breite, _), zelle in zip(spalten, zeile):
            rechteck = pymupdf.Rect(x, y, x + breite, y + zeilenhoehe)
            fuellung = (0.88, 0.9, 0.93) if (i == 0 and kopf) else None
            seite.draw_rect(rechteck, color=(0, 0, 0), fill=fuellung, width=0.6)
            seite.insert_text(
                (x + 5, y + zeilenhoehe - 8),
                str(zelle),
                fontname=FETT if (i == 0 and kopf) else SCHRIFT,
                fontsize=schriftgroesse,
            )
            x += breite
        y += zeilenhoehe
    return y


def _titel(seite, titel, unterzeile=""):
    seite.insert_text((50, 70), titel, fontname=FETT, fontsize=18)
    if unterzeile:
        seite.insert_text((50, 95), unterzeile, fontname=SCHRIFT, fontsize=10)
    return 130


def _absaetze(seite, y, zeilen, groesse=10, abstand=16):
    for zeile in zeilen:
        if zeile:
            seite.insert_text((50, y), zeile, fontname=SCHRIFT, fontsize=groesse)
        y += abstand
    return y


SPALTEN = [(250, "Leistung"), (70, "Einheit"), (100, "Preis netto"), (90, "Preis brutto")]
PREISE = [
    ["Fliesen verlegen, Wand", "qm", "68,00 EUR", "80,92 EUR"],
    ["Fliesen verlegen, Boden", "qm", "74,50 EUR", "88,66 EUR"],
    ["Altfliesen abschlagen", "qm", "22,00 EUR", "26,18 EUR"],
    ["Bodengleiche Dusche einbauen", "Stueck", "1.850,00 EUR", "2.201,50 EUR"],
    ["Badewanne ausbauen und entsorgen", "Stueck", "320,00 EUR", "380,80 EUR"],
    ["Waschbecken mit Unterschrank montieren", "Stueck", "390,00 EUR", "464,10 EUR"],
    ["Abdichtung nach DIN 18534", "qm", "31,00 EUR", "36,89 EUR"],
    ["Anfahrt im Umkreis von 30 km", "pauschal", "45,00 EUR", "53,55 EUR"],
]


def preisliste() -> Path:
    dokument = pymupdf.open()
    seite = dokument.new_page()
    y = _titel(
        seite,
        "Musterbad GmbH",
        "Preisliste Badsanierung, gueltig ab 1. Januar 2026",
    )
    y = _absaetze(seite, y, ["Die folgenden Preise gelten fuer Privatkunden im Landkreis Ansbach."])
    y = _tabelle(seite, 50, y + 20, SPALTEN, [[s[1] for s in SPALTEN]] + PREISE)
    _absaetze(seite, y + 30, [
        "Hinweis: Die Preise verstehen sich als Richtwerte. Verbindlich ist",
        "ausschliesslich das schriftliche Angebot nach einem Besichtigungstermin.",
        "",
        "Zahlungsbedingungen: 30 Prozent bei Auftragserteilung, Rest nach Abnahme.",
        "Zahlbar innerhalb von 14 Tagen ohne Abzug.",
        "",
        "Gewaehrleistung: 5 Jahre auf Abdichtungsarbeiten, 2 Jahre auf Montage.",
        "Ein Besichtigungstermin ist fruehestens vier Wochen nach Anfrage moeglich.",
    ])
    return _speichern(dokument, "beispiel-preisliste.pdf")


def angebot_mehrseitig() -> Path:
    """Vier Seiten. Die Tabelle laeuft ueber den Seitenumbruch weiter."""
    posten = [
        ["1.1", "Baustelle einrichten, Schutzabdeckung", "pauschal", "1", "180,00 EUR"],
        ["1.2", "Altfliesen abschlagen, Wand und Boden", "qm", "28", "616,00 EUR"],
        ["1.3", "Badewanne ausbauen und entsorgen", "Stueck", "1", "320,00 EUR"],
        ["1.4", "Schutt abtransportieren, Container", "pauschal", "1", "420,00 EUR"],
        ["2.1", "Wasseranschluesse neu setzen", "Stueck", "4", "680,00 EUR"],
        ["2.2", "Abfluss fuer bodengleiche Dusche", "Stueck", "1", "540,00 EUR"],
        ["2.3", "Elektro: Steckdosen und Spiegelleuchte", "Stueck", "3", "390,00 EUR"],
        ["3.1", "Abdichtung nach DIN 18534", "qm", "12", "372,00 EUR"],
        ["3.2", "Fliesen verlegen, Wand", "qm", "18", "1.224,00 EUR"],
        ["3.3", "Fliesen verlegen, Boden", "qm", "8", "596,00 EUR"],
        ["3.4", "Silikonfugen ziehen", "lfm", "22", "176,00 EUR"],
        ["4.1", "Bodengleiche Dusche einbauen", "Stueck", "1", "1.850,00 EUR"],
        ["4.2", "Duschabtrennung aus Glas montieren", "Stueck", "1", "740,00 EUR"],
        ["4.3", "Waschbecken mit Unterschrank montieren", "Stueck", "1", "390,00 EUR"],
        ["4.4", "WC montieren, Spuelkasten pruefen", "Stueck", "1", "280,00 EUR"],
        ["5.1", "Endreinigung", "pauschal", "1", "140,00 EUR"],
        ["5.2", "Abnahme und Einweisung", "pauschal", "1", "90,00 EUR"],
    ]
    spalten = [(50, "Pos"), (260, "Leistung"), (70, "Einheit"), (50, "Menge"), (110, "Betrag")]
    dokument = pymupdf.open()

    seite = dokument.new_page()
    y = _titel(seite, "Angebot A-2026-0147", "Musterbad GmbH an Familie Beispiel, Musterstrasse 3, 91550 Dinkelsbuehl")
    y = _absaetze(seite, y, [
        "Angebotsdatum: 8. Oktober 2026. Bindefrist: 30 Tage.",
        "Bauvorhaben: Badezimmer im Obergeschoss, etwa 8 Quadratmeter, Baujahr 1987.",
        "",
        "Der Angebotspreis setzt sich aus den folgenden Positionen zusammen. Die",
        "Positionen 1 bis 5 sind einzeln beauftragbar.",
    ])
    y = _tabelle(seite, 50, y + 15, spalten, [[s[1] for s in spalten]] + posten[:8])
    seite.insert_text((50, y + 25), "Fortsetzung auf Seite 2", fontname=SCHRIFT, fontsize=9)

    seite = dokument.new_page()
    y = _absaetze(seite, 70, ["Angebot A-2026-0147, Fortsetzung der Positionen"], groesse=11)
    y = _tabelle(seite, 50, y + 10, spalten, [[s[1] for s in spalten]] + posten[8:])
    y = _tabelle(
        seite, 50, y + 20, [(360, ""), (110, ""), (110, "")],
        [
            ["Summe netto", "", "9.994,00 EUR"],
            ["Umsatzsteuer 19 Prozent", "", "1.898,86 EUR"],
            ["Gesamtbetrag brutto", "", "11.892,86 EUR"],
        ],
        kopf=False,
    )

    seite = dokument.new_page()
    y = _titel(seite, "Zahlungsplan und Fristen")
    _absaetze(seite, y, [
        "Die Zahlung erfolgt in drei Raten:",
        "",
        "  Erste Rate: 30 Prozent bei Auftragserteilung, 3.567,86 EUR brutto.",
        "  Zweite Rate: 40 Prozent nach Abschluss der Fliesenarbeiten, 4.757,14 EUR brutto.",
        "  Dritte Rate: 30 Prozent nach Abnahme, 3.567,86 EUR brutto.",
        "",
        "Zahlungsziel je Rate: 14 Tage ohne Abzug.",
        "Bei Zahlung der ersten Rate innerhalb von 7 Tagen gewaehren wir 2 Prozent Skonto.",
        "",
        "Ausfuehrungszeitraum: voraussichtlich 12 Werktage ab Baubeginn.",
        "Ein Besichtigungstermin ist fruehestens vier Wochen nach Anfrage moeglich.",
        "Termine sind ab 16 Uhr und samstags moeglich.",
    ])

    seite = dokument.new_page()
    y = _titel(seite, "Gewaehrleistung und Hinweise")
    _absaetze(seite, y, [
        "Gewaehrleistung: 5 Jahre auf Abdichtungsarbeiten, 2 Jahre auf Montageleistungen.",
        "Fuer beigestellte Ware des Auftraggebers wird keine Gewaehrleistung uebernommen.",
        "",
        "Nicht im Angebot enthalten sind: Malerarbeiten, Austausch der Heizkoerper,",
        "Arbeiten an der Elektroverteilung sowie Asbestsanierung, falls erforderlich.",
        "",
        "Die Heizung im Bad bleibt unveraendert und wird lediglich abgedeckt.",
        "",
        "Werden beim Abschlagen der Fliesen Feuchtigkeitsschaeden sichtbar, melden wir",
        "diese unverzueglich. Zusatzarbeiten werden nach Aufwand mit 68,00 EUR netto",
        "je Stunde abgerechnet.",
    ])
    return _speichern(dokument, "beispiel-angebot-mehrseitig.pdf")


def merkblatt_zweispaltig() -> Path:
    """Zwei Spalten. Naive Parser mischen die Lesereihenfolge."""
    links = [
        "Vor der Sanierung",
        "",
        "Raeumen Sie das Badezimmer vollstaendig",
        "aus. Handtuecher, Kosmetik und",
        "Medikamente gehoeren vor Baubeginn",
        "in einen anderen Raum, weil Staub sich",
        "ueberall absetzt.",
        "",
        "Klaeren Sie mit der Hausverwaltung, ob",
        "Arbeiten an Steigleitungen angemeldet",
        "werden muessen. Die Anmeldefrist",
        "betraegt in der Regel 14 Tage.",
        "",
        "Ein Ersatzbad steht Ihnen waehrend der",
        "Bauzeit nicht zur Verfuegung. Planen Sie",
        "fuer 12 Werktage eine Alternative ein.",
    ]
    rechts = [
        "Waehrend der Sanierung",
        "",
        "Die Wasserzufuhr wird taeglich zwischen",
        "8 und 16 Uhr abgestellt. Ausserhalb",
        "dieser Zeit steht Wasser zur Verfuegung.",
        "",
        "Der Staubschutz bleibt bis zur",
        "Endreinigung geschlossen. Oeffnen Sie",
        "ihn nicht selbst, sonst verteilt sich",
        "Fliesenstaub in der Wohnung.",
        "",
        "Nach der Sanierung",
        "",
        "Die Silikonfugen muessen 24 Stunden",
        "aushaerten. Duschen Sie fruehestens",
        "am zweiten Tag nach der Abnahme.",
        "",
        "Lueften Sie in den ersten zwei Wochen",
        "dreimal taeglich fuer 10 Minuten.",
    ]
    dokument = pymupdf.open()
    seite = dokument.new_page()
    _titel(seite, "Merkblatt fuer Kundinnen und Kunden", "Musterbad GmbH, Stand Oktober 2026")
    y0 = 140
    seite.draw_line(pymupdf.Point(300, y0 - 10), pymupdf.Point(300, 700), color=(0.6, 0.6, 0.6), width=0.5)
    for spalte_x, zeilen in ((50, links), (320, rechts)):
        y = y0
        for zeile in zeilen:
            fett = zeile and not zeile.startswith(" ") and zeile.endswith(("Sanierung", "sanierung"))
            if zeile:
                seite.insert_text(
                    (spalte_x, y), zeile,
                    fontname=FETT if fett else SCHRIFT,
                    fontsize=11 if fett else 10,
                )
            y += 17
    return _speichern(dokument, "beispiel-merkblatt-zweispaltig.pdf")


def rechnung() -> Path:
    """Rechnung mit Summenblock. Zahlen muessen der richtigen Zeile folgen."""
    posten = [
        ["1", "Fliesen verlegen, Wand", "18 qm", "68,00 EUR", "1.224,00 EUR"],
        ["2", "Fliesen verlegen, Boden", "8 qm", "74,50 EUR", "596,00 EUR"],
        ["3", "Bodengleiche Dusche einbauen", "1 Stueck", "1.850,00 EUR", "1.850,00 EUR"],
        ["4", "Abdichtung nach DIN 18534", "12 qm", "31,00 EUR", "372,00 EUR"],
        ["5", "Anfahrt", "3 Fahrten", "45,00 EUR", "135,00 EUR"],
    ]
    spalten = [(40, "Pos"), (240, "Leistung"), (80, "Menge"), (100, "Einzelpreis"), (110, "Gesamt")]
    dokument = pymupdf.open()
    seite = dokument.new_page()
    y = _titel(seite, "Rechnung R-2026-0312", "Musterbad GmbH, Handwerkerweg 7, 91522 Ansbach")
    y = _absaetze(seite, y, [
        "Rechnungsempfaenger: Familie Beispiel, Musterstrasse 3, 91550 Dinkelsbuehl",
        "Rechnungsdatum: 2. Oktober 2026    Leistungszeitraum: 14. bis 29. September 2026",
        "Kundennummer: 4711    Steuernummer: 203/123/40567",
    ])
    y = _tabelle(seite, 50, y + 15, spalten, [[s[1] for s in spalten]] + posten)
    y = _tabelle(
        seite, 50, y + 15, [(360, ""), (100, ""), (110, "")],
        [
            ["Zwischensumme netto", "", "4.177,00 EUR"],
            ["Nachlass 3 Prozent", "", "-125,31 EUR"],
            ["Summe netto nach Nachlass", "", "4.051,69 EUR"],
            ["Umsatzsteuer 19 Prozent", "", "769,82 EUR"],
            ["Rechnungsbetrag", "", "4.821,51 EUR"],
            ["Bereits gezahlte Anzahlung", "", "-1.500,00 EUR"],
            ["Offener Betrag", "", "3.321,51 EUR"],
        ],
        kopf=False, zeilenhoehe=22,
    )
    _absaetze(seite, y + 25, [
        "Zahlbar bis 16. Oktober 2026 ohne Abzug.",
        "Bei Zahlung bis 9. Oktober 2026 gewaehren wir 2 Prozent Skonto, das sind 66,43 EUR.",
        "",
        "Nach Paragraf 35a Einkommensteuergesetz sind Lohnanteile steuerlich",
        "beguenstigt. Der Lohnanteil dieser Rechnung betraegt 2.480,00 EUR netto.",
    ])
    return _speichern(dokument, "beispiel-rechnung.pdf")


def hausordnung_lang() -> Path:
    """Zwoelf Seiten. Zeigt, dass das Modell nur vier von vielen Abschnitten sieht."""
    themen = [
        ("Geltungsbereich", "Diese Hausordnung gilt fuer alle Wohneinheiten im Objekt Musterstrasse 3."),
        ("Ruhezeiten", "Ruhezeit ist von 22 Uhr bis 7 Uhr sowie sonntags ganztaegig."),
        ("Treppenhaus", "Das Treppenhaus ist Fluchtweg und bleibt frei von Gegenstaenden."),
        ("Muelltrennung", "Papier, Verpackung, Glas und Restmuell werden getrennt gesammelt."),
        ("Waschkeller", "Die Waschmaschine darf von 7 bis 20 Uhr benutzt werden."),
        ("Fahrraeder", "Fahrraeder gehoeren in den Fahrradkeller, nicht ins Treppenhaus."),
        ("Lueften", "Wohnungen sind dreimal taeglich fuer 10 Minuten quer zu lueften."),
        ("Bauarbeiten", "Handwerkliche Arbeiten sind werktags von 8 bis 18 Uhr zulaessig."),
        ("Wasserschaeden", "Wasserschaeden sind der Verwaltung unverzueglich zu melden."),
        ("Haustiere", "Das Halten von Hunden und Katzen ist anzuzeigen."),
        ("Schluessel", "Der Verlust eines Schluessels ist sofort zu melden. Die Kosten fuer eine neue Schliessanlage traegt die verursachende Partei."),
        ("Kuendigung", "Die Kuendigungsfrist betraegt drei Monate zum Monatsende."),
    ]
    dokument = pymupdf.open()
    for nummer, (titel, kern) in enumerate(themen, start=1):
        seite = dokument.new_page()
        y = _titel(seite, f"Paragraf {nummer}: {titel}", "Hausordnung Musterstrasse 3, Stand Oktober 2026")
        zeilen = [kern, ""]
        for absatz in range(1, 5):
            zeilen += [
                f"Absatz {absatz}. Die Bewohnerinnen und Bewohner halten sich an die in",
                f"Paragraf {nummer} getroffenen Regeln. Verstoesse werden zunaechst schriftlich",
                "abgemahnt. Bei wiederholten Verstoessen behaelt sich die Verwaltung weitere",
                "Schritte vor.",
                "",
            ]
        _absaetze(seite, y, zeilen)
        seite.insert_text((50, 780), f"Seite {nummer} von {len(themen)}", fontname=SCHRIFT, fontsize=8)
    return _speichern(dokument, "beispiel-hausordnung-lang.pdf")


def scan_ohne_textebene() -> Path:
    """Bild ohne Textebene: die Parser finden nichts, die Meldung erklaert es."""
    quelle = pymupdf.open()
    seite = quelle.new_page()
    y = _titel(seite, "Handschriftliche Notiz", "Eingescannt am 5. Oktober 2026")
    _absaetze(seite, y, [
        "Kunde Beispiel, Bad im Obergeschoss.",
        "Aufmass: 8,2 Quadratmeter Bodenflaeche, 18 Quadratmeter Wandflaeche.",
        "Dusche 90 mal 90, bodengleich gewuenscht.",
        "Heizkoerper bleibt.",
        "Termin ab 16 Uhr oder samstags.",
        "Angebot bis Ende Oktober zusenden.",
    ], groesse=13, abstand=26)
    bild = seite.get_pixmap(dpi=120)
    quelle.close()

    dokument = pymupdf.open()
    ziel = dokument.new_page(width=595, height=842)
    # Als JPEG einbetten, sonst wird die Datei unnoetig gross.
    ziel.insert_image(pymupdf.Rect(0, 0, 595, 842), stream=bild.tobytes("jpeg", jpg_quality=72))
    return _speichern(dokument, "beispiel-scan-ohne-textebene.pdf")


def _speichern(dokument, name: str) -> Path:
    ORDNER.mkdir(parents=True, exist_ok=True)
    ziel = ORDNER / name
    dokument.save(str(ziel))
    dokument.close()
    return ziel


ALLE = [
    preisliste,
    angebot_mehrseitig,
    merkblatt_zweispaltig,
    rechnung,
    hausordnung_lang,
    scan_ohne_textebene,
]


if __name__ == "__main__":
    for bauen in ALLE:
        pfad = bauen()
        groesse = pfad.stat().st_size / 1024
        print(f"  {pfad.name:38s} {groesse:7.1f} kB")
