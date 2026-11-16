"""
Reads the reciter files in data/raw/recitations/ and fills the `reciters` and `recitations` tables.
Called by build_db.py. Drop another reciter file into that folder and re-run build_db.py to add one.

IMPORTANT: these files contain LINKS to MP3 files on a CDN, not audio. The browser streams the audio
directly from those links, so the app needs an internet connection to play recitations.

Three layouts are understood (detected automatically):
  1. .json, one entry per ayah         {"67:1": {"audio_url": ..., "segments": [[word, start_ms, end_ms], ...]}}
  2. .db with a `verses` table         one MP3 per ayah (its ayah_number column is a GLOBAL counter across the
                                       whole Qur'an, so the real ayah is read from the MP3 name, e.g. 067003.mp3)
  3. .db with `surah_list`+`segments`  ONE MP3 for the whole surah; each ayah is a start/end time inside it

Every reciter ends up as the same shape per ayah: url, start_ms, end_ms (both NULL for per-ayah MP3s) and
word timings [[word_number, start_ms, end_ms], ...] measured on that MP3's own clock.
"""
import json
import re
import sqlite3
from pathlib import Path

URL_AYAH = re.compile(r"/(\d{3})(\d{3})\.mp3$")


# ---------- helpers -------------------------------------------------------------------------

def humanize(stem):
    """'ayah-recitation-alnufais' -> 'Alnufais' (only used when reciters.json has no name for the file)."""
    s = re.sub(r"^(ayah|surah)-recitation-", "", stem)
    s = re.sub(r"-\d+$", "", s)
    return " ".join(p.capitalize() for p in s.split("-"))


def normalize_segments(raw):
    """Word timings come as [word, start, end] (strings or ints) or [index, word, start, end].
    Always return [[word, start, end], ...] as ints, using the LAST three numbers."""
    out = []
    for seg in raw or []:
        nums = [int(float(x)) for x in seg]
        out.append(nums[-3:])
    return out


def check_segments(segs, n_words):
    """Word timings are only used for word-by-word highlighting, so they must line up with our words.
    Valid = every word number 1..n_words appears and none is outside that range (a reciter may repeat a
    word, which gives extra entries; that is fine). Returns the segments, or None if unusable."""
    if not segs:
        return None
    nums = [s[0] for s in segs]
    if min(nums) < 1 or max(nums) > n_words or set(nums) != set(range(1, n_words + 1)):
        return None
    if any(e < s for _w, s, e in segs):
        return None
    return segs


def _https(url):
    if not isinstance(url, str) or not url.startswith("https://") or any(c.isspace() for c in url):
        raise ValueError(f"not a plain https URL: {url!r}")
    return url


# ---------- the three readers -----------------------------------------------------------------

def read_ayah_json(path, surah):
    data = json.load(open(path, encoding="utf-8"))
    out = {}
    for key, e in data.items():
        s, a = key.split(":")
        if int(s) == surah:
            out[int(a)] = dict(url=_https(e["audio_url"]), start_ms=None, end_ms=None,
                               segments=normalize_segments(e.get("segments")))
    return out


def read_verses_db(path, surah):
    db = sqlite3.connect(path)
    try:
        out = {}
        for url, segs in db.execute("SELECT audio_url, segments FROM verses"):
            m = URL_AYAH.search(url or "")
            if m and int(m[1]) == surah:
                out[int(m[2])] = dict(url=_https(url), start_ms=None, end_ms=None,
                                      segments=normalize_segments(json.loads(segs or "[]")))
        return out
    finally:
        db.close()


def read_surah_db(path, surah):
    db = sqlite3.connect(path)
    try:
        row = db.execute("SELECT audio_url FROM surah_list WHERE surah_number=?", (surah,)).fetchone()
        if not row:
            return {}
        url = _https(row[0])
        out = {}
        for a, t0, t1, segs in db.execute(
                "SELECT ayah_number, timestamp_from, timestamp_to, segments FROM segments WHERE surah_number=?",
                (surah,)):
            out[int(a)] = dict(url=url, start_ms=int(t0), end_ms=int(t1),
                               segments=normalize_segments(json.loads(segs or "[]")))
        return out
    finally:
        db.close()


def read_reciter_file(path, surah):
    """-> (kind, {ayah: entry}). Raises ValueError for a layout it does not recognise."""
    path = Path(path)
    if path.suffix == ".json":
        return "ayah-json", read_ayah_json(path, surah)
    if path.suffix == ".db":
        db = sqlite3.connect(path)
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            db.close()
        if "verses" in tables:
            return "ayah-db", read_verses_db(path, surah)
        if {"surah_list", "segments"} <= tables:
            return "surah-db", read_surah_db(path, surah)
    raise ValueError(f"{path.name}: unrecognised recitation file layout")


# ---------- the import ---------------------------------------------------------------------------

def load_config(config_path):
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {"reciters": []}


def import_all(db, raw_dir, config_path, surah, word_counts):
    """word_counts: {ayah: number of words}. Returns the list of imported reciter ids."""
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        print(f"  recitations: skipped ({raw_dir} not found)")
        return []

    config = load_config(config_path)
    by_file = {r["file"]: r for r in config.get("reciters", [])}
    order = {r["file"]: i for i, r in enumerate(config.get("reciters", []))}
    files = sorted((p for p in raw_dir.iterdir() if p.suffix in (".json", ".db")),
                   key=lambda p: (order.get(p.name, 10_000), p.name))

    imported = []
    for sort_order, path in enumerate(files):
        meta = by_file.get(path.name, {})
        rid = meta.get("id") or re.sub(r"[^a-z0-9]+", "-", humanize(path.stem).lower()).strip("-")
        name = meta.get("name") or humanize(path.stem)
        try:
            kind, entries = read_reciter_file(path, surah)
        except Exception as e:  # a bad file must not stop the whole build
            print(f"  recitations: SKIPPED {path.name}: {e}")
            continue
        missing = [a for a in range(1, len(word_counts) + 1) if a not in entries]
        if missing:
            print(f"  recitations: SKIPPED {name}: no audio for ayahs {missing}")
            continue

        db.execute("INSERT INTO reciters VALUES (?,?,?,?,?)", (rid, name, kind, sort_order, path.name))
        unaligned = []
        for a in range(1, len(word_counts) + 1):
            e = entries[a]
            segs = check_segments(e["segments"], word_counts[a])
            if segs is None:
                unaligned.append(a)
            db.execute("INSERT INTO recitations VALUES (?,?,?,?,?,?)",
                       (rid, a, e["url"], e["start_ms"], e["end_ms"],
                        json.dumps(segs) if segs else None))
        imported.append(rid)
        note = f", word timings unusable for ayahs {unaligned}" if unaligned else ""
        print(f"  recitations: {name} ({kind}): 30/30 ayahs{note}")
    return imported
