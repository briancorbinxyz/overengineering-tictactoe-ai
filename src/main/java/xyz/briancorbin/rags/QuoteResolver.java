package xyz.briancorbin.rags;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.ai.document.Document;

/**
 * Traces each of Beta's quotations to the retrieved chunk it came from, in code.
 *
 * <p>{@code QuestionAnswerAdvisor} gives the model chunk text and nothing else, so the model
 * cannot see an address and cannot be trusted to cite one. It can copy words, though, and copied
 * words can be found. For every source of every claim, the resolver looks for a retrieved chunk
 * that contains it. A match makes the claim supported and the address comes from that chunk's
 * metadata. A quotation found in none of them means Beta paraphrased or invented it: the claim is
 * contradicted and none of it reaches Alpha.
 *
 * <p>This is Episode 2's {@code QuoteChecker} with new evidence: the "file" Beta must quote from
 * is now whatever the retriever brought back. The comparison is still exact, after the
 * normalisation in {@link #normalise}, and nothing looser.
 */
public final class QuoteResolver implements FactChecker<List<Document>> {

  /**
   * A quotation shorter than this proves little: "MUST NOT" appears in hundreds of chunks. A
   * shorter one is unsupported, not contradicted, because it may well be in the chunk.
   */
  public static final int MIN_WORDS = 4;

  /** What Beta's reply came to once every quotation was traced or rejected. */
  public record Resolution(List<Verdict> verdicts, List<Quote> quotes) {

    /** Share of Beta's quoting claims whose every quotation was found, or null with none. */
    public Double verifiedShare() {
      long quoting = verdicts.stream().filter(v -> !v.claim().sources().isEmpty()).count();
      long supported = verdicts.stream().filter(v -> v.status() == Status.SUPPORTED).count();
      return quoting == 0 ? null : (double) supported / quoting;
    }
  }

  @Override
  public Verdict check(Claim claim, List<Document> retrieved) {
    if (claim.sources().isEmpty()) {
      return new Verdict(claim, Status.UNCHECKED, "no quotation");
    }
    var found = new ArrayList<Address>();
    for (String source : claim.sources()) {
      String quote = normalise(source);
      if (quote.split(" ").length < MIN_WORDS) {
        return new Verdict(
            claim, Status.UNSUPPORTED, "quotation too short to trace: \"%s\"".formatted(quote));
      }
      Optional<Integer> at = locate(quote, retrieved);
      if (at.isEmpty()) {
        return new Verdict(
            claim,
            Status.CONTRADICTED,
            "not word for word in anything retrieved: \"%s\"".formatted(preview(quote)));
      }
      found.add(Address.of(retrieved.get(at.get())));
    }
    return new Verdict(claim, Status.SUPPORTED, "quoted from " + found.getFirst());
  }

  /**
   * Checks every claim, and turns the quotations of the supported ones into labelled {@link
   * Quote}s for Alpha. A claim with any untraceable quotation contributes nothing, not even its
   * good quotations: a source that misquotes once is not quoted from again.
   */
  public Resolution resolve(Commentary reply, List<Document> retrieved) {
    var verdicts = checkAll(reply, retrieved);
    Map<String, Quote> quotes = new LinkedHashMap<>();
    for (Verdict v : verdicts) {
      if (v.status() != Status.SUPPORTED) {
        continue;
      }
      for (String source : v.claim().sources()) {
        String key = normalise(source);
        if (quotes.containsKey(key)) {
          continue; // the same words quoted twice are one piece of evidence
        }
        int index = locate(key, retrieved).orElseThrow();
        String label = "Q" + (quotes.size() + 1);
        quotes.put(
            key, new Quote(label, unquote(source.strip()), Address.of(retrieved.get(index)), index + 1));
      }
    }
    return new Resolution(verdicts, List.copyOf(quotes.values()));
  }

  /** Index of the first retrieved chunk that contains the quotation. */
  static Optional<Integer> locate(String normalisedQuote, List<Document> retrieved) {
    for (int i = 0; i < retrieved.size(); i++) {
      String text = retrieved.get(i).getText();
      if (text != null && normalise(text).contains(normalisedQuote)) {
        return Optional.of(i);
      }
    }
    return Optional.empty();
  }

  /**
   * What "word for word" ignores: runs of whitespace, one pair of surrounding quotation marks, and
   * the typographic forms of quotes, dashes and ellipses, which models routinely type as plain
   * ASCII. Case, spelling and word order all still count.
   */
  static String normalise(String s) {
    String t = Normalizer.normalize(s == null ? "" : s, Normalizer.Form.NFKC);
    t =
        t.replace('‘', '\'')
            .replace('’', '\'')
            .replace('“', '"')
            .replace('”', '"')
            .replace('–', '-')
            .replace('—', '-')
            .replace("…", "...");
    t = t.replaceAll("\\s+", " ").strip();
    return unquote(t);
  }

  private static String unquote(String s) {
    if (s.length() >= 2 && s.startsWith("\"") && s.endsWith("\"")) {
      return s.substring(1, s.length() - 1).strip();
    }
    return s;
  }

  private static String preview(String s) {
    return s.length() <= 80 ? s : s.substring(0, 77) + "...";
  }
}
