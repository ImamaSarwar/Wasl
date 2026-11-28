"""
Wasl API. Run from the repo root:
    uvicorn backend.main:app --reload
Interactive docs: http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import queries, quiz
from rag.pipeline import answer as rag_answer
from rag.quiz_feedback import feedback as quiz_feedback
from rag.tutor import lesson as root_lesson

app = FastAPI(title="Wasl - Quran Root Explorer (Surah Al-Mulk)")

# The Vite dev server proxies /api to us, but allow direct calls too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "roots": len(queries.list_roots())}


@app.get("/api/ayahs")
def ayahs():
    return queries.get_ayahs()


@app.get("/api/words/{word_id}")
def word(word_id: int):
    w = queries.get_word(word_id)
    if not w:
        raise HTTPException(404, "word not found")
    return w


@app.get("/api/roots")
def roots():
    return queries.list_roots()


@app.get("/api/roots/{root}/tree")
def tree(root: str):
    t = queries.root_tree(root)
    if not t["forms"]:
        raise HTTPException(404, f"root '{root}' does not occur in Surah Al-Mulk")
    return t


@app.get("/api/roots/{root}/forms/{lemma}/ayahs")
def form_ayahs(root: str, lemma: str):
    return queries.form_ayahs(root, lemma)


@app.get("/api/roots/{root}/lesson")
def lesson(root: str):
    """Root Tutor: LLM-written lesson checked against the database; database-only lesson as fallback."""
    res = root_lesson(root, use_llm=True)
    if res is None:
        raise HTTPException(404, f"root '{root}' does not occur in Surah Al-Mulk")
    return res


@app.get("/api/roots/{root}/distribution")
def distribution(root: str):
    return queries.distribution(root)


@app.get("/api/cross")
def cross(root: str | None = None, min_ayahs: int = 2):
    return queries.cross(root, min_ayahs)


@app.get("/api/reciters")
def reciters():
    return queries.list_reciters()


@app.get("/api/recitations/{reciter_id}")
def recitations(reciter_id: str):
    r = queries.get_recitations(reciter_id)
    if r is None:
        raise HTTPException(404, f"unknown reciter '{reciter_id}'")
    return r


@app.get("/api/tafsir")
def tafsir_sources():
    return queries.list_tafsir_sources()


@app.get("/api/tafsir/{source_id}/{ayah}")
def tafsir(source_id: str, ayah: int):
    t = queries.get_tafsir(source_id, ayah)
    if t is None:
        raise HTTPException(404, "no commentary for this ayah")
    return t


@app.get("/api/quiz")
def quiz_questions(level: str = "easy", seed: int | None = None, focus: str | None = None,
                   weak: str | None = None):
    """Multiple-choice quiz built from the database. level: easy | intermediate | hard.
    Adaptive selection (rule-based): focus = comma-separated roots to revise, weak = weakest skill."""
    if level not in quiz.LEVELS:
        raise HTTPException(404, f"unknown level '{level}'")
    if weak is not None and weak not in quiz.SKILLS:
        raise HTTPException(400, f"unknown skill '{weak}'")
    return quiz.build_quiz(level, seed, focus=(focus or "").split(",") if focus else None, weak=weak)


class FeedbackRequest(BaseModel):
    question: dict
    chosen: str


@app.post("/api/quiz/feedback")
def quiz_answer_feedback(req: FeedbackRequest):
    """Wrong answer -> Gemini explains chosen vs correct from database evidence; verified; template fallback."""
    try:
        return quiz_feedback(req.question, req.chosen, use_llm=True)
    except ValueError as e:
        raise HTTPException(400, str(e))


class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask(req: AskRequest):
    """RAG assistant: question -> resolve roots -> retrieve evidence -> answer (+ verify, later)."""
    return rag_answer(req.question, use_llm=True)
