import test from "node:test";
import assert from "node:assert/strict";
import { confusedPairs, revisionList, rootProgress, skillScores, weakestSkill } from "./progress.js";

const at = (day) => `2026-11-${String(day).padStart(2, "0")}T10:00:00.000Z`;
const a = (root, correct, day = 20, extra = {}) =>
  ({ type: "root", kind: null, root, correct, time: at(day), wordId: 1, answer: "x", chosen: correct ? "x" : "y", ...extra });
const status = (list) => Object.fromEntries(rootProgress(list).map((r) => [r.root, r.status]));

test("a root is learned after two right answers in a row", () => {
  assert.deepEqual(status([a("خلق", true), a("ملك", true), a("ملك", true)]), { "خلق": "learning", "ملك": "learned" });
});

test("a wrong answer sends a learned root back to revision", () => {
  const list = [a("خلق", true), a("خلق", true), a("خلق", false)];
  assert.equal(status(list)["خلق"], "revise");
  assert.equal(status([...list, a("خلق", true)])["خلق"], "learning");
});

test("grammar answers do not change root status", () => {
  assert.deepEqual(status([a("خلق", false, 20, { type: "morphology", kind: "tense" })]), {});
});

test("revision: mistakes first, then stale roots; fresh correct ones are left out", () => {
  const roots = rootProgress([
    a("old", true, 1), a("fresh", true, 26), a("once", false, 25), a("twice", false, 2), a("twice", false, 26),
  ]);
  const list = revisionList(roots, new Date(at(27)));
  assert.deepEqual(list.map((r) => [r.root, r.reason]),
    [["twice", "mistake"], ["once", "mistake"], ["old", "stale"]]);
  assert.equal(revisionList(roots, new Date(at(27)), 1).length, 1);
});

test("skill scores split grammar by kind and skip unpractised skills", () => {
  const list = [a("r", true), a("r", false), a("r", true, 20, { type: "morphology", kind: "case" })];
  assert.deepEqual(skillScores(list).map((s) => [s.id, s.right, s.total]), [["root", 1, 2], ["case", 1, 1]]);
});

test("weakest skill needs enough answers and a low score", () => {
  assert.equal(weakestSkill(skillScores([a("r", false), a("r", false)])), null);
  assert.equal(weakestSkill(skillScores([a("r", false), a("r", false), a("r", true)])).id, "root");
  assert.equal(weakestSkill(skillScores([a("r", true), a("r", true), a("r", true)])), null);
});

test("confused pairs count both directions together and skip verse questions", () => {
  const m = { type: "morphology", kind: "tense" };
  const list = [
    a("r", false, 20, { answer: "A", chosen: "B" }),
    a("r", false, 21, { ...m, answer: "Past", chosen: "Present" }),
    a("r", false, 22, { ...m, answer: "Present", chosen: "Past" }),
    a("r", false, 23, { type: "contextual", answer: "67:1", chosen: "67:2" }),
    a("r", true, 24),
  ];
  const pairs = confusedPairs(list);
  assert.deepEqual(pairs.map((p) => [p.skill, p.count]), [["tense", 2], ["root", 1]]);
  assert.equal(pairs[0].first, "Present"); // shows the latest direction
});

test("no answers gives empty results", () => {
  assert.deepEqual([rootProgress([]), revisionList([]), skillScores([]), confusedPairs([])], [[], [], [], []]);
});
