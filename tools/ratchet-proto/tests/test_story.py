"""story.py on synthetic result files: a run built to match the Mac's numbers keeps every claim,
and a run built to break some breaks exactly those."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import story  # noqa: E402

SIZES = {"single-fact": 10, "paraphrase": 10, "identifier": 8, "relation": 8, "stale": 8}

# Hit@4 per stratum (single, paraphrase, identifier, relation, stale) and stale@4, shaped like the Mac run
MAC = {
    "EP3": ((5, 2, 1, 1, 0), 0), "A": ((5, 2, 1, 1, 0), 0), "B": ((6, 2, 2, 3, 3), 4), "C": ((8, 4, 4, 4, 5), 2),
    "S1": ((9, 2, 6, 7, 6), 3), "S2": ((9, 2, 8, 7, 6), 3), "S3": ((9, 2, 8, 7, 6), 1),
    "S4": ((9, 4, 8, 5, 8), 0), "S5": ((9, 4, 8, 5, 7), 2), "F1": ((9, 4, 5, 5, 8), 0),
    "X1": ((9, 2, 8, 8, 7), 0), "X2": ((9, 2, 8, 8, 8), 0), "H1": ((9, 4, 8, 6, 8), 0), "H2": ((9, 4, 8, 6, 8), 0),
}


def rows(cfg, hits, stale4, embedder, reranker, rerank_scores=True):
    out, qn = [], 0
    for (stratum, n), h in zip(SIZES.items(), hits):
        for i in range(n):
            qn += 1
            hit = i < h
            stale = [2] if (stratum == "stale" and i >= n - stale4) else ([None] if stratum == "stale" else [])
            top1 = (5.0 + i) if (cfg == "S5" and rerank_scores) else 0.5
            out.append({"config": cfg, "embedder": embedder, "reranker": reranker, "id": f"G-{qn:03d}",
                        "stratum": stratum, "expected": [f"x#{qn}"], "ranks": [1 if hit else None],
                        "partial_ranks": [1 if hit else None], "stale_ranks": stale, "pinned": 0,
                        "context_tokens_top4": 100, "top1_score": top1, "top10": [f"x#{qn}", "y"]})
    for j in range(6):
        out.append({"config": cfg, "embedder": embedder, "reranker": reranker, "id": f"G-U{j}",
                    "stratum": "unanswerable", "expected": [], "ranks": [], "partial_ranks": [], "stale_ranks": [],
                    "pinned": 0, "context_tokens_top4": 100, "top1_score": -5.0 if cfg == "S5" else 0.1,
                    "top10": ["z"]})
    return out


def write(path, table, embedder="llamacpp:nomic-embed-text-v1.5-f16", reranker="llamacpp:bge-reranker-v2-m3-fp16"):
    with open(path, "w", encoding="utf-8") as f:
        for cfg, (hits, stale4) in table.items():
            for r in rows(cfg, hits, stale4, embedder, reranker):
                f.write(json.dumps(r) + "\n")


def run_story(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        story.main(list(args))
    return buf.getvalue()


class Story(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.dir = Path(self.d.name)

    def statuses(self, path):
        r = story.Run(story.load(str(path)))
        return {key: story.status(fn(r)[0]) for key, _, fn, _ in story.CLAIMS}

    def test_a_mac_shaped_run_keeps_every_claim(self):
        p = self.dir / "5090-nomic.jsonl"
        write(p, MAC)
        st = self.statuses(p)
        self.assertEqual({"holds"}, set(st.values()), st)

    def test_a_stronger_embedder_that_fixes_relation_breaks_those_claims(self):
        t = dict(MAC)
        t["S4"] = ((9, 5, 8, 7, 8), 0)  # dense no longer costs relation
        t["H2"] = ((9, 4, 8, 8, 8), 0)
        t["S5"] = ((10, 5, 8, 7, 8), 0)  # and the reranker helps
        p = self.dir / "5090-qwen3.jsonl"
        write(p, t, embedder="llamacpp:qwen3-embedding-8b-q8_0")
        st = self.statuses(p)
        self.assertEqual("BREAKS", st["s4-relation"])
        self.assertEqual("BREAKS", st["h2-tradeoff"])
        self.assertEqual("BREAKS", st["rerank-fails"])
        self.assertEqual("n/a", st["anchor"])  # not nomic
        self.assertEqual("holds", st["units-dense"])

    def test_no_reranker_means_not_applicable(self):
        t = {k: v for k, v in MAC.items() if k != "S5"}
        p = self.dir / "none.jsonl"
        write(p, t, reranker=None)
        st = self.statuses(p)
        self.assertEqual("n/a", st["rerank-fails"])
        self.assertEqual("n/a", st["decline-gate"])

    def test_anchor_breaks_when_config_a_drifts(self):
        t = dict(MAC)
        t["A"] = ((6, 3, 2, 2, 1), 0)  # 14/44
        p = self.dir / "5090-nomic-drift.jsonl"
        write(p, t)
        self.assertEqual("BREAKS", self.statuses(p)["anchor"])

    def test_globs_and_side_by_side_table(self):
        write(self.dir / "5090-a.jsonl", MAC)
        write(self.dir / "5090-b.jsonl", MAC, embedder="llamacpp:qwen3-embedding-4b-q8_0")
        out = run_story(str(self.dir / "5090-*.jsonl"))
        self.assertIn("== 5090-a:", out)
        self.assertIn("== 5090-b:", out)
        self.assertIn("MAIN CONFIGURATIONS SIDE BY SIDE", out)
        s4 = next(l for l in out.splitlines() if l.strip().startswith("S4 "))
        self.assertEqual(2, s4.count("34 34 4 5 0"))
        md = run_story(str(self.dir / "5090-a.jsonl"), "--md")
        self.assertIn("| S4 | 34 · 34 · 4 · 5 · 0 |", md)

    def test_held_out_rows_are_refused(self):
        p = self.dir / "bad.jsonl"
        r = rows("S1", (1, 1, 1, 1, 1), 0, None, None)[0]
        r["id"] = "H-001"
        p.write_text(json.dumps(r) + "\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            story.load(str(p))


if __name__ == "__main__":
    unittest.main()
