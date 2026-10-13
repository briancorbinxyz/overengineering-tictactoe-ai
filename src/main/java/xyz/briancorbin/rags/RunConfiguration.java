package xyz.briancorbin.rags;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * What a run does, set by {@code archive.run}:
 *
 * <ul>
 *   <li>{@code golden} (the default): every golden question, with results written to {@code
 *       build/};
 *   <li>{@code ask}: the question in {@code archive.question}, or, with none, questions typed at
 *       the terminal in one conversation, so follow-ups work;
 *   <li>{@code demo}: the embedding demo, which needs no archive;
 *   <li>{@code ingest}: build or load the store and stop;
 *   <li>{@code none}: nothing, for tests.
 * </ul>
 */
@Configuration
class RunConfiguration {

  private static final Logger log = LoggerFactory.getLogger(RunConfiguration.class);

  @Bean
  CommandLineRunner run(
      @Value("${archive.run:golden}") String run,
      @Value("${archive.question:}") String question,
      @Value("${archive.golden:classpath:golden/questions.jsonl}") Resource golden,
      @Value("${spring.ai.ollama.base-url}") String ollama,
      @Value("${spring.ai.ollama.chat.model}") String chatModel,
      @Value("${spring.ai.ollama.embedding.model}") String embeddingModel,
      @Value("classpath:persona/alpha.md") Resource alphaPersona,
      @Value("classpath:persona/beta.md") Resource betaPersona,
      @Value("classpath:persona/alpha-solo.md") Resource soloPersona,
      SpecCorpus corpus,
      Archive archive,
      CitationChecker citations,
      PrefixedEmbeddingModel embedder) {
    return args -> {
      switch (run.strip().toLowerCase(Locale.ROOT)) {
        case "none" -> {}
        case "demo" -> log.info("Embedding demo:\n{}", new EmbeddingDemo(embedder).run());
        case "ingest" -> log.info("Archive ready: {}", corpus.open());
        case "ask" -> {
          corpus.open();
          if (!question.isBlank()) {
            print(archive.ask(question, UUID.randomUUID().toString()));
          } else {
            converse(archive);
          }
        }
        case "golden" -> {
          var manifest = corpus.open();
          var questions = GoldenSet.read(golden);
          var goldenRun = new GoldenRun(archive, new GoldenScorer(corpus.checkout()), citations);
          var rows = goldenRun.run(questions);
          var setup =
              new GoldenRun.Setup(
                  manifest,
                  chatModel,
                  embeddingModel,
                  digests(ollama),
                  GoldenRun.hash(
                      List.of(text(alphaPersona), text(betaPersona), text(soloPersona))));
          log.info("Baseline:\n{}", goldenRun.write(rows, setup, Path.of("build")));
        }
        default -> throw new IllegalArgumentException("Unknown archive.run: " + run);
      }
    };
  }

  /** Questions typed at the terminal, one conversation, until an empty line. */
  private static void converse(Archive archive) throws IOException {
    String session = UUID.randomUUID().toString();
    var in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    System.out.println("Ask the archive. An empty line ends the session.");
    for (String line = in.readLine(); line != null && !line.isBlank(); line = in.readLine()) {
      print(archive.ask(line.strip(), session));
    }
  }

  /** The quotations and their addresses: provenance, printed. */
  private static void print(Archive.Ruling ruling) {
    for (Quote q : ruling.quotes()) {
      log.info("  {} {} (rank {})", q.label(), q.address(), q.rank());
    }
    ruling.alphaVerdicts().forEach(v -> log.info("  [{}] {}", v.status(), v.reason()));
  }

  /**
   * The exact model builds, from Ollama's {@code /api/tags}. A tag such as {@code qwen3:8b} can be
   * re-pointed at new weights; the digest cannot.
   */
  static Map<String, String> digests(String baseUrl) {
    var out = new LinkedHashMap<String, String>();
    try (var http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build()) {
      var response =
          http.send(
              HttpRequest.newBuilder(URI.create(baseUrl + "/api/tags")).GET().build(),
              HttpResponse.BodyHandlers.ofString());
      JsonNode tags = JsonMapper.shared().readTree(response.body());
      for (JsonNode model : tags.path("models")) {
        out.put(model.path("name").asString(), model.path("digest").asString());
      }
    } catch (IOException | RuntimeException e) {
      log.warn("Could not read model digests from Ollama: {}", e.getMessage());
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
    return out;
  }

  private static String text(Resource resource) {
    try {
      return resource.getContentAsString(StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }
}
