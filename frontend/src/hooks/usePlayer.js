import { useCallback, useEffect, useRef, useState } from "react";

// One shared <audio> element that plays a single ayah of the surah.
//
//   recs : {ayah: {url, start_ms, end_ms, segments}} for the chosen reciter (from /api/recitations/<id>)
//          - per-ayah MP3s:  start_ms/end_ms are null; the whole file is the ayah
//          - whole-surah MP3 (e.g. Yasser Al-Dosari): start_ms/end_ms say where the ayah sits inside the file,
//            so we jump to start_ms and stop at end_ms
//          - segments: [[word_number, start_ms, end_ms], ...] on the file's own clock -> word-by-word highlight
//
// Returns { ayah, status, word, progress, error, continuous, toggle, play, playSurah, stop }
//   status: "idle" | "loading" | "playing" | "paused" | "error"
//   word  : the word number (1-based, same as words.pos) being recited right now, or null

const IDLE = { ayah: null, status: "idle", word: null, progress: 0, error: null };
const LOAD_ERROR = "This recording could not be loaded. Check your connection, or try another reciter.";

export function usePlayer(recs, lastAyah = 30) {
  const audioRef = useRef(null);
  const recsRef = useRef(recs);
  recsRef.current = recs; // always the latest, so event handlers never see stale data

  const [state, setState] = useState(IDLE);
  const [continuous, setContinuous] = useState(false);

  // Mutable playback info kept in refs (changes every frame; must not re-render).
  const tokenRef = useRef(0);          // bumps on every new play(); stale async callbacks check it
  const ayahRef = useRef(null);
  const endMsRef = useRef(null);
  const startMsRef = useRef(0);
  const segsRef = useRef(null);
  const loadedUrlRef = useRef(null);
  const pendingRef = useRef(null);     // a "loadedmetadata" listener we may need to cancel
  const rafRef = useRef(0);
  const continuousRef = useRef(false);
  const fns = useRef({});              // latest versions of the functions below, for the audio event listeners

  const getAudio = () => {
    if (!audioRef.current) {
      audioRef.current = new Audio();
      audioRef.current.preload = "auto";
    }
    return audioRef.current;
  };

  const stopTick = () => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = 0;
  };

  const startTick = () => {
    stopTick();
    const loop = () => {
      fns.current.tick();
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
  };

  // Runs every animation frame while playing: find the current word, update progress, stop at the ayah's end.
  fns.current.tick = () => {
    const a = getAudio();
    const t = a.currentTime * 1000;
    const end = endMsRef.current;
    if (end != null && t >= end) {
      fns.current.finish();
      return;
    }
    let word = null;
    let bestStart = -1;
    for (const [w, s] of segsRef.current || []) {
      if (s <= t && s >= bestStart) { word = w; bestStart = s; }
    }
    const from = startMsRef.current;
    const total = end != null ? end - from : (a.duration || 0) * 1000;
    const progress = total > 0 ? Math.min(1, Math.max(0, (t - from) / total)) : 0;
    const rounded = Math.round(progress * 100) / 100;
    setState((s) => (s.status === "playing" && (s.word !== word || s.progress !== rounded) ? { ...s, word, progress: rounded } : s));
  };

  // The ayah is over: carry on to the next one (play-surah mode) or go idle.
  fns.current.finish = () => {
    const a = getAudio();
    const n = ayahRef.current;
    const cur = recsRef.current?.[n];
    const next = recsRef.current?.[n + 1];
    if (continuousRef.current && cur && next && n < lastAyah) {
      if (cur.url === next.url && !a.paused && !a.ended) {
        // Same whole-surah file: keep playing straight through, no seeking, no gap.
        tokenRef.current += 1;
        ayahRef.current = n + 1;
        endMsRef.current = next.end_ms ?? null;
        startMsRef.current = next.start_ms ?? 0;
        segsRef.current = next.segments;
        setState({ ...IDLE, ayah: n + 1, status: "playing" });
        return;
      }
      fns.current.play(n + 1);
      return;
    }
    stopTick();
    a.pause();
    ayahRef.current = null;
    setState(IDLE);
  };

  fns.current.fail = () => {
    stopTick();
    setState({ ...IDLE, ayah: ayahRef.current, status: "error", error: LOAD_ERROR });
  };

  fns.current.play = (n, opts = {}) => {
    const a = getAudio();
    const rec = recsRef.current?.[n];
    if (!rec) return;
    if (opts.continuous !== undefined) {
      continuousRef.current = opts.continuous;
      setContinuous(opts.continuous);
    }
    const token = ++tokenRef.current;
    ayahRef.current = n;
    endMsRef.current = rec.end_ms ?? null;
    startMsRef.current = rec.start_ms ?? 0;
    segsRef.current = rec.segments;
    setState({ ...IDLE, ayah: n, status: "loading" });

    const begin = () => {
      pendingRef.current = null;
      if (token !== tokenRef.current) return; // the user already clicked something else
      a.currentTime = startMsRef.current / 1000;
      a.play()
        .then(() => {
          // Jumping to another ayah of a file that is ALREADY playing never fires a new "playing" event,
          // so move out of "loading" here and make sure the word/progress loop is running.
          if (token !== tokenRef.current) return;
          setState((s) => (s.ayah === n && s.status === "loading" ? { ...s, status: "playing" } : s));
          startTick();
        })
        .catch(() => token === tokenRef.current && fns.current.fail());
    };

    if (pendingRef.current) {
      a.removeEventListener("loadedmetadata", pendingRef.current);
      pendingRef.current = null;
    }
    if (loadedUrlRef.current === rec.url && a.readyState >= 1) {
      begin();
    } else {
      if (loadedUrlRef.current !== rec.url) {
        loadedUrlRef.current = rec.url;
        a.src = rec.url;
      }
      pendingRef.current = begin;
      a.addEventListener("loadedmetadata", begin, { once: true });
      a.load();
    }
  };

  // Wire the audio element's events once.
  useEffect(() => {
    const a = getAudio();
    const on = {
      playing: () => { setState((s) => (s.ayah == null ? s : { ...s, status: "playing", error: null })); startTick(); },
      waiting: () => setState((s) => (s.status === "playing" ? { ...s, status: "loading" } : s)),
      ended: () => fns.current.finish(),
      error: () => ayahRef.current != null && fns.current.fail(),
    };
    Object.entries(on).forEach(([e, f]) => a.addEventListener(e, f));
    return () => {
      Object.entries(on).forEach(([e, f]) => a.removeEventListener(e, f));
      stopTick();
      a.pause();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = useCallback(() => {
    tokenRef.current += 1;
    continuousRef.current = false;
    setContinuous(false);
    stopTick();
    getAudio().pause();
    ayahRef.current = null;
    setState(IDLE);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (n) => {
    const a = getAudio();
    if (ayahRef.current === n && state.status === "playing") {
      a.pause();
      stopTick();
      setState((s) => ({ ...s, status: "paused" }));
    } else if (ayahRef.current === n && state.status === "paused") {
      a.play().catch(() => fns.current.fail());
    } else {
      fns.current.play(n, { continuous: false });
    }
  };

  return {
    ...state,
    continuous,
    toggle,
    play: (n, opts) => fns.current.play(n, opts),
    playSurah: () => fns.current.play(1, { continuous: true }),
    stop,
  };
}
