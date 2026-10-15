"""Reiter „Foto → Daten“: ein Foto lesen und feste Angaben als JSON liefern.

Laeuft auf jeder Station mit einem Bild-faehigen Modell (Gemma 4 kann das
in allen Groessen). Gemessen wird wie ueberall; zusaetzlich wird das Ergebnis
gegen eine Musterloesung bewertet, damit neben dem Tempo auch die Qualitaet
der Stationen vergleichbar ist.
"""

from __future__ import annotations

import json
import re
import uuid
from contextlib import aclosing
from pathlib import Path
from typing import Any, AsyncIterator

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .backends import params_aus_config
from .backends.base import DenkEvent, FehlerEvent, MessungEvent, TextEvent

SYSTEM = (
    "Sie lesen Fotos von Dokumenten und Schildern und geben die Angaben als JSON zurück. "
    "Sie schreiben nur, was auf dem Foto steht. Was fehlt oder unlesbar ist, wird null."
)


def laden(presets: Path) -> dict:
    datei = presets / "foto.yaml"
    if not datei.is_file():
        return {"vorlagen": [], "beispiele": []}
    return yaml.safe_load(datei.read_text(encoding="utf-8")) or {}


def prompt_bauen(vorlage: dict) -> str:
    def beschreibung(felder: list[dict], einzug: str = "  ") -> str:
        hinweise = {
            "datum": "Datum als JJJJ-MM-TT; ohne Jahr auf dem Foto als TT.MM.",
            "uhrzeit": "Uhrzeit als HH:MM",
            "betrag": "Zahl mit Punkt, ohne Währung",
            "zahl": "Zahl mit Punkt, ohne Einheit",
        }
        return "\n".join(
            f'{einzug}"{f["name"]}": {f["label"]}' + (f" ({hinweise[f['typ']]})" if f.get("typ") in hinweise else "")
            for f in felder
        )

    teile = [
        f"Lies das Foto ({vorlage['titel']}). Antworte ausschließlich mit einem JSON-Objekt mit diesen Schlüsseln:",
        beschreibung(vorlage["felder"]),
    ]
    liste = vorlage.get("liste")
    if liste:
        teile += [
            f'  "{liste["name"]}": Liste der {liste["label"]}, jeder Eintrag ein Objekt mit:',
            beschreibung(liste["felder"], "      "),
        ]
    teile.append("Kein Text vor oder nach dem JSON. Nichts erfinden.")
    return "\n".join(teile)


def json_aus(antwort: str) -> dict | None:
    """Das erste vollstaendige JSON-Objekt aus der Antwort ziehen."""
    antwort = re.sub(r"```(?:json)?", "", antwort)
    start = antwort.find("{")
    ende = antwort.rfind("}")
    if start < 0 or ende <= start:
        return None
    try:
        daten = json.loads(antwort[start : ende + 1])
    except json.JSONDecodeError:
        return None
    return daten if isinstance(daten, dict) else None


# ---------------------------------------------------------------- Bewertung


def _zahl(wert: Any) -> float | None:
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return float(wert)
    if not isinstance(wert, str):
        return None
    t = re.sub(r"[^\d,.\-]", "", wert)
    if "," in t and "." in t:  # 1.234,56
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _datum(wert: Any) -> tuple[int, int, int | None] | None:
    if not isinstance(wert, str):
        return None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", wert)
    if m:
        return int(m[3]), int(m[2]), int(m[1])
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.?\s*(\d{2,4})?", wert)
    if m:
        jahr = int(m[3]) if m[3] else None
        if jahr is not None and jahr < 100:
            jahr += 2000
        return int(m[1]), int(m[2]), jahr
    return None


def _norm(wert: Any) -> str:
    return re.sub(r"[^0-9a-zäöüß]", "", str(wert).lower().replace("ue", "ü").replace("ae", "ä").replace("oe", "ö"))


def stimmt(typ: str, wert: Any, muster: Any) -> bool:
    if wert is None or wert == "":
        return False
    if typ in ("betrag", "zahl"):
        a, b = _zahl(wert), _zahl(muster)
        return a is not None and b is not None and abs(a - b) < 0.006
    if typ == "datum":
        a, b = _datum(str(wert)), _datum(str(muster))
        if not a or not b:
            return False
        return a[:2] == b[:2] and (a[2] is None or b[2] is None or a[2] == b[2])
    if typ == "uhrzeit":
        a = re.search(r"(\d{1,2})[:.](\d{2})", str(wert))
        b = re.search(r"(\d{1,2})[:.](\d{2})", str(muster))
        return bool(a and b) and (int(a[1]), a[2]) == (int(b[1]), b[2])
    if typ == "kennung":
        return re.sub(r"[^0-9a-z]", "", str(wert).lower()) == re.sub(r"[^0-9a-z]", "", str(muster).lower())
    a, b = _norm(wert), _norm(muster)
    if not a or not b:
        return False
    # Tippfehler zaehlen als Fehler; egal sind nur Schreibweise, Leerzeichen
    # und Satzzeichen.
    # Mehr gelesen als im Muster steht ist in Ordnung („Säule 4 Diesel“ fuer
    # „Diesel“), weniger nur, wenn fast alles da ist.
    return b in a or (a in b and len(a) >= 0.7 * len(b))


def bewerten(vorlage: dict, daten: dict, muster: dict) -> dict:
    """Jede Angabe der Musterloesung ist ein Punkt, auch jedes Feld jeder Position."""
    felder = []
    for f in vorlage["felder"]:
        if f["name"] not in muster:
            continue
        wert = daten.get(f["name"])
        felder.append(
            {"name": f["name"], "label": f["label"], "wert": wert, "muster": muster[f["name"]],
             "ok": stimmt(f.get("typ", "text"), wert, muster[f["name"]])}
        )
    punkte = sum(f["ok"] for f in felder)
    von = len(felder)

    zeilen = []
    liste = vorlage.get("liste")
    if liste and liste["name"] in muster:
        gelesen = [e for e in (daten.get(liste["name"]) or []) if isinstance(e, dict)]
        frei = list(range(len(gelesen)))
        for erwartet in muster[liste["name"]]:
            # passenden gelesenen Eintrag suchen: der mit den meisten richtigen Feldern
            beste, beste_ok = None, []
            for i in frei:
                ok = [stimmt(lf.get("typ", "text"), gelesen[i].get(lf["name"]), erwartet[lf["name"]])
                      for lf in liste["felder"] if lf["name"] in erwartet]
                if sum(ok) > sum(beste_ok):
                    beste, beste_ok = i, ok
            if beste is not None:
                frei.remove(beste)
            anzahl = len([lf for lf in liste["felder"] if lf["name"] in erwartet])
            zeilen.append(
                {"muster": erwartet, "gelesen": gelesen[beste] if beste is not None else None,
                 "ok": beste_ok or [False] * anzahl}
            )
            punkte += sum(beste_ok)
            von += anzahl
        zusaetzlich = [gelesen[i] for i in frei]
    else:
        zusaetzlich = []
    return {"punkte": punkte, "von": von, "felder": felder, "liste": zeilen, "zusaetzlich": zusaetzlich}


# ---------------------------------------------------------------- Router


def router_bauen(zustand, presets: Path) -> APIRouter:
    router = APIRouter(prefix="/api/foto")
    cfg = zustand.cfg
    fotos = presets / "fotos"

    def daten() -> dict:
        return laden(presets)

    @router.get("/vorlagen")
    async def vorlagen() -> dict:
        d = daten()
        return {"vorlagen": d.get("vorlagen", []), "beispiele": d.get("beispiele", [])}

    @router.get("/bild/{name}")
    async def bild(name: str) -> FileResponse:
        pfad = (fotos / name).resolve()
        if not str(pfad).startswith(str(fotos.resolve())) or not pfad.is_file():
            raise HTTPException(404, "Beispielfoto nicht gefunden.")
        return FileResponse(pfad, headers={"Cache-Control": "max-age=3600"})

    @router.post("/lesen")
    async def lesen(rumpf: dict):
        from .main import strom, sse  # erst hier, sonst Kreisimport

        d = daten()
        vorlage = next((v for v in d.get("vorlagen", []) if v["id"] == rumpf.get("vorlage")), None)
        if vorlage is None:
            raise HTTPException(400, "Unbekannte Vorlage.")
        bild_b64 = rumpf.get("bild_b64") or ""
        if not bild_b64:
            raise HTTPException(400, "Es wurde kein Foto geschickt.")
        beispiel = next((b for b in d.get("beispiele", []) if b["datei"] == rumpf.get("beispiel")), None)
        backend_id = rumpf.get("backend", "")
        modell_id = rumpf.get("modell", "")
        backend, backend_cfg = zustand.backend_oder_fehler(backend_id)
        modell_cfg = backend_cfg.modell(modell_id)
        stapel = bool(rumpf.get("stapel"))

        params = params_aus_config(cfg.generierung, im_lasttest=stapel)
        params.thinking = False
        params.max_tokens = 1500
        prompt = prompt_bauen(vorlage)
        # Eindeutige Kennung vorn: sonst nimmt Ollama Prompt und Foto aus dem
        # Zwischenspeicher, und das Lesen des Fotos faellt aus der Messung.
        # Im echten Betrieb ist jedes Foto neu.
        nachrichten = [
            {"role": "system", "content": f"Anfrage {uuid.uuid4().hex[:8]}. {SYSTEM}"},
            {"role": "user", "content": prompt,
             "bilder": [{"b64": bild_b64, "mime": rumpf.get("mime") or "image/jpeg"}]},
        ]

        async def erzeugen() -> AsyncIterator[str]:
            await zustand.platz_schaffen(backend_id, modell_id)
            yield sse({"art": "start", "prompt": prompt, "system": SYSTEM})
            antwort = ""
            messung = None
            async with aclosing(backend.chat_stream(modell_id, nachrichten, params)) as ereignisse:
                async for e in ereignisse:
                    if isinstance(e, TextEvent):
                        antwort += e.text
                        yield sse({"art": "text", "text": e.text})
                    elif isinstance(e, DenkEvent):
                        yield sse({"art": "denken", "text": e.text})
                    elif isinstance(e, FehlerEvent):
                        yield sse({"art": "fehler", "nachricht": e.nachricht, "detail": e.detail})
                    elif isinstance(e, MessungEvent):
                        messung = e.messung
            gelesen = json_aus(antwort)
            # Ohne gueltiges JSON zaehlen alle Angaben als falsch, damit die Quote ehrlich bleibt.
            bewertung = bewerten(vorlage, gelesen or {}, beispiel["muster"]) if beispiel else None
            if messung is not None:
                zustand.warm.setdefault(backend_id, set()).add(modell_id)
                notiz = f"Foto {beispiel['titel'] if beispiel else 'eigenes'}"
                if bewertung:
                    notiz += f": {bewertung['punkte']} von {bewertung['von']} Angaben richtig"
                elif gelesen is None:
                    notiz += ": kein gültiges JSON"
                zeile = None
                if not stapel:
                    zeile = zustand.messreihe.hinzufuegen(
                        reiter="Foto",
                        backend_id=backend_id,
                        backend_label=backend_cfg.label,
                        modell_id=modell_id,
                        modell_label=modell_cfg.label if modell_cfg else modell_id,
                        messung=messung,
                        notiz=notiz,
                    ).fuer_oberflaeche()
                yield sse({"art": "messung", "messung": messung.dict(), "ergebnis": zeile})
            yield sse({"art": "auswertung", "daten": gelesen, "bewertung": bewertung,
                       "vorlage": vorlage["id"], "beispiel": beispiel["datei"] if beispiel else None})
            yield sse({"art": "ende"})

        return strom(erzeugen())

    return router
