"""
Compare the proposed assistant with simpler alternatives on the SAME questions.

    python eval/run_baselines.py --no-llm                  # offline systems only (free, instant)
    python eval/run_baselines.py --delay 4                 # all systems; prompt-only + hybrid_llm call Gemini
    python eval/run_baselines.py --retriever minilm --with-generated --delay 4

Systems
  prompt_only    the LLM with NO retrieval: question in, answer out (the "simpler alternative")
  semantic_only  embedding search over the ayah translations, nothing else
  exact_only     resolver + database lookup only (no semantic search, no LLM)
  hybrid_db      the full routing (exact lookup, concept map, semantic fallback), database-only answer
  hybrid_llm     hybrid_db + LLM wording + verifier (the proposed system)

Ground truth comes from the database (root questions) or hand labels (semantic questions), never from
a model. Metrics: ayah precision (cited ayahs that really contain the root / are labelled relevant),
recall, hit rate, share of stated counts that are right, refusal accuracy, false refusals.
Replies are cached in .llm_cache/, so re-running costs no quota.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import queries  # noqa: E402
from rag import generate, llm, retrieve, verify  # noqa: E402
from rag.evidence import root_evidence  # noqa: E402
from rag.pipeline import answer  # noqa: E402
from rag.resolve import resolve  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
from run_eval import load  # noqa: E402

ROOT_TYPES = {"single_root", "meaning", "compare", "concept"}
REFUSE_TYPES = {"out_of_scope", "no_match"}
ALL_SYSTEMS = ["prompt_only", "semantic_only", "exact_only", "hybrid_db", "hybrid_llm"]

PROMPT_ONLY_SYSTEM = """You answer questions about Surah Al-Mulk (Quran 67, 30 ayahs) for a Quranic Arabic learning tool.
Cite ayahs like [67:3]. Be brief (at most 4 sentences). Politely refuse questions that ask for religious rulings,
that are about other surahs, or that are unrelated to the surah.
Reply with JSON only: {"refuse": false, "answer": "text with [67:N] citations", "ayahs": [3, 5]}
or {"refuse": true, "answer": "", "ayahs": []}."""


def truth_ayahs(q):
    t, e = q["type"], q["expect"]
    if t == "semantic":
        return set(e["relevant"])
    roots = e.get("roots") or e.get("roots_include") or []
    return {r["ayah"] for x in roots for r in queries.root_words(x)}


def true_total(q):
    roots = q["expect"].get("roots") or []
    return len(queries.root_words(roots[0])) if q["type"] in ("single_root", "meaning") and len(roots) == 1 else None


# each system returns {"refused": bool, "cited": set, "text": str, "error": str|None}
def sys_prompt_only(q, ctx):
    try:
        raw = llm.generate_json(PROMPT_ONLY_SYSTEM, q["question"], config=ctx["cfg"])
    except llm.LLMError as e:
        return {"refused": False, "cited": set(), "text": "", "error": str(e)}
    data = generate.parse(raw)
    if not data:
        return {"refused": False, "cited": set(), "text": raw, "error": None}
    cited = set(verify.cited_ayahs({"answer": data.get("answer", ""), "claims": []}))
    for n in data.get("ayahs") or []:
        if isinstance(n, int):
            cited.add(n)
    return {"refused": bool(data.get("refuse")), "cited": cited, "text": data.get("answer", ""), "error": None}


def sys_semantic_only(q, ctx):
    ret = ctx["ret"]
    thr = retrieve.threshold(ret.name)
    hits = [n for n, sc in ret.search(q["question"], retrieve.TOP_K) if sc >= thr]
    return {"refused": not hits, "cited": set(hits), "text": "", "error": None}


def sys_exact_only(q, ctx):
    r = resolve(q["question"])
    roots = [i["root"] for i in r["direct"]][:2] or [i["root"] for i in r["concept"]]
    evs = [e for e in (root_evidence(x) for x in roots) if e]
    return {"refused": not evs, "cited": {a["ayah"] for e in evs for a in e["ayahs"]},
            "text": " ".join(f"{e['total']} times" for e in evs), "error": None}


def _pipeline(use_llm):
    def run(q, ctx):
        r = answer(q["question"], retriever=ctx["ret"], use_llm=use_llm)
        err = r.get("llm_error")
        return {"refused": r["refused"], "cited": set(r["citations"]), "text": r["answer"], "error": err,
                "generated_by": r.get("generated_by"), "reason": r.get("llm_reason"),
                "verification_errors": r.get("verification_errors")}
    return run


SYSTEMS = {"prompt_only": sys_prompt_only, "semantic_only": sys_semantic_only, "exact_only": sys_exact_only,
           "hybrid_db": _pipeline(False), "hybrid_llm": _pipeline(True)}
USES_LLM = {"prompt_only", "hybrid_llm"}


def score(q, out):
    t = q["type"]
    if t in REFUSE_TYPES:
        return {"kind": "refuse", "ok": out["refused"]}
    s = {"kind": "sem" if t == "semantic" else "root", "refused": out["refused"]}
    if out["refused"]:
        return {**s, "precision": 0.0, "recall": 0.0, "hit": False, "count_stated": False, "count_ok": False}
    truth, cited = truth_ayahs(q), out["cited"]
    s["precision"] = len(cited & truth) / len(cited) if cited else 0.0
    s["recall"] = len(cited & truth) / len(truth) if truth else 0.0
    s["hit"] = bool(cited & truth)
    total = true_total(q)
    nums = set()
    for m in verify.COUNT_PHRASE.finditer(out["text"]):
        w = m.group(2) or m.group(1)
        nums.add(int(w) if w.isdigit() else verify.NUMWORDS.get(w.lower()))
    s["count_stated"] = total is not None and bool(nums)
    s["count_ok"] = s["count_stated"] and total in nums
    return s


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def report(name, rows):
    root = [s for s in rows if s["kind"] == "root"]
    sem = [s for s in rows if s["kind"] == "sem"]
    ref = [s for s in rows if s["kind"] == "refuse"]
    ans = root + sem
    cs = [s for s in root if s["count_stated"]]
    f = lambda v: "  n/a" if v != v else f"{v:5.2f}"
    return (f"{name:<14}| {f(mean(s['precision'] for s in root))} {f(mean(s['recall'] for s in root))} "
            f"| {f(mean(s['hit'] for s in sem))} {f(mean(s['precision'] for s in sem))} "
            f"| {sum(s['count_ok'] for s in cs):>3}/{len(cs):<3} "
            f"| {sum(s['ok'] for s in ref):>3}/{len(ref):<3} | {sum(s['refused'] for s in ans):>3}/{len(ans):<3}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retriever", default=None)
    ap.add_argument("--with-generated", action="store_true")
    ap.add_argument("--systems", nargs="*", default=ALL_SYSTEMS, choices=ALL_SYSTEMS)
    ap.add_argument("--no-llm", action="store_true", help="skip the systems that call the LLM")
    ap.add_argument("--delay", type=float, default=3.0)
    a = ap.parse_args()

    systems = [s for s in a.systems if not (a.no_llm and s in USES_LLM)]
    files = ("questions.jsonl", "generated.jsonl") if a.with_generated else ("questions.jsonl",)
    qs = load("all", files)
    ctx = {"ret": retrieve.get_retriever(a.retriever), "cfg": llm.get_config()}
    if any(s in USES_LLM for s in systems) and ctx["cfg"] is None:
        sys.exit("The LLM is not configured (.env). Use --no-llm for the offline systems.")

    results, raw = {}, {}
    for name in systems:
        rows, errors, streak = [], 0, 0
        for i, q in enumerate(qs, 1):
            out = SYSTEMS[name](q, ctx)
            if out.get("error"):
                errors, streak = errors + 1, streak + 1
                if streak >= 3 and name in USES_LLM:
                    sys.exit(f"{name}: 3 provider errors in a row ({out['error']}). Stopping; try again later "
                             f"or switch LLM_MODEL. Replies so far are cached, so nothing is lost.")
            else:
                streak = 0
            rows.append(score(q, out))
            raw.setdefault(name, []).append({"id": q["id"], "type": q["type"], "refused": out["refused"],
                                             "cited": sorted(out["cited"]), "generated_by": out.get("generated_by"),
                                             "error": out.get("error"), "reason": out.get("reason"),
                                             "verification_errors": out.get("verification_errors")})
            if name in USES_LLM:
                time.sleep(a.delay)
            if i % 20 == 0:
                print(f"  {name}: {i}/{len(qs)}", flush=True)
        results[name] = (rows, errors)

    n = {k: sum(1 for q in qs if (q["type"] in ROOT_TYPES if k == "root" else q["type"] == "semantic" if k == "sem" else q["type"] in REFUSE_TYPES)) for k in ("root", "sem", "ref")}
    print(f"\n{len(qs)} questions: {n['root']} root/word, {n['sem']} meaning-search, {n['ref']} must-refuse "
          f"| retriever={ctx['ret'].name}")
    print(f"{'system':<14}| root questions  | meaning search | counts right | refusals ok | false refusals")
    print(f"{'':<14}| prec   recall  | hit   prec     | (of stated)  | (must refuse)| (answerable)")
    print("-" * 96)
    for name, (rows, errors) in results.items():
        print(report(name, rows) + (f"   [{errors} provider errors]" if errors else ""))
    if "hybrid_llm" in raw:
        text = {q["id"]: q["question"] for q in qs}
        bad = [x for x in raw["hybrid_llm"]
               if (x["refused"] and x["type"] in ROOT_TYPES | {"semantic"}) or x["generated_by"] == "template"]
        if bad:
            print("\nhybrid_llm: answerable questions that were refused or fell back to the database answer:")
            for x in bad:
                why = x.get("reason") or x.get("error") or "; ".join(x.get("verification_errors") or []) or "?"
                kind = "refused " if x["refused"] else "fallback"
                print(f"  [{kind}] {x['id']} {text[x['id']]}\n             {why[:200]}")
    out = ROOT / "eval" / "results"
    out.mkdir(exist_ok=True)
    (out / "baselines.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nper-question details: {out / 'baselines.json'}")


if __name__ == "__main__":
    main()
