package org.xxdc.oss.example.tictactoe;

import java.util.ArrayList;
import java.util.List;

/**
 * What Beta says on a quiet move, as structured output.
 *
 * <p>Beta's contract differs from Alpha's, so it gets its own shape: one sentence that uses the
 * colour line, the line itself copied word for word, and an optional reaction to Alpha with no
 * source at all. Sharing Alpha's list of claims invited Beta to fill every slot, and to put labels
 * such as "Alpha" where a quotation belonged.
 *
 * @param aside one flourish, or empty; never checked
 * @param colour one sentence of colour that uses the line
 * @param quote the colour line, copied exactly
 * @param reaction one sentence reacting to Alpha, or empty; it makes no claim of its own
 */
public record ColourCommentary(String aside, String colour, String quote, String reaction) {

  public ColourCommentary {
    aside = aside == null ? "" : aside.strip();
    colour = colour == null ? "" : colour.strip();
    quote = quote == null ? "" : quote.strip();
    reaction = reaction == null ? "" : reaction.strip();
  }

  /** The same reply as claims, so the shared checkers and the CSV can read it. */
  public Commentary asCommentary() {
    var claims = new ArrayList<Claim>();
    claims.add(new Claim(colour, quote.isEmpty() ? List.of() : List.of(quote)));
    if (!reaction.isEmpty()) {
      claims.add(new Claim(reaction, List.of()));
    }
    return new Commentary(aside, claims);
  }
}
