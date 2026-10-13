package xyz.briancorbin.rags;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.Embedding;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;
import org.springframework.ai.embedding.EmbeddingResponseMetadata;

class PrefixedEmbeddingModelTest {

  /** Records what it was asked to embed, and reports one token per character. */
  static final class Recorder implements EmbeddingModel {
    final List<String> seen = new ArrayList<>();

    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
      seen.addAll(request.getInstructions());
      var out = new ArrayList<Embedding>();
      int tokens = 0;
      for (int i = 0; i < request.getInstructions().size(); i++) {
        out.add(new Embedding(new float[] {1f, 0f}, i));
        tokens += request.getInstructions().get(i).length();
      }
      return new EmbeddingResponse(out, new EmbeddingResponseMetadata("fake", new DefaultUsage(tokens, 0)));
    }

    @Override
    public float[] embed(Document document) {
      return embed(document.getText());
    }
  }

  @Test
  void storedChunksGetTheDocumentPrefixAndQuestionsTheQueryPrefix() {
    var recorder = new Recorder();
    var model = new PrefixedEmbeddingModel(recorder);
    var chunk = new Document("The index is never the source of record.");
    model.embed(chunk);
    model.embed("Why no index?");
    assertEquals(
        List.of("search_document: The index is never the source of record.", "search_query: Why no index?"),
        recorder.seen);
    // The stored text itself is untouched.
    assertEquals("The index is never the source of record.", chunk.getText());
  }

  @Test
  void itRemembersTheLongestChunkItEmbedded() {
    var model = new PrefixedEmbeddingModel(new Recorder());
    model.embed(new Document("short"));
    model.embed(new Document("a little longer"));
    assertEquals("search_document: a little longer".length(), model.largestDocumentTokens());
  }
}
