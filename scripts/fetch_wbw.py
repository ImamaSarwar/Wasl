"""
Fetch word-by-word English meanings for Surah 67 and write data/glosses.csv.

    python scripts/fetch_wbw.py                       # download from the Quran.com API
    python scripts/fetch_wbw.py --from-file saved.json  # use a JSON you saved from the API yourself
    python scripts/fetch_wbw.py --force               # write even if some Arabic words don't match

Then rebuild the database:  python scripts/build_db.py

Safety checks (nothing is written if they fail):
  1. every ayah must have exactly as many words as our database (the 'end of ayah' marker is ignored)
  2. the Arabic of every word must match ours once diacritics are stripped (reported; --force overrides)
The raw download is kept as data/raw/wbw-en.json and is never edited.
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
from rag.resolve import strip_arabic  # noqa: E402

DB = ROOT_DIR / "data" / "quran.db"
RAW = ROOT_DIR / "data" / "raw" / "wbw-en.json"
OUT = ROOT_DIR / "data" / "glosses.csv"
URL = ("https://api.quran.com/api/v4/verses/by_chapter/67?language=en&words=true"
       "&word_fields=text_imlaei,text_uthmani&per_page=50")
SOURCE = "Quran.com API v4 word-by-word (en)"


def clean(text):
    """Remove HTML tags and extra spaces from a gloss."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def convert(payload, db_words):
    """
    payload: parsed API JSON. db_words: {(ayah, pos): arabic}.
    Returns (rows, fatal, warnings); rows = [(ayah, pos, gloss)].
    """
    rows, fatal, warnings = [], [], []
    verses = payload.get("verses", [])
    seen = set()
    for v in verses:
        key = v.get("verse_key") or f"67:{v.get('verse_number')}"
        ayah = int(key.split(":")[1])
        seen.add(ayah)
        words = [w for w in v.get("words", []) if w.get("char_type_name") != "end"]
        ours = sorted(p for (a, p) in db_words if a == ayah)
        if len(words) != len(ours):
            fatal.append(f"ayah {ayah}: API has {len(words)} words, database has {len(ours)}")
            continue
        for w, pos in zip(sorted(words, key=lambda x: x["position"]), ours):
            gloss = clean((w.get("translation") or {}).get("text"))
            api_ar = w.get("text_imlaei") or w.get("text_uthmani") or w.get("text") or ""
            if strip_arabic(api_ar) != strip_arabic(db_words[(ayah, pos)]):
                warnings.append(f"{ayah}:{pos} Arabic differs: API '{api_ar}' vs ours '{db_words[(ayah, pos)]}'")
            if not gloss:
                warnings.append(f"{ayah}:{pos} empty meaning")
            rows.append((ayah, pos, gloss))
    missing = sorted({a for a, _ in db_words} - seen)
    if missing:
        fatal.append(f"ayahs missing from the API response: {missing}")
    return rows, fatal, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.from_file:
        payload = json.loads(Path(a.from_file).read_text(encoding="utf-8"))
    else:
        try:
            req = urllib.request.Request(URL, headers={"Accept": "application/json", "User-Agent": "wasl-course-project"})
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.load(r)
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"Could not download from the API: {e}\n"
                             f"Open this URL in your browser, save the page as a .json file and run:\n"
                             f"  python scripts/fetch_wbw.py --from-file <that file>\n{URL}")
        RAW.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    db = sqlite3.connect(DB)
    db_words = {(a_, p): ar for a_, p, ar in db.execute("SELECT ayah, pos, arabic FROM words")}
    db.close()
    rows, fatal, warnings = convert(payload, db_words)

    for w in warnings:
        print("warning:", w)
    if fatal:
        raise SystemExit("NOT WRITTEN:\n  " + "\n  ".join(fatal))
    if warnings and not a.force:
        raise SystemExit(f"\nNOT WRITTEN: {len(warnings)} warning(s) above. Look at them; if they are only spelling "
                         f"differences between Arabic orthographies, re-run with --force.")
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ayah", "pos", "gloss", "source"])
        for ayah, pos, gloss in sorted(rows):
            w.writerow([ayah, pos, gloss, SOURCE])
    print(f"Wrote {OUT.relative_to(ROOT_DIR)}: {len(rows)} glosses. Now run: python scripts/build_db.py")


if __name__ == "__main__":
    main()
