---
stage: seedling
publish: false
---
# RAGs to Riches, knowledge base schema (living)

A schema for any knowledge base that wants the properties this series is establishing, one episode at a time. It is a by-product of the series, not an article. Each episode either confirms a part of it with measurements or changes it. The series' own SQLite index is the reference implementation, so the schema can't drift from what was measured.

The SQL is in `schema.sql` (core), `extensions.sql` (optional packs) and `apply.sql` (the rule step), beside this note and in the repository under `docs/kb-schema/`. They run as written on SQLite 3.45. `tests/test_schema.py` (standard library only) loads them into memory and walks five cases end to end: the ACME rumour and five golden questions, a 10-K → 8-K Item 4.02 → 10-K/A chain in every arrival order, a superseded T+1 playbook, a set of things the schema must refuse, and a rule fix against an effective-dated rule change. It writes a readable trace to `tests/acme_walkthrough_output.txt`. The YAML beside the SQL is the human-authored side: source profiles in `profiles/`, the link-type catalogue in `link-types.yaml`, and the consequence decision table in `consequences.yaml`.

## The principles it encodes

| # | Principle | Where it lives | Proven in |
|---|---|---|---|
| 1 | **Never lose provenance** (Rule 4). Every answer traces to an exact, hashed version of a unit in a pinned snapshot | `source.snapshot`, `version.body_hash`, `version.blob_sha256`, `quotation.version_id` | Episode 3 (quotations traced to chunks) |
| 2 | **Cite the smallest meaningful unit**, not an arbitrary chunk. Identity is separate from text | `unit` (stable identity, parent, kind) vs `version` (text) | Episode 4 (prototype: Hit@4 20% → 64% from units alone) |
| 3 | **Identifiers are first-class**: what a reader types is looked up exactly, scoped | `identifier` (case-insensitive, scoped, typed scheme) | Episode 4 (identifier questions 1/8 → 8/8) |
| 4 | **Keyword and meaning are both needed; fusion happens in your code** | `version_fts` (weighted fields), `embedding` (per model) | Episode 4, through the ratchet |
| 5 | **Requirements and records are different kinds of statement.** A requirement can go out of date; a record of what happened stays true | `unit.statement` (`normative` / `record`) | Bitemporal research: keeps G-006 and G-018 while filtering stale text |
| 6 | **Two times, named**: when it was in effect (valid time), and when we recorded it (knowledge time). Changes and corrections differ. The source's own clock is a third, separate column | `version.valid_*`, `version.recorded_*`, `version.published_at`, `valid_grade` | Time episode |
| 7 | **Default to now, as known now; history is a deliberate mode** | `current_version`, `current_labeled`; `answer.mode` | Episode 5 routing, time episode |
| 8 | **Links are typed, and say how they were derived**, so a reader can weigh a markup link over a guessed one | `link.type`, `link.origin`, `link.confidence`, `link.emitted_by` | Episode 5 (typed links fix G-029/G-030; untyped links flood) |
| 9 | **Hard boundaries filter first; everything else ranks** | `document.access` (always a pre-filter) | Graph research: graph-first only for hard boundaries |
| 10 | **Measure inside the system**: the golden set, runs and labels live next to the data, so the ratchet is a query | `question`, `expected`, `run`, `result` | Episodes 3 onward |
| 11 | **Swap models without migrating**: embeddings keyed by model and digest | `embedding (version_id, model)` | Episode 4 embedder swap |
| 12 | **Reproduce any past answer**: replay with the same snapshot and AS_KNOWN at the time it was asked, including the trust label the model was shown | `answer.asked_at`, `answer_context.shown_label`, the ledger's knowledge time | Time episode; v2 test (ACME at 09:00 and 10:00) |
| 13 | **Trust is six facts, not one score**: who may see it, how bad a leak is, who stands behind it and how dependable they are, whether it binds anyone, whether it is the publisher's own text, and whether an outsider could have written it | `document.access`, `sensitivity`, `publisher`, `reliability`, `force`, `authenticity`, `trust_zone` | Trust research (v1) |
| 14 | **Each trust fact has one job.** Access is a hard pre-filter. Reliability is a soft rerank bonus, starting at weight 0 and kept only if the ratchet passes. Force and authenticity filter only when a policy demands official sources. External text is datamarked | `official_version` view, `answer.policy`, `answer_context.marked` | To measure: a trust epilogue or the Episode 7 judges |
| 15 | **Set trust from how a document arrived, never from its text**, and keep the defaults cautious. An attacker controls what a document says, not the ingestion path it came through | source profiles, `ingest_run.profile_sha256` | Trust research (v1) |
| 16 | **Know who wrote every text and which run stored it.** Model and agent writes are marked, and agents write only drafts | `ingest_run`, `version.author_kind`, `version.author` | Trust research (v1) |
| 17 | **An answer inherits the sensitivity of everything in its context**, not just what it cites, and the full context is logged | `answer.sensitivity`, `answer_context` | Trust research (v1) |
| 18 | **Text changes make versions; judgment changes make assessments.** Promotions and demotions are new dated rows that point at unchanged text, never edits | `assessment` (append-only, bitemporal) | Ingester research; v2 test (4.02, playbook, ACME) |
| 19 | **Status is computed per query, never stored**, and it decides membership before top-k, not a soft score | `status_now`, `current_labeled.supports` | v2 test; HoH and retracted-article evidence in the ingester report |
| 20 | **Labels may come from anyone; exclusions only from the publisher itself, official markup or an accountable person.** Model, third-party and heuristic demotions are provisional. Promotions need a checker who is not the maker | `assessment` CHECKs and triggers, `authority_kind` | v2 negative tests |
| 21 | **Relationship rules are data in three layers**: what a relation means, how a source reveals it, and what it does to status. Every derived row cites the rule version and premises that made it | `link_type`, `profiles/*.yaml`, `rule_version`, `justification` | v2 test (rule fix vs new version) |
| 22 | **Derivations are order-independent and idempotent**: every derived time is a function of input times, and re-running adds nothing | `apply.sql`, `derivation_key` | v2 test (all 6 arrival orders identical) |

## The tables, in plain words

**Core (`schema.sql`)**

- **Where it comes from.** `source` is one corpus at one pinned snapshot. `ingest_run` is one run over it, with the hashes of the code, the source profile and the fetch manifest it used. `blob` keeps the raw bytes and parser output, write-once, addressed by SHA-256. `document` is one file, filing, message or note, with its access level and its six trust facts as ingest-time defaults.
- **What is known.** `unit` is the thing you cite: a requirement, a 10-K Item, a message. `version` is one text of that unit, with valid time, knowledge time, the source's own publication time and a lifecycle the publisher declared. `identifier` lists the ids a reader or a link might use, including typed composite keys such as `edgar:cik+form+period` = `2098|10-K|2025-12-31`.
- **How to find it.** `version_fts` holds keywords with weighted fields. `embedding` holds one vector per version per model.
- **How it connects.** `link` is a typed relation from a unit to a unit, a document or a key not yet resolved, with how it was found, by which rule, when it holds and when we learned it. Links are never edited; a wrong one is withdrawn by closing `recorded_to` once.
- **How far to trust it, over time.** `assessment` is the status ledger: every trust or status judgment about a document, unit, version, link, claim or mention, as an append-only row with valid time, knowledge time, direction, authority, evidence and maker/checker. `authority_kind` says who may exclude. `status_value` is the vocabulary and says what each value does to retrieval. `clock` freezes "now".
- **What was said.** `answer`, `answer_context` (everything the model saw, with the literal label it was shown) and `quotation`.
- **How we know it works.** `question`, `expected`, `run` and `result`: the golden set and per-run labels.

**Extensions (`extensions.sql`)**

- **Meaning.** `entity` (real, fictional or synthetic), `entity_identifier` (CIK, LEI, ticker with validity; empty by design for a fictional entity), `alias` (builds candidate sets), `entity_link` (brand of, depicted in), `mention` and `mention_candidate` (an ambiguous "ACME" keeps all its candidates), `claim` (with modality: asserted, hedged, in-universe) and `evidence`.
- **Relationship rules.** `key_scheme`, `link_type`, `rule_version`, `link_resolution`, `justification`, and the views that derive status (below).
- **Operations.** `work_item` (the per-document state machine and the analysts' inbox; the kanban board is a `GROUP BY`), `answer_recheck` (answers whose context was later demoted), `derived` and `derived_input` (model-made retrieval aids and their inputs), `version_dup`, `facet`, `access_grant`, `feedback`.
- **Governance pack:** data subjects, retention classes, legal holds, and erasure as a tombstone.

## Three clocks, and which one `recorded_from` is

`valid_from`/`valid_to` say when something holds in the world. `recorded_from`/`recorded_to` say when **this knowledge base** recorded it: knowledge time, exactly as v1.1 defined it. v2 adds `version.published_at` for the source's own time (EDGAR acceptance, an email's `Date:`, a Federal Register publication date). Research had flagged that order-independent derivation might need the KB's insert time and the source time kept apart. Keeping `recorded_from` as the KB's own clock and putting the source's clock in its own column does that. AS_KNOWN means what this store said, the resolver can still ask "was this filing published before that 8-K?", and a backfilled filing is known from the day it arrived, not from its acceptance date. In the synthetic layer the KB's recorded time is the archive's delivery time (the `Date:` plus a little jitter).

## The status ledger

A judgment is a row; it is never an edit. A 10-K that its issuer later says not to rely on keeps its text and its versions. The 8-K adds a `standing = do_not_rely` row on it, valid from the 10-K's own period ("the figures were never reliable") and recorded when the 8-K arrived ("we learned it then"). A row can supersede an earlier row. A row with the reserved value `void` only cancels the row it supersedes, which is how a rule's derivation is withdrawn without deleting anything.

The effective status (`status_now`) is computed under the frozen clock. A row counts if it was recorded by `now_recorded`, is valid at `now_valid` and has not been superseded by a row recorded by then. Provisional rows never decide: they become `flags`, labels shown beside the decision. Among decided rows, exclusions beat labels, then the most specific valid time, then authority, then severity, then recency. To lift a stricter value (a promotion, an undo), supersede it. **AS_KNOWN(t)** is the same views after `UPDATE clock SET now_recorded = t, now_valid = t`.

The rules sit in the table definition and its triggers, not in application code:

- Rows are insert-only. Trust columns on `document` are frozen after insert (except `access`, which is always enforced at its current value, even in replays) and mirrored as `direction = 'initial'` rows.
- A promotion needs `method = 'human'` and a maker (`proposed_by`) who is not the checker (`rated_by`). No rule, model or source promotes.
- A demotion by a model, a third party or a heuristic must be provisional.
- An **exclusion** (a value with `supports = 'no'` or `official = 0`) needs publisher, markup or human authority; ingest-time defaults from a curated profile are the only other way in.
- `authority = 'publisher'` must be true: the evidence must come from the target's own publisher.

## Relationship rules in three layers

| Layer | What it decides | Lives in | Versioned by |
|---|---|---|---|
| 1. Relation semantics | What each link type means: inverse, scope, which end receives the effect, the default effect, where the derived valid time comes from, who may exclude, nearest standard names | `link_type` table, seeded from `link-types.yaml` (frozen rows) | the seed; effects change only through layer 3 |
| 2. Detection | How a source reveals relations: "this 8-K Item 4.02 names Form 10-K for the year ended 31 Dec 2025" becomes a `do-not-rely` link with a typed key, an origin and a confidence | `profiles/*.yaml` (CEL predicates, JSONPath/XPath field maps, Java beans for hard parsers) | `ingest_run.profile_sha256`; `link.emitted_by` names the rule |
| 2b. Resolution | Which unit or document a key names, as of when. Exactly one candidate published before the linking document binds it; two candidates bind nothing and become an inbox item | `link_resolution` (append-only), `desired_link_resolution` view | the `resolve-key` rule version |
| 3. Consequence | What a link does to status, by emitter authority, origin and confidence: apply, label (provisional) or nothing | `rule_version` bodies compiled from `consequences.yaml`, evaluated by the `derive_link_effect` and `derive_resolves` views | `rule_version` (sha256 of the body) |

`apply.sql` is the only writer for layers 2b and 3. It binds keys, appends the rows the derive views say are missing, records each row's premises in `justification`, and appends `void` rows for derivations whose premises stopped holding. Each derived row carries a knowledge-time window: it starts when its last premise became known and ends when a link is withdrawn, a binding is superseded, its rule version is fixed, or a later effective-dated version covers its whole valid period. Re-running adds nothing (`derivation_key`). Arrival order doesn't matter either: the test ingests the 10-K, 8-K and 10-K/A in all six orders and gets the same ledger.

**Two kinds of rule change.** A **fix** (`change_kind = 'fix'`) says our interpretation was wrong. From its adoption it replaces the version it fixes over that version's whole valid range, and AS_KNOWN before the adoption is unchanged. A **new** version (`change_kind = 'new'`, with `effective_from`) says the world's rule changed from a date. Derivations for earlier valid times are left exactly as they were. A source rule (an owned, expiring policy such as "EDGAR filings with an accession number are original") is a `rule_version` of kind `source_rule` with a required `review_by`; when it expires it returns as one renewal item (`source_rule_due`), not as N documents.

## Link types

| Type | Effect on its target | Valid from | Who may exclude | Interop (nearest) |
|---|---|---|---|---|
| `amends` | label `amended` | the link | publisher, markup, human | `eli:amends`, `cito:updates` |
| `corrects` | label `corrected`; an email "correction" acts on claims only | the link | publisher, markup, human | `eli:corrects`, `cito:corrects`, Crossmark correction |
| `supersedes` | `superseded` on the older item | the link (adoption) | publisher, markup, human | `dcterms:replaces` |
| `superseded-by` (v1) | `superseded` on its own (from) end | the link | publisher, markup, human | `dcterms:isReplacedBy` |
| `do-not-rely` | `do_not_rely` (8-K Item 4.02) | the target's own period | publisher only | `prov:wasInvalidatedBy` (closest) |
| `restates` | `restated` (closes the do-not-rely window) | the target's own period | publisher only | `prov:wasRevisionOf` |
| `repeals` | `repealed` | the link | publisher, markup, human | `eli:repeals` |
| `resolves` | claim and mention level: world, verification, resolution | none (epistemic) | human only | — |
| `consolidates`, `refers-to` (v1), `replies-to`, `same-thread-candidate`, `quotes`, `duplicates`, `cites` (v1), `validates` (v1), `defers-to` (v1), `parent` (v1), `revises` (v1) | none: navigation and ranking only | — | — | `eli:consolidates`, `dcterms:references`, `cito:repliesTo`, `cito:includesQuotationFrom`, `cito:cites`, `dcterms:isPartOf`, `dcterms:isVersionOf` |

No type is transitive for status. If A is superseded by B and B by C, A's status comes from its own link; reversing B's supersession can't leave A stranded. Chains are followed at query time with a cycle-safe recursive CTE (`supersession_head`). Thread order is never supersession: a later email in a thread is `replies-to`, and a subject-only match is only a `same-thread-candidate` with no status effect. A Slack or Teams edit is a new **version** of the same unit (the old one's knowledge period closes), not a link.

## Retrieval modes, with status

| Mode | Returns | Default? |
|---|---|---|
| CURRENT | Requirements and decisions in effect now, plus records, as known now, each with its effective status and label (`current_labeled`) | Yes |
| OFFICIAL | CURRENT minus anything whose effective force, authenticity, standing or register says "not official" | Official-only policies |
| HISTORY | Every version of the matched units and their linked versions, labelled, in time order | When the question asks about history |
| AS_OF (t) | What was in effect at t, as known now; later status changes appear as labels ("later superseded, 15 Feb 2023") | When a date or version is asked for |
| CHANGE | Pairs of consecutive versions, with what changed and when | "What changed", "since when" |
| AS_KNOWN (t) | What the knowledge base said at t, including the labels it would have shown | Audit and replaying past answers |

What status does to membership, applied before top-k in both hybrid legs:

| Effective status | CURRENT | OFFICIAL | HISTORY / AS_OF / AS_KNOWN |
|---|---|---|---|
| `in_force`, `factual`, `real` | supports | in | in |
| `do_not_rely` | supports, labelled; append the notice | out | in, labelled, both dates |
| `corrected`, `amended`, `concern`, `at_risk` | supports, labelled | in | in, labelled |
| `superseded`, `restated`, `repealed`, `withdrawn`, `retracted` | never supports; shown only if the question names the item | out | in, labelled |
| non-factual register, non-real world | never supports a real-world claim; may explain (the film's plot) | out | in, labelled with the world |
| any provisional row | a label only ("flagged, under review"); never excludes | unchanged | in |

Claims and mentions follow the same rule (`claim_now`, `mention_now`). A claim supports a real-world answer only if its subject is a resolved real entity, its world is `real`, it is not refuted, and it is neither hedged nor in-universe. That is why "Is Acme United being sued?" can never retrieve the 08:12 "I heard ACME is being sued" email: its "ACME" never resolves to ACU.

## The ACME walkthrough, in brief

At 08:12 −04:00 an analyst at the fictional Tallowmere Asset Management emails "I heard ACME is being sued". The mention is stored as `ambiguous:4` with its four candidates (Acme United, Acme Markets, the fictional Acme Corporation, Acme Packet), and the hedged claim as `world = real`, `unverified`. The 09:40 reply from the same sender carries `In-Reply-To`, so the profile emits `replies-to` (markup) and, from the cue "It's the plot of", a `resolves` link (prose pattern). The consequence table makes its effects provisional: the mention resolves to the fictional Acme Corporation, the claim's world becomes the film's universe, and its real-world reading is refuted. As known at 10:00 these are labels; an analyst confirms them at 10:30. The 08:12 email's own standing never changes: it is still a true record that someone heard a rumour. A variant reply without threading headers only gets a `same-thread-candidate` link and an inbox suggestion. The five golden questions used are in the trace (`ACME-01` to `ACME-05`, plus a drafted `ACME-02b`).

## Design choices worth knowing

- **Text belongs to versions, not units.** That one choice makes time, corrections and model swaps additive rather than migrations.
- **Judgments belong to the ledger, not to versions.** An 8-K Item 4.02 is a `do_not_rely` assessment, not a withdrawal version: the issuer never edited the 10-K, a same-body version would force a re-embed and orphan quotations, and between the 8-K and the 10-K/A the honest answer ("reported X; the issuer says not to rely on it; restatement pending") needs the original figure to stay in CURRENT.
- **The ledger is core, the rule engine is an extension.** The trust columns are frozen in core, so the only way to change trust must be in core too. Link types, rule versions, resolution and derivation are a pack you adopt when you have relations worth deriving from.
- **SQL views, not a rule engine.** The consequence layer is a join (link × binding × link type × rule version), which CEL can't express and Drools expresses procedurally. Views give a declarative, order-independent result; recompute-and-append keeps the ledger honest. The decision table is written as DMN-style YAML with a FIRST hit policy and compiled to JSON rule bodies.
- **Never put status into indexed or embedded text**, including `derived` context prefixes. Status changes; text doesn't.
- **Default tokenizer on purpose.** With `tokenchars '-'`, "file" no longer matches "40-file". Ids still match as phrases, and exact lookup goes through `identifier`.
- **Vectors are plain float32 BLOBs.** An exact Java scan handles tens of thousands; sqlite-vec can read the same column later.
- **Dates are UTC.** Comparing local days made 5.8% of spectastic's changelog look future-dated. An email's `08:12 -0400` is stored as `12:12Z`.
- **`valid_grade` says how good a date is.** In spectastic only 9% of live elements carry their own date.

## Is it generic? The test is a second corpus

A schema fitted to one corpus is just that corpus's schema. The proof is a second, very different source going through an adapter with no change to the tables. The finance corpus (real filings and regulation plus a fictional private layer) is now that test, and it has already changed the schema twice: the CURRENT valid-time bug in v1.1, and the trust-replay defect and relationship rules in v2. The notes vault remains the third candidate:

| Schema | spectastic HTML | Notes vault (Markdown) | Finance corpus |
|---|---|---|---|
| unit / anchor | `<spec-requirement id>`, `<section id>` | heading, `^block-id` | 10-K Item, FR section, CSDR article, message |
| statement | requirement/decision → normative; changelog → record | evergreen note → normative; daily note → record | rule text → normative; filings, releases, email → record |
| identifier | FR-001, D-002 (scoped by spec) | aliases, tags | accession, CIK+form+period, CELEX, Message-ID |
| link | `validates`, `defers-to`, `<spec-delta target>` | wikilinks (untyped), frontmatter (typed) | `do-not-rely`, `restates`, `amends`, `supersedes`, `replies-to`, `resolves` |
| valid time | applied dates | frontmatter dates | period end, compliance or application date, `Date:` |
| knowledge time | git commits | file history | when this KB recorded it; source time in `published_at` |
| status | `spec-status`, `data-status` | `status:` frontmatter | the ledger |

## Files

| File | What it is |
|---|---|
| `schema.sql` | Core tables, the status ledger, retrieval views |
| `extensions.sql` | Optional packs: meaning, relationship rules (with the generated seed), operations, governance |
| `apply.sql` | The idempotent rule step: bind keys, append derived rows, record premises, void what stopped holding |
| `link-types.yaml` | Layer 1: the link-type catalogue (mirrors the `link_type` seed) |
| `consequences.yaml` | Layer 3: the decision table (compiled into `rule_version` bodies) |
| `profiles/*.yaml` | Layer 2: source profiles for SEC 10-K and 8-K, the Federal Register, EUR-Lex, email, Slack and research notes |
| `tests/test_schema.py` | The end-to-end test (standard library and sqlite3; uses PyYAML only for the optional YAML cross-checks) |
| `tests/acme_walkthrough_output.txt` | The trace the test writes |
| `tests/gen_seed.py` | Regenerates the seed in `extensions.sql` from the two YAML files (needs PyYAML) |

## Open questions

- **Chunk parts of very long units.** `part` handles splitting, but quotations may span parts. Option: match against the joined unit text.
- **Model-extracted links** (`origin = 'model'`) are labels by construction. Worth storing only if an episode measures them against markup links.
- **Does `verification` need valid time?** It is knowledge time only for now, an untested choice.
- **A status join on contentless FTS at a million versions.** `status_now` is a window function over the live ledger; check it at scale before relying on it, or materialise it stamped with the clock it was built for.
- **The cue phrases and the 7-day thread window** in the email profile are unvalidated; measure them on a small labelled set.
- **Back-dating.** Derived rows take the knowledge time of their last premise. That is right for live ingestion and for a first load. After answers have been logged, a backfill could change past AS_KNOWN results; the apply step should then refuse derived times earlier than the last logged answer.
- **v1 → v2 is not a migration.** v2 is DDL for a fresh file; no episode has a v1 store worth migrating yet.
- **Access control** is one column. A real deployment needs groups. Keep it a pre-filter either way.

## Changelog

- 14 Oct 2026: v0, from Episodes 3–5 planning, the graph-order research and the bitemporal research.
- 14 Oct 2026: v1. Six trust facts on `document`, ingestion runs, authorship, language, format and locator, identifier scheme, the answer's full context and sensitivity, trust and attack strata in evaluation, and the `official_version` view. Extensions split into `extensions.sql`. From the source-trust research.
- 14 Oct 2026: v1.1. Bug fix found while designing the finance corpus: CURRENT checked only `valid_to`, so a rule adopted but not yet in force (EU T+1, applicable from 11 Oct 2027) showed as current. CURRENT now checks both valid-time bounds and the knowledge-time bounds against a frozen `clock` row.
- 14 Oct 2026: **v2**, from the ingester research and the business-rules research (rule storage, official and unofficial relationships, review UX). Each change and why:
  - `assessment` rebuilt as the core status ledger (append-only, bitemporal, six targets, direction, provisional, supersedes, evidence, method, authority, rule reference, maker/checker): v1 trust labels were overwritable columns, so AS_KNOWN could not replay a label a past answer saw.
  - Promotion, demotion and exclusion rules as CHECKs and triggers, with `authority_kind`: an outsider must not be able to trigger an exclusion (an availability attack), and nobody approves their own promotion.
  - `status_value` vocabulary table: what each value does to CURRENT and OFFICIAL is data, so retrieval and the authority rules read the same source.
  - Document trust columns frozen by trigger and mirrored as `initial` rows; `document.recorded_from` and `ingest_run_id` added: defaults stay as the adapter set them, and every later change is dated and attributed.
  - Views `assessment_live`, `status_now`, `status_scope`, `document_trust_now`, `current_labeled`; `official_version` reads effective status: status decides membership before top-k and is never stored.
  - `link` gets `link_id`, `valid_from`, `recorded_from`, a once-only `recorded_to`, `emitted_by` and a typed key target (`to_key_scheme`, `to_key`), and becomes append-only: links are evidence, so they must be citable and replayable, and an 8-K Item 4.02 names its target by form and period, never by accession.
  - `version.published_at`: the source's own clock in its own column, so `recorded_from` stays this KB's knowledge time (the third-time-axis decision).
  - `blob` (write-once, content-addressed) and `version.blob_sha256`: lineage from bytes to parse to unit, and the fetch tool's URL-keyed cache could overwrite a manifest's digest.
  - `ingest_run.profile_sha256` and `manifest_sha256`: a run names the source profile and the fetch it used.
  - `answer_context.shown_label`: a replay compares the literal label the model saw.
  - `identifier.scope` is `NOT NULL DEFAULT ''`: bug fix, since a WITHOUT ROWID primary key rejects the NULL v1 used for "global", so global identifiers could not be inserted. Index on `(scheme, value)` for key resolution.
  - `version_now` index now covers `(unit_id, valid_to)` for open knowledge periods: since v1.1 CURRENT checks both valid bounds, the old partial index no longer matched the hot path.
  - `expected.role` adds `candidate`: ambiguity questions score whether every candidate was retrieved.
  - Extensions: `link_type` catalogue (19 types, frozen, v1 types kept) and `key_scheme`: relation semantics as data.
  - Extensions: `rule_version` (bitemporal; `fix` vs `new`; `source_rule` kind with owner and expiry) with the `consequence`, `rule_window` and `source_rule_due` views: a law-like change and an interpretation fix need different treatment, and every source rule needs an owner and a review date.
  - Extensions: `link_resolution` (append-only; ambiguous keys bind nothing) with the resolver views: late and out-of-order targets resolve the same whichever arrives first.
  - Extensions: `derive_link_effect`, `derive_resolves`, `desired_assessment`, `justification`, and `apply.sql`: the consequence layer as SQL views with recompute-and-append, so derivations are idempotent, order-independent and explainable.
  - Extensions: `entity` gains kind, reality and description; `entity_identifier`, `alias`, `entity_link`; `mention` gains an id, a surface and a nullable entity; `mention_candidate`; `claim` gains modality and a subject mention; `mention_now` and `claim_now`: ACME needs entities that can be fictional and mentions that stay ambiguous until evidence arrives.
  - Extensions: `work_item` (with a `review` state, quarantine reason and ranked suggestions), `answer_recheck` with the `answer_exposure` view, and `derived_input`: re-drive, an exception inbox, and recall of answers whose evidence was later demoted.
  - Extensions: `assessment_explain`, `link_pending`, `supersession_edge` and `supersession_head` views: one-sentence explanations, dangling links for the inbox, and cycle-safe chain heads.
  - The v1 `assessment` extension is removed; the core ledger replaces it. No episode had adopted it.
  - New files: `apply.sql`, `link-types.yaml`, `consequences.yaml`, seven source profiles, `tests/test_schema.py` with its trace, and `tests/gen_seed.py`.
