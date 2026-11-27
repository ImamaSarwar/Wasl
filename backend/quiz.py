"""
Quiz generator for Surah Al-Mulk. Every question, option, answer key and explanation comes from
data/quran.db. No language model is involved.

    build_quiz("easy" | "intermediate" | "hard", seed=None) -> {"level", "seed", "questions": [...]}

Four question types:
  vocabulary  word -> meaning
  root        word -> root letters
  morphology  verb tense, verb person, or noun case
  contextual  root -> the ayah(s) it appears in. When two shown ayahs are both right, the one correct
              option is "Both A and B".

Rule: every question has exactly ONE correct option.
"""
import random
import re

from . import queries
from .grammar import PERSON

# level -> how many questions of each type
LEVELS = {
    "easy": {"vocabulary": 5, "root": 5},
    "intermediate": {"vocabulary": 5, "root": 5, "morphology": 5},
    "hard": {"vocabulary": 6, "root": 6, "morphology": 6, "contextual": 6},
}

TENSES = {"PERF": "Past (māḍī)", "IMPF": "Present / future (muḍāriʿ)", "IMPV": "Command (amr)"}
CASES = {"NOM": "Nominative (marfūʿ)", "ACC": "Accusative (manṣūb)", "GEN": "Genitive (majrūr)"}
BOTH = "Both A and B"

# Roots whose meanings in this surah are close enough that one could pass for the other. A meaning from
# the same group is never offered as a wrong option. Extend this if a quiz shows a debatable pair.
SIMILAR_ROOTS = [set(g.split()) for g in (
    "رأي بصر",
    "علم خبر عرف عقل",
    "عذب سعر ألم",
    "كفر كذب نكر",
    "خلق فطر ذرأ نشأ جعل",
    "فطر فوت",
    "سمو فوق طبق صفف",
    "رجع قلب صير كرر",
    "ضلل غرر",
    "عتو نفر لجج",
    "رزق أجر أكل",
    "رسل نزل",
    "قول دعو سأل جهر",
    "أتي جيأ",
    "رحم لطف غفر",
    "قدر عزز كبر ملك",
    "صرط نكب مشي",
    "سوي قوم هدي",
    "حشر نشر",
    "دنو زلف عند قبل دون",
    "موت هلك",
    "صدر فأد",
    "جند صحب فوج",
    "بأس سوأ",
    "سرر غيب",
    "جهر بين",
    "غيظ فور",
    "مسك قبض",
)]

_STOPWORDS = set("""a an the of and or so is are was were be been am in on to for with from by at as that
this which who whom his her their your our my its he she it they we you i them him us me will would
could can may might has have had do does did not no then but if every come came""".split())


def _stems(gloss):
    """Rough content-word keys of a meaning: "(the) creation" and "created" both give {"crea"}."""
    return {w[:4] for w in re.findall(r"[a-z]+", gloss.lower()) if w not in _STOPWORDS}


def _similar(root_a, root_b):
    return root_a == root_b or any(root_a in g and root_b in g for g in SIMILAR_ROOTS)


def _load():
    return queries._rows(
        "SELECT w.word_id, w.ayah, w.pos, w.arabic, w.root, w.lemma, w.pos_tag, w.grammar, w.gloss, "
        "a.arabic AS ayah_arabic FROM words w JOIN ayahs a USING(ayah) ORDER BY w.ayah, w.pos")


def _codes(word):
    return set((word["grammar"] or "").split(","))


def _spaced(root):
    return " ".join(root)


def _word_ref(w):
    return {"arabic": w["arabic"], "word_id": w["word_id"], "ayah": w["ayah"]}


def _options(rng, correct, wrong, lang="en"):
    """Shuffle one correct and some wrong options. -> (options, id of the correct one)"""
    texts = [correct] + list(wrong)
    rng.shuffle(texts)
    options = [{"id": "ABCD"[i], "text": t, "lang": lang} for i, t in enumerate(texts)]
    return options, next(o["id"] for o in options if o["text"] == correct)


# ---------- one builder per question type: return a question dict, or None if this word can't make one ----------

def _vocabulary(rng, w, words, level):
    if not w["gloss"]:
        return None
    mine = _stems(w["gloss"])
    pool = [x for x in words if x["root"] and x["gloss"] and not _similar(x["root"], w["root"])]
    rng.shuffle(pool)
    if level != "easy":    # harder: wrong meanings come from the same kind of word (verb / noun)
        pool.sort(key=lambda x: x["pos_tag"] != w["pos_tag"])
    wrong, used_stems, used_roots = [], set(mine), set()
    for x in pool:
        s = _stems(x["gloss"])
        if not s or s & used_stems or x["root"] in used_roots:
            continue
        wrong.append(x["gloss"])
        used_stems |= s
        used_roots.add(x["root"])
        if len(wrong) == 3:
            break
    if len(wrong) < 3:
        return None
    options, answer = _options(rng, w["gloss"], wrong)
    return {"type": "vocabulary", "prompt": "What does this word mean here?", "word": _word_ref(w),
            "options": options, "answer": answer, "root": w["root"], "refs": [w["ayah"]],
            "explanation": f'In ayah {w["ayah"]}, {w["arabic"]} means "{w["gloss"]}". '
                           f'Its root is {_spaced(w["root"])}.'}


def _root(rng, w, words, level):
    others = sorted({x["root"] for x in words if x["root"] and x["root"] != w["root"]})
    rng.shuffle(others)
    if level != "easy":    # harder: wrong roots share letters with the right one
        others.sort(key=lambda r: -len(set(r) & set(w["root"])))
    options, answer = _options(rng, _spaced(w["root"]), [_spaced(r) for r in others[:3]], lang="ar")
    return {"type": "root", "prompt": "Which root does this word come from?", "word": _word_ref(w),
            "options": options, "answer": answer, "root": w["root"], "refs": [w["ayah"]],
            "explanation": f'{w["arabic"]} ("{w["gloss"]}") comes from the root {_spaced(w["root"])}.'}


def _morphology_kinds(w):
    """The grammar questions this word can answer: only features stored for it in the database."""
    codes = _codes(w)
    if w["pos_tag"] == "V":
        kinds = []
        if len(codes & TENSES.keys()) == 1:
            kinds.append("tense")
        if len(codes & PERSON.keys()) == 1:
            kinds.append("person")
        return kinds
    if w["pos_tag"] == "N" and len(codes & CASES.keys()) == 1 and not codes & {"PRON", "REL", "DEM"}:
        return ["case"]
    return []


def _morphology(rng, w, words, level, kind):
    codes = _codes(w)
    if kind == "tense":
        table, prompt = TENSES, "Which verb tense is this word?"
    elif kind == "case":
        table, prompt = CASES, "Which grammatical case is this noun in?"
    else:
        table = {c: f"{plain[0].upper()}{plain[1:]}: {tech}" for c, (plain, tech) in PERSON.items()}
        prompt = "Which person is marked on this verb?"
    code = next(iter(codes & table.keys()))
    if kind == "person":
        # only offer persons that really occur on verbs in this surah
        seen = sorted({c for x in words if x["pos_tag"] == "V" for c in _codes(x) & PERSON.keys()} - {code})
        wrong = rng.sample(seen, 3)
    else:
        wrong = [c for c in table if c != code]
    options, answer = _options(rng, table[code], [table[c] for c in wrong])
    return {"type": "morphology", "kind": kind, "prompt": prompt, "word": _word_ref(w),
            "options": options, "answer": answer, "root": w["root"], "refs": [w["ayah"]],
            "explanation": f'In ayah {w["ayah"]}, {w["arabic"]} ("{w["gloss"]}") is recorded as: {table[code]}.'}


def _contextual(rng, root, words, both):
    hits = sorted({x["ayah"] for x in words if x["root"] == root})
    ayah_text = {x["ayah"]: x["ayah_arabic"] for x in words}
    misses = sorted(set(ayah_text) - set(hits))
    if both:
        if len(hits) < 2:
            return None
        shown = rng.sample(hits, 2) + rng.sample(misses, 1)     # A and B right, C wrong
        answer, right = "D", sorted(shown[:2])
    else:
        correct = rng.choice(hits)
        shown = rng.sample(misses, 2)
        place = rng.randrange(3)
        shown.insert(place, correct)                            # exactly one of A, B, C is right
        answer, right = "ABC"[place], [correct]
    options = [{"id": "ABC"[i], "text": ayah_text[n], "lang": "ar", "ayah": n} for i, n in enumerate(shown)]
    options.append({"id": "D", "text": BOTH, "lang": "en"})
    found = "; ".join(f'ayah {n}: ' + "، ".join(x["arabic"] for x in words if x["root"] == root and x["ayah"] == n)
                      for n in right)
    return {"type": "contextual", "prompt": "Which ayah contains a word from this root?", "word": None,
            "options": options, "answer": answer, "root": root, "refs": right,
            "explanation": f"The root {_spaced(root)} appears in {found}."}


def build_quiz(level, seed=None):
    if level not in LEVELS:
        raise ValueError(f"unknown level '{level}'")
    if seed is None:
        seed = random.randrange(1_000_000_000)
    rng = random.Random(f"{level}:{seed}")
    words = _load()
    rooted = [w for w in words if w["root"]]
    counts = {}
    for w in rooted:
        counts[w["root"]] = counts.get(w["root"], 0) + 1

    questions, used_roots = [], set()   # one question per root, so no question gives away another
    plan = LEVELS[level]

    # contextual first: its "Both A and B" form needs roots found in two or more ayahs
    roots = sorted(counts)
    rng.shuffle(roots)
    for i in range(plan.get("contextual", 0)):
        both = i % 2 == 0
        for root in roots:
            if root in used_roots:
                continue
            q = _contextual(rng, root, words, both)
            if q:
                questions.append(q)
                used_roots.add(root)
                break

    # morphology next (fewest suitable words), taking tense / person / case in turn
    kinds = ["tense", "case", "person"]
    rng.shuffle(kinds)
    for i in range(plan.get("morphology", 0)):
        kind = kinds[i % len(kinds)]
        pool = [w for w in rooted if w["root"] not in used_roots and kind in _morphology_kinds(w)]
        if not pool:
            pool = [w for w in rooted if w["root"] not in used_roots and _morphology_kinds(w)]
            kind = None
        w = rng.choice(pool)
        questions.append(_morphology(rng, w, words, level, kind or _morphology_kinds(w)[0]))
        used_roots.add(w["root"])

    for qtype, builder in (("vocabulary", _vocabulary), ("root", _root)):
        pool = rooted[:]
        rng.shuffle(pool)
        if level == "easy":     # easy: words whose root comes up more than once in the surah
            pool.sort(key=lambda w: counts[w["root"]] < 2)
        made = 0
        for w in pool:
            if made == plan.get(qtype, 0):
                break
            if w["root"] in used_roots:
                continue
            q = builder(rng, w, words, level)
            if q:
                questions.append(q)
                used_roots.add(w["root"])
                made += 1

    rng.shuffle(questions)
    for i, q in enumerate(questions, 1):
        q["id"] = i
    return {"level": level, "seed": seed, "questions": questions}
