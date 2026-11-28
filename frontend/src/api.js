// Every backend call goes through here, so the Debug panel can show the last request/response.
// Paths are relative ("/api/..."); Vite proxies them to FastAPI (see vite.config.js).

const listeners = new Set();

export function onApiCall(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

async function request(method, path, body) {
  const started = performance.now();
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  listeners.forEach((fn) =>
    fn({ method, path, status: res.status, ms: Math.round(performance.now() - started), data })
  );
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
  return data;
}

const enc = encodeURIComponent;

export const api = {
  ayahs: () => request("GET", "/api/ayahs"),
  roots: () => request("GET", "/api/roots"),
  tree: (root) => request("GET", `/api/roots/${enc(root)}/tree`),
  formAyahs: (root, lemma) => request("GET", `/api/roots/${enc(root)}/forms/${enc(lemma)}/ayahs`),
  lesson: (root) => request("GET", `/api/roots/${enc(root)}/lesson`),
  distribution: (root) => request("GET", `/api/roots/${enc(root)}/distribution`),
  cross: (root) => request("GET", `/api/cross${root ? `?root=${enc(root)}` : ""}`),
  reciters: () => request("GET", "/api/reciters"),
  recitations: (reciterId) => request("GET", `/api/recitations/${enc(reciterId)}`),
  tafsirSources: () => request("GET", "/api/tafsir"),
  tafsir: (sourceId, ayah) => request("GET", `/api/tafsir/${enc(sourceId)}/${ayah}`),
  // focus = { roots: [...], weak: "tense" | null } from progress.quizFocus (adaptive question selection)
  quiz: (level, focus) => {
    const params = new URLSearchParams({ level });
    if (focus?.roots?.length) params.set("focus", focus.roots.join(","));
    if (focus?.weak) params.set("weak", focus.weak);
    return request("GET", `/api/quiz?${params}`);
  },
  // Wrong answer -> explanation written by Gemini from database evidence, checked before it is shown
  quizFeedback: (question, chosen) => request("POST", "/api/quiz/feedback", { question, chosen }),
  ask: (question) => request("POST", "/api/ask", { question }),
};
