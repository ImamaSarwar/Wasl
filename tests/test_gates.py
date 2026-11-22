import pytest

from rag.pipeline import answer
from rag.resolve import resolve


@pytest.mark.parametrize("q", [
    "What did Ibn Kathir say about ayah 2?",
    "Explain the hidden meaning of the seven heavens.",
    "What do the scholars say about ayah 5?",
    "Explain Ayat al-Kursi.",
    "Will people who never heard of the warner still be punished?",
    "Does reading this surah every night protect me from punishment?",
    "Should I be afraid of the grave because of this surah?",
])
def test_interpretation_and_personal_questions_are_refused_before_any_search(q):
    r = answer(q)
    assert r["refused"] and r["evidence"] is None


@pytest.mark.parametrize("q", [
    "What does the root khalaq mean?",
    "Where does the root of mawt (m-w-t) appear?",
    "Which words relate to warning in this surah?",
    "How does the surah use words for mercy?",
    "What does the word nadhir mean?",
])
def test_normal_vocabulary_questions_are_still_answered(q):
    assert not answer(q)["refused"]


def test_the_word_works_is_not_a_concept():
    assert resolve("Explain how machine learning works.") == {"direct": [], "concept": []}
    assert resolve("Which verses talk about deeds?")["concept"]   # a real topic word still works


@pytest.mark.parametrize("q", [
    "How is the root Reham used across the Quran",
    "Where else does this word appear outside this surah?",
    "Compare this with other surahs.",
])
def test_whole_quran_questions_are_refused(q):
    r = answer(q)
    assert r["refused"] and r["evidence"] is None


def test_across_the_surah_is_still_answered():
    assert not answer("How is the root of khalaqa used across Surah Al-Mulk?")["refused"]


@pytest.mark.parametrize("q", [
    "Why did Allah not tell anybody when the final hour will happen?",
    "How do the verses about the sky relate to a person's everyday life and choices?",
    "Is the word for holding birds in the air related to the Urdu word maskan?",
])
def test_why_god_daily_life_and_other_language_questions_are_refused(q):
    r = answer(q)
    assert r["refused"] and r["evidence"] is None
