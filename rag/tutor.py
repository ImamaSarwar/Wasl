"""
Root Tutor: a short lesson on one root of Surah Al-Mulk, in three parts:
  1. how the root produces its word forms   (overview)
  2. the grammatical role of each form      (forms)
  3. how each occurrence is used in its verse (uses)

    lesson("خلق", use_llm=True) -> dict, or None if the root does not occur in the surah

The root is already known (the learner picked it), so no search is needed:
  database -> evidence with ids (F1.. for forms, W<word_id> for occurrences) -> Gemini writes one text per id
  -> rag/tutor_verify.py checks each text against ITS evidence item -> one retry -> database-only lesson.

Grammar facts come only from words.pos_tag / words.grammar. The model never supplies them, it only words them,
and the app shows the database facts as labels next to its text.
"""
import re

from . import generate, llm, tutor_verify
from .evidence import root_evidence
from backend import queries

PERSON_WORDS = {"1": "first person", "2": "second person", "3": "third person"}
GENDER_WORDS = {"M": "masculine", "F": "feminine"}
NUMBER_WORDS = {"S": "singular", "P": "plural", "D": "dual"}
SIMPLE_FACTS = {"PERF": "past tense", "IMPF": "present / future tense", "IMPV": "command (imperative)",
                "NOM": "nominative case", "ACC": "accusative case", "GEN": "genitive case",
                "INDEF": "indefinite", "ADJ": "adjective", "ACT_PCPL": "active participle",
                "PASS_PCPL": "passive participle", "VN": "verbal noun", "PN": "proper noun"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

SYSTEM = """You are a tutor of Quranic Arabic vocabulary for Surah Al-Mulk (Quran 67). You write a short lesson about ONE root for a beginner.

RULES
1. Use ONLY the EVIDENCE block. Never use outside knowledge about the Quran, tafsir, history or Arabic grammar.
2. Grammar: use only the facts listed for that item, in those words. Never add any other grammatical idea (no subject, object, predicate, prefix, suffix, pronoun, preposition, mood, causative, intensive and so on). If a fact is not listed, do not mention it.
3. "overview": 2 or 3 sentences on how the root appears as different word forms. The only grammar words allowed here are verb, noun, adjective, participle and verbal noun.
4. "forms": for EVERY form id, 1 or 2 sentences on that form's grammatical role, using only that form's facts.
5. "uses": for EVERY word id, 1 or 2 sentences on how the word is used in its verse. Each must contain at least one exact quotation, inside double quotes, copied from that word's meaning or that ayah's translation. Say only what the quoted text and translation show.
6. Use double quotes only for text copied exactly from the evidence.
7. Do not state counts or any numbers. The only numbers allowed are ayah references written like [67:3].
8. No rulings, theology, tafsir or personal interpretation.
9. Write Arabic words only if they appear in the evidence for that item. Plain English, short sentences.

Reply with JSON only, with exactly the ids given:
{"overview": "text",
 "forms": [{"id": "F1", "text": "text"}],
 "uses": [{"id": "W11", "text": "text"}]}"""


def facts(pos_tag, grammar):
    """The grammar facts stored for one word, in plain terms. Unknown codes are left out."""
    codes = [c.strip() for c in (grammar or "").split(",") if c.strip()]
    out = []
    if pos_tag == "V":
        out.append("verb")
    elif pos_tag == "N" and "PRON" not in codes:
        out.append("noun")
    for c in codes:
        if c in SIMPLE_FACTS:
            out.append(SIMPLE_FACTS[c])
        elif c[:1] in PERSON_WORDS and c[1:]:            # 3MS, 2MP, 1P, 3D ...
            out.append(PERSON_WORDS[c[0]])
            out += [GENDER_WORDS.get(x) or NUMBER_WORDS[x] for x in c[1:] if x in "MFSPD"]
        elif c and set(c) <= set("MFSPD"):               # M, F, MS, FP, FD ...
            out += [GENDER_WORDS.get(x) or NUMBER_WORDS[x] for x in c]
        elif c.startswith("form "):
            n = int(c[5:])
            if 1 <= n <= len(ROMAN):
                out.append(f"Form {ROMAN[n - 1]}")
    if pos_tag == "V":                                   # the data marks only the passive
        out.append("passive voice" if "PASS" in codes else "active voice")
    return list(dict.fromkeys(out))


def build_evidence(root):
    """One item per distinct form (lemma + grammar) and one per occurrence. None if the root is absent."""
    base = root_evidence(root)
    if base is None:
        return None
    forms, uses = {}, []
    for r in queries.root_words(root):
        key = (r["lemma"], r["pos_tag"], r["grammar"])
        f = forms.get(key)
        if f is None:
            f = forms[key] = {"id": f"F{len(forms) + 1}", "lemma": r["lemma"],
                              "facts": facts(r["pos_tag"], r["grammar"]), "words": [], "glosses": [], "ayahs": []}
        for field, value in (("words", r["word_arabic"]), ("glosses", r["gloss"]), ("ayahs", r["ayah"])):
            if value and value not in f[field]:
                f[field].append(value)
        uses.append({"id": f"W{r['word_id']}", "word_id": r["word_id"], "form": f["id"], "ayah": r["ayah"],
                     "word": r["word_arabic"], "lemma": r["lemma"], "gloss": r["gloss"],
                     "ayah_arabic": r["ayah_arabic"], "translation": r["translation"]})
    return {"root": root, "total": base["total"], "lemmas": [f["lemma"] for f in base["forms"]],
            "forms": list(forms.values()), "uses": uses}


def format_evidence(ev):
    lines = [f"ROOT {ev['root']}", "", "FORMS:"]
    for f in ev["forms"]:
        meanings = "; ".join(f'"{g}"' for g in f["glosses"]) or "none"
        lines.append(f"{f['id']} | lemma {f['lemma']} | written {'، '.join(f['words'])} | "
                     f"grammar facts: {', '.join(f['facts'])} | meanings: {meanings} | "
                     f"ayahs: {', '.join(f'[67:{n}]' for n in f['ayahs'])}")
    lines += ["", "WORD OCCURRENCES:"]
    for u in ev["uses"]:
        lines += [f"{u['id']} | form {u['form']} | word {u['word']} | meaning \"{u['gloss'] or ''}\" | [67:{u['ayah']}]",
                  f"    ayah: {u['ayah_arabic']}",
                  f"    translation: {u['translation']}"]
    return "\n".join(lines)


def build_user_prompt(ev, previous_errors=None):
    parts = ["EVIDENCE (the only facts you may use):", format_evidence(ev)]
    if previous_errors:
        parts += ["", "YOUR PREVIOUS LESSON FAILED AUTOMATIC CHECKS. Fix every problem and reply again:"]
        parts += [f"- {e}" for e in previous_errors]
    return "\n".join(parts)


def template_texts(ev):
    """The database-only lesson text, used when there is no LLM or its lesson fails the checks."""
    n_total, n_lemmas = ev["total"], len(ev["lemmas"])
    overview = (f"The root {' '.join(ev['root'])} occurs {n_total} time{'s' if n_total != 1 else ''} in "
                f"Surah Al-Mulk, as {n_lemmas} dictionary word{'s' if n_lemmas != 1 else ''}: "
                f"{'، '.join(ev['lemmas'])}.")
    forms = {f["id"]: f"Recorded as: {', '.join(f['facts'])}." for f in ev["forms"]}
    uses = {u["id"]: f"In ayah {u['ayah']}, {u['word']} means \"{u['gloss']}\"." if u["gloss"]
            else f"{u['word']} occurs in ayah {u['ayah']}." for u in ev["uses"]}
    return {"overview": overview, "forms": forms, "uses": uses}


TENSE_NOTE = "The Arabic form is past tense; the English meaning of this word uses \u201cwill\u201d."
WILL = re.compile(r"\bwill\b", re.I)


def tense_note(form_facts, gloss):
    """A fixed note (never written by the LLM) for a past-tense word whose stored meaning uses "will"."""
    return TENSE_NOTE if "past tense" in form_facts and WILL.search(gloss or "") else None


def _result(ev, texts, generated_by, **extra):
    form_facts = {f["id"]: f["facts"] for f in ev["forms"]}
    return {
        "root": ev["root"], "total": ev["total"], "generated_by": generated_by, "overview": texts["overview"],
        "forms": [{"id": f["id"], "lemma": f["lemma"], "words": f["words"], "facts": f["facts"], "glosses": f["glosses"],
                   "ayahs": f["ayahs"], "text": texts["forms"][f["id"]]} for f in ev["forms"]],
        "uses": [{**{k: u[k] for k in ("id", "word_id", "form", "ayah", "word", "gloss")},
                  "text": texts["uses"][u["id"]], "note": tense_note(form_facts[u["form"]], u["gloss"])}
                 for u in ev["uses"]],
        "verification_errors": [], "llm_error": None, **extra,
    }


def lesson(root, use_llm=False, llm_config=None, llm_transport=None):
    ev = build_evidence(root)
    if ev is None:
        return None
    fallback = template_texts(ev)
    if not use_llm:
        return _result(ev, fallback, "template")
    cfg = llm_config or llm.get_config()
    if cfg is None:
        return _result(ev, fallback, "template", llm_error="the LLM is not configured (.env)")

    errors = None
    for attempt in range(1, 3):          # first try + one regeneration with the checker's complaints
        try:
            raw = llm.generate_json(SYSTEM, build_user_prompt(ev, errors), config=cfg, transport=llm_transport)
        except llm.LLMError as e:
            return _result(ev, fallback, "template", llm_error=str(e), attempts=attempt)
        texts, errors = tutor_verify.check(generate.parse(raw), ev)
        if not errors:
            return _result(ev, texts, "llm", attempts=attempt)
    # never show an unverified lesson
    return _result(ev, fallback, "template", verification_errors=errors, attempts=2)
