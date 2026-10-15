// Reiter „Foto → Daten“: Foto lesen lassen, feste Angaben als Tabelle, gegen
// eine Musterloesung bewertet. Laeuft auf jeder Station mit einem
// Bild-faehigen Modell, damit Laptop, Mac mini und Spark vergleichbar sind.

import { el, zahl, ganz, sekunden } from "./format.js";
import { holen, strom } from "./api.js";
import { ergebnisMelden } from "./store.js";
import { ModellAuswahl } from "./auswahl.js";
import { meldung, meldungLeeren } from "./meldungen.js";

// Jedes Foto wird vor dem Senden gleich verkleinert: gleiche Bedingungen auf
// allen Stationen, und das Modell bekommt nicht 12 Megapixel geschickt.
const MAX_KANTE = 1600;
const STAPEL_STUFEN = [4, 8, 16, 32];

export function fotoAufbauen(wurzel) {
  const auswahl = new ModellAuswahl({});
  const vorlageWahl = el("select", {});
  const beispielzeile = el("div", { class: "foto-beispiele" });
  const eigenesFoto = el("input", { type: "file", accept: "image/*" });
  const vorschau = el("img", { class: "foto-vorschau", alt: "Gewähltes Foto", hidden: true });
  const los = el("button", { class: "knopf", type: "button", text: "Foto lesen" });
  const abbrechen = el("button", { class: "knopf leise", type: "button", text: "Abbrechen", disabled: true });
  const promptfeld = el("pre", { class: "promptansicht", hidden: true });
  const meldungsfeld = el("div", {});
  const werte = { erstes: wert(), schreiben: wert(), gesamt: wert(), richtig: wert() };
  const richtigEinheit = el("span", { class: "einheit", text: "" });
  const ergebnisfeld = el("div", {});
  const rohfeld = el("pre", { class: "promptansicht", hidden: true });
  const stapel = stapelBauen();

  let vorlagen = [];
  let beispiele = [];
  let gewaehlt = null; // { b64, mime, beispiel | null, url }
  let steuerung = null;

  los.addEventListener("click", () => lesen());
  abbrechen.addEventListener("click", () => steuerung?.abort());
  eigenesFoto.addEventListener("change", async () => {
    const datei = eigenesFoto.files?.[0];
    if (!datei) return;
    const url = URL.createObjectURL(datei);
    await fotoSetzen(url, null);
    eigenesFoto.value = "";
  });

  wurzel.append(
    el("div", { class: "karte" }, [
      el("h2", { text: "Foto → Daten" }),
      el("p", {
        class: "leise",
        text:
          "Ein Handyfoto von Beleg, Lieferschein, Typenschild oder Whiteboard wird zu einer Tabelle. " +
          "Dasselbe Foto auf jeder Station: Wie schnell, und wie viele Angaben stimmen?",
      }),
      beispielzeile,
      el("div", { class: "zeile" }, [
        el("label", { class: "feld" }, ["Eigenes Foto", eigenesFoto]),
        el("label", { class: "feld" }, ["Was steht drauf?", vorlageWahl]),
      ]),
      el("div", { style: "margin-top:.6rem" }, [auswahl.wurzel]),
      el("div", { class: "zeile", style: "margin:.7rem 0" }, [
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
      promptfeld,
      el("div", { class: "kacheln" }, [
        kachel("Erstes Zeichen (Foto lesen)", werte.erstes, "s"),
        kachel("Schreibtempo", werte.schreiben, "Token/s"),
        kachel("Gesamtzeit", werte.gesamt, "s"),
        el("div", { class: "kachel" }, [
          el("div", { class: "name", text: "Angaben richtig" }),
          el("div", {}, [werte.richtig, richtigEinheit]),
        ]),
      ]),
      meldungsfeld,
    ]),
    el("div", { class: "spalten-2" }, [
      el("div", { class: "karte" }, [el("h3", { text: "Foto" }), vorschau]),
      el("div", { class: "karte" }, [
        el("h3", { text: "Gelesene Angaben" }),
        ergebnisfeld,
        el("button", {
          class: "knopf leise klein",
          type: "button",
          text: "Rohe Antwort des Modells",
          style: "margin-top:.6rem",
          onclick: () => {
            rohfeld.hidden = !rohfeld.hidden;
          },
        }),
        rohfeld,
      ]),
    ]),
    stapel.karte
  );

  // ---------- Vorlagen und Beispiele ----------

  async function laden() {
    try {
      const d = await holen("/api/foto/vorlagen");
      vorlagen = d.vorlagen;
      beispiele = d.beispiele;
    } catch (fehler) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Vorlagen fehlen.", detail: String(fehler) });
      return;
    }
    vorlageWahl.replaceChildren(...vorlagen.map((v) => el("option", { value: v.id, text: v.titel })));
    beispielzeile.replaceChildren(
      ...beispiele.map((b) =>
        el(
          "button",
          {
            type: "button",
            class: "foto-beispiel",
            title: b.titel,
            onclick: () => fotoSetzen(`/api/foto/bild/${b.datei}`, b),
          },
          [el("img", { src: `/api/foto/bild/${b.datei}`, alt: b.titel }), el("span", { text: b.titel })]
        )
      )
    );
    stapel.beispieleSetzen(beispiele);
    if (beispiele[0]) fotoSetzen(`/api/foto/bild/${beispiele[0].datei}`, beispiele[0]);
  }

  async function fotoSetzen(url, beispiel) {
    try {
      const { b64, mime } = await verkleinern(url);
      gewaehlt = { b64, mime, beispiel, url };
    } catch (fehler) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Das Foto ließ sich nicht öffnen.", detail: String(fehler) });
      return;
    }
    vorschau.src = url;
    vorschau.hidden = false;
    if (beispiel) vorlageWahl.value = beispiel.vorlage;
    for (const k of beispielzeile.children) k.classList.toggle("aktiv", k.title === beispiel?.titel);
    ergebnisfeld.replaceChildren();
    rohfeld.textContent = "";
    for (const w of Object.values(werte)) w.textContent = "–";
    richtigEinheit.textContent = "";
    meldungLeeren(meldungsfeld);
  }

  // ---------- Einzelnes Foto lesen ----------

  async function lesen() {
    if (!gewaehlt) return;
    const { backend, modell } = auswahl.wert();
    los.disabled = true;
    abbrechen.disabled = false;
    meldungLeeren(meldungsfeld);
    ergebnisfeld.replaceChildren(el("div", { class: "leise", text: "Das Modell schaut sich das Foto an …" }));
    rohfeld.textContent = "";
    for (const w of Object.values(werte)) w.textContent = "…";
    richtigEinheit.textContent = "";
    const start = performance.now();
    let erstes = null;
    steuerung = new AbortController();
    try {
      await strom(
        "/api/foto/lesen",
        {
          backend,
          modell,
          vorlage: vorlageWahl.value,
          bild_b64: gewaehlt.b64,
          mime: gewaehlt.mime,
          beispiel: gewaehlt.beispiel?.datei || null,
        },
        (e) => {
          if (e.art === "start") promptfeld.textContent = `System: ${e.system}\n\n${e.prompt}\n\n[+ das Foto]`;
          else if (e.art === "text") {
            if (erstes === null) {
              erstes = (performance.now() - start) / 1000;
              werte.erstes.textContent = sekunden(erstes);
            }
            rohfeld.textContent += e.text;
          } else if (e.art === "fehler") {
            meldung(meldungsfeld, { art: "fehler", nachricht: e.nachricht, detail: e.detail });
          } else if (e.art === "messung") {
            const m = e.messung;
            werte.erstes.textContent = sekunden(m.ttft_s ?? erstes);
            werte.schreiben.textContent = m.decode_tps ? ganz(Math.round(m.decode_tps)) : "–";
            werte.gesamt.textContent = sekunden(m.total_s);
            if (e.ergebnis) ergebnisMelden(e.ergebnis);
            if (m.kalt) {
              meldung(meldungsfeld, {
                nachricht:
                  "Das Modell musste erst geladen werden, die Zeiten enthalten das Laden. " +
                  "Für den Vergleich zwischen den Stationen das Foto noch einmal lesen.",
              });
            }
            auswahl.warmMerken();
          } else if (e.art === "auswertung") {
            auswertungZeigen(e);
          }
        },
        steuerung.signal
      );
    } catch (fehler) {
      if (fehler.name !== "AbortError") meldung(meldungsfeld, { art: "fehler", nachricht: String(fehler) });
    } finally {
      los.disabled = false;
      abbrechen.disabled = true;
    }
  }

  function auswertungZeigen(e) {
    const vorlage = vorlagen.find((v) => v.id === e.vorlage);
    if (!e.daten) {
      ergebnisfeld.replaceChildren(
        el("div", { class: "meldung fehler", text: "Das Modell hat kein gültiges JSON geliefert. Siehe rohe Antwort." })
      );
      werte.richtig.textContent = "0";
      return;
    }
    const b = e.bewertung;
    if (b) {
      werte.richtig.textContent = ganz(b.punkte);
      richtigEinheit.textContent = ` von ${b.von}`;
    } else {
      werte.richtig.textContent = "–";
      richtigEinheit.textContent = "keine Musterlösung";
    }
    ergebnisfeld.replaceChildren(...tabellenBauen(vorlage, e.daten, b), csvKnopf(vorlage, e.daten));
  }

  laden();
  return {};
}

// ---------- Tabellen ----------

function tabellenBauen(vorlage, daten, bewertung) {
  const teile = [];
  const felder = new Map((bewertung?.felder || []).map((f) => [f.name, f]));
  teile.push(
    el("table", { class: "ocr-tabelle foto-tabelle" }, [
      el("thead", {}, el("tr", {}, ["Angabe", "Gelesen", bewertung ? "Muster" : null].filter(Boolean).map((t) => el("th", { text: t })))),
      el(
        "tbody",
        {},
        vorlage.felder.map((f) => {
          const b = felder.get(f.name);
          return el("tr", { class: b ? (b.ok ? "foto-ok" : "foto-falsch") : "" }, [
            el("td", { text: f.label }),
            el("td", { text: anzeige(daten[f.name]) }),
            bewertung ? el("td", { class: "leise", text: b ? anzeige(b.muster) : "" }) : null,
          ]);
        })
      ),
    ])
  );
  const liste = vorlage.liste;
  if (liste) {
    const zeilen = bewertung?.liste?.length
      ? bewertung.liste.map((z) => ({ werte: z.gelesen || {}, ok: z.ok, fehlt: !z.gelesen, muster: z.muster }))
      : (daten[liste.name] || []).map((w) => ({ werte: w, ok: null }));
    for (const extra of bewertung?.zusaetzlich || []) zeilen.push({ werte: extra, ok: null, extra: true });
    teile.push(
      el("h3", { text: liste.label, style: "margin-top:1rem" }),
      el("table", { class: "ocr-tabelle foto-tabelle" }, [
        el("thead", {}, el("tr", {}, liste.felder.map((f) => el("th", { text: f.label })))),
        el(
          "tbody",
          {},
          zeilen.map((z) =>
            el(
              "tr",
              { class: z.extra ? "foto-extra" : "" },
              liste.felder.map((f, i) =>
                el("td", {
                  class: z.ok ? (z.ok[i] ? "foto-ok" : "foto-falsch") : "",
                  title: z.muster ? `Muster: ${anzeige(z.muster[f.name])}` : z.extra ? "Steht nicht in der Musterlösung" : "",
                  text: z.fehlt ? (i === 0 ? `fehlt: ${anzeige(z.muster[f.name])}` : "") : anzeige(z.werte[f.name]),
                })
              )
            )
          )
        ),
      ])
    );
  }
  return teile;
}

function csvKnopf(vorlage, daten) {
  return el("button", {
    class: "knopf leise klein",
    type: "button",
    text: "Als CSV für Excel",
    style: "margin-top:.6rem;margin-right:.5rem",
    onclick: () => {
      const z = (w) => `"${anzeige(w).replace(/"/g, '""')}"`;
      const zeilen = [vorlage.felder.map((f) => z(f.label)).join(";"), vorlage.felder.map((f) => z(daten[f.name])).join(";")];
      if (vorlage.liste) {
        zeilen.push("", vorlage.liste.felder.map((f) => z(f.label)).join(";"));
        for (const e of daten[vorlage.liste.name] || []) zeilen.push(vorlage.liste.felder.map((f) => z(e[f.name])).join(";"));
      }
      const url = URL.createObjectURL(new Blob(["﻿" + zeilen.join("\r\n")], { type: "text/csv;charset=utf-8" }));
      const a = el("a", { href: url, download: `${vorlage.id}.csv` });
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
}

function anzeige(w) {
  if (w === null || w === undefined) return "–";
  if (typeof w === "number") return w.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  if (typeof w === "object") return JSON.stringify(w);
  return String(w);
}

// ---------- Stapel: viele Fotos gleichzeitig ----------

function stapelBauen() {
  const auswahl = new ModellAuswahl({ beschriftung: "" });
  const anzahl = el(
    "select",
    {},
    STAPEL_STUFEN.map((n) => el("option", { value: n, text: `${n} Fotos` }))
  );
  const los = el("button", { class: "knopf", type: "button", text: "Stapel starten" });
  const bahnen = el("div", { class: "bahnen foto-stapel" });
  const zusammenfassung = el("div", { class: "kacheln" });
  let beispiele = [];
  let bilder = null; // vorbereitete Base64-Fotos

  const karte = el("div", { class: "karte" }, [
    el("h2", { text: "Stapel: viele Fotos auf einmal" }),
    el("p", {
      class: "leise",
      text:
        "Die Beispielfotos reihum, alle gleichzeitig abgeschickt. Wie viele Belege schafft dieses Gerät pro Minute, " +
        "und leidet die Qualität, wenn es voll ausgelastet ist?",
    }),
    auswahl.wurzel,
    el("div", { class: "zeile", style: "margin:.6rem 0" }, [el("label", { class: "feld" }, ["Anzahl", anzahl]), los]),
    zusammenfassung,
    bahnen,
  ]);

  los.addEventListener("click", async () => {
    if (!beispiele.length) return;
    los.disabled = true;
    const n = Number(anzahl.value);
    const { backend, modell } = auswahl.wert();
    if (!bilder) bilder = await Promise.all(beispiele.map((b) => verkleinern(`/api/foto/bild/${b.datei}`)));
    const start = performance.now();
    const ergebnisse = [];
    const fuellungen = [];
    bahnen.replaceChildren(
      ...Array.from({ length: n }, (_, i) => {
        const fuellung = el("div", { class: "bahn-fuellung" });
        const wert = el("span", { class: "bahn-wert", text: "wartet" });
        fuellungen.push({ fuellung, wert });
        return el("div", { class: "bahn" }, [
          el("span", { class: "bahn-nr", text: beispiele[i % beispiele.length].titel }),
          el("div", { class: "bahn-bahn" }, [fuellung]),
          wert,
        ]);
      })
    );
    zusammenfassung.replaceChildren();
    const uhr = setInterval(() => {
      const t = (performance.now() - start) / 1000;
      for (const f of fuellungen) if (!f.fertig) f.fuellung.style.width = `${Math.min(95, t * 3)}%`;
    }, 200);

    await Promise.all(
      Array.from({ length: n }, async (_, i) => {
        const b = beispiele[i % beispiele.length];
        const foto = bilder[i % beispiele.length];
        const f = fuellungen[i];
        let ergebnis = { ok: false };
        try {
          await strom(
            "/api/foto/lesen",
            { backend, modell, vorlage: b.vorlage, bild_b64: foto.b64, mime: foto.mime, beispiel: b.datei, stapel: true },
            (e) => {
              if (e.art === "text" && f.wert.textContent === "wartet") f.wert.textContent = "liest …";
              if (e.art === "auswertung") {
                ergebnis = { ok: Boolean(e.daten), punkte: e.bewertung?.punkte ?? 0, von: e.bewertung?.von ?? 0 };
              }
            }
          );
        } catch {
          /* zaehlt als nicht gelesen */
        }
        ergebnis.zeit = (performance.now() - start) / 1000;
        ergebnisse.push(ergebnis);
        f.fertig = true;
        f.fuellung.style.width = "100%";
        f.fuellung.classList.add(ergebnis.ok ? "fertig" : "fehler");
        f.wert.textContent = ergebnis.ok ? `${ergebnis.punkte}/${ergebnis.von} · ${sekunden(ergebnis.zeit)} s` : "kein JSON";
      })
    );
    clearInterval(uhr);
    const gesamt = (performance.now() - start) / 1000;
    const punkte = ergebnisse.reduce((s, e) => s + (e.punkte || 0), 0);
    const von = ergebnisse.reduce((s, e) => s + (e.von || 0), 0);
    zusammenfassung.replaceChildren(
      kachel("Gesamtzeit", wertMit(sekunden(gesamt)), "s"),
      kachel("Fotos pro Minute", wertMit(zahl((n / gesamt) * 60, 1)), ""),
      kachel("Langsamstes Foto", wertMit(sekunden(Math.max(...ergebnisse.map((e) => e.zeit)))), "s"),
      kachel("Angaben richtig", wertMit(von ? zahl((100 * punkte) / von, 0) : "–"), "%")
    );
    los.disabled = false;
  });

  return {
    karte,
    beispieleSetzen(liste) {
      beispiele = liste;
      bilder = null;
    },
  };
}

// ---------- Hilfen ----------

async function verkleinern(url) {
  const bild = new Image();
  bild.src = url;
  await bild.decode();
  const faktor = Math.min(1, MAX_KANTE / Math.max(bild.naturalWidth, bild.naturalHeight));
  const leinwand = document.createElement("canvas");
  leinwand.width = Math.round(bild.naturalWidth * faktor);
  leinwand.height = Math.round(bild.naturalHeight * faktor);
  leinwand.getContext("2d").drawImage(bild, 0, 0, leinwand.width, leinwand.height);
  const daten = leinwand.toDataURL("image/jpeg", 0.9);
  return { b64: daten.split(",")[1], mime: "image/jpeg" };
}

function wert() {
  return el("span", { class: "wert", text: "–" });
}

function wertMit(text) {
  return el("span", { class: "wert", text });
}

function kachel(name, wertKnoten, einheit) {
  return el("div", { class: "kachel" }, [
    el("div", { class: "name", text: name }),
    el("div", {}, [wertKnoten, el("span", { class: "einheit", text: einheit })]),
  ]);
}
