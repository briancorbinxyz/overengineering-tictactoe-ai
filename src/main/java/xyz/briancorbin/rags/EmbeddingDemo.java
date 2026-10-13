package xyz.briancorbin.rags;

import java.util.Arrays;
import java.util.List;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SimpleVectorStore.EmbeddingMath;

/**
 * Embeds a handful of sentences and prints how alike each pair is, before anything bigger is
 * trusted to the same numbers.
 *
 * <p>Run it with {@code --archive.run=demo}. It needs Ollama and the embedding model, not the
 * archive.
 */
public final class EmbeddingDemo {

  /** Two that mean the same thing, one that is related, one that is not, and two near-twin ids. */
  static final List<String> SENTENCES =
      List.of(
          "The index is never the source of record.",
          "A citation must resolve to the committed document, not to the search index.",
          "Retrieval is not built until the corpus passes 200,000 tokens.",
          "Alpha took the centre square on move 1.",
          "FR-012",
          "FR-021");

  static final String QUESTION = "Why won't spectastic build a search index for a small corpus?";

  private final PrefixedEmbeddingModel embedder;

  public EmbeddingDemo(PrefixedEmbeddingModel embedder) {
    this.embedder = embedder;
  }

  public String run() {
    // Stored text gets the document prefix, a question gets the query prefix, as in the archive.
    List<float[]> vectors =
        SENTENCES.stream().map(s -> embedder.embed(new Document(s))).toList();
    float[] question = embedder.embed(QUESTION);

    var out = new StringBuilder();
    float[] first = vectors.getFirst();
    out.append(
        "\"%s\" is %d numbers. The first five: %s%n%n"
            .formatted(SENTENCES.getFirst(), first.length, Arrays.toString(Arrays.copyOf(first, 5))));
    out.append("Cosine similarity, 1.00 = same direction:\n\n");
    for (int i = 0; i < SENTENCES.size(); i++) {
      for (int j = i + 1; j < SENTENCES.size(); j++) {
        out.append(
            "%.2f  %s  |  %s%n"
                .formatted(
                    EmbeddingMath.cosineSimilarity(vectors.get(i), vectors.get(j)),
                    SENTENCES.get(i),
                    SENTENCES.get(j)));
      }
    }
    out.append("%nThe question \"%s\" against each sentence:%n%n".formatted(QUESTION));
    for (int i = 0; i < SENTENCES.size(); i++) {
      out.append(
          "%.2f  %s%n"
              .formatted(EmbeddingMath.cosineSimilarity(question, vectors.get(i)), SENTENCES.get(i)));
    }
    return out.toString();
  }
}
