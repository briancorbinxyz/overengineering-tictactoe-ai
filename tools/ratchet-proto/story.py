#!/usr/bin/env python3
"""Does the story hold? Reads any number of run.py result files (JSONL) and checks, for each run,
the claims the Mac runs (nomic-embed-text + MiniLM) established, then prints the main configurations
side by side.

    python story.py results/5090-*.jsonl                       # globs are expanded here (PowerShell doesn't)
    python story.py results/5090-*.jsonl ~/mac/mac-nomic-embed-text.jsonl --md > story.md

Each file is one run (one embedder and one reranker). A claim is printed as **holds**, **BREAKS**,
or n/a when the run lacks a configuration it needs (no reranker: no S5). The Mac's numbers are shown
next to each claim for reference; they are in the conversation and README, not in this repository
(the Mac's result files live on the Mac).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ratchet import score as S  # noqa: E402

TABLE = ["A", "B", "C", "S1", "S2", "S3", "S4", "S5", "X1", "X2", "H1", "H2", "E5-1", "E5-2", "F1"]


def expand(paths: list) -> list:
    out = []
    for p in paths:
        hits = sorted(glob.glob(str(Path(p).expanduser()))) if any(c in p for c in "*?[") else [str(Path(p).expanduser())]
        if not hits:
            print(f"warning: nothing matches {p}", file=sys.stderr)
        out += hits
    return list(dict.fromkeys(out))


def load(path: str) -> dict:
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        raise SystemExit(f"{path}: empty")
    by = {}
    for r in rows:
        if str(r.get("id", "")).startswith("H-"):  # held-out ids are H-001...; they are scored once, in Java
            raise SystemExit(f"{path}: contains held-out question {r['id']}; refusing")
        by.setdefault(r["config"], []).append(S.QResult(
            r["id"], r["stratum"], r["expected"], r["ranks"], r.get("partial_ranks") or r["ranks"],
            r.get("stale_ranks") or [], r.get("top10") or [], r.get("context_tokens_top4") or 0,
            r.get("top1_score"), r.get("pinned") or 0))
    first = next((r for r in rows if r["config"] != "EP3"), rows[0])
    return {"name": Path(path).stem, "path": path, "embedder": first.get("embedder"),
            "reranker": first.get("reranker"), "res": by}


class Run:
    def __init__(self, d):
        self.__dict__.update(d)
        self.agg = {k: S.aggregate(v) for k, v in self.res.items()}

    def has(self, *keys):
        return all(k in self.res for k in keys)

    def h4(self, k, stratum=None):
        tot, by = self.agg[k]
        return (by[stratum] if stratum else tot).h4

    def tot(self, k):
        return self.agg[k][0]

    def stale4(self, k):
        return self.agg[k][0].stale4


# --- the claims ---------------------------------------------------------------------------------
# Each returns (status, detail): status is True (holds), False (breaks) or None (n/a).


def c_anchor(r):
    if not r.has("A"):
        return None, "no config A"
    a = r.h4("A", None)
    detail = f"A {a}/44"
    same = None
    if r.has("EP3"):
        same = sum(1 for x, y in zip(sorted(r.res["A"], key=lambda q: q.qid), sorted(r.res["EP3"], key=lambda q: q.qid))
                   if x.top[:4] == y.top[:4])
        detail += f", top 4 = Episode 3's on {same}/{len(r.res['EP3'])}"
    if "nomic" not in (r.embedder or ""):
        return None, detail + " (only meaningful for nomic)"
    return (abs(a - 9) <= 1 and (same is None or same >= 45)), detail


def c_units_bm25(r):
    if not r.has("S1", "B"):
        return None, "needs S1, B"
    return r.h4("S1") > r.h4("B"), f"S1 {r.h4('S1')} vs B {r.h4('B')}"


def c_units_dense(r):
    if not r.has("C", "A"):
        return None, "needs C, A"
    return r.h4("C") > r.h4("A"), f"C {r.h4('C')} vs A {r.h4('A')}"


def c_bm25_line(r):
    if not r.has("S1", "S2", "S3"):
        return None, "needs S1-S3"
    ok = r.h4("S2") >= r.h4("S1") and r.h4("S3") >= r.h4("S2") and r.stale4("S3") < r.stale4("S2")
    return ok, f"S1 {r.h4('S1')}, S2 {r.h4('S2')}, S3 {r.h4('S3')}; stale@4 {r.stale4('S2')}→{r.stale4('S3')}"


def c_ids_hybrid(r):
    if not r.has("S4", "F1"):
        return None, "needs S4, F1"
    a, b = r.h4("F1", "identifier"), r.h4("S4", "identifier")
    return a < b, f"identifier without id lookup {a}/8 vs with {b}/8"


def c_dense_paraphrase(r):
    if not r.has("S3", "S4"):
        return None, "needs S3, S4"
    a, b = r.h4("S3", "paraphrase"), r.h4("S4", "paraphrase")
    return b > a, f"paraphrase {a}→{b}; Hit@4 {r.h4('S3')}→{r.h4('S4')}"


def c_s4_relation(r):
    if not r.has("S3", "S4"):
        return None, "needs S3, S4"
    ok, why = S.ratchet(r.res["S3"], r.res["S4"])
    rel = any(w.startswith("relation") for w in why)
    return (not ok and rel), ("fails: " + "; ".join(why)) if not ok else "passes"


def c_reranker_fails(r):
    if not r.has("S4", "S5"):
        return None, "no S5 (no reranker)"
    ok, why = S.ratchet(r.res["S4"], r.res["S5"])
    t5, t4 = r.tot("S5"), r.tot("S4")
    d = f"S5 {t5.h4} vs S4 {t4.h4}, all@4 {t5.all4} vs {t4.all4}, stale@4 {t5.stale4} vs {t4.stale4}"
    return (not ok), ("fails: " + "; ".join(why) + "; " if not ok else "passes; ") + d


def c_episode5_bm25(r):
    if not r.has("S3", "X1", "X2"):
        return None, "needs S3, X1, X2"
    a, b, c = r.h4("S3"), r.h4("X1"), r.h4("X2")
    p1, _ = S.ratchet(r.res["S3"], r.res["X1"])
    p2, _ = S.ratchet(r.res["X1"], r.res["X2"])
    return (c >= b >= a and p1 and p2), (f"S3 {a}, X1 {b}, X2 {c}; relation X2 {r.h4('X2', 'relation')}/8; "
                                         f"ratchet {'pass' if p1 else 'FAIL'}, {'pass' if p2 else 'FAIL'}")


def c_h2_tradeoff(r):
    if not r.has("X2", "H2"):
        return None, "needs X2, H2"
    pa, pb = r.h4("X2", "paraphrase"), r.h4("H2", "paraphrase")
    ra, rb = r.h4("X2", "relation"), r.h4("H2", "relation")
    ok, why = S.ratchet(r.res["X2"], r.res["H2"])
    d = (f"Hit@4 {r.h4('H2')} vs {r.h4('X2')}, all@4 {r.tot('H2').all4} vs {r.tot('X2').all4}, "
         f"paraphrase {pb} vs {pa}, relation {rb} vs {ra}; ratchet {'pass' if ok else 'FAIL: ' + '; '.join(why)}")
    return (pb > pa and rb < ra and not ok), d


def c_decline_gate(r):
    if not r.has("S5"):
        return None, "no S5 (no reranker)"
    s = S.top1_split(r.res["S5"])
    a, u = s["answerable_unpinned"], s["unanswerable"]
    if not a or not u:
        return None, "no scores"
    below = sum(1 for q in r.res["S5"] if q.stratum == "unanswerable" and q.top1_score is not None and q.top1_score < a["p25"])
    return below == u["n"], f"{below}/{u['n']} unanswerable below the answerable p25 ({a['p25']:.3g}); unanswerable max {u['max']:.3g}"


CLAIMS = [
    ("anchor", "harness: nomic config A ≈ 9/44 with Episode 3's top 4", c_anchor, "9/44, 50/50"),
    ("units-bm25", "units beat naive chunks under BM25 (S1 > B)", c_units_bm25, "30 vs 16"),
    ("units-dense", "units beat naive chunks under dense (C > A)", c_units_dense, "25 vs 9"),
    ("bm25-line", "BM25 line: S1 ≤ S2 ≤ S3, lifecycle cuts stale@4", c_bm25_line, "30, 32, 32; 3→1"),
    ("ids-hybrid", "id lookup needed for identifiers under hybrid (F1 < S4)", c_ids_hybrid, "5/8 without"),
    ("dense-para", "dense (S4) lifts paraphrase over S3", c_dense_paraphrase, "2→4; 32→34"),
    ("s4-relation", "S4 fails the ratchet on relation", c_s4_relation, "relation 7→5"),
    ("rerank-fails", "reranker (S5) fails the ratchet vs S4", c_reranker_fails, "33 vs 34, all@4 28 vs 31, stale 2"),
    ("ep5-bm25", "X2 ≥ X1 ≥ S3, both pass (Episode 5 on BM25)", c_episode5_bm25, "32, 34, 35; relation 8/8"),
    ("h2-tradeoff", "H2 vs X2: paraphrase up, relation down, fails", c_h2_tradeoff, "35 vs 35, para 4 vs 2, rel 6 vs 8"),
    ("decline-gate", "reranker top-1 separates unanswerable (S5)", c_decline_gate, "6/6 below p25"),
]


def status(ok):
    return "n/a" if ok is None else ("holds" if ok else "BREAKS")


def cell(r, k):
    if not r.has(k):
        return "–"
    tot, by = r.agg[k]
    return f"{tot.h4} {tot.all4} {by['paraphrase'].h4} {by['relation'].h4} {tot.stale4}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="run.py .jsonl files (globs allowed)")
    ap.add_argument("--md", action="store_true", help="markdown output")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # redirected output on Windows would be cp1252
    except (AttributeError, ValueError):
        pass
    paths = expand(a.files)
    if not paths:
        raise SystemExit("no result files")
    runs = [Run(load(p)) for p in paths]
    md = a.md
    out = []
    w = out.append

    w("# Does the story hold?\n" if md else "DOES THE STORY HOLD?\n")
    for r in runs:
        head = f"{r.name}: {r.embedder or 'no embedder'} + {r.reranker or 'no reranker'}"
        w(f"## {head}\n" if md else f"== {head}")
        if md:
            w("| | claim | this run | Mac (nomic + MiniLM) |")
            w("|---|---|---|---|")
        for key, text, fn, mac in CLAIMS:
            ok, detail = fn(r)
            if md:
                st = {"holds": "holds", "BREAKS": "**BREAKS**", "n/a": "n/a"}[status(ok)]
                w(f"| {st} | {text} | {detail} | {mac} |")
            else:
                w(f"  {status(ok):6s}  {text}\n          {detail}   [Mac: {mac}]")
        w("")

    names = [r.name for r in runs]
    w("## Claims at a glance\n" if md else "CLAIMS AT A GLANCE")
    if md:
        w("| claim | " + " | ".join(names) + " |")
        w("|---|" + "---|" * len(names))
        for key, text, fn, _ in CLAIMS:
            w(f"| {text} | " + " | ".join(status(fn(r)[0]) for r in runs) + " |")
    else:
        width = max(12, *(len(n) for n in names))
        w(f"  {'claim':14s} " + " ".join(f"{n:>{width}s}" for n in names))
        for key, text, fn, _ in CLAIMS:
            w(f"  {key:14s} " + " ".join(f"{status(fn(r)[0]):>{width}s}" for r in runs))
    w("")

    legend = "each cell: Hit@4 · all@4 · paraphrase Hit@4 (of 10) · relation Hit@4 (of 8) · stale@4"
    w("## Main configurations side by side\n" if md else "MAIN CONFIGURATIONS SIDE BY SIDE")
    w(legend + "\n" if md else "  " + legend)
    if md:
        w("| config | " + " | ".join(names) + " |")
        w("|---|" + "---|" * len(names))
        for k in TABLE:
            if any(r.has(k) for r in runs):
                w(f"| {k} | " + " | ".join(cell(r, k).replace(' ', ' · ') if r.has(k) else '–' for r in runs) + " |")
    else:
        width = max(14, *(len(n) for n in names))
        w(f"  {'config':6s} " + " ".join(f"{n:>{width}s}" for n in names))
        for k in TABLE:
            if any(r.has(k) for r in runs):
                w(f"  {k:6s} " + " ".join(f"{cell(r, k):>{width}s}" for r in runs))
    print("\n".join(out))


if __name__ == "__main__":
    main()
