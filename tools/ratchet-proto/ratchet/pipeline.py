"""The retrieval configurations: Episode 4's main line, Episode 5's two graph steps, ablations.

One question goes through, in order:

1. candidate lists: BM25 and/or dense, each over items the lifecycle filter allows (a filter
   applied before the depth cut, as a store-side filter would be);
2. fusion: reciprocal rank fusion, sum of 1/(60 + rank), when there are two lists;
3. identifier lookup: pinned units go first, above the fusion, in pin order;
4. reranker: the cross-encoder reorders the first 50 unpinned items;
5. anchored typed expansion (E5-2): typed-link neighbours of the first pinned unit, inserted right
   after it;
6. supersession redirect (E5-1): a stale item is replaced by its current successor; applied
   history is kept, right behind it.

Every list is cut to 50 items.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass

import numpy as np

from .corpus import EXCLUDED

DEPTH_SINGLE = 50
DEPTH_FUSED = 100  # each list's depth before fusion
RRF_K = 60
RERANK_TOP = 50
EXPAND_MAX = 5
TYPED_WEIGHTS = {"typed:validates": 2.0, "typed:cites": 2.0, "typed:delta": 2.0, "typed:target": 1.5, "typed:defer-to": 1.5}


@dataclass
class Config:
    key: str
    label: str
    items: str = "units"  # units | chunks
    bm25: bool = True
    dense: bool = False
    ids: bool = False
    lifecycle: bool = False
    rerank: bool = False
    expand: bool = False
    redirect: str | None = None  # None | "behind" | "replace"
    rrf_neighbours: bool = False
    corpus: str = "ep4"  # ep4 | legacy (earlier prototype's units: no heading path, no parts)
    dash_tokens: bool = False  # FTS5 tokenchars '-' (earlier prototype)
    linker: str = "ep4"  # ep4 | prior
    needs: tuple = ()  # "dense", "rerank"


def rrf(lists: list, k: int = RRF_K, weights=None) -> list:
    sc = collections.defaultdict(float)
    order = {}
    for li, L in enumerate(lists):
        w = 1.0 if weights is None else weights[li]
        for r, (n, _) in enumerate(L, 1):
            sc[n] += w / (k + r)
            order.setdefault(n, (li, r))
    return sorted(((n, s) for n, s in sc.items()), key=lambda x: (-x[1], order[x[0]]))


class Index:
    """Everything one item set (units or chunks) needs: BM25, vectors, keys."""

    def __init__(self, items, bm25, vectors=None):
        self.items = items
        self.bm25 = bm25
        self.vectors = vectors
        self.live = np.array([it.lifecycle not in EXCLUDED for it in items])

    def dense(self, qv, lifecycle: bool, depth: int) -> list:
        sims = self.vectors @ qv
        if lifecycle:
            sims = np.where(self.live, sims, -np.inf)
        top = np.argsort(-sims, kind="stable")[:depth]
        return [(int(n), float(sims[n])) for n in top if np.isfinite(sims[n])]


class Graph:
    def __init__(self, corpus, idindex):
        self.adj = collections.defaultdict(list)  # node -> [(node, weight, type)]
        for s, d, t in corpus.edges:
            s, d = tuple(s), tuple(d)
            w = TYPED_WEIGHTS.get(t, 1.0)
            self.adj[s].append((d, w, t))
            self.adj[d].append((s, w, t))
        self.supersede = corpus.supersede
        self.page_supersede = {k: v for k, v in corpus.page_supersede.items() if k != v}
        self.idx = idindex

    def typed_neighbours(self, key: str) -> list:
        out = []
        for (kind, d), w, t in self.adj[("u", key)]:
            if kind == "u" and t.startswith("typed:") and d not in out:
                out.append(d)
        return out


class Pipeline:
    def __init__(self, units: Index, chunks: Index | None, idindex, graph: Graph, reranker=None):
        self.u = units
        self.c = chunks
        self.idx = idindex
        self.g = graph
        self.reranker = reranker

    # --- helpers ----------------------------------------------------------------------------
    def _key(self, n):
        it = self.u.items[n]
        return f"{it.source}#{it.anchor}"

    def _live_items(self, key, lifecycle):
        ns = self.idx.items(key)
        return [n for n in ns if not lifecycle or self.u.items[n].lifecycle not in EXCLUDED]

    def _best_part(self, q, key):
        ns = self.idx.items(key)
        if len(ns) == 1:
            return ns[0]
        r = self.u.bm25.search(q, depth=len(ns), scope=ns)
        return r[0][0] if r else ns[0]

    def _best_in_page(self, q, page, cache):
        if (q, page) not in cache:
            scope = [it.n for it in self.u.items if it.source == page and it.lifecycle not in EXCLUDED]
            r = self.u.bm25.search(q, depth=1, scope=scope) if scope else []
            cache[(q, page)] = r[0][0] if r else None
        return cache[(q, page)]

    # --- one question ----------------------------------------------------------------------
    def run(self, cfg: Config, q: str, qv=None) -> tuple[list, float | None, int]:
        ix = self.u if cfg.items == "units" else self.c
        items = ix.items
        allow = (lambda n: items[n].lifecycle not in EXCLUDED) if cfg.lifecycle else None
        depth = DEPTH_FUSED if (cfg.bm25 and cfg.dense) else DEPTH_SINGLE
        lists = []
        if cfg.bm25:
            lists.append(ix.bm25.search(q, allow=allow, depth=depth))
        if cfg.dense:
            lists.append(ix.dense(qv, cfg.lifecycle, depth))
        fused = rrf(lists) if len(lists) > 1 else lists[0]

        pinned_keys, pinned = [], []
        if cfg.ids and cfg.items == "units":
            pinned_keys = [k for k in self.idx.lookup(q, cfg.linker) if self._live_items(k, cfg.lifecycle)]
            for k in pinned_keys:
                pinned += [n for n in self._live_items(k, cfg.lifecycle) if n not in pinned]
        pinned_set = set(pinned)
        rest = [(n, s) for n, s in fused if n not in pinned_set]

        if cfg.rerank:
            head = rest[:RERANK_TOP]
            scores = self.reranker.scores(q, [items[n].passage() for n, _ in head])
            order = sorted(range(len(head)), key=lambda i: -scores[i])
            rest = [(head[i][0], scores[i]) for i in order] + rest[RERANK_TOP:]

        top1 = rest[0][1] if rest else None
        final = (pinned + [n for n, _ in rest])[:50]

        if cfg.expand and pinned_keys:
            final = self.expand(final, pinned_keys[0], q)
        if cfg.rrf_neighbours:
            final = self.rrf_neighbours(final, q)
        if cfg.redirect:
            final = self.redirect(final, q, cfg.redirect)
        return final[:50], top1, len(pinned)

    # --- Episode 5 --------------------------------------------------------------------------
    def expand(self, final, anchor_key, q):
        """E5-2: typed-link neighbours of the anchor (validates, cites, target incl. spec-delta,
        defer-to resolved to a unit), one hop, at most 5 units, ranked by BM25 among themselves,
        inserted right after the anchor's own item(s)."""
        cand = [k for k in self.g.typed_neighbours(anchor_key) if self._live_items(k, True)]
        if not cand:
            return final
        scope = [n for k in cand for n in self._live_items(k, True)]
        ranked = [n for n, _ in self.u.bm25.search(q, depth=len(scope), scope=scope)]
        units_in_order, best = [], {}
        for n in ranked:
            k = self._key(n)
            if k not in best:
                best[k] = n
                units_in_order.append(k)
        for k in cand:
            if k not in best:
                best[k] = self._live_items(k, True)[0]
                units_in_order.append(k)
        nb = [best[k] for k in units_in_order[:EXPAND_MAX]]
        anchor_items = [n for n in final if self._key(n) == anchor_key] or self._live_items(anchor_key, True)
        head = anchor_items + [n for n in nb if n not in anchor_items]
        return head + [n for n in final if n not in head]

    def redirect(self, final, q, mode):
        """E5-1: replace each stale item by the current element that superseded it (spec-delta
        targets, in-place 'superseded' status with a link, prose 'superseded by'), following up to
        three hops; a superseded page maps by the same anchor, else its best BM25 unit. With
        ``mode="behind"`` an applied-history item (an archived change) stays, right behind its
        successor; anything else stale is dropped."""
        out = []
        cache = {}
        for n in final:
            it = self.u.items[n]
            key = j = self._key(n)
            for _ in range(3):
                if j in self.g.supersede:
                    j = self.g.supersede[j]
                elif j.split("#")[0] in self.g.page_supersede:
                    tp = self.g.page_supersede[j.split("#")[0]]
                    cand = f"{tp}#{j.split('#')[1]}"
                    if self.idx.items(cand):
                        j = cand
                    else:
                        b = self._best_in_page(q, tp, cache)
                        if b is None:
                            break
                        j = self._key(b)
                else:
                    break
            if j == key:
                if n not in out:
                    out.append(n)
                continue
            m = self._best_part(q, j)
            if m not in out:
                out.append(m)
            if mode == "behind" and it.lifecycle == "history" and n not in out:
                out.append(n)
        return out

    def rrf_neighbours(self, final, q, seeds_n=5, add=5, gw=0.5, k=RRF_K):
        """Epilogue (measured worse before): neighbours of the first five items over all link
        types, scored by link weight / seed rank, RRF-merged with the list (k=60, weight 0.5);
        the seeds themselves are not in the graph list."""
        cache = {}
        seeds = final[:seeds_n]
        seed_keys = {self._key(s) for s in seeds}
        sc = collections.defaultdict(float)
        for r, s in enumerate(seeds):
            it = self.u.items[s]
            for node, f in ((("u", self._key(s)), 1.0), (("p", it.source), 0.5)):
                for (kind, d), w, t in self.g.adj[node]:
                    if kind == "u":
                        if not self._live_items(d, True):
                            continue
                        uk, ww = d, w
                    else:
                        b = self._best_in_page(q, d, cache)
                        if b is None:
                            continue
                        uk, ww = self._key(b), w * 0.5
                    if uk in seed_keys:
                        continue
                    sc[uk] += ww * f / (r + 1)
        graph = [self._best_part(q, uk) for uk, _ in sorted(sc.items(), key=lambda x: -x[1])[:add]]
        merged = rrf([[(n, 0) for n in final], [(n, 0) for n in graph]], k=k, weights=[1.0, gw])
        return [n for n, _ in merged][:50]
