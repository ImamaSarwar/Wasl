import { useEffect, useState } from "react";
import Dropdown from "./Dropdown.jsx";

const DownloadIcon = () => (
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3.5v11M7.5 10.5L12 15l4.5-4.5M4.5 16.5v2a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2" />
  </svg>
);
const CheckIcon = () => (
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2.2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </svg>
);

// Title of the surah plus the two global listening controls: choose a reciter, and play the whole surah.
export default function ReaderHeader({ reciters, reciterId, onChangeReciter, player, noteCount = 0, onExportNotes }) {
  const listening = player.continuous && player.status !== "idle";
  const [downloaded, setDownloaded] = useState(false); // brief confirmation after a download

  useEffect(() => {
    if (!downloaded) return;
    const timer = setTimeout(() => setDownloaded(false), 4000);
    return () => clearTimeout(timer);
  }, [downloaded]);

  function download() {
    onExportNotes();
    setDownloaded(true);
  }

  return (
    <div className="reader-head">
      <div className="reader-title">
        <span className="title-ar" lang="ar" dir="rtl">سورة الملك</span>
        <h2>Surah Al-Mulk</h2>
      </div>

      {noteCount > 0 && (
        <button className="export-btn" onClick={download} title="Save all your notes to this device as a text file">
          {downloaded ? <CheckIcon /> : <DownloadIcon />}
          <span aria-live="polite">{downloaded ? "Notes downloaded" : "Download my notes"}</span>
          {!downloaded && <span className="export-count">{noteCount}</span>}
        </button>
      )}
      <div className="reader-actions">
        {reciters.length > 0 && (
          <>
            <div className="reciter-pick">
              <span>Reciter</span>
              <Dropdown
                ariaLabel="Reciter"
                value={reciterId}
                options={reciters.map((r) => ({ value: r.id, label: r.name }))}
                onChange={onChangeReciter}
              />
            </div>
            <button className={"btn-royal" + (listening ? " on" : "")} onClick={listening ? player.stop : player.playSurah}>
              {listening ? "Stop" : "Play surah"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
