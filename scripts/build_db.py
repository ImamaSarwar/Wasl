"""
Build data/quran.db (SQLite) for Surah Al-Mulk (67) from the raw Tanzil + morphology files.

Run from the repo root:
    python scripts/build_db.py

What it does
  1. Reads data/raw/quran-simple.txt, en.sahih.txt, quran-morphology.txt (never modified).
  2. Drops the bismillah Tanzil prepends to ayah 1.
  3. Splits ayah text into words; stop-sign tokens (e.g. ۖ ۚ) are kept as `trail` on the previous
     word so the displayed Arabic is identical to Tanzil's.
  4. Aligns words with morphology by (ayah, word number) and refuses to build if they disagree.
  5. Applies manual fixes from data/corrections.csv (your verification log).
"""
import csv
import collections
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW = ROOT_DIR / "data" / "raw"
DB_PATH = ROOT_DIR / "data" / "quran.db"
CORRECTIONS = ROOT_DIR / "data" / "corrections.csv"

SURAH = 67
N_AYAHS = 30
BISMILLAH_TOKENS = 4  # Tanzil prepends it to ayah 1 of every surah except 1 and 9
EDITABLE_FIELDS = {"root", "lemma", "pos_tag", "grammar", "gloss", "verified"}


def has_letter(token):
    return any(unicodedata.category(c).startswith("L") for c in token)


def load_tanzil(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        s, a, text = line.rstrip("\n").split("|", 2)
        if int(s) == SURAH:
            d[int(a)] = text
    return d


def load_morph(path):
    """Returns {(ayah, word_no): [segment dicts]} for the surah."""
    words = collections.defaultdict(list)
    for line in open(path, encoding="utf-8"):
        if not line.startswith(f"{SURAH}:"):
            continue
        loc, form, tag, feats = line.rstrip("\n").split("\t")
        _, a, w, seg = map(int, loc.split(":"))
        kv, flags = {}, []
        for f in feats.split("|"):
            if ":" in f:
                k, v = f.split(":", 1)
                kv[k] = v
            else:
                flags.append(f)
        words[(a, w)].append(dict(seg=seg, form=form, tag=tag, root=kv.get("ROOT"),
                                  lemma=kv.get("LEM"), vform=kv.get("VF"),
                                  flags=flags, raw=feats))
    return words


def split_words(text, ayah):
    """-> list of (word, trail). Stop signs become the trail of the preceding word."""
    tokens = text.split()
    if ayah == 1:
        tokens = tokens[BISMILLAH_TOKENS:]
    out = []
    for t in tokens:
        if has_letter(t) or not out:
            out.append([t, ""])
        else:
            out[-1][1] += (" " if out[-1][1] else "") + t
    return out


SCHEMA = """
CREATE TABLE ayahs(
    ayah INTEGER PRIMARY KEY,
    arabic TEXT NOT NULL,
    translation TEXT NOT NULL
);
CREATE TABLE words(
    word_id INTEGER PRIMARY KEY,
    ayah INTEGER NOT NULL REFERENCES ayahs(ayah),
    pos INTEGER NOT NULL,
    arabic TEXT NOT NULL,
    trail TEXT NOT NULL DEFAULT '',
    root TEXT,
    lemma TEXT,
    pos_tag TEXT,
    grammar TEXT,
    gloss TEXT,
    verified INTEGER NOT NULL DEFAULT 0,
    UNIQUE(ayah, pos)
);
CREATE TABLE segments(
    seg_id INTEGER PRIMARY KEY,
    word_id INTEGER NOT NULL REFERENCES words(word_id),
    seg INTEGER, form TEXT, tag TEXT, root TEXT, lemma TEXT, features TEXT
);
CREATE INDEX idx_words_root  ON words(root);
CREATE INDEX idx_words_lemma ON words(lemma);
CREATE INDEX idx_words_ayah  ON words(ayah);
"""


def apply_corrections(db):
    if not CORRECTIONS.exists():
        return 0
    n = 0
    with open(CORRECTIONS, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("ayah") or row["ayah"].startswith("#"):
                continue
            field = row["field"].strip()
            if field not in EDITABLE_FIELDS:
                raise SystemExit(f"corrections.csv: field '{field}' not allowed ({sorted(EDITABLE_FIELDS)})")
            value = row["new_value"].strip() or None
            cur = db.execute(f"UPDATE words SET {field}=? WHERE ayah=? AND pos=?",
                             (value, int(row["ayah"]), int(row["pos"])))
            if cur.rowcount != 1:
                raise SystemExit(f"corrections.csv: no word at ayah {row['ayah']} pos {row['pos']}")
            n += 1
    return n


def main():
    ar = load_tanzil(RAW / "quran-simple.txt")
    en = load_tanzil(RAW / "en.sahih.txt")
    morph = load_morph(RAW / "quran-morphology.txt")
    assert len(ar) == N_AYAHS and len(en) == N_AYAHS, "expected 30 ayahs in each text file"

    if DB_PATH.exists():
        DB_PATH.unlink()
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)

    problems = []
    for a in range(1, N_AYAHS + 1):
        words = split_words(ar[a], a)
        shown = " ".join(w + (" " + t if t else "") for w, t in words)
        db.execute("INSERT INTO ayahs VALUES (?,?,?)", (a, shown, en[a]))
        n_morph = len([k for k in morph if k[0] == a])
        if len(words) != n_morph:
            problems.append(f"ayah {a}: {len(words)} text words vs {n_morph} morphology words")
            continue
        for i, (tok, trail) in enumerate(words, start=1):
            segs = sorted(morph[(a, i)], key=lambda s: s["seg"])
            stem = (next((s for s in segs if s["root"]), None)
                    or next((s for s in segs if "PREF" not in s["flags"]), segs[0]))
            grammar = ",".join(f for f in stem["flags"] if f != "P")
            if stem["vform"]:
                grammar += f",form {stem['vform']}"
            cur = db.execute(
                "INSERT INTO words(ayah,pos,arabic,trail,root,lemma,pos_tag,grammar) VALUES (?,?,?,?,?,?,?,?)",
                (a, i, tok, trail, stem["root"], stem["lemma"], stem["tag"], grammar))
            for s in segs:
                db.execute(
                    "INSERT INTO segments(word_id,seg,form,tag,root,lemma,features) VALUES (?,?,?,?,?,?,?)",
                    (cur.lastrowid, s["seg"], s["form"], s["tag"], s["root"], s["lemma"], s["raw"]))

    if problems:
        db.close()
        DB_PATH.unlink()
        raise SystemExit("ALIGNMENT PROBLEMS, DB not built:\n  " + "\n  ".join(problems))

    n_fix = apply_corrections(db)
    db.commit()

    one = lambda sql: db.execute(sql).fetchone()[0]
    print(f"Built {DB_PATH.relative_to(ROOT_DIR)}")
    print(f"  ayahs: {one('select count(*) from ayahs')}")
    print(f"  words: {one('select count(*) from words')}")
    print(f"  words with a root: {one('select count(*) from words where root is not null')}")
    print(f"  distinct roots: {one('select count(distinct root) from words')}")
    print(f"  corrections applied: {n_fix}")
    db.close()


if __name__ == "__main__":
    sys.exit(main())
