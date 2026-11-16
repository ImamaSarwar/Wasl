import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { usePlayer } from "./hooks/usePlayer.js";
import ReaderHeader from "./components/ReaderHeader.jsx";
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

  // ---- recitation + tafsir ----
  const [reciters, setReciters] = useState([]);
  const [reciterId, setReciterId] = useState(null);
  const [recsFor, setRecsFor] = useState({ id: null, data: null }); // timings for ONE reciter, tagged with whose they are
  const [tafsirSources, setTafsirSources] = useState([]);
  const [openTafsir, setOpenTafsir] = useState(() => new Set()); // ayah numbers whose tafsir is open
  const resume = useRef(null); // if the reciter changes mid-recitation: { ayah, continuous } to carry on with

  const recs = recsFor.id === reciterId ? recsFor.data : null; // never play the previous reciter's data
  const player = usePlayer(recs, 30);

  useEffect(() => {
    Promise.all([api.ayahs(), api.roots()])
      .then(([a, r]) => { setAyahs(a); setRoots(r); })
      .catch(() => setError("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running on port 8000?"));
    // Listening and tafsir are extras: if they fail, the reader still works.
    api.reciters().then((list) => {
      setReciters(list);
      let saved = null;
      try { saved = localStorage.getItem("wasl.reciter"); } catch { /* storage unavailable: ignore */ }
      setReciterId(list.some((r) => r.id === saved) ? saved : list[0]?.id ?? null);
    }).catch(() => {});
    api.tafsirSources().then(setTafsirSources).catch(() => {});
  }, []);

  // Load the timings whenever the chosen reciter changes.
  useEffect(() => {
    if (!reciterId) return;
    let cancelled = false;
    api.recitations(reciterId)
      .then((data) => !cancelled && setRecsFor({ id: reciterId, data }))
      .catch(() => {});
    return () => { cancelled = true; };
  }, [reciterId]);

  // After a reciter switch, restart the ayah that was playing with the new voice.
  useEffect(() => {
    if (recs && resume.current) {
      const { ayah, continuous } = resume.current;
      resume.current = null;
      player.play(ayah, { continuous });
    }
  }); // intentionally every render: it only acts when `recs` has just arrived and a resume is pending

  const changeReciter = useCallback((id) => {
    if (player.ayah != null && (player.status === "playing" || player.status === "loading")) {
      resume.current = { ayah: player.ayah, continuous: player.continuous };
    }
    player.stop();
    setReciterId(id);
    try { localStorage.setItem("wasl.reciter", id); } catch { /* ignore */ }
  }, [player]);

  const toggleTafsir = useCallback((n) => {
    setOpenTafsir((prev) => {
      const next = new Set(prev);
      next.has(n) ? next.delete(n) : next.add(n);
      return next;
    });
  }, []);

  // While the whole surah is being recited, keep the current ayah in view.
  useEffect(() => {
    if (player.continuous && player.ayah != null) {
      document.getElementById(`ayah-${player.ayah}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [player.ayah, player.continuous]);

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
        <h1>Wasl</h1>
        <p className="tagline">Quran Root Explorer <span>·</span> Surah Al-Mulk</p>
      </header>

      {error && <p className="error banner">{error}</p>}

      <main>
        <section className="reader card">
          <ReaderHeader reciters={reciters} reciterId={reciterId} onChangeReciter={changeReciter} player={player} />
          {ayahs.map((a) => (
            <AyahLine
              key={a.ayah}
              ayah={a}
              selectedRoot={selectedRoot}
              clickedId={clickedId}
              onHover={onHover}
              onWordClick={selectRoot}
              player={player}
              hasAudio={!!recs?.[a.ayah]}
              tafsirSources={tafsirSources}
              tafsirOpen={openTafsir.has(a.ayah)}
              onToggleTafsir={() => toggleTafsir(a.ayah)}
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
        Recitations and tafsir via Tarteel QUL; audio is streamed from the links in those files.
      </footer>

      <HoverCard hover={hover} />
    </div>
  );
}
