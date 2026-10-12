// Reiter 4: Dokumente. PDF einlesen, fragen, Quellen sichtbar machen.

import { el, sekunden, zahl, ganz } from "./format.js";
import { holen, senden, strom } from "./api.js";
import { store, bus, ergebnisMelden } from "./store.js";
import { ModellAuswahl } from "./auswahl.js";
import { meldung, meldungLeeren } from "./meldungen.js";

export function dokumenteAufbauen(wurzel) {
  const auswahl = new ModellAuswahl({});
  const dateien = el("select", {});
  const parserA = el("select", {});
  const parserB = el("select", { disabled: true });
  const vergleichsschalter = el("input", { type: "checkbox" });
  const hochladen = el("input", { type: "file", accept: "application/pdf" });
  const frage = el("input", {
    type: "text",
    placeholder: "Zum Beispiel: Was kostet das Verlegen von Bodenfliesen?",
  });
  const meldungsfeld = el("div", {});
  const einlesestand = el("div", { class: "hinweiszeile" });
  const spalten = el("div", { class: "spalten-2" });
  const seiten = { a: seiteBauen("A"), b: seiteBauen("B") };
  let steuerung = null;
  let parserliste = [];

  const einlesen = el("button", { class: "knopf", type: "button", text: "PDF einlesen" });
  const fragen = el("button", { class: "knopf", type: "button", text: "Frage stellen" });
  const abbrechen = el("button", { class: "knopf leise", type: "button", text: "Abbrechen", disabled: true });
  einlesen.addEventListener("click", () => einlesenLauf());
  fragen.addEventListener("click", () => fragenLauf());
  abbrechen.addEventListener("click", () => steuerung?.abort());

  vergleichsschalter.addEventListener("change", () => {
    parserB.disabled = !vergleichsschalter.checked;
    spaltenZeichnen();
  });
  hochladen.addEventListener("change", () => hochladenLauf());

  function seiteBauen(buchstabe) {
    const kopf = el("h3", { text: "Antwort" });
    const antwort = el("div", { class: "antwort" });
    const promptfeld = el("pre", { class: "promptansicht", hidden: true });
    const promptschalter = el("button", {
      class: "knopf leise klein",
      type: "button",
      text: "Was das Modell gesehen hat",
      onclick: () => {
        promptfeld.hidden = !promptfeld.hidden;
      },
    });
    const quellen = el("div", { class: "quellen" });
    const tabelle = el("pre", { class: "tabellenvorschau", hidden: true });
    const zahlen = el("div", { class: "hinweiszeile" });
    return { kopf, antwort, promptfeld, promptschalter, quellen, tabelle, zahlen, buchstabe };
  }

  function spaltenZeichnen() {
    const vergleich = vergleichsschalter.checked;
    const bauen = (seite, titel) =>
      el("div", { class: "karte" }, [
        el("h3", { text: titel }),
        seite.zahlen,
        seite.antwort,
        el("div", { class: "zeile", style: "margin-top:.5rem" }, [seite.promptschalter]),
        seite.promptfeld,
        el("h3", { text: "Gefundene Abschnitte", style: "margin-top:1rem" }),
        seite.quellen,
        el("div", { class: "klein leise", text: "Erste erkannte Tabelle im geparsten Text:" }),
        seite.tabelle,
      ]);
    if (!vergleich) {
      spalten.replaceChildren(
        el("div", { class: "karte" }, [
          el("h3", { text: "Antwort" }),
          seiten.a.zahlen,
          seiten.a.antwort,
          el("div", { class: "zeile", style: "margin-top:.5rem" }, [seiten.a.promptschalter]),
          seiten.a.promptfeld,
        ]),
        el("div", { class: "karte" }, [
          el("h3", { text: "Gefundene Abschnitte" }),
          el("p", {
            class: "klein leise",
            text: "Nur diese Abschnitte hat das Modell gesehen. Mehr nicht.",
          }),
          seiten.a.quellen,
          el("div", { class: "klein leise", text: "Erste erkannte Tabelle im geparsten Text:" }),
          seiten.a.tabelle,
        ])
      );
    } else {
      spalten.replaceChildren(
        bauen(seiten.a, `Parser A: ${parserLabel(parserA.value)}`),
        bauen(seiten.b, `Parser B: ${parserLabel(parserB.value)}`)
      );
    }
  }

  function parserLabel(id) {
    return parserliste.find((p) => p.id === id)?.label ?? id;
  }

  async function dokumenteLaden() {
    try {
      const daten = await holen("/api/dokumente");
      parserliste = daten.parser;
      const vorher = dateien.value;
      dateien.replaceChildren(
        ...daten.dateien.map((d) =>
          el("option", {
            value: d.schluessel,
            text: `${d.name} (${zahl(d.groesse_kb, 0)} kB${d.quelle === "hochgeladen" ? ", hochgeladen" : ""})`,
          })
        )
      );
      if (!daten.dateien.length) {
        dateien.replaceChildren(
          el("option", { value: "", text: "Keine PDF in docs/ gefunden" })
        );
      }
      if (vorher) dateien.value = vorher;
      for (const feld of [parserA, parserB]) {
        const alt = feld.value;
        feld.replaceChildren(
          ...daten.parser.map((p) =>
            el("option", {
              value: p.id,
              disabled: !p.verfuegbar,
              text: p.verfuegbar ? p.label : `${p.label} — nicht installiert`,
            })
          )
        );
        const brauchbar = daten.parser.filter((p) => p.verfuegbar);
        if (alt && daten.parser.some((p) => p.id === alt && p.verfuegbar)) feld.value = alt;
        else if (brauchbar.length) feld.value = brauchbar[0].id;
      }
      if (parserliste.filter((p) => p.verfuegbar).length > 1) {
        const zweiter = parserliste.filter((p) => p.verfuegbar)[1];
        if (zweiter && parserB.value === parserA.value) parserB.value = zweiter.id;
      }
      if (daten.einbettung && !(daten.einbettung.online && daten.einbettung.vorhanden)) {
        meldung(meldungsfeld, {
          art: "fehler",
          nachricht:
            `Das Einbettungsmodell „${daten.einbettung.modell}“ ist nicht verfügbar. ` +
            "Ohne das kann in Dokumenten nicht gesucht werden.",
        });
      } else if (!daten.einbettung) {
        meldung(meldungsfeld, {
          art: "fehler",
          nachricht: "Für diese Station ist kein Einbettungsmodell konfiguriert.",
        });
      }
      spaltenZeichnen();
    } catch (fehler) {
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Die Dokumentliste konnte nicht geladen werden.",
        detail: String(fehler),
      });
    }
  }

  async function hochladenLauf() {
    const datei = hochladen.files?.[0];
    if (!datei) return;
    const formular = new FormData();
    formular.append("datei", datei);
    try {
      const antwort = await fetch("/api/dokumente/upload", { method: "POST", body: formular });
      const daten = await antwort.json();
      if (!antwort.ok) throw new Error(daten.detail || `Fehlercode ${antwort.status}`);
      await dokumenteLaden();
      dateien.value = daten.schluessel;
      meldung(meldungsfeld, { art: "gut", nachricht: daten.nachricht });
    } catch (fehler) {
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Die Datei konnte nicht hochgeladen werden.",
        detail: String(fehler),
      });
    } finally {
      hochladen.value = "";
    }
  }

  function indexSchluessel(parser) {
    return `${dateien.value}|${parser}`;
  }

  async function einlesenLauf() {
    if (!dateien.value) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Bitte wählen Sie eine PDF aus." });
      return;
    }
    const parser = [parserA.value];
    if (vergleichsschalter.checked && parserB.value) parser.push(parserB.value);
    einlesen.disabled = true;
    meldungLeeren(meldungsfeld);
    einlesestand.replaceChildren(el("span", { text: "Die PDF wird eingelesen und eingebettet …" }));
    const staende = [];
    try {
      for (const [i, p] of parser.entries()) {
        const kopf = await senden("/api/dokumente/index", { datei: dateien.value, parser: p });
        staende.push(kopf);
        const seite = i === 0 ? seiten.a : seiten.b;
        seite.tabelle.hidden = false;
        seite.tabelle.textContent = kopf.erste_tabelle || "(keine Tabelle erkannt)";
      }
      einlesestand.replaceChildren(
        ...staende.flatMap((k) => [
          el("span", {
            html:
              `<b>${parserLabel(k.parser)}</b>: ${ganz(k.seiten)} Seiten, ` +
              `${ganz(k.zeichen)} Zeichen, ${ganz(k.abschnitte)} Abschnitte ` +
              `(davon ${ganz(k.tabellen_abschnitte)} mit Tabelle), ` +
              `Parsen ${sekunden(k.parse_dauer_s)} s, Einbetten ${sekunden(k.einbetten_dauer_s)} s`,
          }),
        ])
      );
    } catch (fehler) {
      einlesestand.replaceChildren();
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Die PDF konnte nicht eingelesen werden.",
        detail: String(fehler),
      });
    } finally {
      einlesen.disabled = false;
    }
  }

  async function fragenLauf() {
    if (!frage.value.trim()) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Bitte geben Sie eine Frage ein." });
      return;
    }
    const { backend, modell } = auswahl.wert();
    if (!modell) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Für diese Laufzeit ist kein Modell verfügbar." });
      return;
    }
    const laeufe = [{ seite: seiten.a, parser: parserA.value }];
    if (vergleichsschalter.checked && parserB.value) {
      laeufe.push({ seite: seiten.b, parser: parserB.value });
    }
    meldungLeeren(meldungsfeld);
    fragen.disabled = true;
    abbrechen.disabled = false;
    steuerung = new AbortController();
    try {
      for (const { seite, parser } of laeufe) {
        seite.antwort.textContent = "";
        seite.antwort.classList.add("laeuft");
        seite.quellen.replaceChildren();
        seite.zahlen.replaceChildren();
        await strom(
          "/api/dokumente/frage",
          { index: indexSchluessel(parser), frage: frage.value, backend, modell },
          (ereignis) => {
            if (ereignis.art === "text") seite.antwort.append(ereignis.text);
            else if (ereignis.art === "quellen") quellenZeichnen(seite, ereignis.quellen);
            else if (ereignis.art === "prompt") {
              seite.promptfeld.textContent =
                `--- Systemanweisung ---\n${ereignis.system}\n\n--- Nutzeranweisung ---\n${ereignis.nutzer}`;
            } else if (ereignis.art === "messung") {
              seite.zahlen.replaceChildren(
                el("span", { html: `Antwort in <b>${sekunden(ereignis.messung.total_s)}</b> s` }),
                el("span", { html: `Schreibtempo <b>${zahl(ereignis.messung.decode_tps, 0)}</b> Token/s` }),
                el("span", { html: `Token rein <b>${ganz(ereignis.messung.prompt_tokens)}</b>` })
              );
              auswahl.warmMerken();
              ergebnisMelden(ereignis.ergebnis);
            } else if (ereignis.art === "fehler") {
              meldung(meldungsfeld, {
                art: "fehler",
                nachricht: ereignis.nachricht,
                detail: ereignis.detail,
              });
            }
          },
          steuerung.signal
        );
        seite.antwort.classList.remove("laeuft");
      }
    } catch (fehler) {
      for (const s of Object.values(seiten)) s.antwort.classList.remove("laeuft");
      if (fehler.name === "AbortError") {
        meldung(meldungsfeld, { nachricht: "Die Frage wurde abgebrochen." });
      } else {
        meldung(meldungsfeld, {
          art: "fehler",
          nachricht:
            "Die Frage konnte nicht beantwortet werden. Ist die PDF schon eingelesen?",
          detail: String(fehler),
        });
      }
    } finally {
      fragen.disabled = false;
      abbrechen.disabled = true;
      steuerung = null;
    }
  }

  function quellenZeichnen(seite, quellen) {
    seite.quellen.replaceChildren(
      ...quellen.map((q) =>
        el("div", { class: "quelle" }, [
          el("div", { class: "quelle-kopf" }, [
            el("span", { class: "quelle-nr", text: `Abschnitt ${q.nr}` }),
            el("span", {
              class: "quelle-seite",
              text: q.seite ? `Seite ${q.seite}` : "Seite unbekannt",
            }),
            q.ist_tabelle ? el("span", { class: "marke", text: "Tabelle" }) : null,
            el("span", { class: "quelle-wert", text: `Ähnlichkeit ${zahl(q.aehnlichkeit, 2)}` }),
          ].filter(Boolean)),
          el("div", { class: "quelle-text", text: q.text }),
        ])
      )
    );
  }

  bus.addEventListener("station", () => dokumenteLaden());
  dokumenteLaden();

  wurzel.replaceChildren(
    el("div", { class: "karte" }, [
      el("h2", { text: "Dokumente" }),
      el("p", {
        class: "leise",
        text:
          "Eine PDF wird gelesen, in Abschnitte zerlegt und eingebettet. " +
          "Das Modell sieht nur die vier Abschnitte, die am besten zur Frage " +
          "passen, und soll ausschließlich daraus antworten.",
      }),
      el("div", { class: "zeile" }, [
        el("label", { class: "feld" }, ["PDF aus docs/", dateien]),
        el("label", { class: "feld" }, ["Oder eigene PDF hochladen", hochladen]),
      ]),
      el("div", { class: "zeile" }, [
        el("label", { class: "feld" }, ["Parser", parserA]),
        el("label", { class: "nowrap" }, [vergleichsschalter, " Zwei Parser vergleichen"]),
        el("label", { class: "feld" }, ["Zweiter Parser", parserB]),
        einlesen,
      ]),
      einlesestand,
      meldungsfeld,
    ]),
    el("div", { class: "karte" }, [
      el("h2", { text: "Frage" }),
      auswahl.wurzel,
      el("label", { class: "feld", style: "margin-top:.6rem" }, ["Ihre Frage an das Dokument", frage]),
      el("div", { class: "zeile", style: "margin-top:.6rem" }, [fragen, abbrechen]),
    ]),
    spalten
  );
}
