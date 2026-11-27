"""
Root Tutor tests with a simulated LLM (no internet, no API key).
    python -m unittest discover -s tests -v
(Rebuild the DB first: python scripts/build_db.py)
"""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import queries  # noqa: E402
from rag import llm, tutor, tutor_verify  # noqa: E402

CFG = llm.Config("gemini", "test-key", "test-model")
ROOTS = [r["root"] for r in queries.list_roots()]


def good_reply(ev):
    """A lesson that says only what the evidence says."""
    return {
        "overview": f"The root {ev['root']} appears in the words listed below.",
        "forms": [{"id": f["id"], "text": f"{f['lemma']} is recorded as: {', '.join(f['facts'])}."}
                  for f in ev["forms"]],
        "uses": [{"id": u["id"], "text": f"In [67:{u['ayah']}], {u['word']} carries the meaning \"{u['gloss']}\"."}
                 for u in ev["uses"]],
    }


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


class TestFacts(unittest.TestCase):
    def test_facts_come_from_the_stored_codes(self):
        self.assertEqual(tutor.facts("V", "PERF,3MS,form 1"),
                         ["verb", "past tense", "third person", "masculine", "singular", "Form I", "active voice"])
        self.assertEqual(tutor.facts("N", "M,GEN"), ["noun", "masculine", "genitive case"])
        self.assertIn("passive voice", tutor.facts("V", "PERF,PASS,3MS,form 4"))

    def test_every_stored_code_is_understood(self):
        for root in ROOTS:
            for w in queries.root_words(root):
                got = tutor.facts(w["pos_tag"], w["grammar"])
                self.assertTrue(got, (root, w["grammar"]))


class TestVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = tutor.build_evidence("خلق")
        cls.verb = next(f for f in cls.ev["forms"] if "verb" in f["facts"])
        cls.noun = next(f for f in cls.ev["forms"] if "noun" in f["facts"])

    def errors(self, part, item_id=None, text=""):
        data = good_reply(self.ev)
        if part == "overview":
            data["overview"] = text
        else:
            next(r for r in data[part] if r["id"] == item_id)["text"] = text
        return tutor_verify.check(data, self.ev)[1]

    def test_faithful_lesson_passes_for_every_root(self):
        for root in ROOTS:
            ev = tutor.build_evidence(root)
            self.assertEqual(tutor_verify.check(good_reply(ev), ev)[1], [], root)

    def test_wrong_grammar_is_rejected(self):
        for claim in ("present tense", "a command", "passive", "second person", "feminine", "plural", "dual",
                      "a noun", "genitive", "nominative", "Form IV", "Form 2", "an adjective", "māḍī and majrūr",
                      "indefinite", "a participle"):
            self.assertTrue(self.errors("forms", self.verb["id"], f"This is {claim}."), claim)

    def test_a_fact_of_another_form_is_rejected(self):
        self.assertTrue(self.errors("forms", self.noun["id"], "This is a past tense verb."))
        self.assertTrue(self.errors("forms", self.verb["id"], "This is in the genitive case."))

    def test_grammar_the_database_never_records_is_rejected(self):
        for term in ("the subject", "a direct object", "a pronoun suffix", "causative", "definite", "jussive"):
            self.assertTrue(self.errors("forms", self.verb["id"], f"This is {term}."), term)

    def test_correct_grammar_is_accepted(self):
        text = "A past tense (māḍī) verb, third person, masculine singular, Form I, in the active voice."
        self.assertEqual(self.errors("forms", self.verb["id"], text), [])

    def test_overview_allows_word_kinds_only(self):
        self.assertEqual(self.errors("overview", text="It appears as a verb and a noun."), [])
        self.assertTrue(self.errors("overview", text="The noun is in the past tense."))

    def test_use_must_stay_inside_its_ayah_and_evidence(self):
        use = self.ev["uses"][0]
        quote = f'"{use["gloss"]}"'
        for bad in (f"In ayah {use['ayah'] + 1} it means {quote}.", f"In [67:30] it means {quote}.",
                    "It speaks of making things.", 'It means "built a house".', f"It means {quote} كتب.",
                    f"It means {quote} and occurs 9 times.", f"It means {quote} and occurs twice.",
                    f"Scholars interpret {quote} widely.", f"It means {quote}, so this is obligatory.",
                    f"It means {quote}. " + "Long. " * 100):
            self.assertTrue(self.errors("uses", use["id"], bad), bad)

    def test_quoting_the_translation_is_accepted(self):
        use = self.ev["uses"][0]
        part = use["translation"][5:30]
        self.assertEqual(self.errors("uses", use["id"], f'The verse says "{part}".'), [])

    def test_shape_and_ids(self):
        base = good_reply(self.ev)
        missing, extra, repeated, empty = (copy.deepcopy(base) for _ in range(4))
        missing["uses"].pop()
        extra["forms"].append({"id": "F99", "text": "A verb."})
        repeated["forms"].append(repeated["forms"][0])
        empty["overview"] = " "
        for data in (None, [], {}, missing, extra, repeated, empty, {**base, "forms": "x"}):
            texts, errors = tutor_verify.check(data, self.ev)
            self.assertIsNone(texts)
            self.assertTrue(errors)


class TestLesson(unittest.TestCase):
    def setUp(self):
        real = llm.generate_json
        # never read or write the on-disk reply cache during tests
        no_cache = mock.patch.object(llm, "generate_json",
                                     lambda s, u, **kw: real(s, u, use_cache=False, **kw))
        no_cache.start()
        self.addCleanup(no_cache.stop)
        self.ev = tutor.build_evidence("خلق")

    def test_database_only_lesson(self):
        res = tutor.lesson("خلق")
        self.assertEqual(res["generated_by"], "template")
        self.assertEqual(res["total"], len(res["uses"]))
        self.assertTrue(all(f["text"] for f in res["forms"]))

    def test_cards_carry_the_actual_words(self):
        res = tutor.lesson("خلق")
        for f in res["forms"]:
            self.assertEqual(set(f["words"]), {u["word"] for u in res["uses"] if u["form"] == f["id"]})

    def test_tense_note_only_on_past_forms_whose_meaning_uses_will(self):
        res = tutor.lesson("قول")
        self.assertEqual([u["ayah"] for u in res["uses"] if u["note"]], [9, 10, 27])
        self.assertIsNone(tutor.tense_note(["present / future tense"], "they will say"))
        self.assertIsNone(tutor.tense_note(["past tense"], "He willed"))
        self.assertTrue(tutor.tense_note(["past tense"], "(will) ask them"))

    def test_unknown_root(self):
        self.assertIsNone(tutor.lesson("zzz", use_llm=True, llm_config=CFG))

    def test_verified_llm_lesson_is_shown(self):
        send = transport_of(good_reply(self.ev))
        res = tutor.lesson("خلق", use_llm=True, llm_config=CFG, llm_transport=send)
        self.assertEqual((res["generated_by"], res["attempts"]), ("llm", 1))
        self.assertIn("grammar facts: verb, past tense", send.seen[0])

    def test_one_retry_with_the_complaints(self):
        bad = good_reply(self.ev)
        bad["forms"][0]["text"] = "This is a plural form."
        send = transport_of(bad, good_reply(self.ev))
        res = tutor.lesson("خلق", use_llm=True, llm_config=CFG, llm_transport=send)
        self.assertEqual((res["generated_by"], res["attempts"]), ("llm", 2))
        self.assertIn("plural", send.seen[1].split("FAILED AUTOMATIC CHECKS")[1])

    def test_two_failures_give_the_database_lesson(self):
        res = tutor.lesson("خلق", use_llm=True, llm_config=CFG, llm_transport=transport_of("not json", "{}"))
        self.assertEqual(res["generated_by"], "template")
        self.assertTrue(res["verification_errors"])
        self.assertEqual(res["overview"], tutor.template_texts(self.ev)["overview"])

    def test_provider_error_gives_the_database_lesson(self):
        res = tutor.lesson("خلق", use_llm=True, llm_config=CFG, llm_transport=lambda *a: (404, "{}"))
        self.assertEqual(res["generated_by"], "template")
        self.assertIn("404", res["llm_error"])


if __name__ == "__main__":
    unittest.main()
