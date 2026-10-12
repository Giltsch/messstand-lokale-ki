// Gemeinsamer Zustand der Oberflaeche plus einfacher Nachrichtenkanal.

export const bus = new EventTarget();

export const store = {
  station: null,
};

export function stationSetzen(daten) {
  store.station = daten;
  bus.dispatchEvent(new CustomEvent("station", { detail: daten }));
}

export function backends() {
  return store.station?.backends ?? [];
}

export function backendVon(id) {
  return backends().find((b) => b.id === id) || null;
}

export function modellVon(backendId, modellId) {
  return backendVon(backendId)?.modelle.find((m) => m.id === modellId) || null;
}

export function erstesNutzbares() {
  for (const b of backends()) {
    const m = b.modelle.find((m) => m.vorhanden);
    if (b.online && m) return { backend: b.id, modell: m.id };
  }
  const b = backends()[0];
  return b ? { backend: b.id, modell: b.modelle[0]?.id ?? "" } : { backend: "", modell: "" };
}

export function ergebnisMelden(ergebnis) {
  bus.dispatchEvent(new CustomEvent("ergebnis", { detail: ergebnis }));
}
