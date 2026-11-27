import { useState } from "react";
import { api } from "../api.js";

// "Explain this root": the Root Tutor lesson inside the root explorer (GET /api/roots/{root}/lesson).
// Grammar labels, verses and translations come from the database. The sentences are written by the LLM and
// checked against that data; if that is not possible the backend sends a plain database lesson instead.
// Give this component key={root} so a new root starts closed.
export default function RootLesson({ root, ayahsByNum, onJumpToAyah }) {
  const [lesson, setLesson] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);

  async function explain() {
    setOpen(true);
    setBusy(true);
    setError(null);
    try {
      setLesson(await api.lesson(root));
    } catch {
      setError("Could not load the lesson. Check that the backend is running, then try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="lesson-start">
        <button className="btn-royal" onClick={lesson ? () => setOpen(true) : explain}>Explain this root</button>
      </div>
    );
  }

  const fromModel = lesson?.generated_by === "llm";

  return (
    <div className="lesson" aria-live="polite">
      <div className="lesson-head">
        <h3>Root lesson</h3>
        <button className="notes-link" onClick={() => setOpen(false)}>Close</button>
      </div>

      {busy && <p className="hint">Preparing your lesson...</p>}
      {error && <p className="error">{error} <button className="notes-link" onClick={explain}>Try again</button></p>}

      {lesson && !busy && (
        <>
          <p className="lesson-source">
            {fromModel
              ? "Written by AI from the database and checked automatically. Compare it with the verse."
              : "The AI explanation is unavailable, so this lesson shows the database facts."}
            {!fromModel && <button className="notes-link" onClick={explain}>Try again</button>}
          </p>

          <h4><span>I</span> Word forms</h4>
          <p dir="ltr">{lesson.overview}</p>

          <h4><span>II</span> Grammatical roles</h4>
          {lesson.forms.map((f) => (
            <div className="lesson-item" key={f.id}>
              <div className="lesson-word" lang="ar" dir="rtl">{f.words.join("، ")}</div>
              <p className="lesson-lemma" dir="ltr">Dictionary form: <span lang="ar" dir="rtl">{f.lemma}</span></p>
              <ul className="facts">{f.facts.map((x) => <li key={x}>{x}</li>)}</ul>
              {fromModel && <p dir="ltr">{f.text}</p>}
            </div>
          ))}

          <h4><span>III</span> Use in the verses</h4>
          {lesson.uses.map((u) => (
            <div className="lesson-item" key={u.id}>
              <div className="lesson-word" lang="ar" dir="rtl">{u.word}</div>
              <p dir="ltr">{u.text}</p>
              {u.note && <p className="lesson-note" dir="ltr">{u.note}</p>}
              <p className="lesson-verse" dir="ltr">{ayahsByNum[u.ayah]?.translation}</p>
              <button className="notes-link" onClick={() => onJumpToAyah(u.ayah)}>Go to ayah {u.ayah}</button>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
