"""
Tests for the word-by-word meanings pipeline, using a fake API response (no network).
    python -m unittest discover -s tests -v
"""
import csv
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_wbw  # noqa: E402


def db_words():
    db = sqlite3.connect(ROOT / "data" / "quran.db")
    try:
        return {(a, p): ar for a, p, ar in db.execute("SELECT ayah, pos, arabic FROM words")}
    finally:
        db.close()


def fake_payload(words, break_ayah=None, drop_ayah=None, bad_word=None):
    """A payload shaped like the Quran.com API, built from our own words."""
    verses = []
    for ayah in range(1, 31):
        if ayah == drop_ayah:
            continue
        ws = [{"position": p, "char_type_name": "word", "text_imlaei": ar,
               "translation": {"text": f"<i>meaning</i> {ayah}.{p}"}}
              for (a, p), ar in sorted(words.items()) if a == ayah]
        if ayah == break_ayah:
            ws = ws[:-1]
        if bad_word and bad_word[0] == ayah:
            ws[bad_word[1] - 1]["text_imlaei"] = "خطأ"
        ws.append({"position": len(ws) + 1, "char_type_name": "end", "text": "end", "translation": {"text": "(30)"}})
        verses.append({"verse_key": f"67:{ayah}", "words": ws})
    return {"verses": verses}


class TestFetchWbw(unittest.TestCase):
    def test_clean_strips_html(self):
        self.assertEqual(fetch_wbw.clean("  <i>He</i>   created "), "He created")

    def test_clean_payload_gives_one_gloss_per_word(self):
        w = db_words()
        rows, fatal, warnings = fetch_wbw.convert(fake_payload(w), w)
        self.assertEqual((fatal, warnings), ([], []))
        self.assertEqual(len(rows), 333)
        self.assertIn((2, 2, "meaning 2.2"), rows)  # html removed

    def test_word_count_mismatch_is_fatal(self):
        w = db_words()
        _, fatal, _ = fetch_wbw.convert(fake_payload(w, break_ayah=5), w)
        self.assertTrue(any("ayah 5" in f for f in fatal))

    def test_missing_ayah_is_fatal(self):
        w = db_words()
        _, fatal, _ = fetch_wbw.convert(fake_payload(w, drop_ayah=9), w)
        self.assertTrue(any("missing" in f and "9" in f for f in fatal))

    def test_different_arabic_is_a_warning(self):
        w = db_words()
        _, fatal, warnings = fetch_wbw.convert(fake_payload(w, bad_word=(3, 2)), w)
        self.assertEqual(fatal, [])
        self.assertTrue(any(x.startswith("3:2 Arabic differs") for x in warnings))


class TestGlossLoading(unittest.TestCase):
    def test_build_db_loads_glosses_csv(self):
        """Builds a scratch DB with a tiny glosses file and checks it lands on the right word."""
        import importlib
        import tempfile
        bd = importlib.import_module("build_db")
        tmp = Path(tempfile.mkdtemp())
        csv_path = tmp / "glosses.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ayah", "pos", "gloss", "source"])
            w.writerow([2, 2, "He created", "test"])
        old = bd.GLOSSES
        bd.GLOSSES = csv_path
        try:
            db = sqlite3.connect(":memory:")
            self.addCleanup(db.close)
            db.executescript(bd.SCHEMA)
            db.execute("INSERT INTO ayahs VALUES (2,'x','y')")
            db.execute("INSERT INTO words(ayah,pos,arabic) VALUES (2,2,'خَلَقَ')")
            self.assertEqual(bd.apply_glosses(db), 1)
            self.assertEqual(db.execute("SELECT gloss FROM words WHERE ayah=2 AND pos=2").fetchone()[0], "He created")
            with open(csv_path, "a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow([2, 99, "nope", "test"])
            with self.assertRaises(SystemExit):
                bd.apply_glosses(db)
        finally:
            bd.GLOSSES = old


if __name__ == "__main__":
    unittest.main()
