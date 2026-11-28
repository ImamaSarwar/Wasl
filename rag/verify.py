"""
Verifier: checks an LLM answer against the evidence (which comes from the database).

Nothing the model says is trusted. An answer passes only if
  * it is valid JSON of the expected shape
  * every ayah it cites (as [67:N] or "ayah N") is in the evidence
  * every claim (ayah, root, lemma, gloss) matches a real word in the database evidence
  * every quoted phrase really appears in the evidence (a gloss or a translation)
  * every number it states is a count/ayah number from the evidence
  * a count is the right KIND of count: "the root occurs N times" must be the root's total, "the form X
    appears N times" that form's own count, "N forms" and "N ayahs" the numbers of forms and ayahs
  * every Arabic word it writes is a word the evidence contains (the root, a lemma, a word of a listed
    ayah, or something the learner typed)
  * it gives no rulings
"""
import re
import unicodedata

from . import generate
from .resolve import strip_arabic

CITE = re.compile(r"\[67:(\d+)\]")
AYAH_WORD = re.compile(r"\b(?:ayah|ayat|verse)s?\s+(\d+(?:\s*(?:,|and|&)\s*\d+)*)", re.I)
QUOTED = re.compile(r'"([^"]{2,})"|“([^”]{2,})”')
COUNT_PHRASE = re.compile(
    r"\b(once|twice|thrice|(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s+(?:times|occurrences|instances|uses))\b", re.I)
RULING = re.compile(r"\b(halal|haram|fatwa|forbidden|permissible|obligatory)\b", re.I)
ARABIC_TOKEN = re.compile(r"[\u0600-\u06ff]+")
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
FORMS_PHRASE = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
                          r"(?:different\s+|distinct\s+)?(?:word\s+)?(?:forms|lemmas)\b", re.I)
AYAHS_PHRASE = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
                          r"(?:different\s+|distinct\s+)?(?:ayahs|ayat|verses)\b", re.I)
NUMWORDS = {"once": 1, "twice": 2, "thrice": 3, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[.,;:!?]+$", "", s.strip().lower()))


_QCH = "\"'\u2018\u2019\u201c\u201d\\"


def _qnorm(s):
    """_norm that also ignores quote marks (and JSON backslashes): a translation that itself contains
    "quotes" is often re-quoted by the model with single quotes."""
    return _norm(re.sub("[" + re.escape(_QCH) + "]", "", s or ""))


def _drop_evidence_quotes(answer, texts):
    """
    Blank out every full evidence translation in the answer (with whatever quote marks surround it), so
    that nested quotes inside a translation cannot pair up wrongly with the quotes around it.
    Short glosses are left alone: only full translations (25+ characters) are removed.
    """
    q = "[" + re.escape(_QCH) + "]*"
    for t in texts:
        if len(t) < 25:
            continue
        pat = q.join(re.escape(part) for part in re.split("[" + re.escape(_QCH) + "]+", t.strip()) if part)
        answer = re.sub(q + pat + q, " ", answer, flags=re.I)
    return answer


def _gloss_norm(s):
    """Compare glosses ignoring case, wrapping quotes and the dataset's (the) parentheses."""
    s = re.sub(r'["\u201c\u201d()]', "", s or "")
    return _norm(s)


def _canon(t):
    """
    Arabic spelling compared the way the dataset writes it. Keeps the vowels that tell words apart
    (خَلَقَ vs خَلْق) but ignores spelling-only variation: a fatha before alif (كَانَ = كانَ), a dagger
    alif (رَحْمٰن = رَحْمَان), alif maqsura vs ya, and tatweel.
    """
    t = unicodedata.normalize("NFC", t).replace("\u0640", "").replace("\u0670", "\u0627")
    t = t.replace("\u0671", "\u0627").replace("\u0649", "\u064a")
    t = re.sub("\u064e(?=\u0627)", "", t)
    t = re.sub("\u0650(?=\u064a)", "", t)
    t = re.sub("\u064f(?=\u0648)", "", t)
    return t


def _lemma_ok(claimed, hits):
    """
    A claimed lemma must be a lemma of one of the root's words in that ayah.
    Exact match (diacritics included) is required, because خَلَقَ (verb) and خَلْق (noun) differ only in
    diacritics. A claim written WITHOUT diacritics is accepted only if it points at exactly one lemma.
    """
    if any(_canon(claimed) == _canon(h["lemma"] or "") for h in hits):
        return True
    if any(unicodedata.category(c) == "Mn" for c in claimed):
        return False
    return len({h["lemma"] for h in hits if strip_arabic(h["lemma"] or "") == strip_arabic(claimed)}) == 1


def _arabic_words(text):
    """The Arabic words in a text, letters only, diacritics and tatweel removed; one-letter tokens skipped."""
    out = []
    for tok in ARABIC_TOKEN.findall(text or ""):
        w = strip_arabic("".join(c for c in tok if unicodedata.category(c).startswith("L")))
        if len(w) >= 2:
            out.append(w)
    return out


def _arabic_known(word, known):
    """A word is known if the evidence has it, with or without a leading و/ف/ب/ل/ك and ال."""
    if word in known:
        return True
    bare = re.sub(r"^[وفبلك]?(?:ال)?", "", word)
    return len(bare) >= 2 and (bare in known or ("ال" + bare) in known)


def _ayah_int(x):
    try:
        return int(str(x).split(":")[-1])
    except (ValueError, TypeError):
        return None


def _index(intent, evidence, extra=None):
    """Everything the model is allowed to rely on."""
    idx = {"ayahs": set(), "hits": {}, "counts": set(), "texts": [], "arabic": set(),
           "ayah_arabic": {}, "evs": []}
    if intent == "semantic":
        for a in evidence:
            idx["ayahs"].add(a["ayah"])
            idx["texts"].append(a["translation"])
            idx["ayah_arabic"][a["ayah"]] = set(_arabic_words(a.get("arabic")))
        return idx
    for a in extra or []:                  # ayahs found by meaning search that came with a root-based answer
        idx["ayahs"].add(a["ayah"])
        idx["texts"].append(a["translation"])
        idx["ayah_arabic"][a["ayah"]] = set(_arabic_words(a.get("arabic")))
    idx["evs"] = list(evidence)
    for ev in evidence:
        idx["counts"] |= {ev["total"], len(ev["forms"]), len(ev["ayahs"])}   # the evidence block states all three
        idx["arabic"].add(strip_arabic(ev["root"]))
        for f in ev["forms"]:
            idx["counts"].add(f["count"])
            idx["arabic"].add(strip_arabic(f["lemma"] or ""))
            idx["arabic"] |= {strip_arabic(w or "") for w in f.get("words", [])}
            idx["texts"] += f.get("glosses", [])
        for a in ev["ayahs"]:
            idx["ayahs"].add(a["ayah"])
            idx["texts"].append(a["translation"])
            idx["ayah_arabic"][a["ayah"]] = set(_arabic_words(a.get("arabic")))
            for h in a["hits"]:
                idx["arabic"] |= {strip_arabic(h["word"] or ""), strip_arabic(h["lemma"] or "")}
                idx["hits"].setdefault((ev["root"], a["ayah"]), []).append(h)
                if h.get("gloss"):
                    idx["texts"].append(h["gloss"])
    return idx


def cited_ayahs(data):
    """Ayah numbers the answer text and claims point at, sorted."""
    found = {int(n) for n in CITE.findall(data.get("answer", ""))}
    for m in AYAH_WORD.findall(data.get("answer", "")):
        found |= {int(n) for n in re.findall(r"\d+", m)}
    for c in data.get("claims") or []:
        if isinstance(c, dict) and _ayah_int(c.get("ayah")) is not None:
            found.add(_ayah_int(c["ayah"]))
    return sorted(found)


def _numval(word):
    return int(word) if word.isdigit() else NUMWORDS.get(word.lower())


def _count_level_errors(answer, idx):
    """Sentence by sentence: a count must be the right kind of count for what the sentence is about."""
    errors = []
    evs = idx["evs"]
    if not evs:
        return errors
    forms_by_word, forms_exact = {}, {}      # lemma (no diacritics / with diacritics) -> counts of such forms
    for ev in evs:
        for f in ev["forms"]:
            forms_by_word.setdefault(strip_arabic(f["lemma"] or ""), set()).add(f["count"])
            forms_exact.setdefault(_canon(f["lemma"] or ""), set()).add(f["count"])
    roots = {strip_arabic(ev["root"]): ev for ev in evs}
    for sent in SENTENCE.split(CITE.sub(" ", answer)):
        words = {w for w in _arabic_words(QUOTED.sub(" ", sent))}
        phrases = list(COUNT_PHRASE.finditer(sent))
        if len(phrases) == 1:
            m = phrases[0]
            word = m.group(2) or m.group(1)
            n = _numval(word)
            allowed = set()
            for tok in ARABIC_TOKEN.findall(QUOTED.sub(" ", sent)):
                w = strip_arabic("".join(c for c in tok if unicodedata.category(c).startswith("L")))
                if len(w) < 2:
                    continue
                if _canon(tok) in forms_exact:          # written with diacritics: names one exact form
                    allowed |= forms_exact[_canon(tok)]
                else:
                    allowed |= forms_by_word.get(w, set())
                if w in roots:
                    allowed.add(roots[w]["total"])
            if not words and len(evs) == 1 and re.search(r"\broot\b", sent, re.I):
                allowed.add(evs[0]["total"])
            if allowed and n is not None and n not in allowed:
                errors.append(f"the answer says '{m.group(0)}' about {'/'.join(sorted(words)) or 'the root'}, "
                              f"but the evidence gives {sorted(allowed)} for that")
        if len(evs) == 1:
            for rx, want, label in ((FORMS_PHRASE, len(evs[0]["forms"]), "forms"),
                                    (AYAHS_PHRASE, len(evs[0]["ayahs"]), "ayahs")):
                for m in rx.finditer(sent):
                    if _numval(m.group(1)) != want:
                        errors.append(f"the answer says '{m.group(0)}', but the evidence has {want} {label}")
    return errors


def _arabic_errors(answer, cites, idx):
    """Arabic words outside quotes must come from the evidence (quoted ones are checked separately)."""
    known = set(idx["arabic"])
    for n in cites:
        known |= idx["ayah_arabic"].get(n, set())
    bad = []
    for w in _arabic_words(QUOTED.sub(" ", answer)):
        if not _arabic_known(w, known) and w not in bad:
            bad.append(w)
    return [f"the answer writes the Arabic word {w}, which is not in the evidence" for w in bad[:3]]


def check(raw, intent, evidence, question=None, extra=None):
    """-> (data or None, [error strings]). Empty error list means the answer passed."""
    data = generate.parse(raw)
    if data is None:
        return None, ["the reply was not valid JSON (reply with the JSON object only)"]
    if not isinstance(data.get("refuse"), bool) or not isinstance(data.get("answer"), str) \
            or not isinstance(data.get("claims", []), list):
        return data, ['the JSON must have "refuse" (true/false), "answer" (text) and "claims" (list)']
    if data["refuse"]:
        return data, []

    idx, errors, answer = _index(intent, evidence, extra), [], data["answer"]
    allowed = ", ".join(map(str, sorted(idx["ayahs"])))

    cites = cited_ayahs(data)           # in the text or in the structured claims
    if not cites:
        errors.append("the answer cites no ayah; cite at least one like [67:3]")
    for n in cites:
        if n not in idx["ayahs"]:
            errors.append(f"the answer cites ayah {n}, which is not in the evidence (allowed: {allowed})")

    for i, c in enumerate(data.get("claims") or [], 1):
        if not isinstance(c, dict):
            errors.append(f"claim {i} is not an object")
            continue
        n = _ayah_int(c.get("ayah"))
        if n is None or n not in idx["ayahs"]:
            errors.append(f"claim {i} names ayah {c.get('ayah')!r}, which is not in the evidence (allowed: {allowed})")
            continue
        root = c.get("root")
        if root is None:
            continue
        hits = idx["hits"].get((root, n))
        if not hits:
            errors.append(f"claim {i}: root {root} does not occur in ayah {n} according to the database")
            continue
        lemma, gloss = c.get("lemma"), c.get("gloss")
        if lemma and not _lemma_ok(lemma, hits):
            errors.append(f"claim {i}: root {root} in ayah {n} has no form with lemma {lemma}")
        if gloss and not any(_gloss_norm(gloss) == _gloss_norm(h.get("gloss") or "") for h in hits):
            errors.append(f'claim {i}: no word of root {root} in ayah {n} has the meaning "{gloss}"')

    texts = _qnorm(" | ".join(idx["texts"]))
    asked = _qnorm(question or "")
    for m in QUOTED.finditer(_drop_evidence_quotes(answer, idx["texts"])):
        phrase = _qnorm(m.group(1) or m.group(2))
        # allowed: a meaning/translation, an Arabic word or lemma from the evidence, or the learner's own words
        if phrase and phrase not in texts and not (asked and phrase in asked) \
                and strip_arabic(phrase) not in idx["arabic"]:
            errors.append(f'the quoted text "{m.group(1) or m.group(2)}" is not a meaning or translation in the evidence')

    if idx["counts"]:
        for m in COUNT_PHRASE.finditer(answer):
            word = m.group(2) or m.group(1)
            n = NUMWORDS.get(word.lower()) if not word.isdigit() else int(word)
            if n not in idx["counts"]:
                errors.append(f"the answer says '{m.group(0)}', but the evidence counts are {sorted(idx['counts'])}")
    stripped = AYAH_WORD.sub(" ", CITE.sub(" ", answer))
    stripped = QUOTED.sub(" ", stripped)
    ok_numbers = idx["counts"] | idx["ayahs"] | {67}
    for n in re.findall(r"\b\d+\b", stripped):
        if int(n) not in ok_numbers:
            errors.append(f"the answer states the number {n}, which is not in the evidence")
            break

    errors += _count_level_errors(answer, idx)
    known_extra = set(_arabic_words(question or ""))
    errors += [e for e in _arabic_errors(answer, cites, idx)
               if not any(w in known_extra for w in _arabic_words(e))]

    if RULING.search(answer):
        errors.append("the answer contains a religious ruling; this tool covers vocabulary only")
    return data, errors
