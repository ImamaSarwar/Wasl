"""
Tests for the recitation and tafsir data (import + query layer) and the tafsir HTML sanitizer.
    python -m unittest discover -s tests -v
(Rebuild the DB first: python scripts/build_db.py)
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from backend import queries  # noqa: E402
import import_audio  # noqa: E402
import import_tafsir  # noqa: E402


class TestReciters(unittest.TestCase):
    def test_reciters_present(self):
        names = [r["name"] for r in queries.list_reciters()]
        self.assertGreaterEqual(len(names), 1)

    def test_every_reciter_covers_all_30_ayahs_with_https_links(self):
        for r in queries.list_reciters():
            recs = queries.get_recitations(r["id"])
            self.assertEqual(sorted(recs), list(range(1, 31)), r["name"])
            for e in recs.values():
                self.assertTrue(e["url"].startswith("https://"))
                self.assertTrue(e["url"].endswith(".mp3"))

    def test_unknown_reciter(self):
        self.assertIsNone(queries.get_recitations("nobody"))

    def test_per_ayah_files_point_at_the_right_ayah(self):
        # Regression: the Afasy file numbers ayahs globally (67:1 is stored as 5242); we read the MP3 name instead.
        ids = {r["id"] for r in queries.list_reciters()}
        if "afasy" in ids:
            recs = queries.get_recitations("afasy")
            self.assertTrue(recs[1]["url"].endswith("067001.mp3"))
            self.assertTrue(recs[30]["url"].endswith("067030.mp3"))

    def test_surah_file_reciter_has_ordered_time_ranges(self):
        for r in queries.list_reciters():
            recs = queries.get_recitations(r["id"])
            if recs[1]["start_ms"] is None:
                continue
            for a in range(1, 31):
                self.assertLess(recs[a]["start_ms"], recs[a]["end_ms"])
                if a < 30:
                    self.assertLessEqual(recs[a]["end_ms"], recs[a + 1]["start_ms"] + 1)
                self.assertEqual(recs[a]["url"], recs[1]["url"])

    def test_word_timings_use_our_word_numbers(self):
        n_words = {a["ayah"]: len(a["words"]) for a in queries.get_ayahs()}
        for r in queries.list_reciters():
            for a, e in queries.get_recitations(r["id"]).items():
                if e["segments"]:
                    self.assertEqual({s[0] for s in e["segments"]}, set(range(1, n_words[a] + 1)), (r["id"], a))
                    for _w, start, end in e["segments"]:
                        self.assertLessEqual(start, end)


class TestSegmentHelpers(unittest.TestCase):
    def test_normalize_handles_all_layouts(self):
        self.assertEqual(import_audio.normalize_segments([["1", "380", "730"]]), [[1, 380, 730]])
        self.assertEqual(import_audio.normalize_segments([[1, 0, 500]]), [[1, 0, 500]])
        self.assertEqual(import_audio.normalize_segments([[0, 1, 0, 560]]), [[1, 0, 560]])  # 4-number layout

    def test_check_segments(self):
        ok = [[1, 0, 10], [2, 10, 20]]
        self.assertEqual(import_audio.check_segments(ok, 2), ok)
        self.assertEqual(import_audio.check_segments(ok + [[1, 20, 30]], 2), ok + [[1, 20, 30]])  # repeated word is fine
        self.assertIsNone(import_audio.check_segments(ok, 3))        # a word has no timing
        self.assertIsNone(import_audio.check_segments(ok + [[9, 20, 30]], 2))  # word number out of range
        self.assertIsNone(import_audio.check_segments([[1, 30, 20]], 1))       # end before start
        self.assertIsNone(import_audio.check_segments(None, 2))

    def test_only_plain_https_links_accepted(self):
        for bad in ("http://x/y.mp3", "javascript:alert(1)", "https://x/a b.mp3", None):
            with self.assertRaises(ValueError):
                import_audio._https(bad)


class TestTafsir(unittest.TestCase):
    def test_every_ayah_has_commentary_and_groups_are_consistent(self):
        sources = queries.list_tafsir_sources()
        self.assertGreaterEqual(len(sources), 1)
        for s in sources:
            for a in range(1, 31):
                t = queries.get_tafsir(s["id"], a)
                self.assertIsNotNone(t, f"{s['id']} ayah {a}")
                self.assertLessEqual(t["group_start"], a)
                self.assertGreaterEqual(t["group_end"], a)
                self.assertGreater(len(t["html"]), 100)

    def test_known_grouping(self):
        t3 = queries.get_tafsir("en-tafsir-ibn-kathir", 3)
        self.assertEqual((t3["group_start"], t3["group_end"]), (1, 5))
        self.assertEqual(t3["html"], queries.get_tafsir("en-tafsir-ibn-kathir", 1)["html"])

    def test_stored_html_has_no_unsafe_parts(self):
        for a in range(1, 31):
            h = queries.get_tafsir("en-tafsir-ibn-kathir", a)["html"].lower()
            for bad in ("<script", "<style", "<iframe", "<img", "<a ", "href=", "javascript:", " onclick", " onerror"):
                self.assertNotIn(bad, h)


class TestSanitizer(unittest.TestCase):
    def test_removes_scripts_and_handlers_and_links(self):
        dirty = ('<p class="en" onclick="x()">Hi <script>alert(1)</script><a href="javascript:x">link</a>'
                 '<img src=x onerror=y><style>p{}</style><b>bold</b></p>')
        clean = import_tafsir.sanitize(dirty)
        self.assertEqual(clean, '<p class="en">Hi link<b>bold</b></p>')

    def test_keeps_class_and_lang_only(self):
        self.assertEqual(import_tafsir.sanitize('<span class="ar qpc-hafs" lang="ar" style="x:y">a</span>'),
                         '<span class="ar qpc-hafs" lang="ar">a</span>')

    def test_rejects_odd_class_values_and_closes_tags(self):
        self.assertEqual(import_tafsir.sanitize('<span class="a&quot;b">x'), "<span>x</span>")
        self.assertEqual(import_tafsir.sanitize("<p><b>unclosed"), "<p><b>unclosed</b></p>")

    def test_text_is_escaped(self):
        self.assertEqual(import_tafsir.sanitize("<p>1 < 2 &amp; 3</p>"), "<p>1 &lt; 2 &amp; 3</p>")


if __name__ == "__main__":
    unittest.main()
