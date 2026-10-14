-- Knowledge base schema, v1 extensions. Each is optional: adopt it when an episode or a
-- deployment measures a need for it. Requires schema.sql first.
-- ═══ EXTENSIONS ═════════════════════════════════════════════════════════

CREATE TABLE access_grant (                 -- multi-user: who holds each access value
  access TEXT NOT NULL, principal TEXT NOT NULL, deny INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (access, principal)) WITHOUT ROWID;

CREATE TABLE assessment (                   -- who set each trust fact, how, and why
  document_id INTEGER NOT NULL REFERENCES document,
  dimension   TEXT NOT NULL,                -- 'reliability','force','sensitivity',...
  value       TEXT NOT NULL,
  method      TEXT NOT NULL CHECK (method IN ('rule','human','model','import')),
  rated_by    TEXT NOT NULL,                -- rule id, person, 'NewsGuard', 'Wikipedia RSP'
  rated_at    TEXT NOT NULL,
  rationale   TEXT);

CREATE TABLE facet (                        -- domain detail that stays out of core
  document_id INTEGER NOT NULL REFERENCES document,
  name TEXT NOT NULL, value TEXT NOT NULL,  -- 'sec_status'='furnished', 'assurance'='audited', 'tlp'='AMBER'
  PRIMARY KEY (document_id, name, value)) WITHOUT ROWID;

CREATE TABLE derived (                      -- model-made retrieval aids; never quotation targets
  version_id  INTEGER NOT NULL REFERENCES version,
  kind        TEXT NOT NULL CHECK (kind IN ('context','summary','translation','caption')),
  model       TEXT NOT NULL,
  prompt_hash TEXT NOT NULL,
  text        TEXT NOT NULL,
  ingest_run_id INTEGER REFERENCES ingest_run,
  PRIMARY KEY (version_id, kind, model, prompt_hash)) WITHOUT ROWID;

CREATE TABLE version_dup (                  -- near-duplicate clusters, collapsed before top-k
  version_id INTEGER PRIMARY KEY REFERENCES version,
  cluster_id INTEGER NOT NULL,
  method     TEXT NOT NULL,                 -- 'minhash-5gram@0.8'
  is_canonical INTEGER NOT NULL DEFAULT 0);

CREATE TABLE entity  (entity_id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT);
CREATE TABLE mention (
  version_id INTEGER NOT NULL REFERENCES version,
  entity_id  INTEGER NOT NULL REFERENCES entity,
  span_start INTEGER, span_end INTEGER,
  origin     TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0);
CREATE INDEX mention_entity ON mention (entity_id);

CREATE TABLE claim    (claim_id INTEGER PRIMARY KEY, text TEXT NOT NULL,
                       subject_entity INTEGER REFERENCES entity);
CREATE TABLE evidence (
  claim_id   INTEGER NOT NULL REFERENCES claim,
  version_id INTEGER NOT NULL REFERENCES version,
  stance     TEXT NOT NULL CHECK (stance IN ('supports','refutes','mentions')),
  origin     TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (claim_id, version_id)) WITHOUT ROWID;

CREATE TABLE feedback (
  feedback_id INTEGER PRIMARY KEY,
  answer_id   INTEGER NOT NULL REFERENCES answer,
  label       TEXT,                         -- quotation label, when aimed at one citation
  signal      TEXT NOT NULL CHECK (signal IN ('thumb_up','thumb_down','copied','opened','corrected')),
  actor       TEXT NOT NULL, at TEXT NOT NULL);

-- Governance pack: personal data, retention, holds, erasure.
CREATE TABLE subject (subject_id INTEGER PRIMARY KEY, keyed_hash TEXT NOT NULL UNIQUE, jurisdiction TEXT);
CREATE TABLE unit_subject (
  unit_id INTEGER NOT NULL REFERENCES unit, subject_id INTEGER NOT NULL REFERENCES subject,
  method TEXT NOT NULL, PRIMARY KEY (unit_id, subject_id)) WITHOUT ROWID;
CREATE TABLE retention_class (name TEXT PRIMARY KEY, regime TEXT, min_days INTEGER, max_days INTEGER);
CREATE TABLE hold (hold_id INTEGER PRIMARY KEY, matter TEXT NOT NULL, created_at TEXT NOT NULL, released_at TEXT);
CREATE TABLE document_hold (document_id INTEGER NOT NULL REFERENCES document,
  hold_id INTEGER NOT NULL REFERENCES hold, PRIMARY KEY (document_id, hold_id)) WITHOUT ROWID;
ALTER TABLE document ADD COLUMN retention TEXT REFERENCES retention_class;
ALTER TABLE version  ADD COLUMN erased_at TEXT;   -- tombstone: body emptied, hash and audit kept
