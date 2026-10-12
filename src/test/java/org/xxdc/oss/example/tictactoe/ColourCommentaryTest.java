package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class ColourCommentaryTest {

  private static final String LINE = "Played perfectly, it is a draw.";

  @Test
  void theQuotationBecomesTheColourClaimsOnlySourceAndTheReactionHasNone() {
    var c = new ColourCommentary("", "As every scholar knows.", LINE, "Alpha seems thrilled.");
    var claims = c.asCommentary().claims();
    assertEquals(2, claims.size());
    assertEquals(List.of(LINE), claims.get(0).sources());
    assertEquals(List.of(), claims.get(1).sources());
    var quotes = new QuoteChecker(new ColourLines(List.of(LINE)));
    assertTrue(quotes.quotesExactly(c.asCommentary(), LINE));
    assertEquals(0, quotes.straySources(c.asCommentary(), LINE));
  }

  @Test
  void anEmptyReactionAddsNoClaim() {
    var c = new ColourCommentary("", "As every scholar knows.", LINE, "");
    assertEquals(1, c.asCommentary().claims().size());
  }
}
