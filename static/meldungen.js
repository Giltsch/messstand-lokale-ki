// Klartextmeldungen mit aufklappbarem technischem Detail.

import { el } from "./format.js";

export function meldung(wurzel, { art = "", nachricht, detail = "" }) {
  const teile = [el("div", { text: nachricht })];
  if (detail) {
    teile.push(
      el("details", {}, [
        el("summary", { text: "Technische Details" }),
        el("pre", { text: detail }),
      ])
    );
  }
  wurzel.replaceChildren(el("div", { class: `meldung ${art}` }, teile));
}

export function meldungLeeren(wurzel) {
  wurzel.replaceChildren();
}
