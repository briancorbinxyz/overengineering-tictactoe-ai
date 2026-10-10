package org.xxdc.oss.example.tictactoe;

import java.util.List;

/**
 * What Alpha says about one move, as structured output.
 *
 * <p>The same three fields are used for the rest of the series: the joke goes in {@code aside},
 * the checkable part goes in {@code answer}, and {@code citations} says where the answer came
 * from. In this episode a citation is an earlier move ("move 3"); from Episode 3 it is an
 * address in the spectastic corpus.
 *
 * @param aside one short joke, or empty
 * @param answer one or two sentences of commentary, literal and checkable
 * @param citations every earlier move mentioned in the answer, as "move N"
 */
public record Commentary(String aside, String answer, List<String> citations) {

  public Commentary {
    aside = aside == null ? "" : aside.strip();
    answer = answer == null ? "" : answer.strip();
    citations = citations == null ? List.of() : List.copyOf(citations);
  }

  public boolean hasAside() {
    return !aside.isEmpty();
  }

  /** A plain, factual line used when the model cannot be reached. */
  static Commentary factual(String answer) {
    return new Commentary("", answer, List.of());
  }
}
