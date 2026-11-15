import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import AyahLine from "./components/AyahLine.jsx";
import HoverCard from "./components/HoverCard.jsx";
import RootPanel from "./components/RootPanel.jsx";
import AskBox from "./components/AskBox.jsx";
import DebugPanel from "./components/DebugPanel.jsx";

export default function App() {
  const [ayahs, setAyahs] = useState([]);
  const [roots, setRoots] = useState([]);
  const [selectedRoot, setSelectedRoot] = useState(null);
  const [clickedId, setClickedId] = useState(null); // the exact word the user clicked (for a clear marker)
  const [hover, setHover] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([api.ayahs(), api.roots()])
      .then(([a, r]) => { setAyahs(a); setRoots(r); })
      .catch(() => setError("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running on port 8000?"));
  }, []);

  const ayahsByNum = useMemo(() => Object.fromEntries(ayahs.map((a) => [a.ayah, a])), [ayahs]);

  const onHover = useCallback((word, ayah, rect) => {
    setHover(word ? { word, ayah, rect } : null);
  }, []);

  // Called with (root, wordId) when a word is clicked, or just (root) from the dropdown / chips.
  const selectRoot = useCallback((root, wordId = null) => {
    setSelectedRoot(root || null);
    setClickedId(wordId);
  }, []);

  const jumpToAyah = useCallback((n) => {
    document.getElementById(`ayah-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  return (
    <div className="app">
      <header>
        <h1>Wasl <small>Quran Root Explorer - Surah Al-Mulk (67)</small></h1>
      </header>

      {error && <p className="error banner">{error}</p>}

      <main>
        <section className="reader card">
          <div className="card-head"><h2>Surah Al-Mulk</h2></div>
          {ayahs.map((a) => (
            <AyahLine
              key={a.ayah}
              ayah={a}
              selectedRoot={selectedRoot}
              clickedId={clickedId}
              onHover={onHover}
              onWordClick={selectRoot}
            />
          ))}
        </section>

        <aside>
          <RootPanel
            root={selectedRoot}
            roots={roots}
            ayahsByNum={ayahsByNum}
            clickedId={clickedId}
            onSelectRoot={selectRoot}
            onHover={onHover}
            onJumpToAyah={jumpToAyah}
          />
          <AskBox onJumpToAyah={jumpToAyah} />
          <DebugPanel />
        </aside>
      </main>

      <footer>
        Data: Quranic Arabic Corpus (Kais Dukes, GPL), quran-morphology (mustafa0x), Tanzil.net (text unmodified).
      </footer>

      <HoverCard hover={hover} />
    </div>
  );
}
