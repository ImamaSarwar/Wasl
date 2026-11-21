"""
Verifier: checks an LLM answer against the evidence (which comes from the database).

Nothing the model says is trusted. An answer passes only if
  * it is valid JSON of the expected shape
  * every ayah it cites (as [67:N] or "ayah N") is in the evidence
  * every claim (ayah, root, lemma, gloss) matches a real word in the database evidence
  * every quoted phrase really appears in the evidence (a gloss or a translation)
  * every number it states is a count/ayah number from the evidence
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
NUMWORDS = {"once": 1, "twice": 2, "thrice": 3, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[.,;:!?]+$", "", s.strip().lower()))


def _gloss_norm(s):
    """Compare glosses ignoring case, wrapping quotes and the dataset's (the) parentheses."""
    s = re.sub(r'["\u201c\u201d()]', "", s or "")
    return _norm(s)


def _lemma_ok(claimed, hits):
    """
    A claimed lemma must be a lemma of one of the root's words in that ayah.
    Exact match (diacritics included) is required, because خَلَقَ (verb) and خَلْق (noun) differ only in
    diacritics. A claim written WITHOUT diacritics is accepted only if it points at exactly one lemma.
    """
    nfc = lambda t: unicodedata.normalize("NFC", t).replace("\u0640", "")
    if any(nfc(claimed) == nfc(h["lemma"] or "") for h in hits):
        return True
    if any(unicodedata.category(c) == "Mn" for c in claimed):
        return False
    return len({h["lemma"] for h in hits if strip_arabic(h["lemma"] or "") == strip_arabic(claimed)}) == 1


def _ayah_int(x):
    try:
        return int(str(x).split(":")[-1])
    except (ValueError, TypeError):
        return None


def _index(intent, evidence):
    """Everything the model is allowed to rely on."""
    idx = {"ayahs": set(), "hits": {}, "counts": set(), "texts": []}
    if intent == "semantic":
        for a in evidence:
            idx["ayahs"].add(a["ayah"])
            idx["texts"].append(a["translation"])
        return idx
    for ev in evidence:
        idx["counts"].add(ev["total"])
        for f in ev["forms"]:
            idx["counts"].add(f["count"])
            idx["texts"] += f.get("glosses", [])
        for a in ev["ayahs"]:
            idx["ayahs"].add(a["ayah"])
            idx["texts"].append(a["translation"])
            for h in a["hits"]:
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


def check(raw, intent, evidence):
    """-> (data or None, [error strings]). Empty error list means the answer passed."""
    data = generate.parse(raw)
    if data is None:
        return None, ["the reply was not valid JSON (reply with the JSON object only)"]
    if not isinstance(data.get("refuse"), bool) or not isinstance(data.get("answer"), str) \
            or not isinstance(data.get("claims", []), list):
        return data, ['the JSON must have "refuse" (true/false), "answer" (text) and "claims" (list)']
    if data["refuse"]:
        return data, []

    idx, errors, answer = _index(intent, evidence), [], data["answer"]
    allowed = ", ".join(map(str, sorted(idx["ayahs"])))

    cites = cited_ayahs({"answer": answer})
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

    texts = _norm(" | ".join(idx["texts"]))
    for m in QUOTED.finditer(answer):
        phrase = _norm(m.group(1) or m.group(2))
        if phrase and phrase not in texts:
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

    if RULING.search(answer):
        errors.append("the answer contains a religious ruling; this tool covers vocabulary only")
    return data, errors
