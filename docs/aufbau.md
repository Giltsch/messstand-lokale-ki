# Aufbau der Stationen

Diese Anleitung beschreibt, was an jeder Station von Hand eingerichtet wird.
Das Werkzeug selbst verwaltet keine Modelle und lädt nichts nach.

## Einmal pro Gerät

1. **uv installieren**
   - macOS: `brew install uv`
   - Windows: `winget install astral-sh.uv`
   - Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. **Repo holen** — entweder klonen:

   ```
   git clone https://github.com/Giltsch/messstand-lokale-ki.git
   cd messstand-lokale-ki
   ```

   oder per USB-Stick kopieren. Am Workshoptag ist der Stick der sicherere
   Weg: das Werkzeug soll ohne Netz laufen, und die Stationen sind dann
   womöglich schon getrennt.
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

**Nachprüfen, ob die Variable wirklich greift.** Es genügt nicht, sie zu
setzen: sie muss vor dem Start von Ollama im Prozess liegen, und auf macOS
erbt die Hintergrund-App die Shell-Variable nicht. Fahren Sie den Lasttest
einmal mit 1 und einmal mit 4 Bahnen:

- **Durchsatz steigt** (etwa 1,5- bis 2-mal): die Parallelität greift.
- **Durchsatz bleibt gleich, nur die Wartezeit wächst**: Ollama arbeitet die
  Anfragen nacheinander ab, die Variable ist nicht wirksam.

So sah der zweite Fall am 12.10.2026 auf dem Mac mini aus, mit dem MoE-Modell
und nicht gesetzter Variable:

| Bahnen | Durchsatz zusammen | Wartezeit im Schnitt | schlechteste |
|---|---|---|---|
| 1 | 30,1 Token/s | 0,4 s | 0,4 s |
| 4 | 30,4 Token/s | 14,8 s | 29,4 s |
| 8 | 30,3 Token/s | 33,3 s | 65,1 s |

Der Durchsatz rührt sich nicht, die Wartezeit vervielfacht sich. Auf dem
Beamer ist das übrigens die eindrucksvollere Hälfte der Geschichte: mehr
Nutzer machen die Maschine nicht langsamer, sie müssen nur warten. Wenn Sie
die Variable vorher setzen, zeigen Sie beides und vergleichen die Tabellen.

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

### Modelle holen

```
ollama pull gemma4:e4b-it-q4_K_M
ollama pull gemma4:e4b-it-q8_0
ollama pull gemma4:e4b-it-bf16
ollama pull gemma4:e4b-mlx
ollama pull gemma4:26b-a4b-it-q4_K_M
ollama pull gemma4:26b-mlx
ollama pull gemma4:31b-it-q4_K_M
ollama pull embeddinggemma
```

Zusammen rund 95 GB. Über eine langsame Leitung dauert das Stunden, also
nicht am Workshoptag anfangen.

### Gemessen am 12.10.2026 auf dem Mac mini M4, 32 GB

Schreibtempo, warm, Prompt der Aufgabenkarte, 8192 Token Kontext. Die Werte
sind auf diesem Gerät reproduzierbar: drei Läufe hintereinander ergaben
dieselbe Zahl (Streuung unter 3 %).

| Modell | Belegt | Schreibtempo |
|---|---|---|
| Gemma 4 E4B, 4 Bit, GGUF | 6,6 GB | 22,8 Token/s |
| Gemma 4 E4B, 8 Bit, GGUF | 9,0 GB | 19,4 Token/s |
| Gemma 4 E4B, 16 Bit, GGUF | 16 GB | 11,1 Token/s |
| Gemma 4 E4B, MLX | 9,5 GB | 51,0 Token/s |
| Gemma 4 26B A4B, MoE, 4 Bit | 17 GB | 31,5 Token/s |
| Gemma 4 26B A4B, MoE, MLX | 17 GB | 31,7 Token/s |
| Gemma 4 31B, dense, 4 Bit | 20 GB | 3,8 Token/s |

Was die Vergleiche davon zeigen:

| Vergleich | Vorhergesagt | Gemessen | |
|---|---|---|---|
| Dense gegen MoE | 7,75x | 8,26x | trifft |
| Acht Bit gegen sechzehn Bit | 1,78x | 1,79x | trifft |
| Vier Bit gegen acht Bit | 1,36x | 1,18x | bleibt zurück |
| Vier Bit gegen sechzehn Bit | 2,42x | 1,60x | bleibt zurück |
| Gleiches Modell, anderer Unterbau | keine | 2,63x für MLX | — |
| MLX gegen GGUF beim MoE | keine | 1,01x | gleich schnell |

Die beiden besten Vorführstücke: **Dense gegen MoE** (3,8 gegen 31,5 Token/s,
das größere Modell schreibt achtmal langsamer als das noch größere) und
**Acht gegen sechzehn Bit**, wo die Vorhersage aus der Dateigröße auf ein
Prozent genau zutrifft.

Zwei Stellen, an denen die Faustregel endet — und die den Workshop besser
machen, wenn Sie sie benennen:

- **Vier Bit ist nicht 1,36-mal schneller als acht Bit, nur 1,18-mal.** Das
  Auspacken der 4-Bit-Gewichte kostet selbst Rechenzeit. Die beiden liegen so
  eng beieinander, dass ein kurzer Prompt die Reihenfolge umdreht: dann ist
  8 Bit mit 19,8 gegen 17,8 Token/s vorn. Immer mit demselben Prompt
  vergleichen.
- **MLX gegen GGUF ist kein stabiler Vorteil.** Beim kleinen Modell schreibt
  MLX 2,6-mal schneller, beim MoE sind beide gleich schnell. Die Laufzeit
  entscheidet also je Modell, nicht grundsätzlich.

### Zwei Vergleiche passen nicht in den Speicher

`Dense gegen MoE` (20 + 17 GB) und `MLX gegen GGUF beim MoE` (17 + 17 GB)
brauchen mehr als die 32 GB der Station. Das zweite Modell verdrängt das
erste, beide warm zu halten ist unmöglich. Der Messstand sagt das im
Vergleichsreiter von selbst und empfiehlt dann nicht mehr, beide vorzuladen.
Vergleichen Sie dort Schreib- und Lesetempo, nicht die Gesamtzeit.

`ollama ps` meldet für `gemma4:e4b-*` nur rund 313 MB statt der Dateigröße.
Das ist kein Hinweis auf ein halb geladenes Modell, die Zahl stimmt bei dieser
Modellreihe einfach nicht. Verlassen Sie sich auf die Messwerte.

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
- [ ] Reiter „Last" mit 1 und mit 4 Bahnen: steigt der Durchsatz? Wenn nicht,
      ist `OLLAMA_NUM_PARALLEL` nicht wirksam und der Hinweis unter den
      Bahnen stimmt nicht. Entweder Variable richtig setzen und Ollama neu
      starten, oder `lasttest.hinweis_parallelitaet` in der Stations-YAML
      berichtigen.
- [ ] Reiter „Dokumente": Beispiel-PDF einlesen, Tabellenfrage stellen
- [ ] Nur wo Docling gebraucht wird: nach `uv sync --extra docling` den
      Parser „strukturiert" einmal einlesen und die Tabellenfrage stellen.
      Dieser Weg ist bisher nicht gelaufen, weil Docling nicht installiert
      war. Die Seitenzahlen kommen dort aus einem Textvergleich mit der
      Seitenaufteilung, bei Bedarf steht „Seite unbekannt".
- [ ] Reiter „Ergebnisse": CSV speichern, Datei liegt in `results/`
- [ ] Netzwerk trennen, alles noch einmal kurz durchspielen

## Neue Reiter auf Mac mini und PC testen

Stand Oktober 2026 sind dazugekommen: „Foto → Daten“ (alle Stationen),
„OCR“ und „Sprache“ (nur Spark, erscheinen woanders gar nicht).

1. Stand holen, solange Netz da ist:
   ```
   git fetch
   git switch station-3-spark        # oder main, sobald zusammengeführt
   git pull
   uv sync                           # neue Abhängigkeiten: markdown, nh3
   ```
2. Ollama läuft, Modelle der Station sind gezogen (siehe oben).
3. Messstand starten, zum Beispiel `uv run messstand --config stations/macmini.yaml`
   (Windows: `start.bat stations\laptop.yaml`).
4. In einem zweiten Fenster den Stationstest:
   ```
   uv run python tools/stationstest.py
   ```
   Er zeigt, welche Laufzeiten und Modelle da sind, lädt jedes Bild-fähige
   Modell vor und lässt die fünf Beispielfotos durchlaufen. Ergebnis: eine
   Tabelle („93 von 94 richtig, im Mittel 2,4 s pro Foto“) und eine CSV in
   `results/`. Mit `--modell <id>` nur ein Modell, mit `--nur-status` nur die
   Übersicht. Ollama-Modelle ohne Bildverständnis werden übersprungen.
5. In der Oberfläche den Reiter „Foto → Daten“ einmal von Hand: Beispiel
   anklicken, „Foto lesen“, dann den Stapel mit 4 Fotos.

Zum Vergleichen: Die CSV-Dateien aller Stationen nebeneinanderlegen. Auf dem
Spark gemessen (E2B / E4B / 26B / 31B): 87 bis 89 / 93 / 92 / 94 von 94 Angaben,
im Mittel rund 3 / 2,4 / 6 / 13 s pro Foto.

Was auf den anderen Stationen noch offen ist:

| Station | Prüfen |
|---|---|
| Mac mini | Ob die MLX-Modelle (`gemma4:e4b-mlx`, `gemma4:26b-mlx`) Bilder annehmen. Der Stationstest fragt Ollama danach und überspringt sie sonst. |
| Laptop | Ob LM Studio mit `gemma4-e2b-it` Bilder annimmt. Dafür muss in LM Studio die Vision-Variante des Modells geladen sein (mit „mmproj“-Datei). Sonst meldet der Stationstest „kein gültiges JSON“; Ollama mit E2B geht unabhängig davon. Auf der CPU dauert ein Foto deutlich länger, das ist gewollt sichtbar. |

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
| Foto → Daten: „kein gültiges JSON“ | Modell kann keine Bilder oder antwortet mit Text. Rohe Antwort aufklappen; anderes Modell wählen. |
| Stationstest: „antwortet nicht“ | Erst den Messstand starten, dann das Skript im zweiten Fenster. |

## Rückfallebene

Open WebUI auf Mac mini und Spark bleibt installiert. Hakt der Messstand am
Workshoptag, läuft die Vorführung dort weiter, ohne Messwerte.
