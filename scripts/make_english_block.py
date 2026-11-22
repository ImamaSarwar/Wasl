"""
Build rag/english_block.txt: common English words that rag/resolve.py would otherwise read as a roughly
spelled Arabic word form (series -> a form of صرط, laser -> ...).

Needs the dev-only package `wordfreq` (pip install wordfreq). Re-run after rag/aliases.json changes:
    python scripts/make_english_block.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wordfreq import top_n_list, zipf_frequency  # noqa: E402

from rag import resolve  # noqa: E402

MIN_ZIPF = 2.0   # roughly: appears in at least 1 of 100 million words of everyday text


def main():
    resolve.FUZZY = True
    old = set(resolve._BLOCK)
    resolve._BLOCK.clear()          # judge every word on its own, ignoring the old list
    out = []
    for w in top_n_list("en", 300000):
        if len(w) < 5 or not (w.isascii() and w.isalpha()) or zipf_frequency(w, "en") < MIN_ZIPF:
            continue
        q = f'"{w}"'                 # a quoted word passes the context test, so this finds every collision
        if resolve._approx_root(w, q, 1, 1 + len(w)):
            out.append(w)
    path = resolve.HERE / "english_block.txt"
    path.write_text("\n".join(sorted(set(out))) + "\n", encoding="utf-8")
    print(f"wrote {len(set(out))} words to {path} (was {len(old)})")


if __name__ == "__main__":
    main()
