-- Knowledge base schema, v1 (living). Core only; optional extensions are in extensions.sql. One SQLite file per knowledge base.
-- Each table says which theme it serves and which episode proves it.
PRAGMA foreign_keys = ON;

-- ── Where knowledge comes from ────────────────────────────────────────────
-- A source is one corpus at one pinned snapshot (git commit, export date...).
CREATE TABLE source (
  source_id     INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,             -- 'spectastic', 'vault'
  adapter       TEXT NOT NULL,             -- 'spectastic-html', 'obsidian-md'
  snapshot      TEXT NOT NULL,             -- commit hash or export id (reproducibility)
  snapshot_at   TEXT NOT NULL,             -- UTC ISO-8601
  UNIQUE (name, snapshot)
);

-- Every ingestion run, so "the source changed" is distinguishable from "our parser changed".
CREATE TABLE ingest_run (
  ingest_run_id    INTEGER PRIMARY KEY,
  source_id        INTEGER NOT NULL REFERENCES source,
  adapter_version  TEXT NOT NULL,            -- 'spectastic-html@1.4.0'
  splitter_version TEXT NOT NULL,            -- unit rules; a change here changes unit identity
  config_hash      TEXT NOT NULL,            -- trust rules, PII rules, model ids, prompts
  started_at       TEXT NOT NULL,
  finished_at      TEXT,
  status           TEXT NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running','ok','failed','superseded'))
);

-- A document is one addressable file or page.
CREATE TABLE document (
  document_id   INTEGER PRIMARY KEY,
  source_id     INTEGER NOT NULL REFERENCES source,
  path          TEXT NOT NULL,             -- 'specs/040-run-budget/spec.html'
  title         TEXT,
  uri           TEXT,                      -- where it was fetched from
  scope         TEXT,                      -- grouping: spec id, folder, client...
  -- Six trust facts, each with one job. Set by the adapter from how the document
  -- arrived, never from its text. Defaults are cautious.
  access        TEXT NOT NULL DEFAULT 'private',      -- who may see it: hard pre-filter, fails closed
  sensitivity   INTEGER NOT NULL DEFAULT 1            -- how bad a leak is: 0 public .. 3 restricted
                CHECK (sensitivity BETWEEN 0 AND 3),
  publisher     TEXT,                                 -- who stands behind it
  reliability   TEXT                                  -- how dependable the publisher is; NULL = can't judge
                CHECK (reliability IN ('authoritative','reliable','unvetted','doubtful')),
                                                      -- soft rerank bonus (weight starts at 0) and the only prompt label
  force         TEXT NOT NULL DEFAULT 'none'          -- does it bind anyone?
                CHECK (force IN ('binding','official','guidance','none')),
  authenticity  TEXT NOT NULL DEFAULT 'unknown'       -- is this the text the publisher issued?
                CHECK (authenticity IN ('signed','original','copy','derived','unknown')),
  trust_zone    TEXT NOT NULL DEFAULT 'external'      -- could an outsider have written it? external text is datamarked
                CHECK (trust_zone IN ('curated','internal','external')),
  UNIQUE (source_id, path)
);
CREATE INDEX document_gate ON document (access, sensitivity, force, authenticity);

-- ── What is known: units, with identity separate from their versions ──────
-- A unit is the smallest thing worth citing: a requirement, decision, section,
-- note paragraph. Identity is stable; text lives in versions. (Episodes 3-4)
CREATE TABLE unit (
  unit_id       INTEGER PRIMARY KEY,
  document_id   INTEGER NOT NULL REFERENCES document,
  anchor        TEXT NOT NULL,             -- 'FR-001', 'requirements', '^block-id'
  part          INTEGER NOT NULL DEFAULT 1,-- long units split into parts
  parent_id     INTEGER REFERENCES unit,   -- structure: section > requirement
  kind          TEXT NOT NULL,             -- 'requirement','decision','task','section','note'...
  statement     TEXT NOT NULL CHECK (statement IN ('normative','record')),
                                           -- normative: states what is true/required;
                                           -- record: says what happened (proposal, log, changelog)
  heading_path  TEXT,                      -- 'Run budget > Requirements > FR-001'
  format        TEXT NOT NULL DEFAULT 'prose'
                CHECK (format IN ('prose','table','figure','code','math','list')),
  locator       TEXT,                      -- JSON: page, bbox, rows, cols, lines
  UNIQUE (document_id, anchor, part)
);

-- Identifiers a reader would type, scoped. Exact lookup, no full-text. (Episode 4)
CREATE TABLE identifier (
  value         TEXT NOT NULL COLLATE NOCASE,  -- 'FR-001', 'D-002', 'KB-017', ticker, ISBN
  scheme        TEXT,                          -- 'spec', 'LEI', 'FIGI', 'ISIN', 'QID'...
  scope         TEXT,                          -- '040' (spec), NULL if global
  unit_id       INTEGER NOT NULL REFERENCES unit,
  PRIMARY KEY (value, scope, unit_id)
) WITHOUT ROWID;

-- A version is one text of one unit over two time axes. (time episode)
--   valid time:     when the content was in effect      [valid_from, valid_to)
--   knowledge time: when the knowledge base recorded it [recorded_from, recorded_to)
-- A change opens a new valid period; a correction keeps valid_from and closes
-- only the recorded period. Dates are UTC.
CREATE TABLE version (
  version_id    INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES unit,
  body          TEXT NOT NULL,             -- exactly what quotations are matched against
  body_hash     TEXT NOT NULL,             -- sha-256 of body: provenance by content
  lifecycle     TEXT NOT NULL DEFAULT 'current'
                CHECK (lifecycle IN ('current','draft','applied','superseded','withdrawn','rejected','retired')),
  valid_from    TEXT,                      -- NULL = unknown (graded below)
  valid_to      TEXT,                      -- NULL = still in effect
  valid_grade   TEXT NOT NULL DEFAULT 'page',  -- 'element','change','page','none': how the date was derived
  recorded_from TEXT NOT NULL,             -- commit time it first appeared
  recorded_to   TEXT,                      -- NULL = still recorded this way
  commit_ref    TEXT,                      -- the commit that recorded it
  ingest_run_id INTEGER REFERENCES ingest_run,
  author_kind   TEXT NOT NULL DEFAULT 'human'      -- AI-written text is marked as such
                CHECK (author_kind IN ('human','tool','model','agent')),
  author        TEXT,                      -- person, agent id, or model@digest
  lang          TEXT                       -- BCP-47; picks the tokenizer
);
CREATE INDEX version_unit ON version (unit_id, valid_from, recorded_from);
-- The hot path: what is true now, as known now.
CREATE INDEX version_now ON version (unit_id) WHERE recorded_to IS NULL AND valid_to IS NULL;

-- Keyword index over current knowledge, weighted fields, ids kept whole. (Episode 4)
CREATE VIRTUAL TABLE version_fts USING fts5 (
  title, ident, body,
  content = '', contentless_delete = 1,
  tokenize = 'unicode61'
);  -- rowid = version_id; query with bm25(version_fts, 5, 10, 1).
    -- Default tokenizer on purpose: with tokenchars '-', "file" no longer matches
    -- "40-file". Ids still match as phrases ("FR-012" -> "fr" "012"), and exact
    -- lookup goes through the identifier table. Quote every user term before MATCH.

-- Vectors per version per model, so a model swap is a new row, not a migration. (Episodes 3-4)
CREATE TABLE embedding (
  version_id    INTEGER NOT NULL REFERENCES version,
  model         TEXT NOT NULL,             -- 'nomic-embed-text:v1.5@0a109f42'
  dims          INTEGER NOT NULL,
  vector        BLOB NOT NULL,             -- float32 little-endian; sqlite-vec reads it as is
  PRIMARY KEY (version_id, model)
) WITHOUT ROWID;

-- ── How knowledge connects ───────────────────────────────────────────────
-- Typed links between units, with how each was derived, so readers can weigh them. (Episode 5)
CREATE TABLE link (
  from_unit     INTEGER NOT NULL REFERENCES unit,
  to_unit       INTEGER REFERENCES unit,   -- NULL when the target is a whole document
  to_document   INTEGER REFERENCES document,
  type          TEXT NOT NULL,             -- 'validates','defers-to','cites','revises',
                                           -- 'superseded-by','parent','refers-to'
  origin        TEXT NOT NULL CHECK (origin IN ('markup','status+link','prose-pattern','model','human')),
  confidence    REAL NOT NULL DEFAULT 1.0,
  CHECK (to_unit IS NOT NULL OR to_document IS NOT NULL)
);
CREATE INDEX link_from ON link (from_unit, type);
CREATE INDEX link_to   ON link (to_unit, type);

-- ── Retrieval modes as views: the default is now, as known now ──────────
-- CURRENT: normative content in effect now, plus records of applied changes.
CREATE VIEW current_version AS
SELECT v.* FROM version v JOIN unit u USING (unit_id)
WHERE v.recorded_to IS NULL
  AND (   (u.statement = 'normative' AND v.valid_to IS NULL
           AND v.lifecycle IN ('current','draft'))
       OR (u.statement = 'record'    AND v.lifecycle IN ('current','applied')));
-- OFFICIAL: current, binding or official, and the publisher's own text. For policies
-- that allow only official sources; otherwise official is just a rerank feature.
CREATE VIEW official_version AS
SELECT v.* FROM current_version v
JOIN unit u USING (unit_id) JOIN document d USING (document_id)
WHERE d.force IN ('binding','official') AND d.authenticity IN ('signed','original');
-- HISTORY, AS_OF(:t), CHANGE and AS_KNOWN(:t) are parameterised queries in the
-- retriever (see the notes), because SQLite views take no parameters.

-- ── Answers, with their evidence (Rule 4: never lose provenance) ─────────
CREATE TABLE answer (
  answer_id     INTEGER PRIMARY KEY,
  asked_at      TEXT NOT NULL,             -- UTC; replaying needs AS_KNOWN(asked_at)
  question      TEXT NOT NULL,
  mode          TEXT NOT NULL DEFAULT 'CURRENT',  -- CURRENT, HISTORY, AS_OF, CHANGE, AS_KNOWN
  as_of         TEXT,
  model         TEXT NOT NULL,
  principal     TEXT,                      -- who asked; 'agent:x for user:y' when delegated
  policy        TEXT,                      -- JSON: filters, official-only, weights
  sensitivity   INTEGER NOT NULL DEFAULT 0,-- max over everything in its context, not just what it cites
  text          TEXT
);
CREATE TABLE answer_context (              -- every version placed in the model's context
  answer_id     INTEGER NOT NULL REFERENCES answer,
  version_id    INTEGER NOT NULL REFERENCES version,
  rank          INTEGER NOT NULL,
  marked        INTEGER NOT NULL DEFAULT 0,-- 1 = datamarked as untrusted
  PRIMARY KEY (answer_id, version_id)
) WITHOUT ROWID;
CREATE TABLE quotation (                   -- a claim's evidence, traced to an exact version
  answer_id     INTEGER NOT NULL REFERENCES answer,
  label         TEXT NOT NULL,             -- 'Q1'
  version_id    INTEGER NOT NULL REFERENCES version,
  text          TEXT NOT NULL,
  rank          INTEGER,                   -- where retrieval placed it
  PRIMARY KEY (answer_id, label)
) WITHOUT ROWID;

-- ── How we know it works: the golden set lives next to the data ──────────
CREATE TABLE question (
  question_id   TEXT PRIMARY KEY,          -- 'G-001', 'H-009'
  text          TEXT NOT NULL,
  stratum       TEXT NOT NULL,             -- single-fact, paraphrase, identifier, relation, stale, history, unanswerable...
  mode          TEXT NOT NULL DEFAULT 'CURRENT',
  as_of         TEXT,
  core_answer   TEXT,                      -- the least a correct answer must say
  reference     TEXT,                      -- the fact check
  held_out      INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'candidate'   -- candidate, signed-off, dropped
);
CREATE TABLE expected (                    -- by unit, and by version where the version matters
  question_id   TEXT NOT NULL REFERENCES question,
  unit_id       INTEGER NOT NULL REFERENCES unit,
  version_id    INTEGER REFERENCES version,
  role          TEXT NOT NULL DEFAULT 'answer'
                CHECK (role IN ('answer','stale','decoy','conflict','poison','inject'))
);
CREATE TABLE run (                         -- one evaluation run; the ratchet compares runs
  run_id        INTEGER PRIMARY KEY,
  episode       TEXT NOT NULL,
  config_hash   TEXT NOT NULL,             -- prompts, models, retrieval settings
  source_id     INTEGER NOT NULL REFERENCES source,
  ingest_run_id INTEGER REFERENCES ingest_run,
  started_at    TEXT NOT NULL
);
CREATE TABLE result (
  run_id        INTEGER NOT NULL REFERENCES run,
  question_id   TEXT NOT NULL REFERENCES question,
  first_hit     INTEGER,                   -- rank of the first expected unit, NULL = miss
  all_evidence  INTEGER,                   -- rank by which every expected unit was retrieved
  stale_in_top  INTEGER NOT NULL DEFAULT 0,
  poison_in_top INTEGER,                   -- planted false units in the top k
  followed_injection INTEGER,              -- 1 = a planted instruction was acted on
  leaked        INTEGER,                   -- 1 = the answer used something the asker may not see
  answer_id     INTEGER REFERENCES answer,
  label         TEXT,                      -- correct, partly, wrong, abstained...
  labelled_by   TEXT,
  PRIMARY KEY (run_id, question_id)
) WITHOUT ROWID;
