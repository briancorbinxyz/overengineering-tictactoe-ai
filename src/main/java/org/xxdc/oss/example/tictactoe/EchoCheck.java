package org.xxdc.oss.example.tictactoe;

import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Spots a claim that only reads the move report back.
 *
 * <p>A fact checker rewards anything true, and nothing is truer than a copy of its own input. A
 * claim such as "X played row 1, column 2" is always supported and says nothing. This check is
 * not about truth but about whether the commentator added anything: a claim is an echo when
 * nearly all of its words already appear in the report it was given.
 */
public final class EchoCheck {

  private static final Pattern WORD = Pattern.compile("[a-z0-9]+");
  private static final Set<String> STOP =
      Set.of(
          "a", "an", "the", "and", "or", "of", "on", "in", "to", "at", "is", "it", "its", "has",
          "have", "with", "for", "by", "as", "this", "that", "now", "so", "be", "was");

  /** The share of a claim's words that must already be in the report for it to be an echo. */
  static final double THRESHOLD = 0.8;

  /** True when the claim adds almost nothing to the report. Very short claims never count. */
  public static boolean echoes(String claim, String report) {
    Set<String> said = words(claim);
    if (said.size() < 3) {
      return false;
    }
    Set<String> given = words(report);
    long copied = said.stream().filter(given::contains).count();
    return (double) copied / said.size() >= THRESHOLD;
  }

  /** How many of a reply's claims echo the report. */
  public static int count(Commentary commentary, String report) {
    return (int) commentary.claims().stream().filter(c -> echoes(c.text(), report)).count();
  }

  static Set<String> words(String text) {
    if (text == null) {
      return Set.of();
    }
    return WORD.matcher(text.toLowerCase(Locale.ROOT))
        .results()
        .map(m -> m.group())
        .filter(w -> !STOP.contains(w))
        .collect(Collectors.toSet());
  }

  private EchoCheck() {}
}
