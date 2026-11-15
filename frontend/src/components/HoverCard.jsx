// Floating card shown while hovering a word. Top to bottom:
//   meaning of THIS word (word-by-word translation) -> root letters -> what kind of word it is (plain English)
//   -> for verbs: the past and present/future forms -> the whole ayah's translation.
export default function HoverCard({ hover }) {
  if (!hover) return null;
  const { word, ayah, rect } = hover;

  const left = Math.min(Math.max(8, rect.left), window.innerWidth - 380);
  // Open upwards when the word is in the lower part of the screen so the card never runs off the page.
  const above = rect.bottom > window.innerHeight * 0.55;
  const pos = above
    ? { left, bottom: window.innerHeight - rect.top + 8 }
    : { left, top: rect.bottom + 8 };

  const plain = word.plain;
  const tenses = word.tenses;

  return (
    <div className="hover-card" style={pos}>
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
