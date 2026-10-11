package org.xxdc.oss.example.tictactoe;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import org.springframework.core.io.Resource;

/**
 * Lines of colour for quiet moves, read from a hand-written file.
 *
 * <p>The program picks the line, in order, and never repeats one within a game. Nothing is
 * searched and nothing is ranked. That is the point: Episode 3 replaces this with retrieval, and
 * this is the baseline it has to beat for relevance.
 */
public final class ColourLines {

  private final List<String> lines;

  public ColourLines(List<String> lines) {
    this.lines = List.copyOf(lines);
  }

  /** Reads lines starting with "- " and ignores everything else. */
  public static ColourLines from(Resource resource) {
    try {
      var text = resource.getContentAsString(StandardCharsets.UTF_8);
      return new ColourLines(
          text.lines().filter(l -> l.startsWith("- ")).map(l -> l.substring(2).strip()).toList());
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  /**
   * The line for the n-th quiet move of a game, counting from 0, or empty once the file has run
   * out. Running out is deliberate: a 3x3 game has at most nine moves.
   */
  public Optional<String> forQuietMove(int quietMoveIndex) {
    return quietMoveIndex >= 0 && quietMoveIndex < lines.size()
        ? Optional.of(lines.get(quietMoveIndex))
        : Optional.empty();
  }

  /**
   * True when the citations are exactly the offered line, which is in this file. Surrounding
   * whitespace and one pair of surrounding quotation marks are ignored; nothing else is. A
   * paraphrase, a fact from elsewhere, or a line that is not in the file all fail.
   */
  public boolean quotesExactly(List<String> citations, String offered) {
    if (citations.isEmpty() || !lines.contains(offered)) {
      return false;
    }
    return citations.stream().map(ColourLines::unquote).allMatch(offered::equals);
  }

  static String unquote(String s) {
    var t = s.strip();
    if (t.length() >= 2
        && ((t.startsWith("\"") && t.endsWith("\""))
            || (t.startsWith("“") && t.endsWith("”")))) {
      t = t.substring(1, t.length() - 1).strip();
    }
    return t;
  }

  public int size() {
    return lines.size();
  }
}
