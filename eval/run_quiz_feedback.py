"""
Evaluation of the quiz feedback (rag/quiz_feedback.py): Gemini explains a wrong quiz answer from database
evidence, a verifier checks it, and the template explanation is the fallback.

The test set is eval/quiz_feedback_cases.jsonl: wrong answers with their questions, made once with --make
and then kept fixed (15 per question type = 60; grammar split over tense / case / person).

    python -m eval.run_quiz_feedback --make               # (re)create the fixed test set (offline)
    python -m eval.run_quiz_feedback --faulty             # verifier catch rate on broken drafts (offline)
    python -m eval.run_quiz_feedback                      # run Gemini on every case (needs .env)
    python -m eval.run_quiz_feedback --ratings FILE.csv   # summarise a filled-in blind rating sheet

The Gemini run writes, in eval/results/ (git-ignored):
    quiz_feedback_<model>.jsonl        one record per case
    quiz_feedback_rating.csv           blind sheet: for each case the Gemini text and the template text,
                                       in random order, labelled X / Y. A teammate fills in the rating columns.
    quiz_feedback_rating_key.json      which of X / Y was Gemini (do not open it before rating)
Replies are cached in .llm_cache/, so a rerun after a quota error continues where it stopped.
"""
import argparse
import csv
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from backend import quiz  # noqa: E402
from rag import llm, quiz_feedback as qf  # noqa: E402
from metrics import percentile, wilson  # noqa: E402

CASES = ROOT / "eval" / "quiz_feedback_cases.jsonl"
OUT = ROOT / "eval" / "results"
PER_TYPE = 15


def pct(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} (95% CI {lo:.0%}-{hi:.0%})" if n else "0/0"


# ---------- the fixed test set ----------

def make_cases(per_type=PER_TYPE):
    """Wrong answers from intermediate and hard quizzes, one random wrong option per question."""
    rng = random.Random(2026)
    want = {"vocabulary": per_type, "root": per_type, "contextual": per_type}
    kinds = {"tense": per_type // 3, "case": per_type // 3, "person": per_type - 2 * (per_type // 3)}
    rows, seen = [], set()
    for seed in range(1000):
        for q in quiz.build_quiz("hard" if seed % 2 else "intermediate", seed)["questions"]:
            key = q["kind"] if q["type"] == "morphology" else q["type"]
            left = kinds if q["type"] == "morphology" else want
            sig = (q["type"], q.get("kind"), q["word"]["word_id"] if q["word"] else q["root"])
            if left.get(key, 0) <= 0 or sig in seen:
                continue
            chosen = rng.choice([o["id"] for o in q["options"] if o["id"] != q["answer"]])
            seen.add(sig)
            left[key] -= 1
            rows.append({"id": f"qf{len(rows) + 1:02d}", "type": q["type"], "kind": q.get("kind"),
                         "question": q, "chosen": chosen})
        if not any(want.values()) and not any(kinds.values()):
            break
    return rows


def load_cases():
    return [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------- verifier test on broken drafts (offline) ----------

GRAMMAR_LIES = ["dual", "feminine", "plural", "accusative case", "genitive case", "nominative case",
                "past tense", "present tense", "command", "passive", "adjective", "verbal noun"]
FACT_OF = {"dual": "dual", "feminine": "feminine", "plural": "plural", "accusative case": "accusative case",
           "genitive case": "genitive case", "nominative case": "nominative case", "past tense": "past tense",
           "present tense": "present / future tense", "command": "command (imperative)",
           "passive": "passive voice", "adjective": "adjective", "verbal noun": "verbal noun"}


def faulty_drafts(case_row, case):
    """The good (template) draft plus one draft per kind of mistake. -> [(kind, texts, expect_reject)]"""
    good = dict(zip(("why_not", "why_correct"), case["template"]))
    q = case_row["question"]
    out = [("good", good, False)]

    def with_(key, text):
        d = dict(good)
        d[key] = text
        return d

    far = next(n for n in (30, 1, 29, 2) if n not in case["correct"]["ayahs"] + case["chosen"]["ayahs"])
    out.append(("ayah_not_in_evidence", with_("why_correct", good["why_correct"] + f" See [67:{far}]."), True))
    out.append(("invented_quote", with_("why_correct", good["why_correct"] + ' It means "a hidden treasure".'),
                True))
    lie = next((g for g in GRAMMAR_LIES if FACT_OF[g] not in case["correct"]["facts"]), None)
    if lie:
        out.append(("wrong_grammar", with_("why_correct", good["why_correct"] + f" It is {lie} here."), True))
    out.append(("ungrounded_grammar_idea", with_("why_correct", good["why_correct"] + " It is the subject."), True))
    out.append(("count", with_("why_not", good["why_not"] + " This happens three times in the surah."), True))
    out.append(("interpretation", with_("why_not", good["why_not"] + " Scholars interpret it as a warning."), True))
    out.append(("arabic_not_in_evidence", with_("why_correct", good["why_correct"] + " Compare مدرسة."), True))
    if q.get("word"):     # the chosen side talks about the question's word: the polarity mix-up
        out.append(("chosen_side_about_the_word",
                    with_("why_not", f'{q["word"]["arabic"]} is what you chose, so it fits.'), True))
    long_text = good["why_correct"]
    while len(long_text) <= qf.LIMIT:
        long_text += " " + good["why_correct"]
    out.append(("too_long", with_("why_correct", long_text), True))
    return out


def run_faulty(rows, show_misses=False):
    by_kind = defaultdict(lambda: [0, 0])
    misses = []
    for r in rows:
        case = qf.build_case(r["question"], r["chosen"])
        for kind, texts, expect in faulty_drafts(r, case):
            _, errors = qf.check(texts, case)
            by_kind[kind][1] += 1
            by_kind[kind][0] += bool(errors)
            if bool(errors) != expect:
                misses.append((r["id"], kind, texts, errors))
    good_k, good_n = by_kind.pop("good")
    caught = sum(k for k, _ in by_kind.values())
    total = sum(n for _, n in by_kind.values())
    print(f"Verifier on {len(rows)} cases, offline\n")
    print(f"  broken drafts rejected (catch rate): {pct(caught, total)}")
    for kind, (k, n) in sorted(by_kind.items()):
        print(f"    {kind:28s} {pct(k, n)}")
    print(f"  good drafts wrongly rejected:        {pct(good_k, good_n)}")
    if show_misses:
        for m in misses:
            print("\nMISS", m)
    return by_kind, (good_k, good_n)


# ---------- the Gemini run ----------

def run_llm(rows, delay):
    cfg = llm.get_config()
    if cfg is None:
        sys.exit("The LLM is not configured: set LLM_API_KEY and LLM_MODEL in .env")
    OUT.mkdir(exist_ok=True)
    records = []
    for i, r in enumerate(rows, 1):
        started = time.perf_counter()
        res = qf.feedback(r["question"], r["chosen"], use_llm=True, llm_config=cfg)
        seconds = round(time.perf_counter() - started, 3)
        case = qf.build_case(r["question"], r["chosen"])
        cached = llm.LAST_CALL.get("cached", False)
        records.append({"id": r["id"], "type": r["type"], "kind": r["kind"], "model": cfg.model,
                        "generated_by": res["generated_by"], "attempts": res["attempts"],
                        "llm_error": res["llm_error"], "verification_errors": res["verification_errors"],
                        "seconds": seconds, "cached": cached,
                        "tokens_in": llm.LAST_CALL.get("tokens_in", 0), "tokens_out": llm.LAST_CALL.get("tokens_out", 0),
                        "why_not": res["why_not"], "why_correct": res["why_correct"],
                        "template_why_not": case["template"][0], "template_why_correct": case["template"][1]})
        print(f"{i:3d}/{len(rows)} {r['id']} {r['type']:10s} -> {res['generated_by']:8s} "
              f"tries={res['attempts']} {seconds:.1f}s{' (cached)' if cached else ''}"
              + (f"  ERROR {res['llm_error']}" if res["llm_error"] else ""))
        if not cached and i < len(rows):
            time.sleep(delay)          # stay under the free-tier rate limit
    path = OUT / f"quiz_feedback_{cfg.model}.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in records) + "\n", encoding="utf-8")
    summarise(records)
    write_rating_sheet(records)
    print(f"\nSaved {path}")
    return records


def summarise(records):
    n = len(records)
    first = sum(r["generated_by"] == "llm" and r["attempts"] == 1 for r in records)
    llm_ok = sum(r["generated_by"] == "llm" for r in records)
    rejected = sum(bool(r["verification_errors"]) for r in records)
    errors = sum(bool(r["llm_error"]) for r in records)
    print(f"\nQuiz feedback, {n} wrong answers, model {records[0]['model'] if records else '-'}\n")
    print(f"  verified Gemini explanation shown: {pct(llm_ok, n)}")
    print(f"    on the first try:                {pct(first, n)}")
    print(f"    after one retry:                 {pct(llm_ok - first, n)}")
    print(f"  template shown, verifier rejected: {pct(rejected, n)}")
    print(f"  template shown, provider error:    {pct(errors, n)}")
    print("  by question type:")
    for t in ("vocabulary", "root", "morphology", "contextual"):
        mine = [r for r in records if r["type"] == t]
        print(f"    {t:11s} {pct(sum(r['generated_by'] == 'llm' for r in mine), len(mine))}")
    reasons = Counter(e.split(" ", 1)[1] if " " in e else e
                      for r in records for e in r["verification_errors"])
    if reasons:
        print("  most common verifier complaints (final attempt):")
        for text, k in reasons.most_common(6):
            print(f"    {k:3d}  {text[:90]}")
    live = [r["seconds"] for r in records if not r["cached"] and not r["llm_error"]]
    if live:
        print(f"  latency of live calls: p50 {percentile(live, 50):.1f}s, p95 {percentile(live, 95):.1f}s "
              f"(n={len(live)}; includes the retry when there was one)")
    else:
        print("  latency: every reply came from the cache; delete .llm_cache/ entries to time live calls")


def write_rating_sheet(records):
    """Blind A/B sheet: Gemini vs template for every case where Gemini's text was shown."""
    rng = random.Random(7)
    rows, key = [], {}
    for r in records:
        if r["generated_by"] != "llm":
            continue
        pair = [("gemini", r["why_not"], r["why_correct"]),
                ("template", r["template_why_not"], r["template_why_correct"])]
        rng.shuffle(pair)
        for label, (system, why_not, why_correct) in zip("XY", pair):
            key[f"{r['id']}-{label}"] = system
            rows.append({"item": f"{r['id']}-{label}", "type": r["type"], "why_not": why_not,
                         "why_correct": why_correct, "correct_1_0": "", "supported_1_0": "",
                         "helpful_1_to_5": "", "notes": ""})
    with open(OUT / "quiz_feedback_rating.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["item"])
        w.writeheader()
        w.writerows(rows)
    (OUT / "quiz_feedback_rating_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"\nRating sheet: eval/results/quiz_feedback_rating.csv ({len(rows)} rows). Ask a teammate to fill in:\n"
          "  correct_1_0   1 if every statement is true (check the ayah in the app)\n"
          "  supported_1_0 1 if every statement is backed by the database facts shown in the app\n"
          "  helpful_1_to_5 how well it helps a beginner see the difference (5 = very helpful)")


def summarise_ratings(path):
    key = json.loads((OUT / "quiz_feedback_rating_key.json").read_text(encoding="utf-8"))
    by = defaultdict(lambda: {"correct": [], "supported": [], "helpful": []})
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            system = key.get(row["item"])
            for col, name in (("correct_1_0", "correct"), ("supported_1_0", "supported"),
                              ("helpful_1_to_5", "helpful")):
                if system and row.get(col, "").strip():
                    by[system][name].append(float(row[col]))
    for system, m in sorted(by.items()):
        c, s, h = m["correct"], m["supported"], m["helpful"]
        print(f"{system:9s} correct {pct(int(sum(c)), len(c))} | supported {pct(int(sum(s)), len(s))} | "
              f"helpful mean {sum(h) / len(h):.2f} (n={len(h)})" if h else f"{system}: no ratings")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--make", action="store_true", help="create the fixed test set")
    ap.add_argument("--faulty", action="store_true", help="verifier catch rate on broken drafts (offline)")
    ap.add_argument("--misses", action="store_true", help="with --faulty: list drafts the verifier got wrong")
    ap.add_argument("--ratings", metavar="CSV", help="summarise a filled-in rating sheet")
    ap.add_argument("--only", type=int, default=0, metavar="N", help="run only the first N cases")
    ap.add_argument("--delay", type=float, default=4.0, help="seconds between live Gemini calls")
    args = ap.parse_args()

    if args.make:
        rows = make_cases()
        CASES.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"Wrote {len(rows)} cases to {CASES.relative_to(ROOT)}: "
              f"{dict(Counter(r['kind'] or r['type'] for r in rows))}")
        return
    if args.ratings:
        summarise_ratings(args.ratings)
        return
    rows = load_cases()[: args.only or None]
    if args.faulty:
        run_faulty(rows, args.misses)
    else:
        run_llm(rows, args.delay)


if __name__ == "__main__":
    main()
