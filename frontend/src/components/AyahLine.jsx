import AyahToolbar from "./AyahToolbar.jsx";
import TafsirPanel from "./TafsirPanel.jsx";

// One ayah: [Listen] [Tafsir] controls (top right), Arabic words (hoverable/clickable),
// transliteration, English translation, and the tafsir panel when opened.
// Used by both the Reader (with `player`) and the verse drill-down list (without it: no controls).
//   selectedRoot : words with this root get a soft highlight
//   clickedId    : the one word the user actually clicked gets a stronger marker
//   highlightIds : (drill-down) words that matched the selected form
//   player       : result of usePlayer(); the word being recited gets the "speaking" highlight
export default function AyahLine({
  ayah,
  selectedRoot,
  clickedId,
  highlightIds,
  onHover,
  onWordClick,
  showTranslation = true,
  player,
  hasAudio = false,
  tafsirSources = [],
  tafsirOpen = false,
  onToggleTafsir,
}) {
  const mine = player && player.ayah === ayah.ayah;
  const active = mine && (player.status === "playing" || player.status === "loading" || player.status === "paused");

  return (
    <div className={"ayah" + (active ? " playing" : "")} id={highlightIds ? undefined : `ayah-${ayah.ayah}`}>
      <div className="ayah-num"><span>{ayah.ayah}</span></div>
      <div className="ayah-body">
        {player && (hasAudio || tafsirSources.length > 0) && (
          <>
            <AyahToolbar
              ayahNum={ayah.ayah}
              player={player}
              hasAudio={hasAudio}
              hasTafsir={tafsirSources.length > 0}
              tafsirOpen={tafsirOpen}
              onToggleTafsir={onToggleTafsir}
            />
            <div className={"ayah-progress" + (active ? " on" : "")} aria-hidden="true">
              <span style={{ width: `${mine ? player.progress * 100 : 0}%` }} />
            </div>
          </>
        )}

        <p className="arabic" dir="rtl" lang="ar">
          {ayah.words.map((w) => {
            const cls = [
              "w",
              w.root ? "has-root" : "no-root",
              selectedRoot && w.root === selectedRoot ? "same-root" : "",
              clickedId === w.word_id ? "clicked" : "",
              highlightIds && highlightIds.has(w.word_id) ? "hit" : "",
              mine && player.status === "playing" && player.word === w.pos ? "speaking" : "",
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

        {tafsirOpen && tafsirSources.length > 0 && (
          <TafsirPanel ayahNum={ayah.ayah} sources={tafsirSources} onClose={onToggleTafsir} />
        )}
      </div>
    </div>
  );
}
