"""Stationstest: Läuft auf diesem Gerät alles, und wie gut liest es Fotos?

Spricht mit dem laufenden Messstand (erst starten, dann dieses Skript):

    uv run messstand --config stations/macmini.yaml        # Fenster 1
    uv run python tools/stationstest.py                    # Fenster 2

1. Zeigt Laufzeiten und Modelle der Station: erreichbar, vorhanden, fehlt.
2. Prüft die Spark-Reiter (OCR, Sprache), falls die Station sie hat.
3. Lässt die Beispielfotos aus „Foto → Daten“ durch jedes vorhandene Modell
   laufen (vorher vorgeladen, damit die Ladezeit nicht mitzählt) und schreibt
   eine Tabelle plus CSV nach results/. Die Läufe stehen auch im Reiter
   „Ergebnisse“ der Oberfläche.

Optionen:
    --nur-status          nur Schritt 1 und 2
    --modell ID           nur dieses Modell (mehrfach möglich)
    --url URL             anderer Messstand (Standard http://127.0.0.1:8765)
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

WURZEL = Path(__file__).resolve().parents[1]
FOTOS = WURZEL / "presets" / "fotos"
RESULTS = WURZEL / "results"


def zeile(*teile) -> None:
    print(*teile, flush=True)


def de(wert: float | None, stellen: int = 1) -> str:
    return "–" if wert is None else f"{wert:.{stellen}f}".replace(".", ",")


def status(c: httpx.Client) -> dict:
    s = c.get("/api/status").json()
    zeile(f"\n{s['station']['name']} — {s['station']['geraet']}\n")
    for b in s["backends"]:
        zeile(f"  [{'ok ' if b['online'] else 'AUS'}] {b['label']}  ({b['url']})")
        for m in b["modelle"]:
            zeile(f"        {'+' if m['vorhanden'] else '-'} {m['label']}" + ("" if m["vorhanden"] else "   (fehlt)"))
    e = s.get("embedding")
    if e:
        ok = e["online"] and e["vorhanden"]
        zeile(f"  [{'ok ' if ok else 'AUS'}] Einbettung {e['modell']}" + ("" if ok else "   (Reiter Dokumente geht nicht)"))
    if s.get("ocr"):
        o = c.get("/api/ocr/status").json()
        zeile(f"  [{'ok ' if o.get('online') else 'AUS'}] OCR-Werkzeug" + ("" if o.get("online") else "   (spark/spark-modus.sh ocr)"))
    if s.get("sprache"):
        p = c.get("/api/sprache/status").json()
        zeile(f"  [{'ok ' if p.get('bereit') else 'AUS'}] Spracherkennung, Sprecher {'ja' if p.get('sprecher') else 'nein'}"
              + ("" if p.get("bereit") else "   (spark/spark-modus.sh sprache)"))
    zeile()
    return s


def kann_bilder(backend: dict, modell: str) -> bool | None:
    """Bei Ollama nachfragen; bei anderen Laufzeiten unbekannt (None)."""
    if backend.get("typ") != "ollama":
        return None
    try:
        info = httpx.post(f"{backend['url'].rstrip('/')}/api/show", json={"model": modell}, timeout=10.0).json()
    except (httpx.HTTPError, ValueError):
        return None
    faehig = info.get("capabilities")
    return None if faehig is None else "vision" in faehig


def foto_lesen(c: httpx.Client, backend: str, modell: str, beispiel: dict) -> dict:
    """Ein Foto über den Messstand lesen lassen; SSE auswerten."""
    b64 = base64.b64encode((FOTOS / beispiel["datei"]).read_bytes()).decode()
    rumpf = {"backend": backend, "modell": modell, "vorlage": beispiel["vorlage"],
             "bild_b64": b64, "mime": "image/jpeg", "beispiel": beispiel["datei"]}
    ergebnis: dict = {"fehler": None, "messung": None, "bewertung": None, "json": False}
    start = time.perf_counter()
    with c.stream("POST", "/api/foto/lesen", json=rumpf, timeout=httpx.Timeout(900.0, connect=10.0)) as antwort:
        if antwort.status_code != 200:
            ergebnis["fehler"] = f"Fehlercode {antwort.status_code}: {antwort.read().decode(errors='replace')[:200]}"
            return ergebnis
        for roh in antwort.iter_lines():
            if not roh.startswith("data:"):
                continue
            e = json.loads(roh[5:])
            if e["art"] == "fehler":
                ergebnis["fehler"] = e.get("nachricht", "") + (f" ({e['detail'][:150]})" if e.get("detail") else "")
            elif e["art"] == "messung":
                ergebnis["messung"] = e["messung"]
            elif e["art"] == "auswertung":
                ergebnis["json"] = e.get("daten") is not None
                ergebnis["bewertung"] = e.get("bewertung")
    ergebnis["wand_s"] = time.perf_counter() - start
    return ergebnis


def main() -> int:
    # Windows-Konsolen mit alter Codepage: Sonderzeichen ersetzen statt abbrechen.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    zerleger = argparse.ArgumentParser(description="Stationstest für den Messstand")
    zerleger.add_argument("--url", default="http://127.0.0.1:8765")
    zerleger.add_argument("--modell", action="append", help="nur dieses Modell (mehrfach möglich)")
    zerleger.add_argument("--nur-status", action="store_true")
    args = zerleger.parse_args()

    try:
        c = httpx.Client(base_url=args.url, timeout=30.0)
        s = status(c)
    except httpx.HTTPError:
        zeile(f"\nDer Messstand antwortet unter {args.url} nicht. Erst starten:\n"
              "  uv run messstand --config stations/<station>.yaml\n")
        return 2
    if args.nur_status:
        return 0

    beispiele = c.get("/api/foto/vorlagen").json()["beispiele"]
    kandidaten = []
    for b in s["backends"]:
        if not b["online"]:
            continue
        for m in b["modelle"]:
            if not m["vorhanden"] or (args.modell and m["id"] not in args.modell):
                continue
            # Modelle ohne Bildverstaendnis gar nicht erst laden (GPT-OSS 120B: 65 GB umsonst).
            if kann_bilder(b, m["id"]) is False:
                zeile(f"  übersprungen, kann keine Bilder: {m['label']}")
                continue
            kandidaten.append((b["id"], b["label"], m["id"], m["label"]))
    if not kandidaten:
        zeile("Kein vorhandenes Modell gefunden (oder --modell passt auf keines).")
        return 1

    zeile(f"Foto → Daten: {len(beispiele)} Beispielfotos × {len(kandidaten)} Modelle\n")
    zeilen_csv = []
    gesamt = []
    for backend, backend_label, modell, modell_label in kandidaten:
        zeile(f"— {modell_label} ({backend_label})")
        vorladen = c.post("/api/warmup", json={"backend": backend, "modell": modell}, timeout=900.0).json()
        if not vorladen.get("ok"):
            zeile(f"    lässt sich nicht laden: {vorladen.get('detail') or vorladen.get('nachricht')}\n")
            continue
        punkte = von = 0
        zeiten = []
        for b in beispiele:
            e = foto_lesen(c, backend, modell, b)
            m = e["messung"] or {}
            bew = e["bewertung"] or {}
            if e["fehler"] and not e["json"]:
                text = f"Fehler: {e['fehler']}"
            elif not e["json"]:
                text = "kein gültiges JSON (kann das Modell Bilder lesen?)"
            else:
                text = f"{bew.get('punkte', 0):>2} von {bew.get('von', 0):>2} richtig"
            punkte += bew.get("punkte", 0)
            von += bew.get("von", 0)
            if m.get("total_s"):
                zeiten.append(m["total_s"])
            zeile(f"    {b['titel']:<26} {text:<44} erstes Zeichen {de(m.get('ttft_s'), 2):>6} s   gesamt {de(m.get('total_s')):>6} s")
            zeilen_csv.append({
                "station": s["station"]["name"], "geraet": s["station"]["geraet"], "laufzeit": backend_label,
                "modell": modell_label, "foto": b["titel"], "richtig": bew.get("punkte"), "von": bew.get("von"),
                "erstes_zeichen_s": m.get("ttft_s"), "gesamt_s": m.get("total_s"),
                "schreibtempo_tps": m.get("decode_tps"), "fehler": e["fehler"] or ("" if e["json"] else "kein JSON"),
            })
        mittel = sum(zeiten) / len(zeiten) if zeiten else None
        gesamt.append((modell_label, punkte, von, mittel))
        zeile()

    zeile("Zusammenfassung")
    for name, p, v, mittel in gesamt:
        quote = f"{100 * p / v:.0f} %" if v else "–"
        zeile(f"  {name:<44} {p:>3} von {v:<3} ({quote:>5})   im Mittel {de(mittel)} s pro Foto")

    RESULTS.mkdir(exist_ok=True)
    schluessel = Path(s.get("quelle") or "station").stem
    ziel = RESULTS / f"stationstest-{schluessel}-{datetime.now():%Y%m%d-%H%M}.csv"
    with ziel.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(zeilen_csv[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(zeilen_csv)
    zeile(f"\nCSV: {ziel}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
