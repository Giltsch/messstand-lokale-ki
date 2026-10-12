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
