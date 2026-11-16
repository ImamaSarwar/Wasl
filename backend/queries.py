"""
All database logic lives here as plain functions (no FastAPI imports), so it can be tested
without a web server. backend/main.py only wraps these in HTTP endpoints.
"""
import json
import os
import sqlite3
from pathlib import Path

from .grammar import describe

DB_PATH = Path(os.environ.get("WASL_DB", Path(__file__).resolve().parent.parent / "data" / "quran.db"))


def _rows(sql, args=()):
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(sql, args)]
    finally:
        db.close()


def _decorate(w):
    """Add the plain-English description and (for verbs) the past/present forms to a word row.
    Raw columns (pos_tag, grammar, ...) are left untouched; the RAG code relies on them."""
    w["plain"] = describe(w["pos_tag"], w["grammar"])
    if w["pos_tag"] == "V" and w["root"]:
        w["tenses"] = {
            "past": {"form": w["past_form"], "ref": w["past_ref"]},
            "present": {"form": w["present_form"], "ref": w["present_ref"]},
        }
    else:
        w["tenses"] = None
    for k in ("past_form", "past_ref", "present_form", "present_ref"):
        w.pop(k, None)
    return w


def get_ayahs():
    """Whole surah: each ayah with its words nested (used by the reader and hover)."""
    ayahs = _rows("SELECT ayah, arabic, translation, transliteration FROM ayahs ORDER BY ayah")
    words = [_decorate(w) for w in _rows(
        "SELECT word_id, ayah, pos, arabic, trail, root, lemma, pos_tag, grammar, gloss, "
        "past_form, past_ref, present_form, present_ref FROM words ORDER BY ayah, pos")]
    by_ayah = {}
    for w in words:
        by_ayah.setdefault(w["ayah"], []).append(w)
    for a in ayahs:
        a["words"] = by_ayah.get(a["ayah"], [])
    return ayahs


def get_word(word_id):
    rows = _rows("SELECT w.*, a.translation FROM words w JOIN ayahs a USING(ayah) WHERE word_id=?", (word_id,))
    return _decorate(rows[0]) if rows else None


def list_roots():
    return _rows("SELECT root, COUNT(*) AS count, COUNT(DISTINCT lemma) AS forms "
                 "FROM words WHERE root IS NOT NULL GROUP BY root ORDER BY count DESC, root")


def root_tree(root):
    """Root family tree: one branch per lemma, with count and the ayahs it occurs in."""
    forms = _rows(
        "SELECT lemma, GROUP_CONCAT(DISTINCT grammar) AS grammar, COUNT(*) AS count, "
        "GROUP_CONCAT(DISTINCT ayah) AS ayahs FROM words WHERE root=? "
        "GROUP BY lemma ORDER BY count DESC, lemma", (root,))
    for f in forms:
        f["ayahs"] = sorted(int(x) for x in f["ayahs"].split(","))
    return {"root": root, "total": sum(f["count"] for f in forms), "forms": forms}


def form_ayahs(root, lemma):
    """Verse drill-down: every ayah containing this root+lemma, with the matching word ids."""
    return _rows(
        "SELECT a.ayah, a.arabic, a.translation, "
        "GROUP_CONCAT(w.word_id) AS word_ids "
        "FROM words w JOIN ayahs a USING(ayah) WHERE w.root=? AND w.lemma=? "
        "GROUP BY a.ayah ORDER BY a.ayah", (root, lemma))


def distribution(root):
    """Occurrences of a root in each of the 30 ayahs (zeros included)."""
    counts = {r["ayah"]: r["n"] for r in _rows(
        "SELECT ayah, COUNT(*) AS n FROM words WHERE root=? GROUP BY ayah", (root,))}
    return [{"ayah": a, "count": counts.get(a, 0)} for a in range(1, 31)]


def cross(root=None, min_ayahs=2):
    """Roots that appear together in the same ayahs. If `root` is given, only pairs with it."""
    pair_sql = (
        "SELECT a.root AS root_a, b.root AS root_b, COUNT(DISTINCT a.ayah) AS ayah_count, "
        "GROUP_CONCAT(DISTINCT a.ayah) AS ayahs FROM words a JOIN words b "
        "ON a.ayah=b.ayah AND a.root<b.root WHERE a.root IS NOT NULL AND b.root IS NOT NULL ")
    args = []
    if root:
        pair_sql += "AND (a.root=? OR b.root=?) "
        args += [root, root]
    pair_sql += "GROUP BY a.root, b.root HAVING ayah_count>=? ORDER BY ayah_count DESC, root_a, root_b"
    args.append(min_ayahs)
    rows = _rows(pair_sql, args)
    for r in rows:
        r["ayahs"] = sorted(int(x) for x in r["ayahs"].split(","))
    return rows


def root_words(root):
    """Every occurrence of a root, with its ayah's text and translation (used by the RAG evidence builder)."""
    return _rows(
        "SELECT w.word_id, w.ayah, w.pos, w.arabic AS word_arabic, w.lemma, w.pos_tag, w.grammar, "
        "a.arabic AS ayah_arabic, a.translation FROM words w JOIN ayahs a USING(ayah) "
        "WHERE w.root=? ORDER BY w.ayah, w.pos", (root,))


# ---------- recitations ----------------------------------------------------------------------------

def list_reciters():
    """Reciters in display order. The first one is the default in the app."""
    return _rows("SELECT reciter_id AS id, name FROM reciters ORDER BY sort_order")


def get_recitations(reciter_id):
    """Everything the player needs for one reciter: {ayah: {url, start_ms, end_ms, segments}}.
    start_ms/end_ms are set for whole-surah MP3s (where in the file this ayah is), else None.
    segments = [[word_number, start_ms, end_ms], ...] on the MP3's own clock, or None if unusable.
    Returns None for an unknown reciter."""
    if not _rows("SELECT 1 FROM reciters WHERE reciter_id=?", (reciter_id,)):
        return None
    out = {}
    for r in _rows("SELECT ayah, url, start_ms, end_ms, segments FROM recitations WHERE reciter_id=? ORDER BY ayah",
                   (reciter_id,)):
        out[r["ayah"]] = {"url": r["url"], "start_ms": r["start_ms"], "end_ms": r["end_ms"],
                          "segments": json.loads(r["segments"]) if r["segments"] else None}
    return out


# ---------- tafsir ----------------------------------------------------------------------------------

def list_tafsir_sources():
    return _rows("SELECT source_id AS id, name FROM tafsir_sources ORDER BY sort_order")


def get_tafsir(source_id, ayah):
    """The commentary that covers this ayah. Commentary is grouped, so group_start..group_end
    says which ayahs the text is about. `html` is already sanitized. None if there is none."""
    rows = _rows(
        "SELECT t.source_id, s.name AS source, t.group_start, t.group_end, t.html "
        "FROM tafsir t JOIN tafsir_sources s USING(source_id) "
        "WHERE t.source_id=? AND t.group_start<=? AND t.group_end>=?", (source_id, ayah, ayah))
    return {**rows[0], "ayah": ayah} if rows else None
