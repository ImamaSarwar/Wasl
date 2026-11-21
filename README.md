# Wasl — Quran Root Explorer (Surah Al-Mulk)

**Wasl** is a root-based reader and AI-assisted study tool for **Surah Al-Mulk** (Qur'an 67)[cite: 52]. Hover over any word to see its root, plain-English grammar, and meaning, or click a rooted word to open its root family tree, verse occurrences, recitation with word highlighting, tafsir, personal notes, and the verified learning assistant[cite: 52].

```text
Browser (React, :5173)  --/api-->  FastAPI (:8000)  -->  SQLite (data/quran.db)
```

---

## 1. Prerequisites

Make sure you have the following installed before running the project:

* **Git**
* **Python 3.10+** (or `py` on Windows)
* **Node.js 18+** (includes `npm`)

Check your versions in the terminal:

```bash
git --version
python --version        # On Windows PowerShell, you can also run: py --version
node --version
npm --version
```

---

## 2. Installation

### 2.1 Clone the repository

```bash
git clone https://github.com/ImamaSarwar/Wasl.git
cd Wasl
```

### 2.2 Set up the Python backend

**macOS / Linux**

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

> If PowerShell blocks activation scripts, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` and try activating `.venv` again.

If you plan to run the AI assistant features locally, copy `.env.example` to `.env` and add your `GEMINI_API_KEY`:

```bash
cp .env.example .env
```

### 2.3 Build the SQLite database

With `.venv` active, build `data/quran.db` from the raw source files[cite: 52]:

```bash
python scripts/build_db.py
```

Expected output:

```text
Built data/quran.db
  ayahs: 30
  words: 333
  words with a root: 209
  distinct roots: 128
```

### 2.4 Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## 3. Running the App

Run the backend and frontend in two separate terminals so both stay active.

### Terminal 1 — Start the FastAPI backend

From the project root with `.venv` active:

```bash
uvicorn backend.main:app --reload
```

* API docs: `[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)`
* Health check: `[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)`

### Terminal 2 — Start the React frontend

```bash
cd frontend
npm run dev
```

Open **`http://localhost:5173`** in your browser.

---

## 4. What You Can Use in the Demo

* **Surah Reader:** Read all 30 ayahs of Surah Al-Mulk with Arabic text, English translation, and transliteration[cite: 52].
* **Hover Word Cards:** Hover over any word to see its meaning, root letters, plain-English grammar, and attested past/present forms (particles show `"No root"`)[cite: 52].
* **Root Family Tree & Drill-Down:** Click a rooted word to inspect its family tree (root, lemma, morphological form, occurrence), verse chart, co-occurring roots, and highlighted ayahs[cite: 52].
* **Recitation with Word Highlighting:** Pick a reciter from the top of the surah card to play an ayah or the whole surah with word highlighting (requires internet to stream audio)[cite: 52].
* **Tafsir Panel:** Open English Tafsir Ibn Kathir commentary grouped by ayah ranges per ayah[cite: 52].
* **Personal Notes:** Save per-ayah notes in browser `localStorage` (marked with a gold dot) and export them as a `.txt` file[cite: 52].
* **Learning Assistant:** Ask grounded questions about roots, word forms, comparisons, or concepts in Surah Al-Mulk[cite: 52].

---

## 5. Running Tests

Run backend unit tests from the repository root (with `.venv` active):

```bash
python -m unittest discover -s tests -v
```

Run frontend storage tests:

```bash
cd frontend
npm test
cd ..
```

---

## 6. Project Structure

```text
Wasl/
├── README.md
├── requirements.txt            # Backend Python dependencies
├── .env.example                # Environment template (copy to .env)
├── data/
│   ├── raw/                    # Original source files (do not edit)
│   ├── corrections.csv         # Reviewed manual fixes
│   ├── CREDITS.md              # Dataset attributions and licenses
│   └── quran.db                # Generated SQLite database (git-ignored)
├── scripts/
│   ├── build_db.py             # Builds data/quran.db from raw sources
│   └── diff_sources.py         # Compares corpus root entries
├── backend/
│   ├── main.py                 # FastAPI endpoints
│   ├── queries.py              # SQL query functions
│   └── grammar.py              # Plain-English grammar labels
├── rag/                        # Routing, retrieval, Gemini client, verifier
├── eval/                       # Evaluation sets and scripts
├── tests/                      # Backend unit tests
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api.js
        ├── styles.css
        └── components/
```

---

## 7. Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | Activate `.venv` first, then run `pip install -r requirements.txt` |
| `uvicorn: command not found` | Run `python -m uvicorn backend.main:app --reload` inside `.venv` |
| `no such table` or missing database | Run `python scripts/build_db.py` from the repo root |
| Frontend says `"Cannot reach the backend"` | Make sure Terminal 1 is running on port `8000` and `/api/health` responds |
| Port `8000` or `5173` already in use | Stop the other process or pass `--port 8001` to `uvicorn` |
| `npm install` fails | Check `node -v` is `18+`, delete `frontend/node_modules`, and run `npm install` again |

---

## 8. Credits & Data Sources

Dataset sources, attributions, and licensing notes are listed in `data/CREDITS.md` and in the application footer[cite: 52].
