"""The faulty-draft set: the verifier must pass every good draft and reject every fault it is built for."""
from eval import run_verifier as rv


def _run():
    return rv.run(rv.load())


def test_set_is_big_enough():
    rows = rv.load()
    assert sum(r["expect"] == "reject" for r in rows) >= 50
    assert len({r["kind"] for r in rows if r["expect"] == "reject"}) >= 12


def test_no_good_draft_is_rejected():
    bad = [r["id"] for r in _run() if r["expect"] == "pass" and r["rejected"]]
    assert not bad, bad


def test_every_designed_fault_is_caught():
    missed = [r["id"] for r in _run() if r["expect"] == "reject" and not r["gap"] and not r["rejected"]]
    assert not missed, missed


def test_known_gaps_are_labelled():
    # if the verifier ever starts catching these, move the kind out of the gap list in make_faulty_drafts.py
    gaps = [r for r in _run() if r["gap"]]
    assert gaps and all(not r["rejected"] for r in gaps)
