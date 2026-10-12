// Reiter 5: Ergebnisse. Tabelle aller Messungen dieser Sitzung plus CSV.

import { el, sekunden, tempo, ganz } from "./format.js";
import { holen, senden } from "./api.js";
import { bus } from "./store.js";
import { meldung } from "./meldungen.js";

const SPALTEN = [
  { schluessel: "nr", titel: "Nr" },
  { schluessel: "zeitpunkt", titel: "Zeit" },
  { schluessel: "reiter", titel: "Reiter" },
  { schluessel: "backend_label", titel: "Laufzeit" },
  { schluessel: "modell_label", titel: "Modell" },
  { schluessel: "ttft_s", titel: "Erstes Wort (s)", formatieren: sekunden, zahl: true },
  { schluessel: "prefill_tps", titel: "Lesetempo", formatieren: tempo, zahl: true },
  { schluessel: "decode_tps", titel: "Schreibtempo", formatieren: tempo, zahl: true },
  { schluessel: "prompt_tokens", titel: "Token rein", formatieren: ganz, zahl: true },
  { schluessel: "output_tokens", titel: "Token raus", formatieren: ganz, zahl: true },
  { schluessel: "total_s", titel: "Gesamtzeit (s)", formatieren: sekunden, zahl: true },
  { schluessel: "temperatur", titel: "Zustand" },
  { schluessel: "quelle", titel: "Quelle" },
  { schluessel: "notiz", titel: "Notiz" },
];

export function ergebnisseAufbauen(wurzel) {
  const koerper = el("tbody", {});
  const meldungsfeld = el("div", {});
  const anzahl = el("span", { class: "leise klein" });
  let eintraege = [];

  const tabelle = el("table", { class: "tabelle" }, [
    el("thead", {}, [
      el("tr", {}, SPALTEN.map((s) => el("th", { class: s.zahl ? "zahl" : "", text: s.titel }))),
    ]),
    koerper,
  ]);

  function zeichnen() {
    anzahl.textContent = `${eintraege.length} ${eintraege.length === 1 ? "Messung" : "Messungen"} in dieser Sitzung`;
    if (!eintraege.length) {
      koerper.replaceChildren(
        el("tr", {}, [
          el("td", {
            colspan: String(SPALTEN.length),
            class: "leise",
            text: "Noch keine Messungen. Starten Sie einen Lauf im Reiter „Aufgabe“ oder „Vergleich“.",
          }),
        ])
      );
      return;
    }
    koerper.replaceChildren(
      ...[...eintraege].reverse().map((e) =>
        el("tr", {}, SPALTEN.map((s) => {
          const roh = e[s.schluessel];
          const text = s.formatieren ? s.formatieren(roh) : roh ?? "";
          return el("td", { class: s.zahl ? "zahl" : "", text: String(text) });
        }))
      )
    );
  }

  async function laden() {
    try {
      const daten = await holen("/api/ergebnisse");
      eintraege = daten.eintraege;
      zeichnen();
    } catch (fehler) {
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Die Messwerte konnten nicht geladen werden.",
        detail: String(fehler),
      });
    }
  }

  bus.addEventListener("ergebnis", (e) => {
    eintraege.push(e.detail);
    zeichnen();
  });

  wurzel.replaceChildren(
    el("div", { class: "karte" }, [
      el("h2", { text: "Ergebnisse" }),
      el("p", {
        class: "leise",
        text:
          "Alle Messungen dieser Sitzung. Nur im Speicher: ein Neustart des " +
          "Werkzeugs leert die Tabelle. Für den Flipchart die CSV-Datei speichern.",
      }),
      el("div", { class: "zeile" }, [
        el("button", {
          class: "knopf",
          type: "button",
          text: "Als CSV speichern",
          onclick: async (ev) => {
            ev.target.disabled = true;
            try {
              const antwort = await senden("/api/ergebnisse/csv", {});
              meldung(meldungsfeld, {
                art: antwort.ok ? "gut" : "",
                nachricht: antwort.nachricht,
              });
            } catch (fehler) {
              meldung(meldungsfeld, {
                art: "fehler",
                nachricht: "Speichern fehlgeschlagen.",
                detail: String(fehler),
              });
            } finally {
              ev.target.disabled = false;
            }
          },
        }),
        el("button", {
          class: "knopf leise",
          type: "button",
          text: "Tabelle leeren",
          onclick: async () => {
            await senden("/api/ergebnisse", undefined, "DELETE");
            eintraege = [];
            zeichnen();
            meldung(meldungsfeld, { nachricht: "Die Tabelle ist geleert." });
          },
        }),
        anzahl,
      ]),
      meldungsfeld,
    ]),
    el("div", { class: "karte tabellenkarte" }, [tabelle])
  );

  laden();
}
