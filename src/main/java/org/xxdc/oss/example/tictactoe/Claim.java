package org.xxdc.oss.example.tictactoe;

import java.util.List;

/**
 * One statement a commentator makes, with the sources it rests on.
 *
 * <p>A claim is not a fact. It becomes one when a {@link FactChecker} finds it supported by the
 * evidence. Keeping each statement next to its own sources is what lets a checker tell which
 * source backs which statement; a single list of citations for a whole reply cannot.
 *
 * @param text one short statement, literal and checkable
 * @param sources what the statement rests on: an earlier move as "move N" in this episode, a
 *     quotation copied word for word, and from Episode 3 an address in a document
 */
public record Claim(String text, List<String> sources) {

  public Claim {
    text = text == null ? "" : text.strip();
    sources = sources == null ? List.of() : List.copyOf(sources);
  }
}
