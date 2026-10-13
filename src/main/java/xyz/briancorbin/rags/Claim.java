package xyz.briancorbin.rags;

import java.util.List;

/**
 * One statement a commentator makes, with the sources it rests on.
 *
 * <p>A claim is not a fact. It becomes one when a {@link FactChecker} finds it supported by the
 * evidence. Keeping each statement next to its own sources is what lets a checker tell which
 * source backs which statement; a single list of citations for a whole reply cannot.
 *
 * @param text one short statement, literal and checkable
 * @param sources what the statement rests on: in Episode 2 an earlier move ("move 3") or a quoted
 *     line; from Episode 3 a passage copied word for word from the archive, or the label of one
 *     ("Q2") that the program has already traced to its address
 */
public record Claim(String text, List<String> sources) {

  public Claim {
    text = text == null ? "" : text.strip();
    sources = sources == null ? List.of() : List.copyOf(sources);
  }
}
