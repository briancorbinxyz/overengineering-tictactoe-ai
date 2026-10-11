package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.xxdc.oss.example.GameBoard;
import org.xxdc.oss.example.GameState;
import org.xxdc.oss.example.tictactoe.FactChecker.Status;

class GameFactCheckerTest {

  private final GameFactChecker checker = new GameFactChecker();

  /** The board after each move, starting from empty: index m is the board after move m. */
  private static List<GameState> play(int... squares) {
    var history = new ArrayList<GameState>();
    var state = new GameState(GameBoard.withDimension(3), List.of("X", "O"), 0);
    history.add(state);
    for (int square : squares) {
      state = state.afterPlayerMoves(square);
      history.add(state);
    }
    return history;
  }

  // A game that ends in a draw. After move 8 the board is
  //   X X O
  //   O O X
  //   X . O
  // and the top-left to bottom-right diagonal is X, O, O: nobody has won.
  private static final List<GameState> DRAWN = play(0, 4, 1, 2, 6, 3, 5, 8, 7);

  private static GameFactChecker.Evidence at(int move, int earliestVisible) {
    return new GameFactChecker.Evidence(DRAWN.subList(0, move + 1), move, earliestVisible);
  }

  private FactChecker.Verdict check(String text, List<String> sources, int move) {
    return checker.check(new Claim(text, sources), at(move, 1));
  }

  @Test
  void aCorrectBackReferenceIsSupported() {
    var v = check("O blocks, much as X opened in the corner on move 1.", List.of("move 1"), 4);
    assertEquals(Status.SUPPORTED, v.status(), v.reason());
  }

  @Test
  void aMoveNotYetPlayedIsContradicted() {
    var v = check("As on move 7, nothing happens.", List.of("move 7"), 4);
    assertEquals(Status.CONTRADICTED, v.status());
  }

  @Test
  void aMoveOutsideTheWindowIsUnsupported() {
    var v = checker.check(new Claim("X opened on move 1.", List.of("move 1")), at(8, 5));
    assertEquals(Status.UNSUPPORTED, v.status());
    assertTrue(v.reason().contains("memory window"));
  }

  @Test
  void theWrongPlayerForAMoveIsContradicted() {
    // Move 2 is O's in a game that X starts.
    var v = check("X took the corner on move 2.", List.of("move 2"), 5);
    assertEquals(Status.CONTRADICTED, v.status());
    assertEquals("move 2 was O's, not X's", v.reason());
  }

  @Test
  void aMentionWithoutACitationIsUnsupported() {
    var v = check("Unlike move 3, this one matters.", List.of(), 6);
    assertEquals(Status.UNSUPPORTED, v.status());
  }

  @Test
  void anInventedWinIsContradicted() {
    // What qwen3:8b said at move 8 of a game that went on to a draw.
    var v =
        check(
            "O has completed a diagonal from top-left to bottom-right, securing a win.",
            List.of(),
            8);
    assertEquals(Status.CONTRADICTED, v.status());
    assertEquals("says O has won, but after move 8 nobody has", v.reason());
  }

  @Test
  void anInventedWinRepeatedInThePostGameSummaryIsContradicted() {
    var v = check("Turning point move 8: O secures a diagonal win.", List.of("move 8"), 9);
    assertEquals(Status.CONTRADICTED, v.status());
  }

  @Test
  void aRealWinIsSupported() {
    // X takes the top row on move 5.
    var won = play(0, 4, 1, 8, 2);
    var v =
        checker.check(
            new Claim("X wins with the top row.", List.of()),
            new GameFactChecker.Evidence(won, 5, 1));
    assertEquals(Status.SUPPORTED, v.status(), v.reason());
  }

  @Test
  void blockingAWinIsNotAWinClaim() {
    assertFalse(GameFactChecker.isWinClaim("O blocks X from winning on the diagonal."));
    assertFalse(GameFactChecker.isWinClaim("X threatens to win next move."));
    assertTrue(GameFactChecker.isWinClaim("O wins."));
  }

  @Test
  void aClaimWithNothingCheckableIsUnchecked() {
    var v = check("A tidy move.", List.of(), 3);
    assertEquals(Status.UNCHECKED, v.status());
  }

  @Test
  void anAsideThatMakesAClaimIsFlagged() {
    var c = new Commentary("O wins this one, mark my words.", List.of());
    var verdicts = checker.checkAll(c, at(4, 1));
    assertEquals(1, verdicts.size());
    assertEquals(Status.UNSUPPORTED, verdicts.getFirst().status());
  }
}
