-- Rule apply step, v2: recompute-and-append. Run after every ingest run and after every new
-- rule_version, inside one transaction. Requires schema.sql + extensions.sql.
--
-- Idempotent: every derived row has a deterministic derivation_key, so running this twice adds
-- nothing. Order-independent: every derived time is a function of input times (when the KB
-- recorded each premise, when each rule version was adopted), never of when this ran. Derived
-- rows therefore carry the knowledge time at which their last premise arrived; in live
-- operation that is the same ingest run, and a backfill reproduces the same history.
-- Nothing is updated or deleted: a derivation that stops holding gets a 'void' row.

-- 1. Bind keyed links whose target has arrived (exactly one candidate known).
INSERT INTO link_resolution (link_id, status, to_unit, to_document, candidates, resolver, recorded_from, derivation_key)
SELECT d.link_id, 'bound', d.to_unit, d.to_document, 1,
       'resolve-key@' || coalesce((SELECT substr(version_sha256, 1, 12) FROM rule_version
                                   WHERE rule_id = 'resolve-key' ORDER BY recorded_from DESC LIMIT 1), '?'),
       d.recorded_from, d.derivation_key
FROM desired_link_resolution d
WHERE d.kind = 'bind'
  AND NOT EXISTS (SELECT 1 FROM link_resolution r WHERE r.derivation_key = d.derivation_key);

-- 2. A second candidate makes the key ambiguous: nothing bound from then on (inbox item).
INSERT INTO link_resolution (link_id, status, candidates, resolver, recorded_from, supersedes, derivation_key)
SELECT d.link_id, 'ambiguous', d.candidates,
       'resolve-key@' || coalesce((SELECT substr(version_sha256, 1, 12) FROM rule_version
                                   WHERE rule_id = 'resolve-key' ORDER BY recorded_from DESC LIMIT 1), '?'),
       d.recorded_from,
       (SELECT r.resolution_id FROM link_resolution r WHERE r.link_id = d.link_id AND r.status = 'bound'
          AND r.resolver NOT LIKE 'human:%' AND r.recorded_from < d.recorded_from
        ORDER BY r.recorded_from DESC LIMIT 1),
       d.derivation_key
FROM desired_link_resolution d
WHERE d.kind = 'ambiguous'
  AND NOT EXISTS (SELECT 1 FROM link_resolution r WHERE r.derivation_key = d.derivation_key);

-- 2b. Orphan bindings (made while a candidate recorded earlier had not been processed yet):
--     cancelled as of the clock. Never happens when documents are processed in the order
--     the KB records them, which live ingestion guarantees.
INSERT INTO link_resolution (link_id, status, candidates, resolver, recorded_from, supersedes, derivation_key)
SELECT r.link_id, 'void', 0, r.resolver, max(c.now_recorded, r.recorded_from), r.resolution_id,
       'void|' || r.derivation_key
FROM link_resolution r JOIN clock c ON c.id = 1
WHERE r.status = 'bound' AND r.resolver LIKE 'resolve-key@%'
  AND NOT EXISTS (SELECT 1 FROM desired_link_resolution d WHERE d.derivation_key = r.derivation_key)
  AND NOT EXISTS (SELECT 1 FROM link_resolution x WHERE x.supersedes = r.resolution_id);

-- 3. Append derived assessments that are missing.
INSERT INTO assessment (document_id, unit_id, claim_id, mention_id, dimension, value, direction, provisional,
                        valid_from, recorded_from, evidence_version_id, evidence_link_id, method, authority,
                        rule_id, rule_sha256, derivation_key, rated_by, confidence, rationale)
SELECT d.document_id, d.unit_id, d.claim_id, d.mention_id, d.dimension, d.value, d.direction, d.provisional,
       d.valid_from, d.recorded_from, d.evidence_version_id, d.evidence_link_id, 'rule', d.authority,
       d.rule_id, d.rule_sha256, d.derivation_key,
       'rule:' || d.rule_id || '@' || substr(d.rule_sha256, 1, 12), d.confidence, d.rationale
FROM desired_assessment d
WHERE NOT EXISTS (SELECT 1 FROM assessment a WHERE a.derivation_key = d.derivation_key)
ORDER BY d.recorded_from, d.derivation_key;

-- 4. Record why (premises) for derived rows that have no justification yet.
INSERT INTO justification (assessment_id, premise_kind, premise_ref)
SELECT DISTINCT a.assessment_id, json_extract(p.value, '$.kind'), json_extract(p.value, '$.ref')
FROM desired_assessment d
JOIN assessment a ON a.derivation_key = d.derivation_key, json_each(d.premises) p
WHERE NOT EXISTS (SELECT 1 FROM justification j WHERE j.assessment_id = a.assessment_id);

-- 5. Void derived rows whose knowledge-time window has closed (premise withdrawn, binding
--    superseded, rule version fixed, or shadowed by a later effective-dated version).
INSERT INTO assessment (document_id, unit_id, claim_id, mention_id, dimension, value, direction, provisional,
                        recorded_from, supersedes, method, authority, rule_id, rule_sha256, derivation_key,
                        rated_by, rationale)
SELECT a.document_id, a.unit_id, a.claim_id, a.mention_id, a.dimension, 'void', 'lateral', a.provisional,
       d.recorded_until, a.assessment_id, 'rule', a.authority, a.rule_id, a.rule_sha256,
       'void|' || a.derivation_key, a.rated_by,
       'premise window closed at ' || d.recorded_until
FROM desired_assessment d JOIN assessment a ON a.derivation_key = d.derivation_key
WHERE d.recorded_until IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM assessment x WHERE x.derivation_key = 'void|' || a.derivation_key);

-- 6. Orphans: derived rows no current derivation explains at all (e.g. a SQL rule body was
--    replaced). Voided as of the clock: the one place apply reads "now".
INSERT INTO assessment (document_id, unit_id, claim_id, mention_id, dimension, value, direction, provisional,
                        recorded_from, supersedes, method, authority, rule_id, rule_sha256, derivation_key,
                        rated_by, rationale)
SELECT a.document_id, a.unit_id, a.claim_id, a.mention_id, a.dimension, 'void', 'lateral', a.provisional,
       max(c.now_recorded, a.recorded_from), a.assessment_id, 'rule', a.authority, a.rule_id, a.rule_sha256,
       'void|' || a.derivation_key, a.rated_by, 'no derivation explains this row any more'
FROM assessment a JOIN clock c ON c.id = 1
WHERE a.derivation_key IS NOT NULL AND a.value <> 'void'
  AND NOT EXISTS (SELECT 1 FROM desired_assessment d WHERE d.derivation_key = a.derivation_key)
  AND NOT EXISTS (SELECT 1 FROM assessment x WHERE x.derivation_key = 'void|' || a.derivation_key);
