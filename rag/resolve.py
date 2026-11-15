"""
Step 1 of the assistant: turn a free-text question into roots from Surah Al-Mulk.

Pure Python, no LLM, no network. Four ways a root can be named (strongest first):
  arabic   - the root or a word/lemma in Arabic script (diacritics ignored): خلق, خَلَقَ
  latin    - a dashed or plain root: q-d-r, kh-l-q, '-l-m, qdr
  lemma    - a Latin spelling of a word form: khalaqa, khalq
  concept  - an English concept word (see/seeing/sight -> رأي, بصر, عين), from rag/concepts.json

Ambiguous spellings (the same Latin string pointing at two roots) are dropped rather than guessed.
"""
import json
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALIASES = json.loads((HERE / "aliases.json").read_text(encoding="utf-8"))
_CONCEPTS_RAW = json.loads((HERE / "concepts.json").read_text(encoding="utf-8"))

# Latin spellings of the two letters people write as an apostrophe:
#   ayn   ع -> "`" internally  (typed as ʿ ‘ `)
#   hamza أ -> "^" internally  (typed as ʾ ’ ʼ)
#   a plain ' stays "'" = ambiguous, see _lookup_root
_APOS = str.maketrans({**{c: "`" for c in "ʿʻ‘`"}, **{c: "^" for c in "ʾʼ’´"}})


def strip_arabic(s):
    """Remove diacritics, tatweel and stop signs; fold alef/ya variants so spellings compare equal."""
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.replace("ـ", "")
    for a in "إأآٱ":
        s = s.replace(a, "ا")
    return s.replace("ى", "ي").replace("ئ", "ي").replace("ؤ", "و").replace("ة", "ه")


def _fold_root(r):
    """Root letters with all hamza forms folded to one, so أتي, ءتي and اتي compare equal."""
    return strip_arabic(r).replace("ا", "ء").replace("ء", "ا")


def _norm_latin(s):
    return re.sub(r"[^a-z'`^]", "", s.lower().translate(_APOS))


def _norm_lemma(s):
    return re.sub(r"['`^]", "", _norm_latin(s))


def _lookup_root(index, key):
    """A plain ' is ambiguous (ayn or hamza). Following the proposal's '-l-m (= علم) try ayn first."""
    if "'" in key:
        return index.get(key.replace("'", "`")) or index.get(key.replace("'", "^"))
    return index.get(key)


def _unique_index(pairs):
    """{key: root}, keeping only keys that point at exactly one root."""
    seen, bad = {}, set()
    for key, root in pairs:
        if not key:
            continue
        if key in seen and seen[key] != root:
            bad.add(key)
        seen.setdefault(key, root)
    return {k: v for k, v in seen.items() if k not in bad}


def _build_indexes():
    arabic_root = {strip_arabic(r): r for r in ALIASES}
    arabic_lemma = _unique_index(
        (strip_arabic(lem), r) for r, e in ALIASES.items() for lem in e["lemmas"])

    latin_pairs, bare_pairs = [], []
    for r, e in ALIASES.items():
        lat = _norm_latin(e["latin"])
        if len(lat) < 3:
            continue
        bare_pairs.append((lat, r))
        # dashed spellings may also write ayn/hamza as nothing or as "a" (a-l-m, l-m)
        stripped = re.sub(r"[`^]", "", lat)
        for v in {lat, stripped, re.sub(r"[`^]", "a", lat)}:
            latin_pairs.append((v, r))
    latin_root = _unique_index(latin_pairs)
    # bare words ("qdr") only match the exact spelling, so ordinary English words never collide
    bare_root = _unique_index(bare_pairs)

    lemma_latin = _unique_index(
        (_norm_lemma(lat), r) for r, e in ALIASES.items() for lat in e["lemmas"].values()
        if len(_norm_lemma(lat)) >= 4)

    concepts = []
    for keys, roots in _CONCEPTS_RAW.items():
        if keys.startswith("_"):
            continue
        for k in keys.split("|"):
            concepts.append((re.compile(r"\b" + re.escape(k) + r"\b", re.I), k, roots))
    return arabic_root, arabic_lemma, latin_root, bare_root, lemma_latin, concepts


_AR_ROOT, _AR_LEMMA, _LAT_ROOT, _BARE_ROOT, _LAT_LEMMA, _CONCEPTS = _build_indexes()

_DASHED = re.compile(r"(?<![\w'])((?:kh|sh|th|dh|gh|[a-z'ʿʾʻʼ‘’`´])(?:[-–.]\s?(?:kh|sh|th|dh|gh|[a-z'ʿʾʻʼ‘’`´])){2})(?![\w'])", re.I)
# The surah's own name must not be read as the root ملك ("in Surah Al-Mulk").
_SURAH_NAME = re.compile(r"\b(?:surah|sura|surat)\s+(?:al|an)?[-\s]?mulk\b|\bal[-\s]?mulk\b|سورة\s+الملك", re.I)
_ARABIC_TOKEN = re.compile(r"[؀-ۿ]+")
_WORD = re.compile(r"[A-Za-z'ʿʾʻʼ‘’`´]+")


def resolve(question):
    """
    Returns {"direct": [...], "concept": [...]}. Each item: {"root", "via", "matched"}.
    `direct` = the person named a root or a word form; `concept` = only an English concept word.
    Items keep their order of appearance in the question, one entry per root.
    """
    question = _SURAH_NAME.sub(lambda m: " " * len(m.group()), question)  # keep positions stable
    found = {}  # root -> (position, item)

    def add(root, via, matched, pos):
        if root not in found:
            found[root] = (pos, {"root": root, "via": via, "matched": matched})

    for m in _ARABIC_TOKEN.finditer(question):
        tok = strip_arabic(m.group())
        # try the token, then without a leading و/ف/ب/ل/ال prefix (وَالْحَيَاةَ -> حياة)
        for cand in (tok, re.sub(r"^(?:[وفبلك])?(?:ال)?", "", tok)):
            if cand in _AR_ROOT:
                add(_AR_ROOT[cand], "arabic", m.group(), m.start()); break
            if cand in _AR_LEMMA:
                add(_AR_LEMMA[cand], "arabic", m.group(), m.start()); break

    for m in _DASHED.finditer(question):
        key = _norm_latin(m.group(1))
        root = _lookup_root(_LAT_ROOT, key)
        if root:
            add(root, "latin", m.group(1), m.start())

    for m in _WORD.finditer(question):
        w = m.group()
        root = _lookup_root(_BARE_ROOT, _norm_latin(w))
        if root and w.lower() not in _COMMON_WORDS:
            add(root, "latin", w, m.start())
        elif _norm_lemma(w) in _LAT_LEMMA:
            add(_LAT_LEMMA[_norm_lemma(w)], "lemma", w, m.start())

    direct = [it for _, it in sorted(found.values(), key=lambda x: x[0])]
    direct_roots = {it["root"] for it in direct}

    concept_found = {}
    for rx, key, roots in _CONCEPTS:
        m = rx.search(question)
        if m:
            for r in roots:
                if r not in direct_roots and r not in concept_found:
                    concept_found[r] = (m.start(), {"root": r, "via": "concept", "matched": key})
    concept = [it for _, it in sorted(concept_found.values(), key=lambda x: x[0])]
    return {"direct": direct, "concept": concept}


# Plain English words that happen to equal a root's Latin spelling (extend if one shows up).
_COMMON_WORDS = set()
