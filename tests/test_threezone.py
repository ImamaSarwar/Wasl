import json

from rag import llm, pipeline, retrieve

CFG = llm.Config("gemini", "k", "m")


class Stub:
    """A retriever that always returns the same scored ayahs."""
    name = "minilm"

    def __init__(self, scored):
        self.scored = scored

    def search(self, q, k):
        return self.scored[:k]


def _reply(**data):
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}
    return lambda url, headers, b: (200, json.dumps(body))


def _down(url, headers, body):
    raise llm.LLMError("could not reach the provider: TimeoutError")


def _no_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)


LOW, HIGH = retrieve.THRESHOLDS_LOW["minilm"], retrieve.THRESHOLDS["minilm"]
BORDER = round((LOW + HIGH) / 2, 3)


def test_below_the_low_threshold_is_always_refused(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    r = pipeline.answer("something unrelated", retriever=Stub([(5, LOW - 0.05)]), use_llm=True,
                        llm_config=CFG, llm_transport=_reply(refuse=False, answer="See [67:5].", claims=[]))
    assert r["refused"]


def test_borderline_question_goes_to_the_llm_and_its_answer_is_used(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    r = pipeline.answer("stars", retriever=Stub([(5, BORDER)]), use_llm=True, llm_config=CFG,
                        llm_transport=_reply(refuse=False, answer="Ayah 5 mentions stars [67:5].", claims=[]))
    assert not r["refused"] and r["generated_by"] == "llm" and r["borderline"]


def test_borderline_question_is_refused_when_the_llm_refuses(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    r = pipeline.answer("poem", retriever=Stub([(5, BORDER)]), use_llm=True, llm_config=CFG,
                        llm_transport=_reply(refuse=True, answer="", claims=[], reason="unrelated"))
    assert r["refused"] and r["llm_reason"] == "unrelated"


def test_borderline_question_is_refused_when_the_llm_is_unavailable(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    r = pipeline.answer("stars", retriever=Stub([(5, BORDER)]), use_llm=True, llm_config=CFG, llm_transport=_down)
    assert r["refused"]


def test_borderline_question_is_refused_without_an_llm():
    assert pipeline.answer("stars", retriever=Stub([(5, BORDER)]), use_llm=False)["refused"]


def test_confident_match_is_still_answered_when_the_llm_is_down(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    r = pipeline.answer("stars", retriever=Stub([(5, HIGH + 0.1)]), use_llm=True, llm_config=CFG, llm_transport=_down)
    assert not r["refused"] and r["generated_by"] == "template"


class Capture:
    """Records the request body and answers with a fixed reply."""
    def __init__(self, **data):
        self.bodies, self.data = [], data

    def __call__(self, url, headers, body):
        self.bodies.append(json.dumps(body, ensure_ascii=False))
        reply = {"candidates": [{"content": {"parts": [{"text": json.dumps(self.data)}]}}]}
        return 200, json.dumps(reply)


def test_topic_word_question_also_gets_the_meaning_search_ayahs(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    cap = Capture(refuse=False, answer="Ayah 12 speaks of fearing the Lord [67:12].", claims=[])
    r = pipeline.answer("Which words relate to disbelievers?", retriever=Stub([(12, 0.5)]),
                        use_llm=True, llm_config=CFG, llm_transport=cap)
    assert r["intent"] == "concept" and r["generated_by"] == "llm" and not r["refused"]
    assert "ALSO CLOSE IN MEANING TO THE QUESTION" in cap.bodies[0] and "[67:12]" in cap.bodies[0]
    assert 12 in r["citations"]                      # citing an ayah that only the search found is allowed


def test_a_root_question_does_not_get_search_ayahs(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    cap = Capture(refuse=False, answer="See [67:2].", claims=[])
    pipeline.answer("What does the root khalaq mean?", retriever=Stub([(3, 0.5)]), use_llm=True,
                    llm_config=CFG, llm_transport=cap)
    assert "ALSO CLOSE IN MEANING TO THE QUESTION" not in cap.bodies[0]


def test_an_llm_refusal_records_which_ayahs_the_model_was_shown(monkeypatch, tmp_path):
    _no_cache(monkeypatch, tmp_path)
    r = pipeline.answer("poem", retriever=Stub([(5, BORDER), (6, BORDER - 0.01)]), use_llm=True, llm_config=CFG,
                        llm_transport=_reply(refuse=True, answer="", claims=[], reason="unrelated"))
    assert r["refused"] and r["retrieved"] == [5, 6]


def test_the_llm_is_shown_five_candidates_and_the_database_answer_three():
    scored = [(n, HIGH + 0.1 - n * 0.01) for n in (7, 8, 9, 10, 11, 12)]
    no_llm = pipeline._semantic("q", Stub(scored), None, use_llm=False)
    with_llm = pipeline._semantic("q", Stub(scored), None, use_llm=True)
    assert [a["ayah"] for a in no_llm["evidence"]] == [7, 8, 9]
    assert [a["ayah"] for a in with_llm["evidence"]] == [7, 8, 9, 10, 11]


def test_candidates_below_the_low_threshold_are_still_dropped_when_five_are_requested():
    scored = [(7, HIGH + 0.05), (8, HIGH), (9, HIGH - 0.01), (10, LOW + 0.01), (11, LOW - 0.05)]
    r = pipeline._semantic("q", Stub(scored), None, use_llm=True)
    assert [a["ayah"] for a in r["evidence"]] == [7, 8, 9, 10]
