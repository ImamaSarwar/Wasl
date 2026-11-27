// The one piece of navigation: a quiet two-way switch under the title.
const VIEWS = [
  { id: "read", label: "Read" },
  { id: "practice", label: "Practice" },
];

export default function ViewSwitch({ view, onChange }) {
  return (
    <nav className={"view-switch " + view} aria-label="Sections">
      {VIEWS.map((v) => (
        <button key={v.id} className={view === v.id ? "on" : ""} aria-current={view === v.id ? "page" : undefined}
                onClick={() => onChange(v.id)}>
          {v.label}
        </button>
      ))}
    </nav>
  );
}
