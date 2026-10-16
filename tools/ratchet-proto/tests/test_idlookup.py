"""The identifier-lookup parser and pin order."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ratchet import idlookup as I  # noqa: E402
from ratchet.corpus import Item  # noqa: E402

ANCHORS = {"FR-001", "FR-008", "FR-012", "NFR-001", "SC-002", "D-001", "D-006", "T-100", "REQ-TOOL-001", "US5", "R-1"}


class Parse(unittest.TestCase):
    def p(self, q):
        return I.parse(q, ANCHORS)

    def test_id_and_spec(self):
        self.assertEqual((["FR-012"], ["040"]), self.p("FR-012 in spec 040"))

    def test_spec_is_case_insensitive_and_possessive(self):
        self.assertEqual([], self.p("Spec 058's corpus-license rule reads a field 058 says it does not own")[0])
        self.assertEqual(["058"], self.p("Spec 058's corpus-license rule")[1])
        self.assertEqual(["055"], self.p("Spec 055 (corpus in review) leaves")[1])
        self.assertEqual(["076"], self.p("SPEC 076 emits a change notification")[1])

    def test_slug_names_a_spec(self):
        self.assertEqual((["FR-001"], ["001"]), self.p("What did 001-cli say in FR-001?"))

    def test_a_bare_number_is_not_a_spec(self):
        # the earlier prototype's bare-number pattern once read "FR-008 (" as spec 008
        self.assertEqual((["FR-008"], ["109"]), self.p("Which criteria in spec 109 validate FR-008 (the sticky header)?"))
        self.assertEqual([], self.p("init must finish in under 2 seconds on 40-file trees")[1])

    def test_ids_must_exist_and_be_capitalised(self):
        self.assertEqual([], self.p("is d-001 the same as FR-999?")[0])
        self.assertEqual(["REQ-TOOL-001", "US5", "R-1"], self.p("REQ-TOOL-001, US5 and R-1")[0])

    def test_several_ids_keep_question_order_without_duplicates(self):
        self.assertEqual(["SC-002", "FR-001"], self.p("Does SC-002 validate FR-001 or SC-002 only?")[0])


def unit(n, source, anchor, lifecycle="current"):
    return Item(n, source, anchor, source.split("/")[1], lifecycle, "", "", "", "text")


class Lookup(unittest.TestCase):
    def setUp(self):
        self.units = [
            unit(0, "specs/040-run-budget/spec.html", "FR-012"),
            unit(1, "specs/041-other/spec.html", "FR-012"),
            unit(2, "specs/040-run-budget/changes/withdrawn/x/proposal.html", "FR-012", "withdrawn"),
            unit(3, "specs/040-run-budget/changes/archive/y/proposal.html", "FR-012", "history"),
            unit(4, "specs/090-command-surface/spec.html", "REQ-TOOL-001"),
            unit(5, "specs/090-command-surface/spec.html", "REQ-TOOL-001"),  # a second part of the same unit
        ]
        self.ix = I.IdIndex(self.units)

    def test_id_in_spec_pins_that_spec_only_current_first(self):
        self.assertEqual(
            ["specs/040-run-budget/spec.html#FR-012",
             "specs/040-run-budget/changes/archive/y/proposal.html#FR-012",
             "specs/040-run-budget/changes/withdrawn/x/proposal.html#FR-012"],
            self.ix.lookup("What does FR-012 in spec 040 require?"))

    def test_ambiguous_id_without_spec_pins_nothing(self):
        self.assertEqual([], self.ix.lookup("What does FR-012 require?"))

    def test_unique_id_without_spec_pins(self):
        self.assertEqual(["specs/090-command-surface/spec.html#REQ-TOOL-001"], self.ix.lookup("What is REQ-TOOL-001?"))
        self.assertEqual([4, 5], self.ix.items("specs/090-command-surface/spec.html#REQ-TOOL-001"))

    def test_spec_without_id_pins_nothing(self):
        self.assertEqual([], self.ix.lookup("What does spec 040 say about budgets?"))

    def test_prior_linker_is_case_sensitive_and_pins_every_match_without_a_spec(self):
        # "Spec 040" is missed by the earlier prototype's lower-case pattern, so every FR-012 is pinned
        self.assertEqual(4, len(self.ix.lookup("What does FR-012 of Spec 040 require?", linker="prior")))
        self.assertEqual(3, len(self.ix.lookup("What does FR-012 of spec 040 require?", linker="prior")))


if __name__ == "__main__":
    unittest.main()
