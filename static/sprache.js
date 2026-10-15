// Reiter 7: Sprache. Besprechung mitschreiben (lokal, Whisper), danach
// Notizen, Aufgaben und Terminvorschlaege von einem Sprachmodell.

import { el, zahl, ganz, sekunden } from "./format.js";
import { holen, senden, strom } from "./api.js";
import { ergebnisMelden, backends } from "./store.js";
import { ModellAuswahl } from "./auswahl.js";
import { meldung, meldungLeeren } from "./meldungen.js";

// Stuecke an Sprechpausen schneiden: frueh genug fuer „fast live“, lang
// genug, dass Whisper Zusammenhang hat.
const STUECK_MIN_S = 4;
const STUECK_MAX_S = 14;
const PAUSE_MS = 450;
const PAUSE_PEGEL = 0.018;

const VORLESETEXT = `Anna: Gut, dann fangen wir an. Thema ist die Wartung der Abfüllanlage bei der Firma Berger in Ansbach.
Tom: Ja, der Kunde hat gestern angerufen. Die Anlage verliert Druck, vermutlich die Dichtung am Ventilblock.
Anna: Wer kann hinfahren?
Tom: Ich kann am Dienstag nächster Woche, so gegen zehn Uhr. Das dauert etwa zwei Stunden.
Anna: Gut. Bitte bestell vorher die Ersatzdichtung, Teilenummer 4711, bis Freitag.
Tom: Mache ich. Und das Angebot für den Wartungsvertrag?
Anna: Das schreibe ich bis Ende des Monats. Lass uns danach noch einen Termin mit Herrn Berger machen, am 3. November um 14 Uhr, eine Stunde, bei uns im Haus.
Tom: Passt. Dann halten wir fest: Dichtung bestellen bis Freitag, Montage Dienstag zehn Uhr, Angebot bis Monatsende.`;

export function spracheAufbauen(wurzel) {
  const statuszeile = el("div", { class: "hinweiszeile" });
  const mikroWahl = el("select", { onchange: () => mikroOeffnen() });
  const pegel = el("div", { class: "sp-pegel" }, [el("div", { class: "sp-pegel-fuellung" })]);
  const startKnopf = el("button", { class: "knopf", type: "button", text: "Aufnahme starten" });
  const stopKnopf = el("button", { class: "knopf leise", type: "button", text: "Stoppen", disabled: true });
  const testKnopf = el("button", {
    class: "knopf leise klein",
    type: "button",
    text: "Mikrofon prüfen",
    onclick: async () => {
      if (await mikroOeffnen()) {
        meldung(meldungsfeld, {
          nachricht: "Mikrofon ist offen. Sprechen Sie: Der Balken muss grün ausschlagen. Bleibt er grau, kommt kein Ton an (Kabel ohne Mikrofonleitung?).",
        });
      }
    },
  });
  const leerenKnopf = el("button", { class: "knopf leise klein", type: "button", text: "Neu anfangen" });
  const dateiwahl = el("input", { type: "file", accept: "audio/*,video/webm,.m4a,.mp3,.wav,.ogg,.webm" });
  const uhr = el("span", { class: "sp-uhr", text: "0:00" });
  const meldungsfeld = el("div", {});
  const mitschrift = el("textarea", {
    class: "sp-mitschrift",
    rows: 12,
    placeholder: "Hier erscheint die Mitschrift, Stück für Stück, während gesprochen wird.",
  });
  const werte = {
    audio: kachelwert(),
    rechnen: kachelwert(),
    echtzeit: kachelwert(),
    woerter: kachelwert(),
  };
  const auswertung = auswertungBauen(() => mitschrift.value);
  const zuordnung = new Sprecherzuordnung();
  const sprecherfeld = el("div", { class: "zeile sp-sprecher" });

  let strom_ = null; // MediaStream
  let analyser = null;
  let rekorder = null;
  let laeuft = false;
  let startzeit = 0;
  let stueckStart = 0;
  let leiseSeit = 0;
  let lautestes = 0; // hoechster Pegel im laufenden Stueck
  let kette = Promise.resolve(); // Stuecke der Reihe nach erkennen
  let summe = { audio: 0, rechnen: 0 };
  let uhrTakt = null;
  let pegelLaeuft = false;

  startKnopf.addEventListener("click", () => aufnahmeStarten());
  stopKnopf.addEventListener("click", () => aufnahmeStoppen());
  leerenKnopf.addEventListener("click", () => {
    mitschrift.value = "";
    zuordnung.leeren();
    sprecherZeichnen();
    summe = { audio: 0, rechnen: 0 };
    zahlenZeichnen();
    uhr.textContent = "0:00";
    meldungLeeren(meldungsfeld);
  });
  dateiwahl.addEventListener("change", () => dateiErkennen());
  mitschrift.addEventListener("input", () => zahlenZeichnen());

  wurzel.append(
    el("div", { class: "karte" }, [
      el("h2", { text: "Besprechung mitschreiben" }),
      el("p", {
        class: "leise",
        text:
          "Das Mikrofon hängt an diesem Gerät, die Spracherkennung läuft auf diesem Gerät. " +
          "Kein Ton und kein Wort verlässt den Raum.",
      }),
      statuszeile,
      el("div", { class: "zeile" }, [
        el("label", { class: "feld" }, ["Mikrofon", mikroWahl]),
        el("div", { class: "feld sp-pegelfeld" }, [el("span", { text: "Pegel" }), pegel]),
        el("div", {}, [testKnopf]),
      ]),
      el("div", { class: "zeile", style: "margin:.7rem 0" }, [startKnopf, stopKnopf, uhr, leerenKnopf]),
      el("div", { class: "kacheln" }, [
        kachel("Aufnahme", werte.audio, "s"),
        kachel("Rechenzeit Erkennung", werte.rechnen, "s"),
        kachel("Schneller als Echtzeit", werte.echtzeit, "x"),
        kachel("Wörter", werte.woerter, ""),
      ]),
      meldungsfeld,
      sprecherfeld,
      el("label", { class: "feld" }, ["Mitschrift (nach dem Stoppen korrigierbar)", mitschrift]),
      el("div", { class: "zeile", style: "margin-top:.6rem" }, [
        el("label", { class: "feld" }, ["Oder eine Audiodatei einlesen", dateiwahl]),
      ]),
      el("details", { class: "sp-vorlesen" }, [
        el("summary", { text: "Text zum Vorlesen (Rollenspiel für zwei Personen)" }),
        el("pre", { class: "promptansicht", text: VORLESETEXT }),
      ]),
    ]),
    auswertung.karte
  );

  // ---------- Status und Mikrofon ----------

  async function statusLaden() {
    try {
      const s = await holen("/api/sprache/status");
      statuszeile.replaceChildren(
        el("span", {
          class: `punkt ${s.bereit ? "online" : "offline"}`,
          text: s.bereit ? `Spracherkennung: ${s.label}` : "Spracherkennung nicht bereit",
        }),
        el("span", {
          class: `punkt ${s.sprecher ? "online" : "offline"}`,
          text: s.sprecher ? "Sprecher unterscheiden: NVIDIA TitaNet" : "Sprecher unterscheiden: aus",
        }),
        s.bereit ? el("span", { text: "läuft auf diesem Gerät" }) : el("span", { text: "Starten mit: spark/spark-modus.sh sprache" })
      );
    } catch (fehler) {
      statuszeile.replaceChildren(el("span", { class: "punkt offline", text: String(fehler) }));
    }
  }

  async function mikrosAuflisten() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Dieser Browser gibt kein Mikrofon frei. Die Seite muss über 127.0.0.1 oder localhost geöffnet sein.",
      });
      return;
    }
    // „Monitor of …“ ist kein Mikrofon, sondern der Ton, der gerade abgespielt wird.
    const geraete = (await navigator.mediaDevices.enumerateDevices()).filter(
      (g) => g.kind === "audioinput" && !/^(monitor|überwachung)/i.test(g.label)
    );
    const vorher = mikroWahl.value;
    mikroWahl.replaceChildren(
      ...(geraete.length
        ? geraete.map((g, i) => el("option", { value: g.deviceId, text: g.label || `Mikrofon ${i + 1}` }))
        : [el("option", { value: "", text: "Kein Mikrofon gefunden (USB-Headset anstecken)" })])
    );
    if (vorher) mikroWahl.value = vorher;
  }

  async function mikroOeffnen() {
    strom_?.getTracks().forEach((t) => t.stop());
    try {
      strom_ = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: mikroWahl.value ? { exact: mikroWahl.value } : undefined,
          channelCount: 1,
          // Die Telefon-Filter des Browsers verfaelschen Sprache fuer Whisper eher,
          // als dass sie helfen. Whisper kommt mit Raumgeraeusch gut zurecht.
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: true,
        },
      });
    } catch (fehler) {
      meldung(meldungsfeld, {
        art: "fehler",
        nachricht: "Das Mikrofon lässt sich nicht öffnen. Ist eines angesteckt und im Browser erlaubt?",
        detail: String(fehler),
      });
      return false;
    }
    await mikrosAuflisten(); // erst nach der Freigabe kennt der Browser die Namen
    const kontext = new AudioContext();
    // Ohne resume() bleibt der Kontext im Browser oft angehalten, der Pegel steht dann bei null.
    await kontext.resume().catch(() => {});
    analyser = kontext.createAnalyser();
    analyser.fftSize = 1024;
    kontext.createMediaStreamSource(strom_).connect(analyser);
    if (!pegelLaeuft) {
      pegelLaeuft = true;
      pegelZeichnen();
    }
    return true;
  }

  function aktuellerPegel() {
    if (!analyser) return 0;
    const puffer = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(puffer);
    let s = 0;
    for (const x of puffer) s += x * x;
    return Math.sqrt(s / puffer.length);
  }

  function pegelZeichnen() {
    const p = aktuellerPegel();
    pegel.firstChild.style.width = `${Math.min(100, p * 400)}%`;
    pegel.classList.toggle("laut", p > PAUSE_PEGEL);
    if (laeuft) pausenSchnitt(p);
    requestAnimationFrame(pegelZeichnen);
  }

  // ---------- Aufnahme in Stuecken ----------

  async function aufnahmeStarten() {
    if (!strom_ && !(await mikroOeffnen())) return;
    meldungLeeren(meldungsfeld);
    laeuft = true;
    startzeit = performance.now();
    startKnopf.disabled = true;
    stopKnopf.disabled = false;
    mitschrift.readOnly = true;
    auswertung.sperren(true);
    stueckBeginnen();
    uhrTakt = setInterval(() => {
      uhr.textContent = zeitText((performance.now() - startzeit) / 1000);
    }, 250);
  }

  function aufnahmeStoppen() {
    laeuft = false;
    clearInterval(uhrTakt);
    rekorder?.state === "recording" && rekorder.stop();
    startKnopf.disabled = false;
    stopKnopf.disabled = true;
    kette.then(() => {
      mitschrift.readOnly = false;
      auswertung.sperren(false);
    });
  }

  function stueckBeginnen() {
    const teile = [];
    const versatz = (performance.now() - startzeit) / 1000;
    rekorder = new MediaRecorder(strom_, { mimeType: "audio/webm;codecs=opus" });
    rekorder.addEventListener("dataavailable", (e) => e.data.size && teile.push(e.data));
    rekorder.addEventListener("stop", () => {
      const blob = new Blob(teile, { type: "audio/webm" });
      // Stille nicht schicken: Whisper erfindet dann gern „Vielen Dank.“
      if (lautestes > PAUSE_PEGEL * 1.5) kette = kette.then(() => stueckErkennen(blob, versatz));
      if (laeuft) stueckBeginnen();
    });
    rekorder.start();
    stueckStart = performance.now();
    leiseSeit = 0;
    lautestes = 0;
  }

  function pausenSchnitt(p) {
    if (!rekorder || rekorder.state !== "recording") return;
    const jetzt = performance.now();
    const dauer = (jetzt - stueckStart) / 1000;
    lautestes = Math.max(lautestes, p);
    if (p < PAUSE_PEGEL) leiseSeit ||= jetzt;
    else leiseSeit = 0;
    const pause = leiseSeit && jetzt - leiseSeit > PAUSE_MS;
    if ((dauer > STUECK_MIN_S && pause) || dauer > STUECK_MAX_S) rekorder.stop();
  }

  async function stueckErkennen(blob, versatz) {
    const formular = new FormData();
    formular.append("datei", blob, "stueck.webm");
    formular.append("vorher", nurText(mitschrift.value).slice(-200));
    try {
      const antwort = await fetch("/api/sprache/erkennen", { method: "POST", body: formular });
      const daten = await antwort.json();
      if (!antwort.ok) throw new Error(daten.detail || `Fehlercode ${antwort.status}`);
      summe.audio += daten.audio_s;
      summe.rechnen += daten.rechen_s;
      if (daten.text && !nurRauschen(daten.text)) zeilenAnhaengen(daten.abschnitte, versatz);
      zahlenZeichnen();
    } catch (fehler) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Ein Stück konnte nicht erkannt werden.", detail: String(fehler) });
    }
  }

  async function dateiErkennen() {
    const datei = dateiwahl.files?.[0];
    if (!datei) return;
    meldung(meldungsfeld, { nachricht: `„${datei.name}“ wird erkannt …` });
    auswertung.sperren(true);
    const formular = new FormData();
    formular.append("datei", datei);
    try {
      const antwort = await fetch("/api/sprache/erkennen", { method: "POST", body: formular });
      const daten = await antwort.json();
      if (!antwort.ok) throw new Error(daten.detail || `Fehlercode ${antwort.status}`);
      summe = { audio: daten.audio_s, rechnen: daten.rechen_s };
      mitschrift.value = "";
      zuordnung.leeren();
      sprecherZeichnen();
      zeilenAnhaengen(daten.abschnitte, 0);
      zahlenZeichnen();
      meldung(meldungsfeld, {
        art: "gut",
        nachricht: `${sekunden(daten.audio_s)} s Audio in ${sekunden(daten.rechen_s)} s erkannt.`,
      });
    } catch (fehler) {
      meldung(meldungsfeld, { art: "fehler", nachricht: "Die Datei konnte nicht erkannt werden.", detail: String(fehler) });
    } finally {
      dateiwahl.value = "";
      mitschrift.readOnly = false;
      auswertung.sperren(false);
    }
  }

  function zahlenZeichnen() {
    werte.audio.textContent = summe.audio ? zahl(summe.audio, 0) : "–";
    werte.rechnen.textContent = summe.rechnen ? sekunden(summe.rechnen) : "–";
    werte.echtzeit.textContent = summe.rechnen ? zahl(summe.audio / summe.rechnen, 0) : "–";
    werte.woerter.textContent = ganz(nurText(mitschrift.value).split(/\s+/).filter(Boolean).length);
  }

  // Abschnitte einem Sprecher zuordnen; aufeinanderfolgende Abschnitte
  // derselben Stimme werden eine Zeile.
  function zeilenAnhaengen(abschnitte, versatz) {
    const zeilen = [];
    for (const a of abschnitte || []) {
      if (!a.text || nurRauschen(a.text)) continue;
      const nr = zuordnung.zuordnen(a.stimme, (a.ende || 0) - (a.start || 0));
      const letzte = zeilen.at(-1);
      if (letzte && letzte.nr === nr) letzte.text += " " + a.text;
      else zeilen.push({ nr, zeit: versatz + (a.start || 0), text: a.text });
    }
    for (const z of zeilen) {
      const wer = z.nr === null ? "" : `${zuordnung.name(z.nr)}: `;
      mitschrift.value += (mitschrift.value ? "\n" : "") + `[${zeitText(z.zeit)}] ${wer}${z.text}`;
    }
    mitschrift.scrollTop = mitschrift.scrollHeight;
    sprecherZeichnen();
  }

  // Namensfelder: „Sprecher 1“ in „Anna“ umbenennen, auch rückwirkend im Text.
  function sprecherZeichnen() {
    const n = zuordnung.anzahl();
    if (!n) {
      sprecherfeld.replaceChildren();
      return;
    }
    sprecherfeld.replaceChildren(
      el("span", { class: "klein leise", text: "Erkannte Stimmen, Namen änderbar:" }),
      ...Array.from({ length: n }, (_, i) => {
        const feld = el("input", { type: "text", value: zuordnung.name(i), class: `sp-name sp-farbe-${i % 6}` });
        feld.addEventListener("change", () => {
          const alt = zuordnung.name(i);
          const neu = feld.value.trim().replace(/[:\n]/g, "") || alt;
          zuordnung.umbenennen(i, neu);
          const geschuetzt = alt.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&");
          const muster = new RegExp("(\\] )" + geschuetzt + ": ", "g");
          mitschrift.value = mitschrift.value.replace(muster, `$1${neu}: `);
          feld.value = neu;
        });
        return feld;
      })
    );
  }

  statusLaden();
  mikrosAuflisten().catch(() => {});
  return {};
}

// Mitschrift ohne Zeitmarken und Sprechernamen (fuer Wortzahl und Whisper-Prompt).
function nurText(mitschrift) {
  return mitschrift.replace(/^\[\d+:\d\d\] (?:[^:\n]{1,40}: )?/gm, "");
}

// Stimmabdruecke (normierte Vektoren) fortlaufend Sprechern zuordnen: aehnlich
// genug zu einer bekannten Stimme → dieselbe, sonst eine neue. Nur Abschnitte
// ab MIN_NEU_S duerfen eine neue Stimme anlegen oder eine bekannte schaerfen;
// kurze Einwuerfe („Ja.“) haben zu unsichere Abdruecke und gehen an die
// aehnlichste bekannte Stimme. Werte an einer echten Gruppenaufnahme eingestellt.
const AEHNLICH = 0.4;
const KURZ_AEHNLICH = 0.25;
const MIN_NEU_S = 2.5;
const HOECHSTENS = 8;

class Sprecherzuordnung {
  constructor() {
    this.leeren();
  }

  leeren() {
    this.zentren = [];
    this.namen = [];
    this.letzter = null;
  }

  anzahl() {
    return this.zentren.length;
  }

  name(nr) {
    return this.namen[nr] || `Sprecher ${nr + 1}`;
  }

  umbenennen(nr, name) {
    this.namen[nr] = name;
  }

  zuordnen(stimme, dauer = MIN_NEU_S) {
    if (!stimme) return this.letzter;
    let beste = -1;
    let wert = -2;
    this.zentren.forEach((z, i) => {
      const w = kosinus(z, stimme);
      if (w > wert) [beste, wert] = [i, w];
    });
    if (dauer < MIN_NEU_S && this.zentren.length) {
      this.letzter = wert >= KURZ_AEHNLICH ? beste : this.letzter ?? beste;
      return this.letzter;
    }
    if (beste < 0 || (wert < AEHNLICH && this.zentren.length < HOECHSTENS)) {
      this.zentren.push([...stimme]);
      beste = this.zentren.length - 1;
    } else {
      const z = this.zentren[beste];
      for (let k = 0; k < z.length; k++) z[k] += stimme[k];
    }
    this.letzter = beste;
    return beste;
  }
}

function kosinus(a, b) {
  let ab = 0;
  let aa = 0;
  let bb = 0;
  for (let k = 0; k < a.length; k++) {
    ab += a[k] * b[k];
    aa += a[k] * a[k];
    bb += b[k] * b[k];
  }
  return ab / Math.sqrt(aa * bb || 1);
}

// Whisper erfindet bei Stille gern Abspanntexte. Die fliegen raus.
function nurRauschen(text) {
  const t = text.toLowerCase().replace(/[^a-zäöüß ]/g, "").trim();
  return (
    !t ||
    /^(untertitel|untertitelung|copyright|vielen dank fürs zuschauen|danke fürs zuschauen|tschüss|amara)/.test(t)
  );
}

// ---------- Auswertung durch ein Sprachmodell ----------

function auswertungBauen(mitschriftHolen) {
  const auswahl = new ModellAuswahl({});
  const los = el("button", { class: "knopf", type: "button", text: "Notizen, Aufgaben und Termine" });
  const abbrechen = el("button", { class: "knopf leise", type: "button", text: "Abbrechen", disabled: true });
  const roh = el("div", { class: "antwort" });
  const denken = el("div", { class: "denken" });
  const notizen = el("div", { class: "ocr-dokument sp-notizen", hidden: true });
  const termine = el("div", { class: "sp-termine" });
  const zahlen = el("div", { class: "hinweiszeile" });
  const promptfeld = el("pre", { class: "promptansicht", hidden: true });
  const download = el("div", { class: "zeile" });
  let steuerung = null;
  let gesperrt = false;

  // GPT-OSS 120B vorwaehlen, wenn es da ist: das ist die Demo dafuer.
  const gross = backends().flatMap((b) => b.modelle.map((m) => ({ b: b.id, m })))
    .find(({ m }) => m.id === "gpt-oss:120b" && m.vorhanden);
  if (gross) auswahl.setzen({ backend: gross.b, modell: gross.m.id });

  const karte = el("div", { class: "karte" }, [
    el("h2", { text: "Auswerten: Notizen, Aufgaben, Termine" }),
    el("p", {
      class: "leise",
      text:
        "Ein Sprachmodell auf diesem Gerät liest die Mitschrift und schlägt vor. Termine werden nicht eingetragen, " +
        "sondern als Datei angeboten: Ein Mensch entscheidet.",
    }),
    auswahl.wurzel,
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
    roh,
    notizen,
    termine,
    download,
    promptfeld,
  ]);

  los.addEventListener("click", async () => {
    const text = mitschriftHolen().trim();
    if (!text) {
      roh.textContent = "Es gibt noch keine Mitschrift.";
      return;
    }
    const { backend, modell } = auswahl.wert();
    const prompt = promptBauen(text);
    promptfeld.textContent = prompt;
    roh.hidden = false;
    roh.textContent = "";
    roh.classList.add("laeuft");
    notizen.hidden = true;
    termine.replaceChildren();
    download.replaceChildren();
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
          system: SYSTEM,
          reiter: "Sprache",
          notiz: `Mitschrift, ${text.split(/\s+/).length} Wörter`,
          max_tokens: 2000,
        },
        (e) => {
          if (e.art === "denken") {
            // Grosse Modelle denken erst nach; das soll man auf dem Beamer sehen.
            if (!denken.parentNode) roh.replaceChildren(el("div", { class: "klein leise", text: "Das Modell denkt nach …" }), denken);
            denken.textContent += e.text;
            roh.scrollTop = roh.scrollHeight;
          } else if (e.art === "text") {
            if (denken.parentNode) {
              roh.replaceChildren();
              denken.textContent = "";
            }
            roh.append(e.text);
            roh.scrollTop = roh.scrollHeight;
          } else if (e.art === "fehler") roh.textContent += `\n[${e.nachricht}]`;
          else if (e.art === "messung") {
            const m = e.messung;
            zahlen.replaceChildren(
              el("span", { text: `Erstes Wort nach ${sekunden(m.ttft_s)} s` }),
              el("span", { text: `Schreiben ${ganz(Math.round(m.decode_tps || 0))} Token/s` }),
              el("span", { text: `Gesamt ${sekunden(m.total_s)} s` })
            );
            ergebnisMelden(e.ergebnis);
            auswahl.warmMerken();
          }
        },
        steuerung.signal
      );
      denken.textContent = "";
      await ergebnisZeigen(roh.textContent);
    } catch (fehler) {
      if (fehler.name !== "AbortError") roh.textContent += `\n[${fehler}]`;
    } finally {
      roh.classList.remove("laeuft");
      los.disabled = gesperrt;
      abbrechen.disabled = true;
    }
  });
  abbrechen.addEventListener("click", () => steuerung?.abort());

  async function ergebnisZeigen(antwort) {
    const { text, daten } = jsonAbtrennen(antwort);
    try {
      const { html } = await senden("/api/markdown", { text });
      notizen.innerHTML = html; // serverseitig bereinigt
      notizen.hidden = false;
      roh.hidden = true;
    } catch {
      /* dann bleibt der Rohtext stehen */
    }
    const liste = (daten?.termine || []).filter((t) => /^\d{4}-\d{2}-\d{2}$/.test(t.datum || ""));
    if (liste.length) {
      termine.replaceChildren(
        el("h3", { text: "Terminvorschläge" }),
        ...liste.map((t) =>
          el("div", { class: "sp-termin" }, [
            el("div", {}, [
              el("b", { text: t.titel || "Termin" }),
              el("div", { class: "klein leise", text: terminText(t) }),
            ]),
            el("button", {
              class: "knopf leise klein",
              type: "button",
              text: "In den Kalender (.ics)",
              onclick: () => herunterladen(ics([t]), `${dateiname(t.titel)}.ics`, "text/calendar"),
            }),
          ])
        )
      );
    }
    download.replaceChildren(
      ...[el("button", {
        class: "knopf leise klein",
        type: "button",
        text: "Protokoll speichern (.md)",
        onclick: () => herunterladen(`${text}\n\n## Mitschrift\n\n${mitschriftHolen()}\n`, "protokoll.md", "text/markdown"),
      }),
      liste.length > 1
        ? el("button", {
            class: "knopf leise klein",
            type: "button",
            text: "Alle Termine (.ics)",
            onclick: () => herunterladen(ics(liste), "termine.ics", "text/calendar"),
          })
        : null].filter(Boolean)
    );
  }

  return {
    karte,
    sperren(an) {
      gesperrt = an;
      los.disabled = an;
    },
  };
}

const SYSTEM =
  "Sie schreiben Besprechungsprotokolle auf Deutsch. Sie verwenden nur, was in der Mitschrift steht, " +
  "und erfinden keine Namen, Daten oder Zahlen. Unklare Angaben kennzeichnen Sie mit (unklar).";

function promptBauen(text) {
  const heute = new Date();
  const datum = heute.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const iso = isoTag(heute);
  // Kleine Modelle rechnen Wochentage gern falsch um. Ein Kalender hilft.
  const kalender = Array.from({ length: 21 }, (_, i) => {
    const d = new Date(heute);
    d.setDate(d.getDate() + i);
    return `${d.toLocaleDateString("de-DE", { weekday: "short" })} ${isoTag(d)}`;
  }).join(", ");
  return `Heute ist ${datum} (${iso}).
Kalender der nächsten drei Wochen: ${kalender}.
Unten steht die automatische Mitschrift einer Besprechung, sie kann Hörfehler enthalten.

Schreibe auf Deutsch, in Markdown:
## Zusammenfassung
(2 bis 4 Sätze)
## Entscheidungen
(Stichpunkte)
## Aufgaben
(Tabelle: Wer | Was | Bis wann)
## Termine
(Stichpunkte mit Datum und Uhrzeit; relative Angaben wie „Dienstag nächster Woche“ in ein Datum umrechnen)
## Offene Fragen

Hänge ganz am Ende einen JSON-Block an, genau so:
\`\`\`json
{"termine": [{"titel": "...", "datum": "JJJJ-MM-TT", "beginn": "HH:MM", "dauer_min": 60, "ort": "...", "teilnehmer": ["..."]}]}
\`\`\`
Jeder Termin aus dem Abschnitt „Termine“ kommt auch in den JSON-Block, auch Vor-Ort-Einsätze.
Nur Termine, die in der Mitschrift wirklich vereinbart wurden. Keine Termine: leere Liste.

Mitschrift:
${text}`;
}

function isoTag(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function jsonAbtrennen(antwort) {
  const treffer = antwort.match(/```json\s*([\s\S]*?)```/);
  if (!treffer) return { text: antwort.trim(), daten: null };
  let daten = null;
  try {
    daten = JSON.parse(treffer[1]);
  } catch {
    /* kaputtes JSON: keine Kalenderknoepfe */
  }
  return { text: antwort.replace(treffer[0], "").trim(), daten };
}

function terminText(t) {
  const tag = new Date(`${t.datum}T12:00:00`).toLocaleDateString("de-DE", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  return [tag, t.beginn ? `${t.beginn} Uhr` : "ganztägig", t.dauer_min ? `${t.dauer_min} min` : "", t.ort || ""]
    .filter(Boolean)
    .join(" · ");
}

// iCalendar mit lokaler Zeit (ohne Zeitzone): jeder Kalender legt den Termin
// zur angegebenen Uhrzeit an.
function ics(liste) {
  const stempel = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  const esc = (s) => String(s || "").replace(/\\/g, "\\\\").replace(/[,;]/g, (z) => `\\${z}`).replace(/\n/g, "\\n");
  const zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:Messstand Sprache"];
  liste.forEach((t, i) => {
    const tag = t.datum.replace(/-/g, "");
    zeilen.push("BEGIN:VEVENT", `UID:${stempel}-${i}@messstand.local`, `DTSTAMP:${stempel}`);
    if (/^\d{1,2}:\d{2}$/.test(t.beginn || "")) {
      const [h, m] = t.beginn.split(":").map(Number);
      const ende = new Date(2000, 0, 1, h, m + (Number(t.dauer_min) || 60));
      const hhmm = (d) => `${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}00`;
      const tagEnde = ende.getDate() > 1 ? naechsterTag(t.datum) : tag;
      zeilen.push(`DTSTART:${tag}T${hhmm(new Date(2000, 0, 1, h, m))}`, `DTEND:${tagEnde}T${hhmm(ende)}`);
    } else {
      zeilen.push(`DTSTART;VALUE=DATE:${tag}`, `DTEND;VALUE=DATE:${naechsterTag(t.datum)}`);
    }
    zeilen.push(`SUMMARY:${esc(t.titel)}`);
    if (t.ort) zeilen.push(`LOCATION:${esc(t.ort)}`);
    if (t.teilnehmer?.length) zeilen.push(`DESCRIPTION:${esc("Teilnehmer: " + t.teilnehmer.join(", "))}`);
    zeilen.push("END:VEVENT");
  });
  zeilen.push("END:VCALENDAR");
  return zeilen.join("\r\n") + "\r\n";
}

function naechsterTag(iso) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
}

function herunterladen(inhalt, name, typ) {
  const url = URL.createObjectURL(new Blob([inhalt], { type: `${typ};charset=utf-8` }));
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function dateiname(titel) {
  return (titel || "termin").toLowerCase().replace(/[^a-z0-9äöüß]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "termin";
}

function zeitText(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function kachelwert() {
  return el("span", { class: "wert", text: "–" });
}

function kachel(name, wert, einheit) {
  return el("div", { class: "kachel" }, [
    el("div", { class: "name", text: name }),
    el("div", {}, [wert, el("span", { class: "einheit", text: einheit })]),
  ]);
}
