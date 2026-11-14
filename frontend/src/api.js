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
  distribution: (root) => request("GET", `/api/roots/${enc(root)}/distribution`),
  cross: (root) => request("GET", `/api/cross${root ? `?root=${enc(root)}` : ""}`),
  ask: (question) => request("POST", "/api/ask", { question }),
};
