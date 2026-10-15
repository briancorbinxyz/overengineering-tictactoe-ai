#!/usr/bin/env python3
"""End-to-end test of the knowledge base schema v2 (stdlib + sqlite3 only).

Loads schema.sql + extensions.sql into :memory: and runs five scenarios:
  A  ACME: a rumour email, its resolution, the real Acmes, and five golden questions
  B  10-K -> 8-K Item 4.02 (keyed link, pending before the 10-K) -> 10-K/A, plus
     order-independence over every processing and arrival order, and an ambiguous key
  C  a T+1 playbook superseded by a hand-written link; withdrawal; supersession chains
  D  negative tests: the ledger, the frozen trust columns and the authority rules
  E  a rule FIX versus an effective-dated NEW rule version, seen through AS_KNOWN

It writes a readable trace to acme_walkthrough_output.txt beside this file and exits
non-zero if any check fails. Every real-company row uses only what the research reports
cite; everything else is marked illustrative or fictional.

Run: python3 docs/kb-schema/tests/test_schema.py
"""
import hashlib
import itertools
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KBDIR = os.path.dirname(HERE)
OUT = os.path.join(HERE, "acme_walkthrough_output.txt")
SCHEMA = open(os.path.join(KBDIR, "schema.sql")).read()
EXT = open(os.path.join(KBDIR, "extensions.sql")).read()
APPLY = open(os.path.join(KBDIR, "apply.sql")).read()
PROFILES = os.path.join(KBDIR, "profiles")

LINES = []
FAILS = []
PASSES = [0]


def say(text=""):
    LINES.append(text)


def head(title, char="="):
    say()
    say(char * 100)
    say(title)
    say(char * 100)


def check(cond, msg):
    if cond:
        PASSES[0] += 1
        say(f"  [ok]   {msg}")
    else:
        FAILS.append(msg)
        say(f"  [FAIL] {msg}")


def table(db, sql, params=(), title=None, width=64):
    cur = db.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if title:
        say(f"-- {title}")
    def cell(v):
        s = "NULL" if v is None else str(v)
        s = s.replace("\n", " / ")
        return s if len(s) <= width else s[: width - 1] + "…"
    data = [[cell(v) for v in r] for r in rows]
    w = [max([len(c)] + [len(r[i]) for r in data]) for i, c in enumerate(cols)]
    say("  " + " | ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
    say("  " + "-+-".join("-" * w[i] for i in range(len(cols))))
    for r in data:
        say("  " + " | ".join(r[i].ljust(w[i]) for i in range(len(cols))))
    say(f"  ({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return rows


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def rejected(db, sql, params=()):
    try:
        db.execute(sql, params)
    except sqlite3.DatabaseError as e:
        return str(e)
    return None


class KB:
    """A fresh in-memory knowledge base with small insert helpers."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.executescript(EXT)
        self.db.execute("INSERT INTO clock VALUES (1, '2026-10-14', '2026-10-14T00:00:00Z')")

    def x(self, sql, params=()):
        return self.db.execute(sql, params)

    def one(self, sql, params=()):
        r = self.db.execute(sql, params).fetchone()
        return None if r is None else r[0]

    def clock(self, valid, recorded=None):
        self.x("UPDATE clock SET now_valid = ?, now_recorded = ?", (valid, recorded or valid))

    def apply(self):
        self.db.executescript(APPLY)

    def source(self, name, adapter, snapshot="2026-10-14", at="2026-10-14T00:00:00Z"):
        return self.x("INSERT INTO source (name, adapter, snapshot, snapshot_at) VALUES (?,?,?,?)",
                      (name, adapter, snapshot, at)).lastrowid

    def run(self, source_id, profile, started="2026-01-01T00:00:00Z"):
        p = os.path.join(PROFILES, profile)
        return self.x("""INSERT INTO ingest_run (source_id, adapter_version, splitter_version, config_hash,
                         profile_sha256, started_at, status) VALUES (?,?,?,?,?,?, 'ok')""",
                      (source_id, f"{profile}@test", "s1", "cfg", sha256_file(p), started)).lastrowid

    def doc(self, source_id, path, title, recorded, run=None, **trust):
        cols = ["source_id", "path", "title", "recorded_from", "ingest_run_id"] + list(trust)
        vals = [source_id, path, title, recorded, run] + list(trust.values())
        q = f"INSERT INTO document ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        return self.x(q, vals).lastrowid

    def unit(self, doc, anchor, kind, statement, heading=None):
        return self.x("INSERT INTO unit (document_id, anchor, kind, statement, heading_path) VALUES (?,?,?,?,?)",
                      (doc, anchor, kind, statement, heading)).lastrowid

    def version(self, unit, body, valid_from, recorded, published=None, run=None):
        return self.x("""INSERT INTO version (unit_id, body, body_hash, valid_from, recorded_from, published_at,
                         ingest_run_id, valid_grade) VALUES (?,?,?,?,?,?,?, 'element')""",
                      (unit, body, sha256_text(body), valid_from, recorded, published, run)).lastrowid

    def ident(self, unit, scheme, value, scope=""):
        self.x("INSERT INTO identifier (value, scheme, scope, unit_id) VALUES (?,?,?,?)", (value, scheme, scope, unit))

    def link(self, from_unit, type_, origin, recorded, to_unit=None, to_document=None, key=None,
             confidence=1.0, emitted_by=None, valid_from=None):
        scheme, value = key if key else (None, None)
        return self.x("""INSERT INTO link (from_unit, type, to_unit, to_document, to_key_scheme, to_key, origin,
                         confidence, emitted_by, valid_from, recorded_from) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (from_unit, type_, to_unit, to_document, scheme, value, origin, confidence, emitted_by,
                       valid_from, recorded)).lastrowid

    def assess(self, **c):
        q = f"INSERT INTO assessment ({', '.join(c)}) VALUES ({', '.join('?' * len(c))})"
        return self.x(q, list(c.values())).lastrowid

    def standing(self, unit_id):
        r = self.x("""SELECT standing, supports, label FROM current_labeled WHERE unit_id = ?""", (unit_id,)).fetchone()
        return r


# ════════════════════════════════════════════════════════════════════════════
# A. ACME
# ════════════════════════════════════════════════════════════════════════════
BANNER = "[FICTIONAL — generated for the RAGs to Riches tutorial; no real person or company]"
E1_ID = "<rumour-0812@tallowmere.example>"
E2_ID = "<resolve-0940@tallowmere.example>"
E3_ID = "<variant-0950@tallowmere.example>"
UTC = {"08:12": "2026-08-31T12:12:00Z", "09:00": "2026-08-31T13:00:00Z", "09:40": "2026-08-31T13:40:00Z",
       "09:50": "2026-08-31T13:50:00Z", "10:00": "2026-08-31T14:00:00Z", "10:30": "2026-08-31T14:30:00Z"}


def build_acme(with_resolution=True, trace=True):
    k = KB()
    t = say if trace else (lambda *a, **kw: None)
    ent = {}
    for eid, name, kind, reality, desc in [
        (1, "Acme United Corporation", "issuer", "real", "NYSE American: ACU; CIK 2098"),
        (2, "Albertsons Companies, Inc.", "issuer", "real", "NYSE: ACI; CIK 1646972; owns the Acme Markets banner"),
        (3, "Acme Markets", "brand", "real", "supermarket banner of Albertsons; no ticker of its own"),
        (4, "Acme Corporation", "fictional_org", "fictional", "the defendant in the film Coyote vs. Acme; no identifiers by design"),
        (5, "Acme Packet", "issuer", "real", "CIK 1130258; acquired by Oracle in 2013"),
        (6, "Coyote vs. Acme", "creative_work", "real", "film; US theatrical release 28 Aug 2026"),
        (7, "ACME Corporation, s.r.o.", "private_company", "real", "Prague; holds an active LEI (a name-collision trap)"),
        (8, "Tallowmere Asset Management (fictional)", "private_company", "synthetic", "the tutorial's fictional asset manager"),
    ]:
        k.x("INSERT INTO entity VALUES (?,?,?,?,?)", (eid, name, kind, reality, desc))
        ent[eid] = name
    k.db.executemany("INSERT INTO entity_identifier VALUES (?,?,?,?,?,?)", [
        (1, "cik", "2098", None, None, None), (1, "ticker", "ACU", "NYSE American", None, None),
        (2, "cik", "1646972", None, None, None), (2, "ticker", "ACI", "NYSE", None, None),
        (5, "cik", "1130258", None, None, "2013"),        # historical filer (acquired 2013)
        (7, "lei", "2549003V2049OXYXLD19", None, None, None)])
    k.db.executemany("INSERT INTO alias VALUES (?,?,?,?,?)", [
        (1, "ACME", "colloquial", None, None), (3, "ACME", "brand", None, None), (4, "ACME", "colloquial", None, None),
        (5, "ACME", "colloquial", None, None), (4, "Acme Corporation", "legal", None, None),
        (7, "Acme Corporation", "legal", None, None), (6, "Coyote vs. Acme", "title", None, None)])
    k.db.executemany("INSERT INTO entity_link VALUES (?,?,?,?,?,?)", [
        (3, 2, "brand_of", None, None, "Albertsons 10-K"), (4, 6, "depicted_in", None, None, "film synopsis")])

    s_edgar = k.source("sec-edgar", "edgar-ixbrl")
    s_mail = k.source("tallowmere-mail", "mbox")
    s_notes = k.source("tallowmere-notes", "obsidian-md")
    r10k = k.run(s_edgar, "sec-edgar-10k.yaml")
    rmail = k.run(s_mail, "email.yaml")
    rnote = k.run(s_notes, "research-note.yaml")
    edgar_trust = dict(access="public", sensitivity=0, reliability="authoritative", force="official",
                       authenticity="original", trust_zone="external")
    mail_trust = dict(access="dist:pm-desk", sensitivity=2, reliability="unvetted", force="none",
                      authenticity="original", trust_zone="internal")

    # ACU FY2025 10-K. Accession and the Item 3 sentence are from the ACME report; times illustrative.
    acu = k.doc(s_edgar, "0001193125-26-102079", "Acme United Corp 10-K FY2025", "2026-03-06T21:15:00Z", r10k,
                publisher="cik:2098", **edgar_trust)
    acu_cover = k.unit(acu, "cover", "section", "record", "Cover page")
    acu_i3 = k.unit(acu, "Item 3", "section", "record", "Part I > Item 3. Legal Proceedings")
    k.version(acu_cover, "ACME UNITED CORP. Annual Report on Form 10-K for the fiscal year ended December 31, 2025 "
              "(illustrative cover text).", "2025-12-31", "2026-03-06T21:15:00Z", "2026-03-06T21:10:00Z", r10k)
    v_acu3 = k.version(acu_i3, "There are no pending material legal proceedings to which the Company is a party.",
                       "2025-12-31", "2026-03-06T21:15:00Z", "2026-03-06T21:10:00Z", r10k)
    k.ident(acu_cover, "edgar:accession", "0001193125-26-102079")
    k.ident(acu_cover, "edgar:cik+form+period", "2098|10-K|2025-12-31")
    k.ident(acu_i3, "edgar:cik+form+period+item", "2098|10-K|2025-12-31|Item 3")
    # ACI 10-K (period ended 24 Feb 2024): the Acme banner. Excerpt is illustrative wording.
    aci = k.doc(s_edgar, "0001646972-24-000060", "Albertsons Companies 10-K FY2023", "2026-01-15T00:00:00Z", r10k,
                publisher="cik:1646972", **edgar_trust)
    aci_i1 = k.unit(aci, "Item 1", "section", "record", "Part I > Item 1. Business")
    v_aci1 = k.version(aci_i1, "(illustrative excerpt) The Company operates stores under well-known banners, "
                       "including Acme.", "2024-02-24", "2026-01-15T00:00:00Z", "2024-04-22T20:00:00Z", r10k)
    k.ident(aci_i1, "edgar:cik+form+period", "1646972|10-K|2024-02-24")
    for d in (acu, aci):
        k.assess(document_id=d, dimension="register", value="factual", direction="initial", method="rule",
                 authority="profile", rated_by="profile:sec-edgar-10k",
                 recorded_from=k.one("SELECT recorded_from FROM document WHERE document_id=?", (d,)))
    m_acu = k.x("INSERT INTO mention (version_id, entity_id, surface, origin, confidence) VALUES (?,?,?,?,?)",
                (v_acu3, 1, "the Company", "filer", 1.0)).lastrowid
    k.x("INSERT INTO mention (version_id, entity_id, surface, origin, confidence) VALUES (?,?,?,?,?)",
        (v_aci1, 3, "Acme", "alias:brand", 0.95))
    c3 = k.x("INSERT INTO claim (text, modality, subject_entity) VALUES (?,?,?)",
             ("Acme United is a party to pending material legal proceedings", "asserted", 1)).lastrowid
    k.x("INSERT INTO evidence VALUES (?,?,?,?,?)", (c3, v_acu3, "refutes", "rule:item3-none-pending", 1.0))
    k.assess(claim_id=c3, dimension="world", value="real", direction="initial", method="rule", authority="profile",
             rated_by="profile:sec-edgar-10k", recorded_from="2026-03-06T21:15:00Z")
    k.assess(claim_id=c3, dimension="verification", value="refuted", direction="initial", method="source",
             authority="publisher", rated_by="cik:2098", evidence_version_id=v_acu3,
             recorded_from="2026-03-06T21:15:00Z", rationale="the issuer's own Item 3")

    # 08:12 -0400 rumour email (fictional), as in the ACME report.
    e1_body = (f"{BANNER}\nFrom: analyst-3@tallowmere.example\nTo: pm-desk@tallowmere.example\n"
               f"Date: Mon, 31 Aug 2026 08:12 -0400\nSubject: ACME?\nMessage-ID: {E1_ID}\n\n"
               "I heard ACME is being sued. It was all over my feed this weekend and I haven't checked "
               "anything. Does anyone know more, or whether it matters to us?")
    e1 = k.doc(s_mail, E1_ID, "ACME?", "2026-08-31T12:12:30Z", rmail,
               publisher="analyst-3@tallowmere.example", **mail_trust)
    e1u = k.unit(e1, "message", "message", "record")
    v_e1 = k.version(e1u, e1_body, UTC["08:12"], "2026-08-31T12:12:30Z", UTC["08:12"], rmail)
    k.ident(e1u, "email:message-id", E1_ID)
    k.ident(e1u, "email:thread-subject", "acme?")          # thread root: no Re:, no In-Reply-To
    k.assess(document_id=e1, dimension="register", value="factual", direction="initial", method="rule",
             authority="profile", rated_by="profile:email", recorded_from="2026-08-31T12:12:30Z")
    m1 = k.x("INSERT INTO mention (version_id, entity_id, surface, span_start, span_end, origin, confidence) "
             "VALUES (?,?,?,?,?,?,?)", (v_e1, None, "ACME", None, None, "alias:candidates", 0.41)).lastrowid
    k.db.executemany("INSERT INTO mention_candidate VALUES (?,?,?,?)",
                     [(m1, 1, 0.41, 1), (m1, 3, 0.22, 2), (m1, 4, 0.12, 3), (m1, 5, 0.08, 4)])
    k.assess(mention_id=m1, dimension="resolution", value="ambiguous:4", direction="initial", method="rule",
             authority="heuristic", rated_by="linker:alias-candidates@v1", recorded_from="2026-08-31T12:12:30Z",
             rationale="four candidates share the alias; no context to choose")
    c1 = k.x("INSERT INTO claim (text, modality, subject_mention_id) VALUES (?,?,?)",
             ("ACME is being sued", "hedged", m1)).lastrowid
    k.x("INSERT INTO evidence VALUES (?,?,?,?,?)", (c1, v_e1, "supports", "prose-pattern:i-heard", 0.6))
    k.assess(claim_id=c1, dimension="world", value="real", direction="initial", method="rule", authority="profile",
             rated_by="profile:email", recorded_from="2026-08-31T12:12:30Z")
    k.assess(claim_id=c1, dimension="verification", value="unverified", direction="initial", method="rule",
             authority="profile", rated_by="profile:email", recorded_from="2026-08-31T12:12:30Z",
             rationale="hedged claim ('I heard') in an internal email")

    ids = dict(acu=acu, aci=aci, acu_i3=acu_i3, v_acu3=v_acu3, e1=e1, e1u=e1u, v_e1=v_e1, m1=m1, c1=c1, c3=c3,
               m_acu=m_acu, ent=ent)
    k.apply()

    if with_resolution:
        # 09:40 reply from the same sender, with In-Reply-To/References: deterministic thread.
        e2_body = (f"{BANNER}\nFrom: analyst-3@tallowmere.example\nTo: pm-desk@tallowmere.example\n"
                   f"Date: Mon, 31 Aug 2026 09:40 -0400\nSubject: Re: ACME?\nMessage-ID: {E2_ID}\n"
                   f"In-Reply-To: {E1_ID}\nReferences: {E1_ID}\n\n"
                   "It's the plot of the Coyote vs. Acme film that opened Friday.")
        e2 = k.doc(s_mail, E2_ID, "Re: ACME?", "2026-08-31T13:40:30Z", rmail,
                   publisher="analyst-3@tallowmere.example", **mail_trust)
        e2u = k.unit(e2, "message", "message", "record")
        v_e2 = k.version(e2u, e2_body, UTC["09:40"], "2026-08-31T13:40:30Z", UTC["09:40"], rmail)
        k.ident(e2u, "email:message-id", E2_ID)
        k.assess(document_id=e2, dimension="register", value="factual", direction="initial", method="rule",
                 authority="profile", rated_by="profile:email", recorded_from="2026-08-31T13:40:30Z")
        m2 = k.x("INSERT INTO mention (version_id, entity_id, surface, origin, confidence) VALUES (?,?,?,?,?)",
                 (v_e2, 6, "Coyote vs. Acme", "alias:title", 0.97)).lastrowid
        k.assess(mention_id=m2, dimension="resolution", value="entity:6", direction="initial", method="rule",
                 authority="heuristic", rated_by="linker:alias-title@v1", recorded_from="2026-08-31T13:40:30Z")
        prof = "profile:email@" + sha256_file(os.path.join(PROFILES, "email.yaml"))[:12]
        k.link(e2u, "replies-to", "markup", "2026-08-31T13:40:30Z", key=("email:message-id", E1_ID),
               emitted_by=prof + "#threading.in-reply-to")
        k.link(e2u, "resolves", "prose-pattern", "2026-08-31T13:40:30Z", key=("email:message-id", E1_ID),
               confidence=0.8, emitted_by=prof + "#corrections.resolves:its-the-plot-of")
        # 09:50 variant: a different sender, "Re:" subject, NO In-Reply-To/References.
        e3_body = (f"{BANNER}\nFrom: analyst-5@tallowmere.example\nTo: pm-desk@tallowmere.example\n"
                   f"Date: Mon, 31 Aug 2026 09:50 -0400\nSubject: Re: ACME?\nMessage-ID: {E3_ID}\n\n"
                   "Pretty sure that's the Coyote vs. Acme movie, not a real company.")
        e3 = k.doc(s_mail, E3_ID, "Re: ACME? (no threading headers)", "2026-08-31T13:50:30Z", rmail,
                   publisher="analyst-5@tallowmere.example", **mail_trust)
        e3u = k.unit(e3, "message", "message", "record")
        v_e3 = k.version(e3u, e3_body, UTC["09:50"], "2026-08-31T13:50:30Z", UTC["09:50"], rmail)
        k.ident(e3u, "email:message-id", E3_ID)
        k.x("INSERT INTO mention (version_id, entity_id, surface, origin, confidence) VALUES (?,?,?,?,?)",
            (v_e3, 6, "Coyote vs. Acme", "alias:title", 0.97))
        l3 = k.link(e3u, "same-thread-candidate", "prose-pattern", "2026-08-31T13:50:30Z",
                    key=("email:thread-subject", "acme?"), confidence=0.6,
                    emitted_by=prof + "#threading.heuristic")
        k.x("""INSERT INTO work_item (doc_key, stage, ingest_run_id, state, quarantine_reason, suggestions, updated_at)
               VALUES (?, 'relate', ?, 'review', 'thread by subject only', ?, '2026-08-31T13:50:30Z')""",
            (sha256_text(e3_body), rmail, json.dumps([
                {"rank": 1, "action": "link", "type": "resolves", "target": E1_ID, "tier": "T1",
                 "why": {"subject 'acme?' matches": True, "participants overlap": True,
                         "In-Reply-To/References": False, "same sender": False, "cue: not a real company": True}},
                {"rank": 2, "action": "decline", "reason": "different sender; a stance, not a correction"}])))
        # Desk note written two days later (fictional), refers to ACU's 10-K by composite key.
        note = k.doc(s_notes, "RN-FILM-001", "Desk note: Coyote vs. Acme", "2026-09-01T14:00:00Z", rnote,
                     publisher="analyst-7@tallowmere.example", access="dist:research", sensitivity=1,
                     reliability="reliable", force="none", authenticity="original", trust_zone="internal")
        nu = k.unit(note, "summary", "note", "record")
        v_note = k.version(nu, f"{BANNER}\nCoyote vs. Acme opened in US theaters on 28 Aug 2026. In the film, "
                           "Wile E. Coyote sues the fictional Acme Corporation. Not a security; no listed issuer. "
                           "Separately, ACU's FY2025 10-K reports no pending material legal proceedings.",
                           "2026-09-01", "2026-09-01T14:00:00Z", "2026-09-01T13:55:00Z", rnote)
        k.ident(nu, "note:id", "RN-FILM-001")
        k.link(nu, "refers-to", "markup", "2026-09-01T14:00:00Z", key=("edgar:cik+form+period", "2098|10-K|2025-12-31"),
               emitted_by="profile:research-note#links.frontmatter")
        k.x("INSERT INTO mention (version_id, entity_id, surface, origin, confidence) VALUES (?,?,?,?,?)",
            (v_note, 6, "Coyote vs. Acme", "alias:title", 0.97))
        c2 = k.x("INSERT INTO claim (text, modality, subject_entity) VALUES (?,?,?)",
                 ("Acme Corporation is being sued (by Wile E. Coyote)", "in_universe", 4)).lastrowid
        k.x("INSERT INTO evidence VALUES (?,?,?,?,?)", (c2, v_note, "supports", "author", 1.0))
        k.assess(claim_id=c2, dimension="world", value="universe:6", direction="initial", method="source",
                 authority="publisher", rated_by="analyst-7@tallowmere.example", recorded_from="2026-09-01T14:00:00Z",
                 rationale="the note says it is the film's plot")
        ids.update(e2=e2, e2u=e2u, v_e2=v_e2, m2=m2, e3=e3, e3u=e3u, v_e3=v_e3, l3=l3, note=note, nu=nu, c2=c2)
        k.apply()
        # 10:30 ET: an analyst on the PM desk confirms the three provisional rows (single-person
        # lateral/demote moves; promotions would need a second person).
        for dim, target_col, target in [("resolution", "mention_id", m1), ("world", "claim_id", c1),
                                        ("verification", "claim_id", c1)]:
            row = k.x(f"""SELECT assessment_id, value, direction FROM assessment WHERE {target_col} = ?
                          AND dimension = ? AND provisional = 1 AND rule_id IS NOT NULL""", (target, dim)).fetchone()
            k.assess(**{target_col: target}, dimension=dim, value=row[1], direction=row[2], method="human",
                     authority="human", rated_by="pm-desk-1", recorded_from=UTC["10:30"], supersedes=row[0],
                     evidence_version_id=v_e2, rationale="confirmed: the 09:40 reply names the film")
    return k, ids


def acme_questions(k, ids):
    head("A3. Golden questions (ACME report table, plus two drafted in the same style)")
    qs = [("ACME-01", "Is ACME being sued?", "ambiguity-fictional", "CURRENT", None,
           "Resolves to the plot of Coyote vs. Acme (fictional Acme Corporation; film released 28 Aug 2026); no document "
           "reports a suit against a real Acme; ACU's FY2025 10-K reports no pending material legal proceedings."),
          ("ACME-02", "Is ACME being sued?", "ambiguity-as-known", "AS_KNOWN", UTC["09:00"],
           "Enumerates the candidates or asks which ACME; no resolution yet."),
          ("ACME-02b", "Is ACME being sued?", "ambiguity-as-known", "AS_KNOWN", UTC["10:00"],
           "(drafted) Provisionally the film's plot, flagged as under review; still no real Acme sued."),
          ("ACME-03", "Which ACMEs file with the SEC, and are any in litigation?", "ambiguity-enumerate", "CURRENT", None,
           "ACU (CIK 2098, none pending); Albertsons for the Acme banner; Acme Packet historical."),
          ("ACME-04", "What is Acme Corporation's LEI?", "unanswerable-fictional", "CURRENT", None,
           "Abstains: fictional entity, no identifiers."),
          ("ACME-05", "Is Acme United being sued?", "conflation-trap", "CURRENT", None,
           "(drafted) No: its FY2025 10-K reports no pending material legal proceedings. The ACME rumour email is "
           "never evidence about ACU.")]
    for q in qs:
        k.x("INSERT INTO question (question_id, text, stratum, mode, as_of, core_answer, status) VALUES (?,?,?,?,?,?, 'candidate')", q)
    k.db.executemany("INSERT INTO expected (question_id, unit_id, role) VALUES (?,?,?)", [
        ("ACME-01", ids["e2u"], "answer"), ("ACME-01", ids["acu_i3"], "answer"), ("ACME-01", ids["e1u"], "conflict"),
        ("ACME-02", ids["e1u"], "answer"), ("ACME-03", ids["acu_i3"], "answer"),
        ("ACME-05", ids["acu_i3"], "answer"), ("ACME-05", ids["e1u"], "decoy")])
    table(k.db, "SELECT question_id, mode, as_of, text, core_answer FROM question ORDER BY question_id",
          title="the questions, stored next to the data", width=90)

    acme = [r[0] for r in k.x("SELECT entity_id FROM alias WHERE surface = 'ACME'")]
    claims_sql = f"""
      SELECT cn.claim_id, cn.text, coalesce(cn.subject_name, '(unresolved)') AS subject, cn.subject_resolution,
             cn.world, cn.world_flags, cn.verification, cn.verification_flags, cn.real_world_support AS rw_support,
             ev.stance, d.title AS from_doc
      FROM claim_now cn JOIN evidence ev USING (claim_id)
      JOIN current_labeled cl ON cl.version_id = ev.version_id
      JOIN document d ON d.document_id = cl.document_id
      WHERE cn.subject_id IN ({','.join(map(str, acme))})
         OR cn.claim_id IN (SELECT c.claim_id FROM claim c JOIN mention_candidate mc ON mc.mention_id = c.subject_mention_id
                            WHERE mc.entity_id IN ({','.join(map(str, acme))}))
      ORDER BY cn.claim_id"""

    # ── ACME-01, CURRENT ──
    head("ACME-01  'Is ACME being sued?'  CURRENT (clock 2026-10-14)", "-")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    rows = table(k.db, claims_sql, title="claims about any ACME, with effective world / verification / support")
    by = {r[0]: r for r in rows}
    c1 = by.get(ids["c1"])
    check(c1 is not None and c1[2] == "Acme Corporation" and c1[4] == "universe:6" and c1[6] == "refuted",
          "the rumour's ACME resolves to the fictional Acme Corporation, world = universe of 'Coyote vs. Acme', "
          "real-world reading refuted")
    check(all(not (r[9] == "supports" and r[8] == "yes") for r in rows),
          "no claim that a real Acme is being sued has real-world support")
    check(by.get(ids["c3"]) is not None and by[ids["c3"]][9] == "refutes",
          "ACU's 10-K Item 3 is retrieved, refuting a pending suit")
    film = k.one("SELECT name FROM entity WHERE entity_id = 6")
    table(k.db, """SELECT cl.document_id, d.title, cl.supports, cl.label, substr(cl.body, instr(cl.body, char(10)||char(10))+2) AS text
                   FROM current_labeled cl JOIN document d USING (document_id) WHERE cl.unit_id IN (?, ?)""",
          (ids["e2u"], ids["nu"]), title="the resolving reply and the desk note (citable)")
    say(f"  ANSWER: 'ACME' here is the fictional Acme Corporation, sued in the plot of {film} (US release 28 Aug "
        "2026, per RN-FILM-001; resolved by the 09:40 reply, confirmed 10:30). No document reports a suit against "
        "a real Acme; ACU's FY2025 10-K: 'no pending material legal proceedings'.")

    # ── ACME-02, AS_KNOWN 09:00 ──
    head("ACME-02  'Is ACME being sued?'  AS_KNOWN 2026-08-31 09:00 ET (13:00Z)", "-")
    k.clock(UTC["09:00"], UTC["09:00"])
    rows = table(k.db, claims_sql)
    by = {r[0]: r for r in rows}
    c1 = by.get(ids["c1"])
    check(c1 is not None and c1[2] == "(unresolved)" and c1[3] == "ambiguous:4" and c1[4] == "real"
          and c1[6] == "unverified" and c1[5] is None, "as known at 09:00 the rumour is open: ambiguous, unverified, no flags")
    check(k.one("SELECT count(*) FROM current_version WHERE unit_id = ?", (ids["e2u"],)) == 0,
          "the 09:40 reply is not yet known")
    cands = table(k.db, """SELECT mc.rank, e.name, e.reality, mc.score FROM mention_candidate mc JOIN entity e USING (entity_id)
                           WHERE mc.mention_id = ? ORDER BY mc.rank""", (ids["m1"],), title="candidates to enumerate")
    check([c[1] for c in cands] == ["Acme United Corporation", "Acme Markets", "Acme Corporation", "Acme Packet"],
          "the candidate set is kept, so the answer can enumerate or ask which ACME")
    say("  ANSWER: unclear which ACME is meant: Acme United (ACU), Acme Markets (Albertsons), the fictional Acme "
        "Corporation, or historical Acme Packet. Nothing in the knowledge base reports a suit; ACU's 10-K reports none pending.")

    # ── ACME-02b, AS_KNOWN 10:00 ──
    head("ACME-02b 'Is ACME being sued?'  AS_KNOWN 2026-08-31 10:00 ET (14:00Z)  [drafted]", "-")
    k.clock(UTC["10:00"], UTC["10:00"])
    rows = table(k.db, claims_sql)
    c1 = {r[0]: r for r in rows}.get(ids["c1"])
    check(c1 is not None and c1[3] == "ambiguous:4" and c1[4] == "real"
          and "universe:6 (provisional" in (c1[5] or "") and "refuted (provisional" in (c1[7] or ""),
          "as known at 10:00 it resolves to the film in-universe, provisionally (labels, not yet decisions)")
    table(k.db, "SELECT mention_id, surface, resolution, flags FROM mention_now WHERE mention_id = ?", (ids["m1"],),
          title="the mention, as known at 10:00")
    std = k.x("SELECT standing, supports, label FROM current_labeled WHERE unit_id = ?", (ids["e1u"],)).fetchone()
    check(std == ("in_force", "yes", ""), "the 08:12 email's own standing is unchanged (it is a true record of a rumour)")
    check(k.one("SELECT count(*) FROM assessment WHERE (document_id = ? OR unit_id = ?) AND dimension = 'standing'",
                (ids["e1"], ids["e1u"])) == 0, "no standing row was ever written for the 08:12 email")
    say("  ANSWER: probably not a real company: a reply in the thread says it is the plot of Coyote vs. Acme "
        "(provisional, under review). No real Acme is reported sued.")

    # ── ACME-03, CURRENT ──
    head("ACME-03  'Which ACMEs file with the SEC, and are any in litigation?'  CURRENT", "-")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    filers = table(k.db, f"""
      WITH cand AS (SELECT entity_id FROM alias WHERE surface = 'ACME'
                    UNION SELECT el.to_entity FROM entity_link el JOIN alias a ON a.entity_id = el.from_entity
                    WHERE a.surface = 'ACME' AND el.type IN ('brand_of','subsidiary_of'))
      SELECT e.name, ei.value AS cik, CASE WHEN ei.valid_to IS NOT NULL AND ei.valid_to <= c.now_valid
                                          THEN 'historical' ELSE 'current' END AS filer,
             (SELECT group_concat(x.name) FROM entity_link l JOIN entity x ON x.entity_id = l.from_entity
              WHERE l.to_entity = e.entity_id AND l.type = 'brand_of') AS via
      FROM cand JOIN entity e USING (entity_id) JOIN entity_identifier ei ON ei.entity_id = e.entity_id AND ei.scheme = 'cik'
      JOIN clock c ON c.id = 1 ORDER BY filer, e.name""", title="ACMEs with a CIK")
    check({(r[1], r[2]) for r in filers} == {("2098", "current"), ("1646972", "current"), ("1130258", "historical")},
          "current filers: ACU (2098) and Albertsons for the Acme banner (1646972); Acme Packet historical")
    lit = table(k.db, f"""
      SELECT cn.subject_name, ev.stance, cn.real_world_support, d.title, cl.label
      FROM claim_now cn JOIN evidence ev USING (claim_id) JOIN current_labeled cl ON cl.version_id = ev.version_id
      JOIN document d ON d.document_id = cl.document_id
      WHERE cn.subject_id IN (1, 2, 3, 5) AND cn.world = 'real'""", title="litigation evidence about those (real world only)")
    check(len(lit) == 1 and lit[0][0] == "Acme United Corporation" and lit[0][1] == "refutes",
          "the only litigation evidence is ACU's 10-K saying none pending; nothing makes Albertsons a defendant")

    # ── ACME-04, CURRENT ──
    head("ACME-04  'What is Acme Corporation's LEI?'  CURRENT", "-")
    table(k.db, """SELECT a.surface, e.entity_id, e.name, e.reality FROM alias a JOIN entity e USING (entity_id)
                   WHERE a.surface = 'Acme Corporation'""", title="the name matches two entities (the trap)")
    ref = k.one("SELECT entity_id FROM mention_now WHERE mention_id = ?", (ids["m1"],))
    lei = k.x("SELECT value FROM entity_identifier WHERE entity_id = ? AND scheme = 'lei'", (ref,)).fetchall()
    check(ref == 4 and lei == [] and k.one("SELECT reality FROM entity WHERE entity_id = 4") == "fictional",
          "the Acme Corporation in this conversation is fictional and has no identifiers: abstain")
    check(k.one("SELECT count(*) FROM entity_identifier WHERE value = '2549003V2049OXYXLD19' AND entity_id = ?", (ref,)) == 0,
          "the Prague s.r.o.'s LEI is not attributed to it")
    say("  ANSWER: none. Acme Corporation is the fictional company in Coyote vs. Acme; it has no LEI. (An unrelated "
        "real ACME Corporation, s.r.o. in Prague has one; it is a different entity.)")

    # ── ACME-05 at three clocks ──
    head("ACME-05  'Is Acme United being sued?'  at 09:00, 10:00 and CURRENT  [drafted]", "-")
    acu_sql = """
      SELECT 'claim' AS via, cl.unit_id, d.title, ev.stance, cn.real_world_support AS rw_support, cl.supports
      FROM claim_now cn JOIN evidence ev USING (claim_id) JOIN current_labeled cl ON cl.version_id = ev.version_id
      JOIN document d ON d.document_id = cl.document_id
      WHERE cn.subject_id = 1 AND cn.world = 'real'
      UNION
      SELECT 'mention', cl.unit_id, d.title, NULL, NULL, cl.supports
      FROM mention_now mn JOIN current_labeled cl ON cl.version_id = mn.version_id
      JOIN document d ON d.document_id = cl.document_id
      WHERE mn.entity_id = 1 AND cl.supports <> 'no'"""
    for label, valid, rec in [("09:00 ET", UTC["09:00"], UTC["09:00"]), ("10:00 ET", UTC["10:00"], UTC["10:00"]),
                              ("CURRENT", "2026-10-14", "2026-10-14T00:00:00Z")]:
        k.clock(valid, rec)
        rows = table(k.db, acu_sql, title=f"evidence about Acme United, {label}")
        units = {r[1] for r in rows}
        check(ids["e1u"] not in units and ids["acu_i3"] in units,
              f"{label}: ACU's Item 3 is the evidence; the ACME rumour email is not retrieved as support")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    say("  ANSWER: No. Acme United's FY2025 10-K states there are no pending material legal proceedings to which "
        "it is a party. (A colleague's 'ACME is being sued' email was about the film, and never named ACU.)")


def scenario_a():
    head("A. ACME: one rumour, its resolution, and the real Acmes")
    say("Times: the email's Date: is 08:12 -0400 = 12:12Z; the reply 09:40 -0400 = 13:40Z. recorded_from is when the")
    say("KB archived each message (30 s later); published_at is the source's own time (the Date: header).")
    k, ids = build_acme()
    head("A1. What was ingested", "-")
    table(k.db, """SELECT d.document_id AS doc, d.title, u.anchor, d.publisher, d.trust_zone, v.published_at, v.recorded_from
                   FROM document d JOIN unit u USING (document_id) JOIN version v USING (unit_id) ORDER BY v.recorded_from""")
    table(k.db, """SELECT m.mention_id, m.surface, d.title AS in_doc, coalesce(e.name, '(none)') AS ingest_pick
                   FROM mention m JOIN version v USING (version_id) JOIN unit u USING (unit_id) JOIN document d USING (document_id)
                   LEFT JOIN entity e ON e.entity_id = m.entity_id ORDER BY m.mention_id""", title="mentions")
    table(k.db, """SELECT l.link_id, l.type, d.title AS from_doc, l.to_key_scheme, l.to_key, l.origin, l.confidence,
                   l.recorded_from FROM link l JOIN unit u ON u.unit_id = l.from_unit JOIN document d USING (document_id)""",
          title="links (detection, layer 2)")
    table(k.db, """SELECT r.resolution_id, r.link_id, r.status, d.title AS bound_to, r.recorded_from, r.resolver
                   FROM link_resolution r LEFT JOIN document d ON d.document_id = coalesce(r.to_document,
                   (SELECT document_id FROM unit WHERE unit_id = r.to_unit))""", title="resolutions (layer 2b)")
    check(k.one("""SELECT d.path FROM link_resolution r JOIN document d ON d.document_id = r.to_document
                   WHERE r.link_id = ?""", (ids["l3"],)) == E1_ID,
          "the headerless 09:50 variant binds by subject key to the thread root only (a same-thread candidate)")
    head("A2. The ledger (layer 3 output and human rows), in knowledge-time order", "-")
    table(k.db, """SELECT a.assessment_id AS id, a.target_kind || ':' || a.target_id AS target,
                   CASE a.target_kind WHEN 'claim' THEN (SELECT text FROM claim WHERE claim_id = a.claim_id)
                                      WHEN 'mention' THEN '"' || (SELECT surface FROM mention WHERE mention_id = a.mention_id) || '"'
                                      WHEN 'document' THEN (SELECT title FROM document WHERE document_id = a.document_id) END AS what,
                   a.dimension, a.value, a.provisional AS prov, a.direction, a.authority, a.method, a.recorded_from, a.supersedes AS sup
                   FROM assessment a WHERE a.target_kind IN ('claim','mention') OR a.dimension IN ('standing','register')
                   ORDER BY a.recorded_from, a.assessment_id""", width=40)
    say("  (entity 4 = Acme Corporation (fictional); entity 6 / universe:6 = the film Coyote vs. Acme)")
    table(k.db, """SELECT e.assessment_id AS id, e.sentence FROM assessment_explain e JOIN assessment a USING (assessment_id)
                   WHERE a.rule_id IS NOT NULL OR a.method = 'human' ORDER BY a.recorded_from, a.assessment_id""",
          title="why (assessment_explain)", width=230)
    table(k.db, """SELECT j.assessment_id, j.premise_kind, j.premise_ref FROM justification j
                   WHERE j.assessment_id = (SELECT min(assessment_id) FROM assessment WHERE rule_id = 'link-effect:resolves')""",
          title="justification of the first derived row", width=100)
    check(k.one("SELECT count(*) FROM assessment WHERE evidence_link_id = ?", (ids["l3"],)) == 0,
          "the same-thread-candidate link produced no assessment (no status effect)")
    check(k.one("SELECT count(*) FROM work_item WHERE state = 'review' AND stage = 'relate'") == 1,
          "the variant reply is an inbox item with ranked suggestions instead")
    table(k.db, "SELECT stage, state, quarantine_reason, suggestions FROM work_item", title="inbox", width=160)
    before = k.one("SELECT count(*) FROM assessment")
    k.apply()
    check(k.one("SELECT count(*) FROM assessment") == before, "apply is idempotent: a second run adds no rows")
    acme_questions(k, ids)

    # Chat: an edit is the same object with new content: a version, never a link.
    head("A5. A Slack edit is a new version of the same unit, not a 'replaces' link", "-")
    s_slack = k.source("tallowmere-slack", "chat-json")
    r_slack = k.run(s_slack, "chat-slack.yaml")
    cd = k.doc(s_slack, "C042ACME/2026-08-31", "#desk 2026-08-31", "2026-08-31T12:20:05Z", r_slack,
               publisher="slack:U07ANALYST3", access="channel:C042ACME", sensitivity=2, reliability="unvetted",
               force="none", authenticity="original", trust_zone="internal")
    cu = k.unit(cd, "C042ACME|1756642800.000100", "message", "record")
    v1 = k.version(cu, "ACME being sued??", "2026-08-31T12:20:00Z", "2026-08-31T12:20:05Z", "2026-08-31T12:20:00Z", r_slack)
    k.x("UPDATE version SET recorded_to = '2026-08-31T12:25:05Z' WHERE version_id = ?", (v1,))   # message_changed
    k.version(cu, "ACME being sued?? (edit: someone said it's a film)", "2026-08-31T12:20:00Z", "2026-08-31T12:25:05Z",
              "2026-08-31T12:25:00Z", r_slack)
    seen = []
    for t in ("2026-08-31T12:22:00Z", "2026-10-14T00:00:00Z"):
        k.clock(t, t)
        seen.append(k.one("SELECT body FROM current_version WHERE unit_id = ?", (cu,)))
    say(f"  as known 12:22 / now: {seen}")
    check(seen == ["ACME being sued??", "ACME being sued?? (edit: someone said it's a film)"]
          and k.one("SELECT count(*) FROM link WHERE from_unit = ? OR to_unit = ?", (cu, cu)) == 0,
          "the edit closes the old version's knowledge period (same valid_from); the pre-edit text stays replayable; no link")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")

    # Contrast: the same KB without the 09:40 reply (only the headerless variant would exist).
    head("A4. Contrast: no headered reply. At 10:00 the rumour stays open", "-")
    k2, ids2 = build_acme(with_resolution=False, trace=False)
    k2.clock(UTC["10:00"], UTC["10:00"])
    r = k2.x("SELECT subject_resolution, world, verification, world_flags FROM claim_now WHERE claim_id = ?",
             (ids2["c1"],)).fetchone()
    say(f"  claim_now(c1) at 10:00 without the reply: {r}")
    check(r == ("ambiguous:4", "real", "unverified", None), "without a resolving reply nothing changes: still ambiguous and unverified")
    return k, ids


# ════════════════════════════════════════════════════════════════════════════
# B. 10-K -> 8-K Item 4.02 -> 10-K/A (fictional issuer)
# ════════════════════════════════════════════════════════════════════════════
KEY_10K = ("edgar:cik+form+period", "x-9000001|10-K|2025-12-31")
TIMES_B1 = {"K": "2026-02-20T21:05:00Z", "E": "2026-05-18T20:02:00Z", "A": "2026-07-01T20:03:00Z", "K2": "2026-03-02T15:05:00Z"}
TIMES_B2 = {"K": "2026-05-25T09:00:00Z", "E": "2026-05-18T20:02:00Z", "A": "2026-07-01T20:03:00Z"}


def edgar_kb():
    k = KB()
    src = k.source("sec-edgar", "edgar-ixbrl")
    runs = {"10k": k.run(src, "sec-edgar-10k.yaml"), "8k": k.run(src, "sec-edgar-8k.yaml")}
    return k, src, runs


TRUST = dict(access="public", sensitivity=0, publisher="x-cik:9000001", reliability="authoritative",
             force="official", authenticity="original", trust_zone="external")


def ingest(k, src, runs, which, rec):
    p10k = "profile:sec-edgar-10k@" + sha256_file(os.path.join(PROFILES, "sec-edgar-10k.yaml"))[:12]
    p8k = "profile:sec-edgar-8k@" + sha256_file(os.path.join(PROFILES, "sec-edgar-8k.yaml"))[:12]
    if which == "K":
        d = k.doc(src, "x-0009000001-26-000010", "Harrowgate Securities (fictional) 10-K FY2025", rec, runs["10k"], **TRUST)
        cov = k.unit(d, "cover", "section", "record")
        i8 = k.unit(d, "Item 8", "section", "record", "Part II > Item 8. Financial Statements")
        k.version(cov, "Annual Report on Form 10-K for the fiscal year ended December 31, 2025 (fictional issuer).",
                  "2025-12-31", rec, "2026-02-20T21:00:00Z", runs["10k"])
        k.version(i8, "Total revenue for fiscal 2025: $412.0 million (illustrative).", "2025-12-31", rec,
                  "2026-02-20T21:00:00Z", runs["10k"])
        k.ident(cov, "edgar:accession", "x-0009000001-26-000010")
        k.ident(cov, *KEY_10K)
    elif which == "K2":   # a second original for the same period (filed in error): makes the key ambiguous
        d = k.doc(src, "x-0009000001-26-000014", "Harrowgate Securities (fictional) 10-K FY2025, re-filed", rec, runs["10k"], **TRUST)
        cov = k.unit(d, "cover", "section", "record")
        k.version(cov, "Annual Report on Form 10-K for the fiscal year ended December 31, 2025 (re-filed; fictional).",
                  "2025-12-31", rec, "2026-03-02T15:00:00Z", runs["10k"])
        k.ident(cov, "edgar:accession", "x-0009000001-26-000014")
        k.ident(cov, *KEY_10K)
    elif which == "E":
        d = k.doc(src, "x-0009000001-26-000031", "Harrowgate Securities (fictional) 8-K Item 4.02", rec, runs["8k"], **TRUST)
        u = k.unit(d, "Item 4.02", "section", "record", "Item 4.02 Non-Reliance on Previously Issued Financial Statements")
        k.version(u, "On May 14, 2026 the Audit Committee concluded that the audited financial statements included in "
                  "the Company's Annual Report on Form 10-K for the fiscal year ended December 31, 2025 should no "
                  "longer be relied upon (fictional).", "2026-05-14", rec, "2026-05-18T20:00:00Z", runs["8k"])
        k.ident(u, "edgar:accession", "x-0009000001-26-000031")
        # The 8-K names its target by form and period in prose; there is no accession to point at.
        k.link(u, "do-not-rely", "prose-pattern", rec, key=KEY_10K, confidence=0.9, valid_from="2026-05-14",
               emitted_by=p8k + "#rules.item-4.02")
    elif which == "A":
        d = k.doc(src, "x-0009000001-26-000052", "Harrowgate Securities (fictional) 10-K/A FY2025", rec, runs["10k"], **TRUST)
        cov = k.unit(d, "cover", "section", "record")
        i8 = k.unit(d, "Item 8", "section", "record", "Part II > Item 8. Financial Statements (restated)")
        k.version(cov, "Amendment No. 1 on Form 10-K/A to restate the financial statements for fiscal 2025 (fictional).",
                  "2025-12-31", rec, "2026-07-01T20:00:00Z", runs["10k"])
        k.version(i8, "Total revenue for fiscal 2025 (as restated): $389.5 million (illustrative).", "2025-12-31", rec,
                  "2026-07-01T20:00:00Z", runs["10k"])
        k.ident(cov, "edgar:accession", "x-0009000001-26-000052")
        k.ident(cov, "edgar:cik+form+period", "x-9000001|10-K/A|2025-12-31")
        k.link(cov, "amends", "status+link", rec, key=KEY_10K, valid_from="2026-07-01", emitted_by=p10k + "#rules.amendment")
        k.link(i8, "restates", "prose-pattern", rec, key=KEY_10K, confidence=0.9, valid_from="2026-07-01",
               emitted_by=p10k + "#rules.restatement")
    else:
        raise ValueError(which)


def unit_by(k, path, anchor):
    return k.one("SELECT unit_id FROM unit JOIN document USING (document_id) WHERE path = ? AND anchor = ?", (path, anchor))


def edgar_probe(k, probes):
    """Natural-key snapshot of what CURRENT says about both Item 8s at each probe clock."""
    out = []
    for valid, rec in probes:
        k.clock(valid, rec)
        rows = k.x("""SELECT d.path, u.anchor, cl.standing, cl.supports, cl.standing_since, cl.standing_known,
                      (SELECT count(*) FROM official_version o WHERE o.version_id = cl.version_id) AS official
                      FROM current_labeled cl JOIN unit u USING (unit_id) JOIN document d ON d.document_id = cl.document_id
                      WHERE u.anchor = 'Item 8' ORDER BY d.path""").fetchall()
        out.append((valid, rec, tuple(rows)))
    return out


def canonical_ledger(k):
    """The ledger and resolutions with ids replaced by natural keys, for cross-order comparison."""
    nk_unit = "(SELECT d.path || '#' || u.anchor FROM unit u JOIN document d USING (document_id) WHERE u.unit_id = {})"
    nk_doc = "(SELECT path FROM document WHERE document_id = {})"
    nk_link = ("(SELECT d.path || '#' || u.anchor || '>' || l.type || '>' || coalesce(l.to_key, '') FROM link l "
               "JOIN unit u ON u.unit_id = l.from_unit JOIN document d ON d.document_id = u.document_id WHERE l.link_id = {})")
    a = k.x(f"""SELECT a.target_kind, coalesce({nk_doc.format('a.document_id')}, {nk_unit.format('a.unit_id')}),
                a.dimension, a.value, a.direction, a.provisional, a.valid_from, a.recorded_from, a.authority, a.method,
                a.rule_id, a.rule_sha256, {nk_link.format('a.evidence_link_id')},
                (SELECT s.dimension || '=' || s.value || '@' || s.recorded_from FROM assessment s WHERE s.assessment_id = a.supersedes)
                FROM assessment a""").fetchall()
    r = k.x(f"""SELECT {nk_link.format('r.link_id')}, r.status, coalesce({nk_doc.format('r.to_document')}, {nk_unit.format('r.to_unit')}),
                r.candidates, r.recorded_from FROM link_resolution r""").fetchall()
    return sorted(map(repr, a)), sorted(map(repr, r))


def scenario_b():
    head("B. 10-K -> 8-K Item 4.02 -> 10-K/A (fictional issuer Harrowgate Securities, x-cik 9000001)")
    say("The 8-K names its target in prose ('Form 10-K for the fiscal year ended December 31, 2025'): no accession.")
    say(f"So the link carries a typed key {KEY_10K[0]} = {KEY_10K[1]} and is bound when a filing with that key")
    say("(published before the 8-K, by source time) is in the KB.")

    head("B1. Natural arrival order: 10-K (Feb), 8-K (May), 10-K/A (Jul)", "-")
    k, src, runs = edgar_kb()
    for w in ("K", "E", "A"):
        ingest(k, src, runs, w, TIMES_B1[w])
        k.apply()
    i8 = unit_by(k, "x-0009000001-26-000010", "Item 8")
    i8a = unit_by(k, "x-0009000001-26-000052", "Item 8")
    k.x("INSERT INTO answer (answer_id, asked_at, question, model) VALUES (1, '2026-04-01T15:00:00Z', 'FY2025 revenue?', 'qwen3:8b')")
    k.x("INSERT INTO answer_context VALUES (1, (SELECT max(version_id) FROM version WHERE unit_id = ?), 1, 0, '')", (i8,))
    k.x("INSERT INTO quotation VALUES (1, 'Q1', (SELECT max(version_id) FROM version WHERE unit_id = ?), '$412.0 million', 1)", (i8,))
    for label, valid, rec in [("as known 2026-04-01", "2026-04-01", "2026-04-01T00:00:00Z"),
                              ("as known 2026-06-01", "2026-06-01", "2026-06-01T00:00:00Z"),
                              ("CURRENT 2026-10-14", "2026-10-14", "2026-10-14T00:00:00Z")]:
        k.clock(valid, rec)
        table(k.db, """SELECT d.title, u.anchor, cl.standing, cl.supports, cl.label,
                       (SELECT count(*) FROM official_version o WHERE o.version_id = cl.version_id) AS in_official,
                       substr(cl.body, 1, 60) AS body
                       FROM current_labeled cl JOIN unit u USING (unit_id) JOIN document d ON d.document_id = cl.document_id
                       WHERE u.anchor = 'Item 8'""", title=label, width=110)
    k.clock("2026-04-01", "2026-04-01T00:00:00Z")
    check(k.standing(i8)[:2] == ("in_force", "yes"), "2026-04-01: the 10-K figure is in force")
    k.clock("2026-06-01", "2026-06-01T00:00:00Z")
    s = k.x("SELECT standing, supports, standing_since, standing_known, standing_authority FROM current_labeled WHERE unit_id = ?", (i8,)).fetchone()
    check(s == ("do_not_rely", "labelled", "2025-12-31", TIMES_B1["E"], "publisher"),
          "2026-06-01: do_not_rely, labelled not hidden, valid from the period end, known from the 8-K, issuer authority")
    check(k.one("SELECT count(*) FROM official_version WHERE unit_id = ?", (i8,)) == 0, "2026-06-01: out of OFFICIAL")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    check(k.standing(i8)[:2] == ("restated", "no") and k.standing(i8a)[:2] == ("in_force", "yes"),
          "2026-10-14: the original is 'restated' (no longer support); the 10-K/A figure supports the answer")
    table(k.db, """SELECT assessment_id AS id, target_kind || ':' || target_id AS target, dimension, value, valid_from,
                   recorded_from, authority, rule_id FROM assessment WHERE rule_id IS NOT NULL ORDER BY recorded_from""",
          title="derived rows")
    table(k.db, "SELECT sentence FROM assessment_explain WHERE rule_id IS NOT NULL ORDER BY recorded_from",
          title="explanations", width=230)
    rc = table(k.db, "SELECT * FROM answer_exposure", title="logged answers exposed by a later demotion (answer_recheck input)")
    check(len(rc) >= 1 and rc[0][2] == "cited", "the April answer that quoted the 10-K figure is found for recheck")
    k.x("""INSERT INTO answer_recheck (answer_id, trigger_assessment_id, exposure, found_at, outcome)
           SELECT answer_id, trigger_assessment_id, exposure, '2026-05-18T20:02:00Z', 'pending' FROM answer_exposure""")

    head("B2. The pending key arrives before the 10-K (the 10-K is backfilled a week later)", "-")
    k2, src2, runs2 = edgar_kb()
    for w in ("E", "K", "A"):
        ingest(k2, src2, runs2, w, TIMES_B2[w])
        k2.apply()
    k2.clock("2026-05-20", "2026-05-20T00:00:00Z")
    table(k2.db, "SELECT link_id, type, to_key_scheme, to_key, recorded_from, last_resolution FROM link_pending",
          title="as known 2026-05-20: the 8-K's link is pending")
    check(k2.one("SELECT count(*) FROM link_pending WHERE type = 'do-not-rely'") == 1, "2026-05-20: link pending, nothing derived")
    k2.clock("2026-05-26", "2026-05-26T00:00:00Z")
    i8b = unit_by(k2, "x-0009000001-26-000010", "Item 8")
    s = k2.x("SELECT standing, standing_since, standing_known FROM current_labeled WHERE unit_id = ?", (i8b,)).fetchone()
    check(s == ("do_not_rely", "2025-12-31", TIMES_B2["K"]),
          "2026-05-26: bound when the 10-K landed; known from the 10-K's arrival, valid from the period end")

    head("B3. Order independence", "-")
    probes = [("2026-04-01", "2026-04-01T00:00:00Z"), ("2026-05-20", "2026-05-20T00:00:00Z"),
              ("2026-05-26", "2026-05-26T00:00:00Z"), ("2026-06-01", "2026-06-01T00:00:00Z"),
              ("2026-10-14", "2026-10-14T00:00:00Z")]
    for name, times in (("B1 times", TIMES_B1), ("B2 times", TIMES_B2)):
        results = {}
        for order in itertools.permutations(["K", "E", "A"]):
            kk, ss, rr = edgar_kb()
            for w in order:
                ingest(kk, ss, rr, w, times[w])
                kk.apply()
            kk.apply()
            results[order] = (canonical_ledger(kk), edgar_probe(kk, probes))
        first = next(iter(results.values()))
        same = all(v == first for v in results.values())
        say(f"  {name}: processed in all {len(results)} orders, apply after every document")
        check(same, f"{name}: identical ledger, resolutions and CURRENT status at every probe in all 6 processing orders")
    finals = {}
    for order in itertools.permutations(["K", "E", "A"]):
        kk, ss, rr = edgar_kb()
        for n, w in enumerate(order):
            ingest(kk, ss, rr, w, f"2026-07-02T1{n}:00:00Z")   # recorded when it arrives
            kk.apply()
        kk.clock("2026-10-14", "2026-10-14T00:00:00Z")
        finals[order] = tuple(kk.x("""SELECT d.path, u.anchor, cl.standing, cl.supports, cl.standing_since
                                      FROM current_labeled cl JOIN unit u USING (unit_id) JOIN document d ON d.document_id = cl.document_id
                                      WHERE u.anchor = 'Item 8' ORDER BY d.path""").fetchall())
    check(len(set(finals.values())) == 1, "arrival order (recorded as it arrives): identical final CURRENT status in all 6 orders")
    say(f"  final status: {next(iter(finals.values()))}")

    head("B4. An ambiguous key: a second original 10-K for the same period", "-")
    k3, s3, r3 = edgar_kb()
    for w in ("K", "K2", "E"):
        ingest(k3, s3, r3, w, TIMES_B1[w])
        k3.apply()
    k3.clock("2026-06-01", "2026-06-01T00:00:00Z")
    table(k3.db, "SELECT resolution_id, link_id, status, candidates, recorded_from FROM link_resolution", title="resolutions")
    i8c = unit_by(k3, "x-0009000001-26-000010", "Item 8")
    check(k3.one("SELECT status FROM link_resolution WHERE link_id = 1") == "ambiguous" and k3.standing(i8c)[0] == "in_force",
          "two candidates known before the 8-K: nothing bound, no do_not_rely, an inbox item instead of a guess")
    check(k3.one("SELECT count(*) FROM link_pending") == 1, "the ambiguous link is listed as pending")
    k4, s4, r4 = edgar_kb()
    for w, t in (("K", TIMES_B1["K"]), ("E", TIMES_B1["E"]), ("K2", "2026-05-30T09:00:00Z")):
        ingest(k4, s4, r4, w, t)
        k4.apply()
    i8d = unit_by(k4, "x-0009000001-26-000010", "Item 8")
    k4.clock("2026-05-25", "2026-05-25T00:00:00Z")
    a = k4.standing(i8d)[0]
    k4.clock("2026-06-01", "2026-06-01T00:00:00Z")
    b = k4.standing(i8d)[0]
    table(k4.db, """SELECT assessment_id AS id, value, recorded_from, supersedes, rationale FROM assessment
                    WHERE rule_id IS NOT NULL ORDER BY assessment_id""", title="the binding, then a void when the key turned ambiguous", width=80)
    check((a, b) == ("do_not_rely", "in_force"),
          "a second candidate arriving later voids the derived row from then on; AS_KNOWN before it is unchanged")
    return k


# ════════════════════════════════════════════════════════════════════════════
# C. T+1 playbook superseded by a hand-written link
# ════════════════════════════════════════════════════════════════════════════
def scenario_c():
    head("C. 2022 T+1 playbook superseded by SEC Release 34-96930 (hand-written link)")
    k = KB()
    s_ind = k.source("industry-docs", "manual")
    s_fr = k.source("federal-register", "fedreg-api")
    r_fr = k.run(s_fr, "federal-register.yaml")
    pb = k.doc(s_ind, "sifma-ici-dtcc-t1-playbook-2022-08-01", "SIFMA/ICI/DTCC T+1 playbook (1 Aug 2022), our summary",
               "2026-10-01T09:00:00Z", None, access="public", sensitivity=0, publisher="sifma-ici-dtcc",
               reliability="reliable", force="guidance", authenticity="derived", trust_zone="external")
    pbu = k.unit(pb, "transition-date", "section", "normative")
    k.version(pbu, "Industry plans assume a third-quarter 2024 transition date to T+1 (summary in our words).",
              "2022-08-01", "2026-10-01T09:00:00Z", "2022-08-01")
    rel = k.doc(s_fr, "34-96930", "SEC Release 34-96930: Shortening the securities settlement cycle", "2026-10-01T09:30:00Z",
                r_fr, access="public", sensitivity=0, publisher="sec.gov", reliability="authoritative", force="official",
                authenticity="original", trust_zone="external")
    relu = k.unit(rel, "compliance-date", "section", "normative")
    k.version(relu, "Compliance date for the T+1 standard settlement cycle under Rule 15c6-1(a): May 28, 2024.",
              "2024-05-28", "2026-10-01T09:30:00Z", "2023-03-06", r_fr)
    k.ident(relu, "sec:release", "34-96930")
    k.ident(relu, "fr:cite", "88 FR 13872")
    l1 = k.link(relu, "supersedes", "human", "2026-10-02T10:00:00Z", to_unit=pbu, valid_from="2023-02-15",
                emitted_by="human:analyst-1 (profiles/federal-register.yaml manual_links)")
    k.apply()
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    table(k.db, """SELECT d.title, cl.standing, cl.supports, cl.label FROM current_labeled cl
                   JOIN document d ON d.document_id = cl.document_id""", title="CURRENT 2026-10-14", width=110)
    check(k.standing(pbu)[:2] == ("superseded", "no") and k.standing(relu)[:2] == ("in_force", "yes"),
          "CURRENT: the playbook's date is superseded (never support); the release's compliance date answers")
    k.clock("2022-12-01", "2026-10-14T00:00:00Z")
    later = k.x("""SELECT value, valid_from FROM assessment WHERE unit_id = ? AND dimension = 'standing'
                   AND valid_from > (SELECT now_valid FROM clock) AND value <> 'void'""", (pbu,)).fetchall()
    cur = k.standing(pbu)
    say(f"  AS_OF 2022-12-01 (as known now): {cur[:2]}; later: {later}")
    check(cur[:2] == ("in_force", "yes") and later == [("superseded", "2023-02-15")],
          "AS_OF 2022-12-01: in force then, labelled 'later superseded (15 Feb 2023)'")
    check(k.one("SELECT count(*) FROM current_version WHERE unit_id = ?", (relu,)) == 0,
          "AS_OF 2022-12-01: the T+1 compliance date is not yet in effect")
    k.clock("2026-10-01T12:00:00Z", "2026-10-01T12:00:00Z")
    check(k.standing(pbu)[0] == "in_force", "AS_KNOWN 2026-10-01 12:00 (before the analyst's link): in force")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    table(k.db, """SELECT s.start_unit, d1.title AS superseded, s.head_unit, d2.title AS current_head FROM supersession_head s
                   JOIN unit a ON a.unit_id = s.start_unit JOIN document d1 ON d1.document_id = a.document_id
                   JOIN unit b ON b.unit_id = s.head_unit JOIN document d2 ON d2.document_id = b.document_id""",
          title="chain head (recursive CTE, not transitive status)")
    check(k.one("SELECT head_unit FROM supersession_head WHERE start_unit = ?", (pbu,)) == relu, "the chain's head is the release")

    head("C2. The analyst withdraws the link (entered in error), then re-enters it", "-")
    k.x("UPDATE link SET recorded_to = '2026-10-05T08:00:00Z' WHERE link_id = ?", (l1,))
    k.apply()
    l2 = k.link(relu, "supersedes", "human", "2026-10-06T09:00:00Z", to_unit=pbu, valid_from="2023-02-15",
                emitted_by="human:analyst-1")
    k.apply()
    table(k.db, """SELECT assessment_id AS id, value, valid_from, recorded_from, supersedes, rationale FROM assessment
                   WHERE unit_id = ? ORDER BY assessment_id""", (pbu,), title="ledger rows for the playbook unit", width=80)
    got = []
    for t in ("2026-10-03T00:00:00Z", "2026-10-05T12:00:00Z", "2026-10-14T00:00:00Z"):
        k.clock(t, t)
        got.append(k.standing(pbu)[0])
    say(f"  as known 10-03 / 10-05 12:00 / 10-14: {got}")
    check(got == ["superseded", "in_force", "superseded"],
          "withdrawal appends a void (history kept: as known on 10-03 it was superseded); re-entry derives anew")
    check(rejected(k.db, "UPDATE link SET recorded_to = '2026-10-07T00:00:00Z' WHERE link_id = ?", (l1,)) is not None,
          "a withdrawn link cannot be re-withdrawn or edited")

    head("C3. A supersession cycle does not hang the chain walk", "-")
    xd = k.doc(s_ind, "cycle-test", "cycle test (fixture)", "2026-10-10T00:00:00Z", None)
    xa, xb = k.unit(xd, "A", "section", "normative"), k.unit(xd, "B", "section", "normative")
    k.version(xa, "A", "2026-01-01", "2026-10-10T00:00:00Z")
    k.version(xb, "B", "2026-01-01", "2026-10-10T00:00:00Z")
    k.link(xa, "supersedes", "human", "2026-10-10T00:00:00Z", to_unit=xb, valid_from="2026-01-01")
    k.link(xb, "supersedes", "human", "2026-10-10T00:00:00Z", to_unit=xa, valid_from="2026-01-01")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    heads = k.x("SELECT * FROM supersession_head WHERE start_unit IN (?, ?)", (xa, xb)).fetchall()
    check(heads == [], "A supersedes B supersedes A: the walk terminates and reports no head")
    return k


# ════════════════════════════════════════════════════════════════════════════
# D. Negative tests
# ════════════════════════════════════════════════════════════════════════════
def scenario_d(k, ids):
    head("D. Negative tests: what the schema refuses")
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    any_row = k.one("SELECT min(assessment_id) FROM assessment WHERE rule_id IS NOT NULL")
    cases = [
        ("edit a ledger row", "UPDATE assessment SET value = 'in_force' WHERE assessment_id = ?", (any_row,)),
        ("delete a ledger row", "DELETE FROM assessment WHERE assessment_id = ?", (any_row,)),
        ("overwrite a frozen trust column (reliability)", "UPDATE document SET reliability = 'doubtful' WHERE document_id = ?", (ids["acu"],)),
        ("overwrite a frozen trust column (publisher)", "UPDATE document SET publisher = 'cik:1' WHERE document_id = ?", (ids["acu"],)),
        ("a model promotes", """INSERT INTO assessment (claim_id, dimension, value, direction, recorded_from, method, authority, rated_by)
                                VALUES (?, 'verification', 'verified', 'promote', '2026-10-14T00:00:00Z', 'model', 'model', 'qwen3:8b')""", (ids["c1"],)),
        ("a rule promotes", """INSERT INTO assessment (claim_id, dimension, value, direction, recorded_from, method, authority, rated_by)
                               VALUES (?, 'verification', 'verified', 'promote', '2026-10-14T00:00:00Z', 'rule', 'profile', 'rule:x')""", (ids["c1"],)),
        ("maker = checker on a promotion", """INSERT INTO assessment (claim_id, dimension, value, direction, recorded_from, method,
                                              authority, rated_by, proposed_by) VALUES (?, 'verification', 'verified', 'promote',
                                              '2026-10-14T00:00:00Z', 'human', 'human', 'analyst-b', 'analyst-b')""", (ids["c3"],)),
        ("a promotion without a maker", """INSERT INTO assessment (claim_id, dimension, value, direction, recorded_from, method,
                                           authority, rated_by) VALUES (?, 'verification', 'verified', 'promote',
                                           '2026-10-14T00:00:00Z', 'human', 'human', 'analyst-b')""", (ids["c3"],)),
        ("a model demotion that is not provisional", """INSERT INTO assessment (unit_id, dimension, value, direction, recorded_from,
                                           method, authority, rated_by) VALUES (?, 'standing', 'concern', 'demote',
                                           '2026-10-14T00:00:00Z', 'model', 'model', 'qwen3:8b')""", (ids["acu_i3"],)),
        ("a third-party exclusion (Retraction-Watch-style) that is not provisional", """INSERT INTO assessment (unit_id, dimension,
                                           value, direction, recorded_from, method, authority, rated_by) VALUES (?, 'standing',
                                           'retracted', 'demote', '2026-10-14T00:00:00Z', 'source', 'third_party', 'some-watchdog')""", (ids["acu_i3"],)),
        ("a non-publisher exclusion dressed as 'lateral'", """INSERT INTO assessment (unit_id, dimension, value, direction,
                                           recorded_from, method, authority, rated_by) VALUES (?, 'standing', 'superseded',
                                           'lateral', '2026-10-14T00:00:00Z', 'rule', 'heuristic', 'rule:cue')""", (ids["acu_i3"],)),
        ("authority=publisher with another publisher's evidence", """INSERT INTO assessment (unit_id, dimension, value,
                                           direction, recorded_from, method, authority, rated_by, evidence_version_id) VALUES
                                           (?, 'standing', 'do_not_rely', 'demote', '2026-10-14T00:00:00Z', 'source', 'publisher',
                                           'cik:1646972', ?)""", (ids["acu_i3"], ids["v_e1"])),
        ("an unknown status value", """INSERT INTO assessment (unit_id, dimension, value, direction, recorded_from, method,
                                       authority, rated_by) VALUES (?, 'standing', 'kinda_stale', 'lateral',
                                       '2026-10-14T00:00:00Z', 'human', 'human', 'analyst-b')""", (ids["acu_i3"],)),
        ("an assessment on a claim that does not exist", """INSERT INTO assessment (claim_id, dimension, value, direction,
                                       recorded_from, method, authority, rated_by) VALUES (999, 'world', 'real', 'lateral',
                                       '2026-10-14T00:00:00Z', 'human', 'human', 'analyst-b')""", ()),
        ("edit a link resolution", "UPDATE link_resolution SET status = 'ambiguous'", ()),
        ("edit a link's target", "UPDATE link SET to_key = 'x' WHERE link_id = 1", ()),
        ("delete a link", "DELETE FROM link WHERE link_id = 1", ()),
        ("a link of an unknown type", """INSERT INTO link (from_unit, type, to_unit, origin, recorded_from)
                                         VALUES (?, 'kinda-replaces', ?, 'human', '2026-10-14T00:00:00Z')""", (ids["e1u"], ids["acu_i3"])),
        ("edit a link type's effect", "UPDATE link_type SET effect = 'none' WHERE type = 'do-not-rely'", ()),
        ("edit a rule version", "UPDATE rule_version SET body = '{}' WHERE rule_id = 'link-effect:do-not-rely'", ()),
        ("a fix with a different effective window", """INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body,
              effective_from, recorded_from, change_kind, fixes_sha256, owner) SELECT rule_id, 'abc', kind, body_format, body,
              '2027-01-01', '2026-10-14T00:00:00Z', 'fix', version_sha256, owner FROM rule_version WHERE rule_id = 'link-effect:corrects'""", ()),
        ("a source rule without an expiry", """INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, assigns,
              recorded_from, change_kind, owner) VALUES ('edgar-original', 'h', 'source_rule', 'cel', 'doc.host == ''www.sec.gov''',
              '{"dimension":"authenticity","value":"original"}', '2026-10-14T00:00:00Z', 'new', 'brian')""", ()),
        ("overwrite a blob", "UPDATE blob SET bytes = 0", ()),
    ]
    k.x("INSERT INTO blob (sha256, kind, path, bytes) VALUES ('ab', 'raw', 'raw/sha256/ab', 10)")
    for name, sql, params in cases:
        err = rejected(k.db, sql, params)
        if name in ("edit a link resolution", "overwrite a blob") and err is None:
            err = None if k.one("SELECT changes()") else "no row matched"
        check(err is not None, f"rejected: {name}  ->  {err}")
    say()
    say("  ...and the legitimate versions are accepted:")
    ok = [
        ("four-eyes promotion (maker analyst-a, checker analyst-b)", """INSERT INTO assessment (unit_id, dimension, value, direction,
            recorded_from, method, authority, rated_by, proposed_by, evidence_version_id) VALUES (?, 'verification', 'verified',
            'promote', '2026-10-14T00:00:00Z', 'human', 'human', 'analyst-b', 'analyst-a', ?)""", (ids["acu_i3"], ids["v_acu3"])),
        ("a provisional model demotion (a label)", """INSERT INTO assessment (unit_id, dimension, value, direction, provisional,
            confidence, recorded_from, method, authority, rated_by) VALUES (?, 'standing', 'concern', 'demote', 1, 0.7,
            '2026-10-14T00:00:00Z', 'model', 'model', 'qwen3:8b')""", (ids["acu_i3"],)),
        ("a single analyst's exclusion", """INSERT INTO assessment (unit_id, dimension, value, direction, recorded_from, method,
            authority, rated_by, rationale) VALUES (?, 'standing', 'withdrawn', 'demote', '2026-10-14T00:00:00Z', 'human', 'human',
            'analyst-c', 'test fixture')""", (ids["aci_unit"],)),
        ("changing access (the one mutable trust fact)", "UPDATE document SET access = 'dist:pm-desk+compliance' WHERE document_id = ?", (ids["e1"],)),
        ("a source rule with owner and expiry", """INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, assigns,
            recorded_from, change_kind, owner, review_by) VALUES ('edgar-original', 'h1', 'source_rule', 'cel',
            'doc.host == ''www.sec.gov'' && has(doc.accession)', '{"dimension":"authenticity","value":"original"}',
            '2026-01-01T00:00:00Z', 'new', 'brian', '2026-07-01')""", ()),
    ]
    for name, sql, params in ok:
        err = rejected(k.db, sql, params)
        check(err is None, f"accepted: {name}" + (f"  ({err})" if err else ""))
    k.clock("2026-10-14", "2026-10-14T00:00:00Z")
    table(k.db, "SELECT rule_id, owner, review_by, assigns FROM source_rule_due", title="expired source rules -> one renewal item each")
    check(k.one("SELECT count(*) FROM source_rule_due") == 1, "an expired source rule comes back as one renewal item")
    st = k.x("SELECT standing, supports, label FROM current_labeled WHERE unit_id = ?", (ids["acu_i3"],)).fetchone()
    check(st[0] == "in_force" and st[1] == "labelled" and "concern (provisional" in st[2],
          "the provisional model flag labels ACU's Item 3 but does not exclude it")


# ════════════════════════════════════════════════════════════════════════════
# E. A rule fix versus an effective-dated new rule version
# ════════════════════════════════════════════════════════════════════════════
def scenario_e():
    head("E. Rule versions: a FIX (interpretation) versus a NEW version (the world's rule changed)")
    say("Rule 'link-effect:corrects' maps an official correction notice (authority markup) to a status.")
    say("  seed (2026-01-01)      markup -> corrected (label)")
    say("  bad fix (2026-06-01)   markup -> superseded            (a mistaken 'fix' of the seed)")
    say("  good fix (2026-09-01)  markup -> corrected             (fixes the bad fix)")
    say("  v2 NEW (adopted 2026-10-01, effective 2027-01-01, hypothetical regime in which corrections have")
    say("         legal effect)    markup -> amended")
    k = KB()
    s = k.source("federal-register", "fedreg-api")
    r = k.run(s, "federal-register.yaml")
    trust = dict(access="public", sensitivity=0, reliability="authoritative", force="official",
                 authenticity="original", trust_zone="external")
    rule = k.doc(s, "x-fr-2026-00001", "Final rule (synthetic fixture)", "2026-03-01T12:00:00Z", r, publisher="agency:x-regulator", **trust)
    ru = k.unit(rule, "§ 1(a)", "section", "normative")
    k.version(ru, "§ 1(a) A covered firm shall report within five business days (synthetic).", "2026-04-01",
              "2026-03-01T12:00:00Z", "2026-03-01", r)
    k.ident(ru, "fr:doc", "x-fr-2026-00001")
    corr = k.doc(s, "x-fr-C6-00001", "Correcting amendment (synthetic fixture, published by the Federal Register office)",
                 "2026-06-15T15:00:00Z", r, publisher="agency:ofr", **trust)
    cu = k.unit(corr, "correction", "section", "record")
    k.version(cu, "In § 1(a), 'five business days' is corrected to read 'five calendar days' (synthetic).", "2026-06-15",
              "2026-06-15T15:00:00Z", "2026-06-15", r)
    k.link(cu, "corrects", "status+link", "2026-06-15T15:00:00Z", key=("fr:doc", "x-fr-2026-00001"), valid_from="2026-06-15",
           emitted_by="profile:federal-register#relations.correction_of")
    seed = k.x("SELECT version_sha256, body FROM rule_version WHERE rule_id = 'link-effect:corrects'").fetchone()

    def variant(body, value):
        b = json.loads(body)
        for row in b["rows"]:
            if row["authority"] == "markup":
                row["value"] = value
        txt = json.dumps(b, sort_keys=True, separators=(",", ":"))
        return sha256_text(txt), txt

    bad_sha, bad = variant(seed[1], "superseded")
    good_sha, good = variant(seed[1], "corrected")
    good = good.replace('"link_type":"corrects"', '"link_type":"corrects","note":"fix of bad fix"')
    good_sha = sha256_text(good)
    v2_sha, v2 = variant(seed[1], "amended")
    ins = """INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, effective_from, recorded_from,
             change_kind, fixes_sha256, owner, review_by) VALUES ('link-effect:corrects', ?, 'consequence', 'json', ?, ?, ?, ?, ?, 'brian', '2027-04-14')"""
    k.x(ins, (bad_sha, bad, None, "2026-06-01T00:00:00Z", "fix", seed[0]))
    k.apply()
    k.x(ins, (good_sha, good, None, "2026-09-01T00:00:00Z", "fix", bad_sha))
    k.apply()
    k.x(ins, (v2_sha, v2, "2027-01-01", "2026-10-01T00:00:00Z", "new", None))
    k.apply()
    table(k.db, """SELECT rule_id, substr(version_sha256, 1, 10) AS sha, change_kind, substr(fixes_sha256, 1, 10) AS fixes,
                   effective_from, recorded_from FROM rule_version WHERE rule_id = 'link-effect:corrects' ORDER BY recorded_from""",
          title="versions of link-effect:corrects")
    table(k.db, """SELECT assessment_id AS id, target_kind || ':' || target_id AS target, value, valid_from, recorded_from,
                   substr(rule_sha256, 1, 10) AS rule_sha, supersedes AS sup, rationale FROM assessment
                   WHERE document_id = ? AND dimension = 'standing' ORDER BY assessment_id""", (rule,),
          title="ledger rows on the corrected rule (the fr:doc key binds the whole document)", width=60)
    expect = [("2026-07-01", "2026-07-01T00:00:00Z", "superseded", "AS_KNOWN 07-01, valid July: the bad fix, as known then"),
              ("2026-07-01", "2026-08-01T00:00:00Z", "superseded", "AS_KNOWN 08-01 (before the good fix): history unchanged"),
              ("2026-07-01", "2026-09-15T00:00:00Z", "corrected", "FIX: from its adoption, July's status changes too"),
              ("2026-12-01", "2026-10-14T00:00:00Z", "corrected", "NEW: valid times before 2027-01-01 are left intact"),
              ("2027-02-01", "2026-09-15T00:00:00Z", "corrected", "NEW: before its adoption, 2027 still reads 'corrected'"),
              ("2027-02-01", "2026-10-14T00:00:00Z", "amended", "NEW: from 2027-01-01, as known after adoption")]
    say()
    say("  valid      | as known             | standing     | why")
    for valid, rec, want, why in expect:
        k.clock(valid, rec)
        got = k.one("SELECT standing FROM current_labeled WHERE unit_id = ?", (ru,))
        say(f"  {valid} | {rec} | {got:<12} | {why}")
        check(got == want, f"{why}: {want}")
    n = k.one("SELECT count(*) FROM assessment")
    k.apply()
    check(k.one("SELECT count(*) FROM assessment") == n, "apply is idempotent after rule changes")
    return k


# ════════════════════════════════════════════════════════════════════════════
# F. Integrity: hashed rules, catalogue and profiles
# ════════════════════════════════════════════════════════════════════════════
def scenario_f():
    head("F. Integrity: rule hashes, catalogue and profiles")
    k = KB()
    bad = [r[0] for r in k.x("SELECT rule_id, version_sha256, body FROM rule_version").fetchall()
           if sha256_text(k.one("SELECT body FROM rule_version WHERE rule_id = ?", (r[0],))) !=
           k.one("SELECT version_sha256 FROM rule_version WHERE rule_id = ?", (r[0],))]
    check(not bad, f"every seeded rule body hashes to its version_sha256 {bad or ''}")
    for rid, view in [("resolve-key", "desired_link_resolution"), ("derive-link-effect", "derive_link_effect"),
                      ("derive-resolves", "derive_resolves")]:
        installed = k.one("SELECT sql FROM sqlite_master WHERE type = 'view' AND name = ?", (view,))
        check(sha256_text(installed) == k.one("SELECT version_sha256 FROM rule_version WHERE rule_id = ?", (rid,)),
              f"the installed view {view} is exactly rule {rid}")
    try:
        import yaml  # optional: not stdlib
    except ImportError:
        say("  (PyYAML not installed: YAML cross-checks skipped)")
        return
    for f in sorted(os.listdir(PROFILES)):
        if f.endswith(".yaml"):
            doc = yaml.safe_load(open(os.path.join(PROFILES, f)))
            check(isinstance(doc, dict) and "source_id" in doc and "match" in doc, f"profiles/{f} parses, has source_id and match")
    lt = yaml.safe_load(open(os.path.join(KBDIR, "link-types.yaml")))["link_types"]
    db_lt = {r[0]: r for r in k.x("SELECT type, inverse, scope, effect, effect_on, effect_value, time_anchor, exclusion_requires FROM link_type")}
    same = set(lt) == set(db_lt) and all(
        (t["inverse"], t["scope"], t["effect"], t["effect_on"], t["effect_value"], t["time_anchor"], ",".join(t["exclusion_requires"]))
        == db_lt[n][1:] for n, t in lt.items())
    check(same, f"link-types.yaml matches the seeded link_type table ({len(lt)} types)")
    cq = yaml.safe_load(open(os.path.join(KBDIR, "consequences.yaml")))["rules"]
    same = all(k.one("SELECT body FROM rule_version WHERE rule_id = ?", (f"link-effect:{n}",)) ==
               json.dumps({"link_type": n, "rows": rows}, sort_keys=True, separators=(",", ":")) for n, rows in cq.items())
    check(same and len(cq) == k.one("SELECT count(*) FROM rule_version WHERE rule_id LIKE 'link-effect:%'"),
          f"consequences.yaml compiles to exactly the seeded rule bodies ({len(cq)} rules)")


def main():
    say("Knowledge base schema v2: end-to-end walkthrough and tests")
    say(f"SQLite {sqlite3.sqlite_version}; schema.sql + extensions.sql loaded into :memory:; apply.sql is the rule step.")
    say("Generated by docs/kb-schema/tests/test_schema.py. Real-company rows carry only what the research reports")
    say("cite (ACU's accession and Item 3 sentence, CIKs, tickers, the Prague LEI); other text is illustrative or fictional.")
    k, ids = scenario_a()
    ids["aci_unit"] = k.one("SELECT unit_id FROM unit WHERE document_id = ? AND anchor = 'Item 1'", (ids["aci"],))
    scenario_b()
    scenario_c()
    scenario_d(k, ids)
    scenario_e()
    scenario_f()
    head("Summary")
    say(f"  {PASSES[0]} checks passed, {len(FAILS)} failed")
    for f in FAILS:
        say(f"  FAILED: {f}")
    with open(OUT, "w") as fh:
        fh.write("\n".join(LINES) + "\n")
    print(f"{PASSES[0]} checks passed, {len(FAILS)} failed; trace written to {OUT}")
    for f in FAILS:
        print("FAILED:", f)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
