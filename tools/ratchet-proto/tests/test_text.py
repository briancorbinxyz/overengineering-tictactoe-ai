"""The standard-library parser against outputs taken from jsoup 1.21.2 and jtokkit (Spring AI's
reader and splitter); the full-corpus comparison is described in the README."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ratchet import corpus as C  # noqa: E402
from ratchet import html as H  # noqa: E402
from ratchet import splitter, tok  # noqa: E402

JSOUP = [  # (html, jsoup's body().text())
    ("<body><div>One</div>Two<p>Three <b>four</b></p><spec-rule>MUST</spec-rule><span>x</span></body>",
     "One Two Three four MUSTx"),
    ("<body><pre>a\n  b</pre><p>c  d</p></body>", "a\n  b c d"),
    ("<body><svg><style>.box{fill:red}</style><text>label</text></svg><script>var x=1</script><style>p{}</style>end"
     "</body></html><p>after</p>", ".box{fill:red}label end after"),
    ("<body><table><tr id=r1><td>a<td>b<tr id=r2><td>c</table><ul><li>one<li>two</ul></body>", "a b c one two"),
    ("<body><dl><dt>Status</dt> <dd><spec-status value=accepted>Accepted</spec-status></dd></dl><time>11 Aug</time>"
     "<span>Applied</span></body>", "Status Accepted 11 AugApplied"),
]


class JsoupText(unittest.TestCase):
    def test_matches_jsoup(self):
        for src, want in JSOUP:
            self.assertEqual(want, H.jsoup_text(H.find_tag(H.parse(src), "body")), src)

    def test_implied_end_tags_keep_rows_separate(self):
        t = H.parse("<table><tr id=r1><td>a<td>b<tr id=r2><td>c</table>")
        rows = [e for e in t.iter() if e.tag == "tr"]
        self.assertEqual(["r1", "r2"], [r.id for r in rows])
        self.assertEqual("a b", H.soup_text(rows[0]))


class Units(unittest.TestCase):
    def test_fixture_units(self):
        root = Path(__file__).resolve().parents[3] / "src/test/resources/fixtures"
        c = C.build(root)
        by = {u.anchor: u for u in c.units}
        self.assertEqual({"requirements", "FR-001", "FR-002"}, set(by))
        self.assertEqual("3 · Requirements", by["requirements"].text)  # children's text is their own
        self.assertTrue(by["FR-001"].text.startswith("The index MUST NOT"))
        self.assertEqual("Demo · Specification › 3 · Requirements", by["FR-001"].path)
        self.assertEqual("current", by["FR-001"].lifecycle)

    def test_long_units_split_into_parts_at_sentence_ends(self):
        text = " ".join(f"Sentence {i} has exactly six words." for i in range(100))  # 600 words
        parts = C.split_parts(text, 250)
        self.assertEqual(3, len(parts))
        self.assertTrue(all(len(p.split()) <= 250 for p in parts))
        self.assertTrue(all(p.endswith(".") for p in parts))
        self.assertEqual(text.split(), " ".join(parts).split())

    def test_lifecycle(self):
        el = H.parse("<section data-status=superseded><p id=x>a b c</p></section>").find(lambda e: e.id == "x")
        self.assertEqual("superseded", C.lifecycle("specs/001/spec.html", el))
        self.assertEqual("withdrawn", C.lifecycle("specs/001/changes/withdrawn/a/proposal.html", el))
        plain = H.parse("<p id=y>a b c</p>").find(lambda e: e.id == "y")
        self.assertEqual("history", C.lifecycle("specs/001/changes/archive/a/proposal.html", plain))


@unittest.skipIf(tok.load(os.environ.get("CL100K_FILE")) is None, "tiktoken / cl100k_base not available (offline: set CL100K_FILE)")
class Splitter(unittest.TestCase):
    def test_matches_spring_ai(self):
        # Reference from TokenTextSplitter's algorithm run in Java with jtokkit: 7 chunks of 793 x6 and 442 tokens.
        text = "".join(f"Sentence number {i} says the archive keeps FR-0{i % 10} whole. " for i in range(400))
        enc = tok.load(os.environ.get("CL100K_FILE"))
        chunks = splitter.split(text, enc)
        self.assertEqual([3344, 3376, 3415, 3415, 3415, 3415, 1903], [len(c) for c in chunks])
        self.assertEqual([793] * 6 + [442], [len(enc.encode_ordinary(c)) for c in chunks])


if __name__ == "__main__":
    unittest.main()
