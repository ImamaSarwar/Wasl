import { useEffect, useRef, useState } from "react";

// A styled replacement for <select>. options: [{ value, label }]
// align="right" opens the list flush with the button's right edge; className adds a size/variant hook.
export default function Dropdown({ value, options, onChange, ariaLabel, className = "", align = "left" }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0); // highlighted row while the list is open
  const root = useRef(null);
  const menu = useRef(null);
  const selectedIndex = Math.max(0, options.findIndex((o) => o.value === value));

  // Click anywhere outside closes the list.
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!root.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  // Keep the highlighted row visible when arrowing through a long list.
  useEffect(() => {
    if (open) menu.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  function openMenu() { setActive(selectedIndex); setOpen(true); }
  function choose(i) { onChange(options[i].value); setOpen(false); }

  function onKeyDown(e) {
    if (e.key === "Escape") { setOpen(false); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) { openMenu(); return; }
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + options.length) % options.length);
    } else if ((e.key === "Enter" || e.key === " ") && open) {
      e.preventDefault();
      choose(active);
    }
  }

  return (
    <div className={"dd " + className} ref={root} onKeyDown={onKeyDown}>
      <button type="button" className="dd-btn" dir="auto" aria-haspopup="listbox" aria-expanded={open} aria-label={ariaLabel}
              onClick={() => (open ? setOpen(false) : openMenu())}>
        {options[selectedIndex]?.label}
      </button>
      {open && (
        <ul className={"dd-menu" + (align === "right" ? " right" : "")} ref={menu} role="listbox" aria-label={ariaLabel}>
          {options.map((o, i) => (
            <li key={o.value} role="option" dir="auto" aria-selected={i === selectedIndex}
                className={i === active ? "active" : ""}
                onMouseEnter={() => setActive(i)} onClick={() => choose(i)}>
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}