# Wasl - Quran Root Explorer (Surah Al-Mulk)

Hover a word to see its root. Click it to open the root's family tree, the ayahs it appears in, and a
chat box for questions (the AI assistant comes in a later phase).

```
Browser (React, :5173)  --/api-->  FastAPI (:8000)  -->  SQLite (data/quran.db)
```

---

## 1. One-time setup

You need: **Git**, **Python 3.10+**, **Node.js 18+** (20 or 22 is fine), and **VS Code**.
Check them:

```bash
git --version
python --version        # Windows may need:  py --version
node --version
npm --version
```

### 1.1 Get the code (person who owns the repo goes first)

```bash
git clone https://github.com/ImamaSarwar/Wasl.git
cd Wasl
```

Copy everything from this starter kit into the cloned folder (keep the folder structure, include the
hidden files `.gitignore`, `.gitattributes`, `.vscode/`), then:

```bash
git add .
git commit -m "Add project scaffold: data pipeline, API, React frontend"
git push origin main
```

The second person then just clones (same `git clone` command above). If the repo already has a
`README.md` from GitHub, let this one replace it.

Open the folder in VS Code: `code .` (or File > Open Folder). Accept the "install recommended
extensions" prompt.

### 1.2 Python backend (each person, once)

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
If PowerShell refuses to run the activate script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry.
In VS Code press `Ctrl+Shift+P`, "Python: Select Interpreter", and choose the `.venv` one.

You'll know it worked when your terminal prompt starts with `(.venv)`.

### 1.3 Build the database

```bash
python scripts/build_db.py
```
Expected output:
```
Built data/quran.db
  ayahs: 30
  words: 333
  words with a root: 209
  distinct roots: 128
  corrections applied: 0
```
If it prints `ALIGNMENT PROBLEMS`, the raw files were changed - re-download them from the repo.

Run the tests (no extra packages needed):
```bash
python -m unittest discover -s tests -v      # expect: Ran 7 tests ... OK
```

### 1.4 Frontend (each person, once)

```bash
cd frontend
npm install
cd ..
```

---

## 2. Run it (every working session: two terminals)

**Terminal 1 - backend** (from the repo root, venv active)
```bash
uvicorn backend.main:app --reload
```
Check: open http://127.0.0.1:8000/docs - you should see the endpoint list. Try `GET /api/roots/{root}/tree`
with root `خلق`; you should get 4 occurrences in 2 forms (ayahs 2, 3, 14).

**Terminal 2 - frontend**
```bash
cd frontend
npm run dev
```
Open http://localhost:5173.

What you should see and be able to test:
- The surah on the left. **Hover** a word: a dark card shows root, lemma, type, grammar and the ayah translation. Particles say "No root".
- **Click** a rooted word: the right panel shows the family tree (thicker branch = more occurrences), a 30-bar chart of which ayahs contain it, "Appears together with" roots, and the ayahs for the selected form with the word highlighted yellow.
- The **Debug** box at the bottom right shows every API call and its raw JSON, so you can check the UI against the backend.
- The **Ask** box already calls `POST /api/ask`; it returns a placeholder until the AI phase.

If the page says "Cannot reach the backend", terminal 1 isn't running.

---

## 3. Folder structure (and who edits what)

```
Wasl/
  README.md
  requirements.txt            # backend deps (light)
  requirements-rag.txt        # AI deps (install later; large)
  .env.example                # copy to .env for API keys (never commit .env)
  data/
    raw/                      # the original source files - NEVER edit these
    corrections.csv           # your manual verification fixes (applied by build_db.py)
    CREDITS.md
    quran.db                  # generated, git-ignored
  scripts/
    build_db.py               # raw files -> data/quran.db
    diff_sources.py           # lists root disagreements between the two corpora
  backend/
    queries.py                # all SQL, plain functions (tested)
    main.py                   # FastAPI endpoints that call queries.py
  rag/                        # (later) router, retrieve, generate, verify
  eval/                       # (later) questions.jsonl, run_eval.py
  tests/test_queries.py
  frontend/
    package.json  vite.config.js  index.html
    src/
      main.jsx  App.jsx  api.js  styles.css
      components/  AyahLine  HoverCard  TreeView  RootPanel  AskBox  DebugPanel
```

Suggested split for two people (so you rarely touch the same file):

| Person A | Person B |
|---|---|
| `data/`, `scripts/`, `backend/`, `rag/`, `eval/`, `tests/` | `frontend/` (and applying the Figma design) |

Both of you split the manual root verification (Section 5) - one takes ayahs 1-15, the other 16-30.

---

## 4. Git workflow for two people

Rule: **`main` always works.** Do your work on a branch and merge it via a Pull Request (PR).

Start a piece of work:
```bash
git checkout main
git pull
git checkout -b feat/short-name        # e.g. feat/tree-styling, feat/verify-roots-1-15
```

Save often:
```bash
git status
git add <files>                        # or:  git add .
git commit -m "Say what changed and why"
```

Share it:
```bash
git pull --rebase origin main          # grab the other person's latest work first
git push -u origin feat/short-name     # first push of the branch (later just: git push)
```
Then on GitHub click **Compare & pull request**, the other person glances at it and clicks **Merge**.
After merging:
```bash
git checkout main
git pull
```

Habits that prevent most pain:
- `git pull` before you start every session.
- Don't both edit the same file at once. If a merge conflict happens, VS Code shows "Accept Current / Incoming / Both" buttons in the file; resolve, then `git add` the file and `git rebase --continue` (or `git commit` if you merged).
- Never commit `.env`, `node_modules/` or `data/quran.db` (already in `.gitignore`).
- Never edit anything in `data/raw/`.
- Tell each other when you change the API shape (a new field in a response), since the frontend depends on it.

---

## 5. Next steps, in order

1. **Verify the data.** Run `python scripts/diff_sources.py`. The two sources disagree on **one** root: ayah 2, word 6 (`أَيُّكُمْ`, mustafa0x added `أيي`; the original has none). Decide it on corpus.quran.com and record the decision in `data/corrections.csv`. Then check every one of the 209 rooted words against corpus.quran.com (split by ayah range) and mark them verified: add a row `ayah,pos,verified,1,checked` per word. Fixes use the same file: `ayah,pos,root,<new root>,<reason>`. Re-run `python scripts/build_db.py` after editing.
2. **Frontend polish** with the Figma design. Colours and fonts are CSS variables at the top of `src/styles.css`; each panel is its own component.
3. **Cross-reference view**: the data is ready at `GET /api/cross`; build a richer view than the current list.
4. **AI assistant** (after first submission): `pip install -r requirements-rag.txt`, then implement `rag/` and plug it into `/api/ask`. See the main guide, Phase 4.
5. **Evaluation set** in `eval/questions.jsonl`.

First-submission checklist (14-22 Nov): verified database, backend API, hover + tree + drill-down in the UI, README, a short demo run-through.

---

## 5b. Word meanings, transliteration, plain-English grammar, past/present forms

Added to the hover card and the reader:

| What | Where it comes from | Notes |
|---|---|---|
| Meaning of each word | `data/raw/english-wbw-translation.json` -> `words.gloss` | The build **stops with an error** if this file does not line up with our 333 words. Fix a wrong meaning in `data/corrections.csv` (`field` = `gloss`). |
| Transliteration under each ayah | `data/raw/en-transliteration-tajweed.json` -> `ayahs.transliteration` | Shown as-is, including the `;` pause marks. |
| "Verb / Past / he / Form VI..." in plain English | `backend/grammar.py` | Only a display layer. The raw codes (`PERF,3MS,form 6`) stay in the database because the RAG code uses them. To reword a label, edit the dictionaries at the top of that file. |
| Past and present/future form of a verb | `scripts/build_db.py` (`load_verb_forms`) | Looked up in the same morphology file: the form of that verb (same root, base form and verb pattern) that actually occurs elsewhere in the Qur'an as "he did" / "he does". Nothing is generated by grammar rules. "Not found in the Qur'an" means there is no such clean form in the data. |

**After pulling these changes, rebuild the database:** `python scripts/build_db.py`
(the schema gained columns, and `data/quran.db` is not stored in git).

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: fastapi` | The venv isn't active. Activate it (Section 1.2) and `pip install -r requirements.txt` |
| `no such table` / empty data | Run `python scripts/build_db.py` |
| `uvicorn: command not found` | Venv not active, or use `python -m uvicorn backend.main:app --reload` |
| Browser: "Cannot reach the backend" | Start terminal 1; confirm http://127.0.0.1:8000/api/health returns `{"ok":true,...}` |
| `TypeError` mentioning `str | None` | Python older than 3.10; upgrade Python |
| Arabic shows without diacritics or as boxes | The Google font failed to load (offline?); it falls back to a system Arabic font |
| Port already in use | Close the old terminal, or `uvicorn backend.main:app --port 8001` (and update `vite.config.js`) |
| `npm install` fails | Check `node --version` is 18+; delete `frontend/node_modules` and retry |

Data credits: see `data/CREDITS.md`. The footer of the site shows them too.
