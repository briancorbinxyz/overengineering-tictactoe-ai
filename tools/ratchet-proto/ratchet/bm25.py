"""BM25 with SQLite FTS5, as the planned Java/SQLite build will run it.

Three weighted columns: ``title`` (page title, heading path and the element's own heading) x5,
``ident`` (the element id) x10, ``body`` x1. The tokenizer is FTS5's default ``unicode61``, which
splits on '-', so "file" matches "40-file" and the phrase "FR-012" matches the tokens "fr 012".
(``tokenchars '-'`` keeps "40-file" as one token, which the earlier prototype used; it is
available as ``dash_tokens=True`` to reproduce its numbers.)

The query is every non-stopword token of the question, each quoted as a phrase, OR-ed.
"""

from __future__ import annotations

import re
import sqlite3

STOP = set(
    "a an the of in on for to and or is are was were be by with what which how does do did that this it its "
    "as at from when who whom why where after before into than then there their they them should must can "
    "could would will spec spectastic say says about".split()
)
WEIGHTS = (5.0, 10.0, 1.0)


def fts_query(q: str) -> str:
    toks = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", q) if t.lower() not in STOP]
    return " OR ".join('"%s"' % t.replace('"', '""') for t in toks)


class BM25:
    def __init__(self, items: list, dash_tokens: bool = False, weights=WEIGHTS):
        self.items = items
        self.weights = weights
        self.db = sqlite3.connect(":memory:")
        tok = "unicode61 tokenchars '-'" if dash_tokens else "unicode61"
        self.db.execute(f'create virtual table f using fts5(title, ident, body, tokenize="{tok}")')
        self.db.executemany(
            "insert into f(rowid, title, ident, body) values (?,?,?,?)",
            [(it.n, " ".join(x for x in (it.path or it.title, it.heading) if x), it.anchor, it.text) for it in items],
        )
        self.db.commit()

    def search(self, q: str, allow=None, depth: int = 100, scope=None) -> list:
        """[(item n, score)] best first; score is -bm25 (higher is better). ``allow(n)`` filters
        before the depth cut, as a store-side filter would; ``scope`` restricts to a set of item ns."""
        m = fts_query(q)
        if not m:
            return []
        w = self.weights
        sql = f"select rowid, bm25(f,{w[0]},{w[1]},{w[2]}) as s from f where f match ?"
        args = [m]
        if scope is not None:
            sql += " and rowid in (select value from json_each(?))"
            import json

            args.append(json.dumps(sorted(scope)))
        sql += " order by s, rowid"
        out = []
        for n, s in self.db.execute(sql, args):
            if allow is None or allow(n):
                out.append((n, -s))
                if len(out) >= depth:
                    break
        return out
