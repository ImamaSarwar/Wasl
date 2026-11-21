"""
Step 2: turn resolved roots into *evidence*: the only facts the assistant may use.

Every ayah gets an evidence id like "67:3". Counts, forms and ayah lists come straight from the
database, never from a language model. The verifier (later) checks answers against this same data.
"""
from backend import queries


def root_evidence(root):
    """Everything the surah says about one root. Returns None if the root does not occur."""
    rows = queries.root_words(root)
    if not rows:
        return None
    forms = {}
    ayahs = {}
    for r in rows:
        f = forms.setdefault(r["lemma"], {"lemma": r["lemma"], "count": 0, "ayahs": [],
                                          "grammar": [], "words": [], "glosses": []})
        f["count"] += 1
        if r["gloss"] and r["gloss"] not in f["glosses"]:
            f["glosses"].append(r["gloss"])
        if r["ayah"] not in f["ayahs"]:
            f["ayahs"].append(r["ayah"])
        if r["grammar"] not in f["grammar"]:
            f["grammar"].append(r["grammar"])
        f["words"].append(r["word_arabic"])
        a = ayahs.setdefault(r["ayah"], {"id": f"67:{r['ayah']}", "ayah": r["ayah"],
                                         "arabic": r["ayah_arabic"], "translation": r["translation"],
                                         "hits": []})
        a["hits"].append({"word_id": r["word_id"], "word": r["word_arabic"], "lemma": r["lemma"],
                          "grammar": r["grammar"], "gloss": r["gloss"]})
    return {
        "root": root,
        "total": len(rows),
        "forms": sorted(forms.values(), key=lambda f: (-f["count"], f["lemma"])),
        "ayahs": [ayahs[k] for k in sorted(ayahs)],
    }


def compare_evidence(root_a, root_b):
    """Two roots side by side, plus the ayahs where both occur."""
    a, b = root_evidence(root_a), root_evidence(root_b)
    if not a or not b:
        return None
    shared = sorted({x["ayah"] for x in a["ayahs"]} & {x["ayah"] for x in b["ayahs"]})
    return {"a": a, "b": b, "shared_ayahs": shared}


def ayah_evidence(scored):
    """Evidence for semantic hits: [(ayah, score), ...] -> list of ayah dicts (best first)."""
    by = {a["ayah"]: a for a in queries.get_ayahs()}
    return [{"id": f"67:{n}", "ayah": n, "arabic": by[n]["arabic"], "translation": by[n]["translation"],
             "score": round(score, 3)} for n, score in scored]
