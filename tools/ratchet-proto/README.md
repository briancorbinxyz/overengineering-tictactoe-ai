# Ratchet prototype for Episodes 4 and 5

A Python harness that runs each planned retrieval step over the spectastic corpus and the
golden set, so we can decide which steps to build in Java before building them. It is a
prototype of the *retrieval* only: no chat model, no answers, no declines.

Everything is standard-library Python plus numpy. Optional extras: `tiktoken` (the naive
chunks and exact token counts), an Ollama server (real embedders), `sentence-transformers`
(the reranker) and `wordllama` (a proxy embedder for machines without Ollama).

## Run it

On a Mac with Ollama running:

```bash
ollama pull nomic-embed-text:v1.5
ollama pull qwen3-embedding:0.6b
git clone --depth 1 --branch v0.1.0-pre.28 https://github.com/spectastic/spectastic.git ../spectastic   # next to the repo
tools/ratchet-proto/run_mac.sh
```

`run_mac.sh` makes a virtualenv in `tools/ratchet-proto/.venv`, installs `numpy tiktoken
sentence-transformers`, runs the tests, then runs every configuration twice, once per
embedder, with the MiniLM reranker:

- `results/mac-nomic-embed-text.md` and `.jsonl`
- `results/mac-qwen3-embedding.md` and `.jsonl`

The first run embeds about 13,700 texts per model (11,492 unit items and 2,147 naive
chunks) and downloads the reranker (about 90 MB). Vectors are cached in
`tools/ratchet-proto/cache/`, keyed by the model's Ollama digest and the exact text, so a
second run takes seconds.

One configuration by hand:

```bash
python3 tools/ratchet-proto/run.py --embedder ollama:nomic-embed-text:v1.5 \
    --reranker cross-encoder/ms-marco-MiniLM-L-6-v2 --out tools/ratchet-proto/results/my-run
python3 tools/ratchet-proto/run.py --embedder none --only S1,S2,S3     # BM25 only, no model at all
python3 -m unittest discover -s tools/ratchet-proto/tests
```

`--embedder` takes `ollama:<model>`, `wordllama` or `none`. `--reranker` takes a
sentence-transformers cross-encoder name or `none`. Offline, `--cl100k-file` points at a
local `cl100k_base.tiktoken` (it is checked against the published SHA-256).

The harness refuses to score `questions-heldout.jsonl`. Held-out questions are scored once,
at the end of an episode, in the Java build.

## What it reproduces

These checks don't depend on the embedder. They are why the numbers below can be trusted
as far as they go.

| Check | Here | Reference |
|---|---|---|
| Body text of all 627 pages (port of jsoup 1.21.2 `Element.text()`) | identical, 627/627 | jsoup 1.21.2 run in Java |
| Naive chunks (port of Spring AI 2.0.1 `TokenTextSplitter`, cl100k) | 2,147, identical text in 627/627 files | Episode 3 manifest: 2,147; same split run in Java with jtokkit |
| "chunk N of M" totals in Episode 3's run file | 0 mismatches | `results/episode-3/*.jsonl` |
| Questions with an expected element whole in some naive chunk | 38/44 | Episode 3: 38/44 |
| Episode 3's real top-4 lists, rescored by this scorer | Hit@4 9/44, Partial@4 11/44, MRR@4 0.14; strata 5·2·1·1·0 | Episode 3 summary: identical |
| Element units (prior definition) | 10,540, identical text, lifecycle, title and heading | earlier prototype's `units.json` |
| Link graph and supersession map | 12,283 edges and 170 redirects, identical | earlier prototype's `graph.json` |
| Earlier keyword prototype, BM25 only (`P0`) | Hit@4 28/44, all@4 22, MRR 0.518, stale@4 3 | 28/44 (64%), 22, 0.518, 3 |
| Earlier keyword prototype, + id lookup + lifecycle (`P1`) | Hit@4 32/44, all@4 26, MRR 0.628, stale@4 1 | 32/44 (73%), 26, 0.628, 1 |

The jsoup and Spring AI comparisons were made once, against jsoup 1.21.2 and jtokkit
compiled from source. The tests keep a few of those reference outputs.

## The configurations

All configurations use the same 50 questions; the 6 unanswerable ones are reported
separately. Every list is cut to 50 items.

**Episode 4 main line**, cumulative. Each row adds one step; fixed defaults, nothing tuned:

| Key | Step | What it does |
|---|---|---|
| S1 | Element units + BM25 | One unit per element with an `id`, holding its own text (id'd descendants are their own units); units of 3 words or fewer are dropped. Its heading path (page title › headings of id'd ancestors) is prefixed to what a reader sees and indexed in the BM25 title column. Units over 250 words are split into parts at sentence ends (about 350 cl100k tokens, so question and part fit MiniLM's 512 word pieces); any part counts as the unit. |
| S2 | + identifier lookup | `FR-012 in spec 040` → that unit pinned first. Spec matching is case-insensitive (`Spec 058's`). An id with no spec pins only if it exists in one spec. Rules and tests: `ratchet/idlookup.py`, `tests/test_idlookup.py`. |
| S3 | + lifecycle filter | Drops withdrawn, superseded and rejected units (from the path, `data-status`/`status` on the element or an ancestor, or a superseded page); keeps applied history in `changes/archive/`, which G-006 and G-018 need. |
| S4 | + dense, RRF | BM25 and cosine lists (top 100 each, lifecycle-filtered first) fused by Σ 1/(60 + rank); identifier hits stay pinned above the fusion. |
| S5 | + reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` reorders the first 50 unpinned items. |
| E5-1 | + supersession redirect | A stale item is replaced by its current successor (spec-delta targets, in-place `superseded` status with a link, "superseded by" prose; up to three hops). An applied-history item stays, right behind its successor. |
| E5-2 | + anchored typed expansion | From the first pinned unit, follow typed links only (validates, cites, target incl. spec-delta, defer-to), one hop, at most 5 units ranked by BM25 among themselves, inserted right after the anchor, after the reranker. |

Without a reranker, S5 is skipped and E5-1/E5-2 run on top of S4, labelled as such.

**Variants and ablations**:

| Key | Configuration | Isolates |
|---|---|---|
| P0, P1 | The earlier keyword prototype exactly (its units, FTS `tokenchars '-'`, its linker) | reproduction |
| P2, P3 | Same units, default tokenizer | the tokenizer change |
| X1, X2 | S3 + redirect, S3 + redirect + expansion | Episode 5 on the BM25 line (no embedder involved) |
| E5-1r, E5-2r | Redirect that drops applied history instead of keeping it behind | the "kept behind" rule |
| EpiB | RRF-merge of neighbours of the top 5 (all link types, k=60, weight 0.5) instead of anchored expansion | the epilogue's rejected design |
| A | Naive 800-token chunks, dense only | Episode 3's pipeline (calibrates the embedder: nomic should give 9/44) |
| B | Naive chunks, BM25 only | chunks vs units under BM25 (with S1) |
| C | Units, dense only | chunks vs units under dense (with A) |
| D | Units, dense + id lookup + lifecycle | S3 with dense instead of BM25 |
| E | S4 without the lifecycle filter | step 3 inside the hybrid |
| F1 | S4 without id lookup | step 2 inside the hybrid |
| F2, F3 | Naive chunks vs units, both BM25 + dense RRF, nothing else | step 1 inside the hybrid |
| F4 | S3 with the prior units (no heading path, no parts) | heading path + parts together |
| F5 | S5 without dense | whether the reranker needs the dense list |
| F6, F7 | S3 without parts; S3 without heading path | each half of step 1 |

## Metrics

Over the 44 answerable questions, overall and per stratum:

- **Hit@4**: an expected element is in the top 4. For units, the item *is* that element or a
  part of it. For naive chunks, Episode 3's rule: the chunk holds the element's text whole.
- **Partial@4** (chunks only): a chunk holds at least half of an expected element.
- **MRR@50**: reciprocal rank of the first hit within 50 (Episode 3's 0.14 is within its 4).
- **all@4, all@10**: every expected element is present (matters for relation questions).
- **stale@4**: questions with a stale expected element (the `stale` field) in the top 4; for
  chunks, at least half of it.
- **Context tokens**: cl100k tokens of the top 4 as a reader gets them (heading path + unit
  text, or the chunk), via tiktoken; mean and max over all 50 questions.
- **Unanswerable**: the top-1 score of the last ranking stage, answerable vs unanswerable.
  A hint only: deciding to decline needs the chat model.

## The ratchet rule

A main-line step passes against the step before it unless overall Hit@4 drops, all-evidence@4
drops, any stratum loses more than one question at Hit@4, or stale-in-top-4 rises. The table
also lists which questions were won and lost at Hit@4, because a pass can hide a swap.

## Caveats

- **The golden set favours BM25.** Its questions were drafted by reading the passages, so
  they share words with them. Single-fact questions were chosen for distinctive strings
  ("len/4", "p-map"), identifier questions name the id, stale questions share wording with the
  stale copy by design. **Paraphrase** is the stratum least affected: its questions avoid the
  element's own words on purpose (G-019 avoids "overflow" and "390 px"). Read dense gains on
  paraphrase as the most honest signal, and BM25 wins on single-fact as partly built in.
- **Small numbers.** One question is 2.3 points of overall Hit@4; relation, identifier and stale
  have 8 questions each. Treat a one-question change as noise unless a mechanism explains it;
  the per-question JSONL is there to find the mechanism.
- **The WordLlama proxy is not nomic.** It is a static token-embedding model, closer to a
  smoothed bag of words than to a contextual encoder. On Episode 3's own pipeline (config A) it
  scores 13/44 where nomic scored 9/44, so it is *more* lexical than nomic here. Dense and
  hybrid rows from the proxy show that the code works and give directions; they are not
  Episode 4 numbers.
- **Units and chunks are scored at different granularity.** A unit hit puts about 130 tokens of
  evidence in the top 4; a chunk hit puts about 700. Compare the context-token column alongside
  Hit@4.
- **qwen3-embedding's query format.** Questions are sent as
  `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:<question>`,
  the model card's example; documents as they are. Whether Ollama's build applies the model's
  last-token pooling and normalisation is not verified here (vectors are normalised again
  anyway).
- **"Kept behind" is read literally.** E5-1 keeps an applied-history item directly behind its
  successor; E5-1r drops it, as the earlier prototype did. Report whichever the plan meant.
- **Lifecycle labelling gap.** 004's D-005 is superseded in place by a child `spec-status`, not a
  `data-status`, so the lifecycle filter keeps it; only the redirect fixes G-037.
- **Fixed, untuned defaults**: part size 250 words, depth 100 per list before fusion, RRF k=60,
  rerank top 50, at most 5 neighbours. None was tuned on the golden set.
- The reranker is not run in the cloud sandbox this was built in (no model download there).

## Files

| File | What it does |
|---|---|
| `run.py` | Builds everything, runs the configurations, writes the markdown table and the JSONL |
| `run_mac.sh` | The full run on a Mac with Ollama |
| `ratchet/html.py` | Standard-library HTML tree; jsoup's `text()` and BeautifulSoup's `get_text(' ')` |
| `ratchet/corpus.py` | Pages, element units, parts, lifecycle, links and the supersession map |
| `ratchet/splitter.py`, `ratchet/tok.py` | Spring AI's `TokenTextSplitter` and cl100k |
| `ratchet/bm25.py` | SQLite FTS5 with weighted columns |
| `ratchet/idlookup.py` | The identifier parser and pin order |
| `ratchet/embed.py`, `ratchet/rerank.py` | Embedders with a vector cache; the cross-encoder |
| `ratchet/pipeline.py` | Fusion, pinning, reranking, redirect, expansion |
| `ratchet/score.py` | Episode 3's chunk scorer, the unit scorer, metrics, the ratchet |
| `results/proxy-wordllama.*` | The run made without Ollama: BM25 rows exact, dense rows PROXY |

The JSONL has one line per configuration and question: the rank of each expected element,
the first hit, stale ranks, the top 10 addresses, context tokens and the top-1 score.
