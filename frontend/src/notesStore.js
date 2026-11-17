// Pure helpers for the personal-notes feature (no React, no browser globals), so they can be unit-tested
// with `npm test`. Notes live in the browser's localStorage on this device only: no account, no server.
//
// Why localStorage and not cookies: cookies hold about 4 KB each and are re-sent to the server on every
// request; notes for 30 ayahs can easily exceed that. localStorage works the same way for the user
// (stays in this browser, no sign-up) but holds ~5 MB and never leaves the device.
//
// Stored shape:  { "67:5": { text: "my note", updated: "2026-11-16T19:14:00.000Z" }, ... }

export const STORAGE_KEY = "wasl.notes.v1";
export const SURAH = 67;
export const MAX_NOTE_LENGTH = 6000;

export const noteKey = (ayah) => `${SURAH}:${ayah}`;

/** window.localStorage, or null when the browser blocks it (merely reading the property can throw). */
export function getStorage(win = globalThis.window) {
  try {
    return win ? win.localStorage : null;
  } catch {
    return null;
  }
}

/** Keep only well-formed, non-empty notes. Anything else in storage (old/corrupt data) is dropped. */
export function cleanNotes(obj) {
  const out = {};
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return out;
  for (const [k, v] of Object.entries(obj)) {
    if (!/^\d+:\d+$/.test(k) || !v || typeof v.text !== "string" || !v.text.trim()) continue;
    out[k] = {
      text: v.text.slice(0, MAX_NOTE_LENGTH),
      updated: typeof v.updated === "string" && !Number.isNaN(Date.parse(v.updated)) ? v.updated : new Date(0).toISOString(),
    };
  }
  return out;
}

/** Read notes from a storage object (window.localStorage). Never throws. */
export function loadNotes(storage) {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    return raw ? cleanNotes(JSON.parse(raw)) : {};
  } catch {
    return {};
  }
}

/** Write notes. Returns true on success, false if storage is full/blocked. */
export function saveNotes(storage, notes) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(notes));
    return true;
  } catch {
    return false;
  }
}

/** Can this browser store anything at all? (Some private modes throw.) */
export function storageWorks(storage) {
  try {
    const probe = "__wasl_probe__";
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

/** The note for an ayah with its trailing whitespace removed, stamped with the time. */
export function makeNote(text, now = new Date()) {
  return { text: text.replace(/\s+$/, "").slice(0, MAX_NOTE_LENGTH), updated: now.toISOString() };
}

/** Plain-text export of every note, with the ayah for context. `ayahs` = the /api/ayahs payload. */
export function buildExport(ayahs, notes, now = new Date(), locale = "en-GB") {
  const fmt = (d) => new Date(d).toLocaleString(locale, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
  const lines = [`Wasl - my notes on Surah Al-Mulk (${SURAH})`, `Exported ${fmt(now)}`, ""];
  const withNotes = ayahs.filter((a) => notes[noteKey(a.ayah)]);
  for (const a of withNotes) {
    const n = notes[noteKey(a.ayah)];
    lines.push(
      "------------------------------------------------------------",
      `Ayah ${a.ayah}`,
      a.arabic,
      a.translation,
      "",
      `My note (saved ${fmt(n.updated)}):`,
      n.text,
      ""
    );
  }
  return lines.join("\n");
}
