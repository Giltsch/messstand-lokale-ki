// Reiter 2: Vergleich. Gleicher Prompt, nacheinander an A und B.

import { el, einsetzen, sekunden, tempo, faktor, zahl } from "./format.js";
import { strom } from "./api.js";
import { store, bus, backendVon, modellVon, ergebnisMelden } from "./store.js";
import { ModellAuswahl } from "./auswahl.js";
import { meldung, meldungLeeren } from "./meldungen.js";

// Was verglichen wird und in welche Richtung besser ist.
const MASSE = [
  { schluessel: "ttft_s", name: "Zeit bis zum ersten Wort", einheit: "s",
    formatieren: sekunden, kleinerBesser: true, satz: "antwortet {f} früher" },
  { schluessel: "prefill_tps", name: "Lesetempo", einheit: "Token/s",
    formatieren: tempo, kleinerBesser: false, satz: "liest {f} schneller" },
  { schluessel: "decode_tps", name: "Schreibtempo", einheit: "Token/s",
    formatieren: tempo, kleinerBesser: false, satz: "schreibt {f} schneller" },
  { schluessel: "total_s", name: "Gesamtzeit", einheit: "s",
    formatieren: sekunden, kleinerBesser: true, satz: "ist {f} schneller fertig" },
];

export function vergleichAufbauen(wurzel) {
  const vorlagen = el("select", { onchange: () => vorlageUebernehmen() });
  const auswahlA = new ModellAuswahl({ beschriftung: "A" });
  const auswahlB = new ModellAuswahl({ beschriftung: "B" });
  const prompt = el("textarea", { spellcheck: "false" });
  const meldungsfeld = el("div", {});
  const vorhersage = el("div", { class: "meldung", hidden: true });
  const balken = el("div", {});
  const seiten = { a: seiteBauen("A"), b: seiteBauen("B") };
  let steuerung = null;
  let messungen = { a: null, b: null };

  const starten = el("button", { class: "knopf", type: "button", text: "Vergleich starten" });
  const abbrechen = el("button", { class: "knopf leise", type: "button", text: "Abbrechen", disabled: true });
  starten.addEventListener("click", () => lauf());
  abbrechen.addEventListener("click", () => steuerung?.abort());

  function seiteBauen(buchstabe) {
    const kopf = el("h3", { text: `${buchstabe}: –` });
    const antwort = el("div", { class: "antwort" });
    const zahlen = el("div", { class: "hinweiszeile" });
    const karte = el("div", { class: "karte" }, [kopf, antwort, zahlen]);
    return { kopf, antwort, zahlen, karte, buchstabe };
  }

  function vorlagenZeichnen() {
    const liste = store.station?.vergleiche ?? [];
    vorlagen.replaceChildren(
      ...liste.map((v, i) => el("option", { value: String(i), text: v.name })),
      el("option", { value: "frei", text: "Freie Auswahl" })
    );
    if (liste.length) vorlageUebernehmen();
  }

  function vorlageUebernehmen() {
    const liste = store.station?.vergleiche ?? [];
    const v = liste[Number(vorlagen.value)];
    if (!v) return;
    auswahlA.setzen({ backend: v.a.backend, modell: v.a.modell });
    auswahlB.setzen({ backend: v.b.backend, modell: v.b.modell });
    vorhersageZeichnen();
  }

  // Zwei Erwartungen sind möglich, beide betreffen das Schreibtempo:
  //  1. Verschieden viele aktive Parameter: halb so viele, etwa doppeltes Tempo.
  //  2. Gleich viele aktive Parameter, aber andere Quantisierung: dann zählt
  //     die Dateigröße, denn je Token wird das ganze Modell einmal gelesen.
  function vorhersageZeichnen() {
    const wahlA = auswahlA.wert();
    const wahlB = auswahlB.wert();
    const a = modellVon(wahlA.backend, wahlA.modell);
    const b = modellVon(wahlB.backend, wahlB.modell);
    const schaetzung = schaetzen(a, b);
    if (!schaetzung) {
      vorhersage.hidden = true;
      vorhersage.dataset.erwartet = "";
      return;
    }
    vorhersage.hidden = false;
    vorhersage.replaceChildren(
      el("div", { html: `<b>Vorhersage:</b> ${schaetzung.satz}` }),
      el("div", { class: "klein leise", text: schaetzung.hinweis })
    );
    vorhersage.dataset.erwartet = String(schaetzung.faktor);
    vorhersage.dataset.schneller = schaetzung.schneller;
  }

  function schaetzen(a, b) {
    const aktivA = a?.parameter_aktiv_mrd;
    const aktivB = b?.parameter_aktiv_mrd;
    if (aktivA && aktivB && Math.abs(aktivA / aktivB - 1) >= 0.15) {
      const erwartet = aktivA / aktivB;
      const schneller = erwartet > 1 ? "B" : "A";
      const wert = erwartet > 1 ? erwartet : 1 / erwartet;
      return {
        faktor: wert,
        schneller,
        satz:
          `${schneller} rechnet mit ${zahl(Math.max(aktivA, aktivB) / Math.min(aktivA, aktivB), 1)}-mal ` +
          `weniger aktiven Parametern (${zahl(aktivA, 1)} gegen ${zahl(aktivB, 1)} Milliarden). ` +
          `Erwartung beim Schreibtempo: grob Faktor <b>${faktor(wert)}</b> für ${schneller}.`,
        hinweis:
          "Der gemessene Faktor steht nach dem Lauf daneben. Dass er darunter " +
          "liegt, ist normal: ein MoE-Modell hat Verwaltungsaufwand.",
      };
    }
    const groesseA = a?.groesse_gb;
    const groesseB = b?.groesse_gb;
    if (groesseA && groesseB && Math.abs(groesseA / groesseB - 1) >= 0.1) {
      const erwartet = groesseA / groesseB;
      const schneller = erwartet > 1 ? "B" : "A";
      const wert = erwartet > 1 ? erwartet : 1 / erwartet;
      return {
        faktor: wert,
        schneller,
        satz:
          `Gleich viele aktive Parameter, aber ${schneller} belegt ` +
          `${zahl(Math.max(groesseA, groesseB) / Math.min(groesseA, groesseB), 1)}-mal weniger Speicher ` +
          `(${zahl(groesseA, 1)} gegen ${zahl(groesseB, 1)} GB). Für jedes Token muss das ganze Modell ` +
          `einmal gelesen werden, Erwartung beim Schreibtempo also grob Faktor <b>${faktor(wert)}</b> für ${schneller}.`,
        hinweis:
          "Hier begrenzt die Speicherbandbreite, nicht die Rechenleistung. " +
          "Darum folgt das Tempo der Dateigröße und nicht der Parameterzahl.",
      };
    }
    return null;
  }

  function beschriftung(auswahl, buchstabe) {
    const { backend, modell } = auswahl.wert();
    const b = backendVon(backend);
    const m = modellVon(backend, modell);
    return `${buchstabe}: ${m?.label ?? modell} — ${b?.label ?? backend}`;
  }

  async function lauf() {
    const paare = [
      { kennung: "a", auswahl: auswahlA },
      { kennung: "b", auswahl: auswahlB },
    ];
    if (!prompt.value.trim()) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Bitte geben Sie einen Prompt ein." });
      return;
    }
    meldungLeeren(meldungsfeld);
    messungen = { a: null, b: null };
    balkenZeichnen();
    for (const { kennung, auswahl } of paare) {
      const seite = seiten[kennung];
      seite.kopf.textContent = beschriftung(auswahl, seite.buchstabe);
      seite.antwort.textContent = "";
      seite.zahlen.replaceChildren();
    }
    starten.disabled = true;
    abbrechen.disabled = false;
    steuerung = new AbortController();

    try {
      // Nacheinander, nicht parallel: sonst verfälschen sich die Werte.
      for (const { kennung, auswahl } of paare) {
        const seite = seiten[kennung];
        const { backend, modell } = auswahl.wert();
        if (!modell) {
          meldung(meldungsfeld, {
            art: "fehler",
            nachricht: `Seite ${seite.buchstabe}: kein Modell verfügbar.`,
          });
          continue;
        }
        seite.antwort.classList.add("laeuft");
        seite.zahlen.replaceChildren(el("span", { text: "läuft …" }));
        await strom(
          "/api/chat",
          {
            backend,
            modell,
            prompt: prompt.value,
            reiter: "Vergleich",
            notiz: `${vorlagen.options[vorlagen.selectedIndex]?.text ?? "Vergleich"}, Seite ${seite.buchstabe}`,
            thinking: false,
          },
          (ereignis) => {
            if (ereignis.art === "text") seite.antwort.append(ereignis.text);
            else if (ereignis.art === "messung") {
              messungen[kennung] = ereignis.messung;
              zahlenZeichnen(seite, ereignis.messung);
              ergebnisMelden(ereignis.ergebnis);
              auswahl.warmMerken();
              balkenZeichnen();
            } else if (ereignis.art === "fehler") {
              seite.zahlen.replaceChildren();
              meldung(meldungsfeld, {
                art: "fehler",
                nachricht: `Seite ${seite.buchstabe}: ${ereignis.nachricht}`,
                detail: ereignis.detail,
              });
            }
          },
          steuerung.signal
        );
        seite.antwort.classList.remove("laeuft");
      }
      kaltHinweis();
    } catch (fehler) {
      for (const seite of Object.values(seiten)) seite.antwort.classList.remove("laeuft");
      meldung(meldungsfeld, {
        art: fehler.name === "AbortError" ? "" : "fehler",
        nachricht:
          fehler.name === "AbortError"
            ? "Der Vergleich wurde abgebrochen."
            : "Die Verbindung zum Messstand ist abgebrochen.",
        detail: fehler.name === "AbortError" ? "" : String(fehler),
      });
    } finally {
      starten.disabled = false;
      abbrechen.disabled = true;
      steuerung = null;
    }
  }

  function zahlenZeichnen(seite, messung) {
    const teile = MASSE.map((m) =>
      el("span", {
        html: `${m.name}: <b>${m.formatieren(messung[m.schluessel])}</b> ${m.einheit}`,
      })
    );
    teile.push(
      el("span", {
        class: `marke ${messung.kalt ? "kalt" : "warm"}`,
        text: messung.kalt ? "kalt gestartet" : "warm",
      })
    );
    if (messung.geschaetzt) {
      teile.push(el("span", { class: "marke geschaetzt", text: "geschätzt" }));
    }
    seite.zahlen.replaceChildren(...teile);
  }

  // Ein kalt gestarteter Lauf verzerrt den Vergleich. Darauf hinweisen.
  function kaltHinweis() {
    const kalte = Object.entries(messungen)
      .filter(([, m]) => m?.kalt)
      .map(([k]) => k.toUpperCase());
    if (!kalte.length) return;
    meldung(meldungsfeld, {
      nachricht:
        `Seite ${kalte.join(" und ")} wurde kalt gestartet: die Ladezeit steckt in ` +
        "der Gesamtzeit. Für einen fairen Vergleich beide Modelle vorladen und " +
        "den Vergleich wiederholen.",
    });
  }

  function balkenZeichnen() {
    const { a, b } = messungen;
    const reihen = MASSE.map((m) => {
      const wertA = a?.[m.schluessel] ?? null;
      const wertB = b?.[m.schluessel] ?? null;
      const groesste = Math.max(wertA ?? 0, wertB ?? 0) || 1;
      const breite = (w) => (w === null ? 0 : Math.max(2, (w / groesste) * 100));
      let satz = "";
      if ((wertA === null) !== (wertB === null) && (a || b)) {
        const fehlt = wertA === null ? "A" : "B";
        satz = `Kein Vergleich möglich: Seite ${fehlt} liefert diesen Wert nicht.`;
      }
      if (wertA && wertB) {
        const besserB = m.kleinerBesser ? wertB < wertA : wertB > wertA;
        const f = Math.max(wertA, wertB) / Math.min(wertA, wertB);
        satz = `${besserB ? "B" : "A"} ${m.satz.replace("{f}", faktor(f))}`;
        if (m.schluessel === "decode_tps" && !vorhersage.hidden && vorhersage.dataset.erwartet) {
          const erwartet = Number(vorhersage.dataset.erwartet);
          satz += ` — vorhergesagt war grob ${faktor(erwartet)} für ${vorhersage.dataset.schneller}`;
        }
      }
      return el("div", { class: "balkenreihe" }, [
        el("div", { class: "balken-name", text: `${m.name} (${m.einheit})` }),
        el("div", { class: "balken-paar" }, [
          balkenZeile("A", wertA, breite(wertA), m, "a"),
          balkenZeile("B", wertB, breite(wertB), m, "b"),
        ]),
        el("div", { class: "balken-satz", text: satz }),
      ]);
    });
    balken.replaceChildren(...reihen);
  }

  function balkenZeile(buchstabe, wert, breite, mass, klasse) {
    return el("div", { class: "balken-zeile" }, [
      el("span", { class: "balken-marke", text: buchstabe }),
      el("div", { class: "balken-bahn" }, [
        el("div", { class: `balken-fuellung ${klasse}`, style: `width:${breite}%` }),
      ]),
      el("span", { class: "balken-wert", text: mass.formatieren(wert) }),
    ]);
  }

  function vorlageEinsetzen(welcher) {
    const karte = store.station?.aufgabenkarte?.[welcher];
    if (!karte) return;
    prompt.value = einsetzen(karte.prompt, { text: store.station.beispieltext || "" });
  }

  function stationUebernehmen() {
    if (!store.station) return;
    vorlagenZeichnen();
    if (!prompt.value) vorlageEinsetzen("teil1");
  }

  bus.addEventListener("station", stationUebernehmen);
  auswahlA.aufAenderung = vorhersageZeichnen;
  auswahlB.aufAenderung = vorhersageZeichnen;
  stationUebernehmen();
  balkenZeichnen();

  wurzel.replaceChildren(
    el("div", { class: "karte" }, [
      el("h2", { text: "Vergleich" }),
      el("p", {
        class: "leise",
        text:
          "Gleicher Prompt, gleiche Einstellungen, nacheinander an A und B. " +
          "Nacheinander, weil parallele Läufe sich gegenseitig verlangsamen würden.",
      }),
      el("div", { class: "zeile" }, [
        el("label", { class: "feld" }, ["Vorbereiteter Vergleich", vorlagen]),
      ]),
      auswahlA.wurzel,
      auswahlB.wurzel,
      el("label", { class: "feld", style: "margin-top:.8rem" }, ["Prompt für beide Seiten", prompt]),
      el("div", { class: "zeile", style: "margin-top:.6rem" }, [
        starten,
        abbrechen,
        el("button", {
          class: "knopf leise klein",
          type: "button",
          text: "Teil 1 einsetzen",
          onclick: () => vorlageEinsetzen("teil1"),
        }),
        el("button", {
          class: "knopf leise klein",
          type: "button",
          text: "Teil 2 einsetzen",
          onclick: () => vorlageEinsetzen("teil2"),
        }),
      ]),
      vorhersage,
      meldungsfeld,
    ]),
    el("div", { class: "spalten-2" }, [seiten.a.karte, seiten.b.karte]),
    el("div", { class: "karte" }, [el("h2", { text: "Messwerte im Vergleich" }), balken])
  );
}
