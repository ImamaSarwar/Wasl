"""
The assistant: question -> intent -> resolve -> evidence -> answer.

Right now the answer is written by a template from database facts (no LLM), which is already
useful and can never invent anything. Generation by a language model plugs in at `_write_answer`
later; the response shape stays the same so the frontend does not change.

Response: {answer, citations [ayah numbers], refused, verification_errors, intent, roots, evidence}
"""
import re

from . import retrieve
from .evidence import ayah_evidence, compare_evidence, root_evidence
from .resolve import resolve

# The assistant covers vocabulary and wording only. Rulings, fatwas and personal religious
# advice are declined (see "Responsible Use" in the proposal).
# Keyword gate, deliberately narrow: only clear religious-ruling phrasing. Generic words like
# "can I" or "should I" are NOT here, because they also appear in normal vocabulary questions.
# Subtler cases (opinions, interpretation) get caught by the LLM intent check added later.
OUT_OF_SCOPE = re.compile(
    r"\b(fatwa|fatawa|halal|haram|makruh|permissible|impermissible|forbidden|"
    r"is it (?:a )?sin|rulings? (?:on|for|of|about)|am i allowed|"
    r"will (?:i|they|he|she) go to (?:hell|heaven|jannah|jahannam))\b", re.I)

REFUSAL_SCOPE = ("I can only answer questions about the vocabulary and root usage of Surah Al-Mulk. "
                 "I don't give rulings, fatwas or personal religious advice - please ask a qualified scholar.")
REFUSAL_NOT_FOUND = ("I couldn't match your question to a root in Surah Al-Mulk, so I don't have enough "
                     "evidence to answer. Try naming a root (e.g. خلق or kh-l-q) or a word form "
                     "(e.g. khalaqa), or ask about a concept such as seeing, knowing or mercy.")


def _times(n):
    return "once" if n == 1 else f"{n} times"


def _root_label(root):
    from .resolve import ALIASES
    lat = ALIASES.get(root, {}).get("latin")
    return f"{root} ({lat})" if lat else root


def _summarise(ev):
    forms = "; ".join(
        f"{f['lemma']} ({_times(f['count'])}, ayah{'s' if len(f['ayahs']) > 1 else ''} "
        f"{', '.join(map(str, f['ayahs']))})" for f in ev["forms"])
    n = len(ev["forms"])
    return (f"The root {_root_label(ev['root'])} occurs {_times(ev['total'])} in Surah Al-Mulk, "
            f"in {n} form{'s' if n != 1 else ''}: {forms}.")


def _ayah_lines(ayahs, limit=6):
    lines = [f"[67:{a['ayah']}] {a['translation']}" for a in ayahs[:limit]]
    if len(ayahs) > limit:
        n = len(ayahs) - limit
        lines.append(f"... and {n} more ayah{'s' if n != 1 else ''} (see the root panel).")
    return "\n".join(lines)


def _write_answer(intent, evs, extra=None):
    """Template answer. Replace/augment with LLM generation later; keep the same inputs."""
    if intent == "compare":
        a, b = evs
        text = f"{_summarise(a)}\n{_summarise(b)}\n"
        shared = (extra or {}).get("shared_ayahs", [])
        text += (f"They appear together in ayah{'s' if len(shared) != 1 else ''} "
                 f"{', '.join(map(str, shared))}." if shared else "They never appear in the same ayah.")
        shown = sorted({x["ayah"]: x for e in evs for x in e["ayahs"]}.items())
        return text + "\n\n" + _ayah_lines([v for _, v in shown])
    text = "\n\n".join(_summarise(e) for e in evs)
    allay = sorted({x["ayah"]: x for e in evs for x in e["ayahs"]}.items())
    return text + "\n\n" + _ayah_lines([v for _, v in allay])


def _refuse(message, intent, roots=()):
    return {"answer": message, "citations": [], "refused": True, "verification_errors": [],
            "intent": intent, "roots": list(roots), "evidence": None}


def _semantic(q, retriever=None, threshold=None):
    """No root named: find ayahs by meaning. Refuse if even the best match is too weak."""
    ret = retriever or retrieve.get_retriever()
    thr = retrieve.threshold(ret.name) if threshold is None else threshold
    hits = [(n, sc) for n, sc in ret.search(q, retrieve.TOP_K) if sc >= thr]
    if not hits:
        return _refuse(REFUSAL_NOT_FOUND, "no_match")
    ev = ayah_evidence(hits)
    lines = "\n".join(f"[67:{a['ayah']}] {a['translation']}" for a in ev)
    return {"answer": "No root was named, so these are the ayahs whose translation is closest in "
                      "meaning to your question:\n\n" + lines,
            "citations": sorted(a["ayah"] for a in ev), "refused": False, "verification_errors": [],
            "intent": "semantic", "roots": [], "matched": [], "retriever": ret.name,
            "evidence": ev}


def answer(question, retriever=None, threshold=None):
    q = (question or "").strip()
    if not q:
        return _refuse("Please type a question.", "empty")
    if OUT_OF_SCOPE.search(q):
        return _refuse(REFUSAL_SCOPE, "out_of_scope")

    r = resolve(q)
    direct = [it["root"] for it in r["direct"]]
    concept = [it["root"] for it in r["concept"]]

    if len(direct) >= 2:
        intent, roots = "compare", direct[:2]
    elif len(direct) == 1:
        intent, roots = "single_root", direct
    elif concept:
        intent, roots = "concept", concept
    else:
        return _semantic(q, retriever, threshold)

    evs = [e for e in (root_evidence(x) for x in roots) if e]
    if not evs:
        return _refuse(REFUSAL_NOT_FOUND, intent, roots)

    extra = None
    if intent == "compare" and len(evs) == 2:
        extra = compare_evidence(roots[0], roots[1])
    text = _write_answer(intent, evs, extra)
    citations = sorted({a["ayah"] for e in evs for a in e["ayahs"]})
    return {"answer": text, "citations": citations, "refused": False, "verification_errors": [],
            "intent": intent, "roots": roots,
            "matched": [{"root": it["root"], "via": it["via"], "matched": it["matched"]}
                        for it in (r["direct"] + r["concept"]) if it["root"] in roots],
            "evidence": evs}
