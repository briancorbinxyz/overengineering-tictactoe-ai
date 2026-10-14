# Episode 3 baseline

One golden run of the naive pipeline, as the article reports it.

- `episode-3-qwen3_8b-duo-k4-summary.md`: the summary the run printed.
- `episode-3-qwen3_8b-duo-k4.jsonl`: every question in full: retrieved chunks, Beta's quotations and verdicts, Alpha's prompt, answer and verdicts.
- `labels.csv`: each of Alpha's answers labelled by a person against the reference answer and the source.

Labels: `correct`, `partly`, `wrong`, `abstained wrongly` (said "Not in the archive" to an answerable question), and for unanswerable questions `declined in own words`, `accepted false premise`, `answered beside the point`. `stale_as_current` marks answers that relied on a withdrawn or superseded record as if it were current.

The run's own checks measure provenance: whether quotations were copied and citations point at them. The labels measure whether the answer is right. Episode 7 measures automated judges against these labels.

## Labelling rule

Judge each answer against the question, not against every detail of the reference answer. The reference answer is the fact check: an answer that is right and answers what was asked is `correct`, even if it leaves out detail the reference includes. Every label in `labels.csv` was confirmed by Brian, either set by him or accepted from Claude's draft (`labelled_by` says which). Later episodes are labelled by the same rule, so their answer tables compare.
