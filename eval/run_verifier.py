"""
How many wrong answers does the verifier catch?

Reads eval/faulty_drafts.jsonl (made by scripts/make_faulty_drafts.py), rebuilds each draft's evidence
from the database, runs rag.verify.check and reports, per fault kind, how many faulty drafts were
rejected, plus how many good drafts were wrongly rejected. Offline, no LLM, no network.

    python -m eval.run_verifier            # summary
    python -m eval.run_verifier --misses   # also list every faulty draft that got through
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from rag import verify  # noqa: E402
from rag.evidence import ayah_evidence, root_evidence  # noqa: E402
from metrics import wilson  # noqa: E402


def load():
    p = ROOT / "eval" / "faulty_drafts.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def evidence_for(row):
    if row["intent"] == "semantic":
        return ayah_evidence([(n, 0.5 - 0.05 * j) for j, n in enumerate(row["ayahs"])])
    return [root_evidence(r) for r in row["roots"]]


def run(rows):
    for r in rows:
        _, errs = verify.check(r["raw"], r["intent"], evidence_for(r), question=r["question"])
        r["errors"], r["rejected"] = errs, bool(errs)
    return rows


def summarize(rows):
    good = [r for r in rows if r["expect"] == "pass"]
    faulty = [r for r in rows if r["expect"] == "reject"]
    by_kind = defaultdict(lambda: [0, 0])
    for r in faulty:
        by_kind[r["kind"]][1] += 1
        by_kind[r["kind"]][0] += r["rejected"]
    designed = [r for r in faulty if not r["gap"]]
    gaps = [r for r in faulty if r["gap"]]
    return {
        "good_total": len(good), "good_wrongly_rejected": sum(r["rejected"] for r in good),
        "faulty_total": len(faulty), "faulty_caught": sum(r["rejected"] for r in faulty),
        "designed_total": len(designed), "designed_caught": sum(r["rejected"] for r in designed),
        "gap_total": len(gaps), "gap_caught": sum(r["rejected"] for r in gaps),
        "by_kind": {k: {"caught": v[0], "total": v[1], "gap": any(r["gap"] for r in faulty if r["kind"] == k)}
                    for k, v in sorted(by_kind.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--misses", action="store_true")
    a = ap.parse_args()
    rows = run(load())
    s = summarize(rows)
    print(f"{len(rows)} drafts: {s['good_total']} good, {s['faulty_total']} faulty\n")
    print(f"{'fault kind':<30}{'caught':>8}{'of':>5}")
    for k, v in s["by_kind"].items():
        print(f"{k:<30}{v['caught']:>8}{v['total']:>5}{'   <- known gap in the verifier' if v['gap'] else ''}")
    lo, hi = wilson(s["designed_caught"], s["designed_total"])
    print(f"\nfaults the verifier is built for : {s['designed_caught']}/{s['designed_total']} caught "
          f"= {s['designed_caught'] / max(1, s['designed_total']):.2f} [{lo:.2f}-{hi:.2f}]")
    print(f"known-gap faults                 : {s['gap_caught']}/{s['gap_total']} caught")
    print(f"all faulty drafts                : {s['faulty_caught']}/{s['faulty_total']} caught")
    print(f"good drafts wrongly rejected     : {s['good_wrongly_rejected']}/{s['good_total']}")
    if a.misses or s["good_wrongly_rejected"]:
        for r in rows:
            if (r["expect"] == "reject" and not r["rejected"]) or (r["expect"] == "pass" and r["rejected"]):
                print(f"\n  [{r['expect']} but {'rejected' if r['rejected'] else 'passed'}] {r['id']}: {r['raw'][:200]}")
                if r["errors"]:
                    print("    errors:", r["errors"])
    (ROOT / "eval" / "results").mkdir(exist_ok=True)
    (ROOT / "eval" / "results" / "verifier.json").write_text(json.dumps(s, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
