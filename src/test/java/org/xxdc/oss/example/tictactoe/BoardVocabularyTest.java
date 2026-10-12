package org.xxdc.oss.example.tictactoe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class BoardVocabularyTest {

  /** The one square a phrase names, or a failure if it names none or several. */
  private static Set<Integer> square(String text) {
    var found = BoardVocabulary.squares(text);
    assertEquals(1, found.size(), "squares in \"" + text + "\": " + found);
    return found.getFirst().readings().getFirst();
  }

  private static Set<Integer> line(String text) {
    var found = BoardVocabulary.lines(text);
    assertEquals(1, found.size(), "lines in \"" + text + "\": " + found);
    return found.getFirst().readings().getFirst();
  }

  @Test
  void bottomCentreMiddleAndEdgeAreAllSquareSeven() {
    for (String s :
        List.of(
            "the bottom-centre square",
            "the bottom centre",
            "the bottom-center",
            "the bottom middle",
            "the bottom edge",
            "the centre-bottom")) {
      assertEquals(Set.of(7), square(s), s);
    }
  }

  @Test
  void theOtherThreeEdgesWorkTheSameWay() {
    assertEquals(Set.of(1), square("the top-centre"));
    assertEquals(Set.of(1), square("the top middle"));
    assertEquals(Set.of(3), square("the left-centre square"));
    assertEquals(Set.of(3), square("the middle-left"));
    assertEquals(Set.of(3), square("the centre-left"));
    assertEquals(Set.of(5), square("the right centre"));
    assertEquals(Set.of(5), square("the middle-right"));
  }

  @Test
  void theBareCentreIsStillSquareFour() {
    assertEquals(Set.of(4), square("X takes the centre"));
    assertEquals(Set.of(4), square("X takes the center"));
    assertEquals(Set.of(4), square("the centre square"));
    assertEquals(Set.of(4), square("the middle square"));
  }

  @Test
  void cornersAndRowColumnAreUnaffected() {
    assertEquals(Set.of(0), square("the top-left corner"));
    assertEquals(Set.of(0, 2, 6, 8), square("a corner"));
    assertEquals(Set.of(2), square("row 1, column 3"));
  }

  @Test
  void middleRowAndMiddleColumnAreLinesNotSquares() {
    assertEquals(Set.of(3, 4, 5), line("the middle row"));
    assertEquals(Set.of(1, 4, 7), line("the centre column"));
    assertTrue(BoardVocabulary.squares("the middle row").isEmpty());
    assertTrue(BoardVocabulary.squares("the centre column").isEmpty());
  }

  @Test
  void cornersJoinedNameTheLineTheyShare() {
    assertEquals(Set.of(2, 5, 8), line("from top-right to bottom-right"));
    assertEquals(Set.of(0, 1, 2), line("from the top-left to the top-right corner"));
    assertEquals(Set.of(0, 4, 8), line("from top-left to bottom-right"));
    assertEquals(Set.of(2, 4, 6), line("the top-right to bottom-left diagonal"));
  }

  @Test
  void aLineThatCannotExistIsReported() {
    assertEquals(
        List.of("calls top-right to bottom-right a diagonal, but those corners are the right column"),
        BoardVocabulary.impossibleLines("O has completed a diagonal from top-right to bottom-right"));
    assertEquals(
        List.of("a diagonal cannot run along the bottom row"),
        BoardVocabulary.impossibleLines("a diagonal line across the bottom row"));
    assertTrue(BoardVocabulary.impossibleLines("a diagonal from top-left to bottom-right").isEmpty());
    assertTrue(BoardVocabulary.impossibleLines("from top-right to bottom-right").isEmpty());
  }
}
