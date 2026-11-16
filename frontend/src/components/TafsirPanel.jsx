import { useEffect, useState } from "react";
import { api } from "../api.js";

// Commentary for one ayah. Commentary is grouped (one text covers several ayahs), so the panel says
// which ayahs it speaks about. The HTML is sanitized by the build script (scripts/import_tafsir.py)
// before it ever reaches the database, which is why it is safe to insert as HTML here.

const cache = new Map(); // "sourceId:ayah" -> response, shared by all ayahs of the same group

export default function TafsirPanel({ ayahNum, sources, onClose }) {
  const [sourceId, setSourceId] = useState(sources[0]?.id);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const key = `${sourceId}:${ayahNum}`;
    if (cache.has(key)) {
      setData(cache.get(key));
      setError(null);
      return;
    }
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .tafsir(sourceId, ayahNum)
      .then((t) => {
        for (let a = t.group_start; a <= t.group_end; a++) cache.set(`${sourceId}:${a}`, t);
        if (!cancelled) setData(t);
      })
      .catch(() => !cancelled && setError("Could not load the commentary."));
    return () => { cancelled = true; };
  }, [sourceId, ayahNum]);

  const shared = data && data.group_end > data.group_start;

  return (
    <section className="tafsir-panel" aria-label={`Tafsir for ayah ${ayahNum}`}>
      <header className="tafsir-head">
        {sources.length > 1 ? (
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)} aria-label="Tafsir source">
            {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        ) : (
          <span className="tafsir-source">{sources[0]?.name}</span>
        )}
        <button className="tafsir-close" onClick={onClose} aria-label="Close tafsir">Close</button>
      </header>

      {shared && (
        <p className="tafsir-scope">
          This commentary covers ayahs {data.group_start}-{data.group_end} together.
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="hint">Loading...</p>}
      {data && <div className="tafsir-body" dangerouslySetInnerHTML={{ __html: data.html }} />}
    </section>
  );
}
