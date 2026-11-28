"""i07: a correct answer was rejected because the translation it quoted contains quote marks itself."""
import json

from rag import verify
from rag.evidence import ayah_evidence

EV = ayah_evidence([(23, 0.5)])
T23 = EV[0]["translation"]            # Say, "It is He who has produced you ... little are you grateful."


def _check(answer):
    raw = json.dumps({"refuse": False, "answer": answer, "claims": []}, ensure_ascii=False)
    return verify.check(raw, "semantic", EV)[1]


def test_translation_requoted_with_single_inner_quotes_passes():
    assert 'Say, "' in T23
    assert _check("Ayah [67:23] states, \"" + T23.replace('"', "'") + "\"") == []


def test_translation_with_its_own_double_quotes_inside_double_quotes_passes():
    assert _check("Ayah [67:23] states, \"" + T23 + "\" In this verse Allah mentions what he gave people.") == []


def test_unquoted_translation_passes():
    assert _check("Ayah [67:23] says " + T23) == []


def test_a_fabricated_quote_is_still_rejected_next_to_a_real_one():
    errs = _check("Ayah [67:23] states, \"" + T23 + "\" It also says \"Allah rewards the grateful with gold\".")
    assert any("gold" in e for e in errs)


def test_a_fabricated_quote_alone_is_still_rejected():
    assert _check('Ayah [67:23] says "Allah rewards the grateful with gold".')
