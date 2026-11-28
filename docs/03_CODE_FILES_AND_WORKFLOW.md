# Code files, patches, commands, workflow

## Where things are
- Repo: https://github.com/ImamaSarwar/Wasl (branch `main`).
- In the old sandbox: repo clone `/home/claude/imamasarwar/wasl`, worktree `/tmp/w`. These are gone in a new session; re-add the repo with the add-repo tool.

## Files I changed or created (all delivered as patches)
| File | What |
|---|---|
| `rag/llm.py` | `LAST_CALL`, `_usage`, 5xx hints, cache stores latency/tokens |
| `rag/generate.py` | SYSTEM rules 1–9, refusal `reason`, extra/matched evidence lines |
| `rag/verify.py` | `_canon`, `_lemma_ok`, `_index`, `check` with extra and question |
| `rag/pipeline.py` | gates, three-zone `_semantic`, `_with_llm` stats, concept `extra` |
| `rag/retrieve.py` | `THRESHOLDS`, `THRESHOLDS_LOW`, `threshold_low` |
| `rag/resolve.py` | `_LAT_EXACT` exact spelling index |
| `rag/concepts.json` | removed "work/works" from deeds |
| `eval/run_eval.py` | `--split gen`, `--with-generated`, meaning type, `load(split, files)` |
| `eval/run_baselines.py` | five systems, flags below, summary with CIs, error analysis |
| `eval/metrics.py` | wilson, bootstrap_mean, percentile, cost_usd, classify_failure, group_failures |
| `scripts/make_eval_set.py` | builds `eval/generated.jsonl` (125 questions, seed 67, from the DB) |
| `scripts/debug_question.py` | shows route, evidence prompt, raw reply, verifier verdict, final answer (uses cache) |
| `eval/questions.jsonl` | 130 hand questions (dev/test) |
| `eval/generated.jsonl` | 125 generated questions, split `gen` |
| `tests/` | `test_llm.py`, `test_baselines.py`, `test_gates.py`, `test_metrics.py`, `test_threezone.py` |
| `backend/quiz.py` | adaptive selection: `build_quiz(level, seed, focus, weak)`, rules 1–3 in the module docstring |
| `rag/quiz_feedback.py` | Gemini feedback on wrong quiz answers: re-grade, two-sided evidence, per-side verifier, retry, template |
| `backend/main.py` | `/api/quiz` takes `focus` and `weak`; new `POST /api/quiz/feedback` |
| `eval/run_quiz_feedback.py` | `--make`, `--faulty`, Gemini run with blind rating sheet, `--ratings` |
| `eval/quiz_feedback_cases.jsonl` | fixed test set: 60 wrong answers (15 vocabulary, 15 root, 15 grammar, 15 contextual) |
| `frontend/src/progress.js` | `quizFocus(attempts)`: revision roots + weakest skill sent with the quiz request |
| `frontend/src/components/Quiz.jsx` | adaptive note on the level picker, "Revision" tag, feedback on wrong answers |
| `tests/` | `test_quiz_adaptive.py`, `test_quiz_feedback.py` |

144 tests pass on the user's machine after the final patch.

## Patches delivered, in order (all already applied by the user)
`wasl-llm.patch`, `wasl-verify-fix.patch`, `wasl-eval-baselines.patch`, `wasl-llm-refusal-reasons.patch`, `wasl-more-questions.patch`, `wasl-gates-threshold.patch`, `wasl-generated-sample.patch`, `wasl-imama-questions.patch`, `wasl-eval-metrics.patch` (final superset). The patch files lived in the old sandbox scratchpad; if they are gone, the code is whatever the user has in their working tree.

## Commands (verify flags with `--help`)
- Baseline comparison: `python -m eval.run_baselines` with `--no-llm`, `--systems`, `--generated-sample N`, `--only TYPE...`, `--delay`. Writes `eval/results/baselines.json`, `summary.json`, `error_analysis.json`. Stops after 3 consecutive provider errors. Cached and resumable.
- Retrieval/route eval: `python -m eval.run_eval` with `--split` (dev/test/gen), `--with-generated`, `--llm`.
- One question: `python scripts/debug_question.py "<question>"` (or by id).
- Provider check: `check_llm` script (it confirmed `gemini-3.5-flash-lite` OK).
- Tests: `python -m pytest -q`.

## Git workflow
1. Assistant creates a patch; user runs `git apply --ignore-whitespace <patch>`.
2. User runs tests, then commits in VS Code with one combined message.
3. Keep `.env` and `.llm_cache/` out of git. (Check `.gitignore` includes both.)
4. Attribution for any commit the assistant itself makes: end with the Co-Authored-By and Claude-Session lines the system reminder gives. The user normally commits by hand.

## Known code issue not yet fixed
`eval/run_baselines.py` runs `time.sleep(a.delay)` after every question for LLM systems, even when the reply came from the cache. That is why full runs took 40+ minutes. Fix: sleep only when `llm.LAST_CALL["cached"]` is False (a live call was made).
