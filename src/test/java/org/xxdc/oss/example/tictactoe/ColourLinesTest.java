package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.springframework.core.io.ClassPathResource;
import java.util.List;
import org.junit.jupiter.api.Test;

class ColourLinesTest {

  @Test
  void readsOnlyBulletLinesAndRunsOutRatherThanRepeating() {
    var colour = ColourLines.from(new ClassPathResource("colour/quiet-moves.md"));
    assertTrue(colour.size() >= 9, "a 3x3 game has at most nine quiet moves");
    assertTrue(colour.forQuietMove(0).orElseThrow().startsWith("Played perfectly"));
    assertEquals(java.util.Optional.empty(), colour.forQuietMove(colour.size()));
  }

  @Test
  void onlyAnExactQuoteOfTheOfferedLineIsVerified() {
    var colour = new ColourLines(List.of("Played perfectly, it is a draw.", "Forks win games."));
    var offered = "Played perfectly, it is a draw.";
    assertTrue(colour.quotesExactly(List.of(offered), offered));
    assertTrue(colour.quotesExactly(List.of("  \u201c" + offered + "\u201d "), offered));
    assertFalse(colour.quotesExactly(List.of("Played perfectly, it's a draw."), offered));
    assertFalse(colour.quotesExactly(List.of(offered, "Forks win games."), offered));
    assertFalse(colour.quotesExactly(List.of(), offered));
    assertFalse(colour.quotesExactly(List.of("Not in the file."), "Not in the file."));
  }
}
