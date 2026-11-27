import { useEffect, useRef, useState } from "react";
import { MAX_NOTE_LENGTH } from "../notesStore.js";

// The note for one ayah: a ruled-paper text area. Opens below the ayah (above the tafsir, if both are open).
//   Save   -> stores the note and closes the panel (the ayah number then shows a blue dot)
//   Close  -> hides the panel; anything typed is kept as a draft, so reopening restores it
//   Delete -> asks first (inline, no browser pop-up), then removes the note
// Ctrl/Cmd + Enter saves, Esc closes.

function formatWhen(iso) {
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export default function NotesPanel({ ayahNum, saved, draft, storageOk, saveError, onDraft, onSave, onDelete, onClose }) {
  const ref = useRef(null);
  const [confirming, setConfirming] = useState(false);

  const value = draft ?? saved?.text ?? "";
  const dirty = draft !== undefined;
  const canSave = dirty && value.trim().length > 0;

  // Grow with the text so the whole note is always visible (min height = about 5 ruled lines).
  const grow = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 160)}px`;
  };
  useEffect(grow, [value]);

  // Start typing straight away, with the cursor at the end of any existing note.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  const onKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && canSave) { e.preventDefault(); onSave(value); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  const status = dirty ? "Unsaved changes" : saved ? `Saved ${formatWhen(saved.updated)}` : "Not saved yet";

  return (
    <section className="notes-panel" aria-label={`Your note for ayah ${ayahNum}`}>
      <header className="notes-head">
        <span className="notes-title">Your note <span>· Ayah {ayahNum}</span></span>
        <span className={"notes-status" + (dirty ? " dirty" : "")} aria-live="polite">{status}</span>
      </header>

      <textarea
        ref={ref}
        className="notes-paper"
        dir="auto"
        value={value}
        maxLength={MAX_NOTE_LENGTH}
        placeholder="Write what you notice: a root, how a word is used, something from the tafsir..."
        aria-label={`Your note for ayah ${ayahNum}`}
        onChange={(e) => onDraft(e.target.value)}
        onKeyDown={onKeyDown}
      />

      {!storageOk && (
        <p className="notes-warning" role="alert">
          This browser is blocking storage (private mode?), so notes will be lost when you close the page.
          Use "Download my notes" to keep a copy.
        </p>
      )}
      {saveError && <p className="notes-warning" role="alert">{saveError}</p>}

      <footer className="notes-foot">
        {confirming ? (
          <span className="notes-confirm">
            Delete this note?
            <button className="notes-link danger" onClick={() => { setConfirming(false); onDelete(); onClose(); }}>Yes, delete</button>
            <button className="notes-link" onClick={() => setConfirming(false)}>Keep it</button>
          </span>
        ) : (
          <>
            <button className="btn-royal small" disabled={!canSave} onClick={() => onSave(value)}>Save</button>
            <button className="notes-link" onClick={onClose}>Close</button>
            {saved && <button className="notes-link danger" onClick={() => setConfirming(true)}>Delete</button>}
            <span className="notes-hint">
              {value.length > MAX_NOTE_LENGTH * 0.9
                ? `${value.length} / ${MAX_NOTE_LENGTH}`
                : "Stays in this browser only · Ctrl+Enter to save"}
            </span>
          </>
        )}
      </footer>
    </section>
  );
}
