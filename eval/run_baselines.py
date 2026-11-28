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
import os
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
from metrics import (bootstrap_mean, classify_failure, cost_usd, group_failures, percentile, wilson)  # noqa: E402
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
    c = llm.LAST_CALL
    usage = {"calls": 1, "latency": c["latency"], "cached_latency": c["latency"] if c["cached"] else 0.0,
             "tokens_in": c["tokens_in"], "tokens_out": c["tokens_out"],
             "unmeasured": 0 if c.get("measured", True) else 1}
    data = generate.parse(raw)
    if not data:
        return {"refused": False, "cited": set(), "text": raw, "error": None, "usage": usage}
    cited = set(verify.cited_ayahs({"answer": data.get("answer", ""), "claims": []}))
    for n in data.get("ayahs") or []:
        if isinstance(n, int):
            cited.add(n)
    return {"refused": bool(data.get("refuse")), "cited": cited, "text": data.get("answer", ""), "error": None,
            "usage": usage}


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
                "verification_errors": r.get("verification_errors"), "intent": r.get("intent"),
                "roots": r.get("roots"), "usage": r.get("llm_stats"), "retrieved": r.get("retrieved")}
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


def _fmt(rate, lo, hi):
    return f"{rate:.2f} [{lo:.2f}-{hi:.2f}]"


def summarise(qs, results, raw, ctx):
    """Every number the slides need, with 95% intervals. Prices come from the environment, never assumed."""
    price_in = float(os.environ.get("LLM_PRICE_IN_PER_M", "nan"))
    price_out = float(os.environ.get("LLM_PRICE_OUT_PER_M", "nan"))
    by_id = {q["id"]: q for q in qs}
    out = {"questions": len(qs), "retriever": ctx["ret"].name,
           "threshold": retrieve.threshold(ctx["ret"].name),
           "model": ctx["cfg"].model if ctx["cfg"] else None,
           "by_type": {t: sum(1 for q in qs if q["type"] == t) for t in sorted({q["type"] for q in qs})},
           "systems": {}}
    for name, (rows, errors) in results.items():
        root = [s for s in rows if s["kind"] == "root"]
        sem = [s for s in rows if s["kind"] == "sem"]
        ref = [s for s in rows if s["kind"] == "refuse"]
        ans = root + sem
        cs = [s for s in root if s["count_stated"]]
        recs = raw[name]
        lat = [r["latency_s"] for r in recs if r["measured"]]
        llm_all = [r for r in recs if r["llm_calls"]]
        llm_recs = [r for r in llm_all if r["measured"]]   # replies cached before timing existed have no numbers
        tin = sum(r["tokens_in"] for r in llm_recs)
        tout = sum(r["tokens_out"] for r in llm_recs)
        entry = {
            "root_precision": bootstrap_mean([s["precision"] for s in root]),
            "root_recall": bootstrap_mean([s["recall"] for s in root]),
            "meaning_hit": [sum(s["hit"] for s in sem), len(sem), *wilson(sum(s["hit"] for s in sem), len(sem))],
            "counts_right": [sum(s["count_ok"] for s in cs), len(cs), *wilson(sum(s["count_ok"] for s in cs), len(cs))],
            "refusals_ok": [sum(s["ok"] for s in ref), len(ref), *wilson(sum(s["ok"] for s in ref), len(ref))],
            "false_refusals": [sum(s["refused"] for s in ans), len(ans),
                               *wilson(sum(s["refused"] for s in ans), len(ans))],
            "latency_median_s": percentile(lat, 50), "latency_p95_s": percentile(lat, 95),
            "llm_calls": sum(r["llm_calls"] for r in recs),
            "llm_questions": len(llm_all), "llm_questions_measured": len(llm_recs),
            "tokens_in": tin, "tokens_out": tout,
            "tokens_per_llm_question": (tin + tout) / len(llm_recs) if llm_recs else 0,
            "cost_usd_total": cost_usd(tin, tout, price_in, price_out) if price_in == price_in and price_out == price_out else None,
            "provider_errors": errors,
        }
        if entry["cost_usd_total"] is not None and llm_recs:
            entry["cost_usd_per_llm_question"] = entry["cost_usd_total"] / len(llm_recs)
        gen = [r for r in recs if r.get("generated_by")]
        if gen:
            entry["llm_verified"] = sum(1 for r in gen if r["generated_by"] == "llm")
            entry["fell_back_to_database"] = sum(1 for r in gen if r["generated_by"] == "template")
        out["systems"][name] = entry
    return out


def print_summary(sm):
    print("\nWith 95% intervals (precision and recall: bootstrap; rates: Wilson):")
    for name, e in sm["systems"].items():
        print(f"  {name}")
        print(f"    root precision {_fmt(*e['root_precision'])}   recall {_fmt(*e['root_recall'])}")
        for label, key in (("meaning-search hit", "meaning_hit"), ("counts right", "counts_right"),
                           ("refusals correct", "refusals_ok"), ("false refusals", "false_refusals")):
            k, n, lo, hi = e[key]
            if n:
                print(f"    {label}: {k}/{n} = {_fmt(k / n, lo, hi)}")
        ms = lambda v: f"{v * 1000:.0f} ms" if v < 1 else f"{v:.2f} s"
        print(f"    latency per question: median {ms(e['latency_median_s'])}, 95th percentile {ms(e['latency_p95_s'])}")
        if e["llm_calls"]:
            cost = (f", cost ${e['cost_usd_total']:.4f} in total" if e["cost_usd_total"] is not None
                    else " (set LLM_PRICE_IN_PER_M and LLM_PRICE_OUT_PER_M to see cost)")
            print(f"    LLM: {e['llm_calls']} calls, {e['tokens_in']} tokens in, {e['tokens_out']} out{cost}")
            if e["llm_questions_measured"] < e["llm_questions"]:
                print(f"    (latency and tokens cover {e['llm_questions_measured']} of {e['llm_questions']} LLM questions; "
                      f"older cached replies have no timing. Delete .llm_cache to measure all, using quota.)")


def error_analysis(qs, raw, system):
    """Group the failures of one system by cause (resolver, threshold, LLM refusal, gate gap, ...)."""
    by_id = {q["id"]: q for q in qs}
    failures = []
    for rec in raw[system]:
        q = by_id[rec["id"]]
        cause = classify_failure(q, rec, truth_ayahs(q) if q["type"] in ROOT_TYPES | {"semantic"} else None)
        if cause:
            failures.append((cause, q["id"], q["question"]))
    groups = group_failures(failures)
    total = len(failures)
    print(f"\nError analysis for {system}: {total} failures in {len(groups)} groups")
    for cause, items in groups.items():
        print(f"  {len(items):>3}  {cause}")
        for qid, text in items[:3]:
            print(f"         {qid}: {text[:90]}")
    return {"system": system, "failures": total,
            "groups": {c: [{"id": i, "question": t} for i, t in items] for c, items in groups.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retriever", default=None)
    ap.add_argument("--with-generated", action="store_true")
    ap.add_argument("--generated-sample", type=int, default=0, metavar="N",
                    help="with --with-generated: use only N of the generated questions (evenly spread), "
                         "to save LLM quota")
    ap.add_argument("--only", nargs="*", default=None, metavar="TYPE",
                    help="use only these question types, e.g. --only semantic out_of_scope no_match "
                         "(saves LLM quota when you are testing one part)")
    ap.add_argument("--systems", nargs="*", default=ALL_SYSTEMS, choices=ALL_SYSTEMS)
    ap.add_argument("--no-llm", action="store_true", help="skip the systems that call the LLM")
    ap.add_argument("--delay", type=float, default=3.0)
    a = ap.parse_args()

    systems = [s for s in a.systems if not (a.no_llm and s in USES_LLM)]
    files = ("questions.jsonl", "generated.jsonl") if a.with_generated else ("questions.jsonl",)
    qs = load("all", files)
    if a.only:
        qs = [q for q in qs if q["type"] in a.only]
    if a.generated_sample:
        gen = [q for q in qs if q["split"] == "gen"]
        keep = {q["id"] for q in gen[::max(1, len(gen) // a.generated_sample)][:a.generated_sample]}
        qs = [q for q in qs if q["split"] != "gen" or q["id"] in keep]
    ctx = {"ret": retrieve.get_retriever(a.retriever), "cfg": llm.get_config()}
    if any(s in USES_LLM for s in systems) and ctx["cfg"] is None:
        sys.exit("The LLM is not configured (.env). Use --no-llm for the offline systems.")

    results, raw = {}, {}
    for name in systems:
        rows, errors, streak = [], 0, 0
        for i, q in enumerate(qs, 1):
            t0 = time.perf_counter()
            out = SYSTEMS[name](q, ctx)
            wall = time.perf_counter() - t0
            usage = out.get("usage") or {}
            # a cached reply costs no time now, so add back the time it took when it was first made
            latency = wall + usage.get("cached_latency", 0.0)
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
                                             "verification_errors": out.get("verification_errors"),
                                             "intent": out.get("intent"), "roots": out.get("roots"),
                                             "retrieved": out.get("retrieved"),
                                             "latency_s": round(latency, 3),
                                             "llm_calls": usage.get("calls", 0),
                                             "measured": not usage.get("unmeasured", 0),
                                             "tokens_in": usage.get("tokens_in", 0),
                                             "tokens_out": usage.get("tokens_out", 0)})
            # pause only after a live call (a cached reply takes no time, so there is nothing to space out)
            if name in USES_LLM and (wall > 0.4 or out.get("error")):
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
    summary = summarise(qs, results, raw, ctx)
    print_summary(summary)
    focus = next((n for n in ("hybrid_llm", "hybrid_db") if n in raw), list(raw)[-1])
    errors_by_cause = error_analysis(qs, raw, focus)
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "error_analysis.json").write_text(json.dumps(errors_by_cause, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
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
