"""
Wasl API. Run from the repo root:
    uvicorn backend.main:app --reload
Interactive docs: http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import queries
from rag.pipeline import answer as rag_answer

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


class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask(req: AskRequest):
    """RAG assistant: question -> resolve roots -> retrieve evidence -> answer (+ verify, later)."""
    return rag_answer(req.question)
