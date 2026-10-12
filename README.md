# Messstand: lokale KI vergleichen

Werkzeug für den MDZ-Workshop „KI auf eigener Hardware“. Gleiche Aufgabe,
verschiedene Laufzeiten und Modelle, saubere Messwerte, live am Beamer sichtbar.

Alles läuft lokal: der Server bindet ausschließlich an `127.0.0.1`, es gibt
keine externen Aufrufe, keine CDNs, keine Telemetrie. Das Werkzeug funktioniert
im Flugmodus.

## Start

```
uv run messstand --config stations/macmini.yaml
```

Weitere Stationen: `stations/laptop.yaml`, `stations/spark.yaml`.
`stations/dev.yaml` ist nur zum Entwickeln gedacht.

Optionen: `--port` (Standard 8765), `--no-browser`.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `src/messstand/` | Server: FastAPI, Konfiguration, Backends, Messung |
| `static/` | Oberfläche: eine HTML-Datei, CSS, Vanilla-JS als ES-Module |
| `stations/` | Eine YAML-Datei pro Station. Alle Unterschiede stehen hier. |
| `presets/` | Aufgabenkarte und Beispieltext des Workshops |
| `results/` | CSV-Ausgaben (nicht im Repo) |

Mehr zum Aufbau jeder Station steht in `docs/aufbau.md` (folgt mit M5).
