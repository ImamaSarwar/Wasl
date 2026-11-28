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


def test_look_like_is_not_the_concept_of_seeing():
    # "what does X look like" asks for a description; it must not pull in the roots for sight
    assert resolve("What does kingship and supreme authority look like in this surah?")["concept"] == []
    assert resolve("What will the disbelievers' faces look like when the punishment arrives?")["concept"] \
        and "رأي" not in [it["root"] for it in
                          resolve("What will the disbelievers' faces look like when the punishment arrives?")["concept"]]


def test_look_at_still_means_seeing():
    assert "رأي" in [it["root"] for it in resolve("Where does the surah tell people to look at the sky?")["concept"]]


def test_allah_as_subject_does_not_hijack_the_root_route():
    # i10: "Allah" is who the question is about, not the word being asked about
    r = resolve("Which verses mention Allah showing mercy or granting relief?")
    assert r["direct"] == [] and "رحم" in [it["root"] for it in r["concept"]]


@pytest.mark.parametrize("q", [
    "What is the root of Allah?",
    "Where does the word Allah appear?",
    "How many times does Allah appear in the surah?",
])
def test_allah_as_the_word_asked_about_still_resolves(q):
    assert [it["root"] for it in resolve(q)["direct"]] == ["أله"]
