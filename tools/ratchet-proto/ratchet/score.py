"""Scoring a ranked list against the golden set, and the ratchet rule.

Element units: an item is a hit for an expected address when it *is* that element (or one part of
it). Naive chunks: the Episode 3 rule (``GoldenScorer.java``), ported: a chunk that holds the
element's text whole is a hit, one that holds at least half of it is a partial hit, judged by
overlap with the element's position in the page text.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

STRATA = ["single-fact", "paraphrase", "identifier", "relation", "stale"]
FULL, PARTIAL, NONE = 2, 1, 0

_JWS = re.compile(r"[ \t\n\x0b\f\r]+")  # Java's \s


def normalise(s: str | None) -> str:
    return "" if s is None else _JWS.sub(" ", s).strip(" \t\n\x0b\f\r\x1c\x1d\x1e\x1f")


class ChunkScorer:
    """Port of GoldenScorer.hit(): page text and element text read the way jsoup reads them."""

    def __init__(self, pages: dict, element_text: dict):
        self.pages = {k: normalise(v) for k, v in pages.items()}
        self.element_text = element_text  # address -> normalised jsoup text of getElementById

    def hit(self, address: str, item) -> int:
        file = address.split("#")[0]
        if file != item.source:
            return NONE
        page = self.pages[file]
        element = self.element_text.get(address, "")
        text = normalise(item.text)
        if not element or not text:
            return NONE
        c0 = page.find(text)
        if c0 < 0 or len(element) < 2:
            if element in text:
                return FULL
            half = max(1, len(element) // 2)
            return PARTIAL if (element[:half] in text or element[half:] in text) else NONE
        best = 0
        e0 = page.find(element)
        while e0 >= 0:
            overlap = min(e0 + len(element), c0 + len(text)) - max(e0, c0)
            best = max(best, overlap)
            e0 = page.find(element, e0 + 1)
        if best >= len(element):
            return FULL
        return PARTIAL if best * 2 >= len(element) else NONE


def unit_hit(address: str, item) -> int:
    return FULL if item.anchor and f"{item.source}#{item.anchor}" == address else NONE


@dataclass
class QResult:
    qid: str
    stratum: str
    expected: list
    ranks: list  # per expected address: first rank (1-based) of a full hit, or None
    partial_ranks: list  # per expected address: first rank of a full-or-partial hit
    stale_ranks: list  # per stale address: first rank of a full-or-partial hit
    top: list  # addresses of the first 10 items
    context_tokens: int  # tokens of the first 4 passages
    top1_score: float | None
    pinned: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def first(self):
        r = [x for x in self.ranks if x]
        return min(r) if r else None

    @property
    def first_partial(self):
        r = [x for x in self.partial_ranks if x]
        return min(r) if r else None

    def hit_at(self, k):
        return self.first is not None and self.first <= k

    def partial_at(self, k):
        return self.first_partial is not None and self.first_partial <= k

    def all_at(self, k):
        return bool(self.ranks) and all(r is not None and r <= k for r in self.ranks)

    def stale_at(self, k):
        return any(r is not None and r <= k for r in self.stale_ranks)

    def rr(self, k=50):
        return 1.0 / self.first if self.first and self.first <= k else 0.0


def rank_list(items: list, q: dict, hit_fn, passage_tokens, top1_score=None, pinned=0) -> QResult:
    ranks, partials, stales = [], [], []
    for addr in q["expected"]:
        f = p = None
        for n, it in enumerate(items, 1):
            h = hit_fn(addr, it)
            if h == FULL and f is None:
                f = n
            if h != NONE and p is None:
                p = n
            if f is not None:
                break
        ranks.append(f)
        partials.append(p)
    for addr in q.get("stale") or []:
        s = None
        for n, it in enumerate(items[:10], 1):
            if hit_fn(addr, it) != NONE:
                s = n
                break
        stales.append(s)
    ctx = sum(passage_tokens(it) for it in items[:4])
    return QResult(q["id"], q["stratum"], list(q["expected"]), ranks, partials, stales,
                   [it.address for it in items[:10]], ctx, top1_score, pinned)


@dataclass
class Agg:
    n: int = 0
    h4: int = 0
    p4: int = 0
    h10: int = 0
    all4: int = 0
    all10: int = 0
    stale4: int = 0
    rr50: float = 0.0
    rr4: float = 0.0

    def add(self, r: QResult):
        self.n += 1
        self.h4 += r.hit_at(4)
        self.p4 += r.partial_at(4)
        self.h10 += r.hit_at(10)
        self.all4 += r.all_at(4)
        self.all10 += r.all_at(10)
        self.stale4 += r.stale_at(4)
        self.rr50 += r.rr(50)
        self.rr4 += r.rr(4)

    @property
    def mrr(self):
        return self.rr50 / self.n if self.n else 0.0

    @property
    def mrr4(self):
        return self.rr4 / self.n if self.n else 0.0


def aggregate(results: list) -> tuple[Agg, dict]:
    tot = Agg()
    by = {s: Agg() for s in STRATA}
    for r in results:
        if r.stratum == "unanswerable":
            continue
        tot.add(r)
        by[r.stratum].add(r)
    return tot, by


def context_stats(results: list) -> dict:
    xs = [r.context_tokens for r in results]
    return {"mean": statistics.mean(xs), "p50": statistics.median(xs), "max": max(xs)} if xs else {}


def top1_split(results: list) -> dict:
    a = [r.top1_score for r in results if r.stratum != "unanswerable" and r.top1_score is not None and not r.pinned]
    u = [r.top1_score for r in results if r.stratum == "unanswerable" and r.top1_score is not None]

    def d(xs):
        if not xs:
            return None
        xs = sorted(xs)
        return {"n": len(xs), "min": xs[0], "p25": xs[len(xs) // 4], "p50": statistics.median(xs), "max": xs[-1]}

    return {"answerable_unpinned": d(a), "unanswerable": d(u)}


def ratchet(prev: list, cur: list) -> tuple[bool, list]:
    """Fail if overall Hit@4 or all-evidence@4 drops, any stratum loses more than one question
    at Hit@4, or stale-in-top-4 rises. Returns (passed, reasons)."""
    pt, pb = aggregate(prev)
    ct, cb = aggregate(cur)
    why = []
    if ct.h4 < pt.h4:
        why.append(f"Hit@4 {pt.h4}→{ct.h4}")
    if ct.all4 < pt.all4:
        why.append(f"all@4 {pt.all4}→{ct.all4}")
    for s in STRATA:
        if pb[s].h4 - cb[s].h4 > 1:
            why.append(f"{s} {pb[s].h4}→{cb[s].h4}")
    if ct.stale4 > pt.stale4:
        why.append(f"stale@4 {pt.stale4}→{ct.stale4}")
    return (not why), why


def flips(prev: list, cur: list, k: int = 4) -> tuple[list, list]:
    """Questions that went miss→hit and hit→miss at k."""
    p = {r.qid: r for r in prev}
    won = [r.qid for r in cur if r.stratum != "unanswerable" and r.hit_at(k) and not p[r.qid].hit_at(k)]
    lost = [r.qid for r in cur if r.stratum != "unanswerable" and not r.hit_at(k) and p[r.qid].hit_at(k)]
    return won, lost
