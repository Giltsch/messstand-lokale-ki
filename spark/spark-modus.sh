#!/usr/bin/env bash
# Betriebsmodus des DGX Spark für den Workshop umschalten.
# Der gemeinsame Speicher (121 GB für GPU und CPU) reicht nicht für alles
# gleichzeitig; läuft er voll, friert die Maschine ein. Darum immer nur ein Modus.
#
#   spark/spark-modus.sh alles    der ganze Messstand auf einmal, ohne Umschalten:
#                                 vLLM-Gemma (:8004), LawAI-OCR mit LightOnOCR (:8000)
#                                 und Oberfläche (:8080), Whisper (:8002),
#                                 Sprecher-Dienst (:8003), Ollama für die kleinen Modelle,
#                                 Open WebUI als Chat (:3001).
#                                 Gemma ist zugleich Prüfer und Zweitleser des OCR.
#   spark/spark-modus.sh bild     alles oben aus, dann das FLUX-Studio (BFL-Demonstrator, :7860)
#   spark/spark-modus.sh ocr      LawAI wie im Alltag: LightOnOCR + Qwen3.8 27B als Prüfer,
#                                 ohne Messstand-Dienste
#   spark/spark-modus.sh status   was gerade läuft, wie viel Speicher frei ist
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
GEMMA=google/gemma-4-26b-a4b-it
# Laufzeit-Drop-ins: verschwinden beim Neustart, LawAIs eigene Konfiguration bleibt unberührt
DROPIN="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/systemd/user"

ollama_leeren() {
  local modelle
  modelle=$(curl -s "$OLLAMA/api/ps" | python3 -c 'import json,sys; print("\n".join(m["name"] for m in json.load(sys.stdin).get("models", [])))' 2>/dev/null || true)
  for m in $modelle; do
    echo "  Ollama entlädt $m"
    curl -s "$OLLAMA/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null
  done
}

lawai_aus()  { echo "  OCR-Dienste anhalten"; systemctl --user stop lawai-app lawai-judge lawai-ocr; }
flux_aus()   { systemctl --user stop flux-studio flux-judge flux-pup 2>/dev/null || true; }
vllm_aus()   { docker stop messstand-vllm >/dev/null 2>&1 && echo "  vLLM-Container angehalten" || true; }
webui_aus()  { docker stop messstand-webui >/dev/null 2>&1 && echo "  Open WebUI angehalten" || true; }
whisper_aus() {
  docker stop messstand-whisper >/dev/null 2>&1 && echo "  Whisper-Container angehalten" || true
  fuser -k 8003/tcp >/dev/null 2>&1 && echo "  Sprecher-Dienst angehalten" || true
}

# LawAI für den Workshop: LightOnOCR mit kleinerem Anteil (1B-Modell, 0,08 ≈ 10 GB),
# Prüfer, Zweitleser und Antworten über das Messstand-Gemma, Qwen-Prüfer gesperrt
# (lawai-app zieht ihn sonst per Wants= mit hoch). Gesperrt per Startbedingung im
# Drop-in: „mask --runtime“ greift nicht, weil die Unit in ~/.config Vorrang hat.
lawai_workshop() {
  mkdir -p "$DROPIN/lawai-ocr.service.d" "$DROPIN/lawai-app.service.d" "$DROPIN/lawai-judge.service.d"
  printf '[Service]\nEnvironment=OCR_MEM=0.08\n' >"$DROPIN/lawai-ocr.service.d/messstand.conf"
  printf '[Service]\nEnvironment=JUDGE_ENDPOINT=http://localhost:8004/v1/chat/completions JUDGE_MODEL=%s\nEnvironment=LAWAI_LLM_BASE=http://localhost:8004/v1 LAWAI_LLM_MODEL=%s\n' \
    "$GEMMA" "$GEMMA" >"$DROPIN/lawai-app.service.d/messstand.conf"
  printf '[Unit]\n# Messstand-Modus „alles“: Prüfer ist Gemma auf :8004\nConditionPathExists=/messstand-alles-qwen-aus\n' \
    >"$DROPIN/lawai-judge.service.d/messstand.conf"
  systemctl --user daemon-reload
}
lawai_alltag() {
  rm -f "$DROPIN/lawai-ocr.service.d/messstand.conf" "$DROPIN/lawai-app.service.d/messstand.conf" \
    "$DROPIN/lawai-judge.service.d/messstand.conf"
  systemctl --user daemon-reload
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
  [ -f "$DROPIN/lawai-app.service.d/messstand.conf" ] && echo "  (Workshop: Prüfer ist Gemma auf :8004)"
  echo; echo "vLLM-Container:    $(docker ps --filter name=messstand-vllm --format '{{.Status}}' 2>/dev/null || true)"
  echo "Whisper-Container: $(docker ps --filter name=messstand-whisper --format '{{.Status}}' 2>/dev/null || true)"
  echo "Sprecher-Dienst:   $(curl -sf http://127.0.0.1:8003/health >/dev/null && echo läuft || echo aus)"
  echo "Open WebUI:        $(curl -sf http://127.0.0.1:3001/health >/dev/null && echo "läuft (http://127.0.0.1:3001)" || echo aus)"
  echo "FLUX-Studio:       $(systemctl --user is-active flux-studio)"
  echo; echo "Ollama geladen:"
  curl -s "$OLLAMA/api/ps" | python3 -c 'import json,sys; [print("  %-28s %5.1f GB" % (m["name"], m["size"]/1e9)) for m in json.load(sys.stdin).get("models", [])]' 2>/dev/null || echo "  (Ollama antwortet nicht)"
}

case "${1:-status}" in
  alles)
    flux_aus; lawai_aus; ollama_leeren; sleep 3
    lawai_workshop
    # Nacheinander: vLLM prüft beim Start, wie viel Speicher frei ist, und zwei
    # gleichzeitige Starts sehen beide denselben freien Speicher.
    echo "  OCR-Server (LightOnOCR) starten"
    systemctl --user start --no-block lawai-ocr
    warten_auf http://127.0.0.1:8000/health 600 || exit 1
    if ! curl -sf http://127.0.0.1:8004/v1/models >/dev/null; then
      echo "  vLLM-Gemma starten, Protokoll in $LOGS/vllm.log"
      nohup "$HIER/vllm-starten.sh" >"$LOGS/vllm.log" 2>&1 &
      warten_auf http://127.0.0.1:8004/v1/models 900 || exit 1
    fi
    if ! curl -sf http://127.0.0.1:8002/v1/models >/dev/null; then
      echo "  Whisper starten, Protokoll in $LOGS/whisper.log"
      nohup "$HIER/whisper-starten.sh" >"$LOGS/whisper.log" 2>&1 &
      warten_auf http://127.0.0.1:8002/v1/models 900 || exit 1
    fi
    if ! curl -sf http://127.0.0.1:8003/health >/dev/null; then
      echo "  Sprecher-Dienst starten (NVIDIA TitaNet), Protokoll in $LOGS/sprecher.log"
      nohup "$SPRECHER_PYTHON" "$HIER/sprecher_dienst.py" >"$LOGS/sprecher.log" 2>&1 &
      warten_auf http://127.0.0.1:8003/health 120 || exit 1
    fi
    echo "  OCR-Oberfläche starten"
    systemctl --user start lawai-app
    echo "  Open WebUI starten"
    "$HIER/webui-starten.sh" | sed 's/^/  /'
    echo "  Alles bereit."
    ;;
  bild)
    lawai_aus; vllm_aus; whisper_aus; webui_aus; ollama_leeren; lawai_alltag; sleep 5
    echo "  FLUX-Studio starten (lädt FLUX, danach Upsampler und Prüfer; dauert einige Minuten)"
    systemctl --user start flux-studio
    warten_auf http://127.0.0.1:7860/api/status 900 && echo "  FLUX-Studio antwortet auf :7860."
    ;;
  ocr)
    flux_aus; vllm_aus; whisper_aus; webui_aus; ollama_leeren; lawai_aus; lawai_alltag; sleep 3
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
  status) ;;
  *) echo "Unbekannter Modus: $1 (alles | bild | ocr | status)"; exit 2 ;;
esac
echo; status
