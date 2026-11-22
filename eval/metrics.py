"""
Numbers for the evaluation write-up: confidence intervals, latency, token cost, and a grouped error analysis.
Pure functions (no network, no database), so they are easy to test.
"""
import math
import random

REFUSE_TYPES = {"out_of_scope", "no_match"}
ROOT_TYPES = {"single_root", "meaning", "compare", "concept"}


def wilson(k, n, z=1.96):
    """95% Wilson interval for a rate k/n. Returns (low, high); (nan, nan) when n == 0."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_mean(xs, resamples=2000, seed=0):
    """(mean, low, high) with a seeded percentile bootstrap, for averages such as precision."""
    xs = list(xs)
    if not xs:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(resamples))
    return sum(xs) / len(xs), means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def percentile(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def cost_usd(tokens_in, tokens_out, price_in_per_m, price_out_per_m):
    """Cost of a call. Prices are USD per million tokens and are supplied by the user, never assumed."""
    return tokens_in * price_in_per_m / 1e6 + tokens_out * price_out_per_m / 1e6


def classify_failure(q, rec, truth=None):
    """
    Why did this question go wrong? Returns a cause string, or None when the answer is acceptable.
    `rec` is one per-question record from run_baselines (refused, intent, roots, cited, generated_by, ...).
    """
    t = q["type"]
    if t in REFUSE_TYPES:
        if rec["refused"]:
            return None
        return f"should refuse but answered (through the {rec.get('intent') or 'unknown'} path)"
    if rec["refused"]:
        if rec.get("generated_by") == "llm":
            return "the LLM refused although evidence was retrieved"
        if t == "semantic":
            return "refused before the LLM: best similarity below the threshold (or an unrelated route)"
        return "refused before the LLM: the word or root was not recognised"
    cited = set(rec.get("cited") or [])
    expected_roots = q["expect"].get("roots")
    if expected_roots is not None and t != "concept" and rec.get("roots") is not None:
        if not rec["roots"]:
            return "the word or root was not recognised (fell through to semantic search)"
        if set(rec["roots"]) != set(expected_roots):
            return "wrong root resolved"
    if t == "concept":   # a topic word legitimately brings in more than one root, so only a total miss counts
        return None if truth is None or cited & set(truth) else "the right ayah was not cited"
    if t == "semantic":
        if truth is not None and not (cited & set(truth)):
            via = rec.get("intent")
            return "the right ayah was not cited" + (f" (answered through the {via} path)" if via != "semantic" else
                                                      " (retrieval missed it)")
        return None
    if truth is not None and cited and not cited <= set(truth):
        return "cited an ayah that does not contain the root"
    return None


def group_failures(failures):
    """[(cause, id, question)] -> {cause: [(id, question), ...]} ordered by size."""
    groups = {}
    for cause, qid, text in failures:
        groups.setdefault(cause, []).append((qid, text))
    return dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))
