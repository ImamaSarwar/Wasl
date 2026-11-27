import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { getStorage } from "../notesStore.js";
import { makeAttempt, saveAttempt } from "../quizStore.js";

// The practice area: choose a level -> answer one question at a time -> see the result.
// Questions and answer keys come from the database (GET /api/quiz); no language model is involved.

const LEVELS = [
  { id: "easy", numeral: "I", name: "Easy", count: 10, about: "Word meanings and roots" },
  { id: "intermediate", numeral: "II", name: "Intermediate", count: 15, about: "Meanings, roots and grammar" },
  { id: "hard", numeral: "III", name: "Hard", count: 24, about: "Meanings, roots, grammar and verses in context" },
];
const TYPE_NAMES = { vocabulary: "Vocabulary", root: "Root", morphology: "Grammar", contextual: "Context" };

export default function Quiz({ ayahsByNum, onOpenAyah }) {
  const [quiz, setQuiz] = useState(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState([]); // chosen option id per question
  const [loading, setLoading] = useState(null);
  const [error, setError] = useState(null);
  const top = useRef(null);

  async function start(level) {
    setLoading(level);
    setError(null);
    try {
      const next = await api.quiz(level);
      setQuiz(next);
      setIndex(0);
      setAnswers([]);
    } catch {
      setError("Could not load the quiz. Check that the backend is running, then try again.");
    } finally {
      setLoading(null);
    }
  }

  // Bring the top of the card back into view when the screen changes.
  useEffect(() => {
    if (top.current?.getBoundingClientRect().top < 0) top.current.scrollIntoView({ block: "start" });
  }, [index, quiz]);

  function choose(id) {
    if (answers[index]) return; // one answer per question
    setAnswers((prev) => { const next = [...prev]; next[index] = id; return next; });
    saveAttempt(getStorage(), makeAttempt(quiz.level, quiz.questions[index], id));
  }

  let screen;
  if (!quiz) {
    screen = <LevelPicker onStart={start} loading={loading} />;
  } else if (index >= quiz.questions.length) {
    screen = <Result quiz={quiz} answers={answers} loading={loading} onRetry={() => start(quiz.level)}
                     onChangeLevel={() => setQuiz(null)} onOpenAyah={onOpenAyah} />;
  } else {
    screen = <Question key={`${quiz.seed}-${index}`} quiz={quiz} index={index} chosen={answers[index]}
                       ayahsByNum={ayahsByNum} onChoose={choose} onNext={() => setIndex(index + 1)}
                       onQuit={() => setQuiz(null)} onOpenAyah={onOpenAyah} />;
  }

  return (
    <div className="quiz" ref={top}>
      {error && <p className="error banner" role="alert">{error}</p>}
      {screen}
    </div>
  );
}

function LevelPicker({ onStart, loading }) {
  return (
    <section className="card quiz-card quiz-intro">
      <span className="title-ar" lang="ar" dir="rtl">اختبر نفسك</span>
      <h2>Test your understanding</h2>
      <p className="hint">Multiple-choice questions drawn from Surah Al-Mulk. Choose a level to begin.</p>
      <div className="levels">
        {LEVELS.map((l) => (
          <button key={l.id} className="level" onClick={() => onStart(l.id)} disabled={!!loading}>
            <span className="level-numeral" aria-hidden="true">{l.numeral}</span>
            <span className="level-name">{l.name}</span>
            <span className="level-about">{l.about}</span>
            <span className="level-count">{loading === l.id ? "Preparing..." : `${l.count} questions`}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

// The ayah with the words of interest marked.
function Verse({ ayah, wordId, root }) {
  if (!ayah) return null;
  return (
    <p className="arabic verse" dir="rtl" lang="ar">
      {ayah.words.map((w) => (
        <span key={w.word_id}
              className={w.word_id === wordId || (root && w.root === root) ? "marked" : undefined}>
          {w.arabic}{w.trail ? ` ${w.trail}` : ""}{" "}
        </span>
      ))}
    </p>
  );
}

function Question({ quiz, index, chosen, ayahsByNum, onChoose, onNext, onQuit, onOpenAyah }) {
  const q = quiz.questions[index];
  const total = quiz.questions.length;
  const done = !!chosen;
  const right = chosen === q.answer;
  const level = LEVELS.find((l) => l.id === quiz.level);
  const next = useRef(null);
  useEffect(() => { if (done) next.current?.focus({ preventScroll: true }); }, [done]);

  // "Both A and B" is right: A and B are then correct too, so show them that way.
  const bothRight = q.type === "contextual" && q.answer === "D";
  const stateOf = (id) => {
    if (!done) return "";
    if (id === q.answer || (bothRight && (id === "A" || id === "B"))) return " correct";
    return id === chosen ? " wrong" : " dim";
  };

  return (
    <section className="card quiz-card">
      <div className="quiz-top">
        <span>{level.name} <i>·</i> {TYPE_NAMES[q.type]}</span>
        <span>{index + 1} of {total}</span>
        <button className="notes-link" onClick={onQuit}>Leave quiz</button>
      </div>
      <div className="quiz-progress" role="progressbar" aria-valuemin="0" aria-valuemax={total}
           aria-valuenow={index + (done ? 1 : 0)}>
        <span style={{ width: `${((index + (done ? 1 : 0)) / total) * 100}%` }} />
      </div>

      <h2 className="quiz-prompt">{q.prompt}</h2>
      {q.word ? (
        <div className="quiz-subject">
          <div className="quiz-word" dir="rtl" lang="ar">{q.word.arabic}</div>
          <div className="quiz-ref">Ayah {q.word.ayah}</div>
        </div>
      ) : (
        <div className="quiz-subject">
          <div className="quiz-word spaced" dir="rtl" lang="ar">{[...q.root].join(" ")}</div>
          <div className="quiz-ref">If two answers are right, choose "Both A and B".</div>
        </div>
      )}

      <div className={"options" + (q.type === "contextual" ? " verses" : "")}>
        {q.options.map((o) => (
          <button key={o.id} className={"option" + stateOf(o.id) + (o.id === chosen ? " picked" : "")}
                  onClick={() => onChoose(o.id)} aria-disabled={done} aria-pressed={o.id === chosen}>
            <span className="option-key">{o.id}</span>
            <span className={"option-text" + (o.lang === "ar" ? " ar" : "")} lang={o.lang}
                  dir={o.lang === "ar" ? "rtl" : "ltr"}>
              {o.text}
              {done && o.ayah && <small dir="ltr" lang="en">Ayah {o.ayah}</small>}
            </span>
          </button>
        ))}
      </div>

      {done && (
        <div className={"feedback" + (right ? " good" : " bad")} role="status">
          <h3>{right ? "Correct" : "Not quite"}</h3>
          <p dir="ltr">{q.explanation}</p>
          {q.refs.map((n) => (
            <div className="feedback-verse" key={n}>
              <Verse ayah={ayahsByNum[n]} wordId={q.word?.word_id} root={q.word ? null : q.root} />
              <p className="translation">{ayahsByNum[n]?.translation}</p>
              <button className="notes-link" onClick={() => onOpenAyah(n)}>Open ayah {n} in the reader</button>
            </div>
          ))}
        </div>
      )}

      {done && (
        <div className="quiz-foot">
          <button ref={next} className="btn-royal" onClick={onNext}>
            {index + 1 === total ? "See result" : "Next question"}
          </button>
        </div>
      )}
    </section>
  );
}

function Result({ quiz, answers, loading, onRetry, onChangeLevel, onOpenAyah }) {
  const qs = quiz.questions;
  const isRight = (q, i) => answers[i] === q.answer;
  const score = qs.filter(isRight).length;
  const missed = qs.map((q, i) => ({ q, i })).filter(({ q, i }) => !isRight(q, i));
  const types = Object.keys(TYPE_NAMES).filter((t) => qs.some((q) => q.type === t));

  return (
    <section className="card quiz-card quiz-result">
      <h3>{LEVELS.find((l) => l.id === quiz.level).name} quiz complete</h3>
      <div className="score"><b>{score}</b><span>of {qs.length}</span></div>

      <dl className="breakdown">
        {types.map((t) => {
          const mine = qs.map((q, i) => [q, i]).filter(([q]) => q.type === t);
          const ok = mine.filter(([q, i]) => isRight(q, i)).length;
          return (
            <div key={t}>
              <dt>{TYPE_NAMES[t]}</dt>
              <dd className="meter"><span style={{ width: `${(ok / mine.length) * 100}%` }} /></dd>
              <dd className="tally">{ok}/{mine.length}</dd>
            </div>
          );
        })}
      </dl>

      <div className="quiz-foot centre">
        <button className="btn-royal" onClick={onRetry} disabled={!!loading}>New {quiz.level} quiz</button>
        <button className="btn-royal on" onClick={onChangeLevel}>Change level</button>
      </div>

      {missed.length > 0 && (
        <div className="review">
          <h3>To revise</h3>
          <ul>
            {missed.map(({ q }) => (
              <li key={q.id}>
                <p dir="ltr">{q.explanation}</p>
                {q.refs.map((n) => (
                  <button key={n} className="notes-link" onClick={() => onOpenAyah(n)}>Ayah {n}</button>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
