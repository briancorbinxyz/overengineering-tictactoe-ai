package org.xxdc.oss.example.tictactoe;

/**
 * Checks Beta's quotation against the colour file, by plain string comparison.
 *
 * <p>The evidence is the line Beta was offered. A claim is supported when every one of its
 * sources is that line, word for word, and the line really is in the file. Surrounding whitespace
 * and one pair of quotation marks are ignored; nothing else is, so a paraphrase fails.
 */
public final class QuoteChecker implements FactChecker<String> {

  private final ColourLines lines;

  public QuoteChecker(ColourLines lines) {
    this.lines = lines;
  }

  @Override
  public Verdict check(Claim claim, String offered) {
    if (claim.sources().isEmpty()) {
      return new Verdict(claim, Status.UNCHECKED, "no quotation");
    }
    if (!lines.contains(offered)) {
      return new Verdict(claim, Status.CONTRADICTED, "the offered line is not in the colour file");
    }
    boolean exact = claim.sources().stream().map(ColourLines::unquote).allMatch(offered::equals);
    return exact
        ? new Verdict(claim, Status.SUPPORTED, "quotes the colour line exactly")
        : new Verdict(claim, Status.CONTRADICTED, "the quotation is not the colour line, word for word");
  }

  /** True when at least one claim quotes the line exactly and none quotes anything else. */
  public boolean quotesExactly(Commentary commentary, String offered) {
    var tally = FactChecker.Tally.of(checkAll(commentary, offered));
    return tally.supported() > 0 && tally.contradicted() == 0;
  }
}
