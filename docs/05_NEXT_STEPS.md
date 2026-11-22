# Next steps, in priority order

Assignment 3 is submitted. The remaining work is about making the system and the final paper stronger before the main deadline.

## 0. Housekeeping (do first, 10 minutes)
- Commit everything applied so far in VS Code with one combined message.
- Confirm `.env` and `.llm_cache/` are git-ignored (`git status` must not list them).
- Make sure Imama has pulled and her frontend still works with the new pipeline outputs.

## 1. Quick tooling fix
Patch `eval/run_baselines.py` to sleep only after live (non-cached) calls. Cached reruns should take minutes, not 45.

## 2. Fix the cheap failures (biggest gain per hour)
- **Approximate spelling matching** for i35, i44, i45, i46: strip clitics (bi-, wa-, al-), edit distance with a unique-match guard. Test that it does not create collisions with English words on the generated set and the refusal sets.
- **Over-refusals m18, m25, i01:** try `gemini-3.6-flash` (`$env:LLM_MODEL`), or tighten the prompt's refusal rule. Use `scripts/debug_question.py` to inspect.
- **Retrieval misses m14, m17, m22, m33:** add concept phrases or check the retriever on those ayahs.
- **i08, i10, i36:** add gate and routing cases; decide whether i36's label is wrong.

## 3. Get an honest test
- Ask Imama for a fresh batch of about 20 questions she has not shown anyone (a description of the question types was already drafted; reuse it). Run it **once**, report, then treat it as dev.

## 4. Measurements still missing
- Hand-rate 20–30 answers (correct, supported, helpful) to get an unsupported-claim rate.
- Set token prices and rerun to get a real cost figure.
- p95 latency (9.7 s vs 5 s target): look at retry waits and timeouts; report the p95 both with and without 503 retries.
- Add more counts questions so "counts right" for prompt-only is not 2 data points.

## 5. Verifier work promised in the proposal
- Level labels in answers (root / lemma / form / occurrence), and stop saying "forms" for lemmas.
- Arabic-text check in the verifier.
- A faulty-draft verifier test set of at least 50 deliberately wrong drafts, to measure how many the verifier catches.

## 6. Features
- Root Tutor (F11).
- Makki/Madani surah facts: needs `data/raw/quran-data.xml` from Tanzil.

## 7. Final paper and demo
- Update the proposal and the system demonstration paper with final numbers.
- Write a demo script: one root question, one meaning question, one refusal, one verifier catch, the fallback.
- Make the evaluation slides match the final numbers.

## Open questions for the user
- Which model should the demo use (flash-lite is fast and free but over-refuses; 3.6-flash is better but 503s)?
- Real token prices for the cost slide.
- When does Imama want the pipeline frozen for deployment?
