package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.springframework.core.io.ClassPathResource;
import org.junit.jupiter.api.Test;

class ColourLinesTest {

  @Test
  void readsOnlyBulletLinesAndRunsOutRatherThanRepeating() {
    var colour = ColourLines.from(new ClassPathResource("colour/quiet-moves.md"));
    assertTrue(colour.size() >= 9, "a 3x3 game has at most nine quiet moves");
    assertTrue(colour.forQuietMove(0).orElseThrow().startsWith("Played perfectly"));
    assertEquals(java.util.Optional.empty(), colour.forQuietMove(colour.size()));
  }
}
