# Workshoptag auf dem Spark: Spickzettel

Alle Befehle aus dem Repo-Ordner:

```
cd ~/Dokumente/Projekte/local_ai_workshop/messstand-lokale-ki
```

## Ablauf

| Wann | Befehl | Dauer | Danach läuft |
|---|---|---|---|
| Morgens, vor dem Einlass | `spark/spark-modus.sh alles` | ~8 min | ganzer Messstand, alle Reiter, Open WebUI |
| Messstand öffnen | `./start.sh` | Sekunden | Oberfläche im Browser |
| Pause vor der Werkstatt-Demo | `spark/spark-modus.sh bild` | ~10 min bis komplett | FLUX-Studio (Werkstatt) |
| Danach wieder zurück | `spark/spark-modus.sh alles` | ~8 min | wie morgens |
| Jederzeit | `spark/spark-modus.sh status` | sofort | zeigt, was läuft und wie viel Speicher frei ist |

Beim Wechsel zu `bild` ist FLUX nach knapp 3 min geladen, der Upsampler
nach ~5,5 min, der Prüfer erst nach ~9,5 min. Die Werkstatt also erst zeigen,
wenn `status` alle drei FLUX-Dienste als aktiv meldet.

## Adressen

| Was | Adresse | Modus |
|---|---|---|
| Messstand | http://127.0.0.1:8765 | immer (läuft in jedem Modus weiter) |
| Open WebUI (Chat zum Ausprobieren) | http://127.0.0.1:3001 | `alles` |
| LawAI-OCR direkt | http://127.0.0.1:8080 (Passwort in `~/.config/lawai/env`) | `alles` |
| Werkstatt (FLUX-Studio) | http://127.0.0.1:7860 | `bild` |

Im Messstand: Reiter **Sprache** (Mitschrift, live), **OCR**, **Foto → Daten**,
**Vergleich**, **Last**, **Dokumente**. Alles im Modus `alles` gleichzeitig.

## Kurz prüfen, bevor es losgeht

1. `spark/spark-modus.sh status`: alles „läuft“ bzw. „Up“, `lawai-judge` **inactive** (gewollt).
2. Messstand öffnen, Reiter **Sprache** → „Mikrofon prüfen“: Balken schlägt grün aus.
3. Einmal 20 Sekunden sprechen: die Zeile „Gerade gesprochen“ erscheint, nach der Pause die Mitschrift.
4. Browser einmal mit **Strg+Umschalt+R** neu laden, falls die Seite schon länger offen war.

## Wenn etwas hakt

| Zeichen | Was tun |
|---|---|
| Ein Reiter sagt „Starten mit: …“ | Dienst ist aus: `spark/spark-modus.sh alles` (startet nur, was fehlt) |
| Mitschrift seltsam, Wörter fehlen | `tail -20 spark/logs/messstand.log` zeigt jedes erkannte Stück mit Text |
| Messstand-Seite lädt nicht | `./start.sh` (er läuft unabhängig von den Modi) |
| Maschine wird zäh, Speicher knapp | `spark/spark-modus.sh status`; nie zusätzlich große Modelle laden |
| Ein Dienst startet nicht | Protokolle in `spark/logs/` (`vllm.log`, `whisper.log`, `sprecher.log`) |

## Nicht machen

- **Keine großen Modelle nachladen** (GPT-OSS 120B, Gemma 31B BF16, Nemotron): neben `alles`
  läuft der Speicher voll, und der Spark friert ein. Open WebUI bietet sie absichtlich nicht an.
- **`lawai-judge` nicht von Hand starten**: im Modus `alles` prüft Gemma; Qwen bräuchte 39 GB extra.
- **Kein `pkill -f "…"`** mit einem Muster, das in der eigenen Befehlszeile steht: das trifft
  die eigene Shell. Dienste über `spark-modus.sh` oder per Port beenden: `kill $(fuser 8765/tcp)`.
- **Werkstatt und Messstand nie gleichzeitig**: immer über `spark-modus.sh` umschalten.

## Wo was liegt

| Was | Wo |
|---|---|
| Messstand (Code, Stationen, diese Datei) | `~/Dokumente/Projekte/local_ai_workshop/messstand-lokale-ki`, GitHub `Giltsch/messstand-lokale-ki`, Branch `station-3-spark` |
| Werkstatt (FLUX-Studio) | `~/Dokumente/Projekte/bfl`, GitHub `Giltsch/bfl-werkstatt` (privat) |
| Werkstatt-Projekte, Backups | `~/Dokumente/Projekte/bfl/projects`, `~/Dokumente/Projekte/bfl-backups` |
| LawAI (OCR) | `~/Dokumente/Projekte/KILaw/LawAI` |
| Modi im Detail | [spark/README.md](README.md) |
