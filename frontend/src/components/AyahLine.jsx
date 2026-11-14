// One ayah: Arabic words (hoverable/clickable) + English translation underneath.
// Used by both the Reader and the verse drill-down list.
export default function AyahLine({
  ayah,
  selectedRoot,
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
              highlightIds && highlightIds.has(w.word_id) ? "hit" : "",
            ].join(" ");
            return (
              <span key={w.word_id}>
                <span
                  className={cls}
                  onMouseEnter={(e) => onHover(w, ayah, e.currentTarget.getBoundingClientRect())}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => w.root && onWordClick(w.root)}
                >
                  {w.arabic}
                </span>
                {w.trail ? <span className="stop"> {w.trail}</span> : null}{" "}
              </span>
            );
          })}
        </p>
        {showTranslation && <p className="translation">{ayah.translation}</p>}
      </div>
    </div>
  );
}
