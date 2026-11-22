# Wasl handoff: start here

Written 2026-11-23 so a new chat can pick up the project with nothing lost.

## What this is
Wasl (Quran Root Explorer) for **Surah Al-Mulk (67)**. Course project for GenAI (AI-4009, FAST-NUCES). Pure Product track; the final deliverable is a system demonstration paper. Supervisor: Dr. Akhtar Jamil.

- **Huzaifa** (huzaifastarburst27@gmail.com, git `HuzaM1001`): owns the RAG / LLM part. This is the user in the chat.
- **Imama Sarwar**: owns data, backend, frontend, learning mode, dashboard, deployment. Repo: https://github.com/ImamaSarwar/Wasl

Assignment 3 (the "AI Evaluation Slides or Dashboard" requirement) has been **submitted**. The main deadline is much later, so quality beats speed.

## Files in this handoff
| File | What it holds |
|---|---|
| `01_PROJECT_AND_WORKING_STYLE.md` | Project, constraints, how the user wants to be helped |
| `02_SYSTEM_ARCHITECTURE.md` | How the RAG pipeline works, thresholds, verifier, LLM client |
| `03_CODE_FILES_AND_WORKFLOW.md` | Every file and patch, tests, commands, git workflow |
| `04_EVALUATION_RESULTS.md` | Test sets, all measured numbers, error analysis, targets |
| `05_NEXT_STEPS.md` | Prioritised roadmap, known issues, open questions |
| `06_DELIVERABLES_AND_DECISIONS.md` | Proposal docx, slide decks, decisions, bugs already fixed |

## Honest caveat
These notes were written from my own running summary of the chat. Exact numbers come from the final comparison run (run 2) the user pasted. Command flags are listed from memory of the code: run `python -m eval.run_baselines --help` (and the same for other scripts) before relying on a flag. The full old transcript, if still available in the old session, is at `/root/.claude/projects/-home-claude/0ea9e425-98cb-5495-9c22-a0f6547613e1.jsonl`.

## Paste this as the first message in the new chat
> I am Huzaifa, continuing the Wasl project (Quran Root Explorer, Surah Al-Mulk, GenAI course AI-4009). I own the RAG/LLM part; Imama Sarwar owns data, backend, frontend and deployment (repo ImamaSarwar/Wasl). Assignment 3 is submitted. I am attaching handoff notes 00–06. Please read them all first, then confirm the state in five lines and start on the first item in `05_NEXT_STEPS.md`. I use PowerShell and VS Code, commit via VS Code in one combined message, and want baby-step Hinglish instructions. Never put my API key in chat, commits or screenshots.

Also attach in the new chat, if you can: the latest `eval/results/*.json`, the proposal docx, and the repo (or tell the assistant to add `ImamaSarwar/Wasl` as a repo).
