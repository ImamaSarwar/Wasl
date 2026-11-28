"""
Which retrieval variant finds the right ayah for a meaning question? Offline, no LLM, no API key.

    python scripts/compare_retrievers.py            # summary
    python scripts/compare_retrievers.py -v         # also every question a variant misses at top 3

Variants (all MiniLM unless noted):
  translation   the ayah translation only. This is what Wasl uses today.
  +glosses      translation + the word-by-word meanings of that ayah ("an inhaling", "boils up", ...).
  rrf           translation ranking fused with the TF-IDF ranking (reciprocal rank fusion).
  +glosses rrf  both of the above.

It reports hit@1 / hit@3 / hit@5 / MRR on the answerable meaning questions in eval/questions.jsonl, and a
safety check: how many must-refuse questions (no_match) would still be answered at the current thresholds.
Those 45 questions were used to tune Wasl, so these numbers are development numbers, not a fresh test.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import queries  # noqa: E402
from rag import retrieve  # noqa: E402

HIGH, LOW = retrieve.THRESHOLDS["minilm"], retrieve.THRESHOLDS_LOW["minilm"]


def load_questions():
    rows = [json.loads(l) for l in (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    return ([q for q in rows if q["type"] == "semantic" and q["expect"].get("relevant")],
            [q for q in rows if q["type"] == "no_match"])


def glosses_by_ayah():
    out = {}
    for r in queries._rows("SELECT ayah, gloss FROM words WHERE gloss IS NOT NULL ORDER BY ayah, pos"):
        out.setdefault(r["ayah"], []).append(r["gloss"])
    return {a: " ".join(g) for a, g in out.items()}


def rrf(rankings, k=60):
    score = {}
    for ranking in rankings:
        for pos, ayah in enumerate(ranking):
            score[ayah] = score.get(ayah, 0.0) + 1.0 / (k + pos + 1)
    return sorted(score, key=score.get, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    from sentence_transformers import SentenceTransformer
    ayahs = queries.get_ayahs()
    ids = [x["ayah"] for x in ayahs]
    gl = glosses_by_ayah()
    model = SentenceTransformer(retrieve.MiniLMRetriever.MODEL, device="cpu")
    emb_t = model.encode([x["translation"] for x in ayahs], normalize_embeddings=True)
    emb_g = model.encode([x["translation"] + " " + gl.get(x["ayah"], "") for x in ayahs], normalize_embeddings=True)
    tfidf = retrieve.TfidfRetriever()

    def cos(emb, q):
        return emb @ model.encode([q], normalize_embeddings=True)[0]

    def rank_from_scores(s):
        return [ids[i] for i in np.argsort(-s)]

    def variant(name, q):
        """-> (ranking best-first, best cosine score used for the thresholds)"""
        st, sg = cos(emb_t, q), cos(emb_g, q)
        t_rank = [n for n, _ in tfidf.search(q, len(ids))]
        if name == "translation":
            return rank_from_scores(st), float(st.max())
        if name == "+glosses":
            return rank_from_scores(sg), float(sg.max())
        if name == "rrf":
            return rrf([rank_from_scores(st), t_rank]), float(st.max())
        return rrf([rank_from_scores(sg), t_rank]), float(sg.max())

    names = ["translation", "+glosses", "rrf", "+glosses rrf"]
    answerable, refuse = load_questions()
    print(f"{len(answerable)} answerable meaning questions, {len(refuse)} must-refuse (no_match) questions\n")
    print(f"{'variant':<14}| hit@1  hit@3  hit@5   MRR  | must-refuse answered (>= {HIGH}) / borderline (>= {LOW})"
          f" | answerable lost (< {LOW})")
    print("-" * 112)
    for name in names:
        h1 = h3 = h5 = 0
        rr = 0.0
        missed, lost = [], 0
        for q in answerable:
            rel = set(q["expect"]["relevant"])
            ranking, best = variant(name, q["question"])
            pos = next((i for i, n in enumerate(ranking, 1) if n in rel), None)
            h1 += pos == 1
            h3 += bool(pos and pos <= 3)
            h5 += bool(pos and pos <= 5)
            rr += 1 / pos if pos else 0
            lost += best < LOW
            if not (pos and pos <= 3):
                missed.append((q["id"], pos, q["question"]))
        hi = lo = 0
        for q in refuse:
            _, best = variant(name, q["question"])
            hi += best >= HIGH
            lo += best >= LOW
        n = len(answerable)
        print(f"{name:<14}| {h1:>2}/{n}  {h3:>2}/{n}  {h5:>2}/{n}  {rr / n:.2f}  | "
              f"{hi:>2}/{len(refuse)} / {lo:>2}/{len(refuse)}"
              f"{'':<27}| {lost}/{n}")
        if a.verbose:
            for qid, pos, text in missed:
                print(f"    miss@3 {qid} (right ayah at rank {pos}): {text}")
    print("\nThe cosine thresholds were tuned for the 'translation' variant; a variant that changes the score "
          "scale (+glosses) may need its own thresholds, so read the two safety columns before choosing.")


if __name__ == "__main__":
    main()
