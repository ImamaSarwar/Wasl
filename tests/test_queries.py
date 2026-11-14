"""
Sanity checks for the database and query layer. Needs no extra packages:
    python -m unittest discover -s tests -v
(Build the DB first: python scripts/build_db.py)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import queries  # noqa: E402


class TestData(unittest.TestCase):
    def test_counts(self):
        ayahs = queries.get_ayahs()
        self.assertEqual(len(ayahs), 30)
        self.assertEqual(sum(len(a["words"]) for a in ayahs), 333)

    def test_bismillah_stripped(self):
        first = queries.get_ayahs()[0]["words"][0]
        self.assertEqual(first["root"], "برك")  # tabaraka, not bismillah

    def test_khalaqa_family(self):
        t = queries.root_tree("خلق")
        self.assertEqual(t["total"], 4)
        self.assertEqual({f["count"] for f in t["forms"]}, {3, 1})
        self.assertEqual(sorted({a for f in t["forms"] for a in f["ayahs"]}), [2, 3, 14])

    def test_distribution_has_30_ayahs(self):
        d = queries.distribution("خلق")
        self.assertEqual(len(d), 30)
        self.assertEqual(sum(x["count"] for x in d), 4)

    def test_drilldown(self):
        rows = queries.form_ayahs("خلق", "خَلَقَ")
        self.assertEqual([r["ayah"] for r in rows], [2, 3, 14])

    def test_cross(self):
        pairs = queries.cross(min_ayahs=2)
        self.assertTrue(len(pairs) > 0)
        self.assertTrue(all(p["ayah_count"] >= 2 for p in pairs))

    def test_stop_signs_kept_in_display_text(self):
        a3 = next(a for a in queries.get_ayahs() if a["ayah"] == 3)
        self.assertIn("ۖ", a3["arabic"])


if __name__ == "__main__":
    unittest.main()
