// The small control row above each ayah, aligned to the right: Listen (play / pause) and Tafsir (open / close).
// The reciter is chosen once for the whole surah in the header, so this row stays quiet.

const Icon = ({ children }) => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);
const PlayIcon = () => <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>;
const PauseIcon = () => <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z" /></svg>;
const BookIcon = () => <Icon><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" /><path d="M4 19V5.5M8 7h8" /></Icon>;
// Open book with a pen over it: "write your own notes" (the plain book above means "tafsir").
const NotesIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 6.8C9.8 5.4 6.6 4.9 3 5.2v11.6c3.4-.3 6.4.2 9 1.6" />
    <path d="M12 6.8c2.2-1.4 5.4-1.9 9-1.6v4.6" />
    <path d="M12 6.8v11.6" />
    <path d="M13.6 20.4l.7-2.9 6.2-6.2a1.5 1.5 0 0 1 2.1 2.1l-6.2 6.2z" />
    <path d="M19.3 12.5l2.1 2.1" />
  </svg>
);
const ChevronIcon = () => <Icon><path d="M6 9l6 6 6-6" /></Icon>;

export default function AyahToolbar({
  ayahNum, player, hasAudio, hasTafsir, tafsirOpen, onToggleTafsir, hasNotes, notesOpen, onToggleNotes,
}) {
  const mine = player.ayah === ayahNum;
  const status = mine ? player.status : "idle";
  const playing = status === "playing";
  const loading = status === "loading";
  const paused = status === "paused";

  const label = playing ? "Pause" : paused ? "Resume" : loading ? "Loading" : "Listen";

  return (
    <div className="ayah-tools">
      {status === "error" && <span className="tool-error" role="alert">{player.error}</span>}

      {hasAudio && (
        <button
          className={"tool play" + (playing ? " on" : "") + (loading ? " loading" : "")}
          aria-label={`${label} ayah ${ayahNum}`}
          title={`${label} ayah ${ayahNum}`}
          onClick={() => player.toggle(ayahNum)}
        >
          <span className="play-disc">{playing ? <PauseIcon /> : <PlayIcon />}</span>
          <span className="tool-label">{label}</span>
        </button>
      )}

      {hasTafsir && (
        <button
          className={"tool tafsir-btn" + (tafsirOpen ? " on" : "")}
          aria-expanded={tafsirOpen}
          aria-label={`${tafsirOpen ? "Hide" : "Read"} tafsir for ayah ${ayahNum}`}
          onClick={onToggleTafsir}
        >
          <BookIcon />
          <span className="tool-label">Tafsir</span>
          <span className={"chev" + (tafsirOpen ? " up" : "")}><ChevronIcon /></span>
        </button>
      )}

      {hasNotes && (
        <button
          className={"tool notes-btn" + (notesOpen ? " on" : "")}
          aria-expanded={notesOpen}
          aria-label={`${notesOpen ? "Hide" : "Open"} your notes for ayah ${ayahNum}`}
          onClick={onToggleNotes}
        >
          <NotesIcon />
          <span className="tool-label">Notes</span>
          <span className={"chev" + (notesOpen ? " up" : "")}><ChevronIcon /></span>
        </button>
      )}
    </div>
  );
}
