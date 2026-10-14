---
stage: seedling
publish: false
---
# RAGs to Riches, knowledge base schema (living)

A schema for any knowledge base that wants the properties this series is establishing, one episode at a time. It is a by-product of the series, not an article. Each episode either confirms a part of it with measurements or changes it. The series' own SQLite index is the reference implementation, so the schema can't drift from what was measured.

The SQL is in `schema.sql` (core) and `extensions.sql` (optional) beside this note, and in the repository under `docs/kb-schema/`. Both run as written on SQLite 3.45. I checked them with two small examples. The first is a bitemporal one: one success criterion with four versions, where now, as of 15 August and as known on 15 August each return a different, correct version. The second is a trust one: a signed 10-K and a vendor blog, where only the 10-K reaches the official-only view, an unlabeled document gets the cautious defaults, and an invalid reliability value is rejected.

## The principles it encodes

| # | Principle | Where it lives | Proven in |
|---|---|---|---|
| 1 | **Never lose provenance** (Rule 4). Every answer traces to an exact, hashed version of a unit in a pinned snapshot | `source.snapshot`, `version.body_hash`, `quotation.version_id` | Episode 3 (quotations traced to chunks) |
| 2 | **Cite the smallest meaningful unit**, not an arbitrary chunk. Identity is separate from text | `unit` (stable identity, parent, kind) vs `version` (text) | Episode 4 (prototype: Hit@4 20% → 64% from units alone) |
| 3 | **Identifiers are first-class**: what a reader types is looked up exactly, scoped | `identifier` (case-insensitive, scoped) | Episode 4 (identifier questions 1/8 → 8/8) |
| 4 | **Keyword and meaning are both needed; fusion happens in your code** | `version_fts` (weighted fields), `embedding` (per model) | Episode 4, through the ratchet |
| 5 | **Requirements and records are different kinds of statement.** A requirement can go out of date; a record of what happened stays true | `unit.statement` (`normative` / `record`) | Bitemporal research: keeps G-006 and G-018 while filtering stale text |
| 6 | **Two times, named**: when it was in effect (valid time), and when we recorded it (knowledge time). Changes and corrections differ | `version.valid_*`, `version.recorded_*`, `valid_grade` | Time episode (valid time first; knowledge time with its own questions) |
| 7 | **Default to now, as known now; history is a deliberate mode** | `current_version` view; `answer.mode` | Episode 5 routing, time episode |
| 8 | **Links are typed, and say how they were derived**, so a reader can weigh a markup link over a guessed one | `link.type`, `link.origin`, `link.confidence` | Episode 5 (typed links fix G-029/G-030; untyped links flood) |
| 9 | **Hard boundaries filter first; everything else ranks** | `document.access` (always a pre-filter) | Graph research: graph-first only for hard boundaries |
| 10 | **Measure inside the system**: the golden set, runs and labels live next to the data, so the ratchet is a query | `question`, `expected`, `run`, `result` | Episodes 3 onward |
| 11 | **Swap models without migrating**: embeddings keyed by model and digest | `embedding (version_id, model)` | Episode 4 embedder swap |
| 12 | **Reproduce any past answer**: replay with the same snapshot and AS_KNOWN at the time it was asked | `answer.asked_at`, `answer.mode`, knowledge time | Time episode |
| 13 | **Trust is six facts, not one score**: who may see it, how bad a leak is, who stands behind it and how dependable they are, whether it binds anyone, whether it is the publisher's own text, and whether an outsider could have written it | `document.access`, `sensitivity`, `publisher`, `reliability`, `force`, `authenticity`, `trust_zone` | Trust research (v1) |
| 14 | **Each trust fact has one job.** Access is a hard pre-filter. Reliability is a soft rerank bonus, starting at weight 0 and kept only if the ratchet passes; it is also the only label shown to the model, in at most three tiers. Force and authenticity filter only when a policy demands official sources. External text is datamarked | `official_version` view, `answer.policy`, `answer_context.marked` | To measure: a trust epilogue or the Episode 7 judges |
| 15 | **Set trust from how a document arrived, never from its text**, and keep the defaults cautious (private, internal sensitivity, external zone, reliability unknown). An attacker controls what a document says, not the ingestion path it came through | adapter rules, recorded in `ingest_run.config_hash` | Trust research (v1) |
| 16 | **Know who wrote every text and which run stored it.** Model and agent writes are marked, and agents write only drafts | `ingest_run`, `version.author_kind`, `version.author` | Trust research (v1) |
| 17 | **An answer inherits the sensitivity of everything in its context**, not just what it cites, and the full context is logged | `answer.sensitivity`, `answer_context` | Trust research (v1) |

## The tables, in plain words

- **Where it comes from.** `source` is one corpus at one pinned snapshot. `document` is one file or page in it, with its access level.
- **What is known.** `unit` is the thing you cite: a requirement, a decision, a section, a note paragraph. `version` is one text of that unit, with both time axes and a lifecycle. `identifier` lists the ids a reader might type.
- **How to find it.** `version_fts` holds keywords with weighted fields. `embedding` holds one vector per version per model.
- **How it connects.** `link` records typed links, each with how it was derived.
- **What was said.** `answer` and `quotation`: every quotation points at an exact version.
- **How far to trust it.** Six columns on `document`, set by the adapter. `ingest_run` records which adapter and configuration wrote each version.
- **How we know it works.** `question`, `expected`, `run` and `result`: the golden set, with core answers, held-out flags and per-run labels. The ratchet becomes a comparison of two runs.

## Retrieval modes

| Mode | Returns | Default? |
|---|---|---|
| CURRENT | Requirements and decisions in effect now, plus records of applied changes, as known now | Yes |
| HISTORY | Every version of the matched units and their linked versions, labeled, in time order | When the question asks about history |
| AS_OF (t) | What was in effect at t, as known now | When a date or version is asked for |
| CHANGE | Pairs of consecutive versions, with what changed and when | "What changed", "since when" |
| AS_KNOWN (t) | What the knowledge base said at t | Audit and replaying past answers |

CURRENT is a view. The others are parameterised queries in the retriever, because SQLite views take no parameters. Every mode filters before it ranks: the time test sits in the WHERE clause, so the top results come only from rows that pass it.

## Design choices worth knowing

- **Text belongs to versions, not units.** That one choice makes time, corrections and model swaps additive rather than migrations.
- **Default tokenizer on purpose.** With `tokenchars '-'`, "file" no longer matches "40-file". I found this while checking the schema. On the golden set the two settings come out within one question of each other (Hit@4 32/44 against 31/44 in the keyword prototype). Ids still match as phrases, and exact lookup goes through `identifier`. The Episode 4 plan should fix this choice before its first ratchet run.
- **Vectors are plain float32 BLOBs.** An exact Java scan handles tens of thousands of them. sqlite-vec can read the same column later without conversion.
- **Dates are UTC.** The spectastic tool stamps dates in UTC, and comparing local days makes 5.8% of its changelog look future-dated.
- **`valid_grade` says how good a date is**: from the element itself, from its change, from its page, or unknown. In spectastic only 9% of live elements carry their own date. The schema shouldn't pretend otherwise.

## Is it generic? The test is a second corpus

A schema fitted to one corpus is just that corpus's schema. The proof is a second, very different source going through an adapter, with no change to the tables. The natural candidate is your notes vault (Obsidian Markdown):

| Schema | spectastic HTML | Notes vault (Markdown) |
|---|---|---|
| unit / anchor | `<spec-requirement id>`, `<section id>` | heading, `^block-id` |
| statement | requirement/decision → normative; proposal, changelog, triage → record | evergreen note → normative; daily note, meeting log → record |
| identifier | FR-001, D-002 (scoped by spec) | aliases, tags, ticket or ticker ids |
| link | `validates`, `defer-to`, `<spec-delta target>` | `[[wikilinks]]` (untyped), frontmatter fields (typed) |
| valid time | applied dates, Created | frontmatter dates, daily-note date |
| knowledge time | git commits | file history, or git if the vault is versioned |
| lifecycle | `spec-status`, `data-status`, `changes/withdrawn` | `status:` frontmatter, an archive folder |

If the vault fits without new columns, the schema is generic. If it needs one, that's the change to make, and the place it comes from is worth a paragraph. The same test would apply to the RMS research documents later.

## Optional extensions (`extensions.sql`)

Adopt each one only when an episode or a deployment measures the need:
- **Trust administration:** `access_grant` (who holds each access value) and `assessment` (who rated each trust fact, how and why, for dated, attributed opinions such as an outlet rating).
- **Detail:** `facet`, for domain detail that stays out of core, such as SEC filed vs furnished, audited vs unaudited, or a TLP color.
- **Retrieval aids:** `derived` (summaries, contextual headers, translations; never a quotation target) and `version_dup` (near-duplicate clusters, collapsed before the top k, because a repeated low-trust claim beats an official one in every model tested).
- **Meaning:** `entity`, `mention`, `claim` and `evidence`, with corroboration computed as distinct primary sources rather than stored.
- **Feedback,** used to propose golden-set candidates, not to boost ranking.
- **Governance pack:** data subjects, retention classes, legal holds, and erasure as a tombstone (body emptied, hash and audit kept).

## Open questions

- **Chunk parts of very long units.** `part` handles splitting, but quotations may span parts. Option: match against the joined unit text.
- **Model-extracted links** (`origin = 'model'`). Worth storing only if an episode measures them against markup links.
- **Contentless FTS** saves space but can't return text, so the retriever joins back to `version`. Fine at this size; check at a million versions.
- **Access control** is one column now. A real deployment needs groups. Keep it a pre-filter either way.

## Changelog

- 14 Oct 2026: v0, from Episodes 3–5 planning, the graph-order research and the bitemporal research.
- 14 Oct 2026: v1. Six trust facts on `document`, ingestion runs, authorship, language, format and locator, identifier scheme, the answer's full context and sensitivity, trust and attack strata in evaluation, and the `official_version` view. Extensions split into `extensions.sql`. From the source-trust research.
