// Zugriff auf den lokalen Server. Alles relativ, nichts Externes.

export async function holen(pfad) {
  const antwort = await fetch(pfad, { headers: { Accept: "application/json" } });
  if (!antwort.ok) throw new Error(`${pfad}: Fehlercode ${antwort.status}`);
  return antwort.json();
}

export async function senden(pfad, rumpf, methode = "POST") {
  const antwort = await fetch(pfad, {
    method: methode,
    headers: { "Content-Type": "application/json" },
    body: rumpf === undefined ? undefined : JSON.stringify(rumpf),
  });
  if (!antwort.ok) throw new Error(`${pfad}: Fehlercode ${antwort.status}`);
  return antwort.json();
}

// Server-Sent-Events ueber POST lesen. aufEreignis bekommt jedes JSON-Objekt.
export async function strom(pfad, rumpf, aufEreignis, signal) {
  const antwort = await fetch(pfad, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rumpf),
    signal,
  });
  if (!antwort.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await antwort.json());
    } catch {
      detail = await antwort.text().catch(() => "");
    }
    aufEreignis({
      art: "fehler",
      nachricht: `Der Server hat die Anfrage abgelehnt (Fehlercode ${antwort.status}).`,
      detail,
    });
    return;
  }
  const leser = antwort.body.getReader();
  const dekoder = new TextDecoder();
  let puffer = "";
  while (true) {
    const { value, done } = await leser.read();
    if (done) break;
    puffer += dekoder.decode(value, { stream: true });
    const bloecke = puffer.split("\n\n");
    puffer = bloecke.pop();
    for (const block of bloecke) {
      for (const zeile of block.split("\n")) {
        if (!zeile.startsWith("data:")) continue;
        try {
          aufEreignis(JSON.parse(zeile.slice(5).trim()));
        } catch {
          /* unvollstaendige Zeile ignorieren */
        }
      }
    }
  }
}
