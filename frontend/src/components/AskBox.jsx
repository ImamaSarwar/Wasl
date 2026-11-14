import { useState } from "react";
import { api } from "../api.js";

// Chat box for the RAG assistant. Talks to POST /api/ask (a placeholder until Phase 4).
// It already renders the final response shape: answer, citations, refused, verification_errors.
export default function AskBox({ onJumpToAyah }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try {
      setRes(await api.ask(q));
    } catch (err) {
      setRes({ answer: `Error: ${err.message}`, citations: [], refused: true, verification_errors: [] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head"><h2>Ask about the roots</h2></div>
      <form onSubmit={submit} className="ask-form">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder='e.g. "How is the root of khalaqa used in this surah?"'
        />
        <button disabled={busy}>{busy ? "..." : "Ask"}</button>
      </form>
      {res && (
        <div className={"answer" + (res.refused ? " refused" : "")}>
          <p>{res.answer}</p>
          {res.citations?.length > 0 && (
            <p className="cites">
              Cited:{" "}
              {res.citations.map((n) => (
                <button key={n} className="link" onClick={() => onJumpToAyah(n)}>
                  [67:{n}]
                </button>
              ))}
            </p>
          )}
          {res.verification_errors?.length > 0 && (
            <ul className="error">{res.verification_errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
          )}
        </div>
      )}
    </section>
  );
}
