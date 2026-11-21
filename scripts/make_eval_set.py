"""
Generate labelled evaluation questions from the verified database (no hand labelling, no LLM).

    python scripts/make_eval_set.py          # writes eval/generated.jsonl

The correct answer to each question is known by construction (the root comes from the database),
so these questions measure root identification at scale. Fixed seed -> same file every time.
Hand-written questions (eval/questions.jsonl) cover meaning search, refusals and tricky cases.
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import queries  # noqa: E402

N_EACH = 25   # per question kind

ARABIC = ["ما هي الآيات التي فيها الجذر {r}؟", "Where does the root {r} appear in the surah?",
          "Show me every ayah that uses the root {r}", "How is the root {r} used in Surah Al-Mulk?",
          "Which forms of {r} occur in this surah?"]
LATIN = ["Where does the root {r} appear?", "How many times is the root {r} used and in which forms?",
         "Show me the ayahs using the root {r}", "Which forms of the root {r} are in the surah?",
         "Tell me about the root {r}"]
MEANING = ["What does the root {r} mean?", "What is the meaning of the root {r} in this surah?"]
WORD = ["What does the word {w} mean?", "Which root does the word {w} come from?",
        "Tell me about the word {w}"]
COMPARE = ["Compare the roots {a} and {b}", "What is the difference between {a} and {b} in this surah?",
           "How do {a} and {b} differ in usage?"]


def main():
    rng = random.Random(67)
    aliases = json.load(open(ROOT / "rag" / "aliases.json", encoding="utf-8"))
    roots = sorted(aliases)
    counts = {r: len(queries.root_words(r)) for r in roots}
    lat = Counter(a["latin"] for a in aliases.values())
    unique_lat = [r for r in roots if lat[aliases[r]["latin"]] == 1 and aliases[r]["latin"] != aliases[r]["buckwalter"]]
    lemma_lat = Counter(l for a in aliases.values() for l in a["lemmas"].values())
    out, n = [], 0

    def add(kind, question, expect):
        nonlocal n
        n += 1
        out.append({"id": f"g{n:03d}", "type": kind, "question": question, "split": "gen", "expect": expect})

    for r in rng.sample(roots, N_EACH):
        add("single_root", rng.choice(ARABIC).format(r=r), {"roots": [r]})
    for r in rng.sample(unique_lat, N_EACH):
        add("single_root", rng.choice(LATIN).format(r=aliases[r]["latin"]), {"roots": [r]})
    for r in rng.sample(unique_lat, N_EACH):
        add("meaning", rng.choice(MEANING).format(r=aliases[r]["latin"]), {"roots": [r]})
    words = [(r, l) for r in roots for l in aliases[r]["lemmas"].values() if lemma_lat[l] == 1 and len(l) > 3]
    for r, l in rng.sample(words, N_EACH):
        q = rng.choice(WORD).format(w=l)
        add("meaning" if "mean" in q else "single_root", q, {"roots": [r]})
    multi = [r for r in unique_lat if counts[r] >= 2]
    for _ in range(N_EACH):
        a, b = rng.sample(multi, 2)
        add("compare", rng.choice(COMPARE).format(a=aliases[a]["latin"], b=aliases[b]["latin"]), {"roots": [a, b]})

    path = ROOT / "eval" / "generated.jsonl"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for q in out:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"wrote {len(out)} questions to {path}")


if __name__ == "__main__":
    main()
