package xyz.briancorbin.rags;

import java.util.ArrayList;
import java.util.List;

/**
 * Checks claims against evidence and returns a verdict for each.
 *
 * <p>The series adds a checker each time the evidence changes. In Episode 2 the evidence was the
 * game's own history and the colour file. In Episode 3 it is what the retriever brought back
 * ({@link QuoteResolver}) and the quotations Alpha was shown ({@link CitationChecker}). Both are
 * still plain code; a model only becomes a checker in Episode 7, behind this same interface.
 *
 * @param <E> what the claims are checked against
 */
public interface FactChecker<E> {

  /** How a claim stands against the evidence. */
  enum Status {
    /** Every check that applied passed. */
    SUPPORTED,
    /** The evidence says otherwise. */
    CONTRADICTED,
    /** Nothing the commentator could see backs it. */
    UNSUPPORTED,
    /** Nothing in it was checkable by this checker. */
    UNCHECKED
  }

  /** The outcome for one claim, with the reason in words. */
  record Verdict(Claim claim, Status status, String reason) {}

  Verdict check(Claim claim, E evidence);

  /** Checks every claim in a reply. Checkers may add verdicts about the reply as a whole. */
  default List<Verdict> checkAll(Commentary commentary, E evidence) {
    var verdicts = new ArrayList<Verdict>();
    for (Claim claim : commentary.claims()) {
      verdicts.add(check(claim, evidence));
    }
    return List.copyOf(verdicts);
  }

  /** Counts per status, and the reasons for anything that is not supported or unchecked. */
  record Tally(int claims, int supported, int contradicted, int unsupported, int unchecked,
      List<String> problems) {

    public static Tally of(List<Verdict> verdicts) {
      int s = 0;
      int c = 0;
      int u = 0;
      int n = 0;
      var problems = new ArrayList<String>();
      for (Verdict v : verdicts) {
        switch (v.status()) {
          case SUPPORTED -> s++;
          case CONTRADICTED -> {
            c++;
            problems.add(v.reason());
          }
          case UNSUPPORTED -> {
            u++;
            problems.add(v.reason());
          }
          case UNCHECKED -> n++;
        }
      }
      return new Tally(verdicts.size(), s, c, u, n, List.copyOf(problems));
    }

    public boolean clean() {
      return contradicted == 0 && unsupported == 0;
    }
  }
}
