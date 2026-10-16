# Ratchet prototype for Episodes 4 and 5

A Python harness that runs each planned retrieval step over the spectastic corpus and the
golden set, so we can decide which steps to build in Java before building them. It is a
prototype of the *retrieval* only: no chat model, no answers, no declines.

Everything is standard-library Python plus numpy. Optional extras: `tiktoken` (the naive
chunks and exact token counts), an Ollama server or llama-server (real embedders),
`sentence-transformers` or llama-server (the reranker) and `wordllama` (a proxy embedder for
machines without either).

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

`--embedder` takes `ollama:<model>`, `llamacpp:<alias>`, `wordllama` or `none`. `--reranker`
takes a sentence-transformers cross-encoder name, `llamacpp:<alias>` or `none` (llama.cpp
aliases: `python3 tools/ratchet-proto/ratchet/llamacpp.py list`). Offline, `--cl100k-file`
points at a local `cl100k_base.tiktoken` (it is checked against the published SHA-256).

The harness refuses to score `questions-heldout.jsonl`. Held-out questions are scored once,
at the end of an episode, in the Java build.

## Run on the RTX 5090

The same configurations and golden set with much stronger models, served by llama.cpp on a
Windows 11 PC with an RTX 5090 (32 GB). The question is whether the story from the Mac (nomic +
MiniLM) still holds when the embedder and reranker are no longer the weak link.

### From a fresh PowerShell

Needs git, Python 3.11+ (python.org or `winget install Python.Python.3.12`) and `llama-server`
on PATH (`winget install llama.cpp`, or the CUDA build from the llama.cpp releases page).

```powershell
git clone https://github.com/briancorbinxyz/rags-spring-ai.git
cd rags-spring-ai
git checkout episode-4-prototype          # existing clone: git fetch origin; git checkout episode-4-prototype; git pull
git -c core.autocrlf=false clone --depth 1 --branch v0.1.0-pre.28 https://github.com/spectastic/spectastic.git ..\spectastic
powershell -ExecutionPolicy Bypass -File tools\ratchet-proto\run_5090.ps1
```

`-List` prints the lineup, the exact `llama-server` command lines and the download size, and
stops. `-Models nomic,qwen3-emb-8b` runs a subset; `-Force` reruns runs that already have results;
`$env:SPECTASTIC` or `-Spectastic` points elsewhere.

What the script does: checks git, Python 3.11+, `llama-server` and the spectastic checkout (a
warning if it is not at c64d41c2e5d0d42c4fefd1b506cb083b9812bf6c); makes `tools\ratchet-proto\.venv`
with numpy and tiktoken only (no torch); checks that Python's SQLite has FTS5 (CPython's Windows
builds do; it stops with a message if not); runs the offline tests. Then, for each run: starts
`llama-server` for the embedder on port 8090 and for the reranker on 8091, waits for `/health`
(the first start downloads the model into the Hugging Face cache), runs `run.py`, and stops both
servers, also on error. A run whose `results\5090-<run>.md` and `.jsonl` exist is skipped, so a
stopped script picks up where it left off. Everything is logged to `results\5090-run.log` (each
server's own output to `results\5090-<run>-<role>.server.log`). At the end it runs `story.py`
over `results\5090-*.jsonl` and any `results\mac-*.jsonl`, to the console and `results\5090-story.md`.

It never touches another llama-server: if 8090 or 8091 is taken it refuses that run rather than
stop anything, and it does not read or change any OpenCode configuration, so the qwen3.6 chat
server keeps its port. It does share the GPU: the largest run (Qwen3-Embedding-8B + Qwen3-Reranker-8B,
16 GB of weights plus buffers) wants about 20 GB free; the script prints free VRAM and warns. With
`-ngl 99` nothing is offloaded to the CPU silently; a server that does not fit fails to start and
the script moves on.

### The lineup

| Run | Embedder | Reranker | Why |
|---|---|---|---|
| `nomic` | nomic-embed-text-v1.5 F16 | bge-reranker-v2-m3 FP16 | Anchor: config A should give about 9/44 and Episode 3's top 4; S1–S4, X, H rows comparable with the Mac |
| `qwen3-emb-8b` | Qwen3-Embedding-8B Q8_0 | bge-reranker-v2-m3 FP16 | The main stronger-model test |
| `qwen3-emb-8b-qwen3-rr` | Qwen3-Embedding-8B Q8_0 | Qwen3-Reranker-8B Q8_0 | The same embedder with an LLM reranker |
| `qwen3-emb-4b` | Qwen3-Embedding-4B Q8_0 | bge-reranker-v2-m3 FP16 | Does 4B tell the same story |
| `qwen3-emb-8b-f16` (optional) | Qwen3-Embedding-8B F16 | bge-reranker-v2-m3 FP16 | Q8_0 vs unquantised |

| Alias | `-hf` | File | Size |
|---|---|---|---|
| `nomic-embed-text-v1.5-f16` | `nomic-ai/nomic-embed-text-v1.5-GGUF:F16` | nomic-embed-text-v1.5.f16.gguf | 262 MiB |
| `qwen3-embedding-8b-q8_0` | `Qwen/Qwen3-Embedding-8B-GGUF:Q8_0` | Qwen3-Embedding-8B-Q8_0.gguf | 8.05 GB |
| `qwen3-embedding-8b-f16` | `Qwen/Qwen3-Embedding-8B-GGUF:F16` | Qwen3-Embedding-8B-f16.gguf | 15.1 GB |
| `qwen3-embedding-4b-q8_0` | `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` | (Q8_0 file) | 4.28 GB |
| `bge-reranker-v2-m3-fp16` | `gpustack/bge-reranker-v2-m3-GGUF:FP16` | bge-reranker-v2-m3-FP16.gguf | 1.16 GB |
| `qwen3-reranker-8b-q8_0` | `ethicalabs/Qwen3-Reranker-8B-GGUF:Q8_0` | Qwen3-Reranker-8B.Q8_0.gguf | 8.05 GB |

Server flags (all from `ratchet/llamacpp.py`, the one place they live): `-hf <repo>:<quant> -a <alias>
--host 127.0.0.1 --port 8090|8091 -ngl 99 -np 8 -c 16384` (2,048 tokens per slot), `-b 2048 -ub 2048`,
and `--embedding --pooling mean` (nomic), `--embedding --pooling last` (Qwen3-Embedding) or
`--reranking` (rerankers). The longest input is a naive chunk of 801 cl100k tokens (about 1,000
model tokens); unit parts are at most 569.

How inputs are sent:

- **nomic**: `search_document: ` and `search_query: `, as Episode 3. 2,048-token native context, no
  YaRN extension.
- **Qwen3-Embedding**: queries as `Instruct: Given a web search query, retrieve relevant passages
  that answer the query\nQuery:<question>` (the model card's format and example task; the same
  task the Mac run used), documents as they are, last-token pooling. Every input ends with exactly
  one `<|endoftext|>`: the official tokenizer appends it (Qwen's "Automatically add EOS via
  Tokenizer" change) and the model pools that token. Whether a given GGUF sets `add_eos_token` is
  not documented on the GGUF card, so the harness asks the server: it tokenizes a probe through
  `/tokenize` with special tokens on and off, appends `<|endoftext|>` as text only when the GGUF
  does not add it, and stops if the GGUF appends anything else. The report says which happened.
- **Rerankers**: `/v1/rerank` with `query`, `documents`, `top_n`. bge-reranker gets llama.cpp's
  `[BOS] query [EOS] [SEP] doc [EOS]` and returns a logit. A Qwen3-Reranker GGUF converted by a
  recent `convert_hf_to_gguf.py` carries a `rerank` prompt template (the model card's
  system/Instruct/Query/Document prompt) and a two-row yes/no head; llama.cpp scores it as
  softmax(yes, no)[yes]. Most public Qwen3-Reranker GGUFs predate that conversion and score null or
  garbage, so the harness first scores a sanity pair (Paris vs bananas) and refuses a reranker that
  ranks it wrong or returns null.

**Nothing is truncated.** Before embedding, every input is counted with the server's own
tokenizer (`/tokenize`, special tokens added as the embeddings endpoint adds them) against
min(`-ub`, the slot context from `/props`); one that does not fit stops the run with its length and
the setting to raise. Behind that, llama-server itself refuses (it never cuts): HTTP 500 "input
(N tokens) is too large to process. increase the physical batch size" for a non-causal model,
HTTP 400 `exceed_context_size_error` when a slot's context is too small; the harness turns either
into the same message. Each report records the longest input embedded.

**The vector cache** is keyed by `llamacpp:<repo>:<quant>@sha256-<first 16 hex of the GGUF>:pool=<pooling>`
plus the exact text sent. The file is the one the server reports in `/props` (`model_path`),
hashed once and remembered in `cache\gguf-sha256.json`. The report's provenance line has the
full SHA-256, the parameter count and the llama.cpp build. The harness also checks the server's
`/v1/models` alias before sending anything, so it cannot embed with a chat model that happens to
answer on the port.

### Time and disk

- Downloads on first use: 21.8 GB for the default lineup (15.1 GB more for the optional F16 run),
  into the Hugging Face cache (`%USERPROFILE%\.cache\huggingface\hub`, or `LLAMA_CACHE`/`HF_HOME`;
  older llama.cpp builds use `%LOCALAPPDATA%\llama.cpp`).
- Vector cache in `tools\ratchet-proto\cache\`: about 45 MB (nomic), 140 MB (4B), 230 MB (8B).
- Each run embeds about 13,700 texts (11,492 unit items, 2,147 naive chunks, 50 questions) and
  reranks about 5,000 query–passage pairs. Rough estimate, not measured on the 5090: a few minutes
  for nomic, 5–15 minutes for Qwen3-Embedding-8B, an hour or so for the whole default lineup on
  the first pass including downloads. The second run of the same embedder (`qwen3-emb-8b-qwen3-rr`)
  reuses the cached vectors.

### Reading story.py

```powershell
.\tools\ratchet-proto\.venv\Scripts\python.exe tools\ratchet-proto\story.py tools\ratchet-proto\results\5090-*.jsonl C:\path\to\mac-nomic-embed-text.jsonl
```

It takes any result files (globs are expanded by story.py itself). For each run it prints one line
per claim of the story: **holds**, **BREAKS**, or **n/a** (the run lacks a configuration the claim
needs, e.g. no reranker), with this run's numbers and the Mac's next to them; then the claims as a
grid (one column per run); then the main configurations side by side, each cell
`Hit@4 all@4 paraphrase relation stale@4`. `--md` gives the same as markdown.

| Claim | Holds when | Mac |
|---|---|---|
| `anchor` | nomic only: A within 9 ± 1 of 44 and A's top 4 = Episode 3's on ≥ 45/50 | 9/44, 50/50 |
| `units-bm25` | S1 > B | 30 vs 16 |
| `units-dense` | C > A | 25 vs 9 |
| `bm25-line` | S1 ≤ S2 ≤ S3 and S3 has less stale@4 than S2 | 30, 32, 32; 3 → 1 |
| `ids-hybrid` | identifier Hit@4: F1 (S4 without id lookup) < S4 | 5/8 without |
| `dense-para` | paraphrase Hit@4: S4 > S3 | 2 → 4 |
| `s4-relation` | S4 fails the ratchet against S3, relation among the reasons | relation 7 → 5 |
| `rerank-fails` | S5 fails the ratchet against S4 | 33 vs 34 |
| `ep5-bm25` | X2 ≥ X1 ≥ S3 and both pass | 32, 34, 35 |
| `h2-tradeoff` | H2 vs X2: paraphrase up, relation down, ratchet fails | para 4 vs 2, rel 6 vs 8 |
| `decline-gate` | every unanswerable question's S5 top-1 score is below the answerable p25 | 6/6 |

`units-bm25`, `bm25-line` and `ep5-bm25` use no model, so they must read the same in every run
(a check that the harness and corpus are the same). The ones to read are `units-dense`,
`dense-para`, `s4-relation`, `h2-tradeoff`, `rerank-fails` and `decline-gate`: if a strong
embedder no longer costs relation questions, `s4-relation` and `h2-tradeoff` break and the case for
the keyword line over the hybrid line weakens; if a strong reranker passes the ratchet,
`rerank-fails` breaks. Check `anchor` on the `nomic` run first: if config A is far from 9/44 there,
the llama.cpp build differs from Ollama's enough that the other rows are not comparable either.

The Mac results are not in the repository (`mac-nomic-embed-text`, `mac-qwen3-embedding` and
`mac-nomic-hybrid` are in `tools/ratchet-proto/results/` on the Mac). Copy the `.jsonl` files into
`results\` on the PC and the script includes them in the story, or pass their paths to story.py.

### Caveats

- **GGUF quantisation.** Q8_0 is close to lossless for embeddings but not identical to F16; the
  optional `qwen3-emb-8b-f16` run measures the difference. Ollama's `qwen3-embedding:0.6b` on the
  Mac was a different model size and its own build; it is not a baseline for these runs.
- **nomic through llama.cpp is not Ollama.** Same F16 weights, but a different runtime, batching
  and kernels (CUDA here, Metal there), so near-ties can swap; expect config A at or near 9/44 and
  most, not all, top-4 lists identical to Episode 3's. Ollama may also cut inputs at its context
  where llama.cpp refuses them; no input here is long enough for that to matter.
- **The rerankers are not the Mac's.** S5, E5-* and F5 use bge-reranker-v2-m3 or Qwen3-Reranker-8B
  instead of MiniLM; "the reranker fails the ratchet" is tested again with stronger rerankers, not
  repeated. Their scores (a logit, a probability) are on other scales than MiniLM's, which matters
  only for the decline-gate threshold, not for whether the scores separate.
- **Qwen3-Reranker-8B is a third-party GGUF** (ethicalabs), chosen because its card says it carries
  the rerank template and head and was tested with llama-server; the other public Q8_0 conversions it
  compares against do not. The sanity pair guards against a bad file; it does not prove the scores
  match the transformers reference. Not verified here: that GGUF was not downloaded (no Hugging Face
  access from the sandbox this was built in).
- **Not run on a GPU here.** The llama.cpp client was tested against a fake server with llama-server's
  request, response and error shapes, and against a real llama-server (CPU build of master 7182ef7)
  serving tiny random-weight BERT and Qwen3 GGUFs: embeddings, the EOS probe both ways, rerank with a
  Qwen3 rerank head and template, and both input-length refusals. The real models were not run.
- **Old llama.cpp builds** may refuse any embedding input longer than `-ub` (not just non-causal
  ones); `-ub` is set to the slot context for every model, so they behave the same.

### Sources

- llama.cpp server: flags, endpoints, request/response shapes and error messages read from the
  source at master 7182ef7 (2026-10-16): `tools/server/server-context.cpp` (embeddings, rerank,
  `/tokenize`, `/props`, the input-length checks), `tools/server/server-common.cpp`
  (`format_prompt_rerank`, the OpenAI-style response bodies, error codes), `common/arg.cpp` (flags),
  `common/common.cpp` (`-b` set to `-ub` with embeddings), `common/download.cpp` (how `:quant`
  picks a file), `conversion/qwen.py` (Qwen3-Reranker conversion: yes/no head, rank pooling, rerank
  template), `src/llama-graph.cpp` (softmax over yes/no for Qwen3 rank pooling);
  [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
- [Qwen/Qwen3-Embedding-8B-GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF) and
  [Qwen/Qwen3-Embedding-4B-GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF): files, sizes,
  `--embedding --pooling last -ub 8192`.
- [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B): query format
  `Instruct: {task}\nQuery:{query}`, no instruction for documents, last-token pooling.
- [Qwen/Qwen3-Embedding-8B discussion 1](https://huggingface.co/Qwen/Qwen3-Embedding-8B/discussions/1):
  the tokenizer appends `<|endoftext|>`, the token pooled (merged 2025-06-06).
- [nomic-ai/nomic-embed-text-v1.5-GGUF](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF):
  files, 2,048-token default context, task prefixes.
- [gpustack/bge-reranker-v2-m3-GGUF](https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF):
  files (FP16 1.16 GB), converted at llama.cpp's reranking commit.
- [ethicalabs/Qwen3-Reranker-8B-GGUF](https://huggingface.co/ethicalabs/Qwen3-Reranker-8B-GGUF): the
  Q8_0 file, `tokenizer.chat_template.rerank`, the comparison with other conversions;
  [Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp](https://huggingface.co/Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp):
  why most community Qwen3-Reranker GGUFs score garbage.

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
| `run_5090.ps1` | The full run on Windows with llama.cpp: starts and stops llama-server per model, resumable, logged |
| `story.py` | Checks each claim of the story against any set of result files; side-by-side table |
| `ratchet/html.py` | Standard-library HTML tree; jsoup's `text()` and BeautifulSoup's `get_text(' ')` |
| `ratchet/corpus.py` | Pages, element units, parts, lifecycle, links and the supersession map |
| `ratchet/splitter.py`, `ratchet/tok.py` | Spring AI's `TokenTextSplitter` and cl100k |
| `ratchet/bm25.py` | SQLite FTS5 with weighted columns |
| `ratchet/idlookup.py` | The identifier parser and pin order |
| `ratchet/embed.py`, `ratchet/rerank.py` | Embedders with a vector cache; the cross-encoder (sentence-transformers or llama.cpp) |
| `ratchet/llamacpp.py` | The llama.cpp lineup, server flags, per-model formats, the HTTP client, the EOS probe |
| `tests/fake_llama.py` | A stand-in llama-server for the offline tests |
| `ratchet/pipeline.py` | Fusion, pinning, reranking, redirect, expansion |
| `ratchet/score.py` | Episode 3's chunk scorer, the unit scorer, metrics, the ratchet |
| `results/proxy-wordllama.*` | The run made without Ollama: BM25 rows exact, dense rows PROXY |

The JSONL has one line per configuration and question: the rank of each expected element,
the first hit, stale ranks, the top 10 addresses, context tokens and the top-1 score.
