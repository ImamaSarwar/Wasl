"""
Tests for the word-by-word meanings, transliteration, plain-English grammar and past/present verb forms.
    python -m unittest discover -s tests -v
(Rebuild the DB first: python scripts/build_db.py)
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import queries  # noqa: E402
from backend.grammar import describe  # noqa: E402

AYAHS = queries.get_ayahs()
WORDS = [w for a in AYAHS for w in a["words"]]
RAW_CODE = re.compile(r"\b(PERF|IMPF|IMPV|ACT_PCPL|PASS_PCPL|NOM|ACC|GEN|INDEF|[123][MF]?[SPD])\b")


class TestWordByWord(unittest.TestCase):
    def test_every_word_has_a_meaning(self):
        self.assertEqual(len(WORDS), 333)
        self.assertTrue(all(w["gloss"] for w in WORDS))

    def test_ayah_number_markers_not_leaked_into_words(self):
        self.assertFalse(any(re.fullmatch(r"\(\d+\)", w["gloss"]) for w in WORDS))

    def test_known_alignments(self):
        by_root = {}
        for w in WORDS:
            by_root.setdefault(w["root"], []).append(w)
        self.assertEqual({w["gloss"] for w in by_root["موت"]}, {"death"})
        self.assertIn("created", {w["gloss"] for w in by_root["خلق"]})
        first = AYAHS[0]["words"][0]
        self.assertEqual((first["arabic"], first["gloss"]), ("تَبَارَكَ", "Blessed is"))


class TestTransliteration(unittest.TestCase):
    def test_every_ayah_has_transliteration(self):
        self.assertTrue(all(a["transliteration"] for a in AYAHS))
        self.assertTrue(AYAHS[0]["transliteration"].startswith("Tabaarakal"))


class TestPlainGrammar(unittest.TestCase):
    def test_verb_description(self):
        d = describe("V", "PERF,3MS,form 6")
        self.assertEqual(d["kind"], "Verb")
        text = " ".join(x["value"] for x in d["details"])
        self.assertIn("Past", text)
        self.assertIn("he / it", text)
        self.assertIn("Form VI", text)

    def test_form_one_is_not_shown(self):
        d = describe("V", "PERF,3MS,form 1")
        self.assertFalse(any(x["label"] == "Pattern" for x in d["details"]))

    def test_particles_and_nouns(self):
        self.assertEqual(describe("P", "NEG")["kind"], "Negation")
        self.assertEqual(describe("N", "REL,MS")["kind"], "Relative pronoun")
        self.assertEqual(describe("N", "ACT_PCPL,M,INDEF,ACC")["kind"], "Doer noun (active participle)")

    def test_no_raw_codes_reach_the_user(self):
        for w in WORDS:
            d = w["plain"]
            self.assertTrue(d["kind"])
            shown = d["kind"] + " " + " ".join(x["value"] for x in d["details"])
            self.assertIsNone(RAW_CODE.search(shown), f"raw code leaked for {w['arabic']}: {shown}")

    def test_unknown_particle_code_is_not_hidden(self):
        d = describe("P", "ZZZ")
        self.assertTrue(any("ZZZ" in x["value"] for x in d["details"]))


class TestVerbForms(unittest.TestCase):
    def test_non_verbs_have_no_tenses(self):
        self.assertTrue(all(w["tenses"] is None for w in WORDS if w["pos_tag"] != "V"))

    def test_khalaqa(self):
        w = next(w for w in WORDS if w["root"] == "خلق" and w["pos_tag"] == "V")
        self.assertEqual(w["tenses"]["past"]["form"], "خَلَقَ")
        self.assertEqual(w["tenses"]["present"]["form"], "يَخْلُقُ")
        self.assertRegex(w["tenses"]["present"]["ref"], r"^\d+:\d+$")

    def test_emphatic_nun_does_not_truncate_forms(self):
        # 2:5 "to test you": the only lookup that used to win was يَبْلُوَ (cut off before an emphatic nun)
        w = next(w for w in AYAHS[1]["words"] if w["root"] == "بلو")
        self.assertEqual(w["tenses"]["present"]["form"], "يَبْلُو")

    def test_missing_forms_are_reported_as_missing_not_invented(self):
        w = AYAHS[0]["words"][0]  # tabaraka: no present form exists in the Qur'an
        self.assertIsNone(w["tenses"]["present"]["form"])
        self.assertIsNone(w["tenses"]["present"]["ref"])

    def test_forms_are_arabic_and_whole_words(self):
        for w in WORDS:
            for t in (w["tenses"] or {}).values():
                if t["form"]:
                    self.assertRegex(t["form"], r"^[؀-ۿࢠ-ࣿ]+$")


if __name__ == "__main__":
    unittest.main()
