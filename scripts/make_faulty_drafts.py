"""
Build eval/faulty_drafts.jsonl: answers a model could plausibly write, half of them wrong in one
specific way, to measure what the verifier (rag/verify.py) catches.

For a sample of roots we write one GOOD draft (must pass) and one FAULTY draft per fault kind
(must be rejected). Kinds marked gap=True are faults the verifier is NOT built to catch yet; they
are in the set on purpose so the report shows the gap instead of hiding it.

Deterministic (seed 67). Re-run only when the database or this script changes:
    python scripts/make_faulty_drafts.py
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.evidence import ayah_evidence, root_evidence  # noqa: E402
from rag.resolve import ALIASES, strip_arabic  # noqa: E402

N_EXTRA = 12   # random single-form roots on top of every root that has 2+ forms
FAKE_PHRASES = ["he who splits the moon", "the keeper of hidden gardens", "a mountain of silver",
                "the people of the white river"]
# fault kind -> (what is wrong, is it a known gap in the verifier?)
KINDS = {
    "cites_ayah_not_in_evidence": (False, "[67:N] points at an ayah outside the evidence"),
    "claim_ayah_not_in_evidence": (False, "a structured claim names an ayah outside the evidence"),
    "root_not_in_that_ayah": (False, "claims the root occurs in an ayah where it does not"),
    "wrong_lemma": (False, "claims a lemma that belongs to another root"),
    "wrong_gloss": (False, "claims a meaning that belongs to another word"),
    "fabricated_english_quote": (False, "quotes a meaning that is in no evidence"),
    "fabricated_arabic_quote": (False, "quotes an Arabic word that is not in the evidence"),
    "wrong_total_count": (False, "states a count that matches nothing in the evidence"),
    "wrong_number": (False, "states a number that matches nothing in the evidence"),
    "ruling": (False, "gives a religious ruling"),
    "no_citation": (False, "cites no ayah at all"),
    "not_json": (False, "answers in plain prose instead of the JSON shape"),
    "bad_shape": (False, "JSON without the required refuse field"),
    "unquoted_fake_arabic": (True, "names another root's Arabic word as if it belonged here, without quotes"),
    "count_of_wrong_form": (True, "gives a real count, but of a different form than the one named"),
}
SEM_KINDS = ["cites_ayah_not_in_evidence", "fabricated_english_quote", "ruling", "no_citation"]


def raw(refuse=False, answer="", claims=None, drop=()):
    d = {"refuse": refuse, "answer": answer, "claims": claims or []}
    for k in drop:
        d.pop(k)
    return json.dumps(d, ensure_ascii=False)


def times(n):
    return "once" if n == 1 else f"{n} times"


def pick_hit(ev, rng):
    hits = [(a["ayah"], h) for a in ev["ayahs"] for h in a["hits"] if h["lemma"] and h["gloss"]]
    return rng.choice(hits) if hits else None


def counts_of(ev):
    return {ev["total"], len(ev["forms"]), len(ev["ayahs"])} | {f["count"] for f in ev["forms"]}


def make_root_drafts(root, other, rng):
    ev, ev2 = root_evidence(root), root_evidence(other)
    ayahs = {a["ayah"] for a in ev["ayahs"]}
    ayah, h = pick_hit(ev, rng)
    lemma, gloss = h["lemma"], h["gloss"]
    claim = {"ayah": ayah, "root": root, "lemma": lemma, "gloss": gloss}
    base = (f"The root {root} occurs {times(ev['total'])} in the surah, for example in [67:{ayah}]. "
            f'The word {lemma} there means "{gloss}".')
    q = f"Where does the root {root} appear?"
    out = []

    def add(kind, text, intent="single_root", roots=None, **kw):
        out.append({"id": f"{root}-{kind}", "root": root, "kind": kind, "intent": intent, "question": q,
                    "roots": roots or [root], "raw": text, "expect": "pass" if kind == "good" else "reject",
                    "gap": KINDS.get(kind, (False,))[0]})

    add("good", raw(answer=base, claims=[claim]))

    outside = [n for n in range(1, 31) if n not in ayahs]
    if outside:
        n = rng.choice(outside)
        add("cites_ayah_not_in_evidence", raw(answer=base.replace(f"[67:{ayah}]", f"[67:{n}]"), claims=[]))
        add("claim_ayah_not_in_evidence", raw(answer=base, claims=[{**claim, "ayah": n}]))
    only2 = [a["ayah"] for a in ev2["ayahs"] if a["ayah"] not in ayahs]
    if only2:
        n = rng.choice(only2)
        add("root_not_in_that_ayah", raw(answer=base.replace(f"[67:{ayah}]", f"[67:{n}]"), claims=[{**claim, "ayah": n}]),
            intent="compare", roots=[root, other])

    h2 = pick_hit(ev2, rng)
    mine = [x for x in ev["ayahs"] if x["ayah"] == ayah][0]["hits"]
    if h2 and h2[1]["lemma"] not in {x["lemma"] for x in mine}:
        add("wrong_lemma", raw(answer=base, claims=[{**claim, "lemma": h2[1]["lemma"]}]))
    if h2 and h2[1]["gloss"] not in {x["gloss"] for x in mine}:
        add("wrong_gloss", raw(answer=base, claims=[{**claim, "gloss": h2[1]["gloss"]}]))

    add("fabricated_english_quote", raw(answer=base + f' It also means "{rng.choice(FAKE_PHRASES)}".', claims=[claim]))
    arabic_here = {strip_arabic(x["word"] or "") for a in ev["ayahs"] for x in a["hits"]} | \
                  {strip_arabic(f["lemma"] or "") for f in ev["forms"]}
    foreign = [f["lemma"] for f in ev2["forms"] if strip_arabic(f["lemma"] or "") not in arabic_here and f["lemma"]]
    if foreign:
        w = rng.choice(foreign)
        add("fabricated_arabic_quote", raw(answer=base + f' It also gives the form "{w}".', claims=[claim]))
        add("unquoted_fake_arabic", raw(answer=base + f" The same root also gives {w} in the surah.", claims=[claim]),
            roots=[root])
    ok = counts_of(ev)
    bad = next(n for n in range(2, 60) if n not in ok and n not in ayahs and n != 67)
    add("wrong_total_count", raw(answer=base.replace(times(ev["total"]), times(bad)), claims=[claim]))
    add("wrong_number", raw(answer=base + f" It is spread over {bad + 40} different ayahs.", claims=[claim]))
    add("ruling", raw(answer=base + " Using this word is not haram.", claims=[claim]))
    add("no_citation", raw(answer=f"The root {root} occurs {times(ev['total'])} in the surah.", claims=[]))
    add("not_json", f"The root {root} appears in ayah {ayah}.")
    add("bad_shape", raw(answer=base, claims=[claim], drop=("refuse",)))

    f_counts = {f["lemma"]: f["count"] for f in ev["forms"]}
    if len(set(f_counts.values())) > 1:
        (la, ca), (lb, cb) = sorted(f_counts.items(), key=lambda kv: kv[1])[::-1][:1] + sorted(f_counts.items(), key=lambda kv: kv[1])[:1]
        if ca != cb:   # state the other form's real count for the form named
            add("count_of_wrong_form", raw(answer=f"The form {lb} appears {times(ca)} in the surah, for example in [67:{ayah}].",
                                           claims=[claim]))
    return out


def make_semantic_drafts(rng):
    from backend import queries
    out = []
    questions = ["Which ayahs talk about the heavens?", "Where does the surah mention warning?",
                 "Which verses describe the punishment of the disbelievers?"]
    n_all = [a["ayah"] for a in queries.get_ayahs()]
    for i, q in enumerate(questions, 1):
        picks = rng.sample(n_all, 3)
        ev = ayah_evidence([(n, 0.5 - 0.05 * j) for j, n in enumerate(picks)])
        a0 = picks[0]
        good = f"Ayah {a0} speaks to this: [67:{a0}]."
        outside = rng.choice([n for n in n_all if n not in picks])

        def add(kind, text):
            out.append({"id": f"sem{i}-{kind}", "root": None, "kind": kind, "intent": "semantic", "question": q,
                        "ayahs": picks, "raw": text, "expect": "pass" if kind == "good" else "reject",
                        "gap": False})
        add("good", raw(answer=good))
        add("cites_ayah_not_in_evidence", raw(answer=f"This is in [67:{outside}]."))
        add("fabricated_english_quote", raw(answer=good + f' It says "{rng.choice(FAKE_PHRASES)}".'))
        add("ruling", raw(answer=good + " This is haram."))
        add("no_citation", raw(answer="Several ayahs speak to this."))
    return out


def main():
    rng = random.Random(67)
    roots = [r for r in sorted(ALIASES) if (e := root_evidence(r)) and any(h["lemma"] and h["gloss"]
             for a in e["ayahs"] for h in a["hits"])]
    multi = [r for r in roots if len(root_evidence(r)["forms"]) >= 2]
    chosen = multi + rng.sample([r for r in roots if r not in multi], N_EXTRA)
    rows = []
    for r in chosen:
        other = rng.choice([x for x in roots if x != r])
        rows += make_root_drafts(r, other, rng)
    rows += make_semantic_drafts(rng)
    path = ROOT / "eval" / "faulty_drafts.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    bad = sum(r["expect"] == "reject" for r in rows)
    print(f"wrote {len(rows)} drafts ({len(rows) - bad} good, {bad} faulty) to {path}")


if __name__ == "__main__":
    main()
