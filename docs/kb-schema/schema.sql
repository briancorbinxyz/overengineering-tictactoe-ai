-- Knowledge base schema, v2 (living). Core only; optional extensions are in extensions.sql,
-- the idempotent rule-apply step in apply.sql. One SQLite file per knowledge base; SQLite 3.45+.
-- Each table says which theme it serves and which episode proves it.
-- Time words used throughout:
--   valid time      when something holds in the world             valid_from / valid_to
--   knowledge time  when THIS knowledge base recorded it           recorded_from / recorded_to
--   source time     when the source itself published or sent it    published_at (version)
-- All timestamps are UTC ISO-8601 strings, so text comparison is time comparison.
PRAGMA foreign_keys = ON;

-- ── Where knowledge comes from ────────────────────────────────────────────
-- A source is one corpus at one pinned snapshot (git commit, export date...).
CREATE TABLE source (
  source_id     INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,             -- 'spectastic', 'vault', 'sec-edgar'
  adapter       TEXT NOT NULL,             -- 'spectastic-html', 'obsidian-md', 'edgar-ixbrl'
  snapshot      TEXT NOT NULL,             -- commit hash or export id (reproducibility)
  snapshot_at   TEXT NOT NULL,
  UNIQUE (name, snapshot)
);

-- Every ingestion run, so "the source changed" is distinguishable from "our parser changed".
CREATE TABLE ingest_run (
  ingest_run_id    INTEGER PRIMARY KEY,
  source_id        INTEGER NOT NULL REFERENCES source,
  adapter_version  TEXT NOT NULL,            -- 'spectastic-html@1.4.0'
  splitter_version TEXT NOT NULL,            -- unit rules; a change here changes unit identity
  config_hash      TEXT NOT NULL,            -- PII rules, model ids, prompts
  profile_sha256   TEXT,                     -- the YAML source profile (CEL rules, trust defaults, link rules)
  manifest_sha256  TEXT,                     -- the fetch manifest (manifest.jsonl) it read
  started_at       TEXT NOT NULL,
  finished_at      TEXT,
  status           TEXT NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running','ok','failed','superseded'))
);

-- Write-once, content-addressed artefacts: raw bytes as fetched, and parser output.
-- A re-fetch adds a blob; it never overwrites one, so an old manifest digest still resolves.
CREATE TABLE blob (
  sha256        TEXT PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('raw','parsed')),
  derived_from  TEXT REFERENCES blob,        -- parsed -> raw
  producer      TEXT,                        -- 'docling-serve@0.7.1+opts:9f2c'; NULL for raw
  url           TEXT, fetched_at TEXT,       -- raw only
  path          TEXT NOT NULL,               -- 'raw/sha256/ab/cd/<sha256>'
  bytes         INTEGER NOT NULL,
  CHECK ((kind = 'raw') = (derived_from IS NULL))
) WITHOUT ROWID;
CREATE TRIGGER blob_write_once_u BEFORE UPDATE ON blob
BEGIN SELECT RAISE(ABORT, 'blob is write-once'); END;
CREATE TRIGGER blob_write_once_d BEFORE DELETE ON blob
BEGIN SELECT RAISE(ABORT, 'blob is write-once'); END;

-- A document is one addressable file, page, filing, message or note.
CREATE TABLE document (
  document_id   INTEGER PRIMARY KEY,
  source_id     INTEGER NOT NULL REFERENCES source,
  path          TEXT NOT NULL,             -- 'specs/040-run-budget/spec.html', accession, Message-ID
  title         TEXT,
  uri           TEXT,                      -- where it was fetched from
  scope         TEXT,                      -- grouping: spec id, folder, client...
  recorded_from TEXT NOT NULL,             -- when this knowledge base first recorded the document
  ingest_run_id INTEGER REFERENCES ingest_run,
  -- Six trust facts plus access. Set by the adapter from how the document arrived, never
  -- from its text; defaults are cautious. They are INGEST-TIME DEFAULTS: frozen after insert
  -- (trigger below) and mirrored as direction='initial' rows in `assessment`. Later changes
  -- are new assessment rows, so AS_KNOWN can replay the label a past answer saw.
  access        TEXT NOT NULL DEFAULT 'private',      -- who may see it: hard pre-filter, fails closed.
                                                      -- The one mutable fact: always enforced at its
                                                      -- current value, even in replays.
  sensitivity   INTEGER NOT NULL DEFAULT 1            -- how bad a leak is: 0 public .. 3 restricted
                CHECK (sensitivity BETWEEN 0 AND 3),
  publisher     TEXT,                                 -- who stands behind it: 'cik:2098', 'analyst-3@tallowmere.example'
  reliability   TEXT                                  -- how dependable the publisher is; NULL = can't judge
                CHECK (reliability IN ('authoritative','reliable','unvetted','doubtful')),
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
-- 10-K Item, message. Identity is stable; text lives in versions. (Episodes 3-4)
CREATE TABLE unit (
  unit_id       INTEGER PRIMARY KEY,
  document_id   INTEGER NOT NULL REFERENCES document,
  anchor        TEXT NOT NULL,             -- 'FR-001', 'Item 4.02', '^block-id', 'message'
  part          INTEGER NOT NULL DEFAULT 1,-- long units split into parts
  parent_id     INTEGER REFERENCES unit,   -- structure: section > requirement
  kind          TEXT NOT NULL,             -- 'requirement','decision','section','note','message'...
  statement     TEXT NOT NULL CHECK (statement IN ('normative','record')),
                                           -- normative: states what is true/required;
                                           -- record: says what happened (filing, log, message)
  heading_path  TEXT,                      -- 'Run budget > Requirements > FR-001'
  format        TEXT NOT NULL DEFAULT 'prose'
                CHECK (format IN ('prose','table','figure','code','math','list')),
  locator       TEXT,                      -- JSON: page, bbox, rows, cols, lines
  UNIQUE (document_id, anchor, part)
);

-- Identifiers a reader (or a link) would type, scoped. Exact lookup, no full-text. (Episode 4)
-- Typed composite keys live here too, so a link can name a target before it arrives:
-- scheme 'edgar:cik+form+period', value '2098|10-K|2025-12-31'. Schemes: key_scheme (extensions).
CREATE TABLE identifier (
  value         TEXT NOT NULL COLLATE NOCASE,  -- 'FR-001', ticker, accession, Message-ID
  scheme        TEXT,                          -- 'spec', 'edgar:accession', 'celex', 'email:message-id'...
  scope         TEXT NOT NULL DEFAULT '',      -- '040' (spec); '' = global. (v1 said NULL, which a
                                               -- WITHOUT ROWID primary key rejects)
  unit_id       INTEGER NOT NULL REFERENCES unit,
  PRIMARY KEY (value, scope, unit_id)
) WITHOUT ROWID;
CREATE INDEX identifier_scheme ON identifier (scheme, value);

-- A version is one text of one unit over two time axes. (time episode)
-- A change opens a new valid period; a correction keeps valid_from and closes only the
-- recorded period. recorded_* is knowledge time: when THIS knowledge base recorded the text.
-- published_at is source time: EDGAR acceptanceDateTime, an email's Date:, FR publication.
-- (Decision, v2: knowledge time stays the KB's own; the source's clock is a separate column,
-- so "when could we have known" and "when did the source say it" never get conflated.)
CREATE TABLE version (
  version_id    INTEGER PRIMARY KEY,
  unit_id       INTEGER NOT NULL REFERENCES unit,
  body          TEXT NOT NULL,             -- exactly what quotations are matched against
  body_hash     TEXT NOT NULL,             -- sha-256 of body: provenance by content
  lifecycle     TEXT NOT NULL DEFAULT 'current'   -- publisher-declared only; judgments go to assessment
                CHECK (lifecycle IN ('current','draft','applied','superseded','withdrawn','rejected','retired')),
  valid_from    TEXT,                      -- NULL = unknown (graded below)
  valid_to      TEXT,                      -- NULL = still in effect
  valid_grade   TEXT NOT NULL DEFAULT 'page',  -- 'element','change','page','none': how the date was derived
  recorded_from TEXT NOT NULL,             -- when this KB first recorded this text
  recorded_to   TEXT,                      -- NULL = still recorded this way
  published_at  TEXT,                      -- when the source published / sent / accepted it
  commit_ref    TEXT,                      -- the commit that recorded it
  blob_sha256   TEXT REFERENCES blob,      -- the raw or parsed artefact this text came from
  ingest_run_id INTEGER REFERENCES ingest_run,
  author_kind   TEXT NOT NULL DEFAULT 'human'      -- AI-written text is marked as such
                CHECK (author_kind IN ('human','tool','model','agent')),
  author        TEXT,                      -- person, agent id, or model@digest
  lang          TEXT                       -- BCP-47; picks the tokenizer
);
CREATE INDEX version_unit ON version (unit_id, valid_from, recorded_from);
CREATE INDEX version_now ON version (unit_id, valid_to) WHERE recorded_to IS NULL;

-- Keyword index over current knowledge, weighted fields, ids kept whole. (Episode 4)
CREATE VIRTUAL TABLE version_fts USING fts5 (
  title, ident, body,
  content = '', contentless_delete = 1,
  tokenize = 'unicode61'
);  -- rowid = version_id; query with bm25(version_fts, 5, 10, 1). Quote every user term.
    -- Never put status labels into indexed or embedded text: status changes, text doesn't.

-- Vectors per version per model, so a model swap is a new row, not a migration. (Episodes 3-4)
CREATE TABLE embedding (
  version_id    INTEGER NOT NULL REFERENCES version,
  model         TEXT NOT NULL,             -- 'nomic-embed-text:v1.5@0a109f42'
  dims          INTEGER NOT NULL,
  vector        BLOB NOT NULL,             -- float32 little-endian; sqlite-vec reads it as is
  PRIMARY KEY (version_id, model)
) WITHOUT ROWID;

-- ── How knowledge connects ───────────────────────────────────────────────
-- Typed links between units, each with how it was derived and when it became known. (Episode 5)
-- A link may name its target by a typed key before the target is ingested; extensions'
-- link_resolution binds it later, order-independently. Types and what they do to status
-- live in link_type (extensions): data, not code. Append-only except closing recorded_to.
CREATE TABLE link (
  link_id       INTEGER PRIMARY KEY,
  from_unit     INTEGER NOT NULL REFERENCES unit,
  type          TEXT NOT NULL,             -- 'supersedes','do-not-rely','replies-to','cites',...
  to_unit       INTEGER REFERENCES unit,   -- direct target, when known at write time
  to_document   INTEGER REFERENCES document,
  to_key_scheme TEXT,                      -- unresolved target: 'edgar:cik+form+period'
  to_key        TEXT,                      --                    '2098|10-K|2025-12-31'
  origin        TEXT NOT NULL CHECK (origin IN ('markup','status+link','prose-pattern','model','human')),
  confidence    REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  emitted_by    TEXT,                      -- 'profile:sec-edgar-8k@<sha12>' | 'rule:<id>@<sha12>' | 'human:<id>'
  valid_from    TEXT,                      -- when the relation holds in the world (e.g. adoption date)
  recorded_from TEXT NOT NULL,             -- when this KB recorded the link
  recorded_to   TEXT,                      -- set once when the link is withdrawn; never deleted
  CHECK (to_unit IS NOT NULL OR to_document IS NOT NULL OR to_key IS NOT NULL),
  CHECK ((to_key_scheme IS NULL) = (to_key IS NULL)),
  CHECK (recorded_to IS NULL OR recorded_to > recorded_from)
);
CREATE INDEX link_from    ON link (from_unit, type);
CREATE INDEX link_to      ON link (to_unit, type);
CREATE INDEX link_key ON link (to_key_scheme, to_key) WHERE to_key IS NOT NULL;  -- "prefix scan" on arrival
CREATE TRIGGER link_append_only BEFORE UPDATE ON link
WHEN OLD.recorded_to IS NOT NULL OR NEW.recorded_to IS NULL
  OR NEW.link_id IS NOT OLD.link_id OR NEW.from_unit IS NOT OLD.from_unit OR NEW.type IS NOT OLD.type
  OR NEW.to_unit IS NOT OLD.to_unit OR NEW.to_document IS NOT OLD.to_document
  OR NEW.to_key_scheme IS NOT OLD.to_key_scheme OR NEW.to_key IS NOT OLD.to_key
  OR NEW.origin IS NOT OLD.origin OR NEW.confidence IS NOT OLD.confidence
  OR NEW.emitted_by IS NOT OLD.emitted_by OR NEW.valid_from IS NOT OLD.valid_from
  OR NEW.recorded_from IS NOT OLD.recorded_from
BEGIN SELECT RAISE(ABORT, 'link is append-only: the only change allowed is closing recorded_to once'); END;
CREATE TRIGGER link_no_delete BEFORE DELETE ON link
BEGIN SELECT RAISE(ABORT, 'link is append-only'); END;

-- ── "Now" is data, not the wall clock ────────────────────────────────────
-- Freeze it so answers don't flip when a future-effective rule comes into force mid-run.
-- AS_KNOWN(t) is the same views with now_recorded = t (and usually now_valid = t).
CREATE TABLE clock (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  now_valid     TEXT NOT NULL,             -- the valid-time "today": a date (start of day) or timestamp
  now_recorded  TEXT NOT NULL              -- the knowledge-time "now", a timestamp
);

-- ── How far to trust it, over time: the status ledger ─────────────────────
-- Who may make a judgment, ranked. Only the first three may exclude something
-- (non-provisionally) from CURRENT support or OFFICIAL; everyone else adds labels.
CREATE TABLE authority_kind (
  authority     TEXT PRIMARY KEY,
  rank          INTEGER NOT NULL,          -- lower wins a tie between live rows
  may_exclude   INTEGER NOT NULL CHECK (may_exclude IN (0,1)),
  meaning       TEXT NOT NULL
);
INSERT INTO authority_kind VALUES
  ('publisher',   1, 1, 'the target''s own publisher: same CIK, signing key, sender or workspace'),
  ('markup',      2, 1, 'structured relation markup from an official publisher (ELI repeals, FR correction_of)'),
  ('human',       3, 1, 'an accountable analyst, directly or through a link they wrote'),
  ('profile',     4, 0, 'a curated, owned source profile or source rule (ingest-time defaults)'),
  ('third_party', 5, 0, 'another organisation''s rating (Retraction Watch, a news outlet)'),
  ('heuristic',   6, 0, 'a prose pattern or cue rule'),
  ('model',       7, 0, 'model output');

-- The status vocabulary, per dimension. Values match by GLOB ('entity:*'). `supports` and
-- `official` say what a non-provisional effective value does to retrieval; a value with
-- supports='no' or official=0 is an EXCLUSION and needs an authority with may_exclude=1.
-- 'void' is reserved: a row with value 'void' only cancels the row it supersedes.
CREATE TABLE status_value (
  dimension     TEXT NOT NULL,
  value         TEXT NOT NULL,             -- exact value or GLOB pattern
  value_rank    INTEGER NOT NULL,          -- lower = more severe; breaks ties between live rows
  supports      TEXT NOT NULL CHECK (supports IN ('yes','labelled','no')),
  official      INTEGER NOT NULL CHECK (official IN (0,1)),
  PRIMARY KEY (dimension, value)
) WITHOUT ROWID;
INSERT INTO status_value VALUES
  -- standing: is the text still something to rely on? (document, unit, version; has valid time)
  ('standing','retracted',1,'no',0), ('standing','withdrawn',2,'no',0), ('standing','repealed',3,'no',0),
  ('standing','superseded',4,'no',0), ('standing','restated',5,'no',0), ('standing','do_not_rely',6,'labelled',0),
  ('standing','corrected',7,'labelled',1), ('standing','amended',8,'labelled',1),
  ('standing','concern',9,'labelled',1), ('standing','at_risk',10,'labelled',1), ('standing','in_force',20,'yes',1),
  -- register: what kind of text it is (set from the arrival path, never from the text)
  ('register','fiction',1,'no',0), ('register','satire',2,'no',0), ('register','parody',3,'no',0),
  ('register','simulation',4,'no',0), ('register','synthetic',5,'labelled',0), ('register','opinion',10,'labelled',1),
  ('register','unknown',15,'labelled',1), ('register','factual',20,'yes',1),
  -- world: the context a claim holds in (claim)
  ('world','universe:*',1,'no',1), ('world','synthetic:*',2,'no',1), ('world','real',20,'yes',1),
  -- verification: epistemic, knowledge time only (claim, unit)
  ('verification','refuted',1,'no',1), ('verification','disputed',5,'labelled',1),
  ('verification','unverified',10,'labelled',1), ('verification','cannot_judge',11,'labelled',1),
  ('verification','verified',20,'yes',1),
  -- resolution: which entity a mention names, as known at t (mention)
  ('resolution','nil',3,'labelled',1), ('resolution','ambiguous:*',5,'labelled',1),
  ('resolution','unresolved',6,'labelled',1), ('resolution','entity:*',20,'yes',1),
  -- the document trust facts, mirrored from the frozen columns
  ('reliability','doubtful',5,'labelled',1), ('reliability','unvetted',10,'labelled',1),
  ('reliability','reliable',15,'yes',1), ('reliability','authoritative',20,'yes',1),
  ('force','none',5,'yes',0), ('force','guidance',10,'yes',0), ('force','official',15,'yes',1), ('force','binding',20,'yes',1),
  ('authenticity','unknown',1,'yes',0), ('authenticity','derived',2,'yes',0), ('authenticity','copy',3,'yes',0),
  ('authenticity','original',15,'yes',1), ('authenticity','signed',20,'yes',1),
  ('trust_zone','external',5,'yes',1), ('trust_zone','internal',10,'yes',1), ('trust_zone','curated',20,'yes',1),
  ('sensitivity','[0-3]',10,'yes',1), ('publisher','*',10,'yes',1), ('access','*',10,'yes',1);

-- The ledger: every trust and status judgment as an append-only, bitemporal row. Text changes
-- make versions; judgment changes make assessments. Effective status is computed per query
-- (status_now), never stored. Several raters may coexist for one target and dimension.
CREATE TABLE assessment (
  assessment_id INTEGER PRIMARY KEY,
  -- exactly one target
  document_id   INTEGER REFERENCES document,
  unit_id       INTEGER REFERENCES unit,
  version_id    INTEGER REFERENCES version,
  link_id       INTEGER REFERENCES link,
  claim_id      INTEGER,                   -- claim (extensions.sql; existence checked there)
  mention_id    INTEGER,                   -- mention (extensions.sql; existence checked there)
  target_kind   TEXT GENERATED ALWAYS AS (CASE
                  WHEN document_id IS NOT NULL THEN 'document' WHEN unit_id IS NOT NULL THEN 'unit'
                  WHEN version_id IS NOT NULL THEN 'version' WHEN link_id IS NOT NULL THEN 'link'
                  WHEN claim_id IS NOT NULL THEN 'claim' ELSE 'mention' END) VIRTUAL,
  target_id     INTEGER GENERATED ALWAYS AS
                  (coalesce(document_id, unit_id, version_id, link_id, claim_id, mention_id)) VIRTUAL,
  dimension     TEXT NOT NULL,             -- see status_value
  value         TEXT NOT NULL,
  direction     TEXT NOT NULL CHECK (direction IN ('initial','promote','demote','lateral')),
  provisional   INTEGER NOT NULL DEFAULT 0 CHECK (provisional IN (0,1)),  -- 1 = label only, never excludes
  valid_from    TEXT, valid_to TEXT,       -- when the judgment holds in the world; NULL = always
  recorded_from TEXT NOT NULL,             -- when this KB recorded it; rows are never updated
  supersedes    INTEGER REFERENCES assessment,
  evidence_version_id INTEGER REFERENCES version,   -- the text that justifies it (the 8-K unit, the 09:40 reply)
  evidence_link_id    INTEGER REFERENCES link,      -- the relation that justifies it
  method        TEXT NOT NULL CHECK (method IN ('source','rule','human','model')),
  authority     TEXT NOT NULL REFERENCES authority_kind,
  rule_id       TEXT,                      -- rule_version (extensions) that derived it
  rule_sha256   TEXT,
  derivation_key TEXT,                     -- deterministic key of a rule derivation: re-running apply is a no-op
  proposed_by   TEXT,                      -- maker
  rated_by      TEXT NOT NULL,             -- checker, 'rule:<id>@<sha12>', issuer key, 'profile@<sha>'
  confidence    REAL,
  rationale     TEXT,
  ingest_run_id INTEGER REFERENCES ingest_run,
  CHECK ((document_id IS NOT NULL) + (unit_id IS NOT NULL) + (version_id IS NOT NULL)
       + (link_id IS NOT NULL) + (claim_id IS NOT NULL) + (mention_id IS NOT NULL) = 1),
  CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
  CHECK ((rule_id IS NULL) = (rule_sha256 IS NULL)),
  CHECK (direction <> 'initial' OR supersedes IS NULL),
  CHECK (method <> 'human' OR authority = 'human'),
  CHECK (method <> 'model' OR authority = 'model'),
  -- promotions: a human checker who is not the maker. No rule, model or source promotes.
  CHECK (direction <> 'promote'
         OR (method = 'human' AND proposed_by IS NOT NULL AND proposed_by <> rated_by)),
  -- demotions by a model, a third party or a heuristic are labels until someone accountable confirms
  CHECK (direction <> 'demote' OR authority NOT IN ('model','third_party','heuristic') OR provisional = 1)
);
CREATE INDEX assessment_target ON assessment (target_kind, target_id, dimension, recorded_from);
CREATE INDEX assessment_supersedes ON assessment (supersedes);
CREATE UNIQUE INDEX assessment_derivation ON assessment (derivation_key) WHERE derivation_key IS NOT NULL;

CREATE TRIGGER assessment_no_update BEFORE UPDATE ON assessment
BEGIN SELECT RAISE(ABORT, 'assessment is append-only'); END;
CREATE TRIGGER assessment_no_delete BEFORE DELETE ON assessment
BEGIN SELECT RAISE(ABORT, 'assessment is append-only'); END;
CREATE TRIGGER assessment_vocab BEFORE INSERT ON assessment
WHEN NEW.value <> 'void' AND NOT EXISTS
  (SELECT 1 FROM status_value s WHERE s.dimension = NEW.dimension AND NEW.value GLOB s.value)
BEGIN SELECT RAISE(ABORT, 'unknown dimension/value (see status_value)'); END;
-- Exclusions only from the publisher itself, official markup, or an accountable human;
-- ingest-time defaults from a curated profile are the one other way in.
CREATE TRIGGER assessment_exclusion_authority BEFORE INSERT ON assessment
WHEN NEW.provisional = 0 AND NEW.value <> 'void'
 AND EXISTS (SELECT 1 FROM status_value s WHERE s.dimension = NEW.dimension AND NEW.value GLOB s.value
             AND (s.supports = 'no' OR s.official = 0))
 AND NOT EXISTS (SELECT 1 FROM authority_kind k WHERE k.authority = NEW.authority AND k.may_exclude = 1)
 AND NOT (NEW.direction = 'initial' AND NEW.authority = 'profile')
BEGIN SELECT RAISE(ABORT, 'exclusion needs publisher, markup or human authority; record it as provisional'); END;
-- authority='publisher' must be true: the evidence comes from the target's own publisher.
CREATE TRIGGER assessment_publisher_is_publisher BEFORE INSERT ON assessment
WHEN NEW.authority = 'publisher' AND NEW.mention_id IS NULL AND NEW.claim_id IS NULL AND NEW.link_id IS NULL
 AND (NEW.evidence_version_id IS NOT NULL OR NEW.evidence_link_id IS NOT NULL)
BEGIN
  SELECT RAISE(ABORT, 'authority=publisher but the evidence comes from another publisher')
  WHERE (SELECT d.publisher FROM document d WHERE d.document_id = coalesce(NEW.document_id,
           (SELECT u.document_id FROM unit u WHERE u.unit_id = NEW.unit_id),
           (SELECT u.document_id FROM version v JOIN unit u USING (unit_id) WHERE v.version_id = NEW.version_id)))
    IS NOT
        (SELECT d.publisher FROM document d WHERE d.document_id = coalesce(
           (SELECT u.document_id FROM version v JOIN unit u USING (unit_id) WHERE v.version_id = NEW.evidence_version_id),
           (SELECT u.document_id FROM link l JOIN unit u ON u.unit_id = l.from_unit WHERE l.link_id = NEW.evidence_link_id)));
END;

-- Trust columns are ingest-time defaults: frozen after insert (access stays mutable).
CREATE TRIGGER document_trust_frozen
BEFORE UPDATE OF sensitivity, publisher, reliability, force, authenticity, trust_zone, recorded_from ON document
WHEN NEW.sensitivity IS NOT OLD.sensitivity OR NEW.publisher IS NOT OLD.publisher
  OR NEW.reliability IS NOT OLD.reliability OR NEW.force IS NOT OLD.force
  OR NEW.authenticity IS NOT OLD.authenticity OR NEW.trust_zone IS NOT OLD.trust_zone
  OR NEW.recorded_from IS NOT OLD.recorded_from
BEGIN SELECT RAISE(ABORT, 'trust facts are ingest-time defaults; change them with assessment rows'); END;
-- ...and mirrored as direction='initial' ledger rows (NULL publisher/reliability = no row: can't judge).
CREATE TRIGGER document_initial_trust AFTER INSERT ON document
BEGIN
  INSERT INTO assessment (document_id, dimension, value, direction, recorded_from, method, authority,
                          rated_by, ingest_run_id, rationale)
  SELECT NEW.document_id, f.d, f.v, 'initial', NEW.recorded_from, 'rule', 'profile',
         coalesce((SELECT 'profile@' || substr(r.profile_sha256, 1, 12) FROM ingest_run r
                   WHERE r.ingest_run_id = NEW.ingest_run_id AND r.profile_sha256 IS NOT NULL),
                  (SELECT 'adapter:' || s.adapter FROM source s WHERE s.source_id = NEW.source_id)),
         NEW.ingest_run_id, 'ingest-time default'
  FROM (SELECT 'access' AS d, NEW.access AS v
        UNION ALL SELECT 'sensitivity', CAST(NEW.sensitivity AS TEXT)
        UNION ALL SELECT 'publisher', NEW.publisher   UNION ALL SELECT 'reliability', NEW.reliability
        UNION ALL SELECT 'force', NEW.force           UNION ALL SELECT 'authenticity', NEW.authenticity
        UNION ALL SELECT 'trust_zone', NEW.trust_zone) f
  WHERE f.v IS NOT NULL;
END;

-- Live rows under the frozen clock: known by now_recorded, valid at now_valid, not superseded
-- by a row known by now_recorded, not a void. Includes provisional rows and losing raters.
CREATE VIEW assessment_live AS
SELECT a.*, s.value_rank, s.supports, s.official, k.rank AS authority_rank
FROM assessment a
JOIN clock c ON c.id = 1
JOIN authority_kind k ON k.authority = a.authority
LEFT JOIN status_value s ON s.dimension = a.dimension AND a.value GLOB s.value
WHERE a.value <> 'void'
  AND a.recorded_from <= c.now_recorded
  AND (a.valid_from IS NULL OR a.valid_from <= c.now_valid)
  AND (a.valid_to   IS NULL OR a.valid_to   >  c.now_valid)
  AND NOT EXISTS (SELECT 1 FROM assessment x
                  WHERE x.supersedes = a.assessment_id AND x.recorded_from <= c.now_recorded);
-- STATUS_NOW: one row per (target, dimension) that has live rows. `value` is the DECISION:
-- the best non-provisional row, where exclusions beat labels, then the most specific valid
-- time (latest valid_from), then authority, then severity, then recency. To lift a stricter
-- value (a promotion, an undo), supersede it. Provisional rows never decide: their values are
-- carried in `flags`. A target with only provisional rows has value NULL (the default holds)
-- and provisional = 1.
CREATE VIEW status_now AS
WITH r AS (
  SELECT l.*, ROW_NUMBER() OVER (PARTITION BY l.target_kind, l.target_id, l.dimension
           ORDER BY (l.supports = 'no' OR l.official = 0) DESC,
                    l.valid_from DESC NULLS LAST, l.authority_rank, l.value_rank,
                    l.recorded_from DESC, l.assessment_id DESC) AS rn
  FROM assessment_live l WHERE l.provisional = 0),
k AS (SELECT DISTINCT target_kind, target_id, dimension FROM assessment_live)
SELECT k.target_kind, k.target_id, k.dimension, d.value, CASE WHEN d.value IS NULL THEN 1 ELSE 0 END AS provisional,
       d.authority, d.method, d.valid_from, d.recorded_from, d.assessment_id, d.rated_by, d.supports, d.official,
       (SELECT group_concat(p.value || ' (provisional, ' || p.authority || ')', '; ')
        FROM assessment_live p
        WHERE p.target_kind = k.target_kind AND p.target_id = k.target_id
          AND p.dimension = k.dimension AND p.provisional = 1 AND p.value IS NOT d.value) AS flags
FROM k LEFT JOIN r d ON d.target_kind = k.target_kind AND d.target_id = k.target_id
                    AND d.dimension = k.dimension AND d.rn = 1;
-- Effective trust facts per document: the ledger, else the frozen column.
CREATE VIEW document_trust_now AS
SELECT d.document_id, d.access,
  coalesce((SELECT value FROM status_now s WHERE s.target_kind='document' AND s.target_id=d.document_id AND s.dimension='sensitivity'), CAST(d.sensitivity AS TEXT)) AS sensitivity,
  coalesce((SELECT value FROM status_now s WHERE s.target_kind='document' AND s.target_id=d.document_id AND s.dimension='publisher'), d.publisher) AS publisher,
  coalesce((SELECT value FROM status_now s WHERE s.target_kind='document' AND s.target_id=d.document_id AND s.dimension='reliability'), d.reliability) AS reliability,
  coalesce((SELECT value FROM status_now s WHERE s.target_kind='document' AND s.target_id=d.document_id AND s.dimension='force'), d.force) AS force,
  coalesce((SELECT value FROM status_now s WHERE s.target_kind='document' AND s.target_id=d.document_id AND s.dimension='authenticity'), d.authenticity) AS authenticity,
  coalesce((SELECT value FROM status_now s WHERE s.target_kind='document' AND s.target_id=d.document_id AND s.dimension='trust_zone'), d.trust_zone) AS trust_zone
FROM document d;

-- ── Retrieval modes as views: the default is now, as known now ──────────
-- CURRENT: normative content in effect at clock.now_valid, plus records of applied changes,
-- as known at clock.now_recorded. Text membership only; status is layered on below.
CREATE VIEW current_version AS
SELECT v.* FROM version v JOIN unit u USING (unit_id), clock c
WHERE v.recorded_from <= c.now_recorded
  AND (v.recorded_to IS NULL OR v.recorded_to > c.now_recorded)
  AND (   (u.statement = 'normative'
           AND v.valid_from IS NOT NULL AND v.valid_from <= c.now_valid
           AND (v.valid_to IS NULL OR v.valid_to > c.now_valid)
           AND v.lifecycle NOT IN ('withdrawn','rejected','retired'))
       OR (u.statement = 'record' AND v.lifecycle IN ('current','applied')));
-- Effective status at every level that applies to a version: version, unit, document.
CREATE VIEW status_scope AS
SELECT v.version_id, s.*, CASE s.target_kind WHEN 'version' THEN 1 WHEN 'unit' THEN 2 ELSE 3 END AS specificity
FROM version v JOIN unit u USING (unit_id)
JOIN status_now s ON (s.target_kind = 'version'  AND s.target_id = v.version_id)
                  OR (s.target_kind = 'unit'     AND s.target_id = v.unit_id)
                  OR (s.target_kind = 'document' AND s.target_id = u.document_id);
-- CURRENT with status: what the retriever ranks and what the model is shown. The decision comes
-- from the most specific level that has one; flags (provisional labels) from every level.
-- `supports` decides membership in the evidence set (filter BEFORE top-k): 'no' never supports an
-- answer (shown only when the question names the item), 'labelled' supports with its label,
-- 'yes' plainly. `label` is the literal text placed beside the passage; log it in
-- answer_context.shown_label.
CREATE VIEW current_labeled AS
WITH cv AS (
  SELECT v.version_id, v.unit_id, u.document_id, v.body, v.valid_from, v.recorded_from,
    (SELECT s.target_kind || ':' || s.target_id FROM status_scope s WHERE s.version_id = v.version_id
       AND s.dimension = 'standing' AND s.value IS NOT NULL ORDER BY s.specificity LIMIT 1) AS st_key,
    (SELECT group_concat(s.flags, '; ') FROM status_scope s WHERE s.version_id = v.version_id
       AND s.dimension = 'standing' AND s.flags IS NOT NULL) AS st_flags,
    (SELECT s.target_kind || ':' || s.target_id FROM status_scope s WHERE s.version_id = v.version_id
       AND s.dimension = 'register' AND s.value IS NOT NULL ORDER BY s.specificity LIMIT 1) AS rg_key,
    (SELECT group_concat(s.flags, '; ') FROM status_scope s WHERE s.version_id = v.version_id
       AND s.dimension = 'register' AND s.flags IS NOT NULL) AS rg_flags
  FROM current_version v JOIN unit u USING (unit_id)),
j AS (
  SELECT cv.*, st.value AS st_value, st.authority AS st_auth, st.valid_from AS st_since,
         st.recorded_from AS st_known, rg.value AS rg_value,
         coalesce(st.supports, 'yes') AS st_eff, coalesce(rg.supports, 'yes') AS rg_eff
  FROM cv
  LEFT JOIN status_now st ON st.dimension = 'standing' AND st.target_kind || ':' || st.target_id = cv.st_key
  LEFT JOIN status_now rg ON rg.dimension = 'register' AND rg.target_kind || ':' || rg.target_id = cv.rg_key)
SELECT version_id, unit_id, document_id, body, valid_from, recorded_from,
  coalesce(st_value, 'in_force') AS standing, st_auth AS standing_authority,
  st_since AS standing_since, st_known AS standing_known, st_flags AS standing_flags,
  coalesce(rg_value, 'factual') AS register, rg_flags AS register_flags,
  CASE WHEN 'no' IN (st_eff, rg_eff) THEN 'no'
       WHEN 'labelled' IN (st_eff, rg_eff) OR st_flags IS NOT NULL OR rg_flags IS NOT NULL THEN 'labelled'
       ELSE 'yes' END AS supports,
  trim(coalesce(CASE WHEN st_value IS NOT NULL AND st_value <> 'in_force' THEN
         st_value || ' [' || st_auth || coalesce(', since ' || st_since, '') || ', known ' || st_known || ']' END, '')
    || coalesce(' register=' || CASE WHEN rg_value <> 'factual' THEN rg_value END, '')
    || coalesce(' flagged: ' || st_flags, '') || coalesce(' flagged: ' || rg_flags, '')) AS label
FROM j;
-- OFFICIAL: current, and no effective non-provisional fact (force, authenticity, standing,
-- register...) at any level says "not official". For official-only policies; otherwise a feature.
CREATE VIEW official_version AS
SELECT v.* FROM current_version v
WHERE NOT EXISTS (SELECT 1 FROM status_scope s
                  WHERE s.version_id = v.version_id AND s.provisional = 0 AND s.official = 0);
-- HISTORY, AS_OF(:t) and CHANGE are parameterised queries in the retriever. AS_KNOWN(:t) is
-- these views after UPDATE clock SET now_recorded = :t, now_valid = :t.

-- ── Answers, with their evidence (Rule 4: never lose provenance) ─────────
CREATE TABLE answer (
  answer_id     INTEGER PRIMARY KEY,
  asked_at      TEXT NOT NULL,             -- UTC; replaying needs AS_KNOWN(asked_at)
  question      TEXT NOT NULL,
  mode          TEXT NOT NULL DEFAULT 'CURRENT',  -- CURRENT, HISTORY, AS_OF, CHANGE, AS_KNOWN
  as_of         TEXT,
  model         TEXT NOT NULL,
  principal     TEXT,                      -- who asked; 'agent:x for user:y' when delegated
  policy        TEXT,                      -- JSON: filters, official-only, worlds, weights
  sensitivity   INTEGER NOT NULL DEFAULT 0,-- max over everything in its context, not just what it cites
  text          TEXT
);
CREATE TABLE answer_context (              -- every version placed in the model's context
  answer_id     INTEGER NOT NULL REFERENCES answer,
  version_id    INTEGER NOT NULL REFERENCES version,
  rank          INTEGER NOT NULL,
  marked        INTEGER NOT NULL DEFAULT 0,-- 1 = datamarked as untrusted
  shown_label   TEXT,                      -- the literal status label the model saw (current_labeled.label)
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
  question_id   TEXT PRIMARY KEY,          -- 'G-001', 'ACME-01'
  text          TEXT NOT NULL,
  stratum       TEXT NOT NULL,             -- single-fact, identifier, relation, stale, history, ambiguity, unanswerable...
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
                CHECK (role IN ('answer','stale','decoy','conflict','poison','inject','candidate'))
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
