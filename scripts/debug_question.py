"""
Show everything the assistant does with ONE question: how it was routed, the exact evidence sent to the
LLM, the model's raw reply, what the verifier said, and the final answer.

    python scripts/debug_question.py "Which ayah says no army can help the disbelievers besides God?"
    python scripts/debug_question.py "What does Jahar mean?" --retriever minilm

Uses the reply cache, so asking about a question you already evaluated costs no quota.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import generate, llm, pipeline, retrieve, verify  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--retriever", default=None)
    a = ap.parse_args()
    ret = retrieve.get_retriever(a.retriever)
    cfg = llm.get_config()

    def _no_llm(url, headers, body):          # gets the evidence exactly as answer() builds it, without a call
        raise llm.LLMError("debug")
    r = pipeline.answer(a.question, retriever=ret, use_llm=True, llm_config=llm.Config("gemini", "x", "x"),
                        llm_transport=_no_llm)
    if r["refused"] and r["intent"] == "no_match":      # maybe only the borderline band, which the LLM may judge
        r2 = pipeline._semantic(a.question, ret, None, True)
        if not r2["refused"]:
            r = r2
    print(f"retriever: {ret.name} (answer above {retrieve.threshold(ret.name)}, ask the LLM from "
          f"{retrieve.threshold_low(ret.name)})")
    print(f"route:     intent={r['intent']}  roots={r.get('roots')}  matched={r.get('matched')}")
    if r["refused"]:
        print(f"\nREFUSED before the LLM: {r['answer']}")
        return 0
    if r["intent"] == "semantic":
        print("candidates: " + ", ".join(f"{e['ayah']} ({e['score']})" for e in r["evidence"])
              + ("   [borderline]" if r.get("borderline") else ""))
    print("\n--- evidence prompt sent to the LLM " + "-" * 40)
    print(generate.build_user_prompt(a.question, r["intent"], r["evidence"], matched=r.get("matched"),
                                      extra=r.get("extra")))
    if cfg is None:
        print("\n(the LLM is not configured: no reply to show)")
        return 0
    try:
        raw = generate.ask(a.question, r["intent"], r["evidence"], matched=r.get("matched"),
                           extra=r.get("extra"), config=cfg)
    except llm.LLMError as e:
        print(f"\nLLM FAILED: {e}")
        return 1
    print("\n--- raw model reply " + "-" * 56)
    print(raw)
    data, errors = verify.check(raw, r["intent"], r["evidence"], question=a.question, extra=r.get("extra"))
    print("\n--- verifier " + "-" * 63)
    print("passed" if not errors else "\n".join(f"- {e}" for e in errors))
    final = pipeline.answer(a.question, retriever=ret, use_llm=True)
    print(f"\n--- final answer (generated_by={final.get('generated_by')}, refused={final['refused']}) " + "-" * 10)
    print(final["answer"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
