"""
All database logic lives here as plain functions (no FastAPI imports), so it can be tested
without a web server. backend/main.py only wraps these in HTTP endpoints.
"""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("WASL_DB", Path(__file__).resolve().parent.parent / "data" / "quran.db"))


def _rows(sql, args=()):
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(sql, args)]
    finally:
        db.close()


def get_ayahs():
    """Whole surah: each ayah with its words nested (used by the reader and hover)."""
    ayahs = _rows("SELECT ayah, arabic, translation FROM ayahs ORDER BY ayah")
    words = _rows("SELECT word_id, ayah, pos, arabic, trail, root, lemma, pos_tag, grammar, gloss "
                  "FROM words ORDER BY ayah, pos")
    by_ayah = {}
    for w in words:
        by_ayah.setdefault(w["ayah"], []).append(w)
    for a in ayahs:
        a["words"] = by_ayah.get(a["ayah"], [])
    return ayahs


def get_word(word_id):
    rows = _rows("SELECT w.*, a.translation FROM words w JOIN ayahs a USING(ayah) WHERE word_id=?", (word_id,))
    return rows[0] if rows else None


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
