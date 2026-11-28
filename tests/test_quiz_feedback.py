"""
Quiz feedback tests with a simulated LLM (no internet, no API key). See rag/quiz_feedback.py.
    python -m unittest discover -s tests -v
(Rebuild the DB first: python scripts/build_db.py)
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import quiz  # noqa: E402
from rag import llm, quiz_feedback as qf  # noqa: E402

CFG = llm.Config("gemini", "test-key", "test-model")
WORDS = qf._words()


def transport_of(*replies):
    """A fake provider that returns the given replies in turn and records the prompts."""
    queue, seen = list(replies), []

    def send(url, headers, body):
        seen.append(body["contents"][0]["parts"][0]["text"])
        reply = queue.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]})
    send.seen = seen
    return send


def wrong_answers(levels=quiz.LEVELS, seeds=range(25)):
    """(question, wrong option id) for every wrong option of many quizzes."""
    for level in levels:
        for seed in seeds:
            for q in quiz.build_quiz(level, seed)["questions"]:
                for o in q["options"]:
                    if o["id"] != q["answer"]:
                        yield q, o["id"]


def first(qtype, kind=None, seed=0):
    for q, chosen in wrong_answers(seeds=range(seed, seed + 10)):
        if q["type"] == qtype and (kind is None or q.get("kind") == kind):
            return q, chosen
    raise AssertionError(qtype)


class TestGrading(unittest.TestCase):
    def test_server_grading_agrees_with_every_answer_key(self):
        for level in quiz.LEVELS:
            for seed in range(25):
                for q in quiz.build_quiz(level, seed)["questions"]:
                    for o in q["options"]:
                        case = qf.build_case(q, o["id"], WORDS)
                        self.assertEqual(case is None, o["id"] == q["answer"], (q, o))

    def test_correct_answer_gets_no_feedback(self):
        q, _ = first("root")
        self.assertEqual(qf.feedback(q, q["answer"], words=WORDS), {"correct": True})

    def test_the_browser_cannot_change_the_answer_key(self):
        q, chosen = first("vocabulary")
        forged = copy.deepcopy(q)
        forged["answer"] = chosen                    # claims the wrong option is right
        self.assertIsNotNone(qf.build_case(forged, chosen, WORDS))

    def test_bad_requests_are_rejected(self):
        q, chosen = first("root")
        bad = [({**q, "type": "essay"}, chosen), (q, "Z"), ({**q, "word": {"word_id": -1}}, chosen),
               ({**q, "options": "nope"}, chosen), ("not a dict", chosen),
               ({**q, "options": [{"id": chosen, "text": "ز ز ز"}]}, chosen)]
        for question, c in bad:
            with self.assertRaises(ValueError):
                qf.build_case(question, c, WORDS)


class TestVerifier(unittest.TestCase):
    def test_every_template_explanation_passes(self):
        for q, chosen in wrong_answers(seeds=range(10)):
            case = qf.build_case(q, chosen, WORDS)
            texts, errors = qf.check(dict(zip(("why_not", "why_correct"), case["template"])), case)
            self.assertEqual(errors, [], (q, chosen, case["template"]))

    def test_grammar_of_the_wrong_option_cannot_be_put_on_the_word(self):
        q, chosen = first("morphology", "case")
        case = qf.build_case(q, chosen, WORDS)
        picked = next(o["text"] for o in q["options"] if o["id"] == chosen).split(" ")[0].lower()
        _, errors = qf.check({"why_not": case["template"][0],
                              "why_correct": f'{q["word"]["arabic"]} is in the {picked} case.'}, case)
        self.assertTrue(any("grammar term" in e for e in errors), errors)

    def test_why_not_cannot_talk_about_the_question_word(self):
        q, chosen = first("root")
        case = qf.build_case(q, chosen, WORDS)
        _, errors = qf.check({"why_not": f'{q["word"]["arabic"]} comes from this root.',
                              "why_correct": case["template"][1]}, case)
        self.assertTrue(any(e.startswith("why_not writes the Arabic word") for e in errors), errors)

    def test_wrong_ayah_number_and_quote_are_rejected(self):
        q, chosen = first("vocabulary")
        case = qf.build_case(q, chosen, WORDS)
        far = 30 if q["word"]["ayah"] != 30 else 1
        _, errors = qf.check({"why_not": case["template"][0],
                              "why_correct": f'In [67:{far}] the word means "something invented".'}, case)
        self.assertTrue(any("refers to ayah" in e for e in errors), errors)
        self.assertTrue(any("quotes" in e for e in errors), errors)

    def test_counts_and_rulings_are_rejected(self):
        q, chosen = first("root")
        case = qf.build_case(q, chosen, WORDS)
        for bad in ("This root appears three times in the surah.", "Scholars interpret this root as forbidden."):
            _, errors = qf.check({"why_not": bad, "why_correct": case["template"][1]}, case)
            self.assertTrue(errors, bad)

    def test_meaning_must_be_quoted_for_vocabulary(self):
        q, chosen = first("vocabulary")
        case = qf.build_case(q, chosen, WORDS)
        _, errors = qf.check({"why_not": case["template"][0], "why_correct": "This is the right meaning."}, case)
        self.assertTrue(any("must quote" in e for e in errors), errors)

    def test_shape(self):
        q, chosen = first("root")
        case = qf.build_case(q, chosen, WORDS)
        self.assertTrue(qf.check([], case)[1])
        self.assertTrue(qf.check({"why_not": ""}, case)[1])


class TestFaultyDrafts(unittest.TestCase):
    def test_fixed_test_set_and_every_broken_draft_is_caught(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
        from eval import run_quiz_feedback as ev
        rows = ev.load_cases()
        self.assertEqual(len(rows), 60)
        for r in rows:
            case = qf.build_case(r["question"], r["chosen"], WORDS)
            self.assertIsNotNone(case, r["id"])
            for kind, texts, expect_reject in ev.faulty_drafts(r, case):
                self.assertEqual(bool(qf.check(texts, case)[1]), expect_reject, (r["id"], kind))


class TestFeedbackFlow(unittest.TestCase):
    def setUp(self):
        # a private reply cache, so one test's fake reply is never served to another test
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(llm, "CACHE_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.q, self.chosen = first("root", seed=3)
        self.case = qf.build_case(self.q, self.chosen, WORDS)
        self.good = dict(zip(("why_not", "why_correct"), self.case["template"]))

    def run_with(self, *replies):
        send = transport_of(*replies)
        res = qf.feedback(self.q, self.chosen, use_llm=True, llm_config=CFG, llm_transport=send, words=WORDS)
        return res, send

    def test_verified_llm_text_is_shown(self):
        reply = {"why_not": self.good["why_not"] + " Look at its letters.",
                 "why_correct": self.good["why_correct"] + " Well tried!"}
        res, send = self.run_with(reply)
        self.assertEqual((res["generated_by"], res["attempts"]), ("llm", 1))
        self.assertEqual(res["why_not"], reply["why_not"])
        self.assertIn("CHOSEN (use only for why_not)", send.seen[0])

    def test_one_retry_with_the_complaints(self):
        bad = {"why_not": "It appears twice in the surah.", "why_correct": self.good["why_correct"]}
        res, send = self.run_with(bad, self.good)
        self.assertEqual((res["generated_by"], res["attempts"]), ("llm", 2))
        self.assertIn("FAILED AUTOMATIC CHECKS", send.seen[1])

    def test_two_failures_give_the_template(self):
        res, _ = self.run_with("not json", {"why_not": "x"})
        self.assertEqual(res["generated_by"], "template")
        self.assertEqual(res["why_correct"], self.good["why_correct"])
        self.assertTrue(res["verification_errors"])

    def test_provider_error_gives_the_template(self):
        res = qf.feedback(self.q, self.chosen, use_llm=True, llm_config=CFG,
                          llm_transport=lambda *a: (404, "{}"), words=WORDS)
        self.assertEqual(res["generated_by"], "template")
        self.assertIn("model not found", res["llm_error"])

    def test_no_llm_gives_the_template(self):
        res = qf.feedback(self.q, self.chosen, words=WORDS)
        self.assertEqual((res["generated_by"], res["correct"]), ("template", False))
        self.assertEqual(res["refs"], [self.q["word"]["ayah"]])


if __name__ == "__main__":
    unittest.main()
