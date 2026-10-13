# The golden set

Fifty questions with known answers and known sources, so a change to the pipeline can be
measured instead of judged by feel. One JSON object per line in `questions.jsonl`.

| Field | Meaning |
|---|---|
| `id` | Stable id, `G-001` to `G-050` |
| `question` | What a reader would ask |
| `stratum` | `single-fact`, `paraphrase`, `identifier`, `relation`, `stale` or `unanswerable` |
| `expected` | Element addresses that answer it: `specs/<spec>/<file>.html#<element-id>`; empty when unanswerable |
| `stale` | For stale questions: the withdrawn or superseded elements that would answer it wrongly |
| `answer` | A one-line reference answer |
| `commit` | The spectastic commit it was checked against |
| `status` | `candidate` until a person has checked it against the source, then `accepted` |
| `evidence` | Up to 40 words copied from the first expected element |
| `note` | What the question tests, and anything to check before accepting it |

| Stratum | Questions | Tests |
|---|---|---|
| single-fact | 10 | The easy case: one element answers it |
| paraphrase | 10 | Meaning without the element's own words |
| identifier | 8 | An id such as FR-001, which exists in over a hundred specs, scoped by its spec |
| relation | 8 | A typed link followed: `validates`, `defer-to`, superseded-by, dependencies |
| stale | 8 | A withdrawn or superseded record that would answer it wrongly |
| unanswerable | 6 | The right answer is "Not in the archive." |

A retrieved chunk is a **hit** when it holds the expected element's text whole, and a
**partial hit** when it holds at least half of it. The set is versioned with the corpus:
when the pinned spectastic commit changes, re-check every question before comparing numbers.

All questions are candidates drafted from the source; each one needs a person's sign-off
before the first published baseline.
