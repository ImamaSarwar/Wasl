"""
Build rag/aliases.json: lets the assistant understand roots typed in Latin letters.

Why: the database stores roots in Arabic script only, but people type "khalaqa" or "q-d-r".
The original Quranic Arabic Corpus file (data/raw/quranic-corpus-morphology-0.4.txt) carries the
same roots and lemmas in Buckwalter transliteration, so we get Latin spellings for free by joining
on (ayah, word number) with the database.

Run from the repo root, after build_db.py:
    python scripts/build_aliases.py
"""
import json
import re
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB = ROOT_DIR / "data" / "quran.db"
CORPUS = ROOT_DIR / "data" / "raw" / "quranic-corpus-morphology-0.4.txt"
OUT = ROOT_DIR / "rag" / "aliases.json"

# Buckwalter -> readable Latin. In *roots*, "A" is hamza (ʾ) and "E" is ayn (ʿ).
ROOT_MAP = {"A": "ʾ", "$": "sh", "*": "dh", "x": "kh", "g": "gh", "E": "ʿ", "H": "h",
            "S": "s", "D": "d", "T": "t", "Z": "z", "v": "th"}
# Lemmas also contain vowels and marks; keep it loose, we only need a searchable spelling.
LEMMA_MAP = {**ROOT_MAP, "A": "a", "Y": "a", "p": "h", "F": "an", "N": "un", "K": "in",
             "{": "a", "|": "a", ">": "a", "<": "i", "&": "u", "}": "i", "`": "a",
             "~": "", "o": "", "^": "", "_": "", "'": ""}


def translit(s, table):
    return "".join(table.get(c, c) for c in s)


def main():
    db = sqlite3.connect(DB)
    ar = {(a, p): (root, lemma) for a, p, root, lemma in
          db.execute("SELECT ayah, pos, root, lemma FROM words WHERE root IS NOT NULL")}
    roots = {}
    for line in open(CORPUS, encoding="utf-8"):
        if not line.startswith("(67:"):
            continue
        loc, _form, _tag, feats = line.rstrip("\n").split("\t")
        _, a, w, _seg = map(int, re.findall(r"\d+", loc))
        m = re.search(r"ROOT:([^|]+)", feats)
        if not m or (a, w) not in ar:
            continue
        root_ar, lemma_ar = ar[(a, w)]
        bw_root = m.group(1)
        lem = re.search(r"LEM:([^|]+)", feats)
        entry = roots.setdefault(root_ar, {"buckwalter": bw_root,
                                           "latin": translit(bw_root, ROOT_MAP), "lemmas": {}})
        if lem:
            entry["lemmas"][lemma_ar] = translit(lem.group(1), LEMMA_MAP)
    # Roots that exist in our DB but not in the original corpus (e.g. the disputed one at 67:2:6):
    # keep them findable by their Arabic spelling and by their lemma, with no Latin root spelling.
    for root_ar, in db.execute("SELECT DISTINCT root FROM words WHERE root IS NOT NULL"):
        roots.setdefault(root_ar, {"buckwalter": None, "latin": "", "lemmas": {}})
    OUT.write_text(json.dumps(roots, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT_DIR)}: {len(roots)} roots")


if __name__ == "__main__":
    main()
