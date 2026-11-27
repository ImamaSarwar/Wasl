import { useCallback, useEffect, useMemo, useState } from "react";
import { STORAGE_KEY, getStorage, loadNotes, saveNotes, storageWorks, makeNote, noteKey } from "../notesStore.js";

// The user's personal notes, one per ayah, kept in this browser (see notesStore.js for why not cookies).
//
//   saved   : notes that are stored            {"67:5": {text, updated}}
//   drafts  : text typed but not saved yet      {5: "text"}   (kept while the panel is closed, so nothing is lost)
//
// Returns helpers keyed by AYAH NUMBER (1-30).
export function useNotes() {
  const [saved, setSaved] = useState(() => loadNotes(getStorage()));
  const [drafts, setDrafts] = useState({});
  const [saveError, setSaveError] = useState(null);
  const storageOk = useMemo(() => storageWorks(getStorage()), []);

  // If the app is open in two tabs, keep them in step.
  useEffect(() => {
    const onStorage = (e) => e.key === STORAGE_KEY && setSaved(loadNotes(getStorage()));
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // Warn before closing the tab if something typed has not been saved.
  const hasUnsaved = Object.keys(drafts).length > 0;
  useEffect(() => {
    if (!hasUnsaved) return;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasUnsaved]);

  const persist = (next) => {
    setSaved(next);
    const ok = saveNotes(getStorage(), next);
    setSaveError(ok ? null : "Your browser would not store this note (storage is full or blocked). It will be lost when you close this page. Use 'Download my notes' to keep a copy.");
  };

  const get = useCallback((ayah) => saved[noteKey(ayah)] || null, [saved]);

  const setDraft = (ayah, text) => {
    const original = saved[noteKey(ayah)]?.text ?? "";
    setDrafts((d) => {
      const next = { ...d };
      if (text === original) delete next[ayah]; else next[ayah] = text;
      return next;
    });
  };

  const clearDraft = (ayah) => setDrafts((d) => { const next = { ...d }; delete next[ayah]; return next; });

  const save = (ayah, text) => {
    if (!text.trim()) return;
    persist({ ...saved, [noteKey(ayah)]: makeNote(text) });
    clearDraft(ayah);
  };

  const remove = (ayah) => {
    const next = { ...saved };
    delete next[noteKey(ayah)];
    persist(next);
    clearDraft(ayah);
  };

  return {
    saved,
    count: Object.keys(saved).length,
    storageOk,
    saveError,
    get,
    has: (ayah) => !!saved[noteKey(ayah)],
    draftOf: (ayah) => drafts[ayah],
    setDraft,
    clearDraft,
    save,
    remove,
  };
}
