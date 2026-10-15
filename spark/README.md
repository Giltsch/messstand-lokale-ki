# Station 3: DGX Spark

Der gemeinsame Speicher (121 GB für GPU und CPU) reicht nicht für alles
gleichzeitig. Darum läuft immer ein Modus; `spark-modus.sh` schaltet um.

| Modus | Was läuft | Reiter | Umschalten dauert (gemessen 15.10.2026) |
|---|---|---|---|
| `ocr` | LawAI: LightOnOCR-2 (:8000), Qwen3.8 27B als Prüfer (:8001), Oberfläche (:8080) | OCR | rund 5,5 min aus dem Kaltstart |
| `sprache` | Whisper large-v3-turbo (:8002), Sprecher-Dienst TitaNet (:8003), GPT-OSS 120B | Sprache | rund 3,5 min |
| `gross` | nur GPT-OSS 120B in Ollama | Aufgabe, Vergleich, Last | unter 30 s, wenn es schon geladen war |
| `vergleich` | vLLM mit Gemma 4 26B NVFP4 (:8000) plus Ollama-Modelle | Vergleich „Ollama gegen vLLM“, Last | rund 4,5 min |

```
spark/spark-modus.sh status
spark/spark-modus.sh sprache
```

Der Messstand selbst (Port 8765) läuft in jedem Modus weiter.

## Ohne Netz

Whisper, vLLM-Gemma und der Sprecher-Dienst laden Modelle nur aus dem lokalen
Cache (`HF_HUB_OFFLINE=1`). Für den allerersten Download einmal mit `ONLINE=1`
starten, zum Beispiel `ONLINE=1 spark/whisper-starten.sh`.

## Dateien

| Datei | Zweck |
|---|---|
| `spark-modus.sh` | Modus umschalten, Status zeigen |
| `vllm-starten.sh` | vLLM-Gemma im NVIDIA-Container |
| `whisper-starten.sh` | Whisper im NVIDIA-Container |
| `sprecher_dienst.py` | Stimmabdrücke; braucht die Python-Umgebung aus `speech_to_text` (`SPRECHER_PYTHON`) |
| `logs/` | Protokolle der Dienste (nicht im Repo) |
