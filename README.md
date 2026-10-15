# Messstand: lokale KI vergleichen

Werkzeug für den MDZ-Workshop „KI auf eigener Hardware“. Gleiche Aufgabe,
verschiedene Laufzeiten und Modelle, saubere Messwerte, live am Beamer sichtbar.

Alles läuft lokal: der Server bindet ausschließlich an `127.0.0.1`, es gibt
keine externen Aufrufe, keine CDNs, keine Telemetrie. Das Werkzeug funktioniert
im Flugmodus.

## Start

```
uv sync                                        # einmal, solange Netz da ist
uv run messstand --config stations/macmini.yaml
```

Oder per Doppelklick: `start.command` (macOS), `start.bat` (Windows),
`./start.sh` (Linux). Jedes Skript nimmt eine andere Station als Argument,
zum Beispiel `./start.sh stations/macmini.yaml`.

Weitere Stationen: `stations/laptop.yaml`, `stations/spark.yaml`.
`stations/dev.yaml` ist nur zum Entwickeln gedacht.

Optionen: `--port` (Standard 8765), `--no-browser`.

Strukturierter Parser (Docling) ist eine optionale Abhängigkeit:

```
uv sync --extra docling
```

## Die Reiter

| Reiter | Zeigt |
|---|---|
| Aufgabe | Die Aufgabenkarte des Workshops, Antwort im Stream, vier Messwert-Kacheln |
| Vergleich | Gleicher Prompt nacheinander an zwei Modelle, Balken mit Faktor, Vorhersage aus den aktiven Parametern |
| Last | Mehrere Anfragen gleichzeitig, eine Bahn je Anfrage, Gesamtdurchsatz und Wartezeiten |
| Dokumente | PDF einlesen, fragen, die vier gefundenen Abschnitte und den vollständigen Prompt sehen |
| Foto → Daten | Alle Stationen: Handyfoto (Beleg, Lieferschein, Typenschild, Whiteboard) wird zu einer Tabelle. Gegen eine Musterlösung bewertet („26 von 28 Angaben richtig“), dazu ein Stapel mit vielen Fotos gleichzeitig. Braucht ein Bild-fähiges Modell, etwa Gemma 4 |
| OCR | Nur Spark: eigenes OCR-Werkzeug (LawAI) vorführen. Scan neben gelesenem Text, Vertrauensfarben, Ablauf je Seite, Grenze und Stellschraube, Weitergabe an ein Sprachmodell. Braucht `ocr:` in der Stations-YAML und `spark/spark-modus.sh ocr` |
| Sprache | Spark und Mac mini: Besprechung über ein USB-Mikrofon mitschreiben (Whisper lokal, Stücke an Sprechpausen), danach Notizen, Aufgaben und Terminvorschläge als .ics von einem Sprachmodell. Braucht `sprache:` in der Stations-YAML und `spark/spark-modus.sh sprache`, auf dem Mac `mac/whisper_dienst.py` (ohne Sprecherzuordnung) |
| Ergebnisse | Alle Messungen der Sitzung, CSV für den Flipchart |

## Messwerte

| Anzeige | Bedeutung |
|---|---|
| Zeit bis zum ersten Wort | Vom Absenden bis zum ersten sichtbaren Token, hier gemessen |
| Lesetempo | Eingabe-Token pro Sekunde |
| Schreibtempo | Ausgabe-Token pro Sekunde, ohne die Zeit für die Eingabe |
| Gesamtzeit | Wanduhrzeit der ganzen Anfrage |

Ollama meldet eigene Zähler, dann steht unter den Kacheln „Tempowerte vom
Server gemeldet". OpenAI-kompatible Server tun das nicht, dort wird hier
gemessen. Fehlt die Token-Zählung ganz, erscheint die Marke „geschätzt".

Für alle Läufe gelten dieselben Bedingungen: Temperatur 0,2, Seed 42,
höchstens 300 Token Antwort, Kontext 8192 Token, Denkschritte aus. Sie
stehen in der Oberfläche und in `generierung` der Stations-YAML.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `src/messstand/` | Server: FastAPI, Konfiguration, Backends, Messung |
| `static/` | Oberfläche: eine HTML-Datei, CSS, Vanilla-JS als ES-Module |
| `stations/` | Eine YAML-Datei pro Station. Alle Unterschiede stehen hier. |
| `presets/` | Aufgabenkarte und Beispieltext des Workshops |
| `docs/` | Beispiel-PDFs und die Aufbauanleitung |
| `results/` | CSV-Ausgaben (nicht im Repo) |
| `tools/` | Hilfsskripte: Offline-Prüfung, Platzhalter-PDF erzeugen |

## Prüfen

```
uv run python tools/offline_pruefen.py
```

Prüft die Oberfläche auf externe Verweise und den Server auf lokale Bindung.

```
uv run python tools/stationstest.py
```

Gegen den laufenden Messstand: welche Laufzeiten und Modelle da sind, dann
die Beispielfotos aus „Foto → Daten“ durch jedes Bild-fähige Modell, mit
Tabelle und CSV in `results/`. Mehr in [docs/aufbau.md](docs/aufbau.md).

Mehr zum Aufbau jeder Station steht in [docs/aufbau.md](docs/aufbau.md).

## Lizenz

MIT, siehe [LICENSE](LICENSE). Sie dürfen den Messstand für Ihre eigenen
Workshops verwenden, verändern und weitergeben; es muss nur der
Urheberrechtshinweis erhalten bleiben.

Die Beispiel-PDFs unter `docs/` sind frei erfundenes Übungsmaterial
(„Musterbad GmbH", „Familie Beispiel") und fallen unter dieselbe Lizenz.
Die Modelle selbst gehören nicht zu diesem Repo: sie werden an jeder Station
von Hand geladen und haben ihre eigenen Lizenzbedingungen.
