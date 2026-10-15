#!/usr/bin/env python3
"""Regenerate the link_type / rule_version seed in extensions.sql from link-types.yaml and
consequences.yaml (needs PyYAML). Run after editing either YAML file, or after editing one of the
SQL-bodied rule views (resolver, derive_*), whose sha256 is pinned in the seed. test_schema.py
checks that the seed, the YAML and the installed views agree."""
import hashlib, json, os, sqlite3, yaml
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"
lt = yaml.safe_load(open(D + "link-types.yaml"))["link_types"]
cq = yaml.safe_load(open(D + "consequences.yaml"))["rules"]
ADOPTED = "2026-01-01T00:00:00Z"; OWNER = "kb-schema"; REVIEW = "2027-04-14"

def q(v):
    if v is None: return "NULL"
    if isinstance(v, bool): return "1" if v else "0"
    if isinstance(v, (int, float)): return repr(v)
    return "'" + str(v).replace("'", "''") + "'"

out = ["-- link types (link-types.yaml)", "INSERT INTO link_type VALUES"]
rows = []
for name, t in lt.items():
    i = t.get("interop") or {}
    rows.append("  (" + ", ".join(q(x) for x in [
        name, t["inverse"], t["scope"], t["effect"], t["effect_on"], t["effect_value"], t["time_anchor"],
        ",".join(t["exclusion_requires"]), 1 if t["transitive"] else 0,
        i.get("dcterms"), i.get("cito"), i.get("prov"), i.get("crossmark"), i.get("eli"), t.get("note")]) + ")")
out.append(",\n".join(rows) + ";")

def body_of(link_type, rows):
    return json.dumps({"link_type": link_type, "rows": rows}, sort_keys=True, separators=(",", ":"))

out.append("-- consequence rules (consequences.yaml), one rule per link type")
out.append("INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, effective_from, recorded_from, change_kind, owner, review_by) VALUES")
rows = []
for name, r in cq.items():
    b = body_of(name, r)
    sha = hashlib.sha256(b.encode()).hexdigest()
    rows.append("  (" + ", ".join(q(x) for x in [f"link-effect:{name}", sha, "consequence", "json", b, None, ADOPTED, "new", OWNER, REVIEW]) + ")")
out.append(",\n".join(rows) + ";")

# SQL-bodied rules: the installed view text IS the body; its hash is pinned here and re-checked by the tests.
db = sqlite3.connect(":memory:")
db.executescript(open(D + "schema.sql").read())
ext = open(D + "extensions.sql").read()
db.executescript(ext[:ext.index("-- BEGIN GENERATED SEED")])
out.append("-- SQL-bodied rules: the installed view is the rule; sha256 of sqlite_master.sql pinned here")
for rid, view, kind in [("resolve-key", "desired_link_resolution", "detection"),
                        ("derive-link-effect", "derive_link_effect", "consequence"),
                        ("derive-resolves", "derive_resolves", "consequence")]:
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='view' AND name=?", (view,)).fetchone()[0]
    sha = hashlib.sha256(sql.encode()).hexdigest()
    out.append(f"INSERT INTO rule_version (rule_id, version_sha256, kind, body_format, body, effective_from, recorded_from, change_kind, owner, review_by)\n"
               f"SELECT {q(rid)}, {q(sha)}, {q(kind)}, 'sql', sql, NULL, {q(ADOPTED)}, 'new', {q(OWNER)}, {q(REVIEW)}\n"
               f"FROM sqlite_master WHERE type = 'view' AND name = {q(view)};")
seed = "\n".join(out)
s = ext
a = s.index("-- BEGIN GENERATED SEED") + len("-- BEGIN GENERATED SEED")
b = s.index("-- END GENERATED SEED")
s = s[:a] + "\n" + seed + "\n" + s[b:]
open(D + "extensions.sql", "w").write(s)
print("seed written:", len(lt), "link types,", len(cq), "consequence rules")
