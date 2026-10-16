"""The scorer: the Episode 3 chunk rule (mirrors GoldenScorerTest.java), the unit rule, the
metrics and the ratchet verdict."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

from ratchet import html as H  # noqa: E402
from ratchet import score as S  # noqa: E402
from ratchet.corpus import Item  # noqa: E402

ROOT = REPO / "src/test/resources/fixtures"
FILE = "specs/001-demo/spec.html"


def chunk(source, text, n=0):
    return Item(n, source, "", "001-demo", "current", "", "", "", text, chunk=1)


def unit(source, anchor, n=0, lifecycle="current"):
    return Item(n, source, anchor, "001-demo", lifecycle, "", "", "", "text")


class ChunkRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = H.parse((ROOT / FILE).read_text(encoding="utf-8"))
        cls.page = H.jsoup_text(H.find_tag(tree, "body"))
        texts = {}
        for ident in ("FR-001", "FR-002"):
            el = tree.find(lambda e: e.id == ident)
            texts[f"{FILE}#{ident}"] = S.normalise(H.jsoup_text(el))
        cls.texts = texts
        cls.scorer = S.ChunkScorer({FILE: cls.page}, texts)

    def test_whole_element_is_a_hit(self):
        self.assertEqual(S.FULL, self.scorer.hit(FILE + "#FR-001", chunk(FILE, self.page)))

    def test_half_or_more_is_a_partial_hit(self):
        el = self.texts[FILE + "#FR-001"]
        start = self.page.index(el)
        cut = self.page[start + len(el) // 3:]
        self.assertEqual(S.PARTIAL, self.scorer.hit(FILE + "#FR-001", chunk(FILE, cut)))

    def test_less_than_half_is_a_miss(self):
        el = self.texts[FILE + "#FR-001"]
        start = self.page.index(el)
        cut = self.page[: start + len(el) // 4]
        self.assertEqual(S.NONE, self.scorer.hit(FILE + "#FR-001", chunk(FILE, cut)))

    def test_another_file_is_a_miss_whatever_it_says(self):
        self.assertEqual(S.NONE, self.scorer.hit(FILE + "#FR-001", chunk("specs/002-other/spec.html", self.page)))

    def test_ranks_count_from_one_and_a_full_hit_is_also_partial(self):
        q = {"id": "Q", "stratum": "single-fact", "expected": [FILE + "#FR-002"], "stale": []}
        items = [chunk("specs/002-other/spec.html", "unrelated"), chunk(FILE, self.page, 1)]
        r = S.rank_list(items, q, self.scorer.hit, lambda it: 1)
        self.assertEqual(2, r.first)
        self.assertEqual(2, r.first_partial)
        self.assertAlmostEqual(0.5, r.rr())
        self.assertTrue(r.hit_at(4))
        self.assertFalse(r.hit_at(1))

    def test_a_miss_scores_zero(self):
        q = {"id": "Q", "stratum": "single-fact", "expected": [FILE + "#FR-001"], "stale": []}
        r = S.rank_list([chunk(FILE, "nothing relevant")], q, self.scorer.hit, lambda it: 1)
        self.assertIsNone(r.first)
        self.assertEqual(0, r.rr())


class UnitRule(unittest.TestCase):
    def test_a_unit_hits_only_its_own_address(self):
        self.assertEqual(S.FULL, S.unit_hit(FILE + "#FR-001", unit(FILE, "FR-001")))
        self.assertEqual(S.NONE, S.unit_hit(FILE + "#FR-001", unit(FILE, "FR-002")))
        self.assertEqual(S.NONE, S.unit_hit(FILE + "#FR-001", unit("specs/002-x/spec.html", "FR-001")))
        self.assertEqual(S.NONE, S.unit_hit(FILE + "#requirements", unit(FILE, "FR-001")))  # a child is not its parent

    def test_any_part_of_a_unit_counts(self):
        a, b = unit(FILE, "FR-001", 0), unit(FILE, "FR-001", 1)
        b.part, b.parts, a.parts = 2, 2, 2
        q = {"id": "Q", "stratum": "single-fact", "expected": [FILE + "#FR-001"], "stale": []}
        r = S.rank_list([unit(FILE, "X", 5), b, a], q, S.unit_hit, lambda it: 1)
        self.assertEqual(2, r.first)

    def test_all_evidence_needs_every_expected_element(self):
        q = {"id": "Q", "stratum": "relation", "expected": [FILE + "#FR-001", FILE + "#FR-002"], "stale": []}
        items = [unit(FILE, "FR-001", 0)] + [unit(FILE, f"X{i}", i + 1) for i in range(4)] + [unit(FILE, "FR-002", 9)]
        r = S.rank_list(items, q, S.unit_hit, lambda it: 1)
        self.assertTrue(r.hit_at(4))
        self.assertFalse(r.all_at(4))
        self.assertTrue(r.all_at(10))

    def test_stale_in_top_four(self):
        q = {"id": "Q", "stratum": "stale", "expected": [FILE + "#FR-002"], "stale": [FILE + "#FR-001"]}
        items = [unit(FILE, "FR-002", 0)] + [unit(FILE, f"X{i}", i + 1) for i in range(3)] + [unit(FILE, "FR-001", 9)]
        self.assertFalse(S.rank_list(items, q, S.unit_hit, lambda it: 1).stale_at(4))
        self.assertTrue(S.rank_list(items[:1] + items[4:], q, S.unit_hit, lambda it: 1).stale_at(4))


def results(hits: dict, stale=()):
    """hits: qid -> (stratum, first rank or None)."""
    out = []
    for qid, (stratum, first) in hits.items():
        out.append(S.QResult(qid, stratum, ["a"], [first], [first], [1] if qid in stale else [], [], 0, None))
    return out


class Ratchet(unittest.TestCase):
    base = {"q1": ("single-fact", 1), "q2": ("single-fact", 2), "q3": ("relation", 1), "q4": ("relation", 3),
            "q5": ("stale", 1), "q6": ("paraphrase", None)}

    def test_equal_passes(self):
        ok, why = S.ratchet(results(self.base), results(self.base))
        self.assertTrue(ok, why)

    def test_overall_drop_fails(self):
        cur = dict(self.base, q1=("single-fact", 9))
        ok, why = S.ratchet(results(self.base), results(cur))
        self.assertFalse(ok)
        self.assertIn("Hit@4", why[0])

    def test_a_stratum_may_lose_one_if_another_gains(self):
        cur = dict(self.base, q3=("relation", 7), q6=("paraphrase", 1))
        ok, why = S.ratchet(results(self.base), results(cur))
        self.assertTrue(ok, why)

    def test_a_stratum_losing_two_fails_even_if_overall_rises(self):
        cur = dict(self.base, q3=("relation", 7), q4=("relation", None), q6=("paraphrase", 1),
                   q7=("paraphrase", 1), q8=("paraphrase", 2))
        prev = dict(self.base, q7=("paraphrase", None), q8=("paraphrase", None))
        ok, why = S.ratchet(results(prev), results(cur))
        self.assertFalse(ok)
        self.assertTrue(any(w.startswith("relation") for w in why), why)

    def test_more_stale_fails(self):
        ok, why = S.ratchet(results(self.base), results(self.base, stale={"q5"}))
        self.assertFalse(ok)
        self.assertIn("stale@4", why[0])

    def test_unanswerable_questions_are_not_counted(self):
        r = results(self.base) + [S.QResult("u", "unanswerable", [], [], [], [], [], 0, None)]
        tot, _ = S.aggregate(r)
        self.assertEqual(6, tot.n)


if __name__ == "__main__":
    unittest.main()
