"""
The assistant: question -> intent -> resolve -> evidence -> answer.

Right now the answer is written by a template from database facts (no LLM), which is already
useful and can never invent anything. Generation by a language model plugs in at `_write_answer`
later; the response shape stays the same so the frontend does not change.

Response: {answer, citations [ayah numbers], refused, verification_errors, intent, roots, evidence}
"""
import re

from . import generate, llm, retrieve, verify
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
    r"will (?:i|they|he|she) go to (?:hell|heaven|jannah|jahannam)|"
    # personal / theological questions that are not about vocabulary
    r"will (?:people|those|non-?believers|unbelievers|disbelievers|muslims|christians|jews)\b.{0,60}"
    r"(?:punish|hell|heaven|paradise|saved|forgiven)|"
    r"should i (?:be )?(?:afraid|fear|worry)|protect me|save me|every night|"
    r"virtues? of (?:reading|reciting|this)|reward (?:for|of) (?:reading|reciting))", re.I)

# The assistant covers Surah Al-Mulk only. A question that names another surah (or an ayah of
# another surah) is refused up front: embedding search would otherwise return a loosely related
# Al-Mulk ayah with a confident-looking score (seen in eval: "Tell me about Surah Al-Baqarah").
_OTHER_SURAHS = (
    "fatihah|fatiha|baqarah|baqara|imran|nisa|maidah|maida|anam|araf|anfal|tawbah|taubah|tawba|yunus|hud|"
    "yusuf|rad|ibrahim|hijr|nahl|isra|kahf|maryam|ta-?ha|taha|anbiya|hajj|muminun|mu'minun|nur|furqan|"
    "shuara|naml|qasas|ankabut|rum|luqman|sajdah|sajda|ahzab|saba|fatir|ya-?sin|yaseen|saffat|sad|zumar|"
    "ghafir|fussilat|shura|zukhruf|dukhan|jathiyah|ahqaf|muhammad|fath|hujurat|qaf|dhariyat|tur|najm|"
    "qamar|rahman|waqiah|waqi'ah|hadid|mujadilah|hashr|mumtahanah|saff|jumu'?ah|munafiqun|taghabun|talaq|"
    "tahrim|qalam|haqqah|ma'?arij|nuh|jinn|muzzammil|muddaththir|muddathir|qiyamah|insan|mursalat|naba|"
    "naziat|abasa|takwir|infitar|mutaffifin|inshiqaq|buruj|tariq|ala|ghashiyah|fajr|balad|shams|layl|duha|"
    "sharh|inshirah|tin|alaq|qadr|bayyinah|zalzalah|adiyat|qariah|takathur|asr|humazah|fil|quraysh|"
    "ma'?un|kawthar|kausar|kafirun|nasr|masad|lahab|ikhlas|falaq|nas"
)
OTHER_SURAH = re.compile(
    rf"\b(?:(?:surah|sura|surat|chapter)\s+(?:(?:al|an|at|ash|as|ad|ar|az|adh|ath)[-\s']*)?(?:{_OTHER_SURAHS})\b"
    rf"|(?:surah|sura|surat|chapter)\s+(?!67\b)\d{{1,3}}\b"
    rf"|(?:al|an|at|ash|as|ad|ar|az|adh|ath)-(?:{_OTHER_SURAHS})\b"
    rf"|(?!67:)\d{{1,3}}:\d{{1,3}})",
    re.I)
# a named verse or chapter of another surah is out of scope even without a surah number
OTHER_SURAH = re.compile(OTHER_SURAH.pattern + r"|\b(?:ayat(?:ul|\s+al|\s+an)?[-\s]?(?:kursi|nur)|throne verse)\b", re.I)
TAFSIR = re.compile(
    r"\b(tafsir|tafseer|exegesis|interpretation of|what does .* really mean|hidden meaning|secret meaning|"
    r"symbolic meaning|ibn kathir|ibn abbas|al-?tabari|tabari|qurtubi|jalalayn|sayyid qutb|maududi|"
    r"what (?:do )?(?:the )?(?:scholars|commentators|mufassir\w*) (?:say|said|think))\b", re.I)

REFUSAL_OTHER_SURAH = ("This assistant only covers Surah Al-Mulk (67). Please ask about a root, word "
                       "form or topic in that surah.")
REFUSAL_TAFSIR = ("I answer questions about vocabulary and root usage only, not interpretation (tafsir). "
                  "Please consult a qualified scholar for the meaning of ayahs.")
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


def _gloss_text(f):
    """'created' / '(the) creation' - the word-by-word meaning(s) of one form, at most three."""
    g = f.get("glosses") or []
    return " " + ", ".join(f'"{x}"' for x in g[:3]) if g else ""


def _summarise(ev):
    forms = "; ".join(
        f"{f['lemma']}{_gloss_text(f)} ({_times(f['count'])}, ayah{'s' if len(f['ayahs']) > 1 else ''} "
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


MEANING = re.compile(r"\b(mean|means|meaning|meanings|define|definition|gloss)\b", re.I)
MEANING_NOTE = ("(Meanings are the word-by-word glosses from the dataset: they show how each form is "
                "rendered in this surah, not a dictionary definition.)")


def _write_answer(intent, evs, extra=None):
    """Template answer, built only from database facts. Also the safe fallback for LLM answers."""
    if intent == "meaning":
        ev = evs[0]
        allay = sorted({x["ayah"]: x for x in ev["ayahs"]}.items())
        return (f"{_summarise(ev)}\n{MEANING_NOTE}\n\n" + _ayah_lines([v for _, v in allay]))
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


def _semantic(q, retriever=None, threshold=None, use_llm=False):
    """
    No root named: find ayahs by meaning. Refuse if even the best match is too weak.
    With an LLM the weak-but-not-hopeless band (retrieve.THRESHOLDS_LOW up to the threshold) is let through,
    marked "borderline", so the LLM can judge the candidates; answer() refuses it if the LLM cannot.
    """
    ret = retriever or retrieve.get_retriever()
    high = retrieve.threshold(ret.name) if threshold is None else threshold
    low = high if (threshold is not None or not use_llm) else retrieve.threshold_low(ret.name)
    scored = ret.search(q, retrieve.TOP_K)
    hits = [(n, sc) for n, sc in scored if sc >= low]
    if not hits:
        return _refuse(REFUSAL_NOT_FOUND, "no_match")
    borderline = max(sc for _, sc in hits) < high
    ev = ayah_evidence(hits)
    lines = "\n".join(f"[67:{a['ayah']}] {a['translation']}" for a in ev)
    return {"answer": "No root was named, so these are the ayahs whose translation is closest in "
                      "meaning to your question:\n\n" + lines,
            "citations": sorted(a["ayah"] for a in ev), "refused": False, "verification_errors": [],
            "intent": "semantic", "roots": [], "matched": [], "retriever": ret.name,
            "evidence": ev, "borderline": borderline}


REFUSAL_UNSUPPORTED = ("I can't answer that from the evidence I retrieved for Surah Al-Mulk. "
                       "Try naming a root or word form, or ask about a topic in the surah.")
MAX_ATTEMPTS = 2   # first try + one regeneration with the verifier's complaints


def _with_llm(res, question, use_llm, config=None, transport=None):
    """
    Optional LLM stage. `res` is a finished database-only answer (the safe fallback).
    The model rewrites it into a short grounded explanation; rag/verify.py checks every claim against
    the evidence. If the check fails twice, or the LLM is unavailable, `res` is returned unchanged.
    Adds: generated_by ("llm" | "template"), attempts, llm_error.
    """
    if not use_llm or res["refused"]:
        return res
    cfg = config or llm.get_config()
    if cfg is None:
        return {**res, "generated_by": "template", "llm_error": "the LLM is not configured (.env)"}

    template, errors, data = res["answer"], None, None
    stats = {"calls": 0, "latency": 0.0, "cached_latency": 0.0, "tokens_in": 0, "tokens_out": 0,
             "unmeasured": 0}

    def _count():
        stats["calls"] += 1
        if not llm.LAST_CALL.get("measured", True):
            stats["unmeasured"] += 1
        stats["latency"] = round(stats["latency"] + llm.LAST_CALL["latency"], 3)
        if llm.LAST_CALL["cached"]:
            stats["cached_latency"] = round(stats["cached_latency"] + llm.LAST_CALL["latency"], 3)
        stats["tokens_in"] += llm.LAST_CALL["tokens_in"]
        stats["tokens_out"] += llm.LAST_CALL["tokens_out"]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = generate.ask(question, res["intent"], res["evidence"], previous_errors=errors,
                               matched=res.get("matched"), extra=res.get("extra"), config=cfg, transport=transport)
        except llm.LLMError as e:
            return {**res, "generated_by": "template", "llm_error": str(e), "attempts": attempt, "llm_stats": stats}
        _count()
        data, errors = verify.check(raw, res["intent"], res["evidence"], question=question, extra=res.get("extra"))
        if not errors:
            break
    if errors:
        # never show an unverified model answer: fall back to the database-only answer
        return {**res, "generated_by": "template", "verification_errors": errors, "attempts": MAX_ATTEMPTS,
                "llm_stats": stats}
    if data["refuse"]:
        return {**_refuse(REFUSAL_UNSUPPORTED, res["intent"], res.get("roots", ())),
                "generated_by": "llm", "attempts": attempt, "llm_reason": data.get("reason"),
                "llm_stats": stats}
    return {**res, "answer": data["answer"].strip() + "\n\nEvidence:\n" + template,
            "citations": verify.cited_ayahs(data), "generated_by": "llm", "attempts": attempt,
            "claims": data.get("claims") or [], "llm_stats": stats}


def answer(question, retriever=None, threshold=None, use_llm=False, llm_config=None, llm_transport=None):
    q = (question or "").strip()
    if not q:
        return _refuse("Please type a question.", "empty")
    if OUT_OF_SCOPE.search(q):
        return _refuse(REFUSAL_SCOPE, "out_of_scope")
    if OTHER_SURAH.search(q):
        return _refuse(REFUSAL_OTHER_SURAH, "other_surah")
    if TAFSIR.search(q):
        return _refuse(REFUSAL_TAFSIR, "out_of_scope")

    r = resolve(q)
    direct = [it["root"] for it in r["direct"]]
    concept = [it["root"] for it in r["concept"]]

    if len(direct) >= 2:
        intent, roots = "compare", direct[:2]
    elif len(direct) == 1:
        intent, roots = ("meaning" if MEANING.search(q) else "single_root"), direct
    elif concept:
        intent, roots = "concept", concept
    else:
        res = _semantic(q, retriever, threshold, use_llm)
        out = _with_llm(res, q, use_llm, llm_config, llm_transport)
        if res.get("borderline") and not out["refused"] and out.get("generated_by") != "llm":
            return _refuse(REFUSAL_NOT_FOUND, "no_match")   # a weak match nobody vouched for
        return out

    evs = [e for e in (root_evidence(x) for x in roots) if e]
    if not evs:
        return _refuse(REFUSAL_NOT_FOUND, intent, roots)

    extra = None
    if intent == "compare" and len(evs) == 2:
        extra = compare_evidence(roots[0], roots[1])
    text = _write_answer(intent, evs, extra)
    citations = sorted({a["ayah"] for e in evs for a in e["ayahs"]})
    res = {"answer": text, "citations": citations, "refused": False, "verification_errors": [],
           "intent": intent, "roots": roots,
           "matched": [{"root": it["root"], "via": it["via"], "matched": it["matched"]}
                       for it in (r["direct"] + r["concept"]) if it["root"] in roots],
           "evidence": evs}
    if intent == "concept" and use_llm:
        # A topic word ("disbelievers", "mercy") must not hide the rest of the question: also give the LLM
        # the ayahs closest in meaning, so it can answer from whichever evidence fits.
        ret = retriever or retrieve.get_retriever()
        have = {a["ayah"] for e in evs for a in e["ayahs"]}
        found = [(n, sc) for n, sc in ret.search(q, retrieve.TOP_K)
                 if sc >= retrieve.threshold_low(ret.name) and n not in have]
        if found:
            res["extra"] = ayah_evidence(found)
    return _with_llm(res, q, use_llm, llm_config, llm_transport)
