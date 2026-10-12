#!/bin/bash
# Messstand starten (macOS). Doppelklick genügt.
# Andere Station: ./start.command stations/spark.yaml
cd "$(dirname "$0")" || exit 1
KONFIG="${1:-stations/macmini.yaml}"

if ! command -v uv >/dev/null 2>&1; then
  echo
  echo "  uv ist nicht installiert oder nicht im Pfad."
  echo "  Installation: brew install uv"
  echo
  read -r -p "  Mit der Eingabetaste schliessen "
  exit 1
fi

if [ ! -f "$KONFIG" ]; then
  echo
  echo "  Konfigurationsdatei nicht gefunden: $KONFIG"
  echo "  Vorhanden sind:"
  ls stations/*.yaml 2>/dev/null | sed 's/^/    /'
  echo
  read -r -p "  Mit der Eingabetaste schliessen "
  exit 1
fi

uv run messstand --config "$KONFIG"
echo
read -r -p "  Messstand beendet. Mit der Eingabetaste schliessen "
