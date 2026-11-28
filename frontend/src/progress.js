// Turns saved quiz answers (see quizStore.js) into what the dashboard shows. Pure functions, no React,
// no browser globals, so they can be unit-tested with `npm test`. Simple counting rules, no AI model.

export const REVIEW_AFTER_DAYS = 7; // a learned root not practised for this long is suggested again
export const WEAK_BELOW = 0.7;      // a skill under 70% correct is worth practising...
export const MIN_ANSWERS = 3;       // ...once there are at least this many answers to judge by

// Grammar questions test the form of a word, not knowledge of its root, so they don't change root status.
const ROOT_TYPES = new Set(["vocabulary", "root", "contextual"]);

export const SKILLS = {
  vocabulary: { name: "Word meanings", level: "easy" },
  root: { name: "Finding roots", level: "easy" },
  tense: { name: "Verb tense", level: "intermediate" },
  person: { name: "Verb person", level: "intermediate" },
  case: { name: "Noun case", level: "intermediate" },
  contextual: { name: "Roots in verses", level: "hard" },
};

const skillOf = (a) => (a.type === "morphology" ? a.kind : a.type);

/**
 * One entry per practised root. Status:
 *   revise   - the latest answer was wrong
 *   learned  - the latest two answers were both right
 *   learning - right once so far
 * `attempts` must be oldest first (the order they are saved in).
 */
export function rootProgress(attempts) {
  const byRoot = new Map();
  for (const a of attempts) {
    if (!a.root || !ROOT_TYPES.has(a.type)) continue;
    const r = byRoot.get(a.root) ?? { root: a.root, streak: 0, mistakes: 0, last: null, wordId: null };
    r.streak = a.correct ? r.streak + 1 : 0;
    if (!a.correct) r.mistakes += 1;
    r.last = a.time;
    r.wordId = a.wordId ?? r.wordId;
    byRoot.set(a.root, r);
  }
  return [...byRoot.values()].map((r) => ({
    ...r,
    status: r.streak === 0 ? "revise" : r.streak >= 2 ? "learned" : "learning",
  }));
}

/** Roots to look at next: wrong ones first (most mistakes, then longest ago), then learned ones gone stale. */
export function revisionList(roots, now = new Date(), limit = 4) {
  const oldest = (a, b) => String(a.last).localeCompare(String(b.last));
  const wrong = roots.filter((r) => r.status === "revise")
    .sort((a, b) => b.mistakes - a.mistakes || oldest(a, b))
    .map((r) => ({ ...r, reason: "mistake" }));
  const stale = roots.filter((r) => r.status !== "revise" &&
      now - new Date(r.last) >= REVIEW_AFTER_DAYS * 86400000)
    .sort(oldest)
    .map((r) => ({ ...r, reason: "stale" }));
  return [...wrong, ...stale].slice(0, limit);
}

/** Share of correct answers per skill, in a fixed order. Skills never practised are left out. */
export function skillScores(attempts) {
  return Object.entries(SKILLS).map(([id, s]) => {
    const mine = attempts.filter((a) => skillOf(a) === id);
    const right = mine.filter((a) => a.correct).length;
    return { id, ...s, total: mine.length, right, share: mine.length ? right / mine.length : 0 };
  }).filter((s) => s.total > 0);
}

/** The weakest skill that clearly needs work, or null. */
export function weakestSkill(scores) {
  return scores.filter((s) => s.total >= MIN_ANSWERS && s.share < WEAK_BELOW)
    .sort((a, b) => a.share - b.share || b.total - a.total)[0] ?? null;
}

/**
 * Pairs the learner mixes up: the right answer and the wrong one picked, in either direction.
 * Most frequent first, then most recent. Verse questions are skipped (their options are ayahs, not forms).
 */
export function confusedPairs(attempts, limit = 4) {
  const pairs = new Map();
  attempts.forEach((a, order) => {
    if (a.correct || a.type === "contextual" || !a.answer || !a.chosen) return;
    const key = [skillOf(a), ...[a.answer, a.chosen].sort()].join("|");
    const p = pairs.get(key) ?? { key, skill: skillOf(a), count: 0 };
    Object.assign(p, { first: a.answer, second: a.chosen, wordId: a.wordId, order });
    p.count += 1;
    pairs.set(key, p);
  });
  return [...pairs.values()].sort((a, b) => b.count - a.count || b.order - a.order).slice(0, limit);
}

export const FOCUS_ROOTS = 8; // most roots sent to the quiz as "revise these"

/**
 * What the next quiz should practise (adaptive question selection, rule-based):
 * the roots on the dashboard's "Revise next" list (mistakes first, then stale) and the weakest skill.
 * The backend mixes these in (see backend/quiz.py); an empty result gives an ordinary quiz.
 */
export function quizFocus(attempts, now = new Date()) {
  const roots = revisionList(rootProgress(attempts), now, FOCUS_ROOTS).map((r) => r.root);
  const weak = weakestSkill(skillScores(attempts))?.id ?? null;
  return { roots, weak };
}
