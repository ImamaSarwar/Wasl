"""
Step 1 of the assistant: turn a free-text question into roots from Surah Al-Mulk.

Pure Python, no LLM, no network. Four ways a root can be named (strongest first):
  arabic   - the root or a word/lemma in Arabic script (diacritics ignored): خلق, خَلَقَ
  latin    - a dashed or plain root: q-d-r, kh-l-q, '-l-m, qdr
  lemma    - a Latin spelling of a word form: khalaqa, khalq
  concept  - an English concept word (see/seeing/sight -> رأي, بصر, عين), from rag/concepts.json
  approx   - a rough Latin spelling of a word form (jahar, tibaka, biyadih), see _approx_root

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


_LATIN_FOLD = str.maketrans({"ṣ": "s", "ḥ": "h", "ṭ": "t", "ḍ": "d", "ẓ": "z", "ā": "a", "ī": "i", "ū": "u",
                             "š": "sh", "ḏ": "dh", "ṯ": "th", "ġ": "gh", "ḫ": "kh", "ǧ": "j",
                             "Ṣ": "S", "Ḥ": "H", "Ṭ": "T", "Ḍ": "D", "Ẓ": "Z"})


def _norm_latin(s):
    return re.sub(r"[^a-z'`^]", "", s.translate(_LATIN_FOLD).lower().translate(_APOS))


def _norm_lemma(s):
    """Loose comparison key for a word form: ghafuwr, ghafur and ghafoor all become ghafur."""
    s = re.sub(r"['`^]", "", _norm_latin(s))
    for a, b in (("uw", "u"), ("oo", "u"), ("iy", "i"), ("ee", "i"), ("aa", "a")):
        s = s.replace(a, b)
    return s


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

    # exact spelling of a word form, ayn/hamza marks kept and vowels NOT collapsed: tells ʿaliym (علم)
    # from aliym (ألم) and allows short forms (shaa, aataa, waʿd) that the loose key would drop
    lemma_exact = _unique_index(
        (_norm_latin(lat), r) for r, e in ALIASES.items() for lat in e["lemmas"].values()
        if len(_norm_latin(lat)) >= 4)

    concepts = []
    for keys, roots in _CONCEPTS_RAW.items():
        if keys.startswith("_"):
            continue
        for k in keys.split("|"):
            concepts.append((re.compile(r"\b" + re.escape(k) + r"\b", re.I), k, roots))
    return arabic_root, arabic_lemma, latin_root, bare_root, lemma_latin, lemma_exact, concepts


_AR_ROOT, _AR_LEMMA, _LAT_ROOT, _BARE_ROOT, _LAT_LEMMA, _LAT_EXACT, _CONCEPTS = _build_indexes()

# ---- approximate spelling -------------------------------------------------------------------------
# People type word forms by ear: "Jahar" for jahara, "Tibaka" for tabaq, "biyadih" for bi + yad + ih.
# Two narrow rules, both applied only after every exact rule failed:
#   1. fold q->k and every vowel to "a", then accept a word form at edit distance 1 (len >= 5) when
#      exactly one root is nearest;
#   2. strip a clitic prefix AND suffix (bi-...-hi) and look the rest up as an exact word form.
# English words that fold onto a word form (series, laser, mouse...) are listed in english_block.txt,
# and rule 1 also needs a context that says "this is a foreign word" (quotes, "does X mean", "root of X").
FUZZY = True
_BLOCK = set((HERE / "english_block.txt").read_text(encoding="utf-8").split()) if (HERE / "english_block.txt").exists() else set()
_PRE = ("wal", "bil", "lil", "bi", "wa", "fa", "li", "ka", "al")
_SUF = ("ihi", "hunna", "hum", "kum", "ih", "hi", "hu", "ha", "ka", "ki", "na", "ni", "uh")
_QUOTES = "\"'“”‘’«»`"


def _fold_approx(s):
    s = re.sub(r"['`^]", "", _norm_latin(s)).replace("q", "k")
    return re.sub(r"[aeiou]", "a", s)


def _lev1(a, b):
    """Edit distance, capped: 0, 1, or 2 (meaning 'two or more')."""
    if abs(len(a) - len(b)) > 1:
        return 2
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return min(d[-1], 2)


def _build_fuzzy():
    keys, exact = {}, {}
    for r, e in ALIASES.items():
        for lat in e["lemmas"].values():
            k = _fold_approx(lat)
            if len(k) >= 5:
                keys.setdefault(k, set()).add(r)
            x = re.sub(r"['`^]", "", _norm_latin(lat))
            if len(x) >= 3:
                exact.setdefault(x, set()).add(r)
    return keys, {k: next(iter(v)) for k, v in exact.items() if len(v) == 1}


_FUZZY_KEYS, _CLITIC_EXACT = _build_fuzzy()


def _approx_root(word, question, start, end):
    """Root for a roughly spelled word form, or None. See the block comment above."""
    w = _norm_latin(word)
    if len(w) < 5 or w in _BLOCK or w in _LAT_EXACT:
        return None
    for p in _PRE:                                   # rule 2: bi-yad-ih -> yad
        if w.startswith(p):
            rest = w[len(p):]
            for sfx in _SUF:
                if rest.endswith(sfx) and rest[:-len(sfx)] in _CLITIC_EXACT:
                    return _CLITIC_EXACT[rest[:-len(sfx)]]
    before = question[max(0, start - 24):start].lower()
    after = question[end:end + 16].lower()
    quoted = (start > 0 and question[start - 1] in _QUOTES) or (end < len(question) and question[end] in _QUOTES)
    asked = re.search(r"\b(?:does|do|is|word|term|root|of|by|about|mean(?:s|ing)?)\s*[\"'“‘]?$", before) or \
        re.match(r"[\"'”’]?\s*(?:mean|means|meaning|come|derive|stand)\b", after)
    if not (quoted or asked):
        return None
    f = _fold_approx(w)                              # rule 1
    best, roots = 2, set()
    for k, rs in _FUZZY_KEYS.items():
        d = _lev1(f, k)
        if d < best:
            best, roots = d, set(rs)
        elif d == best and d < 2:
            roots |= rs
    return next(iter(roots)) if best < 2 and len(roots) == 1 else None


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
    question = question.translate(_LATIN_FOLD)
    question = _SURAH_NAME.sub(lambda m: " " * len(m.group()), question)  # keep positions stable
    found = {}  # root -> (position, item)

    def add(root, via, matched, pos):
        if root not in found:
            found[root] = (pos, {"root": root, "via": via, "matched": matched})

    for m in _ARABIC_TOKEN.finditer(question):
        tok = strip_arabic("".join(c for c in m.group() if unicodedata.category(c)[0] in "LM"))
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
        elif _norm_latin(w) in _LAT_EXACT:
            add(_LAT_EXACT[_norm_latin(w)], "lemma", w, m.start())
        elif _norm_lemma(w) in _LAT_LEMMA:
            add(_LAT_LEMMA[_norm_lemma(w)], "lemma", w, m.start())
        elif FUZZY:
            root = _approx_root(w, question, m.start(), m.end())
            if root:
                add(root, "lemma", w, m.start())

    direct = [it for _, it in sorted(found.values(), key=lambda x: x[0])]
    # "Allah" is usually the subject of a question ("which verses mention Allah showing mercy"), not the word
    # being asked about. If a concept word is also present and the question is not about the word itself
    # (root / word / form / meaning / how often), do not let the name hijack the root route.
    if len(direct) == 1 and direct[0]["via"] == "lemma" and direct[0]["matched"].lower() == "allah" \
            and not _WORD_FOCUS.search(question) and any(rx.search(question) for rx, _, _ in _CONCEPTS):
        direct = []
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


# The question is about the word itself, not about its topic.
_WORD_FOCUS = re.compile(r"\b(?:roots?|words?|lemmas?|forms?|spell(?:ed|ing)?|mean(?:s|ing)?|"
                         r"appear(?:s|ed)?|occur(?:s|red)?|times|how (?:many|often)|count|derive[sd]?)\b", re.I)

# Plain English words that happen to equal a root's Latin spelling (extend if one shows up).
_COMMON_WORDS = set()
