package xyz.briancorbin.rags;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.BatchingStrategy;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingOptions;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;

/**
 * Adds the task prefixes {@code nomic-embed-text} was trained with.
 *
 * <p>nomic embeds a passage and a question differently, and it learned which is which from a
 * prefix: {@code search_document: } for text being stored, {@code search_query: } for a question
 * being searched. Without them it still returns numbers, just worse ones, and nothing warns you.
 * Neither Spring AI nor Ollama adds them, so this wrapper does.
 *
 * <p>The prefix goes only to the embedding model. The stored chunk text stays clean, so what the
 * chat model reads and what the quote resolver matches are the words in the file.
 *
 * <p>Which call is which follows from how {@code SimpleVectorStore} uses an {@link
 * EmbeddingModel}: it stores each chunk through {@link #embed(Document)} and searches through
 * {@link #embed(String)}, which ends in {@link #call}. So documents get the document prefix and
 * everything that arrives through {@link #call} is treated as a query.
 */
public final class PrefixedEmbeddingModel implements EmbeddingModel {

  static final String DOCUMENT = "search_document: ";
  static final String QUERY = "search_query: ";

  private final EmbeddingModel delegate;
  private final AtomicInteger largestDocumentTokens = new AtomicInteger();

  public PrefixedEmbeddingModel(EmbeddingModel delegate) {
    this.delegate = delegate;
  }

  /** A question being searched for. */
  @Override
  public EmbeddingResponse call(EmbeddingRequest request) {
    return delegate.call(prefixed(QUERY, request.getInstructions()));
  }

  /** A chunk being stored. */
  @Override
  public float[] embed(Document document) {
    var response =
        delegate.call(prefixed(DOCUMENT, List.of(text(document))));
    recordTokens(response);
    return response.getResult().getOutput();
  }

  /** Chunks being stored in batches, for vector stores that batch. The options are not passed on. */
  @Override
  public List<float[]> embed(
      List<Document> documents, EmbeddingOptions options, BatchingStrategy batchingStrategy) {
    var out = new ArrayList<float[]>(documents.size());
    for (List<Document> batch : batchingStrategy.batch(documents)) {
      var texts = batch.stream().map(PrefixedEmbeddingModel::text).toList();
      delegate.call(prefixed(DOCUMENT, texts)).getResults().forEach(r -> out.add(r.getOutput()));
    }
    return out;
  }

  @Override
  public int dimensions() {
    return delegate.dimensions();
  }

  /**
   * The most tokens Ollama reported for any one stored chunk, prefix included. With {@code
   * truncate=false} an over-long chunk fails loudly instead, so this is how close the longest one
   * came to the embedding model's window.
   */
  public int largestDocumentTokens() {
    return largestDocumentTokens.get();
  }

  private void recordTokens(EmbeddingResponse response) {
    var usage = response.getMetadata().getUsage();
    if (usage != null && usage.getPromptTokens() != null) {
      largestDocumentTokens.accumulateAndGet(usage.getPromptTokens(), Math::max);
    }
  }

  /**
   * The request goes out with no options of its own, so Ollama's embedding model uses the ones
   * configured in {@code application.properties}. Passing Spring AI's generic options here, as
   * {@link EmbeddingModel#embed(String)} does, would quietly replace them: the Ollama model keeps
   * only the model name from generic options, and {@code truncate=false} is lost.
   */
  private static EmbeddingRequest prefixed(String prefix, List<String> texts) {
    return new EmbeddingRequest(texts.stream().map(t -> prefix + t).toList(), null);
  }

  private static String text(Document document) {
    return document.getText() == null ? "" : document.getText();
  }
}
