"""
Grounded generation: the LLM writes the answer, but ONLY from the evidence we hand it.

The evidence (counts, forms, word meanings, ayah translations) comes from the database. The model is
asked for JSON with a short answer plus a list of `claims`, so rag/verify.py can check every claim
against the database instead of trusting prose.
"""
import json
import re

from . import llm
from .resolve import ALIASES

SYSTEM = """You answer questions about the vocabulary of Surah Al-Mulk (Quran 67) for a Quranic Arabic learning tool.

RULES
1. Use ONLY the EVIDENCE block in the user message. Never use outside knowledge about the Quran, tafsir, history, or Arabic grammar. If the evidence does not contain the answer, refuse.
2. Cite the ayah for every statement about how a word is used, written exactly like [67:3]. Only cite ayahs that appear in the evidence.
3. Describe a word's meaning only with the 'meaning' glosses or the ayah translations in the evidence. When you quote a gloss or a translation, copy it exactly, inside double quotes.
4. Never give rulings (halal/haram), theology, personal interpretation, or tafsir. If the question asks for them, refuse.
5. If you state a count, it must be exactly a number given in the evidence.
6. Be brief: at most 4 sentences. Plain English.

Reply with JSON only, in this shape:
{"refuse": false,
 "answer": "text with [67:N] citations",
 "claims": [{"ayah": 3, "root": "خلق", "lemma": "خَلْق", "gloss": "(the) creation"}]}
Each claim describes one word from the evidence: ayah, root and lemma exactly as listed there, and gloss exactly as listed (or null). For questions with no root in the evidence, claims may be [] .
To refuse, reply {"refuse": true, "answer": "", "claims": []}."""


def _label(root):
    lat = ALIASES.get(root, {}).get("latin")
    return f"{root} ({lat})" if lat else root


def format_evidence(intent, evidence):
    """Plain-text evidence block. `evidence` = list of root evidences, or list of ayah dicts (semantic)."""
    if intent == "semantic":
        lines = ["AYAHS (closest in meaning to the question; no root was named):"]
        lines += [f"[67:{a['ayah']}] translation: {a['translation']}" for a in evidence]
        return "\n".join(lines)

    lines = []
    for ev in evidence:
        lines.append(f"ROOT {_label(ev['root'])}: {ev['total']} occurrence(s) in the surah, {len(ev['forms'])} form(s)")
        for f in ev["forms"]:
            g = "; ".join(f'"{x}"' for x in f.get("glosses", [])) or "none"
            lines.append(f"  FORM {f['lemma']} | count {f['count']} | meanings: {g} | "
                         f"ayahs: {', '.join(map(str, f['ayahs']))}")
    by_ayah = {}
    for ev in evidence:
        for a in ev["ayahs"]:
            slot = by_ayah.setdefault(a["ayah"], {"translation": a["translation"], "hits": []})
            slot["hits"] += [(ev["root"], h) for h in a["hits"]]
    lines.append("AYAHS:")
    for n in sorted(by_ayah):
        lines.append(f"[67:{n}] translation: {by_ayah[n]['translation']}")
        for root, h in by_ayah[n]["hits"]:
            lines.append(f'    word {h["word"]} | root {root} | lemma {h["lemma"]} | meaning "{h.get("gloss") or ""}"')
    return "\n".join(lines)


def build_user_prompt(question, intent, evidence, previous_errors=None):
    parts = [f"QUESTION: {question}", f"QUESTION TYPE: {intent}", "",
             "EVIDENCE (the only facts you may use):", format_evidence(intent, evidence)]
    if previous_errors:
        parts += ["", "YOUR PREVIOUS ANSWER FAILED AUTOMATIC CHECKS. Fix every problem and answer again:"]
        parts += [f"- {e}" for e in previous_errors]
    return "\n".join(parts)


def ask(question, intent, evidence, previous_errors=None, **llm_kwargs):
    """Returns the model's raw reply text (JSON as a string). Raises llm.LLMError on failure."""
    return llm.generate_json(SYSTEM, build_user_prompt(question, intent, evidence, previous_errors), **llm_kwargs)


def parse(raw):
    """Parse the model's reply into a dict, tolerating ```json fences. Returns None if it is not JSON."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
