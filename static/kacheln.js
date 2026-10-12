// Die vier grossen Messwert-Kacheln. Fuellen sich live.

import { el, sekunden, tempo, ganz } from "./format.js";

const FELDER = [
  { schluessel: "ttft_s", name: "Zeit bis zum ersten Wort", einheit: "s", formatieren: sekunden },
  { schluessel: "prefill_tps", name: "Lesetempo", einheit: "Token/s", formatieren: tempo },
  { schluessel: "decode_tps", name: "Schreibtempo", einheit: "Token/s", formatieren: tempo },
  { schluessel: "total_s", name: "Gesamtzeit", einheit: "s", formatieren: sekunden },
];

export class Kacheln {
  constructor(wurzel) {
    this.wurzel = wurzel;
    this.werte = {};
    this.uhr = null;
    this.start_ms = 0;
    this.ttft_ms = null;
    this.hinweis = el("div", { class: "hinweiszeile" });
    this.#bauen();
  }

  #bauen() {
    this.gitter = el("div", { class: "kacheln" });
    this.anzeigen = {};
    for (const feld of FELDER) {
      const wert = el("span", { class: "wert", text: "–" });
      const kachel = el("div", { class: "kachel" }, [
        el("div", { class: "name", text: feld.name }),
        el("div", {}, [wert, el("span", { class: "einheit", text: feld.einheit })]),
      ]);
      this.anzeigen[feld.schluessel] = { wert, kachel, feld };
      this.gitter.append(kachel);
    }
    this.wurzel.replaceChildren(this.gitter, this.hinweis);
  }

  leeren() {
    this.#uhrAus();
    for (const { wert, kachel } of Object.values(this.anzeigen)) {
      wert.textContent = "–";
      kachel.classList.remove("laeuft");
    }
    this.hinweis.replaceChildren();
  }

  start() {
    this.leeren();
    this.start_ms = performance.now();
    this.ttft_ms = null;
    for (const { kachel } of Object.values(this.anzeigen)) kachel.classList.add("laeuft");
    this.uhr = setInterval(() => this.#ticken(), 100);
    this.#ticken();
  }

  #ticken() {
    const vergangen = (performance.now() - this.start_ms) / 1000;
    this.#setzen("total_s", vergangen);
  }

  #uhrAus() {
    if (this.uhr) clearInterval(this.uhr);
    this.uhr = null;
  }

  // Erstes sichtbares Token: Zeit bis zum ersten Wort steht sofort.
  ersterToken() {
    if (this.ttft_ms !== null) return;
    this.ttft_ms = performance.now() - this.start_ms;
    this.#setzen("ttft_s", this.ttft_ms / 1000);
  }

  #setzen(schluessel, wert) {
    const anzeige = this.anzeigen[schluessel];
    if (!anzeige) return;
    anzeige.wert.textContent = anzeige.feld.formatieren(wert);
  }

  // Endgueltige Werte aus der Messung des Servers.
  fertig(messung) {
    this.#uhrAus();
    for (const feld of FELDER) {
      this.#setzen(feld.schluessel, messung[feld.schluessel]);
      this.anzeigen[feld.schluessel].kachel.classList.remove("laeuft");
    }
    this.#hinweise(messung);
  }

  abbruch() {
    this.#uhrAus();
    for (const { kachel } of Object.values(this.anzeigen)) kachel.classList.remove("laeuft");
  }

  #hinweise(messung) {
    const teile = [];
    teile.push(
      el("span", {
        text: `Token rein ${ganz(messung.prompt_tokens)} / raus ${ganz(messung.output_tokens)}`,
      })
    );
    teile.push(
      el("span", { class: `marke ${messung.kalt ? "kalt" : "warm"}` }, [
        messung.kalt ? "kalt gestartet" : "warm",
      ])
    );
    if (messung.load_s) {
      teile.push(el("span", { text: `Ladezeit ${sekunden(messung.load_s)} s` }));
    }
    teile.push(
      el("span", {
        text:
          messung.quelle === "server"
            ? "Tempowerte vom Server gemeldet"
            : "Tempowerte hier gemessen",
      })
    );
    if (messung.geschaetzt) {
      teile.push(el("span", { class: "marke geschaetzt", text: "geschätzt" }));
    }
    if (messung.denk_tokens) {
      teile.push(
        el("span", { text: `${ganz(messung.denk_tokens)} Denk-Abschnitte herausgefiltert` })
      );
    }
    this.hinweis.replaceChildren(...teile);
  }
}
