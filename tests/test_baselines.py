import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_baselines as rb  # noqa: E402
from backend import queries  # noqa: E402
from rag import llm  # noqa: E402
from rag.resolve import resolve  # noqa: E402


def test_generated_questions_are_labelled_from_the_database():
    import make_eval_set
    make_eval_set.main()
    qs = [json.loads(l) for l in open(ROOT / "eval" / "generated.jsonl", encoding="utf-8")]
    assert len(qs) >= 100
    assert len({q["id"] for q in qs}) == len(qs)
    for q in qs:
        assert all(queries.root_words(r) for r in q["expect"]["roots"])   # every gold root exists


def test_generated_questions_are_deterministic():
    import make_eval_set
    path = ROOT / "eval" / "generated.jsonl"
    make_eval_set.main()
    first = path.read_text(encoding="utf-8")
    make_eval_set.main()
    assert path.read_text(encoding="utf-8") == first


def test_exact_spelling_resolves_word_forms_the_loose_key_cannot():
    # the loose key (vowels collapsed, ayn dropped) collides for these; the exact spelling does not
    assert resolve("Tell me about the word ʿaliym")["direct"][0]["root"] == "علم"
    assert resolve("Tell me about the word aajr")["direct"][0]["root"] == "أجر"


def test_short_word_forms_resolve():
    assert resolve("What does the word waʿd mean?")["direct"][0]["root"] == "وعد"


def test_score_penalises_cited_ayahs_that_do_not_contain_the_root():
    q = {"type": "single_root", "expect": {"roots": ["خلق"]}}
    truth = rb.truth_ayahs(q)
    good = rb.score(q, {"refused": False, "cited": set(truth), "text": ""})
    bad = rb.score(q, {"refused": False, "cited": set(truth) | {99}, "text": ""})
    assert good["precision"] == 1.0 and good["recall"] == 1.0
    assert bad["precision"] < 1.0 and bad["recall"] == 1.0


def test_score_checks_stated_counts():
    q = {"type": "single_root", "expect": {"roots": ["خلق"]}}
    total = rb.true_total(q)
    ok = rb.score(q, {"refused": False, "cited": {1}, "text": f"it occurs {total} times"})
    wrong = rb.score(q, {"refused": False, "cited": {1}, "text": f"it occurs {total + 5} times"})
    assert ok["count_ok"] and wrong["count_stated"] and not wrong["count_ok"]


def test_prompt_only_system_reads_the_models_json(monkeypatch):
    reply = json.dumps({"refuse": False, "answer": "Seen in [67:3] and ayah 4.", "ayahs": [5]})
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: reply)
    out = rb.sys_prompt_only({"question": "x"}, {"cfg": object()})
    assert out["cited"] == {3, 4, 5} and not out["refused"]
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: json.dumps({"refuse": True, "answer": "", "ayahs": []}))
    assert rb.sys_prompt_only({"question": "x"}, {"cfg": object()})["refused"]


def test_prompt_only_survives_an_llm_failure(monkeypatch):
    def boom(*a, **k):
        raise llm.LLMError("HTTP 503: provider error")
    monkeypatch.setattr(llm, "generate_json", boom)
    out = rb.sys_prompt_only({"question": "x"}, {"cfg": object()})
    assert out["error"] and out["cited"] == set()


def test_prompt_tells_the_model_how_the_question_was_matched():
    from rag import generate
    ev = [{"root": "شيأ", "total": 3, "forms": [], "ayahs": []}]
    matched = [{"root": "شيأ", "via": "lemma", "matched": "shaa"}]
    text = generate.build_user_prompt("Which root does shaa come from?", "single_root", ev, matched=matched)
    assert 'MATCHED: "shaa" -> root شيأ' in text and "word form" in text
    assert "MATCHED" not in generate.build_user_prompt("q", "single_root", ev)


def test_an_llm_refusal_keeps_its_reason():
    from rag import pipeline

    class Fake:
        def __call__(self, url, headers, body):
            reply = {"refuse": True, "answer": "", "claims": [], "reason": "no relevant ayah"}
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(reply)}]}}]})
    cfg = llm.Config("gemini", "k", "m")
    r = pipeline.answer("What does the root khalaq mean?", use_llm=True, llm_config=cfg, llm_transport=Fake())
    assert r["refused"] and r["generated_by"] == "llm" and r["llm_reason"] == "no relevant ayah"


def test_generated_sample_is_even_and_deterministic(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_baselines.py", "--no-llm", "--with-generated",
                                      "--generated-sample", "25", "--systems", "exact_only"])
    rb.main()
    out = capsys.readouterr().out
    assert "questions:" in out
    n = int(out.split("questions:")[0].split()[-1])
    hand = sum(1 for l in open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") if l.strip())
    assert n == hand + 25
