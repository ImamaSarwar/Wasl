# Project and working style

## Project
- **Name:** Wasl, also called Quran Root Explorer. Scope is one surah, Al-Mulk (67), 30 ayahs.
- **Idea:** a learner asks about Arabic roots, word forms, lemmas and meanings in the surah. Answers come from a SQLite database of the surah, with an LLM allowed only to phrase answers from retrieved evidence. Every claim is checked by a verifier. If the LLM fails or is unverifiable, a database-only answer is shown.
- **Course:** GenAI, AI-4009, FAST-NUCES. Pure Product track. Final deliverable: a system demonstration paper (plus live demo).
- **Assignment 3 requirement:** "AI Evaluation Slides or Dashboard" covering test sets, metrics, baseline comparisons (S1–S4), error analysis with at least 10 grouped failure examples, and latency and cost. Submitted.

## People and split of work
- **Huzaifa (the user):** RAG, LLM generation, verifier, evaluation harness, question sets, baselines, metrics, proposal edits. Writes in Hinglish chat; uses Windows PowerShell and VS Code.
- **Imama Sarwar:** data, backend, frontend (works; `npm install` was needed for vite), learning mode, dashboard, deployment. She also wrote 46 held-out questions (ids i01–i46).
- **Dr. Akhtar Jamil:** supervisor.

## Standing constraints (from the user)
1. API key lives only in the git-ignored `.env`. Never paste the key in chat, commits or screenshots.
2. The user commits through **VS Code**, one big combined commit message. The assistant delivers code as **patches** the user applies (`git apply --ignore-whitespace`). Do not commit or push unless asked.
3. Instructions must be baby-step, PowerShell-friendly, Hinglish tone is welcome.
4. Keep Imama's held-out questions honest. Questions used for tuning become dev data.
5. Never invent numbers. Costs need real token prices supplied by the user.
6. Fix proposal overclaims; keep the proposal consistent with what is actually built.

## How the assistant should work with this user
- Quality over speed: the main deadline is far away.
- Explain what a result means honestly, including misses (several proposal targets are not met).
- The sandbox cannot call the Gemini API for the user; the user runs evals locally and pastes output.
- The sandbox can read the repo only via `git fetch` (the GitHub API returned 403).
- A stop hook repeatedly asked to commit/push; the assistant declined each time because the user commits by hand.

## Environment on the user's machine
- `.env` holds the Gemini key and `LLM_MODEL=gemini-3.5-flash-lite` (free tier). `gemini-3.8-flash` timed out; `gemini-3.6-flash` works but 503s at times.
- Override the model for one run in PowerShell: `$env:LLM_MODEL = "gemini-3.6-flash"`.
- Price variables for cost (user must set real values): `LLM_PRICE_IN_PER_M`, `LLM_PRICE_OUT_PER_M`.
- The Gemini free tier daily quota ran out repeatedly; evals are cached and resumable.
