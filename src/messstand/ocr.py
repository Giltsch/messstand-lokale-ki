"""Bruecke zum eigenen OCR-Werkzeug (LawAI) fuer den Reiter „OCR".

Der Messstand reicht nur durch: Hochladen, Liste, Ergebnis, Seitenbild.
Gelesen und geprueft wird im OCR-Werkzeug selbst. Beide laufen auf
demselben Geraet, das Passwort wird lokal gelesen und nie ausgeliefert.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx
import markdown as md
import nh3
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from .config import OcrCfg

# Was je Seite an die Oberflaeche geht. Der Rest von result.json (Wortlisten,
# Rohprotokolle) ist fuer die Vorfuehrung zu viel.
SEITENFELDER = (
    "index", "blank", "band", "agreement", "flags", "text", "markdown", "spans",
    "fields", "born_digital", "intake_notes", "width", "height",
)
AUDITFELDER = (
    "engines", "anchor", "anchor_kind", "second_reader", "tiles", "escalation",
    "timing_s", "vlm_words", "classic_words", "omissions", "displaced",
    "duplicated_passages", "reorder_repairs",
)


# LaTeX-Reste, die das Bild-Sprachmodell bei Zeichnungen ausgibt.
SYMBOLE = {
    r"\phi": "Ø", r"\varphi": "Ø", r"\diameter": "Ø", r"\pm": "±", r"\circ": "°",
    r"\degree": "°", r"\times": "×", r"\leq": "≤", r"\geq": "≥", r"\approx": "≈",
    r"\mu": "µ", r"\Omega": "Ω", r"\alpha": "α", r"\beta": "β", r"\perp": "⊥",
    r"\parallel": "∥", r"\angle": "∠", r"\square": "□",
}
_SYMBOL_MUSTER = re.compile(
    "(?:" + "|".join(re.escape(k) for k in sorted(SYMBOLE, key=len, reverse=True)) + r")(?![A-Za-z])"
)


def symbole(text: str) -> str:
    """LaTeX-Formeln aus Zeichnungen lesbar machen: $\\phi .002 \\text{ A B}$ → Ø .002 A B."""
    text = text or ""
    # $...$ innerhalb einer Zeile nur dann als Formel, wenn LaTeX drinsteht;
    # „5 $ und 7 $“ bleibt so stehen.
    text = re.sub(
        r"\$\$?([^$\n]{1,600}?)\$\$?",
        lambda m: m.group(1).strip() if "\\" in m.group(1) else m.group(0),
        text,
    )
    text = re.sub(r"\\(?:text|mathrm|mathbf|textbf|operatorname)\{([^{}]*)\}", r"\1", text)
    text = _SYMBOL_MUSTER.sub(lambda m: SYMBOLE[m.group(0)], text)
    text = re.sub(r"\\(?:quad|qquad|,|;|!| )", " ", text)
    text = re.sub(r"\\[()\[\]]", "", text)  # \( \) \[ \]
    return re.sub(r"[ \t]{2,}", " ", text)


ERLAUBT_TAGS = {
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "b", "i", "u", "s",
    "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "mark", "blockquote",
    "code", "pre", "hr", "sup", "sub", "span", "del",
}


def markdown_html(text: str) -> str:
    """Layout-Markdown des OCR (mit <mark>-Vertrauensmarken) als sicheres HTML."""
    text = re.sub(r"<!--.*?-->", "", symbole(text), flags=re.S)
    roh = md.markdown(text, extensions=["tables", "sane_lists"])
    return nh3.clean(
        roh,
        tags=ERLAUBT_TAGS,
        attributes={"mark": {"class", "title"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}},
    )


def _passwort(cfg: OcrCfg) -> str:
    if os.environ.get("LAWAI_PASSWORD"):
        return os.environ["LAWAI_PASSWORD"]
    if not cfg.passwort_datei:
        return ""
    pfad = Path(cfg.passwort_datei).expanduser()
    try:
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            if zeile.startswith("LAWAI_PASSWORD="):
                return zeile.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def _seite_kuerzen(seite: dict) -> dict:
    aus = {k: seite.get(k) for k in SEITENFELDER}
    aus["text"] = symbole(aus.get("text") or "")
    aus["html"] = markdown_html(seite.get("markdown") or "")
    aus["spans"] = [
        {**sp, "text": symbole(sp.get("text", "")), **({"alt": symbole(sp["alt"])} if sp.get("alt") else {})}
        for sp in (seite.get("spans") or [])
    ]
    audit = seite.get("audit") or {}
    aus["audit"] = {k: audit.get(k) for k in AUDITFELDER}
    aus["suspect_insertions"] = len(audit.get("suspect_insertions") or [])
    aus["visual"] = (seite.get("visual") or {}).get("items", [])
    return aus


class Freigabe:
    """Welche Dokumente des OCR-Werkzeugs der Messstand zeigen darf.

    Freigegeben sind die Beispiele aus der Stations-YAML und alles, was ueber
    den Messstand hochgeladen wurde. Die Liste der Uploads ueberlebt Neustarts.
    """

    def __init__(self, cfg: OcrCfg, datei: Path) -> None:
        self.aus = not cfg.nur_freigegebene
        self.datei = datei
        self.beispiele = {b.datei for b in cfg.beispiele}
        try:
            self.hochgeladen = set(json.loads(datei.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self.hochgeladen = set()
        self.sha_name: dict[str, str] = {}

    def merken(self, name: str) -> None:
        self.hochgeladen.add(name)
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            self.datei.write_text(json.dumps(sorted(self.hochgeladen), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def name_erlaubt(self, name: str | None) -> bool:
        return self.aus or (name in self.beispiele or name in self.hochgeladen)

    def sha_erlaubt(self, sha: str) -> bool:
        return self.aus or self.name_erlaubt(self.sha_name.get(sha))


def router_bauen(cfg: OcrCfg, uploadliste: Path) -> APIRouter:
    router = APIRouter(prefix="/api/ocr")
    basis = cfg.url.rstrip("/")
    passwort = _passwort(cfg)
    auth = ("messstand", passwort) if passwort else None
    freigabe = Freigabe(cfg, uploadliste)

    async def pruefen(sha: str) -> None:
        if not freigabe.sha_erlaubt(sha):
            await dokumente()  # Zuordnung sha -> Dateiname auffrischen
        if not freigabe.sha_erlaubt(sha):
            raise HTTPException(404, "Dieses Dokument ist für den Messstand nicht freigegeben.")

    def client(timeout: float = 15.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=basis, auth=auth, timeout=timeout)

    async def json_holen(pfad: str) -> dict:
        try:
            async with client() as c:
                antwort = await c.get(pfad)
        except httpx.HTTPError as fehler:
            raise HTTPException(
                502, f"Das OCR-Werkzeug unter {basis} antwortet nicht ({type(fehler).__name__})."
            ) from fehler
        if antwort.status_code == 401:
            raise HTTPException(
                502, "Das OCR-Werkzeug lehnt das Passwort ab. LAWAI_PASSWORD prüfen."
            )
        if antwort.status_code == 404:
            raise HTTPException(404, "Dokument im OCR-Werkzeug nicht gefunden oder noch nicht fertig.")
        if antwort.status_code != 200:
            raise HTTPException(502, f"OCR-Werkzeug: Fehlercode {antwort.status_code} für {pfad}")
        return antwort.json()

    @router.get("/status")
    async def status() -> dict:
        try:
            daten = await json_holen("/api/status")
        except HTTPException as fehler:
            return {"online": False, "url": basis, "nachricht": fehler.detail}
        return {
            "online": True,
            "url": basis,
            "lesen": bool(daten.get("ocr")),
            "pruefer": bool(daten.get("judge")),
            "pruefer_gewuenscht": bool(daten.get("judge_wanted")),
            "klassisch": daten.get("classic"),
            "parallel": daten.get("workers"),
            "beispiele": [b.model_dump() for b in cfg.beispiele],
            "nur_freigegebene": cfg.nur_freigegebene,
        }

    @router.get("/dokumente")
    async def dokumente() -> dict:
        daten = await json_holen("/api/v1/dokumente")
        felder = (
            "sha", "filename", "title", "status", "n_pages", "bands", "stage",
            "progress_done", "progress_total", "elapsed_s", "error", "uploaded_at",
        )
        alle = daten.get("dokumente", [])
        freigabe.sha_name = {d["sha"]: d.get("filename") for d in alle}
        return {
            "dokumente": [
                {k: d.get(k) for k in felder} for d in alle if freigabe.name_erlaubt(d.get("filename"))
            ]
        }

    @router.post("/upload")
    async def hochladen(datei: UploadFile = File(...)) -> dict:
        inhalt = await datei.read()
        if not inhalt:
            raise HTTPException(400, "Die Datei ist leer.")
        name = Path(datei.filename or "upload.pdf").name
        try:
            async with client(timeout=120.0) as c:
                antwort = await c.post(
                    "/upload",
                    files={"files": (name, inhalt, datei.content_type or "application/octet-stream")},
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as fehler:
            raise HTTPException(502, f"Hochladen zum OCR-Werkzeug gescheitert ({type(fehler).__name__}).") from fehler
        if antwort.status_code != 200:
            raise HTTPException(502, f"OCR-Werkzeug: Fehlercode {antwort.status_code} beim Hochladen")
        daten = antwort.json()
        freigabe.merken(name)
        if daten.get("added"):
            nachricht = f"„{name}“ ist beim OCR-Werkzeug angekommen und wird gelesen."
        else:
            nachricht = f"„{name}“ ist dort schon bekannt (gleicher Inhalt), das Ergebnis liegt bereits vor."
        return {"ok": True, "name": name, "nachricht": nachricht}

    @router.get("/dokument/{sha}")
    async def dokument(sha: str) -> dict:
        await pruefen(sha)
        kopf = await json_holen(f"/api/v1/dokumente/{sha}")
        ergebnis = await json_holen(f"/doc/{sha}/download/result.json")
        return {
            "sha": sha,
            "name": kopf.get("filename"),
            "titel": kopf.get("title") or (kopf.get("title_proposal") or {}).get("title"),
            "seiten_zahl": ergebnis.get("n_pages"),
            "dauer_s": ergebnis.get("elapsed_s"),
            "baender": ergebnis.get("bands"),
            "modelle": ergebnis.get("models"),
            "datenblatt": kopf.get("datenblatt"),
            "werkzeug_url": f"{basis}/doc/{sha}",
            "seiten": [_seite_kuerzen(s) for s in ergebnis.get("pages", [])],
        }

    @router.get("/seite/{sha}/{idx}.png")
    async def seitenbild(sha: str, idx: int) -> Response:
        await pruefen(sha)
        try:
            async with client(timeout=30.0) as c:
                antwort = await c.get(f"/doc/{sha}/page/{idx}.png")
        except httpx.HTTPError as fehler:
            raise HTTPException(502, "Seitenbild nicht erreichbar.") from fehler
        if antwort.status_code != 200:
            raise HTTPException(antwort.status_code, "Seitenbild nicht gefunden.")
        return Response(
            antwort.content,
            media_type="image/png",
            headers={"Cache-Control": "max-age=3600"},
        )

    return router
