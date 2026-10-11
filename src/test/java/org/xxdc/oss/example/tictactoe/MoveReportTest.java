package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.xxdc.oss.example.GameBoard;
import org.xxdc.oss.example.GameState;

class MoveReportTest {

  private static GameState empty() {
    return new GameState(GameBoard.withDimension(3), List.of("X", "O"), 0);
  }

  @Test
  void takingTheCentreIsATurningPointAndGetsNoColour() {
    var before = empty();
    var after = before.afterPlayerMoves(4);
    var report = MoveReport.of(before, after, 1, Optional.of("Some trivia."));
    assertFalse(report.quiet());
    assertTrue(report.colour().isEmpty());
    assertTrue(report.toPrompt().contains("Turning point: X takes the centre square."));
    assertEquals(2, report.row());
    assertEquals(2, report.column());
  }

  @Test
  void aCornerOpeningIsQuietAndOffersColour() {
    var before = empty();
    var after = before.afterPlayerMoves(0);
    var report = MoveReport.of(before, after, 1, Optional.of("Some trivia."));
    assertTrue(report.quiet());
    assertTrue(report.toPrompt().contains("Colour you may use: Some trivia."));
    assertTrue(report.toPrompt().startsWith("Move 1: X played row 1, column 1."));
  }

  @Test
  void aBareMoveSaysSoRatherThanLeavingLinesOut() {
    // A model does not notice an absent line, so "nothing happened" is stated outright.
    var before = empty();
    var report = MoveReport.of(before, before.afterPlayerMoves(0), 1, Optional.empty());
    assertTrue(report.toPrompt().contains("Turning point: none, a quiet move."));
    assertTrue(report.toPrompt().contains("Result: none, play continues."));
  }

  @Test
  void theBoardIsRenderedOneRowPerLine() {
    var state = empty().afterPlayerMoves(0).afterPlayerMoves(4);
    assertEquals("X . .\n. O .\n. . .\n", MoveReport.render(state));
  }
}
