"""Approximate spelling: rough transliterations resolve, ordinary English and every refusal question do not."""
import json
from pathlib import Path

import pytest

from rag import resolve as R

ROOT = Path(__file__).resolve().parents[1]


def roots(q):
    return [it["root"] for it in R.resolve(q)["direct"]]


@pytest.mark.parametrize("question,root", [
    ('what root gives "mubtala" / "balaa" in this surah, and is it a hollow or sound root?', "بلو"),
    ("What does biyadih mean? How does it translate to 'in whose hands'?", "يدي"),
    ("What does Jahar mean?", "جهر"),
    ("What does Tibaka mean?", "طبق"),
])
def test_rough_spellings_resolve(question, root):
    assert root in roots(question)


@pytest.mark.parametrize("question", [
    "What does series mean?",
    'what is the root of "laser"',
    "Show me a series of verses about mercy",
    "What does the word mouse mean?",
])
def test_common_english_is_not_arabic(question):
    assert roots(question) == []


def test_needs_a_foreign_word_context():
    # same rough spelling, but nothing says it is a word being asked about
    assert roots("Tell me jahar tibaka") == []


def _questions():
    out = []
    for f in ("questions.jsonl", "generated.jsonl"):
        p = ROOT / "eval" / f
        out += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def test_fuzzy_never_turns_a_refusal_into_an_answer(monkeypatch):
    from rag.pipeline import answer
    qs = [q for q in _questions() if q["type"] in ("out_of_scope", "no_match")]
    monkeypatch.setattr(R, "FUZZY", False)
    before = {q["id"]: answer(q["question"])["refused"] for q in qs}
    monkeypatch.setattr(R, "FUZZY", True)
    wrong = [q["id"] for q in qs if before[q["id"]] and not answer(q["question"])["refused"]]
    assert not wrong, wrong


def test_changes_only_add_the_expected_root(monkeypatch):
    qs = _questions()
    monkeypatch.setattr(R, "FUZZY", False)
    before = {q["id"]: roots(q["question"]) for q in qs}
    monkeypatch.setattr(R, "FUZZY", True)
    exp = {q["id"]: set((q.get("expect") or {}).get("roots") or []) for q in qs}
    wrong = {q["id"]: (before[q["id"]], roots(q["question"])) for q in qs
             if not (set(roots(q["question"])) - set(before[q["id"]])) <= exp[q["id"]]
             and q["type"] not in ("out_of_scope", "no_match")}
    assert not wrong, wrong
