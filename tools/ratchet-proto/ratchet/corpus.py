"""Reads a spectastic checkout into the three things the harness retrieves over.

- **Pages** for the naive baseline: each file's ``<body>`` text exactly as Spring AI's
  ``JsoupDocumentReader`` reads it, split by the ``TokenTextSplitter`` port (``splitter.py``).
- **Element units** (Episode 4 step 1): one unit per element with an ``id``, holding only its own
  text (text of id'd descendants belongs to their own units), with a heading path and a lifecycle.
  Units of three words or fewer are dropped. Units over ``PART_WORDS`` words are split into parts at
  sentence ends; every part carries the unit's address.
- **Links** for Episode 5: typed attribute links (validates, cites, target, defer-to), hrefs, and a
  supersession map (stale element -> the current one that replaced it).

The unit and link rules are the earlier prototype's (``units.py``, ``graph.py`` in the
"Graph traversal before retrieval" notes), rebuilt on the standard-library parser. ``legacy=True``
reproduces that prototype's units exactly (no heading path, no parts) for comparison.
"""

from __future__ import annotations

import collections
import json
import math
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import html as H

FORMAT = "units-v1"
PART_WORDS = 250  # a unit longer than this is split; ~350 cl100k tokens, so query + part fit a 512-wordpiece reranker
MIN_WORDS = 3
EXCLUDED = {"withdrawn", "superseded", "rejected"}
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


@dataclass
class Item:
    """One retrievable thing: an element unit (or one part of it), or a naive chunk."""

    n: int  # position in the corpus list
    source: str  # specs/<spec>/<file>.html
    anchor: str  # element id; "" for a naive chunk
    spec: str
    lifecycle: str  # current | history | withdrawn | superseded | rejected
    title: str  # page title
    path: str  # heading path: title › ancestor headings (prefixed to the text)
    heading: str  # the element's own heading, if any
    text: str
    part: int = 1
    parts: int = 1
    chunk: int = 0  # naive chunks: 1-based index in the page

    @property
    def address(self) -> str:
        return f"{self.source}#{self.anchor}" if self.anchor else f"{self.source}, chunk {self.chunk}"

    def passage(self) -> str:
        """What a reader (the LLM, the embedder, the reranker) is given."""
        if not self.anchor:
            return self.text
        return f"{self.path}\n{self.text}" if self.path else self.text


def html_files(root: Path) -> list[Path]:
    return sorted((p for p in (root / "specs").rglob("*.html")), key=lambda p: p.as_posix())


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def spec_of(source: str) -> str:
    parts = source.split("/")
    return parts[1] if len(parts) > 1 else ""


def lifecycle(source: str, el: H.Element) -> str:
    if "/changes/withdrawn/" in source:
        return "withdrawn"
    st = [el.get("data-status") or el.get("status")] + [
        a.get("data-status") or a.get("status") for a in el.ancestors()
    ]
    st = [s for s in st if s]
    if any(s in EXCLUDED for s in st):
        return st[0] if st[0] in EXCLUDED else "superseded"
    if "/changes/archive/" in source:
        return "history"
    return "current"


def _strip_join(el: H.Element) -> str:
    """BeautifulSoup get_text(' ', strip=True), then collapsed."""
    out = []

    def walk(e):
        for c in e.children:
            if isinstance(c, H.Text):
                s = c.data.strip()
                if s:
                    out.append(s)
            elif c.tag not in H.RAW:
                walk(c)

    walk(el)
    return H.collapse(" ".join(out))


def _own_heading(el: H.Element) -> str:
    for c in el.children:
        if isinstance(c, H.Element) and c.tag in HEADINGS:
            return _strip_join(c)
    return ""


def heading_path(title: str, el: H.Element) -> str:
    hs = [title] if title else []
    for a in reversed(list(el.ancestors())):
        if a.id and a.tag not in ("body", "main", "html"):
            h = _own_heading(a)
            if h and (not hs or hs[-1] != h):
                hs.append(h)
    return " › ".join(hs)


_SENT = re.compile(r"(?<=[.!?;:])\s+")


def split_parts(text: str, max_words: int = PART_WORDS) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    n = math.ceil(len(words) / max_words)
    target = len(words) / n
    pieces = []
    for s in _SENT.split(text):
        w = s.split()
        while len(w) > max_words:  # one very long "sentence" (a table, say): cut by words
            pieces.append(w[:max_words])
            w = w[max_words:]
        if w:
            pieces.append(w)
    parts, cur = [], []
    for w in pieces:
        if cur and (len(cur) + len(w) > max_words or len(cur) >= target):
            parts.append(cur)
            cur = []
        cur = cur + w
    if cur:
        parts.append(cur)
    return [" ".join(p) for p in parts]


@dataclass
class Corpus:
    root: str
    commit: str
    units: list = field(default_factory=list)  # list[Item]
    pages: dict = field(default_factory=dict)  # source -> jsoup body text
    titles: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)  # (src_node, dst_node, type); node = ["u", unit_key] | ["p", source]
    supersede: dict = field(default_factory=dict)  # unit key -> unit key
    page_supersede: dict = field(default_factory=dict)  # source -> source
    element_text: dict = field(default_factory=dict)  # address -> scorer's element text (expected/stale only)


def unit_key(source: str, anchor: str) -> str:
    return f"{source}#{anchor}"


def commit_of(root: Path) -> str:
    git = root / ".git"
    try:
        if git.is_file():
            ptr = git.read_text().strip()
            git = (root / ptr[len("gitdir:"):].strip()).resolve()
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head
        ref = head[5:]
        common = git
        if (git / "commondir").exists():
            common = (git / (git / "commondir").read_text().strip()).resolve()
        if (common / ref).exists():
            return (common / ref).read_text().strip()
        for line in (common / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split(" ")[0]
    except OSError:
        pass
    return "unknown"


def build(root: Path, legacy: bool = False, part_words: int = PART_WORDS, path: bool = True, parts: bool = True) -> Corpus:
    """``legacy``: the earlier prototype's units. ``path=False`` / ``parts=False``: step 1 without
    the heading path or without splitting long units, to isolate each."""
    root = Path(root)
    c = Corpus(root=str(root), commit=commit_of(root))
    units: list[Item] = []
    keys = {}
    trees = {}
    for f in html_files(root):
        source = rel(root, f)
        tree = H.parse(f.read_text(encoding="utf-8"))
        trees[source] = tree
        body = H.find_tag(tree, "body")
        if body is None:
            continue
        c.pages[source] = H.jsoup_text(body)
        t = H.find_tag(tree, "title")
        title = _strip_join(t) if t else ""
        c.titles[source] = title
        st = H.find_tag(tree, "spec-status")
        page_status = st.get("value") if st is not None else None
        for e in body.iter():
            if e is body or not e.id:
                continue
            text = H.soup_text(e, skip=lambda k: bool(k.id))
            if len(text.split()) < MIN_WORDS:
                continue
            lc = lifecycle(source, e)
            if page_status == "superseded" and lc == "current":
                lc = "superseded"
            hd = e.find(lambda k: k.tag in ("h2", "h3", "h4"))
            heading = _strip_join(hd) if hd is not None else ""
            if legacy:
                hpath, chunks = "", [text]
            else:
                hpath = heading_path(title, e) if path else ""
                chunks = split_parts(text, part_words) if parts else [text]
            key = unit_key(source, e.id)
            if key in keys:  # a repeated id on one page: the first one is the element (getElementById)
                continue
            keys[key] = len(units)
            for i, ch in enumerate(chunks):
                units.append(Item(len(units), source, e.id, spec_of(source), lc, title, hpath, heading, ch,
                                  part=i + 1, parts=len(chunks)))
    c.units = units
    _links(c, trees, set(keys))
    return c


# --- links ------------------------------------------------------------------------------
def _raw_text(el: H.Element) -> str:
    """BeautifulSoup get_text(' ') without stripping: strings joined by one space."""
    out = []

    def walk(e):
        for k in e.children:
            if isinstance(k, H.Text):
                out.append(k.data)
            elif k.tag not in H.RAW:
                walk(k)

    walk(el)
    return " ".join(out)


def _specdir(source: str) -> str:
    return "/".join(source.split("/")[:2])


def _links(c: Corpus, trees: dict, keys: set):
    """Port of graph.py: resolved typed links, hrefs snapped to the nearest unit, supersession."""
    pages = set(c.pages)

    def resolve_id(source, ident, prefer=("same", "spec.html", "tasks.html", "design.html", "verify.html")):
        for p in prefer:
            page = source if p == "same" else _specdir(source) + "/" + p
            if unit_key(page, ident) in keys:
                return ["u", unit_key(page, ident)]
        return None

    def node_of(source, el):
        for p in [el] + list(el.ancestors()):
            if p.id and unit_key(source, p.id) in keys:
                return ["u", unit_key(source, p.id)]
        return ["p", source]

    lc = {}
    for u in c.units:
        lc[unit_key(u.source, u.anchor)] = u.lifecycle

    for source, tree in trees.items():
        body = H.find_tag(tree, "body")
        if body is None:
            continue
        page_superseded = any(e.tag == "spec-status" and e.get("value") == "superseded" for e in tree.iter())
        for a in body.iter():
            if a.tag != "a" or "href" not in a.attrs:
                continue
            h = a.get("href")
            if h.startswith(("http", "mailto")):
                continue
            path, _, frag = h.partition("#")
            tp = os.path.normpath(os.path.join(os.path.dirname(source), path)).replace("\\", "/") if path else source
            if tp not in pages:
                continue
            src = node_of(source, a)
            dst = ["u", unit_key(tp, frag)] if unit_key(tp, frag) in keys else ["p", tp]
            if src == dst:
                continue
            kind = "same-page" if tp == source else ("same-spec" if _specdir(tp) == _specdir(source) else "cross-spec")
            c.edges.append([src, dst, "href:" + kind])
            ctx = _raw_text(a.parent)[:200].lower() if a.parent is not None else ""
            at = _raw_text(a).lower()
            before = ctx.split(at)[0][-40:] if at else ""
            if "superseded" in before and "by" in before:
                if src[0] == "u" and dst[0] == "u" and lc[src[1]] != "current":
                    c.supersede.setdefault(src[1], dst[1])
                elif page_superseded and "/changes/" not in source:
                    c.page_supersede[source] = tp if dst[0] == "p" else dst[1].split("#")[0]
        for e in body.iter():
            for attr in ("validates", "cites", "target", "defer-to"):
                v = e.get(attr)
                if not v:
                    continue
                vals = [x for x in re.split(r"[\s,]+", v) if x]
                if attr == "target" and e.tag == "spec-delta":
                    copy_ = e.find(lambda k: bool(k.id) and unit_key(source, k.id) in keys)
                    src = ["u", unit_key(source, copy_.id)] if copy_ is not None else node_of(source, e)
                    for x in vals:
                        if "/changes/" in source:
                            dst = resolve_id(_specdir(source) + "/spec.html", x, prefer=("spec.html", "design.html", "tasks.html"))
                        else:
                            dst = resolve_id(source, x)
                        if dst and dst != src:
                            c.edges.append([src, dst, "typed:delta"])
                            if src[0] == "u" and lc[src[1]] != "current" and lc[dst[1]] == "current":
                                c.supersede.setdefault(src[1], dst[1])
                    continue
                src = node_of(source, e)
                for x in vals:
                    if attr == "defer-to":
                        if re.match(r"^\d{3}-", x) and f"specs/{x}/spec.html" in pages:
                            dst = ["p", f"specs/{x}/spec.html"]
                        else:
                            continue
                    else:
                        dst = resolve_id(source, x.lstrip("#"))
                    if dst and dst != src:
                        c.edges.append([src, dst, "typed:" + attr])
        # an element marked superseded in place, with a link after the status: that link is its successor
        for e in body.iter():
            if not (e.id and unit_key(source, e.id) in keys):
                continue
            k = unit_key(source, e.id)
            st = e.find(lambda x: x.tag == "spec-status" and x.get("value") == "superseded")
            if e.get("data-status") != "superseded" and st is None:
                continue
            if k in c.supersede or st is None:
                continue
            a = _find_next(tree, st, lambda x: x.tag == "a" and "href" in x.attrs)
            if a is None:
                continue
            path, _, frag = a.get("href").partition("#")
            tp = os.path.normpath(os.path.join(os.path.dirname(source), path)).replace("\\", "/") if path else source
            if unit_key(tp, frag) in keys and unit_key(tp, frag) != k:
                c.supersede[k] = unit_key(tp, frag)


def _find_next(tree: H.Element, start: H.Element, pred):
    """BeautifulSoup find_next: the first matching element after ``start`` in document order."""
    seen = False
    for e in tree.iter():
        if e is start:
            seen = True
            continue
        if seen and pred(e):
            return e
    return None


# --- cache --------------------------------------------------------------------------------
VARIANTS = {
    "ep4": {},
    "legacy": {"legacy": True},
    "ep4-noparts": {"parts": False},
    "ep4-nopath": {"path": False},
}


def load_or_build(root: Path, cache_dir: Path, variant: str = "ep4") -> Corpus:
    root = Path(root)
    commit = commit_of(root)
    name = f"corpus-{commit[:7]}-{FORMAT}-{variant}-p{PART_WORDS}.json"
    path = Path(cache_dir) / name
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        c = Corpus(**{k: v for k, v in d.items() if k != "units"})
        c.units = [Item(**u) for u in d["units"]]
        return c
    c = build(root, **VARIANTS[variant])
    path.parent.mkdir(parents=True, exist_ok=True)
    d = asdict(c)
    path.write_text(json.dumps(d), encoding="utf-8")
    return c
