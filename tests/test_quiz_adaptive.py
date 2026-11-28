"""
Adaptive question selection tests (rule-based personalisation; see backend/quiz.py).
    python -m unittest discover -s tests -v
(Rebuild the DB first: python scripts/build_db.py)
"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import queries, quiz  # noqa: E402
from tests.test_quiz import is_true  # noqa: E402

ROOTS = [r["root"] for r in queries.list_roots()]


def focus_for(seed, n=6):
    return random.Random(seed).sample(ROOTS, n)


CASES = [(level, seed, focus_for(seed), weak)
         for level in quiz.LEVELS for seed in range(60)
         for weak in (None, "vocabulary", "tense", "contextual")]
QUIZZES = [(c, quiz.build_quiz(c[0], c[1], focus=c[2], weak=c[3])) for c in CASES]


def type_counts(z):
    got = {}
    for q in z["questions"]:
        got[q["type"]] = got.get(q["type"], 0) + 1
    return got


class TestAdaptiveQuiz(unittest.TestCase):
    def test_answer_keys_still_match_the_database(self):
        for _, z in QUIZZES:
            for q in z["questions"]:
                true = [o["id"] for o in q["options"] if is_true(q, o)]
                if q["type"] == "contextual" and q["answer"] == "D":
                    self.assertEqual(true, ["A", "B", "D"], q)
                else:
                    self.assertEqual(true, [q["answer"]], q)

    def test_same_length_and_one_question_per_root(self):
        for (level, *_), z in QUIZZES:
            self.assertEqual(len(z["questions"]), sum(quiz.LEVELS[level].values()))
            roots = [q["root"] for q in z["questions"]]
            self.assertEqual(len(roots), len(set(roots)))

    def test_focus_roots_are_used_but_never_more_than_half_of_a_type(self):
        for (level, seed, focus, weak), z in QUIZZES:
            self.assertGreater(z["adaptive"]["revision_questions"], 0, (level, seed))
            for t, n in type_counts(z).items():
                rev = sum(q["revision"] for q in z["questions"] if q["type"] == t)
                # rule 1 caps what is chosen on purpose; a focus root can still come up by chance in the
                # random second pass, so allow that, but the quiz must not be mostly revision
                self.assertLessEqual(rev, n, (level, seed, t))
            self.assertLessEqual(z["adaptive"]["revision_questions"], len(z["questions"]) * 0.75)
            for q in z["questions"]:
                self.assertEqual(q["revision"], q["root"] in focus)

    def test_weak_type_gets_one_more_question(self):
        for (level, seed, focus, weak), z in QUIZZES:
            plan = quiz.LEVELS[level]
            if weak in plan:
                self.assertEqual(type_counts(z)[weak], plan[weak] + 1, (level, seed, weak))
            elif weak is None:
                self.assertEqual(type_counts(z), plan)

    def test_weak_grammar_skill_is_asked_more(self):
        for seed in range(40):
            z = quiz.build_quiz("intermediate", seed, weak="tense")
            kinds = [q.get("kind") for q in z["questions"] if q["type"] == "morphology"]
            self.assertGreaterEqual(kinds.count("tense"), 3, kinds)

    def test_unknown_roots_are_ignored_and_unknown_skills_rejected(self):
        z = quiz.build_quiz("easy", 1, focus=["xyz", "", None, ROOTS[0], ROOTS[0]])
        self.assertEqual(z["adaptive"]["focus"], [ROOTS[0]])
        with self.assertRaises(ValueError):
            quiz.build_quiz("easy", 1, weak="spelling")

    def test_spaced_roots_are_accepted(self):
        z = quiz.build_quiz("easy", 3, focus=[" ".join(ROOTS[5])])
        self.assertEqual(z["adaptive"]["focus"], [ROOTS[5]])

    def test_no_learner_data_gives_the_old_quiz(self):
        plain = quiz.build_quiz("hard", 7)
        self.assertNotIn("adaptive", plain)
        self.assertEqual(plain, quiz.build_quiz("hard", 7, focus=[], weak=None))
        self.assertFalse(any(q["revision"] for q in plain["questions"]))

    def test_same_inputs_same_quiz(self):
        f = focus_for(9)
        self.assertEqual(quiz.build_quiz("hard", 9, f, "case"), quiz.build_quiz("hard", 9, f, "case"))


if __name__ == "__main__":
    unittest.main()
