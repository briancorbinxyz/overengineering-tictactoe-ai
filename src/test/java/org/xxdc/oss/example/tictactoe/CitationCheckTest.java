package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class CitationCheckTest {

  private static final List<String> PLAYERS = List.of("X", "O");

  @Test
  void aCorrectBackReferenceIsClean() {
    var c =
        new Commentary(null, "O blocks, much as X took the centre on move 1.", List.of("move 1"));
    var r = CitationCheck.check(c, 4, 1, PLAYERS);
    assertTrue(r.clean());
    assertEquals(1, r.mentioned().size());
  }

  @Test
  void aFutureMoveIsInvalid() {
    var c = new Commentary(null, "As on move 7, nothing happens.", List.of("move 7"));
    var r = CitationCheck.check(c, 4, 1, PLAYERS);
    assertEquals(List.of(7), r.invalid());
    assertFalse(r.clean());
  }

  @Test
  void aMoveOutsideTheWindowIsOutOfSight() {
    var c = new Commentary(null, "X opened in the corner on move 1.", List.of("move 1"));
    var r = CitationCheck.check(c, 8, 5, PLAYERS);
    assertEquals(List.of(1), r.outOfSight());
  }

  @Test
  void theWrongPlayerForAMoveIsCaught() {
    // Move 2 is O's in a two-player game that X starts.
    var c = new Commentary(null, "X took the corner on move 2.", List.of("move 2"));
    var r = CitationCheck.check(c, 5, 1, PLAYERS);
    assertEquals(1, r.playerChecks());
    assertEquals(0, r.playerCorrect());
    assertFalse(r.clean());
  }

  @Test
  void aMentionWithoutACitationIsReported() {
    var c = new Commentary(null, "Unlike move 3, this one matters.", List.of());
    var r = CitationCheck.check(c, 6, 1, PLAYERS);
    assertEquals(List.of(3), r.uncited());
  }
}
