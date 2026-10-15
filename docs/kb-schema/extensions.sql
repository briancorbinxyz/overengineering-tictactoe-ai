-- Knowledge base schema, v2 extensions. Each pack is optional: adopt it when an episode or a
-- deployment measures a need for it. Requires schema.sql first. SQLite 3.45+ (JSON1 built in).
-- ═══ EXTENSIONS ═════════════════════════════════════════════════════════

CREATE TABLE access_grant (                 -- multi-user: who holds each access value
  access TEXT NOT NULL, principal TEXT NOT NULL, deny INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (access, principal)) WITHOUT ROWID;

CREATE TABLE facet (                        -- domain detail that stays out of core
  document_id INTEGER NOT NULL REFERENCES document,
  name TEXT NOT NULL, value TEXT NOT NULL,  -- 'sec_status'='furnished', 'assurance'='audited', 'tlp'='AMBER'
  PRIMARY KEY (document_id, name, value)) WITHOUT ROWID;

CREATE TABLE derived (                      -- model-made retrieval aids; never quotation targets.
  version_id  INTEGER NOT NULL REFERENCES version,      -- Never put status labels in here: a
  kind        TEXT NOT NULL CHECK (kind IN ('context','summary','translation','caption')),
  model       TEXT NOT NULL,                             -- demotion must not need a re-embed.
  prompt_hash TEXT NOT NULL,
  text        TEXT NOT NULL,
  ingest_run_id INTEGER REFERENCES ingest_run,
  PRIMARY KEY (version_id, kind, model, prompt_hash)) WITHOUT ROWID;
CREATE TABLE derived_input (                -- a summary over several notes: every input, so a
  version_id INTEGER NOT NULL, kind TEXT NOT NULL,       -- demoted input can mark it at_risk
  model TEXT NOT NULL, prompt_hash TEXT NOT NULL,
  input_version_id INTEGER NOT NULL REFERENCES version,
  PRIMARY KEY (version_id, kind, model, prompt_hash, input_version_id),
  FOREIGN KEY (version_id, kind, model, prompt_hash) REFERENCES derived) WITHOUT ROWID;

CREATE TABLE version_dup (                  -- near-duplicate clusters, collapsed before top-k
  version_id INTEGER PRIMARY KEY REFERENCES version,
  cluster_id INTEGER NOT NULL,
  method     TEXT NOT NULL,                 -- 'minhash-5gram@0.8'
  is_canonical INTEGER NOT NULL DEFAULT 0);

-- ── Meaning: entities that can be real, fictional or synthetic; mentions that keep candidates ──
CREATE TABLE entity (
  entity_id   INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  kind        TEXT CHECK (kind IN ('issuer','private_company','subsidiary','brand','product_or_app',
                                   'creative_work','fictional_org','person','regulator')),
  reality     TEXT NOT NULL DEFAULT 'real' CHECK (reality IN ('real','fictional','synthetic')),
  description TEXT);                         -- lets the linker disambiguate by type
CREATE TABLE entity_identifier (            -- CIK, LEI, ticker+venue, with validity: never invent one
  entity_id INTEGER NOT NULL REFERENCES entity,       -- for a fictional entity (it has none)
  scheme TEXT NOT NULL, value TEXT NOT NULL, venue TEXT,
  valid_from TEXT, valid_to TEXT,
  PRIMARY KEY (entity_id, scheme, value)) WITHOUT ROWID;
CREATE TABLE alias (                        -- builds the candidate set: "ACME" is an alias of every Acme
  entity_id INTEGER NOT NULL REFERENCES entity,
  surface TEXT NOT NULL COLLATE NOCASE,
  alias_type TEXT NOT NULL CHECK (alias_type IN ('legal','former','brand','ticker_like','colloquial','title')),
  valid_from TEXT, valid_to TEXT,
  PRIMARY KEY (surface, entity_id, alias_type)) WITHOUT ROWID;
CREATE TABLE entity_link (                  -- Acme Markets brand_of Albertsons; Acme Corporation depicted_in the film
  from_entity INTEGER NOT NULL REFERENCES entity, to_entity INTEGER NOT NULL REFERENCES entity,
  type TEXT NOT NULL CHECK (type IN ('subsidiary_of','brand_of','depicted_in','acquired_by','successor_of')),
  valid_from TEXT, valid_to TEXT, origin TEXT NOT NULL,
  PRIMARY KEY (from_entity, type, to_entity)) WITHOUT ROWID;
CREATE TABLE mention (                      -- entity_id is the linker's ingest-time pick (may be NULL);
  mention_id INTEGER PRIMARY KEY,            -- what it resolves to over time is the ledger's
  version_id INTEGER NOT NULL REFERENCES version,   -- 'resolution' dimension
  entity_id  INTEGER REFERENCES entity,
  surface    TEXT NOT NULL,
  span_start INTEGER, span_end INTEGER,
  origin     TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0);
CREATE INDEX mention_entity ON mention (entity_id);
CREATE INDEX mention_version ON mention (version_id);
CREATE TABLE mention_candidate (            -- kept, not collapsed: AS_KNOWN before resolution enumerates them
  mention_id INTEGER NOT NULL REFERENCES mention,
  entity_id  INTEGER NOT NULL REFERENCES entity,
  score REAL, rank INTEGER NOT NULL,
  PRIMARY KEY (mention_id, entity_id)) WITHOUT ROWID;

CREATE TABLE claim (
  claim_id INTEGER PRIMARY KEY, text TEXT NOT NULL,
  modality TEXT NOT NULL DEFAULT 'asserted' CHECK (modality IN ('asserted','hedged','denied','in_universe')),
  subject_entity INTEGER REFERENCES entity,           -- when the subject is known at ingest
  subject_mention_id INTEGER REFERENCES mention,      -- when it is only a mention ("ACME")
  as_of TEXT);
CREATE TABLE evidence (
  claim_id   INTEGER NOT NULL REFERENCES claim,
  version_id INTEGER NOT NULL REFERENCES version,
  stance     TEXT NOT NULL CHECK (stance IN ('supports','refutes','mentions')),
  origin     TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (claim_id, version_id)) WITHOUT ROWID;

-- The core ledger names claims and mentions without a REFERENCES clause (they live here);
-- these triggers restore the integrity check once the pack is adopted.
CREATE TRIGGER assessment_claim_exists BEFORE INSERT ON assessment
WHEN NEW.claim_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM claim WHERE claim_id = NEW.claim_id)
BEGIN SELECT RAISE(ABORT, 'assessment.claim_id: no such claim'); END;
CREATE TRIGGER assessment_mention_exists BEFORE INSERT ON assessment
WHEN NEW.mention_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM mention WHERE mention_id = NEW.mention_id)
BEGIN SELECT RAISE(ABORT, 'assessment.mention_id: no such mention'); END;
CREATE TRIGGER assessment_publisher_is_publisher_mention BEFORE INSERT ON assessment
WHEN NEW.authority = 'publisher' AND NEW.mention_id IS NOT NULL
 AND (NEW.evidence_version_id IS NOT NULL OR NEW.evidence_link_id IS NOT NULL)
BEGIN
  SELECT RAISE(ABORT, 'authority=publisher but the evidence comes from another publisher')
  WHERE (SELECT d.publisher FROM mention m JOIN version v USING (version_id) JOIN unit u USING (unit_id)
           JOIN document d USING (document_id) WHERE m.mention_id = NEW.mention_id)
    IS NOT
        (SELECT d.publisher FROM document d WHERE d.document_id = coalesce(
           (SELECT u.document_id FROM version v JOIN unit u USING (unit_id) WHERE v.version_id = NEW.evidence_version_id),
           (SELECT u.document_id FROM link l JOIN unit u ON u.unit_id = l.from_unit WHERE l.link_id = NEW.evidence_link_id)));
END;

-- Effective resolution of each mention, and what each claim may support, under the clock.
CREATE VIEW mention_now AS
SELECT m.mention_id, m.version_id, m.surface, m.entity_id AS ingest_entity,
       coalesce(s.value, CASE WHEN m.entity_id IS NOT NULL THEN 'entity:' || m.entity_id ELSE 'unresolved' END) AS resolution,
       s.provisional, s.authority, s.flags,
       CASE WHEN s.value IS NULL THEN m.entity_id
            WHEN s.value GLOB 'entity:*' THEN CAST(substr(s.value, 8) AS INTEGER) END AS entity_id
FROM mention m
LEFT JOIN status_now s ON s.target_kind = 'mention' AND s.target_id = m.mention_id AND s.dimension = 'resolution';
-- A claim supports a REAL-WORLD answer only if its subject is a resolved real entity, its world
-- is 'real', it is not refuted, and it is not hedged or in-universe. status_now values are
-- decisions (non-provisional); provisional ones arrive as flags and only label the claim.
CREATE VIEW claim_now AS
WITH c AS (
  SELECT c.*, mn.resolution AS subject_resolution, mn.flags AS subject_flags,
         coalesce(c.subject_entity, mn.entity_id) AS subject_id,
         w.value AS w_value, w.provisional AS w_prov, w.flags AS w_flags,
         f.value AS f_value, f.provisional AS f_prov, f.flags AS f_flags
  FROM claim c
  LEFT JOIN mention_now mn ON mn.mention_id = c.subject_mention_id
  LEFT JOIN status_now w ON w.target_kind = 'claim' AND w.target_id = c.claim_id AND w.dimension = 'world'
  LEFT JOIN status_now f ON f.target_kind = 'claim' AND f.target_id = c.claim_id AND f.dimension = 'verification')
SELECT c.claim_id, c.text, c.modality, c.subject_id, e.name AS subject_name, e.reality AS subject_reality,
       c.subject_resolution, c.subject_flags,
       coalesce(c.w_value, 'real') AS world, c.w_prov AS world_provisional, c.w_flags AS world_flags,
       coalesce(c.f_value, 'unverified') AS verification, c.f_prov AS verification_provisional, c.f_flags AS verification_flags,
       CASE WHEN c.subject_id IS NULL OR e.reality <> 'real' THEN 'no'
            WHEN coalesce(c.w_value, 'real') <> 'real' THEN 'no'
            WHEN c.f_value = 'refuted' THEN 'no'
            WHEN c.modality = 'in_universe' THEN 'no'
            WHEN c.modality = 'hedged' OR c.w_flags IS NOT NULL OR c.f_flags IS NOT NULL
              OR coalesce(c.f_value, 'unverified') IN ('unverified','disputed','cannot_judge') THEN 'labelled'
            ELSE 'yes' END AS real_world_support
FROM c LEFT JOIN entity e ON e.entity_id = c.subject_id;

CREATE TABLE feedback (
  feedback_id INTEGER PRIMARY KEY,
  answer_id   INTEGER NOT NULL REFERENCES answer,
  label       TEXT,                         -- quotation label, when aimed at one citation
  signal      TEXT NOT NULL CHECK (signal IN ('thumb_up','thumb_down','copied','opened','corrected')),
  actor       TEXT NOT NULL, at TEXT NOT NULL);

-- ═══ Relationship rules pack: catalogue, detection keys, resolution, consequences ══
-- Layer 1 (relation semantics) = link_type, data seeded from link-types.yaml.
-- Layer 2 (detection) = per-source YAML profiles (profiles/*.yaml), hashed into
--   ingest_run.profile_sha256; they write `link` rows, possibly with a typed key target.
-- Layer 2b (resolution) = link_resolution: append-only, time-aware, order-independent.
-- Layer 3 (consequence) = rule_version rows (bodies compiled from consequences.yaml) read by
--   the derive_* views; apply.sql appends what the views say is missing and voids what no
--   longer holds (recompute-and-append). Nothing is ever updated.

CREATE TABLE key_scheme (                   -- typed keys a link may name its target by
  scheme TEXT PRIMARY KEY,
  level  TEXT NOT NULL CHECK (level IN ('document','unit')),
  shape  TEXT NOT NULL, example TEXT, note TEXT);
INSERT INTO key_scheme VALUES
  ('edgar:accession','document','accession','0001193125-26-102079','names one filing'),
  ('edgar:cik+form+period','document','cik|form|period','2098|10-K|2025-12-31','how Item 4.02 and /A amendments name their target: no accession is given'),
  ('edgar:cik+form+period+item','unit','cik|form|period|item','2098|10-K|2025-12-31|Item 3','Rule 12b-15 amends whole items'),
  ('sec:release','document','release number','34-96930',NULL),
  ('fr:doc','document','document_number','2017-06037',NULL),
  ('fr:cite','document','volume FR page','88 FR 13872',NULL),
  ('cfr','unit','title CFR part.section','17 CFR 240.15c6-1',NULL),
  ('celex','document','CELEX','32025R2075','corrigenda add R(nn)'),
  ('eli','document','ELI URI','http://data.europa.eu/eli/reg/2025/2075/oj',NULL),
  ('email:message-id','document','<id@host>','<rumour-0812@tallowmere.example>',NULL),
  ('email:thread-subject','document','normalised subject','acme?','heuristic: thread roots only'),
  ('slack:channel+ts','unit','channel|ts','C042ACME|1756642320.000100',NULL),
  ('note:id','document','frontmatter id','RN-FILM-001',NULL);

CREATE TABLE link_type (
  type TEXT PRIMARY KEY,
  inverse TEXT,                             -- derived, never stored
  scope TEXT NOT NULL CHECK (scope IN ('unit','document','claim')),
  effect TEXT NOT NULL CHECK (effect IN ('none','label','standing')),
  effect_on TEXT NOT NULL DEFAULT 'to' CHECK (effect_on IN ('to','from')),
  effect_value TEXT,                        -- default value; consequences decide per authority
  time_anchor TEXT CHECK (time_anchor IN ('link','target','emitter')),
  exclusion_requires TEXT NOT NULL DEFAULT '',   -- comma list of authorities that may exclude
  transitive INTEGER NOT NULL DEFAULT 0 CHECK (transitive = 0),  -- never transitive for status
  dcterms TEXT, cito TEXT, prov TEXT, crossmark TEXT, eli TEXT,  -- nearest names, export only
  note TEXT);
CREATE TRIGGER link_type_frozen_u BEFORE UPDATE ON link_type
BEGIN SELECT RAISE(ABORT, 'link_type rows are frozen: change effects with a new rule_version'); END;
CREATE TRIGGER link_type_frozen_d BEFORE DELETE ON link_type
BEGIN SELECT RAISE(ABORT, 'link_type rows are frozen'); END;
CREATE TRIGGER link_type_known BEFORE INSERT ON link
WHEN NOT EXISTS (SELECT 1 FROM link_type WHERE type = NEW.type)
BEGIN SELECT RAISE(ABORT, 'unknown link type (see link_type)'); END;

-- Rules as data, bitemporal. effective_from is VALID time (a law-like change applies from a
-- date); recorded_from is when we adopted the version. A 'fix' replaces the version it fixes
-- from its adoption; a 'new' version applies to valid times from its effective_from.
-- kind 'source_rule' is an owned, expiring source policy (CEL match + assigned value).
CREATE TABLE rule_version (
  rule_id        TEXT NOT NULL,             -- 'link-effect:do-not-rely', 'derive-resolves', 'edgar-filing-original'
  version_sha256 TEXT NOT NULL,             -- sha256 of body: cited by every row it derives
  kind           TEXT NOT NULL CHECK (kind IN ('detection','consequence','source_rule')),
  body_format    TEXT NOT NULL CHECK (body_format IN ('cel','sql','json','yaml')),
  body           TEXT NOT NULL,
  assigns        TEXT CHECK (assigns IS NULL OR json_valid(assigns)),  -- source_rule: {"dimension":..,"value":..}
  effective_from TEXT,                      -- valid time; NULL = from the beginning
  recorded_from  TEXT NOT NULL,             -- adoption (knowledge time)
  change_kind    TEXT NOT NULL CHECK (change_kind IN ('new','fix')),
  fixes_sha256   TEXT,                      -- the version a fix replaces
  owner          TEXT NOT NULL,
  review_by      TEXT,                      -- expiry: comes back as ONE renewal item, not N documents
  PRIMARY KEY (rule_id, version_sha256),
  FOREIGN KEY (rule_id, fixes_sha256) REFERENCES rule_version (rule_id, version_sha256),
  CHECK ((change_kind = 'fix') = (fixes_sha256 IS NOT NULL)),
  CHECK (kind <> 'source_rule' OR (review_by IS NOT NULL AND assigns IS NOT NULL))
) WITHOUT ROWID;
CREATE TRIGGER rule_version_no_update BEFORE UPDATE ON rule_version
BEGIN SELECT RAISE(ABORT, 'rule_version is append-only'); END;
CREATE TRIGGER rule_version_no_delete BEFORE DELETE ON rule_version
BEGIN SELECT RAISE(ABORT, 'rule_version is append-only'); END;
CREATE TRIGGER rule_version_fix_same_window BEFORE INSERT ON rule_version
WHEN NEW.change_kind = 'fix' AND NOT EXISTS (
  SELECT 1 FROM rule_version r WHERE r.rule_id = NEW.rule_id AND r.version_sha256 = NEW.fixes_sha256
    AND r.effective_from IS NEW.effective_from AND r.recorded_from < NEW.recorded_from)
BEGIN SELECT RAISE(ABORT, 'a fix keeps the fixed version''s effective_from and is adopted after it'); END;
-- The decision table, one row per consequence-table row, read from the hashed bodies.
CREATE VIEW consequence AS
SELECT rv.rule_id, rv.version_sha256, CAST(r.key AS INTEGER) AS priority,
       json_extract(rv.body, '$.link_type') AS link_type,
       json_extract(r.value, '$.authority') AS authority, json_extract(r.value, '$.origin') AS origin,
       json_extract(r.value, '$.min_confidence') AS min_confidence, json_extract(r.value, '$.outcome') AS outcome,
       json_extract(r.value, '$.dimension') AS dimension, json_extract(r.value, '$.value') AS value
FROM rule_version rv, json_each(rv.body, '$.rows') r
WHERE rv.kind = 'consequence' AND rv.body_format = 'json';
CREATE VIEW rule_window AS                  -- each version's knowledge-time end (when a fix replaced it)
SELECT r.rule_id, r.version_sha256, r.effective_from, r.recorded_from, r.change_kind,
       (SELECT min(f.recorded_from) FROM rule_version f
        WHERE f.rule_id = r.rule_id AND f.fixes_sha256 = r.version_sha256) AS fixed_at
FROM rule_version r WHERE r.kind = 'consequence' AND r.body_format = 'json';
CREATE VIEW source_rule_due AS              -- expired source rules: one renewal item each
SELECT r.rule_id, r.version_sha256, r.owner, r.review_by, r.assigns
FROM rule_version r JOIN clock c ON c.id = 1
WHERE r.kind = 'source_rule' AND r.review_by <= c.now_valid
  AND NOT EXISTS (SELECT 1 FROM rule_version f WHERE f.rule_id = r.rule_id AND f.recorded_from > r.recorded_from);

-- Binding a typed key to a unit or document, as of a time. Append-only. Two or more candidates
-- known at once -> an 'ambiguous' row, nothing bound, and an inbox item: never a guess.
CREATE TABLE link_resolution (
  resolution_id INTEGER PRIMARY KEY,
  link_id      INTEGER NOT NULL REFERENCES link,
  status       TEXT NOT NULL CHECK (status IN ('bound','ambiguous','void')),  -- void cancels what it supersedes
  to_unit      INTEGER REFERENCES unit,
  to_document  INTEGER REFERENCES document,
  candidates   INTEGER NOT NULL DEFAULT 1,
  resolver     TEXT NOT NULL,               -- 'resolve-key@<sha12>' or 'human:<id>'
  recorded_from TEXT NOT NULL,
  supersedes   INTEGER REFERENCES link_resolution,
  derivation_key TEXT UNIQUE,
  CHECK ((status = 'bound') = (to_unit IS NOT NULL OR to_document IS NOT NULL)),
  CHECK (to_unit IS NULL OR to_document IS NULL));
CREATE TRIGGER link_resolution_no_update BEFORE UPDATE ON link_resolution
BEGIN SELECT RAISE(ABORT, 'link_resolution is append-only'); END;
CREATE TRIGGER link_resolution_no_delete BEFORE DELETE ON link_resolution
BEGIN SELECT RAISE(ABORT, 'link_resolution is append-only'); END;

-- Why a derived row exists: its premises (links, resolutions, rule versions, mentions...).
CREATE TABLE justification (
  assessment_id INTEGER NOT NULL REFERENCES assessment,
  premise_kind  TEXT NOT NULL CHECK (premise_kind IN
                  ('link','resolution','rule','assessment','version','mention','claim','entity_link')),
  premise_ref   TEXT NOT NULL,              -- an id, or rule_id@sha
  PRIMARY KEY (assessment_id, premise_kind, premise_ref)) WITHOUT ROWID;

-- Source-time and valid-time starts, used by the resolver and by time anchors.
CREATE VIEW unit_time AS
SELECT unit_id, min(valid_from) AS valid_start, min(published_at) AS published, min(recorded_from) AS recorded
FROM version GROUP BY unit_id;
CREATE VIEW document_time AS
SELECT u.document_id, min(t.valid_start) AS valid_start, min(t.published) AS published, d.recorded_from AS recorded
FROM unit u JOIN unit_time t USING (unit_id) JOIN document d ON d.document_id = u.document_id
GROUP BY u.document_id;

-- RESOLVER (layer 2b). Candidates for a keyed link: identifier rows with the same scheme and
-- value, in another document published no later than the linking document (source time, so the
-- 10-K/A that an 8-K announces can never be its target). Knowledge time of a candidate = when
-- this KB recorded its document. Everything is a function of the inputs, so arrival order
-- does not matter.
CREATE VIEW resolve_key_candidate AS
SELECT DISTINCT l.link_id, l.recorded_from AS l_rec,
       CASE WHEN ks.level = 'document' OR lt.scope = 'document' THEN NULL ELSE i.unit_id END AS to_unit,
       CASE WHEN ks.level = 'document' OR lt.scope = 'document' THEN u.document_id END AS to_document,
       d.recorded_from AS c_rec
FROM link l
JOIN identifier i ON i.scheme = l.to_key_scheme AND i.value = l.to_key
JOIN unit u ON u.unit_id = i.unit_id
JOIN document d ON d.document_id = u.document_id
JOIN unit fu ON fu.unit_id = l.from_unit
JOIN link_type lt ON lt.type = l.type
LEFT JOIN key_scheme ks ON ks.scheme = l.to_key_scheme
LEFT JOIN document_time ct ON ct.document_id = u.document_id
LEFT JOIN document_time et ON et.document_id = fu.document_id
WHERE l.to_key IS NOT NULL AND u.document_id <> fu.document_id
  AND (ct.published IS NULL OR et.published IS NULL OR ct.published <= et.published);
CREATE VIEW desired_link_resolution AS
WITH c AS (
  SELECT k.*, ROW_NUMBER() OVER (PARTITION BY k.link_id ORDER BY k.c_rec, k.to_document, k.to_unit) AS n,
         COUNT(*) OVER (PARTITION BY k.link_id) AS total
  FROM resolve_key_candidate k),
first AS (SELECT * FROM c WHERE n = 1),
second AS (SELECT link_id, c_rec AS rec2 FROM c WHERE n = 2)
SELECT 'bind' AS kind, f.link_id, f.to_unit, f.to_document, 1 AS candidates,
       max(f.l_rec, f.c_rec) AS recorded_from,
       'res|L' || f.link_id || '|' || coalesce('U' || f.to_unit, 'D' || f.to_document) AS derivation_key
FROM first f LEFT JOIN second s USING (link_id)
WHERE s.rec2 IS NULL OR max(f.l_rec, f.c_rec) < max(f.l_rec, s.rec2)
UNION ALL
SELECT 'ambiguous', f.link_id, NULL, NULL, f.total, max(f.l_rec, s.rec2),
       'res|L' || f.link_id || '|ambiguous'
FROM first f JOIN second s USING (link_id);

-- Each link's bound target over knowledge time [k_start, k_end): direct targets for the link's
-- life, keyed targets from the binding until it is superseded or the link is withdrawn.
CREATE VIEW link_binding AS
SELECT l.link_id, NULL AS resolution_id, l.to_unit, l.to_document,
       l.recorded_from AS k_start, l.recorded_to AS k_end
FROM link l WHERE l.to_unit IS NOT NULL OR l.to_document IS NOT NULL
UNION ALL
SELECT r.link_id, r.resolution_id, r.to_unit, r.to_document,
       max(l.recorded_from, r.recorded_from) AS k_start,
       nullif(min(coalesce(l.recorded_to, '9999'),
                  coalesce((SELECT min(s.recorded_from) FROM link_resolution s WHERE s.supersedes = r.resolution_id), '9999')),
              '9999') AS k_end
FROM link_resolution r JOIN link l ON l.link_id = r.link_id
WHERE r.status = 'bound';

-- CONSEQUENCE (layer 3), generic and table-driven: link x binding x link_type x consequence
-- version. The emitter's authority is computed from the data, not asserted. Each derived row
-- carries its knowledge-time window: it starts when its last premise became known and ends
-- when a premise is withdrawn, its binding is superseded, its rule version is fixed, or a later
-- effective-dated version covers its whole valid period. apply.sql appends the start rows and
-- 'void' rows at the ends.
CREATE VIEW derive_link_effect AS
WITH b AS (
  SELECT lb.link_id, lb.resolution_id, lb.to_unit, lb.k_start, lb.k_end,
         l.type, l.from_unit, l.origin, l.confidence, l.valid_from AS link_valid,
         lt.scope, lt.effect_on, lt.time_anchor, lt.exclusion_requires,
         fu.document_id AS from_doc, coalesce(lb.to_document, tu.document_id) AS to_doc
  FROM link_binding lb
  JOIN link l ON l.link_id = lb.link_id
  JOIN link_type lt ON lt.type = l.type
  JOIN unit fu ON fu.unit_id = l.from_unit
  LEFT JOIN unit tu ON tu.unit_id = lb.to_unit
  WHERE lt.effect <> 'none' AND lt.scope <> 'claim'),
t AS (
  SELECT b.*,
    CASE WHEN b.effect_on = 'to' THEN CASE WHEN b.scope = 'document' THEN NULL ELSE b.to_unit END
         ELSE CASE WHEN b.scope = 'document' THEN NULL ELSE b.from_unit END END AS t_unit,
    CASE WHEN b.effect_on = 'to' THEN CASE WHEN b.scope = 'document' OR b.to_unit IS NULL THEN b.to_doc END
         ELSE CASE WHEN b.scope = 'document' THEN b.from_doc END END AS t_doc,
    CASE WHEN b.origin = 'human' THEN 'human'
         WHEN b.origin = 'model' THEN 'model'
         WHEN fd.publisher IS NOT NULL AND fd.publisher = td.publisher THEN 'publisher'
         WHEN b.origin IN ('markup','status+link') AND fd.force IN ('binding','official') THEN 'markup'
         ELSE 'heuristic' END AS authority,
    CASE b.time_anchor WHEN 'link' THEN b.link_valid
         WHEN 'target' THEN coalesce(tut.valid_start, tdt.valid_start)
         WHEN 'emitter' THEN fut.valid_start END AS anchor
  FROM b
  JOIN document fd ON fd.document_id = b.from_doc
  JOIN document td ON td.document_id = b.to_doc
  LEFT JOIN unit_time tut ON tut.unit_id = b.to_unit
  LEFT JOIN document_time tdt ON tdt.document_id = b.to_doc
  LEFT JOIN unit_time fut ON fut.unit_id = b.from_unit),
v AS (
  SELECT t.*, rw.rule_id, rw.version_sha256, rw.recorded_from AS v_rec, rw.fixed_at, rw.effective_from AS v_eff,
    CASE WHEN t.anchor IS NULL THEN rw.effective_from
         WHEN rw.effective_from IS NULL THEN t.anchor
         ELSE max(t.anchor, rw.effective_from) END AS d_valid
  FROM t JOIN rule_window rw ON rw.rule_id = 'link-effect:' || t.type),
w AS (
  SELECT v.*,
    (SELECT min(s.recorded_from) FROM rule_version s
     WHERE s.rule_id = v.rule_id AND s.kind = 'consequence'
       AND coalesce(s.effective_from, '') > coalesce(v.v_eff, '')
       AND coalesce(s.effective_from, '') <= coalesce(v.d_valid, '')) AS shadowed_at
  FROM v),
m AS (
  SELECT w.*, c.outcome, c.dimension, c.value,
    ROW_NUMBER() OVER (PARTITION BY w.link_id, w.resolution_id, w.rule_id, w.version_sha256
                       ORDER BY c.priority) AS rn
  FROM w JOIN consequence c ON c.rule_id = w.rule_id AND c.version_sha256 = w.version_sha256
   AND (c.authority = '*' OR c.authority = w.authority)
   AND (c.origin = '*' OR c.origin = w.origin)
   AND w.confidence >= c.min_confidence),
d AS (
  SELECT m.*, sv.supports, sv.official,
    max(m.k_start, m.v_rec) AS recorded_from,
    nullif(min(coalesce(m.k_end, '9999'), coalesce(m.fixed_at, '9999'), coalesce(m.shadowed_at, '9999')), '9999') AS recorded_until
  FROM m LEFT JOIN status_value sv ON sv.dimension = m.dimension AND m.value GLOB sv.value
  WHERE m.rn = 1 AND m.outcome <> 'none')
SELECT d.t_doc AS document_id, d.t_unit AS unit_id, NULL AS claim_id, NULL AS mention_id,
  d.dimension, d.value,
  CASE WHEN d.supports = 'no' OR d.official = 0 THEN 'demote' ELSE 'lateral' END AS direction,
  CASE WHEN d.outcome = 'label' THEN 1
       WHEN (d.supports = 'no' OR d.official = 0)
            AND instr(',' || d.exclusion_requires || ',', ',' || d.authority || ',') = 0 THEN 1
       ELSE 0 END AS provisional,
  d.d_valid AS valid_from, d.recorded_from, d.recorded_until,
  d.authority, d.rule_id, d.version_sha256 AS rule_sha256,
  d.link_id AS evidence_link_id,
  (SELECT max(x.version_id) FROM version x WHERE x.unit_id = d.from_unit AND x.recorded_from <= d.recorded_from) AS evidence_version_id,
  d.confidence,
  d.rule_id || '@' || substr(d.version_sha256, 1, 12) || '|L' || d.link_id || '|R' || coalesce(d.resolution_id, '-')
    || '|' || coalesce('U' || d.t_unit, 'D' || d.t_doc) AS derivation_key,
  json_array(json_object('kind', 'link', 'ref', CAST(d.link_id AS TEXT)),
             json_object('kind', 'rule', 'ref', d.rule_id || '@' || d.version_sha256),
             json_object('kind', 'rule', 'ref', 'derive-link-effect@' ||
               coalesce((SELECT version_sha256 FROM rule_version WHERE rule_id = 'derive-link-effect'
                         ORDER BY recorded_from DESC LIMIT 1), '?')),
             json_object('kind', 'resolution', 'ref', coalesce(CAST(d.resolution_id AS TEXT), 'direct'))) AS premises,
  d.resolution_id,
  'link ' || d.type || ' (' || d.origin || ', ' || d.authority || ')' AS rationale
FROM d WHERE d.recorded_until IS NULL OR d.recorded_until > d.recorded_from;

-- CONSEQUENCE, claim level: a 'resolves' link from a later message to the message holding a
-- hedged claim. If the later message names a creative work (mention -> creative_work entity)
-- and one of the hedged claim's subject candidates is depicted in that work, then: the
-- mention resolves to that candidate, the claim's world becomes the work's universe, and its
-- real-world reading is refuted. Whether these are provisional comes from
-- link-effect:resolves. The resolved message's own standing is never touched.
CREATE VIEW derive_resolves AS
WITH b AS (
  SELECT lb.link_id, lb.resolution_id, lb.to_unit, lb.k_start, lb.k_end,
         l.from_unit, l.origin, l.confidence, fu.document_id AS from_doc, tu.document_id AS to_doc
  FROM link_binding lb JOIN link l ON l.link_id = lb.link_id
  JOIN unit fu ON fu.unit_id = l.from_unit
  JOIN unit tu ON tu.unit_id = coalesce(lb.to_unit,
       (SELECT min(x.unit_id) FROM unit x WHERE x.document_id = lb.to_document))
  WHERE l.type = 'resolves'),
work AS (
  SELECT b.link_id, m2.mention_id AS work_mention, m2.entity_id AS work_id, v2.recorded_from AS w_rec
  FROM b JOIN version v2 ON v2.unit_id = b.from_unit
  JOIN mention m2 ON m2.version_id = v2.version_id
  JOIN entity e ON e.entity_id = m2.entity_id AND e.kind = 'creative_work'),
hit AS (
  SELECT b.*, work.work_id, work.work_mention, work.w_rec, cl.claim_id, cl.subject_mention_id AS mention_id,
         mc.entity_id AS referent_id, v1.recorded_from AS c_rec,
         CASE WHEN b.origin = 'human' THEN 'human' WHEN b.origin = 'model' THEN 'model'
              WHEN fd.publisher IS NOT NULL AND fd.publisher = td.publisher THEN 'publisher'
              ELSE 'heuristic' END AS authority
  FROM b JOIN work USING (link_id)
  JOIN document fd ON fd.document_id = b.from_doc JOIN document td ON td.document_id = b.to_doc
  JOIN unit tu ON tu.document_id = b.to_doc
  JOIN version v1 ON v1.unit_id = tu.unit_id
  JOIN evidence ev ON ev.version_id = v1.version_id
  JOIN claim cl ON cl.claim_id = ev.claim_id AND cl.modality = 'hedged'
  JOIN mention_candidate mc ON mc.mention_id = cl.subject_mention_id
  JOIN entity_link el ON el.from_entity = mc.entity_id AND el.type = 'depicted_in' AND el.to_entity = work.work_id),
v AS (
  SELECT hit.*, rw.rule_id, rw.version_sha256, rw.recorded_from AS v_rec, rw.fixed_at, rw.effective_from AS v_eff
  FROM hit JOIN rule_window rw ON rw.rule_id = 'link-effect:resolves'),
m AS (
  SELECT v.*, c.outcome,
    ROW_NUMBER() OVER (PARTITION BY v.link_id, v.resolution_id, v.claim_id, v.referent_id, v.rule_id, v.version_sha256
                       ORDER BY c.priority) AS rn
  FROM v JOIN consequence c ON c.rule_id = v.rule_id AND c.version_sha256 = v.version_sha256
   AND (c.authority = '*' OR c.authority = v.authority) AND (c.origin = '*' OR c.origin = v.origin)
   AND v.confidence >= c.min_confidence),
d AS (
  SELECT m.*, max(m.k_start, m.v_rec, m.w_rec, m.c_rec) AS recorded_from,
    nullif(min(coalesce(m.k_end, '9999'), coalesce(m.fixed_at, '9999')), '9999') AS recorded_until
  FROM m WHERE m.rn = 1 AND m.outcome <> 'none'),
e AS (
  SELECT d.*, x.dimension, x.value, x.direction, x.target FROM d,
  (SELECT 'resolution' AS dimension, 'lateral' AS direction, 'mention' AS target, NULL AS value
   UNION ALL SELECT 'world', 'lateral', 'claim', NULL
   UNION ALL SELECT 'verification', 'demote', 'claim', 'refuted') x)
SELECT NULL AS document_id, NULL AS unit_id,
  CASE WHEN e.target = 'claim' THEN e.claim_id END AS claim_id,
  CASE WHEN e.target = 'mention' THEN e.mention_id END AS mention_id,
  e.dimension,
  CASE e.dimension WHEN 'resolution' THEN 'entity:' || e.referent_id
                   WHEN 'world' THEN 'universe:' || e.work_id ELSE e.value END AS value,
  e.direction,
  CASE WHEN e.outcome = 'apply' THEN 0 ELSE 1 END AS provisional,
  NULL AS valid_from, e.recorded_from, e.recorded_until,
  e.authority, e.rule_id, e.version_sha256 AS rule_sha256,
  e.link_id AS evidence_link_id,
  (SELECT max(x.version_id) FROM version x WHERE x.unit_id = e.from_unit AND x.recorded_from <= e.recorded_from) AS evidence_version_id,
  e.confidence,
  e.rule_id || '@' || substr(e.version_sha256, 1, 12) || '|L' || e.link_id || '|R' || coalesce(e.resolution_id, '-')
    || '|' || CASE WHEN e.target = 'claim' THEN 'C' || e.claim_id ELSE 'M' || e.mention_id END || '|' || e.dimension AS derivation_key,
  json_array(json_object('kind', 'link', 'ref', CAST(e.link_id AS TEXT)),
             json_object('kind', 'rule', 'ref', e.rule_id || '@' || e.version_sha256),
             json_object('kind', 'rule', 'ref', 'derive-resolves@' ||
               coalesce((SELECT version_sha256 FROM rule_version WHERE rule_id = 'derive-resolves'
                         ORDER BY recorded_from DESC LIMIT 1), '?')),
             json_object('kind', 'mention', 'ref', CAST(e.work_mention AS TEXT)),
             json_object('kind', 'claim', 'ref', CAST(e.claim_id AS TEXT))) AS premises,
  e.resolution_id,
  CASE e.dimension WHEN 'verification' THEN 'true only in-universe' ELSE 'resolved by a later message' END AS rationale
FROM e WHERE e.recorded_until IS NULL OR e.recorded_until > e.recorded_from;

CREATE VIEW desired_assessment AS
SELECT * FROM derive_link_effect
UNION ALL
SELECT * FROM derive_resolves;

-- ── Reading the ledger ───────────────────────────────────────────────────
-- One sentence per row, for the document-detail timeline and for explanations.
CREATE VIEW assessment_explain AS
SELECT a.assessment_id, a.target_kind, a.target_id, a.dimension, a.value, a.provisional, a.recorded_from, a.rule_id,
  a.dimension || '=' || a.value || CASE WHEN a.provisional = 1 THEN ' (provisional)' ELSE '' END
  || coalesce(' since ' || a.valid_from, '') || ' (known ' || a.recorded_from || ')'
  || ' by ' || a.method || '/' || a.authority || ' ' || a.rated_by
  || coalesce(' because ' || l.type || ' from "' || coalesce(d.title, d.path) || '" ('
              || l.origin || ', ' || printf('%.2f', l.confidence) || ')', '')
  || coalesce(' under ' || a.rule_id || '@' || substr(a.rule_sha256, 1, 7), '')
  || coalesce('; resolved via ' || l.to_key_scheme || ' ' || l.to_key, '')
  || CASE WHEN a.supersedes IS NOT NULL THEN '; supersedes #' || a.supersedes ELSE '' END AS sentence
FROM assessment a
LEFT JOIN link l ON l.link_id = a.evidence_link_id
LEFT JOIN unit u ON u.unit_id = l.from_unit
LEFT JOIN document d ON d.document_id = u.document_id;
-- Links still waiting for their target (or ambiguous), as known now: inbox candidates.
CREATE VIEW link_pending AS
SELECT l.link_id, l.type, l.to_key_scheme, l.to_key, l.recorded_from,
       (SELECT r.status FROM link_resolution r WHERE r.link_id = l.link_id AND r.recorded_from <= c.now_recorded
        ORDER BY r.recorded_from DESC, r.resolution_id DESC LIMIT 1) AS last_resolution
FROM link l JOIN clock c ON c.id = 1
WHERE l.to_key IS NOT NULL AND l.recorded_from <= c.now_recorded
  AND (l.recorded_to IS NULL OR l.recorded_to > c.now_recorded)
  AND NOT EXISTS (SELECT 1 FROM link_binding b WHERE b.link_id = l.link_id
                  AND b.k_start <= c.now_recorded AND (b.k_end IS NULL OR b.k_end > c.now_recorded));
-- Follow supersession to the current head at query time (not transitive for status).
-- UNION (not UNION ALL) makes the walk terminate on cycles; a cycle has no head.
CREATE VIEW supersession_edge AS
SELECT CASE l.type WHEN 'supersedes' THEN b.to_unit ELSE l.from_unit END AS old_unit,
       CASE l.type WHEN 'supersedes' THEN l.from_unit ELSE b.to_unit END AS new_unit
FROM link l JOIN link_binding b ON b.link_id = l.link_id JOIN clock c ON c.id = 1
WHERE l.type IN ('supersedes','superseded-by') AND b.to_unit IS NOT NULL
  AND b.k_start <= c.now_recorded AND (b.k_end IS NULL OR b.k_end > c.now_recorded)
  AND (l.valid_from IS NULL OR l.valid_from <= c.now_valid);
CREATE VIEW supersession_head AS
WITH RECURSIVE walk(start_unit, unit_id) AS (
  SELECT old_unit, new_unit FROM supersession_edge
  UNION
  SELECT w.start_unit, e.new_unit FROM walk w JOIN supersession_edge e ON e.old_unit = w.unit_id)
SELECT start_unit, unit_id AS head_unit FROM walk
WHERE NOT EXISTS (SELECT 1 FROM supersession_edge e WHERE e.old_unit = walk.unit_id);

-- ═══ Operations: the work queue (the kanban is a GROUP BY) and answer recall ════
CREATE TABLE work_item (
  doc_key       TEXT NOT NULL,              -- raw sha256 (url before fetch)
  stage         TEXT NOT NULL CHECK (stage IN ('acquire','land','parse','normalise','classify','version',
                                               'relate','resolve','derive','enrich','embed','index')),
  ingest_run_id INTEGER NOT NULL REFERENCES ingest_run,
  state         TEXT NOT NULL DEFAULT 'pending' CHECK (state IN
                  ('pending','running','done','failed','quarantined','review','skipped')),
  input_hash    TEXT, output_hash TEXT,     -- skip when a 'done' row has the same input hash + stage code
  attempts      INTEGER NOT NULL DEFAULT 0,
  lease_until   TEXT,                       -- claim: UPDATE ... SET state='running' ... RETURNING
  error_class   TEXT, error TEXT,
  quarantine_reason TEXT,                   -- 'unclassifiable-arrival-path', 'ambiguous-target'
  suggestions   TEXT CHECK (suggestions IS NULL OR json_valid(suggestions)),  -- ranked, with feature checks
  updated_at    TEXT NOT NULL,
  PRIMARY KEY (doc_key, stage, ingest_run_id)) WITHOUT ROWID;
CREATE INDEX work_item_board ON work_item (stage, state);
-- the board: SELECT stage, state, count(*) FROM work_item GROUP BY 1, 2;

CREATE TABLE answer_recheck (               -- answers whose context was later demoted
  recheck_id    INTEGER PRIMARY KEY,
  answer_id     INTEGER NOT NULL REFERENCES answer,
  trigger_assessment_id INTEGER NOT NULL REFERENCES assessment,
  exposure      TEXT NOT NULL CHECK (exposure IN ('cited','context_only')),
  found_at      TEXT NOT NULL,
  outcome       TEXT NOT NULL CHECK (outcome IN ('pending','unchanged','changed','withdrawn')),
  replay_answer_id INTEGER REFERENCES answer);
CREATE VIEW answer_exposure AS              -- the join that finds them
SELECT DISTINCT ac.answer_id, a.assessment_id AS trigger_assessment_id,
  CASE WHEN EXISTS (SELECT 1 FROM quotation q WHERE q.answer_id = ac.answer_id AND q.version_id = ac.version_id)
       THEN 'cited' ELSE 'context_only' END AS exposure
FROM answer_context ac JOIN answer an ON an.answer_id = ac.answer_id
JOIN version v ON v.version_id = ac.version_id JOIN unit u ON u.unit_id = v.unit_id
JOIN assessment a ON a.direction = 'demote' AND a.recorded_from > an.asked_at
 AND ((a.target_kind = 'version' AND a.target_id = v.version_id) OR (a.target_kind = 'unit' AND a.target_id = v.unit_id)
   OR (a.target_kind = 'document' AND a.target_id = u.document_id));

-- ═══ Governance pack: personal data, retention, holds, erasure ════════════
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

-- ═══ Seed: link types and consequence rules ═════════════════════════════════
-- Generated by tests/gen_seed.py from link-types.yaml and consequences.yaml; bodies are canonical JSON and
-- version_sha256 = sha256(body). Seed versions are dated 2026-01-01, the start of the
-- simulated knowledge base; a deployment records its own adoption date.
-- BEGIN GENERATED SEED
-- link types (link-types.yaml)
INSERT INTO link_type VALUES
  ('amends', 'amended-by', 'unit', 'label', 'to', 'amended', 'link', 'publisher,markup,human', 0, NULL, 'cito:updates', 'prov:wasRevisionOf', NULL, 'eli:amends', '10-K/A (Rule 12b-15 restates whole items); ELI amends. The amended text arrives as its own version.'),
  ('corrects', 'corrected-by', 'unit', 'label', 'to', 'corrected', 'link', 'publisher,markup,human', 0, NULL, 'cito:corrects', NULL, 'correction', 'eli:corrects', 'FR correction_of, ELI corrects, Crossmark correction. Unofficial (email) corrections act on claims, never on documents.'),
  ('supersedes', 'superseded-by', 'unit', 'standing', 'to', 'superseded', 'link', 'publisher,markup,human', 0, 'dcterms:replaces', NULL, NULL, NULL, NULL, 'Stored on the newer item. Valid from adoption of the superseding text, not its compliance date.'),
  ('superseded-by', 'supersedes', 'unit', 'standing', 'from', 'superseded', 'link', 'publisher,markup,human', 0, 'dcterms:isReplacedBy', NULL, NULL, NULL, NULL, 'v1 type (spectastic). Stored on the older item; the effect lands on that item.'),
  ('do-not-rely', NULL, 'document', 'standing', 'to', 'do_not_rely', 'target', 'publisher', 0, NULL, NULL, 'prov:wasInvalidatedBy (closest)', 'expression_of_concern (closest)', NULL, '8-K Item 4.02. The 8-K names its target by form and period in prose, never by accession, so the link carries an edgar:cik+form+period key.'),
  ('restates', 'restated-by', 'unit', 'standing', 'to', 'restated', 'target', 'publisher', 0, NULL, NULL, 'prov:wasRevisionOf', NULL, NULL, '10-K/A or 10-Q/A whose amendment restates financial statements; closes the do-not-rely window.'),
  ('repeals', 'repealed-by', 'unit', 'standing', 'to', 'repealed', 'link', 'publisher,markup,human', 0, NULL, NULL, NULL, NULL, 'eli:repeals', 'ELI repeals; valid from the repeal''s date of effect.'),
  ('consolidates', 'consolidated-by', 'document', 'none', 'to', NULL, NULL, '', 0, NULL, NULL, NULL, NULL, 'eli:consolidates', 'A consolidated text is a point-in-time copy: ingest it with authenticity=copy.'),
  ('refers-to', 'referred-to-by', 'unit', 'none', 'to', NULL, NULL, '', 0, 'dcterms:references', 'cito:citesAsRelated', NULL, NULL, NULL, 'v1 type. NT 10-K -> later 10-K also uses it: anticipation is not supersession.'),
  ('replies-to', 'replied-to-by', 'unit', 'none', 'to', NULL, NULL, '', 0, NULL, 'cito:repliesTo', NULL, NULL, NULL, 'In-Reply-To/References, Slack thread_ts != ts, Teams replyToId. Ordering only, never supersession.'),
  ('resolves', 'resolved-by', 'claim', 'label', 'to', NULL, 'link', 'human', 0, NULL, NULL, NULL, NULL, NULL, 'A later message resolves a hedged claim or query in the target. Effects land on claims and mentions (world, verification, resolution), computed by derive_resolves; provisional until a human confirms. The target document''s standing never changes.'),
  ('same-thread-candidate', 'same-thread-candidate', 'unit', 'none', 'to', NULL, NULL, '', 0, NULL, NULL, NULL, NULL, NULL, 'Subject-only thread match (normalised subject, participants, window). A suggestion for the inbox, nothing more.'),
  ('quotes', 'quoted-by', 'unit', 'none', 'to', NULL, NULL, '', 0, NULL, 'cito:includesQuotationFrom', NULL, NULL, NULL, 'Forwards and inline quotes. Never replies-to, never supersedes.'),
  ('duplicates', 'duplicates', 'unit', 'none', 'to', NULL, NULL, '', 0, NULL, NULL, NULL, NULL, NULL, 'Near-duplicate; clusters live in version_dup and are collapsed before top-k.'),
  ('cites', 'cited-by', 'unit', 'none', 'to', NULL, NULL, '', 0, 'dcterms:references', 'cito:cites', NULL, NULL, NULL, 'v1 type.'),
  ('validates', 'validated-by', 'unit', 'none', 'to', NULL, NULL, '', 0, NULL, NULL, NULL, NULL, NULL, 'v1 type (spectastic: a test or check validates a requirement).'),
  ('defers-to', 'deferred-to-by', 'unit', 'none', 'to', NULL, NULL, '', 0, NULL, NULL, NULL, NULL, NULL, 'v1 type (spectastic).'),
  ('parent', 'child', 'unit', 'none', 'to', NULL, NULL, '', 0, 'dcterms:isPartOf', NULL, NULL, NULL, NULL, 'v1 structural type.'),
  ('revises', 'revised-by', 'unit', 'none', 'to', NULL, NULL, '', 0, 'dcterms:isVersionOf', NULL, 'prov:wasRevisionOf', NULL, NULL, 'v1 type, kept with no status effect so v1 behaviour is unchanged. New adapters emit amends, corrects or restates.');
-- consequence rules (consequences.yaml), one rule per link type
INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, effective_from, recorded_from, change_kind, owner, review_by) VALUES
  ('link-effect:amends', 'd8b6ebb3ea339c66f02fac19d5944826da0f9c761a7aaaa142702a2bd64a3357', 'consequence', 'json', '{"link_type":"amends","rows":[{"authority":"publisher","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"amended"},{"authority":"markup","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"amended"},{"authority":"human","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"amended"},{"authority":"*","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"label","value":"amended"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'),
  ('link-effect:corrects', '99b8abb80898d31f71053f3f918237eaa8c30763661ace59cd105774b31dcbcd', 'consequence', 'json', '{"link_type":"corrects","rows":[{"authority":"publisher","dimension":"standing","min_confidence":0.0,"origin":"prose-pattern","outcome":"none","value":"corrected"},{"authority":"publisher","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"corrected"},{"authority":"markup","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"corrected"},{"authority":"human","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"corrected"},{"authority":"*","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"label","value":"corrected"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'),
  ('link-effect:supersedes', '88789a98f5e9965d07252e39cc38e7ed5c8d1f22d278e35eb53fb493f3abce67', 'consequence', 'json', '{"link_type":"supersedes","rows":[{"authority":"publisher","dimension":"standing","min_confidence":0.8,"origin":"*","outcome":"apply","value":"superseded"},{"authority":"markup","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"superseded"},{"authority":"human","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"superseded"},{"authority":"*","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"label","value":"superseded"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'),
  ('link-effect:superseded-by', 'dd5058824ca6982b8de5638d9fdc46940054ee32f7b7954d68eeb83bb90290aa', 'consequence', 'json', '{"link_type":"superseded-by","rows":[{"authority":"publisher","dimension":"standing","min_confidence":0.8,"origin":"*","outcome":"apply","value":"superseded"},{"authority":"markup","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"superseded"},{"authority":"human","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"superseded"},{"authority":"*","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"label","value":"superseded"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'),
  ('link-effect:do-not-rely', 'e92b03f29609be73b6131ed58432a071987dc0bcc797b049b450283717a1abc1', 'consequence', 'json', '{"link_type":"do-not-rely","rows":[{"authority":"publisher","dimension":"standing","min_confidence":0.8,"origin":"*","outcome":"apply","value":"do_not_rely"},{"authority":"*","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"label","value":"do_not_rely"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'),
  ('link-effect:restates', '9aab60aee42cbbf35ba5d3dd62c1fbffaa9e41405102823fee93df67cebf10aa', 'consequence', 'json', '{"link_type":"restates","rows":[{"authority":"publisher","dimension":"standing","min_confidence":0.8,"origin":"*","outcome":"apply","value":"restated"},{"authority":"*","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"label","value":"restated"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'),
  ('link-effect:repeals', 'dd0ba4c093c8c352da24d8c2cd59facbe2fb2cc19ad9eb02830a632e2e32df9b', 'consequence', 'json', '{"link_type":"repeals","rows":[{"authority":"publisher","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"repealed"},{"authority":"markup","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"repealed"},{"authority":"human","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"apply","value":"repealed"},{"authority":"*","dimension":"standing","min_confidence":0.0,"origin":"*","outcome":"label","value":"repealed"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'),
  ('link-effect:resolves', '79d948d60a1befd34ae068a62f11935bdb3cc2ce764238944a715b5b9abbb98e', 'consequence', 'json', '{"link_type":"resolves","rows":[{"authority":"human","dimension":"*","min_confidence":0.0,"origin":"*","outcome":"apply","value":"*"},{"authority":"*","dimension":"*","min_confidence":0.5,"origin":"*","outcome":"label","value":"*"},{"authority":"*","dimension":"*","min_confidence":0.0,"origin":"*","outcome":"none","value":"*"}]}', NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14');
-- SQL-bodied rules: the installed view is the rule; sha256 of sqlite_master.sql pinned here
INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, effective_from, recorded_from, change_kind, owner, review_by)
SELECT 'resolve-key', '68dacf7ce8823c4bf6ee7726c3ca2b60a15efc1a9a53624129aa6b6d0284032b', 'detection', 'sql', sql, NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'
FROM sqlite_master WHERE type = 'view' AND name = 'desired_link_resolution';
INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, effective_from, recorded_from, change_kind, owner, review_by)
SELECT 'derive-link-effect', '31f4a1a47c4af98cf50385e895598a83e7196e8f68259e944d49c959a4bcfb42', 'consequence', 'sql', sql, NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'
FROM sqlite_master WHERE type = 'view' AND name = 'derive_link_effect';
INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, effective_from, recorded_from, change_kind, owner, review_by)
SELECT 'derive-resolves', '2af19a3055601a77d5ab04b59a04807b27421e69d7f4f07781b1b181ff3c0c76', 'consequence', 'sql', sql, NULL, '2026-01-01T00:00:00Z', 'new', 'kb-schema', '2027-04-14'
FROM sqlite_master WHERE type = 'view' AND name = 'derive_resolves';
-- END GENERATED SEED
