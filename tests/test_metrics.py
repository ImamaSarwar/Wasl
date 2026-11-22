import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import metrics  # noqa: E402
from rag import llm  # noqa: E402


def test_wilson_interval_contains_the_rate_and_stays_in_range():
    lo, hi = metrics.wilson(5, 10)
    assert 0.23 < lo < 0.25 and 0.75 < hi < 0.77
    assert metrics.wilson(0, 10)[0] == 0.0 and metrics.wilson(10, 10)[1] == 1.0
    assert math.isnan(metrics.wilson(0, 0)[0])


def test_bootstrap_is_deterministic_and_brackets_the_mean():
    xs = [1.0, 1.0, 0.0, 1.0, 0.5, 1.0, 0.0, 1.0]
    a, b = metrics.bootstrap_mean(xs), metrics.bootstrap_mean(xs)
    assert a == b and a[1] <= a[0] <= a[2]
    assert metrics.bootstrap_mean([1.0] * 5) == (1.0, 1.0, 1.0)


def test_percentile_and_cost():
    assert metrics.percentile([1, 2, 3, 4, 5], 50) == 3
    assert abs(metrics.percentile([0, 10], 95) - 9.5) < 1e-9
    assert abs(metrics.cost_usd(1_000_000, 500_000, 0.10, 0.40) - 0.30) < 1e-9


def _q(t, **e):
    return {"id": "x", "type": t, "question": "q", "expect": e}


def test_classify_failure_causes():
    c = metrics.classify_failure
    assert c(_q("no_match", refused=True), {"refused": True}) is None
    assert "should refuse" in c(_q("no_match", refused=True), {"refused": False, "intent": "concept"})
    assert "LLM refused" in c(_q("semantic", relevant=[1]), {"refused": True, "generated_by": "llm"}, [1])
    assert "threshold" in c(_q("semantic", relevant=[1]), {"refused": True, "generated_by": None}, [1])
    assert "not recognised" in c(_q("meaning", roots=["جهر"]), {"refused": True}, [13])
    assert "not recognised" in c(_q("meaning", roots=["جهر"]), {"refused": False, "roots": [], "cited": [14]}, [13])
    assert c(_q("single_root", roots=["خلق"]), {"refused": False, "roots": ["موت"], "cited": [2]}, [2, 3]) == "wrong root resolved"
    assert "contain the root" in c(_q("single_root", roots=["خلق"]), {"refused": False, "roots": ["خلق"], "cited": [2, 9]}, [2, 3])
    assert c(_q("single_root", roots=["خلق"]), {"refused": False, "roots": ["خلق"], "cited": [2, 3]}, [2, 3]) is None
    assert "not cited" in c(_q("semantic", relevant=[5]), {"refused": False, "intent": "semantic", "cited": [14]}, [5])
    assert c(_q("concept", roots_include=["رحم"]), {"refused": False, "cited": [3, 19, 5]}, [3, 19]) is None


def test_group_failures_orders_by_size():
    g = metrics.group_failures([("a", 1, "x"), ("b", 2, "y"), ("b", 3, "z")])
    assert list(g) == ["b", "a"] and g["b"] == [(2, "y"), (3, "z")]


class _Fake:
    def __init__(self):
        self.calls = 0

    def __call__(self, url, headers, body):
        self.calls += 1
        reply = {"candidates": [{"content": {"parts": [{"text": "{\"ok\": true}"}]}}],
                 "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 10, "totalTokenCount": 150}}
        return 200, json.dumps(reply)


def test_llm_records_latency_and_tokens_and_replays_them_from_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    cfg, fake = llm.Config("gemini", "k", "m"), _Fake()
    llm.generate_json("s", "u", config=cfg, transport=fake)
    first = dict(llm.LAST_CALL)
    assert first["cached"] is False and first["tokens_in"] == 120 and first["tokens_out"] == 30
    llm.generate_json("s", "u", config=cfg, transport=fake)
    assert fake.calls == 1                                   # second call came from the cache
    assert llm.LAST_CALL["cached"] is True
    assert llm.LAST_CALL["tokens_in"] == 120 and llm.LAST_CALL["latency"] == first["latency"]


def test_usage_for_openai_compatible_replies():
    assert llm._usage("openai_compatible", {"usage": {"prompt_tokens": 7, "completion_tokens": 3}}) == (7, 3)
    assert llm._usage("gemini", {}) == (0, 0)


def test_503_now_has_a_helpful_hint():
    assert "busy" in llm._HINTS[503]


def test_cache_entries_without_timing_are_flagged_not_counted_as_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    cfg = llm.Config("gemini", "k", "m")
    fake = _Fake()
    llm.generate_json("s", "u", config=cfg, transport=fake)
    f = next(tmp_path.glob("*.json"))
    old = json.loads(f.read_text(encoding="utf-8"))
    f.write_text(json.dumps({"model": old["model"], "text": old["text"]}), encoding="utf-8")   # pre-timing format
    llm.generate_json("s", "u", config=cfg, transport=fake)
    assert llm.LAST_CALL["cached"] is True and llm.LAST_CALL["measured"] is False
