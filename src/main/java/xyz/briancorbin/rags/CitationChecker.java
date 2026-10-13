package xyz.briancorbin.rags;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Pattern;

/**
 * Checks that each of Alpha's claims cites quotations Alpha was actually given.
 *
 * <p>Alpha cites by label ("Q2"), the way it cited "move 3" in Episode 2, and the check is just
 * as exact: a label is either in the list Alpha was shown or it is not. A supported verdict here
 * means "rests on a verified quotation", not "is entailed by it". Whether the quotation really
 * says what the claim says is a judgement, and judges arrive in Episode 7, measured against the
 * human labels this episode collects.
 *
 * <p>Saying {@value #ABSTENTION} is a legitimate answer, and on a question the archive cannot
 * answer it is the right one, so an abstaining claim with no sources is unchecked rather than
 * unsupported.
 */
public final class CitationChecker implements FactChecker<List<Quote>> {

  /** The exact words Alpha's prompt asks for when nothing it was given answers the question. */
  public static final String ABSTENTION = "Not in the archive.";

  private static final Pattern ABSTAINS = Pattern.compile("(?i)\\bnot in the archive\\b");

  @Override
  public Verdict check(Claim claim, List<Quote> given) {
    if (claim.sources().isEmpty()) {
      return abstains(claim)
          ? new Verdict(claim, Status.UNCHECKED, "abstains")
          : new Verdict(claim, Status.UNSUPPORTED, "cites no quotation");
    }
    var cited = new ArrayList<Quote>();
    for (String source : claim.sources()) {
      Optional<Quote> quote = find(source, given);
      if (quote.isEmpty()) {
        return new Verdict(
            claim,
            Status.CONTRADICTED,
            "cites %s, which it was not given".formatted(source.strip()));
      }
      cited.add(quote.get());
    }
    return new Verdict(
        claim,
        Status.SUPPORTED,
        "cites " + String.join(", ", cited.stream().map(q -> q.label() + " (" + q.address() + ")").toList()));
  }

  /** True when the reply says the answer is not in the archive and backs no claim with a quote. */
  public boolean abstained(Commentary reply, List<Quote> given) {
    var verdicts = checkAll(reply, given);
    boolean says = reply.claims().stream().anyMatch(CitationChecker::abstains);
    boolean cites = verdicts.stream().anyMatch(v -> v.status() == Status.SUPPORTED);
    return says && !cites;
  }

  /** The quotations a reply cites, in the order first cited, for the results file. */
  public List<Quote> cited(Commentary reply, List<Quote> given) {
    var out = new ArrayList<Quote>();
    for (Claim c : reply.claims()) {
      for (String s : c.sources()) {
        find(s, given).filter(q -> !out.contains(q)).ifPresent(out::add);
      }
    }
    return List.copyOf(out);
  }

  static boolean abstains(Claim claim) {
    return ABSTAINS.matcher(claim.text()).find();
  }

  /** Accepts "Q2", "q2" and "[Q2]"; nothing looser. */
  private static Optional<Quote> find(String source, List<Quote> given) {
    String label = source.strip().replaceAll("^\\[(.*)]$", "$1").toUpperCase(Locale.ROOT);
    return given.stream().filter(q -> q.label().equals(label)).findFirst();
  }
}
