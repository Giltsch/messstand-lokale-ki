# Station 3: DGX Spark

Der gemeinsame Speicher (121 GB für GPU und CPU) reicht nicht für alles
gleichzeitig; läuft er voll, friert die Maschine ein. Darum läuft immer ein
Modus; `spark-modus.sh` schaltet um. Für den Workshop reicht `alles`: Damit
sind alle Reiter des Messstands gleichzeitig bereit, ohne Umschalten.

| Modus | Was läuft | Speicher (grob) |
|---|---|---|
| `alles` | vLLM mit Gemma 4 26B NVFP4 (:8004), LawAI mit LightOnOCR-2 (:8000) und Oberfläche (:8080), Whisper large-v3-turbo (:8002), Sprecher-Dienst TitaNet (:8003), Open WebUI als Chat (:3001), Ollama nach Bedarf | ~55 GB plus Ollama (Budget 40 GB) |
| `bild` | alles oben aus, dann das FLUX-Studio (BFL-Demonstrator, :7860) mit Upsampler und Prüfer | ~75 GB |
| `ocr` | LawAI wie im Alltag: LightOnOCR-2 (:8000) und Qwen3.8 27B als Prüfer (:8001) | ~66 GB |

```
spark/spark-modus.sh alles
spark/spark-modus.sh status
```

Im Modus `alles` übernimmt das eine Gemma in vLLM drei Aufgaben: den
Vergleich „Ollama gegen vLLM“ und den Lasttest, die Notizen im Reiter
„Sprache“ und den Prüfer und Zweitleser von LawAI. Der Qwen-Prüfer (39 GB)
bleibt aus. Dafür legt `spark-modus.sh` Laufzeit-Drop-ins unter
`$XDG_RUNTIME_DIR/systemd/user/lawai-*.service.d/` an und sperrt
`lawai-judge` per Startbedingung im Drop-in (gilt bis zum nächsten Neustart). LawAIs
eigene Einstellungen in `~/.config/lawai/env` bleiben unberührt; `ocr` und
`bild` räumen die Drop-ins wieder weg.

GPT-OSS 120B (65 GB) passt neben `alles` nicht mehr und ist aus
`stations/spark.yaml` entfernt.

Open WebUI (`webui-starten.sh`, http://127.0.0.1:3001) ist ein Chat zum freien
Ausprobieren, ohne Anmeldung. Angeboten werden nur die Ollama-Modelle aus
`stations/spark.yaml` und vLLM-Gemma: `webui_einrichten.py` setzt die
Freigabeliste, damit niemand GPT-OSS 120B, Nemotron oder ein Cloud-Modell
anklickt.

Der Messstand selbst (Port 8765) läuft in jedem Modus weiter.

Für den Workshoptag: Spickzettel in [WORKSHOPTAG.md](WORKSHOPTAG.md).

## Ohne Netz

Whisper, vLLM-Gemma und der Sprecher-Dienst laden Modelle nur aus dem lokalen
Cache (`HF_HUB_OFFLINE=1`). Für den allerersten Download einmal mit `ONLINE=1`
starten, zum Beispiel `ONLINE=1 spark/whisper-starten.sh`.

## Dateien

| Datei | Zweck |
|---|---|
| `spark-modus.sh` | Modus umschalten, Status zeigen |
| `vllm-starten.sh` | vLLM-Gemma im NVIDIA-Container |
| `webui-starten.sh`, `webui_einrichten.py` | Open WebUI als Chat, nur mit den Modellen der Station |
| `whisper-starten.sh` | Whisper im NVIDIA-Container |
| `sprecher_dienst.py` | Stimmabdrücke; braucht die Python-Umgebung aus `speech_to_text` (`SPRECHER_PYTHON`) |
| `logs/` | Protokolle der Dienste (nicht im Repo) |
