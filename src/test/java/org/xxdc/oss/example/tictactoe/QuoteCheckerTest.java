package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class QuoteCheckerTest {

  private static final String OFFERED = "Played perfectly, it is a draw.";
  private final QuoteChecker quotes =
      new QuoteChecker(new ColourLines(List.of(OFFERED, "Forks win games.")));

  private static Commentary saying(String... sources) {
    return new Commentary("", List.of(new Claim("Colour.", List.of(sources))));
  }

  @Test
  void onlyAnExactQuoteOfTheOfferedLineIsVerified() {
    assertTrue(quotes.quotesExactly(saying(OFFERED), OFFERED));
    assertTrue(quotes.quotesExactly(saying("  “" + OFFERED + "” "), OFFERED));
    assertFalse(quotes.quotesExactly(saying("Played perfectly, it's a draw."), OFFERED));
    assertFalse(quotes.quotesExactly(saying(OFFERED, "Forks win games."), OFFERED));
    assertFalse(quotes.quotesExactly(saying(), OFFERED));
    assertFalse(quotes.quotesExactly(saying("Not in the file."), "Not in the file."));
  }

  @Test
  void aParaphraseIsContradictedAndAClaimWithNoQuoteIsUnchecked() {
    var paraphrase = quotes.check(new Claim("x", List.of("Perfect play draws.")), OFFERED);
    assertEquals(FactChecker.Status.CONTRADICTED, paraphrase.status());
    var bare = quotes.check(new Claim("x", List.of()), OFFERED);
    assertEquals(FactChecker.Status.UNCHECKED, bare.status());
  }
}
