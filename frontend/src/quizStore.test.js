import test from "node:test";
import assert from "node:assert/strict";
import { MAX_ATTEMPTS, QUIZ_KEY, loadAttempts, makeAttempt, saveAttempt } from "./quizStore.js";

const fake = (initial) => {
  const m = new Map(initial ? [[QUIZ_KEY, initial]] : []);
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
};
const q = {
  type: "root", root: "خلق", word: { word_id: 11 }, answer: "B",
  options: [{ id: "A", text: "م ل ك" }, { id: "B", text: "خ ل ق" }],
};

test("an attempt records what was chosen and whether it was right", () => {
  const a = makeAttempt("easy", q, "A", new Date("2026-11-26T10:00:00Z"));
  assert.equal(a.correct, false);
  assert.equal(a.chosen, "م ل ك");
  assert.equal(a.answer, "خ ل ق");
  assert.equal(a.wordId, 11);
});

test("attempts are appended and read back", () => {
  const s = fake();
  assert.equal(saveAttempt(s, makeAttempt("easy", q, "B")), true);
  saveAttempt(s, makeAttempt("easy", q, "A"));
  assert.deepEqual(loadAttempts(s).map((a) => a.correct), [true, false]);
});

test("old attempts are dropped beyond the limit", () => {
  const s = fake(JSON.stringify(Array(MAX_ATTEMPTS).fill({ correct: true })));
  saveAttempt(s, { correct: false });
  const list = loadAttempts(s);
  assert.equal(list.length, MAX_ATTEMPTS);
  assert.equal(list.at(-1).correct, false);
});

test("corrupt or blocked storage never throws", () => {
  assert.deepEqual(loadAttempts(fake("not json")), []);
  assert.deepEqual(loadAttempts(null), []);
  assert.equal(saveAttempt(null, { correct: true }), false);
});
