"""
Evaluate the assistant on eval/questions.jsonl.

    python eval/run_eval.py                       # all questions, default retriever (tfidf)
    python eval/run_eval.py --split dev           # tune on dev ...
    python eval/run_eval.py --split test          # ... and report on test, once, at the end
    python eval/run_eval.py --retriever minilm    # needs requirements-rag.txt
    python eval/run_eval.py --sweep               # threshold sweep on dev (semantic + no_match)
    python eval/run_eval.py -v                    # show every question, not only failures

Metrics (match section 10 of the proposal)
  routing accuracy      did it pick the right intent (single_root / compare / concept / semantic)
  root accuracy         did it find exactly the expected root(s)
  citation validity     share of cited ayahs that exist AND really contain the claimed root
                        (root questions); for semantic answers: precision/hit against hand labels
  refusal accuracy      out_of_scope and no_match questions must be refused
  false refusal rate    answerable questions that were refused
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import queries  # noqa: E402
from rag import retrieve  # noqa: E402
from rag.pipeline import answer  # noqa: E402
from rag.resolve import resolve  # noqa: E402

ANSWERABLE = {"single_root", "compare", "concept", "semantic"}


def load(split):
    qs = [json.loads(l) for l in open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") if l.strip()]
    return [q for q in qs if split == "all" or q["split"] == split]


def root_ayahs(root):
    return {r["ayah"] for r in queries.root_words(root)}


def grade(q, r):
    """Returns (passed, notes, metrics dict)."""
    t, exp, notes = q["type"], q["expect"], []
    m = {"refused": r["refused"]}

    if t in ("out_of_scope", "no_match"):
        ok = r["refused"]
        if not ok:
            notes.append(f"should have refused, answered intent={r['intent']} citations={r['citations']}")
        return ok, notes, m

    if r["refused"]:
        return False, [f"refused (intent={r['intent']}) but should answer"], m

    # A "semantic" question may legitimately be answered via the concept map (e.g. birds -> طير);
    # what matters is that a relevant ayah is cited. Retriever quality is measured separately below.
    m["intent_ok"] = r["intent"] == t or (t == "semantic" and r["intent"] == "concept")
    if not m["intent_ok"]:
        notes.append(f"intent {r['intent']} != {t}")

    if t in ("single_root", "compare"):
        m["roots_ok"] = r["roots"] == exp["roots"] if t == "single_root" else set(r["roots"]) == set(exp["roots"])
        if not m["roots_ok"]:
            notes.append(f"roots {r['roots']} != {exp['roots']}")
    if t == "concept":
        m["roots_ok"] = set(exp["roots_include"]) <= set(r["roots"])
        if not m["roots_ok"]:
            notes.append(f"roots {r['roots']} missing {set(exp['roots_include']) - set(r['roots'])}")

    if t != "semantic":
        # citation validity: every cited ayah exists and contains one of the answer's roots
        valid_ayahs = set().union(*(root_ayahs(x) for x in r["roots"])) if r["roots"] else set()
        cited = set(r["citations"])
        m["cit_total"], m["cit_valid"] = len(cited), len(cited & valid_ayahs)
        if cited != valid_ayahs and not cited <= valid_ayahs:
            notes.append(f"invalid citations {sorted(cited - valid_ayahs)}")
        ok = m["intent_ok"] and m.get("roots_ok", True) and m["cit_valid"] == m["cit_total"]
        return ok, notes, m

    rel, cited = set(exp["relevant"]), set(r["citations"])
    m["hit"] = bool(rel & cited)
    m["precision"] = len(rel & cited) / len(cited) if cited else 0.0
    m["recall"] = len(rel & cited) / len(rel)
    if not m["hit"]:
        notes.append(f"no relevant ayah cited: cited {sorted(cited)} relevant {sorted(rel)}")
    return m["intent_ok"] and m["hit"], notes, m


def retriever_only(retriever, qs):
    """Run the retriever alone on every semantic question: hit@k, precision@k, mean best score."""
    sem = [q for q in qs if q["type"] == "semantic"]
    if not sem:
        return
    hits = prec = p1 = mrr = 0
    print(f"\nretriever alone ({retriever.name}), semantic questions only, top-{retrieve.TOP_K} before any threshold:")
    for q in sem:
        res = retriever.search(q["question"], retrieve.TOP_K)
        got, rel = [n for n, _ in res], set(q["expect"]["relevant"])
        h = bool(rel & set(got))
        hits += h
        prec += len(rel & set(got)) / len(got)
        p1 += got[0] in rel
        mrr += next((1 / (i + 1) for i, n in enumerate(got) if n in rel), 0)
        print(f"  [{'hit ' if h else 'MISS'}] {q['id']} top={[(n, round(sc, 2)) for n, sc in res]} relevant={sorted(rel)}")
    print(f"  hit@{retrieve.TOP_K} {hits}/{len(sem)}   precision@1 {p1/len(sem):.2f}   MRR {mrr/len(sem):.2f}   "
          f"mean precision@{retrieve.TOP_K} {prec/len(sem):.2f}")
    print("  (with 30 ayahs, top-3 is 10% of the surah, so hit@3 flatters; watch precision@1 and MRR)")


def sweep(retriever, split):
    qs = [q for q in load(split) if q["type"] in ("semantic", "no_match")
          and not resolve(q["question"])["direct"] and not resolve(q["question"])["concept"]]
    rows = []
    for q in qs:
        hits = retriever.search(q["question"], retrieve.TOP_K)
        rows.append((q, hits))
    print(f"Threshold sweep, retriever={retriever.name}, split={split}, {len(rows)} questions "
          f"({sum(q['type']=='semantic' for q, _ in rows)} should answer, "
          f"{sum(q['type']=='no_match' for q, _ in rows)} should refuse)\n")
    print("  thr   answered-ok  refused-ok  accuracy")
    best = (-1, None)
    grid = [round(x * 0.02, 2) for x in range(2, 40)]
    for thr in grid:
        a_ok = r_ok = 0
        for q, hits in rows:
            kept = [n for n, sc in hits if sc >= thr]
            if q["type"] == "semantic":
                a_ok += bool(set(kept) & set(q["expect"]["relevant"]))
            else:
                r_ok += not kept
        n_sem = sum(q["type"] == "semantic" for q, _ in rows)
        n_nm = len(rows) - n_sem
        acc = (a_ok + r_ok) / len(rows)
        print(f"  {thr:.2f}   {a_ok:>3}/{n_sem:<3}      {r_ok:>3}/{n_nm:<3}     {acc:.2f}")
        if acc > best[0] + 1e-9:
            best = (acc, thr)
    print(f"\nBest accuracy {best[0]:.2f} first reached at threshold {best[1]} (current setting: "
          f"{retrieve.threshold(retriever.name)}). Ties are common with few questions - prefer the middle of a plateau.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["all", "dev", "test"])
    ap.add_argument("--retriever", default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--llm", action="store_true",
                    help="let the LLM write answers (needs .env). Replies are cached in .llm_cache/, so a re-run is free")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds to wait between LLM questions (rate limits)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    ret = retrieve.get_retriever(a.retriever)

    if a.sweep:
        return sweep(ret, "dev" if a.split == "all" else a.split)

    qs = load(a.split)
    results, passed = [], 0
    for q in qs:
        r = answer(q["question"], retriever=ret, use_llm=a.llm)
        if a.llm and r.get("attempts"):      # only after a real LLM call (not cache-less fallbacks)
            time.sleep(a.delay)
        ok, notes, m = grade(q, r)
        passed += ok
        results.append((q, r, ok, notes, m))
        if a.verbose or not ok:
            print(f"[{'PASS' if ok else 'FAIL'}] {q['id']} ({q['type']}) {q['question']}")
            for n in notes:
                print(f"        - {n}")

    def rate(pred, pool):
        pool = list(pool)
        return f"{sum(map(pred, pool))}/{len(pool)}" if pool else "n/a"

    ans = [x for x in results if x[0]["type"] in ANSWERABLE]
    ref = [x for x in results if x[0]["type"] not in ANSWERABLE]
    root_q = [x for x in ans if x[0]["type"] != "semantic" and not x[1]["refused"]]
    sem_q = [x for x in ans if x[0]["type"] == "semantic" and not x[1]["refused"]]
    print(f"\n=== {len(qs)} questions, split={a.split}, retriever={ret.name}, threshold={retrieve.threshold(ret.name)} ===")
    print(f"overall pass                : {passed}/{len(qs)}")
    print(f"routing (intent) accuracy   : {rate(lambda x: x[4].get('intent_ok', False), ans)}")
    print(f"root accuracy               : {rate(lambda x: x[4].get('roots_ok', False), [y for y in ans if y[0]['type'] in ('single_root','compare','concept')])}")
    print(f"citation validity (roots)   : {sum(x[4].get('cit_valid', 0) for x in root_q)}/{sum(x[4].get('cit_total', 0) for x in root_q)} cited ayahs exist and contain the root")
    if sem_q:
        print(f"semantic hit@{retrieve.TOP_K}            : {rate(lambda x: x[4].get('hit'), sem_q)}   mean precision {sum(x[4]['precision'] for x in sem_q)/len(sem_q):.2f}")
    print(f"refusal accuracy            : {rate(lambda x: x[1]['refused'], ref)}   (out_of_scope + no_match must be refused)")
    print(f"false refusal rate          : {rate(lambda x: x[1]['refused'], ans)}   (answerable but refused)")
    if a.llm:
        gen = [x[1] for x in results if x[1].get("generated_by")]
        by = lambda k: sum(1 for r in gen if r["generated_by"] == k)
        print(f"\nLLM stage: {len(gen)} answers reached it | written by the LLM and verified: {by('llm')} "
              f"| fell back to the database-only answer: {by('template')}")
        from collections import Counter
        why = Counter((r.get("llm_error") or "; ".join(r.get("verification_errors", []))[:160])
                      for r in gen if r["generated_by"] == "template")
        for reason, n in why.most_common():
            print(f"   fallback x{n}: {reason}")
        print(f"   regenerated once: {sum(1 for r in gen if r.get('attempts') == 2 and r['generated_by'] == 'llm')}")
    retriever_only(ret, qs)


if __name__ == "__main__":
    main()
