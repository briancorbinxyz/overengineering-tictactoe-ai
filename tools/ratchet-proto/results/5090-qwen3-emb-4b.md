# Ratchet prototype: llamacpp:qwen3-embedding-4b-q8_0

Run 2026-10-16 16:25 · spectastic c64d41c · 10,540 element units in 11,492 items (units over 250 words split into parts) · 10,540 prior-prototype units · 2,147 naive chunks

- Embedder: llama.cpp Qwen/Qwen3-Embedding-4B-GGUF:Q8_0 as `qwen3-embedding-4b-q8_0` (pooling last); file C:\Users\blaca\.cache\huggingface\hub\models--Qwen--Qwen3-Embedding-4B-GGUF\snapshots\f4602530db1d980e16da9d7d3a70294cf5c190be\Qwen3-Embedding-4B-Q8_0.gguf; sha256 b60ae5ce2dd6a0b77f82cadf21def1f310a3e10cde380ad0081b07a9d416949d; 4021774336 params, n_embd 2560, n_ctx_train 40960; slot context 2048; server build b10919-d3146f2b5; queries as 'Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:{text}', documents as '{text}'; <|endoftext|> added by the GGUF's tokenizer (add_eos_token); inputs must fit 2048 tokens (checked, never truncated)
- Longest embedder input embedded in this run: 973 tokens (texts already in the vector cache are not re-counted)
- Reranker: llama.cpp gpustack/bge-reranker-v2-m3-GGUF:FP16 as `bge-reranker-v2-m3-fp16` (pooling rank); file C:\Users\blaca\.cache\huggingface\hub\models--gpustack--bge-reranker-v2-m3-GGUF\snapshots\3093af03b1a635e67b084b1d8c03c5f5e020fd05\bge-reranker-v2-m3-FP16.gguf; sha256 5df93be121c09c43432102ad2b9569d369ccb85c209ca7583e8ccd28f0e41b88; 567753729 params, n_embd 1024, n_ctx_train 8192; slot context 2048; server build b10919-d3146f2b5; sanity pair 7.796 > -11.04; query + passage must fit 2048 tokens (refused, never truncated)
- Context tokens: cl100k_base via tiktoken (SHA-256 checked); counted over the text given to a reader (heading path + unit text, or the chunk)
- Golden set: src\main\resources\golden\questions.jsonl (answerable 44, unanswerable 6); run time 511 s

## Episode 4 main line and Episode 5 (cumulative)

Each row adds one step to the row above. Verdict against the previous row that ran: **pass** unless overall Hit@4 or all-evidence@4 drops, a stratum loses more than one question at Hit@4, or stale-in-top-4 rises.

| key | configuration | Hit@4 | Partial@4 | MRR@50 | all@4 | all@10 | stale@4 | ctx tokens mean / max | verdict | won / lost at Hit@4 |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | 1 element units + BM25 | 30/44 (68%) | – | 0.553 | 24 | 28 | 3 | 528 / 1227 | (start) |  |
| S2 | 2 + identifier lookup | 32/44 (73%) | – | 0.636 | 26 | 30 | 3 | 529 / 1227 | **pass** (vs S1) | +2 G-026 G-028 / −0 |
| S3 | 3 + lifecycle filter | 32/44 (73%) | – | 0.655 | 26 | 30 | 1 | 529 / 1227 | **pass** (vs S2) | +0 / −0 |
| S4 | 4 + dense, RRF k=60 | 35/44 (80%) | – | 0.691 | 31 | 33 | 1 | 545 / 1216 | **pass** (vs S3) | +5 G-006 G-018 G-020 G-037 G-044 / −2 G-009 G-036 |
| S5 | 5 + cross-encoder rerank top 50 | 33/44 (75%) | – | 0.656 | 29 | 35 | 3 | 790 / 1371 | **fail**: Hit@4 35→33; all@4 31→29; stale@4 1→3 (vs S4) | +1 G-009 / −3 G-002 G-005 G-029 |
| E5-1 | E5-1 + supersession redirect (history kept behind) | 33/44 (75%) | – | 0.694 | 29 | 35 | 2 | 792 / 1371 | **pass** (vs S5) | +0 / −0 |
| E5-2 | E5-2 + anchored typed expansion | 35/44 (80%) | – | 0.709 | 31 | 36 | 2 | 782 / 1371 | **pass** (vs E5-1) | +2 G-029 G-030 / −0 |

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
| E5-1r | variant: redirect drops applied history (earlier prototype's rule) | 33/44 (75%) | – | 0.694 | 29 | 35 | 0 | 779 / 1371 |
| E5-2r | variant: E5-2 with the dropping redirect | 35/44 (80%) | – | 0.710 | 31 | 36 | 0 | 769 / 1371 |
| EpiB | epilogue: RRF-merge neighbours (k=60, w=0.5) instead of anchored expansion | 29/44 (66%) | – | 0.399 | 22 | 33 | 2 | 712 / 1371 |
| H1 | S3 + redirect + dense RRF (no reranker) | 35/44 (80%) | – | 0.723 | 31 | 33 | 0 | 544 / 1216 |
| H2 | H1 + anchored typed expansion (no reranker) | 36/44 (82%) | – | 0.731 | 33 | 35 | 0 | 539 / 1216 |
| A | naive 800-token chunks, dense only | 15/44 (34%) | 17 | 0.269 | 13 | 22 | 3 | 2775 / 3177 |
| B | naive 800-token chunks, BM25 only | 16/44 (36%) | 17 | 0.268 | 13 | 26 | 4 | 2793 / 3170 |
| C | element units, dense only | 27/44 (61%) | – | 0.394 | 23 | 32 | 2 | 521 / 1164 |
| D | element units, dense + id lookup + lifecycle | 32/44 (73%) | – | 0.565 | 29 | 35 | 1 | 545 / 1333 |
| E | hybrid without lifecycle filter (S4 minus step 3) | 35/44 (80%) | – | 0.665 | 31 | 33 | 3 | 540 / 1216 |
| F1 | hybrid without id lookup (S4 minus step 2) | 32/44 (73%) | – | 0.643 | 28 | 32 | 1 | 540 / 1216 |
| F2 | naive chunks, BM25 + dense RRF (no id lookup, no lifecycle) | 18/44 (41%) | 19 | 0.289 | 16 | 29 | 4 | 2814 / 3181 |
| F3 | element units, BM25 + dense RRF (no id lookup, no lifecycle) | 32/44 (73%) | – | 0.616 | 28 | 32 | 3 | 534 / 1216 |
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
| S4 | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 6 · 2 · 3 | 8 · 8 · 8 | 1 |
| S5 | 8 · 8 · 10 | 4 · 4 · 6 | 8 · 8 · 8 | 5 · 1 · 3 | 8 · 8 · 8 | 3 |
| E5-1 | 8 · 8 · 10 | 4 · 4 · 6 | 8 · 8 · 8 | 5 · 1 · 3 | 8 · 8 · 8 | 2 |
| E5-2 | 8 · 8 · 10 | 4 · 4 · 6 | 8 · 8 · 8 | 7 · 3 · 4 | 8 · 8 · 8 | 2 |
| E5-1r | 8 · 8 · 10 | 4 · 4 · 6 | 8 · 8 · 8 | 5 · 1 · 3 | 8 · 8 · 8 | 0 |
| E5-2r | 8 · 8 · 10 | 4 · 4 · 6 | 8 · 8 · 8 | 7 · 3 · 4 | 8 · 8 · 8 | 0 |
| EpiB | 6 · 6 · 8 | 3 · 3 · 6 | 5 · 5 · 8 | 8 · 1 · 3 | 7 · 7 · 8 | 2 |
| X1 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 8 · 8 · 8 | 0 |
| X2 | 9 · 9 · 9 | 2 · 2 · 4 | 8 · 8 · 8 | 8 · 3 · 4 | 8 · 8 · 8 | 0 |
| H1 | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 6 · 2 · 3 | 8 · 8 · 8 | 0 |
| H2 | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 7 · 4 · 5 | 8 · 8 · 8 | 0 |
| A | 5 · 5 · 8 | 4 · 4 · 7 | 1 · 1 · 3 | 3 · 1 · 2 | 2 · 2 · 2 | 3 |
| B | 8 · 8 · 9 | 3 · 3 · 4 | 0 · 0 · 4 | 3 · 0 · 4 | 2 · 2 · 5 | 4 |
| C | 6 · 6 · 9 | 6 · 5 · 7 | 3 · 3 · 5 | 5 · 2 · 3 | 7 · 7 · 8 | 2 |
| D | 6 · 6 · 9 | 6 · 5 · 7 | 8 · 8 · 8 | 4 · 2 · 3 | 8 · 8 · 8 | 1 |
| E | 9 · 9 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 6 · 2 · 3 | 8 · 8 · 8 | 3 |
| F1 | 9 · 9 · 10 | 4 · 4 · 4 | 5 · 5 · 7 | 6 · 2 · 3 | 8 · 8 · 8 | 1 |
| F2 | 8 · 8 · 9 | 4 · 4 · 6 | 0 · 0 · 5 | 4 · 2 · 4 | 2 · 2 · 5 | 4 |
| F3 | 9 · 9 · 10 | 4 · 4 · 4 | 5 · 5 · 7 | 6 · 2 · 3 | 8 · 8 · 8 | 3 |
| F4 | 9 · 9 · 10 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 5 · 5 · 7 | 1 |
| F5 | 8 · 8 · 10 | 4 · 4 · 4 | 8 · 8 · 8 | 5 · 1 · 3 | 8 · 8 · 8 | 3 |
| F6 | 9 · 9 · 10 | 3 · 3 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 5 · 5 · 8 | 1 |
| F7 | 9 · 9 · 10 | 2 · 2 · 4 | 8 · 8 · 8 | 7 · 1 · 2 | 7 · 7 · 7 | 1 |
| EP3 | 5 · 5 · 5 | 2 · 2 · 2 | 1 · 1 · 1 | 1 · 0 · 0 | 0 · 0 · 0 | 1 |

## Checks against Episode 3 and the earlier prototype

- Naive chunks rebuilt: **2,147** (Episode 3 manifest: 2,147). Every Episode 3 "chunk N of M" total matches this splitter: 0 mismatches.
- Answerable questions with an expected element whole in some naive chunk: **38/44** (Episode 3: 38/44); expected elements whole in some chunk: 46/52.
- Episode 3's own retrieved top-4 lists, rescored by this scorer: Hit@4 9/44, Partial@4 11/44, MRR@4 0.14; single 5, paraphrase 2, identifier 1, relation 1, stale 0 (Episode 3 summary: 9, 11, 0.14; 5, 2, 1, 1, 0).
- Config A's top-4 equals Episode 3's top-4 (same chunks, same order) on **0/50** questions. With the same nomic-embed-text digest it should be at or near 50/50 (Ollama's batching can move near-ties; nomic through llama.cpp is another build of the same weights, so expect most, not all); with any other embedder it means nothing.

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
| S4 | 33 · 0.0256 · 0.0313 · 0.032 · 0.0328 | 6 · 0.0214 · 0.0234 · 0.0262 · 0.032 |
| S5 | 33 · -5.13 · 0.11 · 2.68 · 6.88 | 6 · -2.9 · -1.7 · -1.09 · 0.321 |
| E5-1 | 33 · -5.13 · 0.11 · 2.68 · 6.88 | 6 · -2.9 · -1.7 · -1.09 · 0.321 |
| E5-2 | 33 · -5.13 · 0.11 · 2.68 · 6.88 | 6 · -2.9 · -1.7 · -1.09 · 0.321 |
| E5-1r | 33 · -5.13 · 0.11 · 2.68 · 6.88 | 6 · -2.9 · -1.7 · -1.09 · 0.321 |
| E5-2r | 33 · -5.13 · 0.11 · 2.68 · 6.88 | 6 · -2.9 · -1.7 · -1.09 · 0.321 |
| EpiB | 33 · -5.13 · 0.11 · 2.68 · 6.88 | 6 · -2.9 · -1.7 · -1.09 · 0.321 |
| X1 | 33 · 13.8 · 20.4 · 27.7 · 55.1 | 6 · 11.1 · 11.7 · 15.4 · 31.1 |
| X2 | 33 · 13.8 · 20.4 · 27.7 · 55.1 | 6 · 11.1 · 11.7 · 15.4 · 31.1 |
| H1 | 33 · 0.0256 · 0.0313 · 0.032 · 0.0328 | 6 · 0.0214 · 0.0234 · 0.0262 · 0.032 |
| H2 | 33 · 0.0256 · 0.0313 · 0.032 · 0.0328 | 6 · 0.0214 · 0.0234 · 0.0262 · 0.032 |
| A | 44 · 0.506 · 0.586 · 0.633 · 0.768 | 6 · 0.509 · 0.541 · 0.604 · 0.652 |
| B | 44 · 12.2 · 17.7 · 23.5 · 44.8 | 6 · 9.09 · 9.1 · 11.5 · 21.1 |
| C | 44 · 0.483 · 0.63 · 0.678 · 0.834 | 6 · 0.507 · 0.508 · 0.592 · 0.706 |
| D | 33 · 0.483 · 0.641 · 0.681 · 0.834 | 6 · 0.507 · 0.508 · 0.59 · 0.685 |
| E | 33 · 0.0255 · 0.0313 · 0.032 · 0.0328 | 6 · 0.0208 · 0.0233 · 0.0264 · 0.032 |
| F1 | 44 · 0.0246 · 0.0312 · 0.032 · 0.0328 | 6 · 0.0214 · 0.0234 · 0.0262 · 0.032 |
| F2 | 44 · 0.0278 · 0.0317 · 0.0323 · 0.0328 | 6 · 0.0227 · 0.026 · 0.027 · 0.0323 |
| F3 | 44 · 0.0246 · 0.0312 · 0.0319 · 0.0328 | 6 · 0.0208 · 0.0233 · 0.0264 · 0.032 |
| F4 | 33 · 13.7 · 19.7 · 28.2 · 55.9 | 6 · 11.2 · 11.4 · 15.5 · 31.6 |
| F5 | 33 · -5.13 · 0.11 · 2.68 · 6.88 | 6 · -3.89 · -3.14 · -2.68 · 0.304 |
| F6 | 33 · 14 · 19.7 · 28.5 · 56.1 | 6 · 11.2 · 11.2 · 15.5 · 31.3 |
| F7 | 33 · 13.6 · 20.2 · 27.5 · 54.9 | 6 · 11.2 · 11.9 · 15.5 · 31.5 |
