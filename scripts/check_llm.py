"""
Check that your .env is set up and the model answers. Run from the repo root:
    python scripts/check_llm.py
It sends one tiny request (no Quran text) and prints what happened. The key is never printed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import llm  # noqa: E402


def main():
    cfg = llm.get_config()
    if cfg is None:
        print("NOT CONFIGURED. In the repo root, make a file called .env (copy .env.example) containing:\n"
              "  LLM_PROVIDER=gemini\n  LLM_API_KEY=<your key>\n  LLM_MODEL=gemini-3.8-flash\n"
              "No quotes, no spaces around '='. The file must be named exactly .env (not .env.txt).")
        return 1
    print(f"provider: {cfg.provider}\nmodel:    {cfg.model}\nkey:      set ({len(cfg.api_key)} characters)")
    try:
        text = llm.generate_json('Reply with JSON only, no other text.',
                                 'Return exactly {"ok": true, "word": "hello"}', use_cache=False, max_retries=2)
    except llm.LLMError as e:
        print(f"\nFAILED: {e}")
        return 1
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"\nThe model answered, but not with valid JSON:\n{text[:300]}")
        return 1
    print(f"\nOK - the model answered with JSON: {data}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
