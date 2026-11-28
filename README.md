# Wasl: Quran Root Explorer (Surah Al-Mulk)

Wasl ("connection") is a web app that teaches the vocabulary of **Surah Al-Mulk** (Qur'an 67: 30 ayahs, 333 words) through Arabic roots. Hover over any word to see its root, meaning and grammar in plain English, follow the root to every related word and ayah, listen to four reciters, read the tafsir, keep notes, ask a learning assistant, and practise with quizzes that adapt to your mistakes.

**Design rule:** every fact comes from a verified database. Generative AI (Gemini) only writes explanations, and a deterministic verifier checks every AI text against the database before it is shown. If the check fails, you see the database text instead.

| | |
| --- | --- |
| **Live app** | _to be added after deployment_ |
| **API docs** | `/docs` on the backend (Swagger UI), `/openapi.json` |
| **Repository** | https://github.com/ImamaSarwar/Wasl |
| **Team** | Huzaifa Muhammad (23i-0608), Imama Sarwar (23i-3048) |

---

## Current status (28 November 2026)

| Area | Status |
| --- | --- |
| Reader, hover card, root tree, recitation, tafsir, notes (F1 to F6) | Built and tested |
| Learning assistant with Gemini and verifier (F7 to F10) | Built and evaluated |
| Root Tutor (F11) | Built; Gemini run not yet scored |
| Quiz with AI feedback and adaptive question selection (F14) | Built and evaluated |
| Progress dashboard (F15) | Built and tested |
| Goal-based lessons (F12) | Not built |
| Root comparison view (F13) | Partly built (comparison questions in the assistant) |
| Data cross-check (F16) | Partly built (two-source morphology diff; API sync not built) |
| Automated tests | 223 backend + 28 frontend, all passing |
| Docker, CI, public deployment, AI call logging | **Not built yet** (see "Docker" below) |

---

## How it works

```text
Browser (React + Vite, :5173)
   |  /api (JSON)                       audio streamed from the reciters' CDNs
FastAPI backend (:8000)
   |-- deterministic core: SQL queries, plain-English grammar, quiz generator
   |-- assistant package (rag/): scope gates -> resolver -> retrieval -> evidence by SQL
   |                              -> Gemini drafts JSON -> verifier -> (retry once) -> database fallback
SQLite database (data/quran.db), read-only, built from data/raw by scripts/build_db.py
```

**Where AI is used**

| Feature | AI | What stops it from being wrong |
| --- | --- | --- |
| Learning assistant (`POST /api/ask`) | Gemini writes the answer; all-MiniLM-L6-v2 finds ayahs for questions that name no root | Scope gates, evidence by SQL, verifier on every claim, database answer as fallback |
| Root Tutor (`GET /api/roots/{root}/lesson`) | Gemini explains how a root forms its words | Grammar terms must be recorded facts; quotes must match; database lesson as fallback |
| Quiz feedback (`POST /api/quiz/feedback`) | Gemini explains a wrong answer | Server re-grades; each sentence checked against the evidence for its own option; template fallback |
| Everything else (text, roots, grammar, quiz questions and keys, adaptive selection, dashboard) | None | Deterministic code over the database or the browser's stored answers |

Notes and quiz progress are stored only in your browser and are never sent to the server.

---

## 1. Prerequisites

- **Git**
- **Python 3.10+** (`py` on Windows)
- **Node.js 18+** (includes `npm`)
- A **Gemini API key** from Google AI Studio (optional: without it every AI feature returns database text)

```bash
git --version
python --version      # Windows: py --version
node --version
npm --version
```

---

## 2. Setup

### 2.1 Clone

```bash
git clone https://github.com/ImamaSarwar/Wasl.git
cd Wasl
```

### 2.2 Python environment

**Windows (PowerShell)**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-rag.txt
```

If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-rag.txt
```

`requirements-rag.txt` includes `requirements.txt` and adds the retrievers (sentence-transformers pulls in PyTorch, a large download). `requirements.txt` alone runs the reader without meaning search.

### 2.3 Configuration

Copy the example file and fill it in. **Never commit `.env`** (it is git-ignored).

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

| Variable | Example | Meaning |
| --- | --- | --- |
| `LLM_PROVIDER` | `gemini` | `gemini` (default) or `openai_compatible` |
| `LLM_API_KEY` | _your key_ | Gemini API key; leave empty to run without AI text |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | The model used in our evaluation |
| `WASL_RETRIEVER` | `minilm` | Meaning-search retriever. **Set this**: the code default is `tfidf`, and all reported results used `minilm` |
| `LLM_BASE_URL` | | Only for `openai_compatible` providers |

### 2.4 Build the database

```bash
python scripts/build_db.py
```

Expected output ends with:

```text
Built data/quran.db
  ayahs: 30
  words: 333
  words with a root: 209
  distinct roots: 128
```

### 2.5 Frontend packages

```bash
cd frontend
npm install
cd ..
```

---

## 3. Run

Use two terminals.

**Terminal 1: backend** (repository root, virtual environment active)

```bash
uvicorn backend.main:app --reload
```

Check http://127.0.0.1:8000/api/health returns `{"ok": true, "roots": 128}`. API docs: http://127.0.0.1:8000/docs

**Terminal 2: frontend**

```bash
cd frontend
npm run dev
```

Open http://localhost:5173

---

## 4. Docker

**Not available yet.** The repository does not contain Dockerfiles or a Compose file as of 28 November 2026. The planned command, once they are added, is:

```bash
docker compose up --build
```

It will build the backend image (database built at image build time, read-only at run time) and the frontend image, and read secrets from `.env`. The deployment runbook lists the steps.

---

## 5. Tests and evaluation

```bash
pip install pytest            # once
python -m pytest -q           # 223 backend tests

cd frontend
npm test                      # 28 frontend tests
cd ..
```

AI evaluation (results are written to `eval/results/`, which is git-ignored; Gemini replies are cached in `.llm_cache/`):

```bash
python eval/run_verifier.py                      # assistant verifier on 480 drafts (offline)
python -m eval.run_baselines                     # assistant vs 4 alternatives (needs .env)
python -m eval.run_quiz_feedback --faulty        # quiz-feedback verifier on broken drafts (offline)
python -m eval.run_quiz_feedback                 # Gemini quiz feedback on 60 wrong answers (needs .env)
python -m eval.run_quiz_feedback --ratings eval/results/quiz_feedback_rating.csv   # after human rating
```

**Headline results**

| Measure | Result |
| --- | --- |
| Assistant, root precision / recall (170 questions) | 0.92 / 0.89 (prompt-only Gemini: 0.70 / 0.56) |
| Assistant, out-of-scope questions refused | 58 / 58 |
| Assistant, false refusals | 12 / 112 (11%) |
| Verifier, faulty drafts rejected | 357 / 357 (assistant), 525 / 525 (quiz feedback); no good draft rejected |
| Quiz feedback, verified Gemini explanation shown | 60 / 60 (56 first try, 4 after one retry) |
| Latency, median / p95 | Quiz feedback 1.1 s / 1.9 s; assistant 1.22 s / 9.70 s |
| Cost per assistant call | about USD 0.00058 at paid-tier Gemini prices |

Full numbers, error analysis and what is still missing are in the Product Evaluation Report.

---

## 6. Project structure

```text
backend/        FastAPI app (main.py), SQL queries, plain-English grammar, quiz generator
rag/            Assistant package: gates, resolver, retrievers, evidence, Gemini client,
                generators (assistant, Root Tutor, quiz feedback) and verifiers
frontend/       React app (Vite, d3): reader, root tree, assistant, quiz, dashboard
scripts/        build_db.py and data import, diff and debugging tools
data/           raw sources, corrections.csv, CREDITS.md (quran.db is generated)
eval/           test sets, baselines, verifier fault sets, quiz-feedback evaluation
tests/          backend unit tests
docs/           project documentation
```

---

## 7. Documentation

| Document | Contents |
| --- | --- |
| Product Requirements Document | Users, features F1 to F16 with acceptance criteria and status, non-functional requirements |
| Architecture Document | Architecture diagram, components, data model, AI vs deterministic parts |
| AI Card | Models and versions, purpose, data, results, limitations, risks and safeguards per AI component |
| API Documentation | All 16 endpoints with parameters and examples (live schema at `/docs`) |
| User Guide and Deployment Runbook | How to use the app; configuration, local run, deployment plan, operations |
| Product Evaluation Report | Functional tests, AI evaluation, robustness and safety, performance and cost |
| AI Tool Declaration | AI tools used to build the product and write the documents |
| System demonstration paper | IEEE conference format, 4 to 6 pages |

---

## 8. Troubleshooting

| Problem | Fix |
| --- | --- |
| `vite` is not recognised | Run `npm install` in `frontend` |
| Frontend shows network errors | Start the backend first; check http://127.0.0.1:8000/api/health |
| Every AI answer is database text | Check `LLM_API_KEY` and `LLM_MODEL` in `.env`; run `python scripts/check_llm.py`; the response's `llm_error` says why |
| Meaning questions are refused | Install `requirements-rag.txt` and set `WASL_RETRIEVER=minilm` |
| No audio | Recitation needs internet; try another reciter |
| Notes or progress disappeared | They live in this browser only; clearing browser data deletes them. Export notes regularly |

---

## 9. Data, credits and disclaimer

Qur'anic text: Tanzil. Roots, lemmas and grammar: Quranic Arabic Corpus v0.4. Word-by-word meanings, transliteration and translation: QUL exports. Tafsir: Tafsir Ibn Kathir (English). Recitations are streamed from the providers' CDNs, not redistributed. Full sources and licences: `data/CREDITS.md`.

Wasl is a learning aid for vocabulary, not a religious authority. It does not interpret the Qur'an or give rulings; for those, please ask a qualified scholar.
