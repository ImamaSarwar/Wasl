// One ayah: Arabic words (hoverable/clickable), then transliteration, then English translation.
// Used by both the Reader and the verse drill-down list.
//   selectedRoot : words with this root get a soft highlight
//   clickedId    : the one word the user actually clicked gets a stronger marker
//   highlightIds : (drill-down) words that matched the selected form, shown in yellow
export default function AyahLine({
  ayah,
  selectedRoot,
  clickedId,
  highlightIds,
  onHover,
  onWordClick,
  showTranslation = true,
}) {
  return (
    <div className="ayah" id={highlightIds ? undefined : `ayah-${ayah.ayah}`}>
      <div className="ayah-num">{ayah.ayah}</div>
      <div className="ayah-body">
        <p className="arabic" dir="rtl" lang="ar">
          {ayah.words.map((w) => {
            const cls = [
              "w",
              w.root ? "has-root" : "no-root",
              selectedRoot && w.root === selectedRoot ? "same-root" : "",
              clickedId === w.word_id ? "clicked" : "",
              highlightIds && highlightIds.has(w.word_id) ? "hit" : "",
            ].join(" ");
            return (
              <span key={w.word_id}>
                <span
                  className={cls}
                  onMouseEnter={(e) => onHover(w, ayah, e.currentTarget.getBoundingClientRect())}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => w.root && onWordClick(w.root, w.word_id)}
                >
                  {w.arabic}
                </span>
                {w.trail ? <span className="stop"> {w.trail}</span> : null}{" "}
              </span>
            );
          })}
        </p>
        {showTranslation && ayah.transliteration && (
          <p className="translit">{ayah.transliteration}</p>
        )}
        {showTranslation && <p className="translation">{ayah.translation}</p>}
      </div>
    </div>
  );
}
