package xyz.briancorbin.rags;

import java.util.Map;
import org.springframework.ai.document.Document;

/**
 * Where a passage came from: the file in the archive, which chunk of it, and the page title.
 *
 * <p>This is provenance, and it lives in a chunk's metadata, not its text. The reader records
 * the title, {@link SpecCorpus} adds the file path, and the splitter adds the chunk number. The
 * model never sees any of it, so nothing here can be mistyped by a model.
 *
 * @param source the file, relative to the spectastic checkout, e.g. {@code
 *     specs/059-corpus-retrieval-scale/spec.html}
 * @param chunk which chunk of the file, counting from 1
 * @param chunks how many chunks the file was split into
 * @param title the page's {@code <title>}
 */
public record Address(String source, int chunk, int chunks, String title) {

  /** Metadata key {@link SpecCorpus} uses for the file path. */
  public static final String SOURCE = "source";

  /** Metadata key {@link SpecCorpus} uses for the spec folder, e.g. 059-corpus-retrieval-scale. */
  public static final String SPEC = "spec";

  /** Metadata key {@link SpecCorpus} uses for the spectastic commit the archive was read at. */
  public static final String COMMIT = "commit";

  /** Reads the address back out of a stored chunk's metadata. */
  public static Address of(Document chunk) {
    Map<String, Object> m = chunk.getMetadata();
    return new Address(
        String.valueOf(m.getOrDefault(SOURCE, "unknown")),
        number(m.get("chunk_index"), 0) + 1, // the splitter counts from 0
        number(m.get("total_chunks"), 1),
        String.valueOf(m.getOrDefault("title", "")));
  }

  /** How the address is shown to Alpha and to readers: {@code specs/…/spec.html, chunk 2 of 7}. */
  @Override
  public String toString() {
    return "%s, chunk %d of %d".formatted(source, chunk, chunks);
  }

  /**
   * Numbers come back from the store's JSON file as whatever type Jackson chose, so accept any
   * {@link Number} and fall back when the key is missing.
   */
  private static int number(Object value, int fallback) {
    return value instanceof Number n ? n.intValue() : fallback;
  }
}
