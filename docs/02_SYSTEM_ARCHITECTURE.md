# System architecture (the RAG part)

## Pipeline, in order
1. **Scope gates** (regexes in `rag/pipeline.py`): `OUT_OF_SCOPE` (personal and theological questions), `OTHER_SURAH` (other surahs, ayat al-kursi, ayat an-nur, the throne verse), `TAFSIR` (hidden/secret/symbolic meaning, scholar names, "what do scholars say"). A hit means refuse.
2. **Resolver** (`rag/resolve.py`): maps the question to an Arabic or Latin root, lemma, or concept (`rag/concepts.json`). Has an exact word-form spelling index `_LAT_EXACT` (ayn/hamza kept, short forms allowed).
3. **Intent:** one of `single_root`, `meaning`, `compare`, `concept`, `semantic`.
4. **Evidence** from SQLite for the resolved root/lemma/forms.
5. **Optional LLM generation** (Gemini REST) using the evidence only.
6. **Verifier** checks the answer against the evidence.
7. **Fallback:** if the LLM fails, refuses wrongly, or the verifier rejects, show the database-only answer.

## Semantic retrieval
- Retrievers: TF-IDF baseline and MiniLM (sentence embeddings). MiniLM is the default.
- Thresholds (`rag/retrieve.py`): `THRESHOLDS = {"tfidf": 0.18, "minilm": 0.38}`, `THRESHOLDS_LOW = {"tfidf": 0.18, "minilm": 0.28}`, helper `threshold_low(name)`.
- **Three zones for meaning questions:** best score below 0.28 means refuse; 0.28 to 0.38 is borderline (Gemini judges; refused if the LLM is unavailable); 0.38 or above means answer. TF-IDF has no borderline band.
- Retriever alone on the held-out set: P@1 0.94, MRR 0.97, hit@3 16/16.

## Concept-path hijack and its fix
Topic words like "disbelievers" routed to root evidence and hid the real answer. Fix: for intent `concept` with the LLM on, attach `extra` ayahs from meaning search, shown to the model as "ALSO CLOSE IN MEANING TO THE QUESTION". Residual over-refusals remain (m18, m25, i01).

## Generation (`rag/generate.py`)
- `SYSTEM` prompt, rules 1–9. Rule 7: for semantic type, the evidence is candidate ayahs; refuse only if none relates. Rule 8: always cite at least one ayah. Rule 9: use the "ALSO CLOSE IN MEANING" ayahs when they help.
- Reply is JSON: `{"refuse","answer","claims":[{ayah,root,lemma,gloss}]}`; a refusal also carries `"reason"`.
- Functions: `_matched_line`, `_extra_lines`, `format_evidence(intent, evidence, extra=None)`, `build_user_prompt(question, intent, evidence, previous_errors=None, matched=None, extra=None)`, `ask(..., matched=None, extra=None, **llm_kwargs)`.

## Verifier (`rag/verify.py`)
- Checks cited ayahs, each claim's root/lemma/gloss, quoted text, counts and rulings.
- `_canon` canonicalises lemmas (fatha before alif, dagger alif, alif maqsura/ya, tatweel) but keeps verb versus noun vowel distinctions (خَلَقَ vs خَلْق).
- Claims count as citations. Quote allowlist: Arabic words/lemmas from the evidence plus the learner's own words. Allowed counts include `len(forms)` and `len(ayahs)`.
- Helpers: `_gloss_norm`, `_lemma_ok`, `_index(intent, evidence, extra=None)`, `check(raw, intent, evidence, question=None, extra=None)`.
- Gaps promised in the proposal and not yet built: level-labelled counts (root/lemma/form/occurrence), an Arabic-token check, the extra verifier layers.

## LLM client (`rag/llm.py`)
- Gemini REST with retries on 429/5xx, disk cache in `.llm_cache/`, hints for 500/502/503/504.
- Records `LAST_CALL = {"latency","tokens_in","tokens_out","cached","measured"}`; `_usage(provider, data)` reads token counts.
- Cache entries made before timing existed are flagged `measured=False` and excluded from latency/token statistics.

## Pipeline details (`rag/pipeline.py`)
- `_semantic(q, retriever=None, threshold=None, use_llm=False)` returns a `borderline` flag.
- `_with_llm` collects `llm_stats`: calls, latency, cached_latency, tokens_in, tokens_out, unmeasured.
- The semantic path refuses borderline answers the LLM did not vouch for. `llm_reason` is kept on LLM refusals.

## Known behaviour to remember
- Answers still say "forms" when they mean lemmas.
- Prompt-only Gemini does better on meaning search than the hybrid (0.93 vs 0.80) but worse on root precision/recall, counts, refusals and verifiability.
