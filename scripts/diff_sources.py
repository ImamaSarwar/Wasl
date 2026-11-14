"""
List every word in Surah 67 where the original Quranic Arabic Corpus (v0.4) and the cleaned
mustafa0x file disagree on root or lemma. Use the output as your checklist for manual
verification on corpus.quran.com, and log each decision in data/corrections.csv.

Run from the repo root:   python scripts/diff_sources.py
Writes: data/source_diff.csv
"""
import csv
import re
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT = Path(__file__).resolve().parent.parent / "data" / "source_diff.csv"
SURAH = 67

# Buckwalter -> Arabic letters (consonants only; enough for roots)
BW = {"'": "ء", ">": "أ", "&": "ؤ", "<": "إ", "}": "ئ", "A": "ا", "b": "ب", "p": "ة", "t": "ت",
      "v": "ث", "j": "ج", "H": "ح", "x": "خ", "d": "د", "*": "ذ", "r": "ر", "z": "ز", "s": "س",
      "$": "ش", "S": "ص", "D": "ض", "T": "ط", "Z": "ظ", "E": "ع", "g": "غ", "f": "ف", "q": "ق",
      "k": "ك", "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "Y": "ى", "y": "ي"}


def bw_to_ar(s):
    # In the original corpus, a root radical written "A" is a hamza (e.g. Aty = أتي), never a true alif.
    return "".join("أ" if c == "A" else BW.get(c, c) for c in s)


def roots_original():
    d = {}
    for line in open(RAW / "quranic-corpus-morphology-0.4.txt", encoding="utf-8"):
        m = re.match(rf"\({SURAH}:(\d+):(\d+):(\d+)\)\t(\S+)\t(\S+)\t(.*)", line)
        if not m:
            continue
        a, w = int(m[1]), int(m[2])
        r = re.search(r"ROOT:([^|]+)", m[6])
        if r:
            d[(a, w)] = bw_to_ar(r[1])
    return d


def roots_cleaned():
    d = {}
    for line in open(RAW / "quran-morphology.txt", encoding="utf-8"):
        if not line.startswith(f"{SURAH}:"):
            continue
        loc, form, tag, feats = line.rstrip("\n").split("\t")
        _, a, w, _s = map(int, loc.split(":"))
        r = re.search(r"ROOT:([^|]+)", feats)
        if r:
            d[(a, w)] = r[1]
    return d


def main():
    o, c = roots_original(), roots_cleaned()
    rows = []
    for key in sorted(set(o) | set(c)):
        if o.get(key) != c.get(key):
            rows.append({"ayah": key[0], "word": key[1],
                         "original_corpus_root": o.get(key, ""), "mustafa0x_root": c.get(key, "")})
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ayah", "word", "original_corpus_root", "mustafa0x_root"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} root differences written to {OUT.name}")
    for r in rows:
        print(" ", r)


if __name__ == "__main__":
    main()
