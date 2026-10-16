# Ratchet prototype: wordllama

Run 2026-10-16 01:21 · spectastic c64d41c · 10,540 element units in 11,492 items (units over 250 words split into parts) · 10,540 prior-prototype units · 2,147 naive chunks

- Embedder: wordllama 0.4.0.post1, l2_supercat_256.safetensors sha256 64b47a2dc493cb8e85944076601189739852d7b64e0e1eedcb1937a251cd9fd5 (bundled in the wheel; PROXY)
- Reranker: reranker cross-encoder/ms-marco-MiniLM-L-6-v2 skipped: sentence-transformers is not installed (pip install sentence-transformers)
- Context tokens: cl100k_base via tiktoken (SHA-256 checked); counted over the text given to a reader (heading path + unit text, or the chunk)
- Golden set: src/main/resources/golden/questions.jsonl (answerable 44, unanswerable 6); run time 19 s
- **PROXY embedder.** WordLlama is a static bag-of-token-vectors model (256-d), not a contextual encoder like nomic-embed-text. Dense and hybrid rows show the harness works and the direction of some effects; they are not Episode 4 numbers. Re-run on the Mac with nomic-embed-text:v1.5.

## Episode 4 main line and Episode 5 (cumulative)

Each row adds one step to the row above. Verdict against the previous row that ran: **pass** unless overall Hit@4 or all-evidence@4 drops, a stratum loses more than one question at Hit@4, or stale-in-top-4 rises.

| key | configuration | Hit@4 | Partial@4 | MRR@50 | all@4 | all@10 | stale@4 | ctx tokens mean / max | verdict | won / lost at Hit@4 |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | 1 element units + BM25 | 30/44 (68%) | – | 0.553 | 24 | 28 | 3 | 528 / 1227 | (start) |  |
| S2 | 2 + identifier lookup | 32/44 (73%) | – | 0.636 | 26 | 30 | 3 | 529 / 1227 | **pass** (vs S1) | +2 G-026 G-028 / −0 |
| S3 | 3 + lifecycle filter | 32/44 (73%) | – | 0.655 | 26 | 30 | 1 | 529 / 1227 | **pass** (vs S2) | +0 / −0 |
| S4 | 4 + dense, RRF k=60 | 31/44 (70%) | – | 0.581 | 28 | 28 | 0 | 512 / 1281 | **fail**: Hit@4 32→31; relation 7→4 (vs S3) | +4 G-006 G-018 G-037 G-044 / −5 G-001 G-009 G-029 G-035 G-036 |
| E5-1 | E5-1 + supersession redirect (history kept behind) — on S4 (reranker skipped) | 31/44 (70%) | – | 0.610 | 28 | 28 | 0 | 512 / 1281 | **pass** (vs S4) | +0 / −0 |
| E5-2 | E5-2 + anchored typed expansion — on S4 (reranker skipped) | 33/44 (75%) | – | 0.630 | 30 | 30 | 0 | 512 / 1281 | **pass** (vs E5-1) | +2 G-029 G-030 / −0 |

## Episode 5 on the BM25 line (no embedder involved)

The same two Episode 5 steps on top of step 3, so their effect can be read without any embedder.

| key | configuration | Hit@4 | Partial@4 | MRR@50 | all@4 | all@10 | stale@4 | ctx tokens mean / max | verdict | won / lost at Hit@4 |
|---|---|---|---|---|---|---|---|---|---|---|
| S3 | 3 + lifecycle filter | 32/44 (73%) | – | 0.655 | 26 | 30 | 1 | 529 / 1227 | (start) |  |
| X1 | S3 + supersession redirect (history kept behind) | 34/44 (77%) | – | 0.705 | 28 | 31 | 0 | 533 / 1227 | **pass** (vs S3) | +2 G-037 G-044 / −0 |
| X2 | S3 + redirect + anchored typed expansion | 35/44 (80%) | – | 0.713 | 30 | 33 | 0 | 525 / 1227 | **pass** (vs X1) | +1 G-030 / −0 |

## Variants, epilogue and ablations

| key | configuration | Hit@4 | Partial@4 | MRR@50 | all@4 | all@10 | stale@4 | ctx tokens mean / max |
|---|---|---|---|---|---|---|---|---|
| P0 | prior units, FTS tokenchars '-', BM25 | 28/44 (64%) | – | 0.518 | 22 | 28 | 3 | 464 / 1506 |
| P1 | prior units, FTS tokenchars '-', BM25 + prior id lookup + lifecycle | 32/44 (73%) | – | 0.628 | 26 | 31 | 1 | 465 / 1506 |
| P2 | prior units, default tokenizer, BM25 | 27/44 (61%) | – | 0.488 | 21 | 28 | 3 | 499 / 2124 |
| P3 | prior units, default tokenizer, BM25 + id lookup + lifecycle | 31/44 (70%) | – | 0.621 | 25 | 31 | 1 | 504 / 2124 |
| E5-1r | variant: redirect drops applied history (earlier prototype's rule) — on S4 (reranker skipped) | 31/44 (70%) | – | 0.614 | 28 | 28 | 0 | 509 / 1281 |
| E5-2r | variant: E5-2 with the dropping redirect — on S4 (reranker skipped) | 33/44 (75%) | – | 0.634 | 30 | 30 | 0 | 509 / 1281 |
| EpiB | epilogue: RRF-merge neighbours (k=60, w=0.5) instead of anchored expansion — on S4 (reranker skipped) | 29/44 (66%) | – | 0.330 | 27 | 30 | 3 | 595 / 1450 |
| A | naive 800-token chunks, dense only | 13/44 (30%) | 14 | 0.201 | 10 | 17 | 3 | 2752 / 3191 |
| B | naive 800-token chunks, BM25 only | 16/44 (36%) | 17 | 0.268 | 13 | 26 | 4 | 2793 / 3170 |
| C | element units, dense only | 16/44 (36%) | – | 0.272 | 14 | 17 | 2 | 513 / 1076 |
| D | element units, dense + id lookup + lifecycle | 24/44 (55%) | – | 0.451 | 22 | 25 | 1 | 531 / 1076 |
| E | hybrid without lifecycle filter (S4 minus step 3) | 30/44 (68%) | – | 0.576 | 27 | 27 | 1 | 506 / 1281 |
| F1 | hybrid without id lookup (S4 minus step 2) | 24/44 (55%) | – | 0.433 | 21 | 23 | 0 | 509 / 1281 |
| F2 | naive chunks, BM25 + dense RRF (no id lookup, no lifecycle) | 16/44 (36%) | 17 | 0.274 | 13 | 27 | 3 | 2825 / 3190 |
| F3 | element units, BM25 + dense RRF (no id lookup, no lifecycle) | 23/44 (52%) | – | 0.427 | 20 | 22 | 1 | 503 / 1281 |
| F4 | S3 without heading path and parts (prior units, Ep4 linker) | 31/44 (70%) | – | 0.621 | 25 | 31 | 1 | 504 / 2124 |
| F6 | S3 without parts (long units whole) | 32/44 (73%) | – | 0.639 | 26 | 32 | 1 | 545 / 2171 |
| F7 | S3 without heading path | 33/44 (75%) | – | 0.624 | 27 | 31 | 1 | 492 / 1257 |
| EP3 | Episode 3 run replayed (its real nomic top-4, rescored here) | 9/44 (20%) | 11 | 0.138 (@4) | 8 | 8 | 1 | 2818 / 3178 |

Skipped: **S5** (5 + cross-encoder rerank top 50): reranker cross-encoder/ms-marco-MiniLM-L-6-v2 skipped: sentence-transformers is not installed (pip install sentence-transformers); **F5** (S5 without dense (BM25 + id + lifecycle + rerank)): reranker cross-encoder/ms-marco-MiniLM-L-6-v2 skipped: sentence-transformers is not installed (pip install sentence-transformers)

## Per stratum: Hit@4 · all@4 · all@10

| key | single-fact (10) | paraphrase (10) | identifier (8) | relation (8) | stale (8) | stale@4 |
|---|---|---|---|---|---|---|
| P0 | 9 · 9 · 10 | 2 · 2 · 3 | 4 · 4 · 5 | 7 · 1 · 3 | 6 · 6 · 7 | 3 |
| P1 | 9 · 9 · 10 | 2 · 2 · 3 | 8 · 8 · 8 | 7 · 1 · 3 | 6 · 6 · 7 | 1 |
| P2 | 9 · 9 · 10 | 2 · 2 · 4 | 4 · 4 · 5 | 7 · 1 · 2 | 5 · 5 · 7 | 3 |
| P3 | 9 · 9 · 10 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 5 · 5 · 7 | 1 |
| S1 | 9 · 9 · 9 | 2 · 2 · 4 | 6 · 6 · 6 | 7 · 1 · 2 | 6 · 6 · 7 | 3 |
| S2 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 6 · 6 · 7 | 3 |
| S3 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 6 · 6 · 7 | 1 |
| S4 | 8 · 8 · 8 | 3 · 3 · 3 | 8 · 8 · 8 | 4 · 1 · 1 | 8 · 8 · 8 | 0 |
| E5-1 | 8 · 8 · 8 | 3 · 3 · 3 | 8 · 8 · 8 | 4 · 1 · 1 | 8 · 8 · 8 | 0 |
| E5-2 | 8 · 8 · 8 | 3 · 3 · 3 | 8 · 8 · 8 | 6 · 3 · 3 | 8 · 8 · 8 | 0 |
| E5-1r | 8 · 8 · 8 | 3 · 3 · 3 | 8 · 8 · 8 | 4 · 1 · 1 | 8 · 8 · 8 | 0 |
| E5-2r | 8 · 8 · 8 | 3 · 3 · 3 | 8 · 8 · 8 | 6 · 3 · 3 | 8 · 8 · 8 | 0 |
| EpiB | 9 · 9 · 9 | 3 · 3 · 3 | 6 · 6 · 8 | 4 · 2 · 2 | 7 · 7 · 8 | 3 |
| X1 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 8 · 8 · 8 | 0 |
| X2 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 8 · 3 · 4 | 8 · 8 · 8 | 0 |
| A | 5 · 5 · 6 | 3 · 3 · 3 | 1 · 1 · 1 | 3 · 0 · 3 | 1 · 1 · 4 | 3 |
| B | 8 · 8 · 9 | 3 · 3 · 4 | 0 · 0 · 4 | 3 · 0 · 4 | 2 · 2 · 5 | 4 |
| C | 8 · 8 · 8 | 2 · 2 · 3 | 0 · 0 · 0 | 3 · 1 · 2 | 3 · 3 · 4 | 2 |
| D | 8 · 8 · 8 | 2 · 2 · 3 | 8 · 8 · 8 | 3 · 1 · 2 | 3 · 3 · 4 | 1 |
| E | 8 · 8 · 8 | 3 · 3 · 3 | 8 · 8 · 8 | 4 · 1 · 1 | 7 · 7 · 7 | 1 |
| F1 | 8 · 8 · 8 | 3 · 3 · 3 | 1 · 1 · 3 | 4 · 1 · 1 | 8 · 8 · 8 | 0 |
| F2 | 6 · 6 · 9 | 2 · 2 · 5 | 0 · 0 · 5 | 4 · 1 · 3 | 4 · 4 · 5 | 3 |
| F3 | 8 · 8 · 8 | 3 · 3 · 3 | 1 · 1 · 3 | 4 · 1 · 1 | 7 · 7 · 7 | 1 |
| F4 | 9 · 9 · 10 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 5 · 5 · 7 | 1 |
| F6 | 9 · 9 · 10 | 3 · 3 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 5 · 5 · 8 | 1 |
| F7 | 9 · 9 · 10 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 7 · 7 · 7 | 1 |
| EP3 | 5 · 5 · 5 | 2 · 2 · 2 | 1 · 1 · 1 | 1 · 0 · 0 | 0 · 0 · 0 | 1 |

## Checks against Episode 3 and the earlier prototype

- Naive chunks rebuilt: **2,147** (Episode 3 manifest: 2,147). Every Episode 3 "chunk N of M" total matches this splitter: 0 mismatches.
- Answerable questions with an expected element whole in some naive chunk: **38/44** (Episode 3: 38/44); expected elements whole in some chunk: 46/52.
- Episode 3's own retrieved top-4 lists, rescored by this scorer: Hit@4 9/44, Partial@4 11/44, MRR@4 0.14; single 5, paraphrase 2, identifier 1, relation 1, stale 0 (Episode 3 summary: 9, 11, 0.14; 5, 2, 1, 1, 0).
- Config A's top-4 equals Episode 3's top-4 (same chunks, same order) on **0/50** questions. With the same nomic-embed-text digest it should be at or near 50/50 (Ollama's batching can move near-ties); with any other embedder it means nothing.

## Unanswerable questions: top-1 score of the last ranking stage (hint only)

Pinned identifier hits have no score and are left out. Scores are not comparable across rows (BM25, cosine, RRF and cross-encoder scales differ). Declining needs the full run with the chat model.

| key | answerable, unpinned: n · min · p25 · p50 · max | unanswerable: n · min · p25 · p50 · max |
|---|---|---|
| P0 | 44 · 13.3 · 20.1 · 26.9 · 54.3 | 6 · 11.5 · 13 · 15.8 · 33.8 |
| P1 | 33 · 13.3 · 19.9 · 27.4 · 54.3 | 6 · 11.2 · 11.5 · 15.8 · 33.8 |
| P2 | 44 · 13.7 · 20.7 · 27.5 · 55.9 | 6 · 11.4 · 12.5 · 15.5 · 31.6 |
| P3 | 33 · 13.7 · 19.7 · 28.2 · 55.9 | 6 · 11.2 · 11.4 · 15.5 · 31.6 |
| S1 | 44 · 13.8 · 20.6 · 27.2 · 55.1 | 6 · 11.7 · 12.3 · 15.4 · 31.1 |
| S2 | 33 · 13.8 · 20.5 · 27.7 · 55.1 | 6 · 11.7 · 12.3 · 15.4 · 31.1 |
| S3 | 33 · 13.8 · 20.4 · 27.7 · 55.1 | 6 · 11.1 · 11.7 · 15.4 · 31.1 |
| S4 | 33 · 0.0241 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0248 · 0.0283 · 0.0323 |
| E5-1 | 33 · 0.0241 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0248 · 0.0283 · 0.0323 |
| E5-2 | 33 · 0.0241 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0248 · 0.0283 · 0.0323 |
| E5-1r | 33 · 0.0241 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0248 · 0.0283 · 0.0323 |
| E5-2r | 33 · 0.0241 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0248 · 0.0283 · 0.0323 |
| EpiB | 33 · 0.0241 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0248 · 0.0283 · 0.0323 |
| X1 | 33 · 13.8 · 20.4 · 27.7 · 55.1 | 6 · 11.1 · 11.7 · 15.4 · 31.1 |
| X2 | 33 · 13.8 · 20.4 · 27.7 · 55.1 | 6 · 11.1 · 11.7 · 15.4 · 31.1 |
| A | 44 · 0.367 · 0.471 · 0.513 · 0.735 | 6 · 0.336 · 0.38 · 0.423 · 0.495 |
| B | 44 · 12.2 · 17.7 · 23.5 · 44.8 | 6 · 9.09 · 9.1 · 11.5 · 21.1 |
| C | 44 · 0.388 · 0.52 · 0.58 · 0.75 | 6 · 0.351 · 0.459 · 0.466 · 0.508 |
| D | 33 · 0.388 · 0.491 · 0.535 · 0.75 | 6 · 0.351 · 0.459 · 0.462 · 0.508 |
| E | 33 · 0.024 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0247 · 0.0302 · 0.0323 |
| F1 | 44 · 0.0241 · 0.0306 · 0.0319 · 0.0328 | 6 · 0.0164 · 0.0248 · 0.0283 · 0.0323 |
| F2 | 44 · 0.0241 · 0.0315 · 0.0323 · 0.0328 | 6 · 0.0164 · 0.028 · 0.0318 · 0.0325 |
| F3 | 44 · 0.024 · 0.0306 · 0.032 · 0.0328 | 6 · 0.0164 · 0.0247 · 0.0302 · 0.0323 |
| F4 | 33 · 13.7 · 19.7 · 28.2 · 55.9 | 6 · 11.2 · 11.4 · 15.5 · 31.6 |
| F6 | 33 · 14 · 19.7 · 28.5 · 56.1 | 6 · 11.2 · 11.2 · 15.5 · 31.3 |
| F7 | 33 · 13.6 · 20.2 · 27.5 · 54.9 | 6 · 11.2 · 11.9 · 15.5 · 31.5 |
