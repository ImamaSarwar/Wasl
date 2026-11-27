import { useMemo, useState } from "react";
import { getStorage } from "../notesStore.js";
import { loadAttempts } from "../quizStore.js";
import {
  REVIEW_AFTER_DAYS, SKILLS, confusedPairs, revisionList, rootProgress, skillScores, weakestSkill,
} from "../progress.js";

// The learner's progress, worked out from the quiz answers saved in this browser.

const GROUPS = [
  { id: "learned", name: "Learned" },
  { id: "learning", name: "Learning" },
  { id: "revise", name: "To revise" },
];
const LEVEL_NAMES = { easy: "Easy", intermediate: "Intermediate", hard: "Hard" };
const spaced = (root) => [...root].join(" ");

export default function Dashboard({ active, ayahs, totalRoots, onPractise, onOpenRoot, onOpenAyah }) {
  // Read the saved answers again each time the dashboard is opened.
  const attempts = useMemo(() => (active ? loadAttempts(getStorage()) : []), [active]);
  const words = useMemo(
    () => Object.fromEntries(ayahs.flatMap((a) => a.words.map((w) => [w.word_id, { ...w, ayah: a.ayah }]))),
    [ayahs]);
  const [showRoots, setShowRoots] = useState(false);

  if (!active) return null;

  if (!attempts.length) {
    return (
      <div className="dash">
        <section className="card quiz-card quiz-intro">
          <span className="title-ar" lang="ar" dir="rtl">رحلتك</span>
          <h2>Your journey begins here</h2>
          <p className="hint">Take a quiz and your learned roots and revision topics will appear on this page.</p>
          <button className="btn-royal" onClick={onPractise}>Take your first quiz</button>
        </section>
      </div>
    );
  }

  const roots = rootProgress(attempts);
  const count = (status) => roots.filter((r) => r.status === status).length;
  const scores = skillScores(attempts);
  const weak = weakestSkill(scores);
  const revise = revisionList(roots);
  const pairs = confusedPairs(attempts, 3);
  const right = attempts.filter((a) => a.correct).length;
  const firstAyah = (root) => ayahs.find((a) => a.words.some((w) => w.root === root))?.ayah;

  return (
    <div className="dash">
      <section className="card quiz-card quiz-intro">
        <span className="title-ar" lang="ar" dir="rtl">رحلتك</span>
        <h2>Your journey</h2>
        <div className="score"><b>{count("learned")}</b><span>of {totalRoots || "..."}</span></div>
        <p className="dash-lead">roots learned</p>
        <p className="hint">A root counts as learned after two correct answers in a row.</p>
        <dl className="stats">
          <div><dt>Still learning</dt><dd>{count("learning")}</dd></div>
          <div><dt>Questions answered</dt><dd>{attempts.length}</dd></div>
          <div><dt>Answered correctly</dt><dd>{Math.round((right / attempts.length) * 100)}%</dd></div>
        </dl>
      </section>

      <section className="card quiz-card">
        <h3>Revise next</h3>
        {revise.length === 0 && !weak && <p className="hint">Nothing is waiting for revision. Well done.</p>}
        {weak && (
          <div className="focus">
            <div>
              <b>{weak.name}</b>
              <span>{weak.right} of {weak.total} correct so far. The {LEVEL_NAMES[weak.level]} quiz covers this.</span>
            </div>
            <button className="btn-royal" onClick={onPractise}>Take a quiz</button>
          </div>
        )}
        <ul className="rows">
          {revise.map((r) => {
            const word = words[r.wordId];
            const ayah = word?.ayah ?? firstAyah(r.root);
            return (
              <li key={r.root}>
                <span className="row-root" lang="ar" dir="rtl">{spaced(r.root)}</span>
                <span className="row-text">
                  {word && <><bdi className="row-word" lang="ar">{word.arabic}</bdi> {word.gloss}</>}
                  <small>{r.reason === "stale" ? `Not practised for ${REVIEW_AFTER_DAYS} days or more` : "Missed last time"}</small>
                </span>
                {ayah && <button className="notes-link" onClick={() => onOpenRoot(r.root, ayah)}>Study</button>}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="card quiz-card">
        <h3>Your strengths</h3>
        <dl className="breakdown">
          {scores.map((s) => (
            <div key={s.id}>
              <dt>{s.name}</dt>
              <dd className="meter"><span style={{ width: `${s.share * 100}%` }} /></dd>
              <dd className="tally">{s.right}/{s.total}</dd>
            </div>
          ))}
        </dl>
      </section>

      {pairs.length > 0 && (
        <section className="card quiz-card">
          <h3>Easily mixed up</h3>
          <ul className="rows">
            {pairs.map((p) => {
              const word = words[p.wordId];
              const arabic = p.skill === "root";
              return (
                <li key={p.key} className="pair">
                  <div className="pair-head">
                    <span>{SKILLS[p.skill]?.name}{word && <> · <bdi className="row-word" lang="ar">{word.arabic}</bdi></>}</span>
                    {p.count > 1 && <span>{p.count} times</span>}
                  </div>
                  <div className="pair-body">
                    <div><small>Correct</small><bdi className={arabic ? "ar" : undefined}>{p.first}</bdi></div>
                    <div className="picked"><small>You chose</small><bdi className={arabic ? "ar" : undefined}>{p.second}</bdi></div>
                  </div>
                  {word && <button className="notes-link" onClick={() => onOpenAyah(word.ayah)}>See ayah {word.ayah}</button>}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {roots.length > 0 && (
        <section className="card quiz-card">
          <div className="dash-head">
            <h3>Your roots</h3>
            <button className="notes-link" aria-expanded={showRoots} onClick={() => setShowRoots((v) => !v)}>
              {showRoots ? "Hide" : `Show ${roots.length}`}
            </button>
          </div>
          {showRoots && GROUPS.filter((g) => count(g.id) > 0).map((g) => (
            <div className="root-group" key={g.id}>
              <h4>{g.name} <span>{count(g.id)}</span></h4>
              <div className="root-chips">
                {roots.filter((r) => r.status === g.id).map((r) => (
                  <button key={r.root} className={"root-chip " + g.id} lang="ar" dir="rtl"
                          onClick={() => onOpenRoot(r.root, firstAyah(r.root))}>
                    {spaced(r.root)}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      <p className="dash-note">Your progress is saved only in this browser.</p>
    </div>
  );
}
