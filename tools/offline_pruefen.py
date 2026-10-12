"""Prueft, ob der Messstand wirklich ohne Netz auskommt.

    uv run python tools/offline_pruefen.py

Geprueft wird:
  1. Verweise auf externe Adressen in den Dateien der Oberflaeche
  2. Webfonts aus dem Netz
  3. ob der Server nur auf 127.0.0.1 lauscht (nur wenn er laeuft)
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
ERLAUBT = ("127.0.0.1", "localhost", "::1")
ADRESSE = re.compile(r"""(?:https?:)?//([A-Za-z0-9._\-]+)""")


def oberflaeche_pruefen() -> list[str]:
    beschwerden: list[str] = []
    for datei in sorted((WURZEL / "static").rglob("*")):
        if datei.suffix not in {".html", ".js", ".css"}:
            continue
        text = datei.read_text(encoding="utf-8")
        for zeile_nr, zeile in enumerate(text.splitlines(), 1):
            for host in ADRESSE.findall(zeile):
                if host.startswith(ERLAUBT):
                    continue
                beschwerden.append(
                    f"{datei.relative_to(WURZEL)}:{zeile_nr}: externe Adresse „{host}“"
                )
        if "@font-face" in text and "url(" in text:
            for treffer in re.findall(r"url\(([^)]+)\)", text):
                if treffer.strip("\"'").startswith(("http", "//")):
                    beschwerden.append(
                        f"{datei.relative_to(WURZEL)}: Webfont aus dem Netz: {treffer}"
                    )
    return beschwerden


def port_pruefen(port: int = 8765) -> list[str]:
    beschwerden: list[str] = []
    with socket.socket() as s:
        s.settimeout(0.5)
        laeuft = s.connect_ex(("127.0.0.1", port)) == 0
    if not laeuft:
        print(f"  Hinweis: auf Port {port} laeuft gerade kein Messstand, "
              "die Socket-Pruefung wird uebersprungen.")
        return beschwerden
    try:
        ausgabe = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  Hinweis: lsof ist nicht verfuegbar, Socket-Pruefung uebersprungen.")
        return beschwerden
    for zeile in ausgabe.splitlines()[1:]:
        if "LISTEN" in zeile and "127.0.0.1" not in zeile:
            beschwerden.append(f"Server lauscht nicht nur lokal: {zeile.strip()}")
    if ausgabe.strip():
        print("  Lauschende Sockets:")
        for zeile in ausgabe.splitlines()[1:]:
            print("    " + zeile.strip())
    return beschwerden


def main() -> int:
    print("\n  Offline-Pruefung des Messstands\n")
    beschwerden = oberflaeche_pruefen() + port_pruefen()
    if beschwerden:
        print("\n  Gefunden:")
        for b in beschwerden:
            print(f"    - {b}")
        print("\n  Ergebnis: nicht offline-tauglich.\n")
        return 1
    print("\n  Ergebnis: keine externen Verweise, keine fremden Adressen.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
