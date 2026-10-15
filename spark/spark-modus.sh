#!/usr/bin/env bash
# Betriebsmodus des DGX Spark für den Workshop umschalten.
# Der gemeinsame Speicher (121 GB für GPU und CPU) reicht nicht für alles
# gleichzeitig; läuft er voll, friert die Maschine ein. Darum immer nur ein Modus.
#
#   spark/spark-modus.sh ocr        eigenes OCR (LawAI: LightOnOCR + Qwen3.8 27B + Oberfläche :8080)
#   spark/spark-modus.sh gross      nur GPT-OSS 120B in Ollama, alles andere aus
#   spark/spark-modus.sh sprache    Whisper (Docker, :8002), Sprecher-Dienst (:8003) plus GPT-OSS 120B
#                               für den Reiter „Sprache“
#   spark/spark-modus.sh vergleich  Messstand: vLLM-Gemma (Docker, :8000) plus kleine Ollama-Modelle
#   spark/spark-modus.sh status     was gerade läuft, wie viel Speicher frei ist
#
# Aufruf aus dem Repo: spark/spark-modus.sh <modus>
# Der Messstand selbst (Port 8765) läuft in jedem Modus weiter; Reiter, deren
# Laufzeit gerade aus ist, zeigen das an.
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
LOGS="$HIER/logs"; mkdir -p "$LOGS"
# Python mit NeMo fuer den Sprecher-Dienst (aus dem Projekt speech_to_text)
SPRECHER_PYTHON="${SPRECHER_PYTHON:-$HOME/Dokumente/Projekte/speech_to_text/.venv/bin/python}"
OLLAMA=http://127.0.0.1:11434

ollama_leeren() {  # $1: Modell, das geladen bleiben darf
  local behalten=${1:-} modelle
  modelle=$(curl -s "$OLLAMA/api/ps" | python3 -c 'import json,sys; print("\n".join(m["name"] for m in json.load(sys.stdin).get("models", [])))' 2>/dev/null || true)
  for m in $modelle; do
    [ "$m" = "$behalten" ] && continue
    echo "  Ollama entlädt $m"
    curl -s "$OLLAMA/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null
  done
}

lawai_aus()  { echo "  OCR-Dienste anhalten"; systemctl --user stop lawai-app lawai-judge lawai-ocr; }
vllm_aus()   { docker stop messstand-vllm >/dev/null 2>&1 && echo "  vLLM-Container angehalten" || true; }
whisper_aus() {
  docker stop messstand-whisper >/dev/null 2>&1 && echo "  Whisper-Container angehalten" || true
  fuser -k 8003/tcp >/dev/null 2>&1 && echo "  Sprecher-Dienst angehalten" || true
}
gross_laden() {
  echo "  GPT-OSS 120B laden (rund 65 GB, bleibt geladen)"
  curl -s "$OLLAMA/api/generate" -d '{"model":"gpt-oss:120b","prompt":"","keep_alive":-1}' >/dev/null
  echo "  GPT-OSS 120B bereit."
}

warten_auf() {  # URL, Sekunden
  local url=$1 frist=$2 t=0
  until curl -sf "$url" >/dev/null; do
    sleep 3; t=$((t + 3))
    if [ "$t" -ge "$frist" ]; then echo "  $url antwortet nach ${frist}s nicht."; return 1; fi
  done
}

status() {
  echo "Speicher:"; free -h | sed -n 1,2p
  echo; echo "OCR-Dienste:"
  for d in lawai-ocr lawai-judge lawai-app; do printf "  %-12s %s\n" "$d" "$(systemctl --user is-active $d)"; done
  echo; echo "vLLM-Container:    $(docker ps --filter name=messstand-vllm --format '{{.Status}}' 2>/dev/null || true)"
  echo "Whisper-Container: $(docker ps --filter name=messstand-whisper --format '{{.Status}}' 2>/dev/null || true)"
  echo "Sprecher-Dienst:   $(curl -sf http://127.0.0.1:8003/health >/dev/null && echo läuft || echo aus)"
  echo; echo "Ollama geladen:"
  curl -s "$OLLAMA/api/ps" | python3 -c 'import json,sys; [print("  %-28s %5.1f GB" % (m["name"], m["size"]/1e9)) for m in json.load(sys.stdin).get("models", [])]' 2>/dev/null || echo "  (Ollama antwortet nicht)"
}

case "${1:-status}" in
  ocr)
    vllm_aus; whisper_aus; ollama_leeren; sleep 3
    # Nacheinander: Prüfer und Oberfläche warten beim Start auf den OCR-Server,
    # und systemd bricht dieses Warten sonst nach 90 s ab.
    echo "  OCR-Server starten"
    systemctl --user start --no-block lawai-ocr
    warten_auf http://127.0.0.1:8000/health 600 || exit 1
    echo "  Prüfer (Qwen3.8 27B) und Oberfläche starten"
    systemctl --user start --no-block lawai-judge lawai-app
    warten_auf http://127.0.0.1:8001/health 900 || exit 1
    until systemctl --user is-active --quiet lawai-app; do sleep 3; done
    echo "  OCR bereit."
    ;;
  gross)
    lawai_aus; vllm_aus; whisper_aus; ollama_leeren gpt-oss:120b; sleep 5
    gross_laden
    ;;
  sprache)
    lawai_aus; vllm_aus; ollama_leeren gpt-oss:120b; sleep 5
    if ! curl -sf http://127.0.0.1:8002/v1/models >/dev/null; then
      echo "  Whisper-Container starten, Protokoll in $LOGS/whisper.log"
      nohup "$HIER/whisper-starten.sh" >"$LOGS/whisper.log" 2>&1 &
      warten_auf http://127.0.0.1:8002/v1/models 900 && echo "  Whisper bereit."
    fi
    if ! curl -sf http://127.0.0.1:8003/health >/dev/null; then
      echo "  Sprecher-Dienst starten (NVIDIA TitaNet), Protokoll in $LOGS/sprecher.log"
      nohup "$SPRECHER_PYTHON" "$HIER/sprecher_dienst.py" >"$LOGS/sprecher.log" 2>&1 &
      warten_auf http://127.0.0.1:8003/health 120 && echo "  Sprecher-Dienst bereit."
    fi
    gross_laden
    ;;
  vergleich)
    lawai_aus; whisper_aus; ollama_leeren; sleep 3
    echo "  vLLM-Container starten, Protokoll in $LOGS/vllm.log"
    nohup "$HIER/vllm-starten.sh" >"$LOGS/vllm.log" 2>&1 &
    warten_auf http://127.0.0.1:8000/v1/models 900 && echo "  vLLM bereit."
    ;;
  status) ;;
  *) echo "Unbekannter Modus: $1 (ocr | gross | sprache | vergleich | status)"; exit 2 ;;
esac
echo; status
