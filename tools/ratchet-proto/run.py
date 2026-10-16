#!/usr/bin/env python3
"""Ratchet prototype: runs Episode 4's retrieval steps and Episode 5's graph steps over the golden
set, and writes a markdown table and a JSONL of per-question ranks.

    python3 run.py --embedder wordllama --out results/proxy-wordllama
    python3 run.py --embedder ollama:nomic-embed-text:v1.5 \\
        --reranker cross-encoder/ms-marco-MiniLM-L-6-v2 --out results/mac-nomic
    python3 run.py --embedder llamacpp:qwen3-embedding-8b-q8_0 --reranker llamacpp:bge-reranker-v2-m3-fp16 \\
        --out results/5090-qwen3-emb-8b        # llama-servers on :8090 and :8091 (run_5090.ps1 starts them)

See README.md for what each configuration is and how to read the verdicts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from ratchet import bm25 as B  # noqa: E402
from ratchet import corpus as C  # noqa: E402
from ratchet import embed as E  # noqa: E402
from ratchet import html as H  # noqa: E402
from ratchet import idlookup as I  # noqa: E402
from ratchet import pipeline as P  # noqa: E402
from ratchet import rerank as R  # noqa: E402
from ratchet import score as S  # noqa: E402
from ratchet import splitter as SP  # noqa: E402
from ratchet import tok as T  # noqa: E402
from ratchet.pipeline import Config  # noqa: E402

MAIN = ["S1", "S2", "S3", "S4", "S5", "E5-1", "E5-2"]


def configs() -> list[Config]:
    ep4 = dict(items="units", corpus="ep4")
    return [
        # earlier keyword prototype, reproduced (legacy units, tokenchars '-', its linker)
        Config("P0", "prior units, FTS tokenchars '-', BM25", corpus="legacy", dash_tokens=True),
        Config("P1", "prior units, FTS tokenchars '-', BM25 + prior id lookup + lifecycle", corpus="legacy",
               dash_tokens=True, ids=True, lifecycle=True, linker="prior"),
        Config("P2", "prior units, default tokenizer, BM25", corpus="legacy"),
        Config("P3", "prior units, default tokenizer, BM25 + id lookup + lifecycle", corpus="legacy", ids=True, lifecycle=True),
        # Episode 4 main line, cumulative
        Config("S1", "1 element units + BM25", **ep4),
        Config("S2", "2 + identifier lookup", ids=True, **ep4),
        Config("S3", "3 + lifecycle filter", ids=True, lifecycle=True, **ep4),
        Config("S4", "4 + dense, RRF k=60", ids=True, lifecycle=True, dense=True, needs=("dense",), **ep4),
        Config("S5", "5 + cross-encoder rerank top 50", ids=True, lifecycle=True, dense=True, rerank=True,
               needs=("dense", "rerank"), **ep4),
        # Episode 5 on top of Episode 4's final line
        Config("E5-1", "E5-1 + supersession redirect (history kept behind)", ids=True, lifecycle=True, dense=True,
               rerank=True, redirect="behind", needs=("dense", "rerank"), **ep4),
        Config("E5-2", "E5-2 + anchored typed expansion", ids=True, lifecycle=True, dense=True, rerank=True,
               redirect="behind", expand=True, needs=("dense", "rerank"), **ep4),
        Config("E5-1r", "variant: redirect drops applied history (earlier prototype's rule)", ids=True, lifecycle=True,
               dense=True, rerank=True, redirect="replace", needs=("dense", "rerank"), **ep4),
        Config("E5-2r", "variant: E5-2 with the dropping redirect", ids=True, lifecycle=True, dense=True, rerank=True,
               redirect="replace", expand=True, needs=("dense", "rerank"), **ep4),
        Config("EpiB", "epilogue: RRF-merge neighbours (k=60, w=0.5) instead of anchored expansion", ids=True,
               lifecycle=True, dense=True, rerank=True, redirect="behind", rrf_neighbours=True, needs=("dense", "rerank"), **ep4),
        # Episode 5 steps on the BM25 line (exact here: no embedder involved)
        Config("X1", "S3 + supersession redirect (history kept behind)", ids=True, lifecycle=True, redirect="behind", **ep4),
        Config("X2", "S3 + redirect + anchored typed expansion", ids=True, lifecycle=True, redirect="behind", expand=True, **ep4),
        # hybrid line without the reranker, Episode 5 steps folded in (added after the first Mac run)
        Config("H1", "S3 + redirect + dense RRF (no reranker)", ids=True, lifecycle=True, dense=True,
               redirect="behind", needs=("dense",), **ep4),
        Config("H2", "H1 + anchored typed expansion (no reranker)", ids=True, lifecycle=True, dense=True,
               redirect="behind", expand=True, needs=("dense",), **ep4),
        # ablations
        Config("A", "naive 800-token chunks, dense only", items="chunks", bm25=False, dense=True, needs=("dense",)),
        Config("B", "naive 800-token chunks, BM25 only", items="chunks"),
        Config("C", "element units, dense only", bm25=False, dense=True, needs=("dense",), **ep4),
        Config("D", "element units, dense + id lookup + lifecycle", bm25=False, dense=True, ids=True, lifecycle=True,
               needs=("dense",), **ep4),
        Config("E", "hybrid without lifecycle filter (S4 minus step 3)", dense=True, ids=True, needs=("dense",), **ep4),
        Config("F1", "hybrid without id lookup (S4 minus step 2)", dense=True, lifecycle=True, needs=("dense",), **ep4),
        Config("F2", "naive chunks, BM25 + dense RRF (no id lookup, no lifecycle)", items="chunks", dense=True, needs=("dense",)),
        Config("F3", "element units, BM25 + dense RRF (no id lookup, no lifecycle)", dense=True, needs=("dense",), **ep4),
        Config("F4", "S3 without heading path and parts (prior units, Ep4 linker)", corpus="legacy", ids=True, lifecycle=True),
        Config("F5", "S5 without dense (BM25 + id + lifecycle + rerank)", ids=True, lifecycle=True, rerank=True,
               needs=("rerank",), **ep4),
        Config("F6", "S3 without parts (long units whole)", corpus="ep4-noparts", ids=True, lifecycle=True),
        Config("F7", "S3 without heading path", corpus="ep4-nopath", ids=True, lifecycle=True),
    ]


def load_golden(path: Path) -> list:
    if "heldout" in path.name and "--score-heldout-at-episode-end" not in sys.argv:
        raise SystemExit("refusing to score a held-out file: held-out questions are scored once, at the end of an episode")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def element_texts(root: Path, addresses: set) -> dict:
    """GoldenScorer.elementText: normalised jsoup text of the first element with that id."""
    out, trees = {}, {}
    for a in sorted(addresses):
        f, _, ident = a.partition("#")
        if f not in trees:
            trees[f] = H.parse((root / f).read_text(encoding="utf-8"))
        el = trees[f].find(lambda e: e.id == ident)
        out[a] = S.normalise(H.jsoup_text(el)) if el is not None else ""
    return out


def naive_chunks(c: C.Corpus, enc) -> list:
    items = []
    for source in sorted(c.pages, key=lambda s: s):
        for i, ch in enumerate(SP.split(c.pages[source], enc), 1):
            items.append(C.Item(len(items), source, "", C.spec_of(source), "current", c.titles.get(source, ""),
                                "", "", ch, chunk=i))
    return items


def fmt_pct(a, n):
    return f"{a}/{n} ({100 * a / n:.0f}%)" if n else "–"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spectastic", default=str(REPO.parent / "spectastic"), help="spectastic checkout (default ../spectastic)")
    ap.add_argument("--golden", default=str(REPO / "src/main/resources/golden/questions.jsonl"))
    ap.add_argument("--embedder", default="wordllama", help="wordllama | ollama:<model> | llamacpp:<alias> | none")
    ap.add_argument("--reranker", default="none",
                    help="e.g. cross-encoder/ms-marco-MiniLM-L-6-v2 or llamacpp:<alias>")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--llamacpp-url", default="http://127.0.0.1:8090", help="llama-server for --embedder llamacpp:")
    ap.add_argument("--llamacpp-rerank-url", default="http://127.0.0.1:8091",
                    help="llama-server for --reranker llamacpp:")
    ap.add_argument("--cl100k-file", default=None, help="local cl100k_base.tiktoken (offline)")
    ap.add_argument("--cache", default=str(HERE / "cache"))
    ap.add_argument("--ep3-run", default=str(REPO / "results/episode-3/episode-3-qwen3_8b-duo-k4.jsonl"))
    ap.add_argument("--only", default="", help="comma-separated config keys")
    ap.add_argument("--out", default=str(HERE / "results/run"), help="output path without extension")
    ap.add_argument("--score-heldout-at-episode-end", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    t0 = time.time()
    root = Path(args.spectastic).resolve()
    if not (root / "specs").is_dir():
        raise SystemExit(f"no spectastic checkout at {root} (git clone --branch v0.1.0-pre.28 ...)")
    golden = load_golden(Path(args.golden))
    commits = {q["commit"] for q in golden}
    enc = T.load(args.cl100k_file)
    print(f"tokenizer: {T.how()}", file=sys.stderr)

    cache = Path(args.cache)
    corp = {v: C.load_or_build(root, cache, v) for v in C.VARIANTS}
    cp = corp["ep4"]
    warn = []
    if cp.commit not in commits:
        warn.append(f"spectastic is at {cp.commit}, the golden set was checked against {sorted(commits)}: a new baseline, not a comparison")

    addrs = {a for q in golden for a in q["expected"] + (q.get("stale") or [])}
    etext = element_texts(root, addrs)
    chunks = naive_chunks(cp, enc) if enc is not None else None
    if chunks is None:
        warn.append("tiktoken/cl100k unavailable: naive-chunk configurations skipped")
    scorer = S.ChunkScorer(cp.pages, etext)

    # --- embedder, reranker -----------------------------------------------------------------
    emb = None
    if args.embedder != "none":
        emb = E.make(args.embedder, args.ollama_url, args.llamacpp_url, cache)
        emb.attach_cache(cache)
    rr, rr_msg = R.make(args.reranker, args.llamacpp_rerank_url, cache)
    print(rr_msg, file=sys.stderr)

    # --- indexes ----------------------------------------------------------------------------
    idx = {k: I.IdIndex(v.units) for k, v in corp.items()}
    graph = P.Graph(cp, idx["ep4"])
    bm = {}

    def bm25_for(corpus_key, dash, items):
        k = (corpus_key, dash)
        if k not in bm:
            bm[k] = B.BM25(items, dash_tokens=dash)
        return bm[k]

    uvec = cvec = None
    qtexts = [q["question"] for q in golden]
    qvec = None
    if emb is not None:
        uvec = emb.embed_docs([it.passage() for it in cp.units])
        if chunks is not None:
            cvec = emb.embed_docs([it.passage() for it in chunks])
        qvec = emb.embed_queries(qtexts)

    def tokens(it):
        return T.count(it.passage())

    # --- runs ------------------------------------------------------------------------------
    results, skipped, labels, kinds = {}, {}, {}, {"EP3": "chunks"}
    only = set(filter(None, args.only.split(",")))
    for cfg in configs():
        if only and cfg.key not in only:
            continue
        cfg_run = cfg
        if "dense" in cfg.needs and emb is None:
            skipped[cfg.key] = (cfg.label, "no embedder")
            continue
        if cfg.items == "chunks" and chunks is None:
            skipped[cfg.key] = (cfg.label, "no cl100k tokenizer for the naive splitter")
            continue
        label = cfg.label
        if "rerank" in cfg.needs and rr is None:
            if cfg.key in ("S5", "F5"):
                skipped[cfg.key] = (cfg.label, rr_msg)
                continue
            # Episode 5 rows still run, on top of S4, and say so
            from dataclasses import replace
            cfg_run = replace(cfg, rerank=False)
            label = cfg.label + " — on S4 (reranker skipped)"
        labels[cfg.key] = label
        kinds[cfg.key] = cfg.items
        units = corp[cfg.corpus].units
        uix = P.Index(units, bm25_for(cfg.corpus, cfg.dash_tokens, units), uvec if cfg.corpus == "ep4" else None)
        cix = P.Index(chunks, bm25_for("chunks", False, chunks), cvec) if chunks is not None else None
        g = graph if cfg.corpus == "ep4" else None
        pipe = P.Pipeline(uix, cix, idx[cfg.corpus], g, rr)
        hit_fn = S.unit_hit if cfg.items == "units" else scorer.hit
        out = []
        for qi, q in enumerate(golden):
            final, top1, npinned = pipe.run(cfg_run, q["question"], qvec[qi] if qvec is not None else None)
            items = (uix if cfg.items == "units" else cix).items
            out.append(S.rank_list([items[n] for n in final], q, hit_fn, tokens, top1, npinned))
        results[cfg.key] = out
        tot, _ = S.aggregate(out)
        print(f"{cfg.key:6s} Hit@4 {tot.h4}/{tot.n}  all@4 {tot.all4}  MRR {tot.mrr:.3f}  stale@4 {tot.stale4}  {label}", file=sys.stderr)

    # --- Episode 3 replay and corpus checks --------------------------------------------------
    calib = {}
    if chunks is not None:
        calib["chunks"] = len(chunks)
        by_addr = {(it.source, it.chunk): it for it in chunks}
        nchunks = {}
        for it in chunks:
            nchunks[it.source] = nchunks.get(it.source, 0) + 1
        per_q = {}
        whole_q = whole_e = n_e = 0
        for q in golden:
            if q["stratum"] == "unanswerable":
                continue
            anyfull = False
            for a in q["expected"]:
                n_e += 1
                f = a.split("#")[0]
                full = any(scorer.hit(a, it) == S.FULL for it in chunks if it.source == f)
                whole_e += full
                anyfull |= full
            whole_q += anyfull
        calib["whole_q"], calib["whole_e"], calib["n_e"] = whole_q, whole_e, n_e
        ep3 = Path(args.ep3_run)
        if ep3.exists():
            rows = [json.loads(l) for l in ep3.read_text(encoding="utf-8").splitlines()[1:] if l.strip()]
            gq = {q["id"]: q for q in golden}
            replay, mism = [], 0
            for r in rows:
                its = []
                for x in r["retrieved"]:
                    m = re.match(r"(.*), chunk (\d+) of (\d+)$", x["address"])
                    f, i, tot_ = m.group(1), int(m.group(2)), int(m.group(3))
                    mism += nchunks.get(f) != tot_
                    its.append(by_addr[(f, i)])
                replay.append(S.rank_list(its, gq[r["id"]], scorer.hit, tokens, its and r["retrieved"][0]["score"]))
            results["EP3"] = replay
            labels["EP3"] = "Episode 3 run replayed (its real nomic top-4, rescored here)"
            calib["ep3_total_mismatch"] = mism
            if "A" in results:
                same = sum(1 for a, b in zip(results["A"], replay) if a.top[:4] == b.top[:4])
                calib["A_vs_ep3_same_top4"] = same

    # --- write -------------------------------------------------------------------------------
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp.with_suffix(".jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for key, res in results.items():
            for r in res:
                f.write(json.dumps({
                    "config": key, "label": labels.get(key, key), "embedder": emb.name if emb else None,
                    "reranker": rr.name if rr else None, "embedder_id": emb.model_id if emb else None,
                    "reranker_id": getattr(rr, "model_id", rr.name) if rr else None, "id": r.qid, "stratum": r.stratum,
                    "expected": r.expected, "ranks": r.ranks, "partial_ranks": r.partial_ranks,
                    "first_hit": r.first, "stale_ranks": r.stale_ranks, "pinned": r.pinned,
                    "context_tokens_top4": r.context_tokens, "top1_score": r.top1_score, "top10": r.top,
                }) + "\n")
    md = report(args, cp, corp, chunks, emb, rr_msg, results, labels, kinds, skipped, calib, warn, time.time() - t0)
    outp.with_suffix(".md").write_text(md, encoding="utf-8", newline="\n")
    print(f"wrote {outp.with_suffix('.md')} and {outp.with_suffix('.jsonl')}", file=sys.stderr)


def report(args, cp, corp, chunks, emb, rr_msg, results, labels, kinds, skipped, calib, warn, secs) -> str:
    L = []
    w = L.append
    nparts = len(cp.units)
    nunits = len({(u.source, u.anchor) for u in cp.units})
    w(f"# Ratchet prototype: {emb.name if emb else 'no embedder'}\n")
    nchunks = f"{len(chunks):,} naive chunks" if chunks is not None else "naive chunks not built"
    w(f"Run {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} · spectastic {cp.commit[:7]} · "
      f"{nunits:,} element units in {nparts:,} items (units over {C.PART_WORDS} words split into parts) · "
      f"{len(corp['legacy'].units):,} prior-prototype units · {nchunks}")
    w("")
    w(f"- Embedder: {emb.provenance if emb else 'none'}")
    if emb is not None and getattr(emb, "longest", 0):
        w(f"- Longest embedder input embedded in this run: {emb.longest} tokens (texts already in the vector cache are not re-counted)")
    if emb is not None and getattr(emb, 'truncated', 0):
        w(f"- **{emb.truncated} texts were longer than the embedding model's window and were embedded truncated.**")
    w(f"- Reranker: {rr_msg}")
    w(f"- Context tokens: {T.how()}; counted over the text given to a reader (heading path + unit text, or the chunk)")
    gpath = Path(args.golden).resolve()
    gshow = gpath.relative_to(REPO) if gpath.is_relative_to(REPO) else gpath
    w(f"- Golden set: {gshow} (answerable 44, unanswerable 6); run time {secs:.0f} s")
    for x in warn:
        w(f"- **Warning:** {x}")
    if emb is not None and emb.name == "wordllama":
        w("- **PROXY embedder.** WordLlama is a static bag-of-token-vectors model (256-d), not a contextual "
          "encoder like nomic-embed-text. Dense and hybrid rows show the harness works and the direction of "
          "some effects; they are not Episode 4 numbers. Re-run on the Mac with nomic-embed-text:v1.5.")
    w("")

    def row(key):
        res = results[key]
        tot, by = S.aggregate(res)
        cs = S.context_stats(res)
        p4 = f"{tot.p4}" if kinds.get(key) == "chunks" else "–"
        mrr = f"{tot.mrr:.3f}" if key != "EP3" else f"{tot.mrr4:.3f} (@4)"
        return [key, labels.get(key, key), fmt_pct(tot.h4, tot.n), p4, mrr, str(tot.all4), str(tot.all10),
                str(tot.stale4), f"{cs['mean']:.0f} / {cs['max']}"], tot, by

    head = "| key | configuration | Hit@4 | Partial@4 | MRR@50 | all@4 | all@10 | stale@4 | ctx tokens mean / max"
    sep = "|---|---|---|---|---|---|---|---|---|"

    def chain(title, keys, intro):
        w(f"## {title}\n")
        w(intro + "\n")
        w(head + " | verdict | won / lost at Hit@4 |")
        w(sep + "---|---|")
        prev = None
        for key in keys:
            if key not in results:
                continue
            cells, tot, by = row(key)
            if prev is None:
                verdict, wl = "(start)", ""
            else:
                ok, why = S.ratchet(results[prev], results[key])
                verdict = ("**pass**" if ok else "**fail**: " + "; ".join(why)) + f" (vs {prev})"
                won, lost = S.flips(results[prev], results[key])
                wl = " ".join([f"+{len(won)}"] + won) + " / " + " ".join([f"−{len(lost)}"] + lost)
            w("| " + " | ".join(cells + [verdict, wl]) + " |")
            prev = key
        w("")

    chain("Episode 4 main line and Episode 5 (cumulative)", MAIN,
          "Each row adds one step to the row above. Verdict against the previous row that ran: **pass** unless "
          "overall Hit@4 or all-evidence@4 drops, a stratum loses more than one question at Hit@4, or "
          "stale-in-top-4 rises.")
    chain("Episode 5 on the BM25 line (no embedder involved)", ["S3", "X1", "X2"],
          "The same two Episode 5 steps on top of step 3, so their effect can be read without any embedder.")
    w("## Variants, epilogue and ablations\n")
    w(head + " |")
    w(sep)
    for key in results:
        if key in MAIN or key in ("X1", "X2"):
            continue
        cells, _, _ = row(key)
        w("| " + " | ".join(cells) + " |")
    w("")
    if skipped:
        w("Skipped: " + "; ".join(f"**{k}** ({v[0]}): {v[1]}" for k, v in skipped.items()) + "\n")

    w("## Per stratum: Hit@4 · all@4 · all@10\n")
    w("| key | " + " | ".join(f"{s} ({n})" for s, n in zip(S.STRATA, (10, 10, 8, 8, 8))) + " | stale@4 |")
    w("|---|" + "---|" * (len(S.STRATA) + 1))
    for key in results:
        _, by = S.aggregate(results[key])
        w(f"| {key} | " + " | ".join(f"{by[s].h4} · {by[s].all4} · {by[s].all10}" for s in S.STRATA) +
          f" | {sum(by[s].stale4 for s in S.STRATA)} |")
    w("")

    w("## Checks against Episode 3 and the earlier prototype\n")
    if "chunks" in calib:
        w(f"- Naive chunks rebuilt: **{calib['chunks']:,}** (Episode 3 manifest: 2,147). Every Episode 3 "
          f"\"chunk N of M\" total matches this splitter: {calib.get('ep3_total_mismatch', '?')} mismatches.")
        w(f"- Answerable questions with an expected element whole in some naive chunk: **{calib['whole_q']}/44** "
          f"(Episode 3: 38/44); expected elements whole in some chunk: {calib['whole_e']}/{calib['n_e']}.")
    if "EP3" in results:
        tot, by = S.aggregate(results["EP3"])
        w(f"- Episode 3's own retrieved top-4 lists, rescored by this scorer: Hit@4 {tot.h4}/44, Partial@4 {tot.p4}/44, "
          f"MRR@4 {tot.mrr4:.2f}; single {by['single-fact'].h4}, paraphrase {by['paraphrase'].h4}, identifier "
          f"{by['identifier'].h4}, relation {by['relation'].h4}, stale {by['stale'].h4} "
          f"(Episode 3 summary: 9, 11, 0.14; 5, 2, 1, 1, 0).")
    if "A_vs_ep3_same_top4" in calib:
        w(f"- Config A's top-4 equals Episode 3's top-4 (same chunks, same order) on "
          f"**{calib['A_vs_ep3_same_top4']}/50** questions. With the same nomic-embed-text digest it should be at or near 50/50 "
          f"(Ollama's batching can move near-ties; nomic through llama.cpp is another build of the same weights, so "
          f"expect most, not all); with any other embedder it means nothing.")
    w("")

    w("## Unanswerable questions: top-1 score of the last ranking stage (hint only)\n")
    w("Pinned identifier hits have no score and are left out. Scores are not comparable across rows "
      "(BM25, cosine, RRF and cross-encoder scales differ). Declining needs the full run with the chat model.\n")
    w("| key | answerable, unpinned: n · min · p25 · p50 · max | unanswerable: n · min · p25 · p50 · max |")
    w("|---|---|---|")

    def d5(d):
        return "–" if not d else f"{d['n']} · {d['min']:.3g} · {d['p25']:.3g} · {d['p50']:.3g} · {d['max']:.3g}"

    for key in results:
        if key == "EP3":
            continue
        s = S.top1_split(results[key])
        w(f"| {key} | {d5(s['answerable_unpinned'])} | {d5(s['unanswerable'])} |")
    w("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
