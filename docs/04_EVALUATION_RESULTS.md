# Evaluation: sets, numbers, errors, targets

## Test sets
| Set | Size | Notes |
|---|---|---|
| `eval/questions.jsonl` (hand) | 130 | 45 semantic, 36 no_match, 22 out_of_scope, 10 single_root, 7 meaning, 6 compare, 4 concept. Includes my 51 dev questions (m09–m33, o05–o14, n07–n22) and Imama's i01–i46 |
| `eval/generated.jsonl` | 125 | split `gen`, from the DB, seed 67 |
| Comparison run | 170 | 67 root/word, 45 meaning search, 58 must-refuse; sampled from both sets |
| Held-out round 1 | 62 | Imama's questions at the time; **now consumed by tuning** |

Rule: any question used for tuning counts as dev. A fresh batch from Imama is needed for another honest test.

## Five systems compared
`prompt_only` (Gemini, no retrieval), `semantic_only` (MiniLM), `exact_only` (exact root lookup), `hybrid_db` (lookup plus MiniLM, database answer), `hybrid_llm` (Wasl: same plus Gemini, verifier, DB fallback).

## Final comparison (run 2, the cleanest). 170 questions, MiniLM, gemini-3.5-flash-lite
| System | Root P | Root R | Meaning hit@3 | Refusals ok | False refusals |
|---|---|---|---|---|---|
| prompt_only | 0.70 [0.61–0.79] | 0.56 [0.47–0.66] | 42/45 = 0.93 [0.82–0.98] | 50/58 = 0.86 | 10/112 = 0.09 |
| semantic_only | 0.04 | 0.01 | 35/45 = 0.78 [0.64–0.87] | 42/58 = 0.72 | 67/112 = 0.60 |
| exact_only | 0.94 | 0.94 | 22/45 = 0.49 | 46/58 = 0.79 | 24/112 = 0.21 |
| hybrid_db | 0.94 | 0.94 | 35/45 = 0.78 | 54/58 = 0.93 | 8/112 = 0.07 |
| hybrid_llm | 0.92 [0.85–0.98] | 0.89 [0.82–0.96] | 36/45 = 0.80 [0.66–0.89] | 58/58 = 1.00 [0.94–1.00] | 12/112 = 0.11 [0.06–0.18] |

Counts right: prompt_only 0/2; exact_only 47/47; hybrid_db 47/47; hybrid_llm 46/46. hybrid_llm meaning precision 0.78.
Honest framing: exact and hybrid_db scores are partly by construction (labels come from the same database). Prompt-only beats the hybrid on meaning search but loses on roots, counts, refusals and verifiability.

## Latency, tokens, cost (hybrid_llm)
- Median 1.22 s, p95 9.70 s (includes 503 retry waits). prompt_only: median 1.86 s, p95 16.64 s.
- 123 calls, 110,848 tokens in, 15,063 out (about 900 in and 122 out per call). prompt_only: 170 calls, 13,948 in, 4,909 out, only 97/170 measured.
- One provider error (g037, 503, fell back to the database).
- **Cost: no dollar figure exists.** The run was not given prices. Set `LLM_PRICE_IN_PER_M` and `LLM_PRICE_OUT_PER_M` (real current prices, do not guess) and rerun. The runs used the free tier.

## Error analysis (hybrid_llm): 14 failures
| Cause | n | Ids |
|---|---|---|
| Word not recognised (rough transliteration) | 4 | i35 (mubtala/balaa), i44 (biyadih), i45 (Jahar), i46 (Tibaka) |
| Retrieval missed, refusal defensible | 4 | m14, m17, m22, m33 |
| LLM refused although evidence present (real over-refusal) | 3 | m18, m25, i01 |
| Interpretive question refused | 1 | i08 |
| Wrong route | 1 | i10 |
| Label disputed (qiyamat not in the surah; refusal is right) | 1 | i36 |

Debug output for m18 and m25 showed Gemini refusing even though ayah 20/25 was in the evidence.

## Held-out round 1 (Imama's questions, MiniLM, before the final fixes)
51/62 pass; routing 28/35; root accuracy 15/19; refusals 24/27; false refusals 6/35 (17%); hit@3 12/14 through the pipeline. Retriever alone: P@1 0.94, MRR 0.97, hit@3 16/16.

## Proposal targets vs measured
| Target | Goal | Measured | Status |
|---|---|---|---|
| Routing | ≥90% | 80% held-out | Not met |
| Root accuracy | ≥90% | 79% held-out (0.92/0.89 on comparison, dev data) | Not met |
| False refusals | ≤10% | 11% [6–18%] | Borderline |
| p95 latency | <5 s | 9.7 s | Not met |
| Invalid citations | 0 | 0 | Met |

Not measured yet: unsupported-claim rate; counts-right for prompt-only has only 2 data points.

## Earlier results worth remembering
- TF-IDF dev: 31/33; MiniLM dev: 32/33; LLM run: 22 verified, 1 fallback (after verifier fix).
- Generated gate checks and threshold sweeps picked the 0.38 / 0.28 MiniLM values.
