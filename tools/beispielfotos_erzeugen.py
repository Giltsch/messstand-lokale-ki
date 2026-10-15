"""Beispielfotos für den Reiter „Foto → Daten“ erzeugen.

Vier ausgedachte Dokumente (fiktive Firmen), gerendert und dann wie ein
Handyfoto verfremdet: schräg, perspektivisch verzerrt, ungleiches Licht,
Rauschen, JPEG. Die Musterlösungen stehen in presets/foto.yaml.

Nur zum Neuerzeugen nötig, die fertigen Bilder liegen im Repo:
    uv run --with pillow python tools/beispielfotos_erzeugen.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ZIEL = Path(__file__).resolve().parents[1] / "presets" / "fotos"

SCHRIFTORTE = [
    Path.home() / ".fonts/liberation-fonts-ttf-2.1.5",
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/dejavu"),
]


def schrift(name: str, groesse: int) -> ImageFont.FreeTypeFont:
    for ort in SCHRIFTORTE:
        if (ort / name).is_file():
            return ImageFont.truetype(str(ort / name), groesse)
    return ImageFont.truetype("DejaVuSans.ttf", groesse)


MONO = "LiberationMono-Regular.ttf"
MONO_B = "LiberationMono-Bold.ttf"
SANS = "LiberationSans-Regular.ttf"
SANS_B = "LiberationSans-Bold.ttf"


# ---------------------------------------------------------------- Dokumente


def kassenbon() -> Image.Image:
    b, h = 760, 1500
    bild = Image.new("RGB", (b, h), (250, 249, 244))
    d = ImageDraw.Draw(bild)
    f, fb, fg = schrift(MONO, 30), schrift(MONO_B, 30), schrift(MONO_B, 42)
    y = 50

    def zeile(text: str, font=f, mitte=False, rechts: str | None = None):
        nonlocal y
        if mitte:
            w = d.textlength(text, font=font)
            d.text(((b - w) / 2, y), text, font=font, fill=(30, 30, 30))
        else:
            d.text((50, y), text, font=font, fill=(30, 30, 30))
        if rechts is not None:
            w = d.textlength(rechts, font=font)
            d.text((b - 50 - w, y), rechts, font=font, fill=(30, 30, 30))
        y += font.size + 12

    zeile("BAUMARKT MUSTERMANN", fg, mitte=True)
    zeile("Industriestr. 12, 91522 Ansbach", mitte=True)
    zeile("Tel. 0981 123 45 67", mitte=True)
    zeile("USt-IdNr. DE123456789", mitte=True)
    y += 20
    zeile("-" * 34)
    for name, menge, preis in [
        ("Holzschrauben 4x40 200St", 2, 8.99),
        ("Duebel 8mm 50St", 1, 4.49),
        ("Silikon transparent", 3, 6.95),
        ("Abdeckfolie 4x5m", 1, 3.29),
        ("Arbeitshandschuhe Gr.10", 1, 5.49),
    ]:
        zeile(name)
        zeile(f"  {menge} x {preis:.2f}".replace(".", ","), rechts=f"{menge * preis:.2f} A".replace(".", ","))
    zeile("-" * 34)
    zeile("SUMME EUR", fg, rechts="52,10")
    y += 10
    zeile("Gegeben EC-Karte", rechts="52,10")
    y += 10
    zeile("MwSt   Netto    Steuer   Brutto")
    zeile("A 19%  43,78     8,32    52,10")
    y += 20
    zeile("09.10.2026  14:37   Kasse 3", mitte=True)
    zeile("Bon-Nr. 4711-0815", mitte=True)
    y += 20
    zeile("Vielen Dank fuer Ihren Einkauf!", mitte=True)
    return bild.crop((0, 0, b, y + 60))


def tankquittung() -> Image.Image:
    """Verblasster Thermodruck: blasse Schrift, ungleichmaessig ausgebleicht."""
    b = 700
    bild = Image.new("RGB", (b, 1300), (246, 244, 236))
    d = ImageDraw.Draw(bild)
    f, fg = schrift(MONO, 27), schrift(MONO_B, 36)
    farbe = (150, 150, 156)
    y = 40

    def zeile(text, font=f, mitte=False, rechts=None):
        nonlocal y
        x = (b - d.textlength(text, font=font)) / 2 if mitte else 40
        d.text((x, y), text, font=font, fill=farbe)
        if rechts is not None:
            d.text((b - 40 - d.textlength(rechts, font=font), y), rechts, font=font, fill=farbe)
        y += font.size + 10

    zeile("TANKSTELLE AM RING", fg, mitte=True)
    zeile("Ringstrasse 88, 90402 Nuernberg", mitte=True)
    zeile("St.-Nr. 241/123/45678", mitte=True)
    y += 14
    zeile("Saeule 4  Diesel")
    zeile("  52,31 l x 1,689 EUR/l", rechts="88,35")
    zeile("Scheibenreiniger 1l")
    zeile("  1 x 4,99", rechts="4,99")
    zeile("=" * 31)
    zeile("GESAMT EUR", fg, rechts="93,34")
    zeile("Zahlung Kreditkarte", rechts="93,34")
    y += 8
    zeile("Netto     MwSt 19%    Brutto")
    zeile("78,44       14,90      93,34")
    y += 14
    zeile("13.10.2026   07:52", mitte=True)
    zeile("Beleg 20817  Kasse 1", mitte=True)
    zeile("Gute Fahrt!", mitte=True)
    bild = bild.crop((0, 0, b, y + 40))
    # Ausbleichen: helle Flecken, Knick quer ueber den Bon
    rnd = random.Random(5)
    schleier = Image.new("L", bild.size, 0)
    ds = ImageDraw.Draw(schleier)
    for _ in range(6):
        x, yy, r = rnd.randint(0, b), rnd.randint(0, bild.height), rnd.randint(80, 200)
        ds.ellipse((x - r, yy - r, x + r, yy + r), fill=rnd.randint(130, 200))
    schleier = schleier.filter(ImageFilter.GaussianBlur(40))
    bild = Image.composite(Image.new("RGB", bild.size, (246, 244, 236)), bild, schleier)
    dk = ImageDraw.Draw(bild)
    knick = int(bild.height * 0.47)
    dk.line((0, knick, b, knick + 14), fill=(205, 202, 195), width=3)
    dk.line((0, knick + 3, b, knick + 17), fill=(255, 255, 252), width=2)
    return bild


def lieferschein() -> Image.Image:
    b, h = 1240, 1754  # A4 bei 150 dpi
    bild = Image.new("RGB", (b, h), (255, 255, 255))
    d = ImageDraw.Draw(bild)
    f, fb, fk = schrift(SANS, 26), schrift(SANS_B, 26), schrift(SANS, 20)
    d.text((90, 80), "Schrauben Huber GmbH", font=schrift(SANS_B, 46), fill=(20, 60, 120))
    d.text((90, 140), "Gewerbering 7 · 90763 Fürth · www.schrauben-huber.example", font=fk, fill=(80, 80, 80))
    d.text((90, 260), "Metallbau Berger KG", font=f, fill=(0, 0, 0))
    d.text((90, 296), "z. Hd. Herrn Tom Berger", font=f, fill=(0, 0, 0))
    d.text((90, 332), "Am Bahnhof 3", font=f, fill=(0, 0, 0))
    d.text((90, 368), "91522 Ansbach", font=f, fill=(0, 0, 0))
    for i, (k, v) in enumerate(
        [("Lieferschein-Nr.", "LS-2026-04817"), ("Datum", "12.10.2026"), ("Ihre Bestellung", "B-7731"), ("Kunden-Nr.", "10442")]
    ):
        d.text((760, 260 + i * 38), k, font=fb, fill=(0, 0, 0))
        d.text((990, 260 + i * 38), v, font=f, fill=(0, 0, 0))
    d.text((90, 500), "Lieferschein", font=schrift(SANS_B, 40), fill=(0, 0, 0))
    spalten = [90, 200, 420, 900, 1040]
    kopf = ["Pos.", "Artikel-Nr.", "Bezeichnung", "Menge", "Einheit"]
    y = 580
    d.rectangle((80, y - 8, 1160, y + 40), fill=(225, 232, 242))
    for x, t in zip(spalten, kopf):
        d.text((x, y), t, font=fb, fill=(0, 0, 0))
    y += 60
    for i, (art, bez, menge, einheit) in enumerate(
        [
            ("SH-4471", "Sechskantschraube M10x60 verzinkt", "200", "Stk"),
            ("SH-1203", "Unterlegscheibe M10 DIN 125", "400", "Stk"),
            ("SH-8890", "Gewindestange M12 1 m", "15", "Stk"),
            ("SH-5521", "Schweißdraht SG2 1,0 mm", "2", "Rolle"),
        ],
        start=1,
    ):
        for x, t in zip(spalten, [str(i), art, bez, menge, einheit]):
            d.text((x, y), t, font=f, fill=(0, 0, 0))
        d.line((80, y + 46, 1160, y + 46), fill=(200, 200, 200), width=2)
        y += 64
    y += 40
    d.text((90, y), "Lieferung vollständig. Ware bleibt bis zur vollständigen Bezahlung unser Eigentum.", font=fk, fill=(60, 60, 60))
    d.text((90, y + 120), "Ware erhalten:", font=f, fill=(0, 0, 0))
    d.line((300, y + 150, 700, y + 150), fill=(0, 0, 0), width=2)
    # Unterschrift als Kritzel
    pts = [(320 + i * 9, y + 140 - 18 * ((i * 7) % 5) / 4) for i in range(40)]
    d.line(pts, fill=(20, 40, 140), width=3)
    return bild


def typenschild() -> Image.Image:
    b, h = 1100, 680
    bild = Image.new("RGB", (b, h), (186, 190, 196))
    d = ImageDraw.Draw(bild)
    # gebuerstetes Metall
    rnd = random.Random(3)
    for x in range(0, b, 2):
        g = 178 + rnd.randint(-10, 10)
        d.line((x, 0, x, h), fill=(g, g + 3, g + 8))
    d.rounded_rectangle((20, 20, b - 20, h - 20), radius=26, outline=(60, 60, 64), width=6)
    for cx, cy in [(60, 60), (b - 60, 60), (60, h - 60), (b - 60, h - 60)]:
        d.ellipse((cx - 16, cy - 16, cx + 16, cy + 16), fill=(120, 122, 128), outline=(70, 70, 70), width=3)
    dunkel = (25, 25, 28)
    d.text((100, 60), "ELEKTROMOTOREN FRANK AG", font=schrift(SANS_B, 46), fill=dunkel)
    d.text((100, 118), "3~ Mot.   Made in Germany", font=schrift(SANS, 30), fill=dunkel)
    f, fb = schrift(SANS, 34), schrift(SANS_B, 34)
    reihen = [
        ("Typ", "DM 112M-4", "Nr.", "FR-2019-338471"),
        ("Baujahr", "2019", "IP", "55"),
        ("400 V Δ", "8,2 A", "4,0 kW", "cos φ 0,82"),
        ("50 Hz", "1440 1/min", "Isol.-Kl.", "F"),
        ("Gewicht", "31 kg", "IE3", "88,6 %"),
    ]
    y = 200
    for a, b1, c, d1 in reihen:
        d.text((100, y), a, font=f, fill=dunkel)
        d.text((290, y), b1, font=fb, fill=dunkel)
        d.text((600, y), c, font=f, fill=dunkel)
        d.text((790, y), d1, font=fb, fill=dunkel)
        d.line((90, y + 52, b - 90, y + 52), fill=(110, 112, 118), width=2)
        y += 76
    return bild


def whiteboard() -> Image.Image:
    b, h = 1600, 1000
    bild = Image.new("RGB", (b, h), (244, 246, 245))
    d = ImageDraw.Draw(bild)
    rnd = random.Random(7)
    d.rectangle((0, 0, b - 1, h - 1), outline=(150, 150, 155), width=18)

    def marker(x, y, text, groesse=52, farbe=(25, 45, 140)):
        font = schrift("LiberationSans-Italic.ttf", groesse)
        for z in text:
            dy = rnd.randint(-4, 4)
            d.text((x, y + dy), z, font=font, fill=farbe, stroke_width=1, stroke_fill=farbe)
            x += d.textlength(z, font=font) * rnd.uniform(0.98, 1.08)
        return x

    marker(90, 60, "Team-Meeting 14.10.", 70, (160, 30, 30))
    d.line((90, 150, 760, 158), fill=(160, 30, 30), width=5)
    marker(90, 210, "To-dos:", 56)
    zeilen = [
        "- Angebot Wartungsvertrag Berger -> Anna, bis 31.10.",
        "- Ersatzdichtung bestellen -> Tom, bis Fr 16.10.",
        "- Messestand Stuttgart buchen -> Lisa, bis 23.10.",
        "- Server-Update testen -> Ali, bis 20.10.",
    ]
    y = 300
    for z in zeilen:
        marker(120, y, z, 46)
        y += 90
    marker(90, y + 40, "Naechstes Meeting: 21.10. 9:00", 50, (20, 110, 60))
    return bild


# ---------------------------------------------------------------- Foto-Effekt


def als_foto(
    dok: Image.Image, seed: int, hintergrund=(120, 96, 70), schraeg=3.0, rand=0.08, kipp=0.04
) -> Image.Image:
    rnd = random.Random(seed)
    w, h = dok.size
    leinwand_w, leinwand_h = int(w * (1 + 2 * rand)), int(h * (1 + 2 * rand))
    leinwand = Image.new("RGB", (leinwand_w, leinwand_h), hintergrund)
    # Holz-/Tischmaserung
    dl = ImageDraw.Draw(leinwand)
    for y in range(0, leinwand_h, 3):
        t = rnd.randint(-12, 12)
        dl.line((0, y, leinwand_w, y), fill=tuple(max(0, min(255, c + t)) for c in hintergrund))
    gedreht = dok.convert("RGBA").rotate(rnd.uniform(-schraeg, schraeg), expand=True, resample=Image.BICUBIC)
    ox = (leinwand_w - gedreht.width) // 2 + rnd.randint(-20, 20)
    oy = (leinwand_h - gedreht.height) // 2 + rnd.randint(-20, 20)
    schatten = Image.new("RGBA", gedreht.size, (0, 0, 0, 0))
    schatten.paste((0, 0, 0, 90), mask=gedreht.split()[3])
    leinwand.paste(schatten.filter(ImageFilter.GaussianBlur(14)), (ox + 12, oy + 16), schatten.filter(ImageFilter.GaussianBlur(14)))
    leinwand.paste(gedreht, (ox, oy), gedreht)

    # Perspektive: oben etwas schmaler, als waere das Handy geneigt
    k = kipp
    W, H = leinwand.size
    quelle = [(0, 0), (W, 0), (W, H), (0, H)]
    ziel = [(W * k, H * 0.02), (W * (1 - k * 0.6), 0), (W, H), (0, H * 0.99)]
    leinwand = leinwand.transform((W, H), Image.PERSPECTIVE, _perspektive(ziel, quelle), Image.BICUBIC)

    # ungleiches Licht
    # weicher Verlauf aus vier zufaelligen Eckhelligkeiten
    ecken = Image.new("L", (2, 2))
    ecken.putdata([rnd.randint(150, 255) for _ in range(4)])
    licht = ecken.resize((W, H), Image.BILINEAR)
    leinwand = Image.composite(leinwand, Image.blend(leinwand, Image.new("RGB", (W, H), (40, 38, 30)), 0.45), licht)

    # leichte Unschaerfe und Sensorrauschen
    leinwand = leinwand.filter(ImageFilter.GaussianBlur(0.8))
    rauschen = Image.effect_noise((W, H), 14).convert("RGB")
    leinwand = Image.blend(leinwand, rauschen, 0.05)
    leinwand.thumbnail((1800, 1800))
    return leinwand


def _perspektive(ziel, quelle):
    """Koeffizienten fuer Image.PERSPECTIVE (ziel → quelle)."""
    import numpy as np

    zeilen = []
    for (x, y), (u, v) in zip(ziel, quelle):
        zeilen.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        zeilen.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(zeilen, dtype=float)
    b = np.array([c for p in quelle for c in p], dtype=float)
    return np.linalg.solve(a, b).tolist()


def main() -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    for name, dok, seed, hg, extra in [
        ("kassenbon", kassenbon(), 11, (110, 84, 58), {}),
        ("lieferschein", lieferschein(), 12, (70, 72, 78), {}),
        ("typenschild", typenschild(), 13, (52, 70, 60), {}),
        ("whiteboard", whiteboard(), 14, (200, 196, 186), {}),
        ("tankquittung", tankquittung(), 15, (58, 58, 62), {"schraeg": 7.0, "kipp": 0.12}),
    ]:
        foto = als_foto(dok, seed, hg, **extra)
        foto.save(ZIEL / f"{name}.jpg", quality=85)
        print(name, foto.size)


if __name__ == "__main__":
    main()
