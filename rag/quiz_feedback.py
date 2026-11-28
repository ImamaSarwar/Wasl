"""
Quiz feedback: when a learner picks a wrong option, explain the difference between what they chose and the
right answer. The AI component of the quiz.

    feedback(question, chosen_id, use_llm=True) -> dict        (raises ValueError for a bad request)

Same pattern as the Root Tutor (rag/tutor.py):
  1. the code grades the answer again from the DATABASE (the question sent by the browser is not trusted)
  2. SQL fetches evidence for both options: the chosen one and the correct one
  3. Gemini writes two short texts: "why_not" (about the chosen option) and "why_correct" (about the answer)
  4. rag/tutor_verify.py checks EACH text against ITS OWN evidence only. A grammar term, ayah, Arabic word or
     quotation that belongs to the other option is rejected, so the model cannot say the word itself has the
     feature the learner wrongly picked.
  5. one retry with the checker's complaints; if that fails too (or there is no API key), the database-only
     template explanation is shown. An unverified text is never shown.
"""
import re

from backend import queries, quiz
from backend.grammar import PERSON

from . import generate, llm, tutor_verify
from .tutor import facts

LIMIT = 380                 # characters per text
EXAMPLES = 2                # example words fetched for a chosen root / meaning / grammar feature

SYSTEM = """You are a tutor of Quranic Arabic vocabulary for Surah Al-Mulk (Quran 67). A beginner answered a multiple-choice question wrongly. Explain the difference between their choice and the right answer.

RULES
1. Use ONLY the EVIDENCE block. Never use outside knowledge about the Quran, tafsir, history or Arabic grammar.
2. "why_not": 1 or 2 sentences about the CHOSEN option only, using only the CHOSEN evidence: what it really is or where it really occurs in this surah. Do not mention the question's word here.
3. "why_correct": 1 or 2 sentences about the CORRECT answer only, using only the CORRECT evidence.
4. Grammar: use only the grammar facts listed in that part, in those words. Never add any other grammatical idea (no subject, object, prefix, suffix, pronoun, preposition, mood, pattern and so on).
5. When you give a meaning, copy it exactly from the evidence, inside double quotes. Use double quotes only for text copied exactly from the evidence.
6. Write Arabic words only if they appear in that part of the evidence. Root letters may be written spaced, like خ ل ق.
7. Do not state counts or any numbers. The only numbers allowed are ayah references written like [67:3].
8. No rulings, theology, tafsir or personal interpretation. Plain English, short sentences, encouraging tone.

Reply with JSON only:
{"why_not": "text", "why_correct": "text"}"""


# ---------- database helpers ----------

def _words():
    return queries._rows(
        "SELECT w.word_id, w.ayah, w.pos, w.arabic, w.root, w.lemma, w.pos_tag, w.grammar, w.gloss, "
        "a.arabic AS ayah_arabic, a.translation FROM words w JOIN ayahs a USING(ayah) ORDER BY w.ayah, w.pos")


def _codes(w):
    return set((w["grammar"] or "").split(","))


def _spaced(root):
    return " ".join(root)


def _example(w):
    return {"word": w["arabic"], "lemma": w["lemma"], "root": w["root"], "gloss": w["gloss"], "ayah": w["ayah"],
            "translation": w["translation"], "facts": facts(w["pos_tag"], w["grammar"])}


def _part(examples, *, extra_facts=(), extra_arabic=(), extra_quotable=(), ayahs=(), notes=()):
    """One side of the evidence (chosen or correct) and what the verifier lets its text use."""
    arabic, quotable, fact_set, refs = set(extra_arabic), list(extra_quotable), set(extra_facts), list(ayahs)
    for e in examples:
        arabic |= {x for x in (e["word"], e["lemma"], e["root"]) if x}
        quotable += [x for x in (e["gloss"], e["translation"]) if x]
        fact_set |= set(e["facts"])
        refs.append(e["ayah"])
    return {"examples": examples, "notes": list(notes), "facts": fact_set, "ayahs": sorted(set(refs)),
            "quotable": quotable, "arabic": {x for a in arabic for x in tutor_verify._arabic_words(a)}}


# ---------- grading + evidence, one function per question type ----------

def _word_of(question, words):
    word = question.get("word") or {}
    w = next((x for x in words if x["word_id"] == word.get("word_id")), None)
    if w is None or not w["root"]:
        raise ValueError("unknown word in the question")
    return w


def _option(question, chosen_id):
    o = next((o for o in question.get("options") or [] if o.get("id") == chosen_id), None)
    if o is None or not isinstance(o.get("text"), str):
        raise ValueError("the chosen option is not in the question")
    return o


def _root_case(question, chosen, words):
    w = _word_of(question, words)
    picked = chosen["text"].replace(" ", "")
    if picked == w["root"]:
        return None
    hits = [x for x in words if x["root"] == picked]
    if not hits:
        raise ValueError("the chosen root does not occur in the surah")
    shared = [c for c in w["root"] if c in set(picked)]
    notes = [f"shared letters between the two roots: {' '.join(shared)}"] if shared else \
        ["the two roots share no letters"]
    return {
        "type": "root", "refs": [w["ayah"]],
        "chosen": _part([_example(x) for x in hits[:EXAMPLES]], extra_arabic=[picked],
                        notes=[f"the chosen root {_spaced(picked)} is a different root"]),
        "correct": _part([_example(w)], notes=[f"the word comes from the root {_spaced(w['root'])}"] + notes),
        "template": (
            f'{_spaced(picked)} is a different root. In this surah it gives {hits[0]["arabic"]}'
            + (f' ("{hits[0]["gloss"]}")' if hits[0]["gloss"] else "") + f' in ayah {hits[0]["ayah"]}.',
            f'{w["arabic"]}' + (f' ("{w["gloss"]}")' if w["gloss"] else "")
            + f' comes from the root {_spaced(w["root"])}.'),
    }


def _vocabulary_case(question, chosen, words):
    w = _word_of(question, words)
    if chosen["text"] == w["gloss"]:
        return None
    hits = [x for x in words if x["gloss"] == chosen["text"] and x["root"] != w["root"]]
    if not hits:
        raise ValueError("the chosen meaning is not a meaning in the surah")
    h = hits[0]
    return {
        "type": "vocabulary", "refs": [w["ayah"]],
        "chosen": _part([_example(x) for x in hits[:EXAMPLES]]),
        "correct": _part([_example(w)]),
        "template": (f'"{h["gloss"]}" is the meaning of {h["arabic"]}, from the root {_spaced(h["root"])}, '
                     f'in ayah {h["ayah"]}.',
                     f'In ayah {w["ayah"]}, {w["arabic"]} means "{w["gloss"]}".'),
    }


def _label_table(kind):
    if kind == "tense":
        return quiz.TENSES, "V"
    if kind == "case":
        return quiz.CASES, "N"
    if kind == "person":
        return {c: f"{plain[0].upper()}{plain[1:]}: {tech}" for c, (plain, tech) in PERSON.items()}, "V"
    raise ValueError("unknown grammar question kind")


def _morphology_case(question, chosen, words):
    w = _word_of(question, words)
    table, pos = _label_table(question.get("kind"))
    code = next((c for c, label in table.items() if label == chosen["text"]), None)
    if code is None:
        raise ValueError("the chosen option is not a grammar label")
    if code in _codes(w):
        return None
    label_facts = [f for f in facts(pos, code) if f not in ("verb", "noun", "active voice")]
    examples = [x for x in words if x["pos_tag"] == pos and code in _codes(x) and x["word_id"] != w["word_id"]]
    examples.sort(key=lambda x: (x["root"] == w["root"], x["ayah"], x["pos"]))
    mine = facts(w["pos_tag"], w["grammar"])
    if examples:
        e = examples[0]
        not_text = f'{chosen["text"]} would be a word like {e["arabic"]} in ayah {e["ayah"]}, ' \
                   f'recorded as: {", ".join(label_facts)}.'
    else:
        not_text = f'No word in this surah is recorded as: {", ".join(label_facts)}.'
    return {
        "type": "morphology", "refs": [w["ayah"]],
        "chosen": _part([_example(x) for x in examples[:EXAMPLES]], extra_facts=label_facts,
                        extra_quotable=[chosen["text"]],
                        notes=[f"the chosen option means: {', '.join(label_facts)}"]),
        "correct": _part([_example(w)], notes=[f"the word is recorded as: {', '.join(mine)}"]),
        "template": (not_text, f'In ayah {w["ayah"]}, {w["arabic"]} is recorded as: {", ".join(mine)}.'),
    }


def _ayah(ayah, words):
    """(translation, [Arabic words]) of one ayah."""
    ws = [x for x in words if x["ayah"] == ayah]
    if not ws:
        raise ValueError("unknown ayah in the question")
    return ws[0]["translation"], [x["arabic"] for x in ws]


def _contextual_case(question, chosen, words):
    root = (question.get("root") or "").replace(" ", "")
    hit_ayahs = {x["ayah"] for x in words if x["root"] == root}
    if not hit_ayahs:
        raise ValueError("unknown root in the question")
    shown = [o.get("ayah") for o in (question.get("options") or [])[:3]]
    if len(shown) != 3 or not all(isinstance(n, int) and 1 <= n <= 30 for n in shown):
        raise ValueError("the question's ayahs are missing")
    right = sorted(n for n in shown if n in hit_ayahs)
    both_right = shown[0] in hit_ayahs and shown[1] in hit_ayahs
    picked_both = chosen["text"] == quiz.BOTH
    if (picked_both and both_right) or (not picked_both and not both_right and chosen.get("ayah") in hit_ayahs):
        return None

    def ayah_examples(n):
        hits = [x for x in words if x["ayah"] == n and x["root"] == root]
        return [_example(x) for x in hits]

    correct = _part([e for n in right for e in ayah_examples(n)], extra_arabic=[root],
                    notes=[f"the root {_spaced(root)} occurs in " + ", ".join(f"[67:{n}]" for n in right)])
    found = "; ".join(f'ayah {n}: ' + "، ".join(x["arabic"] for x in words if x["root"] == root and x["ayah"] == n)
                      for n in right)
    why_correct = f"The root {_spaced(root)} appears in {found}."

    if picked_both or chosen.get("ayah") not in hit_ayahs:
        # the learner picked (or included) an ayah without the root
        wrong = next(n for n in shown[:2] if n not in hit_ayahs) if picked_both else chosen["ayah"]
        translation, ayah_words = _ayah(wrong, words)
        part = _part([], extra_quotable=[translation, quiz.BOTH], extra_arabic=ayah_words, ayahs=[wrong],
                     notes=[f"no word from the root {_spaced(root)} occurs in [67:{wrong}]",
                            f"translation of [67:{wrong}]: {translation}"])
        why_not = (f'Ayah {wrong} does not contain a word from the root {_spaced(root)}, so "{quiz.BOTH}" '
                   f'cannot be right.' if picked_both else
                   f'Ayah {wrong} does not contain a word from the root {_spaced(root)}.')
    else:
        # the learner picked one right ayah when both A and B are right
        other = next(n for n in shown[:2] if n != chosen["ayah"])
        part = _part(ayah_examples(chosen["ayah"]), extra_arabic=[root], extra_quotable=[quiz.BOTH],
                     ayahs=[other], notes=[f"[67:{chosen['ayah']}] does contain the root, but [67:{other}] "
                                           f"contains it too, so the full answer is \"{quiz.BOTH}\""])
        why_not = (f'Ayah {chosen["ayah"]} does contain this root, but ayah {other} contains it too, '
                   f'so the full answer is "{quiz.BOTH}".')
    return {"type": "contextual", "refs": right, "chosen": part, "correct": correct,
            "template": (why_not, why_correct)}


CASES = {"root": _root_case, "vocabulary": _vocabulary_case, "morphology": _morphology_case,
         "contextual": _contextual_case}


def build_case(question, chosen_id, words=None):
    """Grade the answer from the database and collect evidence. None if the chosen option is correct."""
    if not isinstance(question, dict) or question.get("type") not in CASES:
        raise ValueError("unknown question type")
    try:
        chosen = _option(question, chosen_id)
        return CASES[question["type"]](question, chosen, words or _words())
    except (TypeError, AttributeError, KeyError, StopIteration):
        raise ValueError("the question is not in the expected shape") from None


# ---------- prompt, checks, result ----------

def _format_part(name, part):
    lines = [f"{name}:"]
    for n in part["notes"]:
        lines.append(f"- {n}")
    for e in part["examples"]:
        meaning = f'"{e["gloss"]}"' if e["gloss"] else "none"
        lines.append(f'- word {e["word"]} | lemma {e["lemma"]} | root {_spaced(e["root"])} | meaning {meaning} | '
                     f'grammar facts: {", ".join(e["facts"]) or "none"} | [67:{e["ayah"]}]')
        lines.append(f'    translation of [67:{e["ayah"]}]: {e["translation"]}')
    return lines


def build_user_prompt(question, chosen_id, case, previous_errors=None):
    chosen = _option(question, chosen_id)
    answer = next((o for o in question["options"] if o["id"] == question.get("answer")), {})
    word = (question.get("word") or {}).get("arabic")
    parts = [f"QUESTION: {question.get('prompt', '')}" + (f" Word: {word}" if word else "")
             + (f" Root: {_spaced(question['root'])}" if not word else ""),
             f"LEARNER CHOSE: {chosen['text']}" + (f" ([67:{chosen['ayah']}])" if chosen.get("ayah") else ""),
             f"CORRECT ANSWER: {answer.get('text', '')}", "",
             "EVIDENCE (the only facts you may use):"]
    parts += _format_part("CHOSEN (use only for why_not)", case["chosen"])
    parts += [""] + _format_part("CORRECT (use only for why_correct)", case["correct"])
    if previous_errors:
        parts += ["", "YOUR PREVIOUS REPLY FAILED AUTOMATIC CHECKS. Fix every problem and reply again:"]
        parts += [f"- {e}" for e in previous_errors]
    return "\n".join(parts)


def check(data, case):
    """-> ({"why_not", "why_correct"} or None, [errors]). Each text is checked against its own evidence."""
    if not isinstance(data, dict):
        return None, ['reply with one JSON object holding "why_not" and "why_correct"']
    texts, errors = {}, []
    for key, side, need_quote in (("why_not", "chosen", False),
                                  ("why_correct", "correct", case["type"] in ("vocabulary", "root")
                                   and any(e["gloss"] for e in case["correct"]["examples"]))):
        text = data.get(key)
        if not isinstance(text, str) or not text.strip():
            errors.append(f'"{key}" must be a non-empty text')
            continue
        p = case[side]
        found = tutor_verify._text_errors(text.strip(), facts=p["facts"], ayahs=p["ayahs"], quotable=p["quotable"],
                                          arabic=p["arabic"], limit=LIMIT, need_quote=need_quote)
        errors += [f"{key} {e}" for e in found]
        texts[key] = text.strip()
    return (None, errors) if errors else (texts, [])


def _result(case, texts, generated_by, **extra):
    return {"correct": False, "type": case["type"], "generated_by": generated_by,
            "why_not": texts["why_not"], "why_correct": texts["why_correct"], "refs": case["refs"],
            "verification_errors": [], "llm_error": None, "attempts": 0, **extra}


def feedback(question, chosen_id, use_llm=False, llm_config=None, llm_transport=None, words=None):
    case = build_case(question, chosen_id, words)
    if case is None:
        return {"correct": True}
    fallback = dict(zip(("why_not", "why_correct"), case["template"]))
    if not use_llm:
        return _result(case, fallback, "template")
    cfg = llm_config or llm.get_config()
    if cfg is None:
        return _result(case, fallback, "template", llm_error="the LLM is not configured (.env)")

    errors = None
    for attempt in range(1, 3):          # first try + one regeneration with the checker's complaints
        try:
            raw = llm.generate_json(SYSTEM, build_user_prompt(question, chosen_id, case, errors),
                                    config=cfg, transport=llm_transport)
        except llm.LLMError as e:
            return _result(case, fallback, "template", llm_error=str(e), attempts=attempt)
        texts, errors = check(generate.parse(raw), case)
        if not errors:
            return _result(case, texts, "llm", attempts=attempt, latency=llm.LAST_CALL.get("latency"))
    return _result(case, fallback, "template", verification_errors=errors, attempts=2)   # never unverified
