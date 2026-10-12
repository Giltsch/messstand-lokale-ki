// Reiter 1: Aufgabe. Aufgabenkarte des Workshops, Antwort und Messwerte.

import { el, einsetzen } from "./format.js";
import { strom } from "./api.js";
import { store, bus, ergebnisMelden } from "./store.js";
import { Kacheln } from "./kacheln.js";
import { ModellAuswahl } from "./auswahl.js";
import { meldung, meldungLeeren } from "./meldungen.js";

export function aufgabeAufbauen(wurzel) {
  const auswahl = new ModellAuswahl({});
  const text = el("textarea", { spellcheck: "false" });
  const antwort = el("div", { class: "antwort" });
  const denken = el("div", { class: "denken", hidden: true });
  const meldungsfeld = el("div", {});
  const kachelraum = el("div", {});
  const kacheln = new Kacheln(kachelraum);
  const promptvorschau = el("div", { class: "klein leise" });
  const denkschalter = el("input", { type: "checkbox" });

  let abbruchsteuerung = null;

  const knopf1 = el("button", { class: "knopf", type: "button", text: "Teil 1: Zusammenfassen" });
  const knopf2 = el("button", { class: "knopf", type: "button", text: "Teil 2: Antwort entwerfen" });
  const abbrechen = el("button", {
    class: "knopf leise",
    type: "button",
    text: "Abbrechen",
    disabled: true,
  });

  knopf1.addEventListener("click", () => starten("teil1"));
  knopf2.addEventListener("click", () => starten("teil2"));
  abbrechen.addEventListener("click", () => abbruchsteuerung?.abort());

  const bedingungen = el("div", { class: "bedingungen" });

  function bedingungenZeichnen() {
    const g = store.station?.generierung;
    if (!g) return;
    bedingungen.replaceChildren(
      el("span", { html: "Gleiche Bedingungen für alle:" }),
      el("span", { html: `Temperatur <b>${String(g.temperatur).replace(".", ",")}</b>` }),
      el("span", { html: `Seed <b>${g.seed}</b>` }),
      el("span", { html: `höchstens <b>${g.max_tokens}</b> Token Antwort` }),
      el("span", { html: `Kontext <b>${g.num_ctx}</b> Token` }),
      el("span", { html: `Zeitlimit <b>${g.timeout_s} s</b>` }),
      el("label", { class: "nowrap" }, [denkschalter, " Denkschritte zulassen"])
    );
  }

  function vorschauZeichnen(welcher) {
    const karte = store.station?.aufgabenkarte?.[welcher];
    if (!karte) return;
    promptvorschau.textContent = `Anweisung ${karte.titel}: ${karte.prompt.split("\n")[0]}`;
  }

  async function starten(welcher) {
    const karte = store.station?.aufgabenkarte?.[welcher];
    if (!karte) {
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Die Aufgabenkarte konnte nicht geladen werden (presets/aufgabenkarte.yaml).",
      });
      return;
    }
    const { backend, modell } = auswahl.wert();
    if (!modell) {
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Für diese Laufzeit ist kein Modell verfügbar.",
      });
      return;
    }
    const prompt = einsetzen(karte.prompt, { text: text.value.trim() });
    vorschauZeichnen(welcher);
    meldungLeeren(meldungsfeld);
    antwort.textContent = "";
    antwort.classList.add("laeuft");
    denken.textContent = "";
    denken.hidden = true;
    kacheln.start();
    laufenLassen(true);
    abbruchsteuerung = new AbortController();

    try {
      await strom(
        "/api/chat",
        {
          backend,
          modell,
          prompt,
          reiter: "Aufgabe",
          notiz: karte.titel,
          thinking: denkschalter.checked,
        },
        (ereignis) => {
          if (ereignis.art === "text") {
            kacheln.ersterToken();
            antwort.append(ereignis.text);
          } else if (ereignis.art === "denken") {
            denken.hidden = false;
            denken.textContent += ereignis.text;
          } else if (ereignis.art === "messung") {
            kacheln.fertig(ereignis.messung);
            auswahl.warmMerken();
            ergebnisMelden(ereignis.ergebnis);
            if (ereignis.messung.kalt) {
              meldung(meldungsfeld, {
                nachricht:
                  "Das Modell war kalt: die Ladezeit steckt in der Gesamtzeit. " +
                  "Für einen fairen Vergleich bitte vorladen und erneut messen.",
              });
            }
          } else if (ereignis.art === "fehler") {
            kacheln.abbruch();
            meldung(meldungsfeld, {
              art: "fehler",
              nachricht: ereignis.nachricht,
              detail: ereignis.detail,
            });
          }
        },
        abbruchsteuerung.signal
      );
    } catch (fehler) {
      kacheln.abbruch();
      if (fehler.name === "AbortError") {
        meldung(meldungsfeld, { nachricht: "Die Anfrage wurde abgebrochen." });
      } else {
        meldung(meldungsfeld, {
          art: "fehler",
          nachricht: "Die Verbindung zum Messstand ist abgebrochen.",
          detail: String(fehler),
        });
      }
    } finally {
      antwort.classList.remove("laeuft");
      laufenLassen(false);
      abbruchsteuerung = null;
    }
  }

  function laufenLassen(laeuft) {
    knopf1.disabled = laeuft;
    knopf2.disabled = laeuft;
    abbrechen.disabled = !laeuft;
  }

  function stationUebernehmen() {
    if (!store.station) return;
    if (!text.value) text.value = store.station.beispieltext || "";
    const karte = store.station.aufgabenkarte || {};
    if (karte.teil1) knopf1.textContent = `Teil 1: ${karte.teil1.titel}`;
    if (karte.teil2) knopf2.textContent = `Teil 2: ${karte.teil2.titel}`;
    bedingungenZeichnen();
    // Standard aus der Konfiguration, danach entscheidet die Bedienung.
    if (!denkschalter.dataset.gesetzt) {
      denkschalter.checked = !!store.station.generierung?.thinking;
      denkschalter.dataset.gesetzt = "1";
    }
  }

  bus.addEventListener("station", stationUebernehmen);
  stationUebernehmen();

  wurzel.replaceChildren(
    el("div", { class: "karte" }, [
      el("h2", { text: "Aufgabenkarte" }),
      el("p", {
        class: "leise",
        text:
          "Dieselbe Aufgabe wie an jeder Station. Der Text unten ist bearbeitbar, " +
          "Sie können auch eine eigene Anfrage einsetzen.",
      }),
      auswahl.wurzel,
      bedingungen,
      el("label", { class: "feld", style: "margin-top:.8rem" }, ["Kundenanfrage", text]),
      el("div", { class: "zeile", style: "margin-top:.8rem" }, [knopf1, knopf2, abbrechen]),
      promptvorschau,
    ]),
    el("div", { class: "karte" }, [el("h2", { text: "Messwerte" }), kachelraum, meldungsfeld]),
    el("div", { class: "karte" }, [el("h2", { text: "Antwort" }), antwort, denken])
  );

  return { kacheln };
}
