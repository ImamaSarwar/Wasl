// Title of the surah plus the two global listening controls: choose a reciter, and play the whole surah.
export default function ReaderHeader({ reciters, reciterId, onChangeReciter, player, noteCount = 0, onExportNotes }) {
  const listening = player.continuous && player.status !== "idle";

  return (
    <div className="reader-head">
      <div className="reader-title">
        <span className="title-ar" lang="ar" dir="rtl">سورة الملك</span>
        <h2>Surah Al-Mulk</h2>
      </div>

      <div className="reader-actions">
        {noteCount > 0 && (
          <button className="export-btn" onClick={onExportNotes} title="Download all your notes as a text file">
            Export notes ({noteCount})
          </button>
        )}
        {reciters.length > 0 && (
          <>
            <label className="reciter-pick">
              <span>Reciter</span>
              <select value={reciterId || ""} onChange={(e) => onChangeReciter(e.target.value)}>
                {reciters.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </label>
            <button className={"btn-royal" + (listening ? " on" : "")} onClick={listening ? player.stop : player.playSurah}>
              {listening ? "Stop" : "Play surah"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
