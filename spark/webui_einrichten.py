"""Open WebUI für den Workshop einrichten: nur die Modelle der Station anbieten.

Ollama auf dem Spark kennt auch Modelle, die neben dem Modus „alles“ den
Speicher sprengen (GPT-OSS 120B, Gemma 31B BF16, Nemotron 120B) und ein
Cloud-Modell (kimi-…:cloud), bei dem der Text das Haus verlässt. Open WebUI
zeigt ungefiltert alle. Dieses Skript setzt über die Admin-API eine
Freigabeliste: genau die Ollama-Modelle aus stations/spark.yaml.

Aufruf (aus dem Repo, Open WebUI muss laufen): uv run python spark/webui_einrichten.py
"""

import sys
from pathlib import Path

import httpx
import yaml

WEBUI = "http://127.0.0.1:3001"
STATION = Path(__file__).resolve().parent.parent / "stations" / "spark.yaml"


def main() -> int:
    station = yaml.safe_load(STATION.read_text(encoding="utf-8"))
    erlaubt = [m["id"] for b in station["backends"] if b["typ"] == "ollama" for m in b["modelle"]]

    with httpx.Client(base_url=WEBUI, timeout=30.0) as c:
        # Ohne Anmeldung (WEBUI_AUTH=False) gibt die Anmeldung den eingebauten Admin zurück.
        token = c.post("/api/v1/auths/signin", json={"email": "", "password": ""}).raise_for_status().json()["token"]
        kopf = {"Authorization": f"Bearer {token}"}

        ollama = c.get("/ollama/config", headers=kopf).raise_for_status().json()
        konfig = {str(i): {**ollama.get("OLLAMA_API_CONFIGS", {}).get(str(i), {}), "enable": True, "model_ids": erlaubt}
                  for i in range(len(ollama["OLLAMA_BASE_URLS"]))}
        c.post("/ollama/config/update", headers=kopf, json={
            "ENABLE_OLLAMA_API": True,
            "OLLAMA_BASE_URLS": ollama["OLLAMA_BASE_URLS"],
            "OLLAMA_API_CONFIGS": konfig,
        }).raise_for_status()

        modelle = [m["id"] for m in c.get("/api/models", headers=kopf).raise_for_status().json()["data"]]
    verboten = sorted(set(modelle) - set(erlaubt) - {"google/gemma-4-26b-a4b-it"})
    print("Open WebUI bietet an:", ", ".join(modelle) or "(noch nichts – laufen Ollama und vLLM?)")
    if verboten:
        print("Unerwartet sichtbar:", ", ".join(verboten), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
