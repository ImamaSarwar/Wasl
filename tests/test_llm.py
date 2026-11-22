"""
Tests for the LLM stage: client, verifier and pipeline. A FAKE model is used everywhere, so these
need no internet, no API key and use no quota.
    python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rag import generate, llm, verify  # noqa: E402
from rag.evidence import root_evidence  # noqa: E402
from rag.pipeline import REFUSAL_UNSUPPORTED, answer  # noqa: E402

CFG = llm.Config("gemini", "SECRET-KEY-123", "test-model")


def gemini_reply(obj_or_text):
    text = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text, ensure_ascii=False)
    return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


class FakeTransport:
    """Replays queued (status, body) replies and records every request."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


GOOD = {"refuse": False,
        "answer": 'The root appears as "created" in [67:2], [67:3] and [67:14], and as "(the) creation" in [67:3].',
        "claims": [{"ayah": 2, "root": "خلق", "lemma": "خَلَقَ", "gloss": "created"},
                   {"ayah": 3, "root": "خلق", "lemma": "خَلْق", "gloss": "(the) creation"}]}


class CacheIsolated(unittest.TestCase):
    """Every test gets its own empty reply cache, so fake replies never leak between tests."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = mock.patch.object(llm, "CACHE_DIR", Path(d.name) / "cache")
        p.start()
        self.addCleanup(p.stop)


class TestClient(CacheIsolated):
    def test_gemini_request_shape(self):
        t = FakeTransport(gemini_reply({"ok": True}))
        out = llm.generate_json("SYS", "USER", config=CFG, transport=t)
        self.assertEqual(json.loads(out), {"ok": True})
        url, headers, body = t.calls[0]
        self.assertIn("test-model:generateContent", url)
        self.assertNotIn("SECRET", url)                       # key only in a header, never in the URL
        self.assertEqual(headers["x-goog-api-key"], "SECRET-KEY-123")
        self.assertEqual(body["system_instruction"]["parts"][0]["text"], "SYS")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")

    def test_openai_compatible_request_shape(self):
        cfg = llm.Config("openai_compatible", "k", "m", "https://example.test/v1")
        t = FakeTransport((200, json.dumps({"choices": [{"message": {"content": '{"a": 1}'}}]})))
        self.assertEqual(llm.generate_json("S", "U", config=cfg, transport=t), '{"a": 1}')
        self.assertEqual(t.calls[0][0], "https://example.test/v1/chat/completions")
        self.assertEqual(t.calls[0][1]["Authorization"], "Bearer k")

    def test_rate_limit_is_retried_then_succeeds(self):
        t = FakeTransport((429, "slow down"), gemini_reply({"ok": 1}))
        sleeps = []
        out = llm.generate_json("S", "U", config=CFG, transport=t, sleep=sleeps.append)
        self.assertEqual(json.loads(out), {"ok": 1})
        self.assertEqual(len(t.calls), 2)
        self.assertEqual(len(sleeps), 1)

    def test_errors_have_hints_and_never_leak_the_key(self):
        for status, hint in ((404, "LLM_MODEL"), (401, "LLM_API_KEY"), (429, "rate limit")):
            t = FakeTransport((status, "body with SECRET-KEY-123 inside"))
            with self.assertRaises(llm.LLMError) as cm:
                llm.generate_json("S", "U", config=CFG, transport=t, sleep=lambda s: None)
            self.assertIn(hint, str(cm.exception))
            self.assertNotIn("SECRET", str(cm.exception))

    def test_blocked_prompt_and_empty_reply(self):
        for payload in ({"promptFeedback": {"blockReason": "SAFETY"}}, {"candidates": []}):
            t = FakeTransport((200, json.dumps(payload)))
            with self.assertRaises(llm.LLMError):
                llm.generate_json("S", "U", config=CFG, transport=t)

    def test_replies_are_cached_on_disk(self):
        t = FakeTransport(gemini_reply({"n": 1}))
        llm.generate_json("S", "U", config=CFG, transport=t)
        llm.generate_json("S", "U", config=CFG, transport=t)
        self.assertEqual(len(t.calls), 1)
        llm.generate_json("S", "other prompt", config=CFG, transport=t)
        self.assertEqual(len(t.calls), 2)

    def test_not_configured(self):
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "", "LLM_MODEL": ""}):
            with mock.patch.object(llm, "load_env"):
                self.assertIsNone(llm.get_config())
                with self.assertRaises(llm.LLMError):
                    llm.generate_json("S", "U")

    def test_env_file_parsing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / ".env"
            f.write_text('# comment\nWASL_T_A="quoted"\nWASL_T_B=plain\n\nWASL_T_C=\nWASL_T_KEEP=file\n',
                         encoding="utf-8")
            with mock.patch.dict(os.environ, {"WASL_T_KEEP": "env"}):
                llm.load_env(f)
                self.assertEqual(os.environ["WASL_T_A"], "quoted")
                self.assertEqual(os.environ["WASL_T_B"], "plain")
                self.assertNotIn("WASL_T_C", os.environ)       # empty values are ignored
                self.assertEqual(os.environ["WASL_T_KEEP"], "env")  # real environment wins
            for k in ("WASL_T_A", "WASL_T_B"):
                os.environ.pop(k, None)


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.ev = [root_evidence("خلق")]

    def check(self, obj, intent="single_root", ev=None):
        return verify.check(json.dumps(obj, ensure_ascii=False), intent, ev or self.ev)[1]

    def with_(self, **changes):
        return {**GOOD, **changes}

    def test_good_answer_passes(self):
        self.assertEqual(self.check(GOOD), [])

    def test_json_with_code_fence_is_accepted(self):
        raw = "```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```"
        self.assertEqual(verify.check(raw, "single_root", self.ev)[1], [])

    def test_not_json(self):
        self.assertTrue(verify.check("sorry I cannot", "single_root", self.ev)[1])

    def test_refusal_passes(self):
        data, errors = verify.check('{"refuse": true, "answer": "", "claims": []}', "single_root", self.ev)
        self.assertEqual(errors, [])
        self.assertTrue(data["refuse"])

    def test_cited_ayah_not_in_evidence(self):
        errs = self.check(self.with_(answer='"created" [67:2] and also [67:30]'))
        self.assertTrue(any("ayah 30" in e for e in errs))

    def test_ayah_word_form_is_checked_too(self):
        errs = self.check(self.with_(answer='"created" in [67:2] and in ayah 25'))
        self.assertTrue(any("ayah 25" in e for e in errs))

    def test_no_citation(self):
        self.assertTrue(any("cites no ayah" in e for e in self.check(self.with_(answer='"created"', claims=[]))))

    def test_claims_count_as_citations(self):
        # a reply that names its ayah in a structured claim, not in the prose, is still cited
        self.assertEqual(self.check(self.with_(answer='"created" is used here')), [])

    def test_claim_root_not_in_that_ayah(self):
        bad = self.with_(claims=[{"ayah": 14, "root": "علم", "lemma": "عَلِمَ", "gloss": "know"}])
        self.assertTrue(any("does not occur" in e or "not in the evidence" in e for e in self.check(bad)))
        bad = self.with_(claims=[{"ayah": 14, "root": "خلق", "lemma": "خَلْق", "gloss": None}])  # 14 has خَلَقَ only
        self.assertTrue(any("no form with lemma" in e for e in self.check(bad)))

    def test_lemma_without_diacritics_only_when_unambiguous(self):
        # ayah 14 has only the verb خَلَقَ, so the bare spelling points at exactly one lemma: accepted
        ok = self.with_(claims=[{"ayah": 14, "root": "خلق", "lemma": "خلق", "gloss": "created"}])
        self.assertEqual(self.check(ok), [])
        # ayah 3 has both the verb and the noun: the bare spelling is ambiguous: rejected
        amb = self.with_(claims=[{"ayah": 3, "root": "خلق", "lemma": "خلق", "gloss": None}])
        self.assertTrue(any("no form with lemma" in e for e in self.check(amb)))

    def test_claim_with_wrong_meaning(self):
        bad = self.with_(claims=[{"ayah": 2, "root": "خلق", "lemma": "خَلَقَ", "gloss": "destroyed"}])
        self.assertTrue(any("meaning" in e for e in self.check(bad)))

    def test_invented_quote(self):
        errs = self.check(self.with_(answer='The word means "to build a house" in [67:2].'))
        self.assertTrue(any("to build a house" in e for e in errs))

    def test_quote_from_translation_is_allowed(self):
        ok = self.with_(answer='It says "[He] who created death and life" in [67:2].')
        self.assertEqual(self.check(ok), [])

    def test_wrong_count(self):
        errs = self.check(self.with_(answer='It appears 9 times: "created" [67:2].'))
        self.assertTrue(errs)
        self.assertEqual(self.check(self.with_(answer='It appears 4 times: "created" [67:2].')), [])

    def test_ruling_is_rejected(self):
        self.assertTrue(any("ruling" in e for e in self.check(self.with_(answer='"created" [67:2] is haram'))))

    def test_semantic_intent(self):
        ev = [{"ayah": 19, "arabic": "x", "translation": "Do they not see the birds above them?", "score": 0.5}]
        ok = {"refuse": False, "answer": "Ayah [67:19] mentions birds.", "claims": [{"ayah": 19}]}
        self.assertEqual(self.check(ok, "semantic", ev), [])
        bad = {"refuse": False, "answer": "Ayah [67:3] mentions birds.", "claims": []}
        self.assertTrue(self.check(bad, "semantic", ev))

    def test_cited_ayahs(self):
        self.assertEqual(verify.cited_ayahs({"answer": "[67:3] and [67:2], ayahs 14 and 19",
                                             "claims": [{"ayah": 3}, {"ayah": "67:30"}]}), [2, 3, 14, 19, 30])


class TestPipelineWithFakeLLM(CacheIsolated):
    Q = "What does khalaqa mean?"

    def ask(self, *replies, q=None):
        t = FakeTransport(*replies)
        return answer(q or self.Q, use_llm=True, llm_config=CFG, llm_transport=t), t

    def test_llm_answer_is_used_when_it_verifies(self):
        r, t = self.ask(gemini_reply(GOOD))
        self.assertEqual((r["generated_by"], r["attempts"], r["refused"]), ("llm", 1, False))
        self.assertEqual(r["intent"], "meaning")
        self.assertEqual(r["citations"], [2, 3, 14])
        self.assertIn('"created"', r["answer"])
        self.assertIn("Evidence:", r["answer"])            # database facts are always appended
        self.assertIn("occurs 4 times", r["answer"])
        self.assertEqual(len(t.calls), 1)

    def test_prompt_contains_evidence_but_not_the_key(self):
        _, t = self.ask(gemini_reply(GOOD))
        sent = json.dumps(t.calls[0][2], ensure_ascii=False)
        self.assertIn("(the) creation", sent)
        self.assertIn("[67:14]", sent)
        self.assertNotIn("SECRET", sent)

    def test_regenerates_once_with_the_verifiers_complaints(self):
        bad = {**GOOD, "answer": '"created" in [67:30]'}
        r, t = self.ask(gemini_reply(bad), gemini_reply(GOOD))
        self.assertEqual((r["generated_by"], r["attempts"]), ("llm", 2))
        second = json.dumps(t.calls[1][2], ensure_ascii=False)
        self.assertIn("FAILED AUTOMATIC CHECKS", second)
        self.assertIn("ayah 30", second)

    def test_falls_back_to_template_when_both_attempts_fail(self):
        bad = {**GOOD, "answer": '"created" in [67:30]'}
        r, t = self.ask(gemini_reply(bad))
        self.assertEqual(r["generated_by"], "template")
        self.assertTrue(r["verification_errors"])
        self.assertFalse(r["refused"])
        self.assertIn("occurs 4 times", r["answer"])        # still a correct, database-only answer
        self.assertNotIn("[67:30]", r["answer"])
        self.assertEqual(len(t.calls), 2)

    def test_llm_outage_falls_back_to_template(self):
        r, _ = self.ask((503, "down"))
        self.assertEqual(r["generated_by"], "template")
        self.assertIn("HTTP 503", r["llm_error"])
        self.assertFalse(r["refused"])
        self.assertIn("occurs 4 times", r["answer"])

    def test_model_can_refuse(self):
        r, _ = self.ask(gemini_reply({"refuse": True, "answer": "", "claims": []}))
        self.assertTrue(r["refused"])
        self.assertEqual(r["answer"], REFUSAL_UNSUPPORTED)
        self.assertEqual(r["citations"], [])

    def test_not_configured_falls_back(self):
        with mock.patch.object(llm, "get_config", return_value=None):
            r = answer(self.Q, use_llm=True)
        self.assertEqual(r["generated_by"], "template")
        self.assertIn("not configured", r["llm_error"])

    def test_llm_is_off_by_default(self):
        t = FakeTransport(gemini_reply(GOOD))
        r = answer(self.Q, llm_config=CFG, llm_transport=t)
        self.assertNotIn("generated_by", r)
        self.assertEqual(t.calls, [])

    def test_refused_questions_never_reach_the_llm(self):
        for q in ("Is it haram to disbelieve?", "Tell me about Surah Al-Baqarah", "What is the correct tafsir of ayah 2?"):
            t = FakeTransport(gemini_reply(GOOD))
            r = answer(q, use_llm=True, llm_config=CFG, llm_transport=t)
            self.assertTrue(r["refused"], q)
            self.assertEqual(t.calls, [], q)

    def test_semantic_questions_use_the_llm_too(self):
        good = {"refuse": False, "answer": "Ayah [67:6] describes the punishment of Hell.", "claims": [{"ayah": 6}]}
        r, t = self.ask(gemini_reply(good), q="What happens to the people in hellfire?")
        self.assertEqual((r["intent"], r["generated_by"]), ("semantic", "llm"))
        self.assertEqual(r["citations"], [6])

    def test_compare_questions(self):
        good = {"refuse": False,
                "answer": 'قدر is "All-Powerful" in [67:1]; علم includes "the knowledge" in [67:26].',
                "claims": [{"ayah": 1, "root": "قدر", "lemma": "قَدِير", "gloss": "All-Powerful"},
                           {"ayah": 26, "root": "علم", "lemma": "عِلْم", "gloss": "the knowledge"}]}
        r, _ = self.ask(gemini_reply(good), q="Compare the roots q-d-r and '-l-m in this surah.")
        self.assertEqual((r["intent"], r["generated_by"]), ("compare", "llm"))


class TestPromptFormatting(unittest.TestCase):
    def test_evidence_block_has_forms_meanings_and_ayahs(self):
        text = generate.format_evidence("single_root", [root_evidence("خلق")])
        self.assertIn("ROOT خلق (khlq): 4 occurrence(s)", text)
        self.assertIn('"(the) creation"', text)
        self.assertIn("[67:3] translation:", text)
        self.assertIn('meaning "created"', text)


if __name__ == "__main__":
    unittest.main()


def test_gloss_claim_tolerates_wrapping_quotes_and_parentheses():
    from rag import verify
    assert verify._gloss_norm('"the birds"') == verify._gloss_norm("the birds")
    assert verify._gloss_norm("(the) creation") == verify._gloss_norm("the creation")
    assert verify._gloss_norm("a warner") != verify._gloss_norm("warners")
