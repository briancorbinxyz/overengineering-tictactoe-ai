package org.xxdc.oss.example.tictactoe;

import java.util.List;
import java.util.stream.Collectors;

/**
 * What a commentator says, as structured output.
 *
 * <p>The shape carries through the rest of the series. {@code claims} is everything checkable,
 * each statement with its own sources. {@code aside} is the joke, and it is deliberately
 * unchecked, which is why it may not contain anything a checker could check.
 *
 * @param aside one short joke, or empty; no move numbers, results or other facts
 * @param claims one to three statements, each with the sources it rests on
 */
public record Commentary(String aside, List<Claim> claims) {

  public Commentary {
    aside = aside == null ? "" : aside.strip();
    claims = claims == null ? List.of() : List.copyOf(claims);
  }

  public boolean hasAside() {
    return !aside.isEmpty();
  }

  /** The claims read as one piece of commentary, in order. */
  public String answer() {
    return claims.stream()
        .map(Claim::text)
        .filter(t -> !t.isEmpty())
        .collect(Collectors.joining(" "));
  }

  /** A plain, factual line used when the model cannot be reached. */
  static Commentary factual(String line) {
    return new Commentary("", List.of(new Claim(line, List.of())));
  }
}
