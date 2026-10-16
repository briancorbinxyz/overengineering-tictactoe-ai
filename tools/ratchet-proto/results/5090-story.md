# Does the story hold?

## 5090-nomic: llamacpp:nomic-embed-text-v1.5-f16 + llamacpp:bge-reranker-v2-m3-fp16

| | claim | this run | Mac (nomic + MiniLM) |
|---|---|---|---|
| holds | harness: nomic config A ≈ 9/44 with Episode 3's top 4 | A 9/44, top 4 = Episode 3's on 48/50 | 9/44, 50/50 |
| holds | units beat naive chunks under BM25 (S1 > B) | S1 30 vs B 16 | 30 vs 16 |
| holds | units beat naive chunks under dense (C > A) | C 25 vs A 9 | 25 vs 9 |
| holds | BM25 line: S1 ≤ S2 ≤ S3, lifecycle cuts stale@4 | S1 30, S2 32, S3 32; stale@4 3→1 | 30, 32, 32; 3→1 |
| holds | id lookup needed for identifiers under hybrid (F1 < S4) | identifier without id lookup 5/8 vs with 8/8 | 5/8 without |
| holds | dense (S4) lifts paraphrase over S3 | paraphrase 2→4; Hit@4 32→34 | 2→4; 32→34 |
| holds | S4 fails the ratchet on relation | fails: relation 7→5 | relation 7→5 |
| holds | reranker (S5) fails the ratchet vs S4 | fails: all@4 31→30; stale@4 0→3; S5 34 vs S4 34, all@4 30 vs 31, stale@4 3 vs 0 | 33 vs 34, all@4 28 vs 31, stale 2 |
| holds | X2 ≥ X1 ≥ S3, both pass (Episode 5 on BM25) | S3 32, X1 34, X2 35; relation X2 8/8; ratchet pass, pass | 32, 34, 35; relation 8/8 |
| holds | H2 vs X2: paraphrase up, relation down, fails | Hit@4 35 vs 35, all@4 33 vs 30, paraphrase 4 vs 2, relation 6 vs 8; ratchet FAIL: relation 8→6 | 35 vs 35, para 4 vs 2, rel 6 vs 8 |
| **BREAKS** | reranker top-1 separates unanswerable (S5) | 5/6 unanswerable below the answerable p25 (0.106); unanswerable max 0.301 | 6/6 below p25 |

## 5090-qwen3-emb-4b: llamacpp:qwen3-embedding-4b-q8_0 + llamacpp:bge-reranker-v2-m3-fp16

| | claim | this run | Mac (nomic + MiniLM) |
|---|---|---|---|
| n/a | harness: nomic config A ≈ 9/44 with Episode 3's top 4 | A 15/44, top 4 = Episode 3's on 0/50 (only meaningful for nomic) | 9/44, 50/50 |
| holds | units beat naive chunks under BM25 (S1 > B) | S1 30 vs B 16 | 30 vs 16 |
| holds | units beat naive chunks under dense (C > A) | C 27 vs A 15 | 25 vs 9 |
| holds | BM25 line: S1 ≤ S2 ≤ S3, lifecycle cuts stale@4 | S1 30, S2 32, S3 32; stale@4 3→1 | 30, 32, 32; 3→1 |
| holds | id lookup needed for identifiers under hybrid (F1 < S4) | identifier without id lookup 5/8 vs with 8/8 | 5/8 without |
| holds | dense (S4) lifts paraphrase over S3 | paraphrase 2→4; Hit@4 32→35 | 2→4; 32→34 |
| **BREAKS** | S4 fails the ratchet on relation | passes | relation 7→5 |
| holds | reranker (S5) fails the ratchet vs S4 | fails: Hit@4 35→33; all@4 31→29; stale@4 1→3; S5 33 vs S4 35, all@4 29 vs 31, stale@4 3 vs 1 | 33 vs 34, all@4 28 vs 31, stale 2 |
| holds | X2 ≥ X1 ≥ S3, both pass (Episode 5 on BM25) | S3 32, X1 34, X2 35; relation X2 8/8; ratchet pass, pass | 32, 34, 35; relation 8/8 |
| **BREAKS** | H2 vs X2: paraphrase up, relation down, fails | Hit@4 36 vs 35, all@4 33 vs 30, paraphrase 4 vs 2, relation 7 vs 8; ratchet pass | 35 vs 35, para 4 vs 2, rel 6 vs 8 |
| **BREAKS** | reranker top-1 separates unanswerable (S5) | 5/6 unanswerable below the answerable p25 (0.11); unanswerable max 0.321 | 6/6 below p25 |

## 5090-qwen3-emb-8b: llamacpp:qwen3-embedding-8b-q8_0 + llamacpp:bge-reranker-v2-m3-fp16

| | claim | this run | Mac (nomic + MiniLM) |
|---|---|---|---|
| n/a | harness: nomic config A ≈ 9/44 with Episode 3's top 4 | A 16/44, top 4 = Episode 3's on 1/50 (only meaningful for nomic) | 9/44, 50/50 |
| holds | units beat naive chunks under BM25 (S1 > B) | S1 30 vs B 16 | 30 vs 16 |
| holds | units beat naive chunks under dense (C > A) | C 24 vs A 16 | 25 vs 9 |
| holds | BM25 line: S1 ≤ S2 ≤ S3, lifecycle cuts stale@4 | S1 30, S2 32, S3 32; stale@4 3→1 | 30, 32, 32; 3→1 |
| holds | id lookup needed for identifiers under hybrid (F1 < S4) | identifier without id lookup 5/8 vs with 8/8 | 5/8 without |
| holds | dense (S4) lifts paraphrase over S3 | paraphrase 2→4; Hit@4 32→35 | 2→4; 32→34 |
| holds | S4 fails the ratchet on relation | fails: relation 7→5 | relation 7→5 |
| holds | reranker (S5) fails the ratchet vs S4 | fails: Hit@4 35→33; all@4 32→29; single-fact 10→8; stale@4 1→3; S5 33 vs S4 35, all@4 29 vs 32, stale@4 3 vs 1 | 33 vs 34, all@4 28 vs 31, stale 2 |
| holds | X2 ≥ X1 ≥ S3, both pass (Episode 5 on BM25) | S3 32, X1 34, X2 35; relation X2 8/8; ratchet pass, pass | 32, 34, 35; relation 8/8 |
| holds | H2 vs X2: paraphrase up, relation down, fails | Hit@4 36 vs 35, all@4 34 vs 30, paraphrase 4 vs 2, relation 6 vs 8; ratchet FAIL: relation 8→6 | 35 vs 35, para 4 vs 2, rel 6 vs 8 |
| **BREAKS** | reranker top-1 separates unanswerable (S5) | 5/6 unanswerable below the answerable p25 (-0.0416); unanswerable max 0.306 | 6/6 below p25 |

## 5090-qwen3-emb-8b-qwen3-rr: llamacpp:qwen3-embedding-8b-q8_0 + llamacpp:qwen3-reranker-8b-q8_0

| | claim | this run | Mac (nomic + MiniLM) |
|---|---|---|---|
| n/a | harness: nomic config A ≈ 9/44 with Episode 3's top 4 | A 16/44, top 4 = Episode 3's on 1/50 (only meaningful for nomic) | 9/44, 50/50 |
| holds | units beat naive chunks under BM25 (S1 > B) | S1 30 vs B 16 | 30 vs 16 |
| holds | units beat naive chunks under dense (C > A) | C 24 vs A 16 | 25 vs 9 |
| holds | BM25 line: S1 ≤ S2 ≤ S3, lifecycle cuts stale@4 | S1 30, S2 32, S3 32; stale@4 3→1 | 30, 32, 32; 3→1 |
| holds | id lookup needed for identifiers under hybrid (F1 < S4) | identifier without id lookup 5/8 vs with 8/8 | 5/8 without |
| holds | dense (S4) lifts paraphrase over S3 | paraphrase 2→4; Hit@4 32→35 | 2→4; 32→34 |
| holds | S4 fails the ratchet on relation | fails: relation 7→5 | relation 7→5 |
| **BREAKS** | reranker (S5) fails the ratchet vs S4 | passes; S5 39 vs S4 35, all@4 36 vs 32, stale@4 1 vs 1 | 33 vs 34, all@4 28 vs 31, stale 2 |
| holds | X2 ≥ X1 ≥ S3, both pass (Episode 5 on BM25) | S3 32, X1 34, X2 35; relation X2 8/8; ratchet pass, pass | 32, 34, 35; relation 8/8 |
| holds | H2 vs X2: paraphrase up, relation down, fails | Hit@4 36 vs 35, all@4 34 vs 30, paraphrase 4 vs 2, relation 6 vs 8; ratchet FAIL: relation 8→6 | 35 vs 35, para 4 vs 2, rel 6 vs 8 |
| holds | reranker top-1 separates unanswerable (S5) | 6/6 unanswerable below the answerable p25 (0.994); unanswerable max 0.867 | 6/6 below p25 |

## Claims at a glance

| claim | 5090-nomic | 5090-qwen3-emb-4b | 5090-qwen3-emb-8b | 5090-qwen3-emb-8b-qwen3-rr |
|---|---|---|---|---|
| harness: nomic config A ≈ 9/44 with Episode 3's top 4 | holds | n/a | n/a | n/a |
| units beat naive chunks under BM25 (S1 > B) | holds | holds | holds | holds |
| units beat naive chunks under dense (C > A) | holds | holds | holds | holds |
| BM25 line: S1 ≤ S2 ≤ S3, lifecycle cuts stale@4 | holds | holds | holds | holds |
| id lookup needed for identifiers under hybrid (F1 < S4) | holds | holds | holds | holds |
| dense (S4) lifts paraphrase over S3 | holds | holds | holds | holds |
| S4 fails the ratchet on relation | holds | BREAKS | holds | holds |
| reranker (S5) fails the ratchet vs S4 | holds | holds | holds | BREAKS |
| X2 ≥ X1 ≥ S3, both pass (Episode 5 on BM25) | holds | holds | holds | holds |
| H2 vs X2: paraphrase up, relation down, fails | holds | BREAKS | holds | holds |
| reranker top-1 separates unanswerable (S5) | BREAKS | BREAKS | BREAKS | holds |

## Main configurations side by side

each cell: Hit@4 · all@4 · paraphrase Hit@4 (of 10) · relation Hit@4 (of 8) · stale@4

| config | 5090-nomic | 5090-qwen3-emb-4b | 5090-qwen3-emb-8b | 5090-qwen3-emb-8b-qwen3-rr |
|---|---|---|---|---|
| A | 9 · 8 · 2 · 1 · 1 | 15 · 13 · 4 · 3 · 3 | 16 · 13 · 6 · 3 · 4 | 16 · 13 · 6 · 3 · 4 |
| B | 16 · 13 · 3 · 3 · 4 | 16 · 13 · 3 · 3 · 4 | 16 · 13 · 3 · 3 · 4 | 16 · 13 · 3 · 3 · 4 |
| C | 25 · 23 · 4 · 4 · 1 | 27 · 23 · 6 · 5 · 2 | 24 · 23 · 5 · 3 · 4 | 24 · 23 · 5 · 3 · 4 |
| S1 | 30 · 24 · 2 · 7 · 3 | 30 · 24 · 2 · 7 · 3 | 30 · 24 · 2 · 7 · 3 | 30 · 24 · 2 · 7 · 3 |
| S2 | 32 · 26 · 2 · 7 · 3 | 32 · 26 · 2 · 7 · 3 | 32 · 26 · 2 · 7 · 3 | 32 · 26 · 2 · 7 · 3 |
| S3 | 32 · 26 · 2 · 7 · 1 | 32 · 26 · 2 · 7 · 1 | 32 · 26 · 2 · 7 · 1 | 32 · 26 · 2 · 7 · 1 |
| S4 | 34 · 31 · 4 · 5 · 0 | 35 · 31 · 4 · 6 · 1 | 35 · 32 · 4 · 5 · 1 | 35 · 32 · 4 · 5 · 1 |
| S5 | 34 · 30 · 5 · 5 · 3 | 33 · 29 · 4 · 5 · 3 | 33 · 29 · 4 · 5 · 3 | 39 · 36 · 10 · 4 · 1 |
| X1 | 34 · 28 · 2 · 7 · 0 | 34 · 28 · 2 · 7 · 0 | 34 · 28 · 2 · 7 · 0 | 34 · 28 · 2 · 7 · 0 |
| X2 | 35 · 30 · 2 · 8 · 0 | 35 · 30 · 2 · 8 · 0 | 35 · 30 · 2 · 8 · 0 | 35 · 30 · 2 · 8 · 0 |
| H1 | 34 · 31 · 4 · 5 · 0 | 35 · 31 · 4 · 6 · 0 | 35 · 32 · 4 · 5 · 0 | 35 · 32 · 4 · 5 · 0 |
| H2 | 35 · 33 · 4 · 6 · 0 | 36 · 33 · 4 · 7 · 0 | 36 · 34 · 4 · 6 · 0 | 36 · 34 · 4 · 6 · 0 |
| E5-1 | 34 · 30 · 5 · 5 · 2 | 33 · 29 · 4 · 5 · 2 | 33 · 29 · 4 · 5 · 2 | 39 · 36 · 10 · 4 · 1 |
| E5-2 | 36 · 32 · 5 · 7 · 2 | 35 · 31 · 4 · 7 · 2 | 35 · 31 · 4 · 7 · 2 | 41 · 38 · 10 · 6 · 1 |
| F1 | 31 · 28 · 4 · 5 · 0 | 32 · 28 · 4 · 6 · 1 | 32 · 29 · 4 · 5 · 1 | 32 · 29 · 4 · 5 · 1 |
