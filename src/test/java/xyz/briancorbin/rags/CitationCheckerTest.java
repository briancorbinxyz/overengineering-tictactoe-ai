package xyz.briancorbin.rags;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import xyz.briancorbin.rags.FactChecker.Status;

class CitationCheckerTest {

  private final CitationChecker checker = new CitationChecker();
  private final List<Quote> given =
      List.of(
          new Quote("Q1", "Retrieval MUST NOT be built", new Address("specs/059/spec.html", 2, 3, "T"), 1),
          new Quote("Q2", "The corpus MUST NOT require a vector index", new Address("specs/051/spec.html", 1, 2, "T"), 2));

  @Test
  void citingAGivenLabelIsSupported() {
    var v = checker.check(new Claim("No index below the line.", List.of("Q1")), given);
    assertEquals(Status.SUPPORTED, v.status());
    assertEquals("cites Q1 (specs/059/spec.html, chunk 2 of 3)", v.reason());
  }

  @Test
  void bracketsAndCaseAreForgivenButNothingElse() {
    assertEquals(Status.SUPPORTED, checker.check(new Claim("x", List.of("[q2]")), given).status());
    assertEquals(Status.CONTRADICTED, checker.check(new Claim("x", List.of("Quote 2")), given).status());
  }

  @Test
  void citingALabelItWasNotGivenIsContradicted() {
    var v = checker.check(new Claim("x", List.of("Q1", "Q7")), given);
    assertEquals(Status.CONTRADICTED, v.status());
    assertEquals("cites Q7, which it was not given", v.reason());
  }

  @Test
  void anUncitedClaimIsUnsupportedUnlessItAbstains() {
    assertEquals(Status.UNSUPPORTED, checker.check(new Claim("spectastic uses Postgres.", List.of()), given).status());
    assertEquals(Status.UNCHECKED, checker.check(new Claim("Not in the archive.", List.of()), given).status());
  }

  @Test
  void abstainingMeansSayingSoAndCitingNothing() {
    assertTrue(checker.abstained(new Commentary("", List.of(new Claim("Not in the archive.", List.of()))), List.of()));
    var both =
        new Commentary(
            "",
            List.of(new Claim("Not in the archive.", List.of()), new Claim("Though Q1 says this.", List.of("Q1"))));
    assertFalse(checker.abstained(both, given));
  }

  @Test
  void citedQuotationsComeBackInOrderWithoutRepeats() {
    var reply =
        new Commentary("", List.of(new Claim("a", List.of("Q2")), new Claim("b", List.of("Q2", "Q1", "Q9"))));
    assertEquals(List.of("Q2", "Q1"), checker.cited(reply, given).stream().map(Quote::label).toList());
  }
}
