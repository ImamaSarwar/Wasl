// Run with:  cd frontend && npm test      (uses Node's built-in test runner; nothing to install)
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  STORAGE_KEY, MAX_NOTE_LENGTH, getStorage, noteKey, cleanNotes, loadNotes, saveNotes, storageWorks, makeNote, buildExport,
} from "./notesStore.js";

const fakeStorage = (initial = {}, { failWrites = false } = {}) => {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { if (failWrites) throw new Error("QuotaExceededError"); data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
  };
};

test("noteKey is surah:ayah", () => assert.equal(noteKey(5), "67:5"));

test("cleanNotes keeps good notes and drops junk", () => {
  const out = cleanNotes({
    "67:1": { text: "hello", updated: "2026-11-16T10:00:00.000Z" },
    "67:2": { text: "   ", updated: "2026-11-16T10:00:00.000Z" },   // blank
    "abc": { text: "bad key" },
    "67:3": "not an object",
    "67:4": { text: 5 },
    "67:5": { text: "no date" },
  });
  assert.deepEqual(Object.keys(out).sort(), ["67:1", "67:5"]);
  assert.equal(out["67:5"].updated, new Date(0).toISOString());
});

test("cleanNotes survives non-objects and truncates huge notes", () => {
  assert.deepEqual(cleanNotes(null), {});
  assert.deepEqual(cleanNotes([1, 2]), {});
  assert.deepEqual(cleanNotes("x"), {});
  const big = cleanNotes({ "67:1": { text: "a".repeat(MAX_NOTE_LENGTH + 50), updated: "2026-01-01T00:00:00Z" } });
  assert.equal(big["67:1"].text.length, MAX_NOTE_LENGTH);
});

test("save then load round-trips, including Arabic", () => {
  const s = fakeStorage();
  const notes = { "67:2": makeNote("خلق = to create\nsecond line  \n\n", new Date("2026-11-16T10:00:00Z")) };
  assert.equal(saveNotes(s, notes), true);
  assert.deepEqual(loadNotes(s), notes);
  assert.equal(notes["67:2"].text, "خلق = to create\nsecond line");   // trailing whitespace trimmed
});

test("loadNotes never throws on corrupt data or a broken storage", () => {
  assert.deepEqual(loadNotes(fakeStorage({ [STORAGE_KEY]: "{not json" })), {});
  assert.deepEqual(loadNotes({ getItem() { throw new Error("blocked"); } }), {});
});

test("saveNotes reports failure instead of throwing", () => {
  assert.equal(saveNotes(fakeStorage({}, { failWrites: true }), { "67:1": makeNote("x") }), false);
});

test("storageWorks", () => {
  assert.equal(storageWorks(fakeStorage()), true);
  assert.equal(storageWorks(fakeStorage({}, { failWrites: true })), false);
});

test("buildExport lists only ayahs that have notes, in ayah order, with context", () => {
  const ayahs = [
    { ayah: 1, arabic: "AR1", translation: "EN1" },
    { ayah: 2, arabic: "AR2", translation: "EN2" },
    { ayah: 3, arabic: "AR3", translation: "EN3" },
  ];
  const notes = { "67:3": makeNote("third"), "67:1": makeNote("first") };
  const text = buildExport(ayahs, notes, new Date("2026-11-16T10:00:00Z"));
  assert.ok(text.indexOf("Ayah 1") < text.indexOf("Ayah 3"));
  assert.ok(!text.includes("Ayah 2"));
  assert.ok(text.includes("AR1") && text.includes("EN3") && text.includes("first") && text.includes("third"));
});

test("a browser that blocks storage never crashes the app", () => {
  // Chrome with "block all cookies" throws just from reading window.localStorage.
  const blocked = { get localStorage() { throw new Error("SecurityError"); } };
  assert.equal(getStorage(blocked), null);
  assert.deepEqual(loadNotes(null), {});
  assert.equal(saveNotes(null, { "67:1": makeNote("x") }), false);
  assert.equal(storageWorks(null), false);
  assert.equal(getStorage(null), null);
});
