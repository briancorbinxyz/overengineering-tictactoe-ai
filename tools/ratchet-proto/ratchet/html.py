"""A small HTML tree built with the standard library, and two ways of reading its text.

The spectastic pages are generated, well-formed HTML, so a tree builder that knows void
elements and the few implicit end tags HTML allows (<p>, <li>, <dt>/<dd>, table rows and
cells, <option>) rebuilds the same tree a browser, lxml or jsoup would. Two text readers:

- ``soup_text``: every text node joined by one space, whitespace collapsed. This is what
  BeautifulSoup's ``get_text(' ')`` gives, which the earlier element-unit prototype used.
- ``jsoup_text``: a port of jsoup 1.21's ``Element.text()``, which Spring AI's
  ``JsoupDocumentReader`` uses, so the naive chunks match the Episode 3 archive.

Both are checked against the real libraries in ``tests/`` and in the README.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
    "source", "track", "wbr", "keygen", "command", "basefont", "bgsound", "menuitem", "frame",
}
# Start tags that close an open <p> (HTML's "close a p element" list).
CLOSES_P = {
    "address", "article", "aside", "blockquote", "center", "details", "dialog", "dir", "div",
    "dl", "fieldset", "figcaption", "figure", "footer", "header", "hgroup", "main", "menu",
    "nav", "ol", "p", "search", "section", "summary", "ul", "h1", "h2", "h3", "h4", "h5", "h6",
    "pre", "listing", "form", "plaintext", "table", "hr", "xmp",
}
# Tag -> tags that an open one of the same kind is implicitly closed by.
IMPLIED = {
    "li": ({"li"}, {"ul", "ol", "menu"}),
    "dt": ({"dt", "dd"}, {"dl"}),
    "dd": ({"dt", "dd"}, {"dl"}),
    "tr": ({"tr"}, {"table", "tbody", "thead", "tfoot"}),
    "td": ({"td", "th"}, {"table", "tr"}),
    "th": ({"td", "th"}, {"table", "tr"}),
    "option": ({"option", "optgroup"}, {"select", "datalist"}),
    "thead": ({"tbody", "tfoot"}, {"table"}),
    "tbody": ({"tbody", "tfoot", "thead"}, {"table"}),
}
RAW = {"script", "style"}

# jsoup 1.21.2 TagSet: block tags; anything else (including custom elements) is inline.
JSOUP_BLOCK = {
    "html", "head", "body", "frameset", "script", "noscript", "style", "meta", "link", "title",
    "frame", "noframes", "section", "nav", "aside", "hgroup", "header", "footer", "p", "h1",
    "h2", "h3", "h4", "h5", "h6", "br", "button", "ul", "ol", "pre", "div", "blockquote", "hr",
    "address", "figure", "figcaption", "form", "fieldset", "ins", "del", "dl", "dt", "dd", "li",
    "table", "caption", "thead", "tfoot", "tbody", "colgroup", "col", "tr", "th", "td", "video",
    "audio", "canvas", "details", "menu", "plaintext", "template", "article", "main", "center",
    "dir", "applet", "marquee", "listing", "svg", "femerge", "femergenode", "math",
}
JSOUP_PRESERVE = {"pre", "plaintext", "title", "textarea", "script"}
JSOUP_DATA = {"iframe", "noembed", "noframes", "script", "style", "xmp"}
JSOUP_SVG_BLOCK = {"svg", "femerge", "femergenode"}


def _jblock(e: "Element") -> bool:
    if e.ns == "svg":
        return e.tag in JSOUP_SVG_BLOCK
    if e.ns == "math":
        return e.tag == "math"
    return e.tag in JSOUP_BLOCK


def _jdata(e: "Element") -> bool:
    return e.tag == "script" if e.ns != "html" else e.tag in JSOUP_DATA


class Text:
    __slots__ = ("data", "parent")

    def __init__(self, data: str, parent: "Element | None" = None):
        self.data = data
        self.parent = parent


class Element:
    __slots__ = ("tag", "attrs", "children", "parent", "ns")

    def __init__(self, tag: str, attrs: dict, parent: "Element | None" = None):
        self.tag = tag
        self.attrs = attrs
        self.children: list = []
        self.parent = parent
        pns = parent.ns if parent is not None else "html"
        self.ns = "svg" if tag == "svg" else "math" if tag == "math" else pns

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    @property
    def id(self):
        return self.attrs.get("id")

    def iter(self):
        """This element and every descendant element, in document order."""
        stack = [self]
        while stack:
            e = stack.pop()
            yield e
            stack.extend(c for c in reversed(e.children) if isinstance(c, Element))

    def find(self, pred):
        for e in self.iter():
            if e is not self and pred(e):
                return e
        return None

    def ancestors(self):
        p = self.parent
        while p is not None:
            yield p
            p = p.parent

    def next_sibling(self):
        if self.parent is None:
            return None
        sib = self.parent.children
        i = next(n for n, c in enumerate(sib) if c is self)
        return sib[i + 1] if i + 1 < len(sib) else None


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#root", {})
        self.stack = [self.root]

    @property
    def cur(self):
        return self.stack[-1]

    def _open(self, tag):
        return any(e.tag == tag for e in self.stack)

    def _close(self, tag):
        for n in range(len(self.stack) - 1, 0, -1):
            if self.stack[n].tag == tag:
                del self.stack[n:]
                return True
        return False

    def handle_starttag(self, tag, attrs):
        if tag in CLOSES_P and self._open("p"):
            # only if the <p> is in button scope: no table/custom boundary between; good enough here
            for n in range(len(self.stack) - 1, 0, -1):
                t = self.stack[n].tag
                if t == "p":
                    del self.stack[n:]
                    break
                if t in ("table", "td", "th", "button", "html") or "-" in t:
                    break
        if tag in IMPLIED:
            closers, scope = IMPLIED[tag]
            for n in range(len(self.stack) - 1, 0, -1):
                t = self.stack[n].tag
                if t in closers:
                    del self.stack[n:]
                    break
                if t in scope or t in CLOSES_P or "-" in t:
                    break
        el = Element(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(el)
        if tag not in VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.cur.tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        # HTML keeps the body open after </body> and </html>: later content still lands in it
        if tag in VOID or tag in ("body", "html"):
            return
        self._close(tag)

    def handle_data(self, data):
        c = self.cur.children
        if c and isinstance(c[-1], Text):
            c[-1].data += data
        else:
            c.append(Text(data, self.cur))


def parse(html: str) -> Element:
    b = _Builder()
    b.feed(html.replace("\r\n", "\n").replace("\r", "\n"))
    b.close()
    return b.root


def find_tag(root: Element, tag: str):
    return root.find(lambda e: e.tag == tag)


_WS = re.compile(r"\s+")


def collapse(s: str) -> str:
    return _WS.sub(" ", s).strip()


def soup_text(el: Element, skip=None) -> str:
    """Text nodes joined by a space and collapsed, skipping script/style and any element ``skip(e)`` is true for."""
    out: list[str] = []

    def walk(e):
        for c in e.children:
            if isinstance(c, Text):
                out.append(c.data)
            elif c.tag not in RAW and not (skip and skip(c)):
                walk(c)

    walk(el)
    return collapse(" ".join(out))


# --- jsoup Element.text() ------------------------------------------------------------
_JWS = {" ", "\t", "\n", "\f", "\r", " "}
_INVISIBLE = {"​", "­"}


def _preserve(el: Element | None) -> bool:
    i = 0
    while el is not None and i < 6:
        if el.ns == "html" and el.tag in JSOUP_PRESERVE:
            return True
        el = el.parent
        i += 1
    return False


def jsoup_text(el: Element) -> str:
    """Port of jsoup 1.21.2 Element.text(): normalised text with spaces around block elements."""
    acc: list[str] = []
    state = {"last_ws": False, "len": 0}

    def append(s):
        if s:
            acc.append(s)
            state["len"] += len(s)
            state["last_ws"] = s[-1] == " "

    def last_ws():
        return state["len"] > 0 and state["last_ws"]

    def norm_append(text, strip_leading):
        last_was_white = False
        reached = False
        buf = []
        for ch in text:
            if ch in _JWS:
                if (strip_leading and not reached) or last_was_white:
                    continue
                buf.append(" ")
                last_was_white = True
            elif ch not in _INVISIBLE:
                buf.append(ch)
                last_was_white = False
                reached = True
        append("".join(buf))

    def head(node):
        if isinstance(node, Text):
            if _preserve(node.parent):
                append(node.data)
            else:
                norm_append(node.data, last_ws())
        else:
            if state["len"] > 0 and (_jblock(node) or node.tag == "br") and not last_ws():
                append(" ")

    def tail(node, nxt):
        if isinstance(node, Element):
            if _jblock(node) and (
                isinstance(nxt, Text) or (isinstance(nxt, Element) and not _jblock(nxt))
            ) and not last_ws():
                append(" ")

    def walk(node, nxt):
        head(node)
        if isinstance(node, Element):
            # jsoup keeps script/style text as DataNodes, which text() does not read
            if not _jdata(node):
                ch = node.children
                for i, c in enumerate(ch):
                    walk(c, ch[i + 1] if i + 1 < len(ch) else None)
        tail(node, nxt)

    walk(el, None)
    return java_trim("".join(acc))


def java_trim(s: str) -> str:
    """Java's String.trim(): strips characters up to U+0020 only (not U+00A0)."""
    a, b = 0, len(s)
    while a < b and s[a] <= " ":
        a += 1
    while b > a and s[b - 1] <= " ":
        b -= 1
    return s[a:b]
