// Reiter 3: Last. Mehrere Anfragen gleichzeitig, eine Bahn je Anfrage.

import { el, einsetzen, sekunden, tempo, ganz, zahl } from "./format.js";
import { strom } from "./api.js";
import { store, bus, ergebnisMelden } from "./store.js";
import { ModellAuswahl } from "./auswahl.js";
import { meldung, meldungLeeren } from "./meldungen.js";

export function lastAufbauen(wurzel) {
  const auswahl = new ModellAuswahl({});
  const stufen = el("div", { class: "zeile" });
  const prompt = el("textarea", { spellcheck: "false" });
  const bahnraum = el("div", { class: "bahnen" });
  const auswertung = el("div", {});
  const meldungsfeld = el("div", {});
  const parallelhinweis = el("p", { class: "klein leise" });
  let gewaehlt = null;   // kommt aus der Konfiguration (lasttest.standard)
  let steuerung = null;
  const bahnen = new Map();

  const starten = el("button", { class: "knopf", type: "button", text: "Lasttest starten" });
  const abbrechen = el("button", { class: "knopf leise", type: "button", text: "Abbrechen", disabled: true });
  starten.addEventListener("click", () => lauf());
  abbrechen.addEventListener("click", () => steuerung?.abort());

  function stufenZeichnen() {
    const cfg = store.station?.lasttest;
    if (!cfg) return;
    if (gewaehlt === null || !cfg.stufen.includes(gewaehlt)) gewaehlt = cfg.standard;
    stufen.replaceChildren(
      el("span", { class: "feld", text: "Gleichzeitige Anfragen" }),
      ...cfg.stufen.map((n) =>
        el("button", {
          class: `knopf ${n === gewaehlt ? "" : "leise"} klein`,
          type: "button",
          text: String(n),
          onclick: () => {
            gewaehlt = n;
            stufenZeichnen();
          },
        })
      )
    );
    parallelhinweis.textContent = cfg.hinweis_parallelitaet
      ? `Server-Einstellung an dieser Station: ${cfg.hinweis_parallelitaet}`
      : "Zur Parallelität dieser Station ist keine Angabe hinterlegt.";
  }

  function bahnenZeichnen(anzahl) {
    bahnen.clear();
    const max = store.station?.generierung?.max_tokens || 300;
    bahnraum.replaceChildren(
      ...Array.from({ length: anzahl }, (_, i) => {
        const nr = i + 1;
        const fuellung = el("div", { class: "bahn-fuellung" });
        const wert = el("span", { class: "bahn-wert", text: "wartet" });
        const zeile = el("div", { class: "bahn" }, [
          el("span", { class: "bahn-nr", text: String(nr) }),
          el("div", { class: "bahn-bahn" }, [fuellung]),
          wert,
        ]);
        bahnen.set(nr, { fuellung, wert, zeile, max });
        return zeile;
      })
    );
  }

  function bahnSetzen(nr, tokens, zustand) {
    const bahn = bahnen.get(nr);
    if (!bahn) return;
    const anteil = Math.min(100, (tokens / bahn.max) * 100);
    bahn.fuellung.style.width = `${anteil}%`;
    bahn.fuellung.className = `bahn-fuellung ${zustand || ""}`;
    bahn.wert.textContent = `${ganz(tokens)} Token`;
  }

  async function lauf() {
    const { backend, modell } = auswahl.wert();
    if (!modell) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Für diese Laufzeit ist kein Modell verfügbar." });
      return;
    }
    if (!prompt.value.trim()) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Bitte geben Sie einen Prompt ein." });
      return;
    }
    meldungLeeren(meldungsfeld);
    auswertung.replaceChildren(el("p", { class: "leise", text: "Der Lasttest läuft …" }));
    bahnenZeichnen(gewaehlt);
    starten.disabled = true;
    abbrechen.disabled = false;
    steuerung = new AbortController();

    try {
      await strom(
        "/api/lasttest",
        { backend, modell, parallel: gewaehlt, prompt: prompt.value },
        (ereignis) => {
          if (ereignis.art === "bahn") bahnSetzen(ereignis.nr, ereignis.tokens, "");
          else if (ereignis.art === "bahn_fertig") {
            bahnSetzen(ereignis.nr, ereignis.tokens, "fertig");
            const bahn = bahnen.get(ereignis.nr);
            if (bahn) {
              bahn.wert.textContent =
                `${ganz(ereignis.tokens)} Token, erstes Wort nach ${sekunden(ereignis.messung.ttft_s)} s`;
            }
          } else if (ereignis.art === "bahn_fehler") {
            const bahn = bahnen.get(ereignis.nr);
            if (bahn) {
              bahn.fuellung.className = "bahn-fuellung fehler";
              bahn.wert.textContent = "gescheitert";
            }
            meldung(meldungsfeld, {
              art: "fehler",
              nachricht: `Bahn ${ereignis.nr}: ${ereignis.nachricht}`,
              detail: ereignis.detail,
            });
          } else if (ereignis.art === "ergebnis") {
            auswertungZeichnen(ereignis.ergebnis);
            auswahl.warmMerken();
            if (ereignis.ergebnis_zeile) ergebnisMelden(ereignis.ergebnis_zeile);
          }
        },
        steuerung.signal
      );
    } catch (fehler) {
      if (fehler.name === "AbortError") {
        meldung(meldungsfeld, { nachricht: "Der Lasttest wurde abgebrochen." });
        auswertung.replaceChildren();
      } else {
        meldung(meldungsfeld, {
          art: "fehler",
          nachricht: "Die Verbindung zum Messstand ist abgebrochen.",
          detail: String(fehler),
        });
      }
    } finally {
      starten.disabled = false;
      abbrechen.disabled = true;
      steuerung = null;
    }
  }

  function auswertungZeichnen(e) {
    auswertung.replaceChildren(
      el("div", { class: "kacheln" }, [
        kachel("Gesamtdurchsatz", tempo(e.durchsatz_tps), "Token/s"),
        kachel("Wartezeit im Schnitt", sekunden(e.ttft_mittel_s), "s"),
        kachel("Schlechteste Wartezeit", sekunden(e.ttft_schlechtester_s), "s"),
        kachel("Wanduhrzeit", sekunden(e.wanduhr_s), "s"),
      ]),
      el("p", { class: "lastsatz", text: e.satz }),
      el("div", { class: "hinweiszeile" }, [
        el("span", {
          text:
            `${ganz(e.fertige_bahnen)} von ${ganz(e.parallel)} ` +
            `${e.parallel === 1 ? "Bahn" : "Bahnen"} fertig`,
        }),
        el("span", { text: `${ganz(e.gesamt_tokens)} Token insgesamt erzeugt` }),
        el("span", { text: "Ein Token ist etwa ein Wortteil." }),
      ])
    );
  }

  function kachel(name, wert, einheit) {
    return el("div", { class: "kachel" }, [
      el("div", { class: "name", text: name }),
      el("div", {}, [
        el("span", { class: "wert", text: wert }),
        el("span", { class: "einheit", text: einheit }),
      ]),
    ]);
  }

  function vorlageEinsetzen() {
    const karte = store.station?.aufgabenkarte?.teil1;
    if (!karte) return;
    prompt.value = einsetzen(karte.prompt, { text: store.station.beispieltext || "" });
  }

  function stationUebernehmen() {
    if (!store.station) return;
    stufenZeichnen();
    if (!prompt.value) vorlageEinsetzen();
  }

  bus.addEventListener("station", stationUebernehmen);
  stationUebernehmen();
  bahnenZeichnen(gewaehlt || 1);

  wurzel.replaceChildren(
    el("div", { class: "karte" }, [
      el("h2", { text: "Last" }),
      el("p", {
        class: "leise",
        text:
          "Mehrere Anfragen gleichzeitig an dieselbe Laufzeit, so wie mehrere " +
          "Personen gleichzeitig fragen würden. Jede Bahn bekommt einen eigenen " +
          "Prompt mit Nummer, damit kein Zwischenspeicher das Ergebnis schönt.",
      }),
      auswahl.wurzel,
      stufen,
      el("label", { class: "feld", style: "margin-top:.8rem" }, ["Prompt für alle Bahnen", prompt]),
      el("div", { class: "zeile", style: "margin-top:.6rem" }, [
        starten,
        abbrechen,
        el("button", {
          class: "knopf leise klein",
          type: "button",
          text: "Aufgabe einsetzen",
          onclick: vorlageEinsetzen,
        }),
      ]),
      parallelhinweis,
      meldungsfeld,
    ]),
    el("div", { class: "karte" }, [el("h2", { text: "Auswertung" }), auswertung]),
    el("div", { class: "karte" }, [el("h2", { text: "Bahnen" }), bahnraum])
  );
}
