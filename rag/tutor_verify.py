"""
Checks a Root Tutor lesson against its evidence (see rag/tutor.py). Each text is checked against the ONE
item it is about, so a grammar term that is true of another form of the same root is still rejected.

Checked: JSON shape and ids, grammar terms, ayah references, quotations, Arabic words, numbers and counts,
rulings / tafsir wording. NOT checked: whether the plain-English wording around a quotation is a faithful
description of the verse. That still needs people to rate sample lessons.

    check(data, evidence) -> (texts or None, [error strings])
"""
import re
import unicodedata

from . import verify
from .resolve import strip_arabic

MAX_CHARS = {"overview": 700, "item": 450}
KIND_FACTS = {"verb", "noun", "adjective", "active participle", "passive participle", "verbal noun"}
ROMAN = {"i": "I", "ii": "II", "iii": "III", "iv": "IV", "v": "V", "vi": "VI", "vii": "VII", "viii": "VIII",
         "ix": "IX", "x": "X"}

# (pattern, facts any one of which makes the term true). An empty set means the database never records it.
# Order matters: longer phrases come first and are removed before shorter ones are looked for.
TERMS = [(re.compile(rf"\b(?:{p})\b"), set(f)) for p, f in (
    (r"active participles?|doer nouns?", ["active participle"]),
    (r"passive participles?|receiver nouns?", ["passive participle"]),
    (r"participles?", ["active participle", "passive participle"]),
    (r"verbal nouns?|masdar", ["verbal noun"]),
    (r"proper (?:nouns?|names?)", ["proper noun"]),
    (r"(?:first|1st)[ -]person", ["first person"]),
    (r"(?:second|2nd)[ -]person", ["second person"]),
    (r"(?:third|3rd)[ -]person", ["third person"]),
    (r"past|perfect|madi", ["past tense"]),
    (r"present|future|imperfect|mudari", ["present / future tense"]),
    (r"commands?|imperative|amr", ["command (imperative)"]),
    (r"passive", ["passive voice", "passive participle"]),
    (r"active", ["active voice"]),
    (r"masculine", ["masculine"]),
    (r"feminine", ["feminine"]),
    (r"singular", ["singular"]),
    (r"plural", ["plural"]),
    (r"dual", ["dual"]),
    (r"nominative|marfu", ["nominative case"]),
    (r"accusative|mansub", ["accusative case"]),
    (r"genitive|majrur", ["genitive case"]),
    (r"indefinite", ["indefinite"]),
    (r"adjectives?|adjectival", ["adjective"]),
    (r"verbs?|verbal", ["verb"]),
    (r"nouns?", ["noun", "verbal noun", "proper noun"]),
    (r"subjects?|objects?|predicates?|mubtada|khabar|idafa|possessive|construct", []),
    (r"definite|jussive|subjunctive|indicative|moods?", []),
    (r"pronouns?|prepositions?|conjunctions?|particles?|prefix(?:es|ed)?|suffix(?:es|ed)?|adverbs?(?:ial)?", []),
    (r"causative|intensive|intensified|reflexive|reciprocal|transitive|intransitive|emphatic", []),
)]
FORM_NO = re.compile(r"\bforms?\s+(viii|vii|vi|iv|ix|iii|ii|i|v|x|10|[1-9])\b")
REF = re.compile(r"\[?\b67:(\d+)\b\]?")
COUNT_WORDS = re.compile(
    r"\b(?:once|twice|thrice|(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|several|many)\s+"
    r"(?:\w+\s+)?(?:times|occurrences|instances|forms|lemmas|ayahs|ayat|verses|words))\b", re.I)
INTERPRET = re.compile(r"\b(?:tafsir|scholars?|theolog\w*|interpret\w*|symboli[sz]\w*)\b", re.I)


ARABIC_TOKEN = re.compile(r"[\u0600-\u06ff]+")


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


def _plain(text):
    """Lower case without transliteration marks: "māḍī" -> "madi"."""
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c) and c not in "ʿʾ'’")


def _grammar_errors(text, allowed_facts):
    errors, t = [], _plain(text)
    for m in FORM_NO.finditer(t):
        n = m.group(1)
        roman = list(ROMAN.values())[int(n) - 1] if n.isdigit() else ROMAN[n]
        if f"Form {roman}" not in allowed_facts:
            errors.append(f"says '{m.group(0)}', which is not a listed fact")
    t = FORM_NO.sub(" ", t)
    for pattern, needed in TERMS:
        found = pattern.search(t)
        if found and not (needed & allowed_facts):
            errors.append(f"uses the grammar term '{found.group(0)}', which is not a listed fact")
        t = pattern.sub(" ", t)
    return errors


def _text_errors(text, *, facts, ayahs, quotable, arabic, limit, need_quote=False):
    errors = []
    if len(text) > limit:
        errors.append(f"is too long (over {limit} characters)")

    quotes = [m.group(1) or m.group(2) for m in verify.QUOTED.finditer(text)]
    sources = [verify._norm(q) for q in quotable]
    for q in quotes:
        phrase = verify._norm(q)
        if phrase and not any(phrase in s for s in sources) and strip_arabic(phrase) not in arabic:
            errors.append(f'quotes "{q}", which is not in the meaning or translation for this item')
    if need_quote and not any(re.search(r"[A-Za-z]{2}", q) and any(verify._norm(q) in s for s in sources)
                              for q in quotes):
        errors.append("must quote the meaning or the translation exactly, inside double quotes")

    outside = verify.QUOTED.sub(" ", text)        # quoted text was checked above
    refs = {int(n) for n in REF.findall(outside)}
    for m in verify.AYAH_WORD.finditer(outside):
        refs |= {int(n) for n in re.findall(r"\d+", m.group(1))}
    for n in sorted(refs - set(ayahs)):
        errors.append(f"refers to ayah {n}, which does not belong to this item")

    for w in _arabic_words(outside):
        if not _arabic_known(w, arabic):
            errors.append(f"writes the Arabic word {w}, which is not in the evidence for this item")

    rest = verify.AYAH_WORD.sub(" ", REF.sub(" ", outside))
    rest = re.sub(r"\b(?:1st|2nd|3rd)\b|\b[Ff]orms?\s+(?:10|[1-9])\b", " ", rest)
    if re.search(r"\d", rest) or COUNT_WORDS.search(rest):
        errors.append("states a number or count; only ayah references are allowed")

    errors += _grammar_errors(outside, facts)
    if verify.RULING.search(outside) or INTERPRET.search(outside):
        errors.append("contains a ruling or interpretation")
    return errors


def _items(data, key, wanted, errors):
    """data[key] -> {id: text}, requiring exactly the wanted ids."""
    got = {}
    rows = data.get(key)
    if not isinstance(rows, list):
        errors.append(f'"{key}" must be a list')
        return got
    for row in rows:
        if not (isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("text"), str)
                and row["text"].strip()):
            errors.append(f'every entry in "{key}" needs an "id" and a non-empty "text"')
        elif row["id"] not in wanted or row["id"] in got:
            errors.append(f'"{key}" has an unknown or repeated id {row["id"]}')
        else:
            got[row["id"]] = row["text"].strip()
    missing = [i for i in wanted if i not in got]
    if missing:
        errors.append(f'"{key}" is missing {", ".join(missing)}')
    return got


def check(data, ev):
    if not isinstance(data, dict) or not isinstance(data.get("overview"), str) or not data["overview"].strip():
        return None, ['reply with one JSON object holding "overview", "forms" and "uses"']
    errors = []
    forms = {f["id"]: f for f in ev["forms"]}
    uses = {u["id"]: u for u in ev["uses"]}
    texts = {"overview": data["overview"].strip(),
             "forms": _items(data, "forms", list(forms), errors),
             "uses": _items(data, "uses", list(uses), errors)}

    def bare(words):
        return {w for text in words for w in _arabic_words(text)}

    root = strip_arabic(ev["root"])
    all_ayah_words = {u["id"]: bare([u["ayah_arabic"]]) for u in ev["uses"]}

    def add(where, found):
        errors.extend(f"{where} {e}" for e in found)

    add("overview", _text_errors(
        texts["overview"],
        facts={x for f in ev["forms"] for x in f["facts"]} & KIND_FACTS,
        ayahs=[u["ayah"] for u in ev["uses"]],
        quotable=[g for f in ev["forms"] for g in f["glosses"]] + [u["translation"] for u in ev["uses"]],
        arabic={root} | bare(ev["lemmas"] + [u["word"] for u in ev["uses"]]),
        limit=MAX_CHARS["overview"]))

    for i, text in texts["forms"].items():
        f = forms[i]
        add(i, _text_errors(
            text, facts=set(f["facts"]), ayahs=f["ayahs"],
            quotable=f["glosses"] + [u["translation"] for u in ev["uses"] if u["form"] == i],
            arabic={root} | bare([f["lemma"]] + f["words"]), limit=MAX_CHARS["item"]))

    for i, text in texts["uses"].items():
        u = uses[i]
        add(i, _text_errors(
            text, facts=set(forms[u["form"]]["facts"]), ayahs=[u["ayah"]],
            quotable=[u["gloss"] or "", u["translation"]],
            arabic={root} | bare([u["word"], u["lemma"]]) | all_ayah_words[i],
            limit=MAX_CHARS["item"], need_quote=True))

    return (None, errors) if errors else (texts, [])