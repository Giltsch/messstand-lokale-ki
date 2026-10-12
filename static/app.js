// Start der Oberflaeche: Kopfzeile, Reiter, Statusabfrage, Theme.

import { el, zahl } from "./format.js";
import { holen } from "./api.js";
import { store, stationSetzen, bus } from "./store.js";
import { aufgabeAufbauen } from "./aufgabe.js";

const REITER = [
  { id: "aufgabe", titel: "Aufgabe", aufbauen: aufgabeAufbauen },
];

const kopf = {
  name: document.getElementById("station-name"),
  daten: document.getElementById("kopf-daten"),
  punkte: document.getElementById("status-punkte"),
  netz: document.getElementById("netz-status"),
};
const reiterleiste = document.getElementById("reiterleiste");
const blaetter = document.getElementById("blaetter");

let aktiv = null;
const gebaut = new Map();
let letzterStand = "";

// ---------- Kopfzeile ----------

function kopfZeichnen() {
  const s = store.station;
  if (!s) return;
  kopf.name.textContent = s.station.name;
  const bandbreite =
    s.station.bandbreite_gbs === null || s.station.bandbreite_gbs === undefined
      ? "unbekannt"
      : `${zahl(s.station.bandbreite_gbs, 0)} GB/s`;
  kopf.daten.replaceChildren(
    el("span", { html: `Gerät: <b>${s.station.geraet}</b>` }),
    el("span", {
      html: `Arbeitsspeicher: <b>${
        s.station.speicher_gb ? zahl(s.station.speicher_gb, 0) + " GB" : "unbekannt"
      }</b>`,
    }),
    el("span", { html: `Speicherbandbreite: <b>${bandbreite}</b>` })
  );
  const punkte = s.backends.map((b) =>
    el("span", {
      class: `punkt ${b.online ? "online" : "offline"}`,
      title: b.online ? `${b.label} erreichbar unter ${b.url}` : `${b.label} antwortet nicht`,
      text: b.label,
    })
  );
  if (s.embedding) {
    punkte.push(
      el("span", {
        class: `punkt ${s.embedding.online && s.embedding.vorhanden ? "online" : "offline"}`,
        title: `Einbettungsmodell ${s.embedding.modell}`,
        text: "Einbettung",
      })
    );
  }
  kopf.punkte.replaceChildren(...punkte);
}

function netzZeichnen() {
  const online = navigator.onLine;
  kopf.netz.className = `netz ${online ? "" : "offline"}`;
  kopf.netz.textContent = online
    ? "Netzwerk: verbunden (wird nicht gebraucht)"
    : "Netzwerk: getrennt — läuft weiter";
}

// ---------- Reiter ----------

function reiterZeichnen() {
  reiterleiste.replaceChildren(
    ...REITER.map((r) => {
      const knopf = el("button", {
        type: "button",
        role: "tab",
        id: `reiter-${r.id}`,
        "aria-selected": String(aktiv === r.id),
        "aria-controls": `blatt-${r.id}`,
        text: r.titel,
        disabled: r.aktiv ? !r.aktiv() : false,
        onclick: () => reiterWaehlen(r.id),
      });
      return knopf;
    })
  );
}

function reiterWaehlen(id) {
  const eintrag = REITER.find((r) => r.id === id);
  if (!eintrag) return;
  aktiv = id;
  for (const r of REITER) {
    let blatt = document.getElementById(`blatt-${r.id}`);
    if (!blatt) {
      blatt = el("section", {
        class: "blatt",
        id: `blatt-${r.id}`,
        role: "tabpanel",
        "aria-labelledby": `reiter-${r.id}`,
        hidden: true,
      });
      blaetter.append(blatt);
    }
    blatt.hidden = r.id !== id;
  }
  if (!gebaut.has(id)) {
    gebaut.set(id, eintrag.aufbauen(document.getElementById(`blatt-${id}`)));
  }
  reiterZeichnen();
  location.hash = id;
}

export function reiterAnmelden(eintrag) {
  if (!REITER.find((r) => r.id === eintrag.id)) REITER.push(eintrag);
}

// ---------- Theme ----------

function themeSetzen(name) {
  document.documentElement.dataset.theme = name;
  try {
    localStorage.setItem("messstand-theme", name);
  } catch {
    /* privater Modus: dann eben nicht merken */
  }
  const knopf = document.getElementById("theme-knopf");
  knopf.textContent = name === "dunkel" ? "Helles Thema" : "Dunkles Thema";
  knopf.setAttribute(
    "aria-label",
    name === "dunkel" ? "Zu hellem Thema wechseln" : "Zu dunklem Thema wechseln"
  );
}

// ---------- Start ----------

async function standHolen(pfad = "/api/status") {
  try {
    const daten = await holen(pfad);
    const stand = JSON.stringify(daten);
    if (stand !== letzterStand) {
      letzterStand = stand;
      stationSetzen(daten);
    }
  } catch (fehler) {
    kopf.punkte.replaceChildren(
      el("span", { class: "punkt offline", text: "Messstand antwortet nicht" })
    );
  }
}

async function start() {
  let gemerkt = null;
  try {
    gemerkt = localStorage.getItem("messstand-theme");
  } catch {
    /* ignorieren */
  }
  themeSetzen(gemerkt || "hell");
  document.getElementById("theme-knopf").addEventListener("click", () => {
    themeSetzen(document.documentElement.dataset.theme === "dunkel" ? "hell" : "dunkel");
  });

  bus.addEventListener("station", () => {
    kopfZeichnen();
    reiterZeichnen();
  });
  window.addEventListener("online", netzZeichnen);
  window.addEventListener("offline", netzZeichnen);
  netzZeichnen();

  await standHolen("/api/station");
  const gewuenscht = location.hash.replace("#", "");
  reiterWaehlen(REITER.find((r) => r.id === gewuenscht) ? gewuenscht : REITER[0].id);
  setInterval(() => standHolen(), 15000);
}

start();
