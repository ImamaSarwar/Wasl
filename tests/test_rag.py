"""
Tests for the assistant's deterministic half (resolver, evidence, pipeline). No network, no LLM.
    python -m unittest discover -s tests -v
(Build the DB and aliases first: python scripts/build_db.py && python scripts/build_aliases.py)
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import queries  # noqa: E402
from rag.evidence import compare_evidence, root_evidence  # noqa: E402
from rag.pipeline import answer  # noqa: E402
from rag.resolve import ALIASES, resolve  # noqa: E402


def roots(q, key="direct"):
    return [i["root"] for i in resolve(q)[key]]


class TestResolve(unittest.TestCase):
    def test_every_db_root_has_an_alias_entry(self):
        self.assertEqual({r["root"] for r in queries.list_roots()}, set(ALIASES))

    def test_concept_map_only_names_real_roots(self):
        real = {r["root"] for r in queries.list_roots()}
        raw = json.loads((Path(__file__).resolve().parent.parent / "rag" / "concepts.json").read_text(encoding="utf-8"))
        for k, v in raw.items():
            if not k.startswith("_"):
                self.assertTrue(set(v) <= real, f"{k}: {set(v) - real}")

    def test_lemma_latin(self):
        self.assertEqual(roots("How is khalaqa used?"), ["خلق"])

    def test_dashed_roots_and_ayn(self):
        self.assertEqual(roots("Compare the roots q-d-r and '-l-m"), ["قدر", "علم"])
        self.assertEqual(roots("ʿ-l-m"), ["علم"])
        self.assertEqual(roots("ʾ-l-m"), ["ألم"])  # explicit hamza is a different root

    def test_arabic_with_diacritics_and_prefix(self):
        self.assertEqual(roots("معنى خَلَقَ"), ["خلق"])
        self.assertEqual(roots("وَالْحَيَاةَ"), ["حيي"])

    def test_surah_name_is_not_the_root_malk(self):
        self.assertEqual(roots("How is khalaqa used across Surah Al-Mulk?"), ["خلق"])
        self.assertEqual(roots("in Surah Al-Mulk"), [])

    def test_ordinary_english_words_are_not_roots(self):
        self.assertEqual(roots("Compare the roots and the forms"), [])

    def test_concept(self):
        self.assertEqual(roots("Which ayahs use the root for seeing?", "concept"), ["رأي", "بصر"])


class TestResolveRegressions(unittest.TestCase):
    """Bugs found by eval/run_eval.py - keep them fixed."""

    def test_arabic_question_mark_is_not_part_of_the_word(self):
        self.assertEqual(roots("ما هي الآيات التي فيها الجذر رحم؟"), ["رحم"])

    def test_common_spellings_of_a_word_form(self):
        for spelling in ("ghafur", "ghafoor", "ghafuwr"):
            self.assertEqual(roots(f"Tell me about the word {spelling}"), ["غفر"], spelling)

    def test_latin_diacritics_are_folded(self):
        self.assertEqual(roots("Compare s-m-ʿ and b-ṣ-r"), ["سمع", "بصر"])

    def test_question_boilerplate_say_is_not_the_speech_concept(self):
        self.assertEqual(roots("What does the surah say about eating?", "concept"), [])


class TestSemantic(unittest.TestCase):
    def test_retriever_ranks_the_provision_ayah_first(self):
        from rag.retrieve import get_retriever
        top = get_retriever("tfidf").search("provision")[0][0]
        self.assertIn(top, (15, 21))

    def test_semantic_fallback_answers_and_cites_evidence(self):
        r = answer("What happens to the people in hellfire?", retriever=None)
        self.assertFalse(r["refused"])
        self.assertEqual(r["intent"], "semantic")
        self.assertIn(6, r["citations"])
        self.assertTrue(all(0 <= a["score"] <= 1 for a in r["evidence"]))

    def test_very_weak_match_is_refused(self):
        self.assertTrue(answer("Explain quantum computing")["refused"])


class TestScopeGates(unittest.TestCase):
    def test_other_surahs_are_refused(self):
        for q in ["Tell me about Surah Al-Baqarah", "What is in surah 2?", "explain 2:255",
                  "words in al-Fatiha", "How is khalaqa used in Surah Yasin?"]:
            r = answer(q)
            self.assertTrue(r["refused"], q)
            self.assertEqual(r["intent"], "other_surah", q)

    def test_al_mulk_questions_are_not_blocked(self):
        for q in ["How is khalaqa used across Surah Al-Mulk?", "What does the surah say about birds?",
                  "Show me 67:3", "Which ayah in surah 67 mentions water?", "What does the surah say about hearing?"]:
            self.assertNotEqual(answer(q)["intent"], "other_surah", q)

    def test_tafsir_is_declined(self):
        r = answer("What is the correct tafsir of ayah 2?")
        self.assertTrue(r["refused"])
        self.assertEqual(r["intent"], "out_of_scope")


class TestEvidence(unittest.TestCase):
    def test_khalaqa_matches_existing_queries(self):
        ev = root_evidence("خلق")
        self.assertEqual(ev["total"], 4)
        self.assertEqual([a["ayah"] for a in ev["ayahs"]], [2, 3, 14])
        self.assertTrue(all(a["translation"] for a in ev["ayahs"]))

    def test_unknown_root(self):
        self.assertIsNone(root_evidence("ضرب"))

    def test_compare_shared_ayahs(self):
        c = compare_evidence("بصر", "رأي")
        self.assertEqual(c["shared_ayahs"], [3, 19])


class TestPipeline(unittest.TestCase):
    def test_single_root(self):
        r = answer("How is the root of khalaqa used across Surah Al-Mulk?")
        self.assertFalse(r["refused"])
        self.assertEqual(r["intent"], "single_root")
        self.assertEqual(r["citations"], [2, 3, 14])
        self.assertIn("4 times", r["answer"])

    def test_compare(self):
        r = answer("Compare the roots q-d-r and '-l-m in this surah.")
        self.assertEqual(r["intent"], "compare")
        self.assertEqual(r["roots"], ["قدر", "علم"])

    def test_concept(self):
        r = answer("Which ayahs use forms of the root for seeing?")
        self.assertEqual(r["intent"], "concept")
        self.assertIn(3, r["citations"])

    def test_every_citation_is_a_real_ayah_in_the_evidence(self):
        for q in ["khalaqa", "q-d-r vs '-l-m", "seeing", "mercy"]:
            r = answer(q)
            self.assertFalse(r["refused"], q)
            ids = {a["ayah"] for e in r["evidence"] for a in e["ayahs"]}
            self.assertTrue(set(r["citations"]) <= ids and all(1 <= c <= 30 for c in r["citations"]))

    def test_refuses_rulings(self):
        r = answer("Is it haram to disbelieve? Give me a fatwa")
        self.assertTrue(r["refused"])
        self.assertEqual(r["intent"], "out_of_scope")

    def test_normal_questions_with_can_i_or_should_i_are_not_refused(self):
        for q in ["Can I see which ayahs use khalaqa?", "Should I start with the root q-d-r?"]:
            self.assertFalse(answer(q)["refused"], q)

    def test_refuses_when_nothing_matches(self):
        r = answer("What is the capital of France?")
        self.assertTrue(r["refused"])
        self.assertEqual(r["intent"], "no_match")


if __name__ == "__main__":
    unittest.main()
