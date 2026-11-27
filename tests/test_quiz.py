"""
Quiz generator tests: every answer key is re-checked against the database, over many generated quizzes.
    python -m unittest discover -s tests -v
(Rebuild the DB first: python scripts/build_db.py)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import queries, quiz  # noqa: E402

WORDS = {w["word_id"]: w for a in queries.get_ayahs() for w in a["words"]}
QUIZZES = [quiz.build_quiz(level, seed) for level in quiz.LEVELS for seed in range(200)]
QUESTIONS = [q for z in QUIZZES for q in z["questions"]]


def ayahs_of(root):
    return {w["ayah"] for w in WORDS.values() if w["root"] == root}


def is_true(q, option):
    """Is this option factually correct according to the database?"""
    if q["type"] == "contextual":
        if option["text"] == quiz.BOTH:
            return all(o["ayah"] in ayahs_of(q["root"]) for o in q["options"][:2])
        return option["ayah"] in ayahs_of(q["root"])
    w = WORDS[q["word"]["word_id"]]
    if q["type"] == "root":
        return option["text"].replace(" ", "") == w["root"]
    if q["type"] == "vocabulary":
        return option["text"] == w["gloss"]
    codes = set(w["grammar"].split(","))
    table = {"tense": quiz.TENSES, "case": quiz.CASES}.get(q["kind"])
    if table:
        return any(option["text"] == table[c] for c in codes & table.keys())
    return any(option["text"].endswith(": " + quiz.PERSON[c][1]) for c in codes & quiz.PERSON.keys())


class TestQuiz(unittest.TestCase):
    def test_question_counts_per_level(self):
        for z in QUIZZES:
            got = {}
            for q in z["questions"]:
                got[q["type"]] = got.get(q["type"], 0) + 1
            self.assertEqual(got, quiz.LEVELS[z["level"]], (z["level"], z["seed"]))
        self.assertEqual({k: sum(v.values()) for k, v in quiz.LEVELS.items()},
                         {"easy": 10, "intermediate": 15, "hard": 24})

    def test_answer_key_matches_database(self):
        for q in QUESTIONS:
            keyed = next(o for o in q["options"] if o["id"] == q["answer"])
            self.assertTrue(is_true(q, keyed), q)

    def test_exactly_one_best_option(self):
        for q in QUESTIONS:
            true = [o["id"] for o in q["options"] if is_true(q, o)]
            if q["type"] == "contextual" and q["answer"] == "D":
                self.assertEqual(true, ["A", "B", "D"], q)     # the one complete answer is "Both A and B"
            else:
                self.assertEqual(true, [q["answer"]], q)

    def test_options_are_distinct(self):
        for q in QUESTIONS:
            texts = [o["text"] for o in q["options"]]
            self.assertEqual(len(texts), len(set(texts)), q)
            self.assertIn(len(texts), (3, 4))

    def test_no_wrong_meaning_comes_from_a_similar_root(self):
        by_gloss = {}
        for w in WORDS.values():
            by_gloss.setdefault(w["gloss"], set()).add(w["root"])
        for q in (q for q in QUESTIONS if q["type"] == "vocabulary"):
            right = next(o["text"] for o in q["options"] if o["id"] == q["answer"])
            for o in q["options"]:
                if o["id"] != q["answer"]:
                    self.assertFalse(quiz._stems(o["text"]) & quiz._stems(right), (right, o["text"]))
                    self.assertTrue(any(r and not quiz._similar(r, q["root"]) for r in by_gloss[o["text"]]))

    def test_one_question_per_root(self):
        for z in QUIZZES:
            roots = [q["root"] for q in z["questions"]]
            self.assertEqual(len(roots), len(set(roots)), (z["level"], z["seed"]))

    def test_hard_quiz_uses_both_a_and_b_sometimes(self):
        for z in (z for z in QUIZZES if z["level"] == "hard"):
            answers = [q["answer"] for q in z["questions"] if q["type"] == "contextual"]
            self.assertEqual(answers.count("D"), 3)

    def test_same_seed_same_quiz(self):
        self.assertEqual(quiz.build_quiz("hard", 7), quiz.build_quiz("hard", 7))

    def test_unknown_level(self):
        with self.assertRaises(ValueError):
            quiz.build_quiz("extreme")


if __name__ == "__main__":
    unittest.main()
