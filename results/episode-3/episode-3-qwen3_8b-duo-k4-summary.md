Commit c64d41c · chat qwen3:8b · embeddings nomic-embed-text:v1.5 · 627 files, 2147 chunks · ingest 4.0 min · largest chunk 1043 tokens

| Stratum | Questions | Hit@4 | Partial@4 | MRR | Alpha abstained | Stale as current |
|---|---|---|---|---|---|---|
| single-fact | 10 | 50% | 60% | 0.40 | 2 | 0 |
| paraphrase | 10 | 20% | 30% | 0.13 | 0 | 0 |
| identifier | 8 | 13% | 13% | 0.03 | 1 | 0 |
| relation | 8 | 13% | 13% | 0.06 | 0 | 0 |
| stale | 8 | 0% | 0% | 0.00 | 0 | 1 |
| unanswerable | 6 | n/a | n/a | n/a | 0 | 0 |
| all | 50 | 20% | 25% | 0.14 | 3 | 1 |

Abstained correctly on 0 of 6 unanswerable questions; abstained wrongly on 3 of 44 answerable ones.
Beta's quotations traced word for word: 84%. Alpha's claims: 92 supported, 0 contradicted, 0 unsupported, 3 unchecked.
Prompt tokens per question, mean 4064. Time per question, p50 61.1 s, p95 77.7 s.
