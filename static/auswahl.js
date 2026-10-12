// Auswahl von Laufzeit und Modell, inklusive Vorladen-Knopf.

import { el } from "./format.js";
import { senden } from "./api.js";
import { backends, backendVon, erstesNutzbares, bus } from "./store.js";

export class ModellAuswahl {
  constructor({ mitVorladen = true, aufAenderung = null, beschriftung = "" } = {}) {
    this.aufAenderung = aufAenderung;
    this.laufzeit = el("select", { onchange: () => this.#laufzeitGewechselt() });
    this.modell = el("select", { onchange: () => this.#melden() });
    this.meldung = el("span", { class: "klein leise" });
    const felder = [
      el("label", { class: "feld" }, [
        beschriftung ? `Laufzeit ${beschriftung}` : "Laufzeit",
        this.laufzeit,
      ]),
      el("label", { class: "feld" }, ["Modell", this.modell]),
    ];
    if (mitVorladen) {
      this.vorladen = el("button", {
        class: "knopf leise klein",
        type: "button",
        text: "Modell vorladen",
        onclick: () => this.#vorladen(),
      });
      felder.push(el("div", {}, [this.vorladen]));
    }
    this.wurzel = el("div", { class: "zeile" }, [...felder, this.meldung]);
    bus.addEventListener("station", () => this.neuzeichnen());
    this.neuzeichnen();
  }

  neuzeichnen() {
    const vorher = this.wert();
    this.laufzeit.replaceChildren(
      ...backends().map((b) =>
        el("option", {
          value: b.id,
          text: b.online ? b.label : `${b.label} — nicht erreichbar`,
        })
      )
    );
    if (vorher.backend && backendVon(vorher.backend)) this.laufzeit.value = vorher.backend;
    else if (!this.laufzeit.value) this.laufzeit.value = erstesNutzbares().backend;
    this.#modelleZeichnen(vorher.modell);
  }

  #modelleZeichnen(wunsch) {
    const backend = backendVon(this.laufzeit.value);
    const modelle = backend?.modelle ?? [];
    this.modell.replaceChildren(
      ...modelle.map((m) =>
        el("option", {
          value: m.id,
          disabled: !m.vorhanden,
          text: m.vorhanden ? m.label : `${m.label} — nicht geladen`,
        })
      )
    );
    const passt = modelle.find((m) => m.id === wunsch && m.vorhanden);
    const ersatz = modelle.find((m) => m.vorhanden) || modelle[0];
    const gewaehlt = passt || ersatz;
    if (gewaehlt) this.modell.value = gewaehlt.id;
    this.#warmzeichen();
  }

  #warmzeichen() {
    const backend = backendVon(this.laufzeit.value);
    const modell = backend?.modelle.find((m) => m.id === this.modell.value);
    if (!modell) {
      this.meldung.textContent = "";
      return;
    }
    if (!modell.vorhanden) {
      this.meldung.textContent = "Dieses Modell liegt auf diesem Gerät nicht vor.";
      return;
    }
    this.meldung.textContent = modell.warm ? "Modell ist warm." : "Modell ist noch kalt.";
  }

  #laufzeitGewechselt() {
    this.#modelleZeichnen(this.modell.value);
    this.#melden();
  }

  #melden() {
    this.#warmzeichen();
    this.aufAenderung?.(this.wert());
  }

  async #vorladen() {
    const { backend, modell } = this.wert();
    if (!modell) return;
    this.vorladen.disabled = true;
    const vorher = this.meldung.textContent;
    this.meldung.textContent = "Modell wird geladen …";
    try {
      const antwort = await senden("/api/warmup", { backend, modell });
      this.meldung.textContent = antwort.nachricht || vorher;
      if (antwort.ok) {
        const m = backendVon(backend)?.modelle.find((m) => m.id === modell);
        if (m) m.warm = true;
      }
    } catch (fehler) {
      this.meldung.textContent = `Vorladen fehlgeschlagen: ${fehler.message}`;
    } finally {
      this.vorladen.disabled = false;
    }
  }

  wert() {
    return { backend: this.laufzeit.value, modell: this.modell.value };
  }

  setzen({ backend, modell }) {
    if (backend) this.laufzeit.value = backend;
    this.#modelleZeichnen(modell);
  }

  warmMerken() {
    const { backend, modell } = this.wert();
    const m = backendVon(backend)?.modelle.find((m) => m.id === modell);
    if (m) m.warm = true;
    this.#warmzeichen();
  }
}
