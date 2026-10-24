// Reiter 6: OCR. Das eigene OCR-Werkzeug vorfuehren: was lokal geht, wo die
// Grenzen liegen und mit welcher Stellschraube man sie selbst verschiebt.

import { el, zahl, ganz, sekunden } from "./format.js";
import { holen, strom } from "./api.js";
import { ergebnisMelden } from "./store.js";
import { ModellAuswahl } from "./auswahl.js";
import { meldung, meldungLeeren } from "./meldungen.js";

const VERTRAUEN = {
  verified: { name: "belegt", text: "Beide Leser haben dasselbe gelesen." },
  verified_displaced: {
    name: "belegt, verschoben",
    text: "Beide Leser haben es gelesen, aber an anderer Stelle der Reihenfolge.",
  },
  low_agreement: { name: "uneinig", text: "Die Leser haben Verschiedenes gelesen." },
  suspect_insertion: {
    name: "ohne Beleg",
    text: "Nur das Sprachmodell hat es gelesen. Möglicherweise erfunden.",
  },
  suspect_omission: {
    name: "ausgelassen",
    text: "Der zweite Leser hat es gesehen, der Hauptleser hat es weggelassen.",
  },
};

const BAND = {
  auto_accept: { name: "verlässlich", text: "ohne Mensch freigegeben", klasse: "gut" },
  recheck: { name: "kurz prüfen", text: "ein Mensch schaut kurz drauf", klasse: "warn" },
  human_review: { name: "genau prüfen", text: "ein Mensch muss lesen", klasse: "schlecht" },
};

const LESER = {
  lightonocr2: "LightOnOCR-2, 1 Mrd. Parameter (Bild zu Text)",
  "doctr-torch-parseq-ml": "docTR, klassische OCR (Wort für Wort, mit Positionen)",
  "qwen3.8-second-reader": "Qwen3.8 27B als Zweitleser (Bild-Sprachmodell)",
  textlayer: "Textebene der PDF",
};

const VORGABEN = [
  {
    titel: "Angaben als Tabelle",
    auftrag:
      "Lies den OCR-Text unten und gib alle konkreten Angaben (Nummern, Daten, Mengen, " +
      "Maße, Namen, Werkstoffe) als Tabelle mit den Spalten Angabe | Wert | sicher? aus. " +
      "Stellen in [unsicher: …] bekommen in der dritten Spalte ein Nein. Erfinde nichts.",
  },
  {
    titel: "In drei Sätzen",
    auftrag: "Fasse das Dokument unten in drei Sätzen zusammen: Was ist es, von wem, was ist zu tun?",
  },
  {
    titel: "Was muss ein Mensch prüfen?",
    auftrag:
      "Nenne alle Stellen im OCR-Text unten, die mit [unsicher: …] markiert sind, und sage " +
      "jeweils in einem Satz, warum ein Fehler dort teuer wäre.",
  },
];

export function ocrAufbauen(wurzel) {
  const statuszeile = el("div", { class: "hinweiszeile" });
  const beispielzeile = el("div", { class: "zeile ocr-beispiele" });
  const auswahl = el("select", { onchange: () => dokumentLaden(auswahl.value) });
  const hochladen = el("input", {
    type: "file",
    accept: "application/pdf,image/png,image/jpeg,image/tiff",
    onchange: () => hochladenLauf(),
  });
  const werkzeugLink = el("a", { class: "knopf leise klein", target: "_blank", hidden: true, text: "Im OCR-Werkzeug öffnen" });
  const meldungsfeld = el("div", {});
  const dokbereich = el("div", {});
  const llm = llmBauen();

  let liste = [];
  let beispiele = [];
  let aktuell = null; // geladenes Dokument
  let seiteNr = 0;
  let wartenAuf = null; // sha, das gerade gelesen wird
  let uhr = null;

  wurzel.append(
    el("div", { class: "karte" }, [
      el("h2", { text: "Eigenes OCR auf diesem Gerät" }),
      el("p", {
        class: "leise",
        text:
          "Zwei Leser lesen jede Seite unabhängig: ein kleines Bild-Sprachmodell und eine klassische OCR. " +
          "Vertraut wird nicht dem Modell, sondern der Übereinstimmung. Wo beide sich uneinig sind, wird markiert, " +
          "nachgelesen oder an einen Menschen gegeben.",
      }),
      statuszeile,
      beispielzeile,
      el("div", { class: "zeile" }, [
        el("label", { class: "feld" }, ["Dokument", auswahl]),
        el("label", { class: "feld" }, ["Eigene Datei (PDF, Foto, Scan)", hochladen]),
        werkzeugLink,
      ]),
      meldungsfeld,
    ]),
    dokbereich,
    llm.karte,
    grenzenKarte()
  );

  // ---------- Status, Liste, Hochladen ----------

  async function statusLaden() {
    try {
      const s = await holen("/api/ocr/status");
      if (!s.online) {
        statuszeile.replaceChildren(
          el("span", { class: "punkt offline", text: "OCR-Werkzeug nicht erreichbar" }),
          el("span", { text: s.nachricht || "" }),
          el("span", { text: "Starten mit: spark/spark-modus.sh alles" })
        );
        return false;
      }
      beispiele = s.beispiele || [];
      statuszeile.replaceChildren(
        el("span", { class: `punkt ${s.lesen ? "online" : "offline"}`, text: "Leser: LightOnOCR-2 (1 Mrd.)" }),
        el("span", { class: "punkt online", text: `Klassisch: ${s.klassisch || "docTR"}` }),
        el("span", {
          class: `punkt ${s.pruefer ? "online" : "offline"}`,
          text: s.pruefer ? "Prüfer: Qwen3.8 27B" : "Prüfer aus",
        }),
        el("span", { text: `${ganz(s.parallel)} Seiten gleichzeitig` })
      );
      return true;
    } catch (fehler) {
      statuszeile.replaceChildren(el("span", { class: "punkt offline", text: String(fehler) }));
      return false;
    }
  }

  async function listeLaden() {
    const daten = await holen("/api/ocr/dokumente");
    liste = daten.dokumente;
    const vorher = auswahl.value;
    auswahl.replaceChildren(
      el("option", { value: "", text: "– bitte wählen –" }),
      ...liste.map((d) =>
        el("option", {
          value: d.sha,
          disabled: d.status !== "done",
          text:
            `${d.title || d.filename} · ${ganz(d.n_pages)} S.` +
            (d.status === "done" ? "" : d.status === "error" ? " · Fehler" : " · wird gelesen"),
        })
      )
    );
    if (vorher) auswahl.value = vorher;
    beispielzeile.replaceChildren(
      ...beispiele
        .map((b) => ({ b, d: liste.find((d) => d.filename === b.datei && d.status === "done") }))
        .filter(({ d }) => d)
        .map(({ b, d }) =>
          el(
            "button",
            {
              class: "knopf leise ocr-beispiel",
              type: "button",
              title: b.zeigt,
              onclick: () => {
                auswahl.value = d.sha;
                dokumentLaden(d.sha);
              },
            },
            [el("b", { text: b.titel }), el("span", { class: "klein leise", text: b.zeigt })]
          )
        )
    );
    return liste;
  }

  async function hochladenLauf() {
    const datei = hochladen.files?.[0];
    if (!datei) return;
    const formular = new FormData();
    formular.append("datei", datei);
    meldung(meldungsfeld, { nachricht: `„${datei.name}“ wird übertragen …` });
    try {
      const antwort = await fetch("/api/ocr/upload", { method: "POST", body: formular });
      const daten = await antwort.json();
      if (!antwort.ok) throw new Error(daten.detail || `Fehlercode ${antwort.status}`);
      meldung(meldungsfeld, { art: "gut", nachricht: daten.nachricht });
      await listeLaden();
      const neu = liste.find((d) => d.filename === daten.name);
      if (neu) beobachten(neu.sha);
    } catch (fehler) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Hochladen gescheitert.", detail: String(fehler) });
    } finally {
      hochladen.value = "";
    }
  }

  // Fortschritt einer frisch hochgeladenen Datei verfolgen, dann anzeigen.
  function beobachten(sha) {
    wartenAuf = sha;
    clearInterval(uhr);
    const schritt = async () => {
      await listeLaden().catch(() => {});
      const d = liste.find((x) => x.sha === wartenAuf);
      if (!d) return;
      if (d.status === "done") {
        clearInterval(uhr);
        wartenAuf = null;
        auswahl.value = d.sha;
        meldung(meldungsfeld, {
          art: "gut",
          nachricht: `Fertig gelesen: ${ganz(d.n_pages)} Seite(n) in ${sekunden(d.elapsed_s)} s.`,
        });
        dokumentLaden(d.sha);
      } else if (d.status === "error") {
        clearInterval(uhr);
        meldung(meldungsfeld, { art: "fehler", nachricht: "Das OCR-Werkzeug meldet einen Fehler.", detail: d.error || "" });
      } else {
        const gesamt = d.progress_total ? ` ${ganz(d.progress_done || 0)} von ${ganz(d.progress_total)} Seiten` : "";
        meldung(meldungsfeld, { nachricht: `„${d.filename}“ wird gelesen …${gesamt} (${d.stage || "wartet"})` });
      }
    };
    schritt();
    uhr = setInterval(schritt, 2000);
  }

  // ---------- Dokument ----------

  async function dokumentLaden(sha) {
    if (!sha) return;
    meldungLeeren(meldungsfeld);
    dokbereich.replaceChildren(el("div", { class: "karte leise", text: "Ergebnis wird geholt …" }));
    try {
      aktuell = await holen(`/api/ocr/dokument/${sha}`);
    } catch (fehler) {
      dokbereich.replaceChildren();
      meldung(meldungsfeld, { art: "fehler", nachricht: "Das Ergebnis konnte nicht geholt werden.", detail: String(fehler) });
      return;
    }
    aktuell.quelle = beispiele.find((b) => b.datei === aktuell.name)?.quelle || "";
    werkzeugLink.href = aktuell.werkzeug_url;
    werkzeugLink.hidden = false;
    seiteNr = aktuell.seiten.findIndex((s) => !s.blank);
    if (seiteNr < 0) seiteNr = 0;
    dokumentZeichnen();
    llm.dokumentGesetzt(aktuell);
  }

  function dokumentZeichnen() {
    const d = aktuell;
    const nichtLeer = d.seiten.filter((s) => !s.blank);
    const schnitt = nichtLeer.length
      ? nichtLeer.reduce((a, s) => a + (s.agreement || 0), 0) / nichtLeer.length
      : null;
    const proStunde = d.dauer_s ? (d.seiten_zahl / d.dauer_s) * 3600 : null;
    const b = d.baender || {};

    const kacheln = el("div", { class: "kacheln" }, [
      kachel("Seiten", ganz(d.seiten_zahl), ""),
      kachel("Gesamtzeit", sekunden(d.dauer_s), "s"),
      kachel("Hochgerechnet", proStunde ? ganz(Math.round(proStunde)) : "–", "Seiten/h"),
      kachel("Übereinstimmung", schnitt === null ? "–" : zahl(schnitt * 100, 0), "%"),
    ]);
    const ampel = el("div", { class: "hinweiszeile" }, [
      ...Object.entries(BAND).map(([k, v]) =>
        el("span", { class: `ocr-band ${v.klasse}`, text: `${v.name}: ${ganz(b[k] || 0)}` })
      ),
      el("span", {
        text:
          "Hochgerechnet gilt für eine Datei allein. Viele Dateien gleichzeitig laufen parallel und sind schneller.",
      }),
    ]);

    const seitenknoepfe =
      d.seiten.length > 1
        ? el(
            "div",
            { class: "zeile ocr-seiten" },
            d.seiten.map((s, i) =>
              el("button", {
                type: "button",
                class: `knopf klein ${i === seiteNr ? "" : "leise"} ${s.blank ? "" : BAND[s.band]?.klasse || ""}`,
                text: s.blank ? `${i + 1} (leer)` : String(i + 1),
                onclick: () => {
                  seiteNr = i;
                  dokumentZeichnen();
                },
              })
            )
          )
        : null;

    const seite = d.seiten[seiteNr];
    dokbereich.replaceChildren(
      el("div", { class: "karte" }, [
        el("h2", { text: d.titel || d.name }),
        kacheln,
        ampel,
        seitenknoepfe,
      ]),
      seite.blank
        ? el("div", { class: "karte", text: "Leere Seite. Sie erreicht kein Modell und erzeugt keinen Text." })
        : seiteBauen(d, seite)
    );
  }

  (async () => {
    if (!(await statusLaden())) return;
    try {
      await listeLaden();
    } catch (fehler) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Die Dokumentliste fehlt.", detail: String(fehler) });
    }
  })();

  return {};
}

// ---------- Eine Seite: Bild, Text, Ablauf, Grenzen ----------

// Gewaehlte Textansicht gilt fuer alle Seiten, bis man sie wieder umschaltet.
let wortgenau = false;

function seiteBauen(d, seite) {
  const zeigeBelegte = el("input", { type: "checkbox" });
  const bild = el("img", {
    src: `/api/ocr/seite/${d.sha}/${seite.index}.png`,
    alt: `Seite ${seite.index + 1}`,
    class: "ocr-bild",
  });
  const rahmen = el("div", { class: "ocr-bildrahmen" }, [bild]);
  // Grosse Plaene: Klick oeffnet den Scan in voller Aufloesung.
  bild.addEventListener("click", () => window.open(bild.src, "_blank"));
  bild.title = "Klicken: Scan in voller Auflösung";
  const textfeld = el("div", { class: "ocr-text" });
  // Server liefert das Layout-Markdown bereits als bereinigtes HTML (nh3).
  const dokumentfeld = el("div", { class: "ocr-text ocr-dokument", html: seite.html || "" });
  const ansicht = el("button", { class: "knopf leise klein", type: "button" });
  const ansichtSetzen = () => {
    textfeld.hidden = !wortgenau;
    dokumentfeld.hidden = wortgenau;
    ansicht.textContent = wortgenau ? "Als Dokument anzeigen" : "Wortgenau, mit dem Scan verknüpft";
  };
  ansicht.addEventListener("click", () => {
    wortgenau = !wortgenau;
    ansichtSetzen();
  });
  ansichtSetzen();

  const spans = seite.spans || [];
  const kaesten = [];
  spans.forEach((span, i) => {
    const art = span.trust || "verified";
    const textteil = el("span", {
      class: `ocr-span ${art}`,
      "data-i": i,
      title: titelFuer(span),
      text: span.text + " ",
    });
    textfeld.append(textteil);
    for (const box of span.boxes || []) {
      if (!box) continue;
      const [x0, y0, x1, y1] = box;
      const k = el("div", {
        class: `ocr-kasten ${art}`,
        "data-i": i,
        title: titelFuer(span),
        style: `left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%`,
      });
      rahmen.append(k);
      kaesten.push(k);
    }
  });
  const ohneKaesten = spans.length > 0 && kaesten.length === 0;

  // Hover verbindet Text und Bild in beide Richtungen.
  const hervorheben = (i, an) => {
    for (const knoten of [...textfeld.children, ...kaesten]) {
      if (knoten.dataset.i === String(i)) knoten.classList.toggle("aktiv", an);
    }
  };
  for (const knoten of [...textfeld.children, ...kaesten]) {
    knoten.addEventListener("mouseenter", () => hervorheben(knoten.dataset.i, true));
    knoten.addEventListener("mouseleave", () => hervorheben(knoten.dataset.i, false));
  }
  zeigeBelegte.addEventListener("change", () => rahmen.classList.toggle("belegte", zeigeBelegte.checked));

  const zaehler = {};
  for (const s of spans) zaehler[s.trust] = (zaehler[s.trust] || 0) + 1;
  const legende = el(
    "div",
    { class: "hinweiszeile" },
    Object.entries(VERTRAUEN).map(([k, v]) =>
      el("span", { class: `ocr-span ${k}`, title: v.text, text: `${v.name} (${ganz(zaehler[k] || 0)})` })
    )
  );

  const band = BAND[seite.band] || { name: seite.band, text: "", klasse: "" };
  return el("div", {}, [
    el("div", { class: "spalten-2" }, [
      el("div", { class: "karte" }, [
        el("h3", { text: `Scan, Seite ${seite.index + 1}` }),
        el("div", { class: "zeile klein" }, [
          el("label", {}, [zeigeBelegte, " auch belegte Stellen einrahmen"]),
          ohneKaesten
            ? el("span", { class: "leise", text: "Keine Wortpositionen: der Zweitleser liefert nur Text." })
            : null,
        ]),
        rahmen,
        d.quelle ? el("div", { class: "klein leise", style: "margin-top:.4rem", text: `Quelle: ${d.quelle}` }) : null,
      ]),
      el("div", { class: "karte" }, [
        el("h3", {}, [
          "Gelesener Text ",
          el("span", { class: `ocr-band ${band.klasse}`, text: `${band.name}: ${band.text}` }),
        ]),
        legende,
        dokumentfeld,
        textfeld,
        el("div", { class: "zeile", style: "margin-top:.5rem" }, [
          ansicht,
          el("span", {
            class: "klein leise",
            text: wortgenau ? "" : "Maus auf eine markierte Stelle: zweite Lesart. Wortgenau leuchtet sie auch auf dem Scan.",
          }),
        ]),
        felderBauen(seite),
      ]),
    ]),
    el("div", { class: "spalten-2" }, [ablaufBauen(seite), grenzenBauen(seite)]),
  ]);
}

function titelFuer(span) {
  const v = VERTRAUEN[span.trust] || { name: span.trust, text: "" };
  return `${v.name}: ${v.text}` + (span.alt ? `\nAndere Lesart: „${span.alt}“` : "");
}

function felderBauen(seite) {
  const felder = (seite.fields || []).filter((f) => f.valid);
  if (!felder.length) return null;
  const namen = { date: "Datum", iban: "IBAN", amount: "Betrag", aktenzeichen: "Aktenzeichen" };
  return el("div", { style: "margin-top:.6rem" }, [
    el("div", { class: "klein leise", text: "Geprüfte Felder (Regeln, kein Modell):" }),
    el(
      "div",
      { class: "hinweiszeile" },
      felder.map((f) => el("span", { html: `${namen[f.kind] || f.kind}: <b>${escape(f.normalized || f.raw)}</b>` }))
    ),
  ]);
}

function ablaufBauen(seite) {
  const a = seite.audit || {};
  const t = a.timing_s || {};
  const schritte = [];
  const groesse = seite.width && seite.height ? `${ganz(seite.width)} × ${ganz(seite.height)} Pixel` : "";
  schritte.push(
    `Vorbereitung: ${groesse}` +
      (seite.born_digital ? ", digitale PDF mit Textebene" : "") +
      (a.tiles ? `, zu groß für einen Blick, darum in ${a.tiles.cols} × ${a.tiles.rows} Kacheln zerlegt` : "") +
      "."
  );
  const leser = a.engines || [];
  if (leser[0]) schritte.push(`Leser 1: ${LESER[leser[0]] || leser[0]}, ${ganz(a.vlm_words)} Wörter in ${sekunden(t.vlm)} s.`);
  if (a.anchor_kind === "second_reader" && a.second_reader) {
    schritte.push(
      `Leser 2: Die klassische OCR stimmte nur zu ${zahl(a.second_reader.agreement_classic * 100, 0)} % überein ` +
        `(${sekunden(t.classic)} s). Das deutet auf Handschrift. Darum hat Qwen3.8 27B die Seite ` +
        `komplett neu gelesen: ${sekunden(t.second_reader)} s.`
    );
  } else if (leser[1]) {
    schritte.push(`Leser 2: ${LESER[leser[1]] || leser[1]}, ${ganz(a.classic_words)} Wörter in ${sekunden(t.classic)} s.`);
  }
  schritte.push(`Abgleich: ${zahl((seite.agreement || 0) * 100, 1)} % Übereinstimmung. Ab 72 % und ohne Verdachtsstellen wird automatisch freigegeben.`);
  const e = a.escalation || {};
  if (e.disputes) {
    let satz = `${ganz(e.disputes)} strittige Stellen.`;
    if (e.reread) satz += ` Nachlesen mit 1,4-facher Auflösung hat ${ganz(e.reread.resolved)} davon geklärt.`;
    if (e.judge) satz += " Danach hat das Prüfer-Modell die übrigen Ausschnitte angesehen.";
    schritte.push(satz);
  }
  if ((a.omissions || []).length) schritte.push(`Vom Hauptleser ausgelassen: ${a.omissions.map((o) => `„${o}“`).join(", ")}.`);
  const band = BAND[seite.band];
  schritte.push(`Ergebnis: ${band ? `${band.name}, ${band.text}` : seite.band}.`);

  const zeiten = Object.entries(t)
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => `${k} ${sekunden(v)} s`)
    .join(" · ");
  return el("div", { class: "karte" }, [
    el("h3", { text: "Was auf dieser Seite passiert ist" }),
    el("ol", { class: "ocr-ablauf" }, schritte.map((s) => el("li", { text: s }))),
    el("div", { class: "klein leise", text: zeiten }),
  ]);
}

// Aus dem Protokoll ableiten, welche Grenze die Seite erreicht hat und welche
// Stellschraube man selbst drehen kann.
function grenzenBauen(seite) {
  const a = seite.audit || {};
  const spans = seite.spans || [];
  const liste = [];
  if (a.anchor_kind === "second_reader") {
    liste.push({
      grenze:
        "Handschrift. Die klassische OCR kann sie nicht lesen, und zwei KI-Leser können gemeinsam danebenliegen. " +
        "Solche Seiten gibt das System deshalb nie allein frei.",
      schraube:
        "Korrekturen sammeln (jede Prüfung wird Testmaterial) und den Leser auf die eigenen Formulare und Schriften " +
        "nachtrainieren, lokal auf diesem Gerät. Bei festen Formularen Felder nach Position lesen statt Freitext.",
    });
  }
  if ((a.omissions || []).some((o) => /\[[xX✓ ]?\]/.test(o))) {
    liste.push({
      grenze: "Angekreuzte Kästchen hat der Hauptleser übersehen.",
      schraube:
        "Kästchen per Bildanalyse prüfen, wie es für Durchstreichungen und Stempel schon geschieht: deterministisch, ohne Modell.",
    });
  }
  if (seite.suspect_insertions) {
    liste.push({
      grenze: `${ganz(seite.suspect_insertions)} Stelle(n) hat nur das Sprachmodell gelesen. Kandidaten für Erfindungen.`,
      schraube: "Das Prüfer-Modell sieht sich genau diese Ausschnitte an. Ob es eingreift und ab wann freigegeben wird, ist eine Einstellung.",
    });
  }
  const symbole = spans.filter((s) => s.trust !== "verified" && /\\phi|Ø|±|⌀|\\pm/.test(s.text + (s.alt || ""))).length;
  if (symbole || /\\phi|Ø/.test(seite.text || "")) {
    liste.push({
      grenze:
        "Zeichnungssymbole (Ø, Toleranzen, Form- und Lagezeichen) kennt die klassische OCR nicht. " +
        "Dort fehlt der zweite Beleg, und Maße in der Zeichnung selbst stehen gedreht und verstreut.",
      schraube:
        "Eigene Prüfregeln wie heute für IBAN und Aktenzeichen: Maß, Toleranz, Zeichnungsnummer, Revision. " +
        "Für Fragen an die Zeichnung zusätzlich ein Bild-Sprachmodell, das die Geometrie sieht.",
    });
  }
  if (a.tiles) {
    liste.push({
      grenze: "Die Seite ist größer, als das Modell auf einmal sehen kann.",
      schraube: "Kachelgröße und Auflösung sind Parameter. Gemessen bis A2 bei 300 dpi.",
    });
  }
  if (!liste.length) {
    liste.push({
      grenze:
        seite.band === "auto_accept"
          ? "Keine erreicht. Beide Leser stimmen überein, alle Felder sind gültig. Das ist der Normalfall bei gedrucktem Text."
          : "Einzelne Wörter sind strittig, die Seite geht zur kurzen Sichtprüfung.",
      schraube: "Die Schwelle für die automatische Freigabe (72 %) ist einstellbar, gemessen an eigenen Testseiten.",
    });
  }
  return el("div", { class: "karte" }, [
    el("h3", { text: "Grenze und Stellschraube" }),
    ...liste.map((g) =>
      el("div", { class: "ocr-grenze" }, [
        el("div", { html: `<b>Grenze:</b> ${escape(g.grenze)}` }),
        el("div", { html: `<b>Selbst verschieben:</b> ${escape(g.schraube)}` }),
      ])
    ),
  ]);
}

// ---------- Weiter mit einem Sprachmodell ----------

function llmBauen() {
  const auswahl = new ModellAuswahl({});
  const auftrag = el("textarea", { rows: 3 });
  const antwort = el("div", { class: "antwort" });
  const zahlen = el("div", { class: "hinweiszeile" });
  const promptfeld = el("pre", { class: "promptansicht", hidden: true });
  const los = el("button", { class: "knopf", type: "button", text: "Ausführen", disabled: true });
  const abbrechen = el("button", { class: "knopf leise", type: "button", text: "Abbrechen", disabled: true });
  let dokument = null;
  let steuerung = null;
  auftrag.value = VORGABEN[0].auftrag;

  const karte = el("div", { class: "karte" }, [
    el("h2", { text: "Weiter mit einem Sprachmodell" }),
    el("p", {
      class: "leise",
      text:
        "Das Sprachmodell bekommt den geprüften Text, unsichere Stellen sind markiert. " +
        "So weiß es, wo es vorsichtig sein muss. Das Bild selbst sieht es nicht.",
    }),
    auswahl.wurzel,
    el(
      "div",
      { class: "zeile", style: "margin:.6rem 0" },
      VORGABEN.map((v) =>
        el("button", {
          class: "knopf leise klein",
          type: "button",
          text: v.titel,
          onclick: () => {
            auftrag.value = v.auftrag;
          },
        })
      )
    ),
    el("label", { class: "feld" }, ["Auftrag", auftrag]),
    el("div", { class: "zeile", style: "margin:.6rem 0" }, [
      los,
      abbrechen,
      el("button", {
        class: "knopf leise klein",
        type: "button",
        text: "Was das Modell gesehen hat",
        onclick: () => {
          promptfeld.hidden = !promptfeld.hidden;
        },
      }),
    ]),
    zahlen,
    antwort,
    promptfeld,
  ]);

  los.addEventListener("click", async () => {
    if (!dokument) return;
    const { backend, modell } = auswahl.wert();
    const prompt = `${auftrag.value.trim()}\n\nOCR-Text:\n\n${textMitMarken(dokument)}`;
    promptfeld.textContent = prompt;
    antwort.textContent = "";
    antwort.classList.add("laeuft");
    zahlen.replaceChildren();
    los.disabled = true;
    abbrechen.disabled = false;
    steuerung = new AbortController();
    try {
      await strom(
        "/api/chat",
        {
          backend,
          modell,
          prompt,
          system: "Sie arbeiten mit OCR-Ergebnissen. Antworten Sie auf Deutsch, knapp und nur mit dem, was im Text steht.",
          reiter: "OCR",
          notiz: dokument.titel || dokument.name,
          max_tokens: 1200,
        },
        (e) => {
          if (e.art === "text") antwort.textContent += e.text;
          else if (e.art === "fehler") antwort.textContent += `\n[${e.nachricht}]`;
          else if (e.art === "messung") {
            const m = e.messung;
            zahlen.replaceChildren(
              el("span", { text: `Erstes Wort nach ${sekunden(m.ttft_s)} s` }),
              el("span", { text: `Lesen ${ganz(Math.round(m.prefill_tps || 0))} Token/s` }),
              el("span", { text: `Schreiben ${ganz(Math.round(m.decode_tps || 0))} Token/s` }),
              el("span", { text: `Gesamt ${sekunden(m.total_s)} s` })
            );
            ergebnisMelden(e.ergebnis);
            auswahl.warmMerken();
          }
        },
        steuerung.signal
      );
    } catch (fehler) {
      if (fehler.name !== "AbortError") antwort.textContent += `\n[${fehler}]`;
    } finally {
      antwort.classList.remove("laeuft");
      los.disabled = false;
      abbrechen.disabled = true;
    }
  });
  abbrechen.addEventListener("click", () => steuerung?.abort());

  return {
    karte,
    dokumentGesetzt(d) {
      dokument = d;
      los.disabled = false;
    },
  };
}

function textMitMarken(d) {
  return d.seiten
    .filter((s) => !s.blank)
    .map((s) => {
      const teile = (s.spans || []).map((sp) =>
        sp.trust === "verified" || sp.trust === "verified_displaced"
          ? sp.text
          : `[unsicher: ${sp.text}${sp.alt ? ` / oder: ${sp.alt}` : ""}]`
      );
      const text = teile.length ? teile.join(" ") : s.text || "";
      return `--- Seite ${s.index + 1} ---\n${text}`;
    })
    .join("\n\n");
}

// ---------- Feste Karte: Grenzen, die man selbst verschiebt ----------

function grenzenKarte() {
  const zeilen = [
    ["Gedruckter Text, Briefe, Bescheide", "99,99 % der Zeichen richtig, 57 von 59 Seiten ohne Mensch", "Gelöst. Neue Dokumentarten als Testseiten aufnehmen."],
    ["Handschrift", "91 % der Zeichen richtig, aber 0 von 77 Seiten allein freigegeben", "Nachtrainieren auf eigene Schriften und Formulare, lokal."],
    ["Technische Zeichnungen", "Notizen und Schriftfeld sicher, Maßsymbole strittig", "Eigene Prüfregeln für Maße und Toleranzen, Bildmodell für Fragen."],
    ["Stempel, Kästchen, Durchstreichungen", "Stempel 98,9 %, Durchstreichungen fast vollständig erkannt", "Bildanalyse ohne Modell, je Merkmal eine Regel."],
    ["Tempo", "rund 5.000 Seiten pro Stunde, dichte Seiten rund 600", "Mehr Seiten parallel, kleinere Prüfmodelle, zweites Gerät."],
    ["Datenschutz", "Kein Byte verlässt das Gerät", "Nichts zu tun."],
  ];
  return el("div", { class: "karte" }, [
    el("h2", { text: "Grenzen, die man selbst verschieben kann" }),
    el("p", {
      class: "klein leise",
      text: "Gemessen mit den Testsätzen des OCR-Werkzeugs auf diesem Gerät (Stand August 2026).",
    }),
    el("div", { class: "tabellenkarte" }, [
      el("table", { class: "ocr-tabelle" }, [
        el("thead", {}, el("tr", {}, ["Wo", "Heute gemessen", "Stellschraube"].map((t) => el("th", { text: t })))),
        el("tbody", {}, zeilen.map((z) => el("tr", {}, z.map((t) => el("td", { text: t }))))),
      ]),
    ]),
  ]);
}

function kachel(name, wert, einheit) {
  return el("div", { class: "kachel" }, [
    el("div", { class: "name", text: name }),
    el("div", {}, [el("span", { class: "wert", text: wert }), el("span", { class: "einheit", text: einheit })]),
  ]);
}

function escape(text) {
  return String(text ?? "").replace(/[&<>"]/g, (z) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[z]);
}
