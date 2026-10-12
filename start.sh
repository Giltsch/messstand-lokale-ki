#!/bin/bash
# Messstand starten (Linux, zum Beispiel DGX Spark mit DGX OS).
# Andere Station: ./start.sh stations/macmini.yaml
cd "$(dirname "$0")" || exit 1
KONFIG="${1:-stations/spark.yaml}"

if ! command -v uv >/dev/null 2>&1; then
  echo
  echo "  uv ist nicht installiert oder nicht im Pfad."
  echo "  Installation: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if [ ! -f "$KONFIG" ]; then
  echo
  echo "  Konfigurationsdatei nicht gefunden: $KONFIG"
  echo "  Vorhanden sind:"
  ls stations/*.yaml 2>/dev/null | sed 's/^/    /'
  exit 1
fi

exec uv run messstand --config "$KONFIG"
