import { useLayoutEffect, useRef, useState } from "react";
import { placeCard, shrinkToFit } from "../placeCard.js";

// Floating card shown while hovering a word. Top to bottom:
//   meaning of THIS word (word-by-word translation) -> root letters -> what kind of word it is (plain English)
//   -> for verbs: the past and present/future forms -> the whole ayah's translation.
// The card is measured before it is shown, so that all of it lands on screen (see placeCard.js).
export default function HoverCard({ hover }) {
  if (!hover) return null;
  // The key gives every hovered word a fresh card, so it is measured again.
  return <Card key={`${hover.word.word_id}:${hover.rect.top}:${hover.rect.left}`} {...hover} />;
}

function Card({ word, ayah, rect }) {
  const ref = useRef(null);
  const [wide, setWide] = useState(false); // two columns: shorter, for screens that are not tall enough
  const [pos, setPos] = useState(null);

  useLayoutEffect(() => {
    const card = { width: ref.current.offsetWidth, height: ref.current.offsetHeight };
    const view = { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight };
    const found = placeCard(rect, card, view);
    if (found) setPos(found);
    else if (!wide && view.width >= 680) setWide(true); // measured again in the next pass, before painting
    else setPos(shrinkToFit(rect, card, view));
  }, [wide, rect]);

  const style = pos
    ? { left: pos.left, top: pos.top, transform: pos.scale < 1 ? `scale(${pos.scale})` : undefined }
    : { left: 0, top: 0, visibility: "hidden" };

  const plain = word.plain;
  const tenses = word.tenses;

  return (
    <div ref={ref} className={"hover-card" + (wide ? " wide" : "")} style={style} role="tooltip">
      <div className="hc-col">
        {word.gloss && (
          <div className="hc-meaning">
            <span className="hc-label">Meaning</span>
            {word.gloss}
          </div>
        )}

        {word.root ? (
          <div className="hc-root" dir="rtl" lang="ar">
            {[...word.root].join(" ")}
          </div>
        ) : (
          <div className="hc-noroot">No root (a small linking word)</div>
        )}

        {plain && (
          <div className="hc-kind">
            <b>{plain.kind}</b>
            {plain.hint && <span> - {plain.hint}</span>}
          </div>
        )}

        {plain?.details?.length > 0 && (
          <dl>
            {plain.details.map((d) => (
              <div className="hc-row" key={d.label}>
                <dt>{d.label}</dt>
                <dd>{d.value}</dd>
              </div>
            ))}
          </dl>
        )}

        {word.lemma && word.root && (
          <div className="hc-row hc-lemma">
            <dt>Base form</dt>
            <dd dir="rtl" lang="ar">{word.lemma}</dd>
          </div>
        )}
      </div>
      <div className="hc-col">
        {tenses && (
          <div className="hc-tenses">
            <TenseBox title="Past (māḍī)" sub="he did" data={tenses.past} />
            <TenseBox title="Present / future (muḍāriʿ)" sub="he does" data={tenses.present} />
            <div className="hc-note">Forms as they appear elsewhere in the Qur'an</div>
          </div>
        )}

        <div className="hc-trans">
          <b>Ayah {ayah.ayah}:</b> {ayah.translation}
        </div>
      </div>
    </div>
  );
}

function TenseBox({ title, sub, data }) {
  return (
    <div className="hc-tense">
      <div className="hc-tense-title">
        {title} <span>({sub})</span>
      </div>
      {data?.form ? (
        <>
          <div className="hc-tense-form" dir="rtl" lang="ar">{data.form}</div>
          <div className="hc-tense-ref">e.g. {data.ref}</div>
        </>
      ) : (
        <div className="hc-tense-none">not found in the Qur'an</div>
      )}
    </div>
  );
}
