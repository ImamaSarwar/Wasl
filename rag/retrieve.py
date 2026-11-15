"""
Step 3: concept search. Finds the ayahs whose *translation* is closest in meaning to a question,
for questions that name no root ("What does the surah say about birds?").

Two interchangeable retrievers, same interface:
  tfidf  - scikit-learn, character n-grams. Runs anywhere, instant. This is the BASELINE.
  minilm - sentence-transformers all-MiniLM-L6-v2 (CPU is fine, ~90 MB download on first use).

Choose with the environment variable WASL_RETRIEVER (default: tfidf).

Every retriever returns [(ayah_number, score)] best-first, scores in 0..1 (cosine similarity).
A score threshold decides "not enough evidence" - see THRESHOLDS and `python eval/run_eval.py --sweep`.
"""
import os

from backend import queries

# Minimum best-ayah score to answer instead of refusing. TUNE these with the eval sweep.
THRESHOLDS = {
    "tfidf": 0.18,   # lowest value that refuses every no_match dev question; only 6 dev questions, so weak evidence
    "minilm": 0.30,   # UNTUNED placeholder: run `WASL_RETRIEVER=minilm python eval/run_eval.py --sweep`
}
TOP_K = 3


def _ayah_texts():
    ayahs = queries.get_ayahs()
    return [a["ayah"] for a in ayahs], [a["translation"] for a in ayahs]


# Words that carry no topic: "What does the surah say about X?" -> "X". Used by the TF-IDF baseline only
# (MiniLM understands whole sentences).
_BOILERPLATE = {"surah", "sura", "ayah", "ayahs", "ayat", "verse", "verses", "quran", "mulk", "al",
                "mention", "mentions", "mentioned", "say", "says", "said", "talk", "talks", "describe",
                "describes", "tell", "show", "find", "word", "words", "use", "uses", "used", "root",
                "forms", "form", "there", "happens", "happen", "people", "speak", "about"}


def clean_query(q):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    import re
    toks = re.findall(r"[a-z]+", q.lower())
    kept = [t for t in toks if t not in ENGLISH_STOP_WORDS and t not in _BOILERPLATE]
    return " ".join(kept) or q


class TfidfRetriever:
    name = "tfidf"

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.ids, texts = _ayah_texts()
        # char n-grams inside word boundaries: "punish" still matches "punishment", "see" ~ "seeing"
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                                   lowercase=True, stop_words=None)
        self.matrix = self.vec.fit_transform(texts)

    def search(self, query, k=TOP_K):
        scores = (self.matrix @ self.vec.transform([clean_query(query)]).T).toarray().ravel()
        order = scores.argsort()[::-1][:k]
        return [(self.ids[i], float(scores[i])) for i in order]


class MiniLMRetriever:
    name = "minilm"
    MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self):
        from sentence_transformers import SentenceTransformer  # needs requirements-rag.txt
        self.ids, texts = _ayah_texts()
        self.model = SentenceTransformer(self.MODEL, device="cpu")
        self.matrix = self.model.encode(texts, normalize_embeddings=True)  # 30 x 384

    def search(self, query, k=TOP_K):
        q = self.model.encode([query], normalize_embeddings=True)[0]
        scores = self.matrix @ q
        order = scores.argsort()[::-1][:k]
        return [(self.ids[i], float(scores[i])) for i in order]


_cache = {}


def get_retriever(name=None):
    name = (name or os.environ.get("WASL_RETRIEVER", "tfidf")).lower()
    if name not in _cache:
        _cache[name] = {"tfidf": TfidfRetriever, "minilm": MiniLMRetriever}[name]()
    return _cache[name]


def threshold(name=None):
    return THRESHOLDS[(name or get_retriever().name)]
