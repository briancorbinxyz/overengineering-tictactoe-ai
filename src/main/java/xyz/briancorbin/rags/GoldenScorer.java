package xyz.briancorbin.rags;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Element;
import org.springframework.ai.document.Document;

/**
 * Decides, in code, whether a retrieved chunk found the passage a question expects.
 *
 * <p>An expected address names an element, such as {@code spec.html#FR-001}, but the naive
 * chunks know nothing about elements: they are 800-token slices of a page's text. So the scorer
 * finds where the element's text sits in the page's text, finds where the chunk sits, and
 * measures the overlap. A chunk that holds the whole element is a <em>hit</em>. One that holds at
 * least half of it is a <em>partial hit</em>, which is what a requirement cut in two by a chunk
 * boundary looks like.
 *
 * <p>The page text is read exactly as the archive read it, with jsoup's {@code body().text()}, so
 * a chunk's text is a slice of it and positions can be compared directly.
 */
public final class GoldenScorer {

  public enum Hit {
    FULL,
    PARTIAL,
    NONE
  }

  /**
   * Where the first full and first partial hits came in the results, counting from 1, or null when
   * there was none. A full hit also counts as a partial one.
   */
  public record Score(Integer firstHit, Integer firstPartial) {

    public boolean hitAt(int k) {
      return firstHit != null && firstHit <= k;
    }

    public boolean partialAt(int k) {
      return firstPartial != null && firstPartial <= k;
    }

    /** The reciprocal rank of the first full hit: 1, 1/2, 1/3, …, or 0 for a miss. */
    public double reciprocalRank() {
      return firstHit == null ? 0 : 1.0 / firstHit;
    }
  }

  private record Page(String text, org.jsoup.nodes.Document html) {}

  private final Path checkout;
  private final Map<String, Page> pages = new HashMap<>();

  public GoldenScorer(Path checkout) {
    this.checkout = checkout;
  }

  /** Scores a ranked list of chunks against any of the expected addresses. */
  public Score score(List<String> expected, List<Document> retrieved) {
    Integer hit = null;
    Integer partial = null;
    for (int i = 0; i < retrieved.size(); i++) {
      for (String address : expected) {
        Hit h = hit(address, retrieved.get(i));
        if (h == Hit.FULL && hit == null) {
          hit = i + 1;
        }
        if (h != Hit.NONE && partial == null) {
          partial = i + 1;
        }
      }
    }
    return new Score(hit, partial);
  }

  /** How much of the element at {@code address} one chunk holds. */
  public Hit hit(String address, Document chunk) {
    String file = address.contains("#") ? address.substring(0, address.indexOf('#')) : address;
    if (!file.equals(Address.of(chunk).source())) {
      return Hit.NONE;
    }
    Page page = page(file);
    String element = elementText(address).orElse("");
    String text = normalise(chunk.getText());
    if (element.isEmpty() || text.isEmpty()) {
      return Hit.NONE;
    }
    int c0 = page.text().indexOf(text);
    if (c0 < 0 || element.length() < 2) {
      // Not a clean slice of the page (a multi-byte character split by the tokenizer, say).
      if (text.contains(element)) {
        return Hit.FULL;
      }
      int half = Math.max(1, element.length() / 2);
      return text.contains(element.substring(0, half)) || text.contains(element.substring(half))
          ? Hit.PARTIAL
          : Hit.NONE;
    }
    // The element's text can occur more than once on a page (in a summary table, say); judge the
    // chunk by the occurrence it overlaps most.
    int best = 0;
    for (int e0 = page.text().indexOf(element); e0 >= 0; e0 = page.text().indexOf(element, e0 + 1)) {
      int overlap = Math.min(e0 + element.length(), c0 + text.length()) - Math.max(e0, c0);
      best = Math.max(best, overlap);
    }
    if (best >= element.length()) {
      return Hit.FULL;
    }
    return best * 2 >= element.length() ? Hit.PARTIAL : Hit.NONE;
  }

  /** The text of the element an address names, or the whole page for an address with no {@code #}. */
  public Optional<String> elementText(String address) {
    int hash = address.indexOf('#');
    String file = hash < 0 ? address : address.substring(0, hash);
    Page page = page(file);
    if (hash < 0) {
      return Optional.of(page.text());
    }
    Element el = page.html().getElementById(address.substring(hash + 1));
    return el == null ? Optional.empty() : Optional.of(normalise(el.text()));
  }

  private Page page(String file) {
    return pages.computeIfAbsent(
        file,
        f -> {
          try {
            var html = Jsoup.parse(Files.readString(checkout.resolve(f)));
            return new Page(normalise(html.body().text()), html);
          } catch (IOException e) {
            throw new UncheckedIOException("No such file in the archive: " + f, e);
          }
        });
  }

  static String normalise(String s) {
    return s == null ? "" : s.replaceAll("\\s+", " ").strip();
  }
}
