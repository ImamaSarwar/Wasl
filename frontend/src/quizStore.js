// Pure helpers for quiz results (no React, no browser globals), so they can be unit-tested with `npm test`.
// Results live in the browser's localStorage on this device only: no account, no server.
// The future dashboard reads this list; scores, learned roots and confused forms can all be derived from it.
//
// Stored shape: [{ level, type, kind, root, wordId, answer, chosen, correct, time }, ...]

export const QUIZ_KEY = "wasl.quiz.v1";
export const MAX_ATTEMPTS = 2000; // oldest are dropped beyond this

const textOf = (q, id) => {
  const o = q.options.find((x) => x.id === id);
  return o?.ayah ? `67:${o.ayah}` : o?.text ?? null;
};

export function makeAttempt(level, q, chosenId, now = new Date()) {
  return {
    level,
    type: q.type,
    kind: q.kind ?? null,
    root: q.root,
    wordId: q.word?.word_id ?? null,
    answer: textOf(q, q.answer),
    chosen: textOf(q, chosenId),
    correct: chosenId === q.answer,
    time: now.toISOString(),
  };
}

/** Never throws: blocked storage or corrupt data gives an empty list. */
export function loadAttempts(storage) {
  try {
    const list = JSON.parse(storage.getItem(QUIZ_KEY) || "[]");
    return Array.isArray(list) ? list.filter((a) => a && typeof a.correct === "boolean") : [];
  } catch {
    return [];
  }
}

/** Append one attempt. Returns false if it could not be saved. */
export function saveAttempt(storage, attempt) {
  try {
    const list = [...loadAttempts(storage), attempt].slice(-MAX_ATTEMPTS);
    storage.setItem(QUIZ_KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}
