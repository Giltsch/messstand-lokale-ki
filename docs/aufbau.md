# Aufbau der Stationen

Diese Anleitung beschreibt, was an jeder Station von Hand eingerichtet wird.
Das Werkzeug selbst verwaltet keine Modelle und lädt nichts nach.

## Einmal pro Gerät

1. **uv installieren**
   - macOS: `brew install uv`
   - Windows: `winget install astral-sh.uv`
   - Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. **Repo kopieren** (USB-Stick genügt, es muss nichts geklont werden).
3. **Abhängigkeiten holen**, solange noch Netz da ist:
   ```
   uv sync
   ```
   Für den strukturierten Parser zusätzlich (groß, mehrere Gigabyte):
   ```
   uv sync --extra docling
   ```
4. **Ollama installieren** und die Modelle der Station vorab ziehen,
   zum Beispiel `ollama pull gemma4:e4b-it-q4_K_M`.
5. **Einbettungsmodell ziehen**, zum Beispiel `ollama pull embeddinggemma`.
   Ohne das bleibt der Reiter „Dokumente" leer.

## Umgebungsvariablen für Ollama

Der Lasttest zeigt nur dann etwas Interessantes, wenn Ollama mehrere
Anfragen gleichzeitig annehmen darf.

| Variable | Empfehlung | Wirkung |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | Laptop 1, Mac mini 4, Spark 15 | Wie viele Anfragen gleichzeitig bedient werden |
| `OLLAMA_MAX_LOADED_MODELS` | 1 bis 2 | Wie viele Modelle gleichzeitig im Speicher liegen |
| `OLLAMA_KEEP_ALIVE` | `-1` | Modelle bleiben geladen, Messungen bleiben warm |

macOS und Linux, dauerhaft in der Shell-Konfiguration oder vor dem Start:

```
OLLAMA_NUM_PARALLEL=4 OLLAMA_KEEP_ALIVE=-1 ollama serve
```

Windows: Systemumgebungsvariablen setzen, dann Ollama neu starten.

Der eingestellte Wert gehört in die Stations-YAML, Feld
`lasttest.hinweis_parallelitaet`. Er erscheint dann in der Oberfläche,
damit niemand rätseln muss, woher die Zahlen kommen.

## Station 1: Laptop (Windows 11, nur CPU)

- Ollama mit `gemma4:e2b-it-qat`
- LM Studio installieren, Modell laden, im Reiter „Developer" den Server
  auf Port 1234 aktivieren
- Parser nur `naiv` und `schnell`, Docling bleibt hier weg
- Start: Doppelklick auf `start.bat`

## Station 2: Mac mini (Apple Silicon)

- Ollama mit den GGUF-Modellen und dem MLX-Modell
- Start: Doppelklick auf `start.command`
- Wenn macOS das Skript nicht ausführen will: einmal mit rechter Maustaste
  öffnen und „Öffnen" bestätigen

## Station 3: DGX Spark (Ubuntu auf ARM64)

- Ollama mit `gemma4:26b` und einem Modell, das auf 32 GB nicht passt
- vLLM im NVIDIA-Container auf Port 8000, `--gpu-memory-utilization` so
  niedrig wählen, dass Ollama mit dem großen Modell daneben Platz hat
- Die Modell-IDs für vLLM in `stations/spark.yaml` nach dem Setup eintragen:
  sie müssen genau so lauten, wie `curl http://127.0.0.1:8000/v1/models`
  sie meldet
- Start: `./start.sh`

## Material für den Reiter „Dokumente"

In `docs/` liegen sechs Platzhalter-PDFs. Jede zeigt eine andere Schwäche
beim Parsen. Neu bauen lassen sie sich mit
`uv run python tools/beispiel_pdfs_erzeugen.py`.

| Datei | Zeigt | Erprobte Frage | Erwartete Antwort |
|---|---|---|---|
| `beispiel-preisliste.pdf` | Einfache Tabelle auf einer Seite | Was kostet das Verlegen von Bodenfliesen pro Quadratmeter netto? | 74,50 EUR |
| `beispiel-angebot-mehrseitig.pdf` | Vier Seiten, Tabelle über den Seitenumbruch | Wie hoch ist die zweite Rate und wann wird sie fällig? | 4.757,14 EUR brutto, Quelle Seite 3 |
| `beispiel-merkblatt-zweispaltig.pdf` | Zwei Spalten, Lesereihenfolge | Ab wann darf ich nach der Abnahme wieder duschen? | Frühestens am zweiten Tag |
| `beispiel-rechnung.pdf` | Summenblock mit Zwischensummen | Wie hoch ist der offene Betrag? | 3.321,51 EUR, nicht die Zwischensumme |
| `beispiel-hausordnung-lang.pdf` | Zwölf Seiten, zwanzig Abschnitte | Wer zahlt eine neue Schließanlage bei Schlüsselverlust? | Die verursachende Partei, Quelle Seite 11 |
| `beispiel-scan-ohne-textebene.pdf` | Bild ohne Textebene | Wie groß ist die Bodenfläche des Bades? | 8,2 Quadratmeter, aber nur mit Parser „schnell" |

Die letzte Datei ist der stärkste Vergleich: der Parser „naiv" findet
überhaupt keinen Text und sagt das in Klartext, während „schnell" über die
Texterkennung an den Inhalt kommt. Ein guter Anlass, über eingescannte
Unterlagen zu sprechen.

Nehmen Sie für diesen Reiter kein Ein-Milliarden-Modell. Für das Arbeiten
mit Quellen braucht es mindestens die Vier-Milliarden-Klasse, sonst
beantwortet das Modell die Frage nicht, sondern beschreibt die Abschnitte.

## Vor dem Workshop prüfen

```
uv run python tools/offline_pruefen.py      # keine externen Verweise
uv run messstand --config stations/<name>.yaml
```

Beim Start listet die Konsole jedes Backend und jedes Modell auf. Ein `-`
bedeutet: Modell fehlt auf diesem Gerät. Das Werkzeug startet trotzdem, das
Modell erscheint in der Oberfläche ausgegraut.

Checkliste je Station:

- [ ] Oberfläche nach wenigen Sekunden unter http://127.0.0.1:8765 erreichbar
- [ ] Alle Statuspunkte in der Kopfzeile grün
- [ ] Reiter „Aufgabe": Teil 1 liefert Text und vier Messwerte
- [ ] „Modell vorladen" gedrückt, danach zeigt die Messung „warm"
- [ ] Reiter „Vergleich": beide Seiten liefern Werte, Balken erscheinen
- [ ] Reiter „Last": die eingestellte Zahl Bahnen läuft durch
- [ ] Reiter „Dokumente": Beispiel-PDF einlesen, Tabellenfrage stellen
- [ ] Nur wo Docling gebraucht wird: nach `uv sync --extra docling` den
      Parser „strukturiert" einmal einlesen und die Tabellenfrage stellen.
      Dieser Weg ist bisher nicht gelaufen, weil Docling nicht installiert
      war. Die Seitenzahlen kommen dort aus einem Textvergleich mit der
      Seitenaufteilung, bei Bedarf steht „Seite unbekannt".
- [ ] Reiter „Ergebnisse": CSV speichern, Datei liegt in `results/`
- [ ] Netzwerk trennen, alles noch einmal kurz durchspielen

## Wenn etwas hakt

| Symptom | Ursache und Abhilfe |
|---|---|
| Statuspunkt rot | Dienst läuft nicht. `curl http://127.0.0.1:11434/api/version` prüfen. |
| Modell ausgegraut | Modell-ID in der YAML stimmt nicht mit `ollama list` überein. |
| Jede Messung „kalt" | `OLLAMA_KEEP_ALIVE=-1` setzen oder „Modell vorladen" drücken. |
| Lesetempo bleibt leer | Die Laufzeit meldet keine Eingabe-Token (LM Studio). Das ist normal und steht als Hinweis unter den Kacheln. |
| „geschätzt" an den Werten | Die Laufzeit liefert keine Zählung, der Messstand hat Chunks gezählt. |
| Dokumente-Reiter meckert | Einbettungsmodell fehlt: `ollama pull embeddinggemma`. |
| Port 8765 belegt | `uv run messstand --config ... --port 8766` |

## Rückfallebene

Open WebUI auf Mac mini und Spark bleibt installiert. Hakt der Messstand am
Workshoptag, läuft die Vorführung dort weiter, ohne Messwerte.
