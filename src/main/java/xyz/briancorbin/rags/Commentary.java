package xyz.briancorbin.rags;

import io.swagger.v3.oas.annotations.media.ArraySchema;
import java.util.List;
import java.util.stream.Collectors;

/**
 * What a commentator says, as structured output.
 *
 * <p>The shape carries through the rest of the series. {@code claims} is everything checkable,
 * each statement with its own sources. {@code aside} is the joke, and it is deliberately
 * unchecked, which is why it may not contain anything a checker could check.
 *
 * <p>Episode 2 used it for one move of tic-tac-toe. From Episode 3 a claim's sources are passages
 * from the archive: Beta's are quotations copied word for word, and Alpha's are the labels of the
 * quotations it was given ("Q2").
 *
 * @param aside one short joke, or empty; it states nothing a reader could check
 * @param claims one to three statements, each with the sources it rests on
 */
public record Commentary(
    String aside, @ArraySchema(minItems = 1, maxItems = MAX_CLAIMS) List<Claim> claims) {

  /**
   * The most claims a reply may make. It is in the JSON schema Spring AI sends, so {@code
   * validateSchema()} rejects a longer reply and asks again, whether or not the model's
   * constrained decoding honours it.
   */
  public static final int MAX_CLAIMS = 3;

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

  /** A plain line used when the model cannot be reached or has nothing to say. */
  static Commentary factual(String line) {
    return new Commentary("", List.of(new Claim(line, List.of())));
  }
}
