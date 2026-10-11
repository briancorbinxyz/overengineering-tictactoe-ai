package org.xxdc.oss.example.tictactoe;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The words commentators use for squares and lines on a 3x3 board, and the squares they mean.
 *
 * <p>Squares are numbered as the game numbers them: 0 to 8, left to right, top to bottom. Lines
 * are matched before squares, and each match is blanked out before the next pattern runs, so
 * "the top-left to bottom-right diagonal" is one line, not two corners, and "the top-left corner"
 * is one square, not also "a corner".
 */
final class BoardVocabulary {

  /**
   * A phrase and what it can mean. A line has one or more readings ("a diagonal" has two); a
   * square phrase has one reading, which may cover several squares ("a corner" covers four).
   */
  record Named(String phrase, List<Set<Integer>> readings) {}

  private record Term(Pattern pattern, String name, List<Set<Integer>> readings) {}

  private static final String TL = "top[- ]left";
  private static final String TR = "top[- ]right";
  private static final String BL = "bottom[- ]left";
  private static final String BR = "bottom[- ]right";
  private static final String TO = "(?: corner)? (?:to|through|into) (?:the )?";

  private static final List<Term> LINES =
      List.of(
          line("(?:" + TL + TO + BR + "|" + BR + TO + TL + ")(?: diagonal)?"
                  + "|main diagonal|leading diagonal",
              "the top-left to bottom-right diagonal", Set.of(0, 4, 8)),
          line("(?:" + TR + TO + BL + "|" + BL + TO + TR + ")(?: diagonal)?"
                  + "|anti[- ]?diagonal",
              "the top-right to bottom-left diagonal", Set.of(2, 4, 6)),
          new Term(
              Pattern.compile("(?i)\\bdiagonal\\b"),
              "a diagonal",
              List.of(Set.of(0, 4, 8), Set.of(2, 4, 6))),
          line("top row", "the top row", Set.of(0, 1, 2)),
          line("(?:middle|centre|center) row", "the middle row", Set.of(3, 4, 5)),
          line("bottom row", "the bottom row", Set.of(6, 7, 8)),
          line("left(?:-hand)? column", "the left column", Set.of(0, 3, 6)),
          line("(?:middle|centre|center) column", "the middle column", Set.of(1, 4, 7)),
          line("right(?:-hand)? column", "the right column", Set.of(2, 5, 8)));

  private static final List<Term> SQUARES =
      List.of(
          square(TL + "(?: corner| square)?", "the top-left corner", Set.of(0)),
          square(TR + "(?: corner| square)?", "the top-right corner", Set.of(2)),
          square(BL + "(?: corner| square)?", "the bottom-left corner", Set.of(6)),
          square(BR + "(?: corner| square)?", "the bottom-right corner", Set.of(8)),
          square("(?:centre|center|middle) square|(?:the )?(?:centre|center)", "the centre",
              Set.of(4)),
          square("top(?:[- ]middle| edge)", "the top edge", Set.of(1)),
          square("bottom(?:[- ]middle| edge)", "the bottom edge", Set.of(7)),
          square("left(?:[- ]middle| edge)|middle[- ]left", "the left edge", Set.of(3)),
          square("right(?:[- ]middle| edge)|middle[- ]right", "the right edge", Set.of(5)),
          square("corner", "a corner", Set.of(0, 2, 6, 8)),
          square("edge|side", "an edge", Set.of(1, 3, 5, 7)));

  private static final Pattern ROW_COLUMN =
      Pattern.compile("(?i)\\brow (\\d),? column (\\d)\\b");

  /** The lines a text names, in order. */
  static List<Named> lines(String text) {
    return find(new StringBuilder(text == null ? "" : text), LINES);
  }

  /** The squares a text names, after the lines have been taken out. */
  static List<Named> squares(String text) {
    var working = new StringBuilder(text == null ? "" : text);
    find(working, LINES);
    var found = new ArrayList<Named>();
    Matcher rc = ROW_COLUMN.matcher(working);
    while (rc.find()) {
      int r = Integer.parseInt(rc.group(1));
      int c = Integer.parseInt(rc.group(2));
      if (r >= 1 && r <= 3 && c >= 1 && c <= 3) {
        found.add(new Named(rc.group(), List.of(Set.of((r - 1) * 3 + (c - 1)))));
      }
      blank(working, rc.start(), rc.end());
    }
    found.addAll(find(working, SQUARES));
    return found;
  }

  /** "row 1, column 2" for a square index, the way the move reports say it. */
  static String describe(int square) {
    return "row %d, column %d".formatted(square / 3 + 1, square % 3 + 1);
  }

  private static List<Named> find(StringBuilder working, List<Term> terms) {
    var found = new ArrayList<Named>();
    for (Term t : terms) {
      Matcher m = t.pattern().matcher(working);
      while (m.find()) {
        found.add(new Named(t.name(), t.readings()));
        blank(working, m.start(), m.end());
      }
    }
    return found;
  }

  private static void blank(StringBuilder working, int start, int end) {
    for (int i = start; i < end; i++) {
      working.setCharAt(i, ' ');
    }
  }

  private static Term line(String regex, String name, Set<Integer> squares) {
    return new Term(Pattern.compile("(?i)\\b(?:" + regex + ")\\b"), name, List.of(squares));
  }

  private static Term square(String regex, String name, Set<Integer> squares) {
    return new Term(Pattern.compile("(?i)\\b(?:" + regex + ")\\b"), name, List.of(squares));
  }

  private BoardVocabulary() {}
}
