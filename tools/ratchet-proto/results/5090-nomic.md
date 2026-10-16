# Ratchet prototype: llamacpp:nomic-embed-text-v1.5-f16

Run 2026-10-16 15:54 · spectastic c64d41c · 10,540 element units in 11,492 items (units over 250 words split into parts) · 10,540 prior-prototype units · 2,147 naive chunks

- Embedder: llama.cpp nomic-ai/nomic-embed-text-v1.5-GGUF:F16 as `nomic-embed-text-v1.5-f16` (pooling mean); file C:\Users\blaca\.cache\huggingface\hub\models--nomic-ai--nomic-embed-text-v1.5-GGUF\snapshots\0188c9bf409793f810680a5a431e7b899c46104c\nomic-embed-text-v1.5.f16.gguf; sha256 f7af6f66802f4df86eda10fe9bbcfc75c39562bed48ef6ace719a251cf1c2fdb; 136727040 params, n_embd 768, n_ctx_train 2048; slot context 2048; server build b10919-d3146f2b5; queries as 'search_query: {text}', documents as 'search_document: {text}'; inputs must fit 2048 tokens (checked, never truncated)
- Longest embedder input embedded in this run: 1043 tokens (texts already in the vector cache are not re-counted)
- Reranker: llama.cpp gpustack/bge-reranker-v2-m3-GGUF:FP16 as `bge-reranker-v2-m3-fp16` (pooling rank); file C:\Users\blaca\.cache\huggingface\hub\models--gpustack--bge-reranker-v2-m3-GGUF\snapshots\3093af03b1a635e67b084b1d8c03c5f5e020fd05\bge-reranker-v2-m3-FP16.gguf; sha256 5df93be121c09c43432102ad2b9569d369ccb85c209ca7583e8ccd28f0e41b88; 567753729 params, n_embd 1024, n_ctx_train 8192; slot context 2048; server build b10919-d3146f2b5; sanity pair 7.796 > -11.04; query + passage must fit 2048 tokens (refused, never truncated)
- Context tokens: cl100k_base via tiktoken (SHA-256 checked); counted over the text given to a reader (heading path + unit text, or the chunk)
- Golden set: src\main\resources\golden\questions.jsonl (answerable 44, unanswerable 6); run time 97 s

## Episode 4 main line and Episode 5 (cumulative)

Each row adds one step to the row above. Verdict against the previous row that ran: **pass** unless overall Hit@4 or all-evidence@4 drops, a stratum loses more than one question at Hit@4, or stale-in-top-4 rises.

| key | configuration | Hit@4 | Partial@4 | MRR@50 | all@4 | all@10 | stale@4 | ctx tokens mean / max | verdict | won / lost at Hit@4 |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | 1 element units + BM25 | 30/44 (68%) | – | 0.553 | 24 | 28 | 3 | 528 / 1227 | (start) |  |
| S2 | 2 + identifier lookup | 32/44 (73%) | – | 0.636 | 26 | 30 | 3 | 529 / 1227 | **pass** (vs S1) | +2 G-026 G-028 / −0 |
| S3 | 3 + lifecycle filter | 32/44 (73%) | – | 0.655 | 26 | 30 | 1 | 529 / 1227 | **pass** (vs S2) | +0 / −0 |
| S4 | 4 + dense, RRF k=60 | 34/44 (77%) | – | 0.666 | 31 | 32 | 0 | 634 / 1216 | **fail**: relation 7→5 (vs S3) | +5 G-006 G-018 G-020 G-037 G-044 / −3 G-005 G-031 G-036 |
| S5 | 5 + cross-encoder rerank top 50 | 34/44 (77%) | – | 0.640 | 30 | 34 | 3 | 802 / 1539 | **fail**: all@4 31→30; stale@4 0→3 (vs S4) | +2 G-016 G-031 / −2 G-002 G-029 |
| E5-1 | E5-1 + supersession redirect (history kept behind) | 34/44 (77%) | – | 0.678 | 30 | 34 | 2 | 807 / 1539 | **pass** (vs S5) | +0 / −0 |
| E5-2 | E5-2 + anchored typed expansion | 36/44 (82%) | – | 0.696 | 32 | 36 | 2 | 795 / 1539 | **pass** (vs E5-1) | +2 G-029 G-030 / −0 |

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
| E5-1r | variant: redirect drops applied history (earlier prototype's rule) | 34/44 (77%) | – | 0.678 | 30 | 34 | 0 | 799 / 1539 |
| E5-2r | variant: E5-2 with the dropping redirect | 36/44 (82%) | – | 0.696 | 32 | 36 | 0 | 787 / 1539 |
| EpiB | epilogue: RRF-merge neighbours (k=60, w=0.5) instead of anchored expansion | 27/44 (61%) | – | 0.369 | 24 | 34 | 2 | 737 / 1539 |
| H1 | S3 + redirect + dense RRF (no reranker) | 34/44 (77%) | – | 0.678 | 31 | 32 | 0 | 634 / 1216 |
| H2 | H1 + anchored typed expansion (no reranker) | 35/44 (80%) | – | 0.689 | 33 | 34 | 0 | 635 / 1216 |
| A | naive 800-token chunks, dense only | 9/44 (20%) | 11 | 0.165 | 8 | 12 | 1 | 2818 / 3178 |
| B | naive 800-token chunks, BM25 only | 16/44 (36%) | 17 | 0.268 | 13 | 26 | 4 | 2793 / 3170 |
| C | element units, dense only | 25/44 (57%) | – | 0.472 | 23 | 26 | 1 | 711 / 1345 |
| D | element units, dense + id lookup + lifecycle | 30/44 (68%) | – | 0.585 | 28 | 30 | 0 | 721 / 1184 |
| E | hybrid without lifecycle filter (S4 minus step 3) | 34/44 (77%) | – | 0.651 | 31 | 32 | 2 | 629 / 1216 |
| F1 | hybrid without id lookup (S4 minus step 2) | 31/44 (70%) | – | 0.597 | 28 | 29 | 0 | 638 / 1216 |
| F2 | naive chunks, BM25 + dense RRF (no id lookup, no lifecycle) | 13/44 (30%) | 15 | 0.248 | 11 | 18 | 3 | 2795 / 3193 |
| F3 | element units, BM25 + dense RRF (no id lookup, no lifecycle) | 31/44 (70%) | – | 0.582 | 28 | 29 | 2 | 633 / 1216 |
| F4 | S3 without heading path and parts (prior units, Ep4 linker) | 31/44 (70%) | – | 0.621 | 25 | 31 | 1 | 504 / 2124 |
| F5 | S5 without dense (BM25 + id + lifecycle + rerank) | 33/44 (75%) | – | 0.644 | 29 | 33 | 3 | 755 / 1610 |
| F6 | S3 without parts (long units whole) | 32/44 (73%) | – | 0.639 | 26 | 32 | 1 | 545 / 2171 |
| F7 | S3 without heading path | 33/44 (75%) | – | 0.624 | 27 | 31 | 1 | 492 / 1257 |
| EP3 | Episode 3 run replayed (its real nomic top-4, rescored here) | 9/44 (20%) | 11 | 0.138 (@4) | 8 | 8 | 1 | 2818 / 3178 |

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
| S4 | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 5 · 2 · 2 | 8 · 8 · 8 | 0 |
| S5 | 8 · 8 · 10 | 5 · 5 · 6 | 8 · 8 · 8 | 5 · 1 · 2 | 8 · 8 · 8 | 3 |
| E5-1 | 8 · 8 · 10 | 5 · 5 · 6 | 8 · 8 · 8 | 5 · 1 · 2 | 8 · 8 · 8 | 2 |
| E5-2 | 8 · 8 · 10 | 5 · 5 · 6 | 8 · 8 · 8 | 7 · 3 · 4 | 8 · 8 · 8 | 2 |
| E5-1r | 8 · 8 · 10 | 5 · 5 · 6 | 8 · 8 · 8 | 5 · 1 · 2 | 8 · 8 · 8 | 0 |
| E5-2r | 8 · 8 · 10 | 5 · 5 · 6 | 8 · 8 · 8 | 7 · 3 · 4 | 8 · 8 · 8 | 0 |
| EpiB | 6 · 6 · 9 | 3 · 3 · 6 | 6 · 6 · 8 | 5 · 2 · 3 | 7 · 7 · 8 | 2 |
| X1 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 8 · 8 · 8 | 0 |
| X2 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 8 · 3 · 4 | 8 · 8 · 8 | 0 |
| H1 | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 5 · 2 · 2 | 8 · 8 · 8 | 0 |
| H2 | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 6 · 4 · 4 | 8 · 8 · 8 | 0 |
| A | 5 · 5 · 7 | 2 · 2 · 3 | 1 · 1 · 1 | 1 · 0 · 0 | 0 · 0 · 1 | 1 |
| B | 8 · 8 · 9 | 3 · 3 · 4 | 0 · 0 · 4 | 3 · 0 · 4 | 2 · 2 · 5 | 4 |
| C | 7 · 7 · 8 | 4 · 4 · 5 | 3 · 3 · 4 | 4 · 2 · 2 | 7 · 7 · 7 | 1 |
| D | 7 · 7 · 8 | 4 · 4 · 5 | 8 · 8 · 8 | 4 · 2 · 2 | 7 · 7 · 7 | 0 |
| E | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 5 · 2 · 2 | 8 · 8 · 8 | 2 |
| F1 | 9 · 9 · 10 | 4 · 4 · 4 | 5 · 5 · 5 | 5 · 2 · 2 | 8 · 8 · 8 | 0 |
| F2 | 7 · 7 · 9 | 2 · 2 · 4 | 1 · 1 · 3 | 2 · 0 · 1 | 1 · 1 · 1 | 3 |
| F3 | 9 · 9 · 10 | 4 · 4 · 4 | 5 · 5 · 5 | 5 · 2 · 2 | 8 · 8 · 8 | 2 |
| F4 | 9 · 9 · 10 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 5 · 5 · 7 | 1 |
| F5 | 8 · 8 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 5 · 1 · 3 | 8 · 8 · 8 | 3 |
| F6 | 9 · 9 · 10 | 3 · 3 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 5 · 5 · 8 | 1 |
| F7 | 9 · 9 · 10 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 7 · 7 · 7 | 1 |
| EP3 | 5 · 5 · 5 | 2 · 2 · 2 | 1 · 1 · 1 | 1 · 0 · 0 | 0 · 0 · 0 | 1 |

## Checks against Episode 3 and the earlier prototype

- Naive chunks rebuilt: **2,147** (Episode 3 manifest: 2,147). Every Episode 3 "chunk N of M" total matches this splitter: 0 mismatches.
- Answerable questions with an expected element whole in some naive chunk: **38/44** (Episode 3: 38/44); expected elements whole in some chunk: 46/52.
- Episode 3's own retrieved top-4 lists, rescored by this scorer: Hit@4 9/44, Partial@4 11/44, MRR@4 0.14; single 5, paraphrase 2, identifier 1, relation 1, stale 0 (Episode 3 summary: 9, 11, 0.14; 5, 2, 1, 1, 0).
- Config A's top-4 equals Episode 3's top-4 (same chunks, same order) on **48/50** questions. With the same nomic-embed-text digest it should be at or near 50/50 (Ollama's batching can move near-ties; nomic through llama.cpp is another build of the same weights, so expect most, not all); with any other embedder it means nothing.

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
| S4 | 33 · 0.0248 · 0.0313 · 0.0323 · 0.0328 | 6 · 0.0164 · 0.0215 · 0.0239 · 0.0317 |
| S5 | 33 · -5.97 · 0.106 · 2.68 · 6.88 | 6 · -2.91 · -2.45 · -0.832 · 0.301 |
| E5-1 | 33 · -5.97 · 0.106 · 2.68 · 6.88 | 6 · -2.91 · -2.45 · -0.832 · 0.301 |
| E5-2 | 33 · -5.97 · 0.106 · 2.68 · 6.88 | 6 · -2.91 · -2.45 · -0.832 · 0.301 |
| E5-1r | 33 · -5.97 · 0.106 · 2.68 · 6.88 | 6 · -2.91 · -2.45 · -0.832 · 0.301 |
| E5-2r | 33 · -5.97 · 0.106 · 2.68 · 6.88 | 6 · -2.91 · -2.45 · -0.832 · 0.301 |
| EpiB | 33 · -5.97 · 0.106 · 2.68 · 6.88 | 6 · -2.91 · -2.45 · -0.832 · 0.301 |
| X1 | 33 · 13.8 · 20.4 · 27.7 · 55.1 | 6 · 11.1 · 11.7 · 15.4 · 31.1 |
| X2 | 33 · 13.8 · 20.4 · 27.7 · 55.1 | 6 · 11.1 · 11.7 · 15.4 · 31.1 |
| H1 | 33 · 0.0248 · 0.0313 · 0.0323 · 0.0328 | 6 · 0.0164 · 0.0215 · 0.0239 · 0.0317 |
| H2 | 33 · 0.0248 · 0.0313 · 0.0323 · 0.0328 | 6 · 0.0164 · 0.0215 · 0.0239 · 0.0317 |
| A | 44 · 0.671 · 0.726 · 0.753 · 0.824 | 6 · 0.65 · 0.69 · 0.692 · 0.768 |
| B | 44 · 12.2 · 17.7 · 23.5 · 44.8 | 6 · 9.09 · 9.1 · 11.5 · 21.1 |
| C | 44 · 0.679 · 0.741 · 0.769 · 0.862 | 6 · 0.654 · 0.717 · 0.718 · 0.768 |
| D | 33 · 0.69 · 0.743 · 0.782 · 0.837 | 6 · 0.654 · 0.701 · 0.718 · 0.768 |
| E | 33 · 0.0246 · 0.0313 · 0.0323 · 0.0328 | 6 · 0.0164 · 0.0214 · 0.0261 · 0.0317 |
| F1 | 44 · 0.0248 · 0.0315 · 0.0321 · 0.0328 | 6 · 0.0164 · 0.0215 · 0.0239 · 0.0317 |
| F2 | 44 · 0.0254 · 0.0318 · 0.0323 · 0.0328 | 6 · 0.0233 · 0.0256 · 0.0267 · 0.0323 |
| F3 | 44 · 0.0246 · 0.0315 · 0.0321 · 0.0328 | 6 · 0.0164 · 0.0214 · 0.0261 · 0.0317 |
| F4 | 33 · 13.7 · 19.7 · 28.2 · 55.9 | 6 · 11.2 · 11.4 · 15.5 · 31.6 |
| F5 | 33 · -5.14 · 0.106 · 2.68 · 6.88 | 6 · -3.89 · -3.14 · -2.68 · 0.301 |
| F6 | 33 · 14 · 19.7 · 28.5 · 56.1 | 6 · 11.2 · 11.2 · 15.5 · 31.3 |
| F7 | 33 · 13.6 · 20.2 · 27.5 · 54.9 | 6 · 11.2 · 11.9 · 15.5 · 31.5 |
