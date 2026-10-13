package xyz.briancorbin.rags;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.reader.jsoup.JsoupDocumentReader;
import org.springframework.ai.reader.jsoup.config.JsoupDocumentReaderConfig;
import org.springframework.ai.transformer.splitter.TokenTextSplitter;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.core.io.FileSystemResource;
import tools.jackson.databind.json.JsonMapper;

/**
 * The archive: every HTML file under {@code specs/} in a pinned spectastic checkout, read, split
 * and embedded into a {@link SimpleVectorStore}, once.
 *
 * <p>This is Spring AI's ETL pipeline with its defaults. Extract: {@link JsoupDocumentReader}
 * turns each file into one {@link Document}. Transform: {@link TokenTextSplitter} cuts it into
 * chunks of about 800 tokens. Load: the vector store embeds each chunk and keeps it. The only
 * thing added to the defaults is provenance: the reader records a page's title but not which file
 * it read, so the file path, spec and commit are stamped into each document's metadata here.
 *
 * <p>Embedding a million words takes minutes, so the store is saved to {@code build/archive/} with
 * a manifest, and a later run with the same commit and embedding model loads it instead.
 */
public final class SpecCorpus {

  private static final Logger log = LoggerFactory.getLogger(SpecCorpus.class);

  /**
   * What was loaded, for the results file. If the commit or the embedding model differ between two
   * runs, their numbers are not comparable.
   */
  public record Manifest(
      String commit,
      String embeddingModel,
      int files,
      int chunks,
      long ingestMillis,
      int largestChunkTokens) {}

  private final Path checkout;
  private final SimpleVectorStore store;
  private final PrefixedEmbeddingModel embedder;
  private final String embeddingModel;
  private final String expectedCommit;
  private final Path storeDir;

  public SpecCorpus(
      Path checkout,
      SimpleVectorStore store,
      PrefixedEmbeddingModel embedder,
      String embeddingModel,
      String expectedCommit,
      Path storeDir) {
    this.checkout = checkout;
    this.store = store;
    this.embedder = embedder;
    this.embeddingModel = embeddingModel;
    this.expectedCommit = expectedCommit;
    this.storeDir = storeDir;
  }

  public Path checkout() {
    return checkout;
  }

  /** Loads the saved store for this commit and model, or builds it. */
  public Manifest open() {
    String commit = commitOf(checkout);
    if (!expectedCommit.isBlank() && !commit.startsWith(expectedCommit)) {
      log.warn(
          "spectastic is at {}, not the pinned {}: these numbers are a new baseline, not a comparison",
          commit,
          expectedCommit);
    }
    String name = "spectastic-%s-%s".formatted(commit.substring(0, 7), embeddingModel.replaceAll("[^A-Za-z0-9.-]", "_"));
    Path storeFile = storeDir.resolve(name + ".json");
    Path manifestFile = storeDir.resolve(name + ".manifest.json");
    if (Files.exists(storeFile) && Files.exists(manifestFile)) {
      store.load(storeFile.toFile());
      Manifest manifest = read(manifestFile);
      log.info("Loaded {} chunks from {} files ({})", manifest.chunks(), manifest.files(), storeFile);
      return manifest;
    }
    Manifest manifest = ingest(commit);
    try {
      Files.createDirectories(storeDir);
      store.save(storeFile.toFile());
      Files.writeString(manifestFile, JsonMapper.shared().writeValueAsString(manifest));
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
    log.info("Saved the store to {}", storeFile);
    return manifest;
  }

  private Manifest ingest(String commit) {
    long start = System.nanoTime();
    List<Path> files = htmlFiles();
    var splitter = TokenTextSplitter.builder().build(); // 800 tokens, as shipped
    int chunks = 0;
    for (int i = 0; i < files.size(); i++) {
      // Extract, transform, load: one file at a time, so progress shows.
      List<Document> pages = read(files.get(i), commit);
      List<Document> pieces = splitter.apply(pages);
      store.add(pieces);
      chunks += pieces.size();
      if ((i + 1) % 50 == 0 || i + 1 == files.size()) {
        log.info("Embedded {} of {} files, {} chunks so far", i + 1, files.size(), chunks);
      }
    }
    long millis = (System.nanoTime() - start) / 1_000_000;
    return new Manifest(
        commit, embeddingModel, files.size(), chunks, millis, embedder.largestDocumentTokens());
  }

  /**
   * One file as one {@link Document}, with its address stamped in. Everything else is the
   * reader's default: the whole {@code <body>} as one string of text, whitespace collapsed.
   */
  List<Document> read(Path file, String commit) {
    String source = checkout.relativize(file).toString().replace('\\', '/');
    var config =
        JsoupDocumentReaderConfig.builder()
            .additionalMetadata(
                Map.of(
                    Address.SOURCE, source,
                    Address.SPEC, specOf(source),
                    Address.COMMIT, commit))
            .build();
    return new JsoupDocumentReader(new FileSystemResource(file), config).get();
  }

  /** Every {@code .html} file under {@code specs/}, in a stable order. */
  List<Path> htmlFiles() {
    try (Stream<Path> walk = Files.walk(checkout.resolve("specs"))) {
      return walk.filter(p -> p.toString().endsWith(".html")).sorted().toList();
    } catch (IOException e) {
      throw new UncheckedIOException("No spectastic checkout at " + checkout, e);
    }
  }

  /** {@code specs/059-corpus-retrieval-scale/spec.html} is in spec {@code 059-corpus-retrieval-scale}. */
  static String specOf(String source) {
    String[] parts = source.split("/");
    return parts.length > 1 ? parts[1] : "";
  }

  /** The commit the checkout is at, read from {@code .git} so no git client is needed. */
  static String commitOf(Path checkout) {
    try {
      Path git = checkout.resolve(".git");
      String head = Files.readString(git.resolve("HEAD")).strip();
      if (!head.startsWith("ref: ")) {
        return head; // a tag checkout is detached: HEAD is the commit itself
      }
      String ref = head.substring(5);
      Path loose = git.resolve(ref);
      if (Files.exists(loose)) {
        return Files.readString(loose).strip();
      }
      for (String line : Files.readAllLines(git.resolve("packed-refs"))) {
        if (line.endsWith(" " + ref)) {
          return line.substring(0, line.indexOf(' '));
        }
      }
      throw new IllegalStateException("Cannot resolve " + ref + " in " + git);
    } catch (IOException e) {
      throw new UncheckedIOException("Not a git checkout: " + checkout, e);
    }
  }

  private static Manifest read(Path manifest) {
    try {
      return JsonMapper.shared().readValue(Files.readString(manifest), Manifest.class);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }
}
