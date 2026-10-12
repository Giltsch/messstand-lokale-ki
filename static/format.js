// Zahlen und Zeiten in deutscher Schreibweise.

export function zahl(wert, stellen = 1) {
  if (wert === null || wert === undefined || Number.isNaN(wert)) return "–";
  return Number(wert).toLocaleString("de-DE", {
    minimumFractionDigits: stellen,
    maximumFractionDigits: stellen,
  });
}

export function ganz(wert) {
  if (wert === null || wert === undefined) return "–";
  return Number(wert).toLocaleString("de-DE");
}

export function sekunden(wert) {
  if (wert === null || wert === undefined) return "–";
  return zahl(wert, wert < 10 ? 2 : 1);
}

export function tempo(wert) {
  if (wert === null || wert === undefined) return "–";
  return zahl(wert, wert < 10 ? 1 : 0);
}

export function faktor(wert) {
  if (!Number.isFinite(wert) || wert <= 0) return "–";
  return zahl(wert, 2) + "x";
}

// Minimaler Text-Einsetzer: {text} in der Vorlage ersetzen.
export function einsetzen(vorlage, werte) {
  return String(vorlage || "").replace(/\{(\w+)\}/g, (treffer, name) =>
    name in werte ? werte[name] : treffer
  );
}

export function el(tag, attribute = {}, kinder = []) {
  const knoten = document.createElement(tag);
  for (const [name, wert] of Object.entries(attribute)) {
    if (wert === null || wert === undefined || wert === false) continue;
    if (name === "class") knoten.className = wert;
    else if (name === "text") knoten.textContent = wert;
    else if (name === "html") knoten.innerHTML = wert;
    else if (name.startsWith("on")) knoten.addEventListener(name.slice(2), wert);
    else knoten.setAttribute(name, wert === true ? "" : wert);
  }
  for (const kind of [].concat(kinder)) {
    if (kind === null || kind === undefined) continue;
    knoten.append(kind instanceof Node ? kind : document.createTextNode(String(kind)));
  }
  return knoten;
}
