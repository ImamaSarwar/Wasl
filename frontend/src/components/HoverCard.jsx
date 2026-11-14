// Floating card shown while hovering a word: root + lemma + grammar, ayah translation below.
export default function HoverCard({ hover }) {
  if (!hover) return null;
  const { word, ayah, rect } = hover;
  const left = Math.min(Math.max(8, rect.left), window.innerWidth - 340);
  const top = rect.bottom + 8;

  return (
    <div className="hover-card" style={{ left, top }}>
      {word.root ? (
        <>
          <div className="hc-root" dir="rtl" lang="ar">
            {[...word.root].join(" ")}
          </div>
          <dl>
            <dt>Lemma</dt>
            <dd dir="rtl" lang="ar">{word.lemma || "-"}</dd>
            <dt>Type</dt>
            <dd>{word.pos_tag}</dd>
            <dt>Grammar</dt>
            <dd>{word.grammar || "-"}</dd>
            {word.gloss ? (<><dt>Meaning</dt><dd>{word.gloss}</dd></>) : null}
          </dl>
        </>
      ) : (
        <div className="hc-noroot">
          No root <span>({word.pos_tag}: particle / pronoun / etc.)</span>
        </div>
      )}
      <div className="hc-trans">
        <b>Ayah {ayah.ayah}:</b> {ayah.translation}
      </div>
    </div>
  );
}
