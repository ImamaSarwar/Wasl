import { useEffect, useState } from "react";
import { api } from "../api.js";
import TreeView from "./TreeView.jsx";
import AyahLine from "./AyahLine.jsx";
import RootLesson from "./RootLesson.jsx";

// Everything about ONE selected root: family tree, distribution across ayahs,
// verse drill-down for the selected form, and roots that co-occur with it.
export default function RootPanel({ root, roots, ayahsByNum, clickedId, onSelectRoot, onHover, onJumpToAyah }) {
  const [tree, setTree] = useState(null);
  const [dist, setDist] = useState([]);
  const [cross, setCross] = useState([]);
  const [lemma, setLemma] = useState(null);
  const [drill, setDrill] = useState([]);
  const [error, setError] = useState(null);

  // Load tree + distribution + co-occurring roots when the root changes.
  useEffect(() => {
    setTree(null); setDist([]); setCross([]); setLemma(null); setDrill([]); setError(null);
    if (!root) return;
    Promise.all([api.tree(root), api.distribution(root), api.cross(root)])
      .then(([t, d, c]) => {
        setTree(t); setDist(d); setCross(c);
        setLemma(t.forms[0]?.lemma ?? null); // open the most frequent form by default
      })
      .catch((e) => setError(e.message));
  }, [root]);

  // Load the ayahs for the selected form.
  useEffect(() => {
    if (!root || !lemma) return;
    api.formAyahs(root, lemma).then(setDrill).catch((e) => setError(e.message));
  }, [root, lemma]);

  const maxCount = Math.max(1, ...dist.map((d) => d.count));

  return (
    <section className="card">
      <div className="card-head">
        <h2>Root explorer</h2>
        <select value={root || ""} onChange={(e) => onSelectRoot(e.target.value || null)}>
          <option value="">Choose a root...</option>
          {roots.map((r) => (
            <option key={r.root} value={r.root}>
              {r.root} ({r.count})
            </option>
          ))}
        </select>
      </div>

      {!root && <p className="hint">Hover any word in the surah, then click it (or pick a root above).</p>}
      {error && <p className="error">{error}</p>}

      {tree && (
        <>
          <p className="summary">
            <b className="arabic-inline" dir="rtl" lang="ar">{root}</b> appears{" "}
            <b>{tree.total}</b> time{tree.total === 1 ? "" : "s"} in {tree.forms.length} form
            {tree.forms.length === 1 ? "" : "s"}.
          </p>

          <TreeView tree={tree} selectedLemma={lemma} onSelectForm={setLemma} />

          <RootLesson key={tree.root} root={tree.root} ayahsByNum={ayahsByNum} onJumpToAyah={onJumpToAyah} />

          <h3>Where it occurs</h3>
          <div className="dist">
            {dist.map((d) => (
              <button
                key={d.ayah}
                className={"bar" + (d.count ? " on" : "")}
                title={`Ayah ${d.ayah}: ${d.count}`}
                onClick={() => d.count && onJumpToAyah(d.ayah)}
              >
                <span className="bar-fill" style={{ height: `${(d.count / maxCount) * 100}%` }} />
                <span className="bar-label">{d.ayah}</span>
              </button>
            ))}
          </div>

          {cross.length > 0 && (
            <>
              <h3>Appears together with</h3>
              <ul className="chips">
                {cross.slice(0, 8).map((c) => {
                  const other = c.root_a === root ? c.root_b : c.root_a;
                  return (
                    <li key={other}>
                      <button
                        className="chip"
                        title={`Open the root ${other}`}
                        onClick={() => onSelectRoot(other)}
                      >
                        <span className="chip-root" dir="rtl" lang="ar">{other}</span>
                        <span className="chip-ayahs">ayah{c.ayahs.length === 1 ? "" : "s"} {c.ayahs.join(", ")}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          <h3>
            Ayahs with <span className="arabic-inline" dir="rtl" lang="ar">{lemma}</span>
          </h3>
          {drill.map((d) => {
            const ayah = ayahsByNum[d.ayah];
            if (!ayah) return null;
            return (
              <AyahLine
                key={d.ayah}
                ayah={ayah}
                clickedId={clickedId}
                highlightIds={new Set(d.word_ids.split(",").map(Number))}
                onHover={onHover}
                onWordClick={onSelectRoot}
              />
            );
          })}
        </>
      )}
    </section>
  );
}
