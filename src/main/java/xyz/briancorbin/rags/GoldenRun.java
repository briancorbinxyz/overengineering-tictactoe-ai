package xyz.briancorbin.rags;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import tools.jackson.databind.json.JsonMapper;
import xyz.briancorbin.rags.FactChecker.Tally;
import xyz.briancorbin.rags.GoldenScorer.Hit;
import xyz.briancorbin.rags.GoldenScorer.Score;
import xyz.briancorbin.rags.GoldenSet.Question;

/**
 * Runs every golden question through the archive and writes down what happened.
 *
 * <p>Three files go to {@code build/}, named {@code episode-3-<model>-<mode>-k4}:
 *
 * <ul>
 *   <li>{@code .csv}: one row per question, with the retrieval score, Beta's traced quotations,
 *       Alpha's claims by verdict, abstention, stale answers, tokens and time;
 *   <li>{@code .jsonl}: the same rows in full, with every chunk retrieved, every quotation and
 *       every claim, so a failure can be diagnosed from the run itself;
 *   <li>{@code -summary.md}: the per-stratum table the article prints.
 * </ul>
 *
 * <p>Every row records the commit, the models and a hash of the prompts. Change any of them and
 * the numbers are a new baseline, not a comparison.
 */
public final class GoldenRun {

  private static final Logger log = LoggerFactory.getLogger(GoldenRun.class);

  /** The advisor's default: four chunks per question. */
  static final int K = 4;

  /** Words that mark an answer as knowing its source is out of date. A heuristic, said so. */
  private static final Pattern FLAGS_STALE =
      Pattern.compile("(?i)\\b(withdrawn|superseded|no longer|retired|archived|was proposed)\\b");

  /** What the run was measured on. */
  public record Setup(
      SpecCorpus.Manifest corpus,
      String chatModel,
      String embeddingModel,
      Map<String, String> digests,
      String promptsHash) {}

  /** One question's outcome. */
  public record Row(
      Question question,
      Archive.Ruling ruling,
      Score score,
      Double betaVerified,
      Tally alphaTally,
      boolean staleRetrieved,
      boolean staleCited,
      boolean staleFlagged) {

    boolean staleAsCurrent() {
      return staleCited && !staleFlagged;
    }

    int tokens() {
      return value(ruling.betaPromptTokens()) + value(ruling.alphaPromptTokens());
    }
  }

  private final Archive archive;
  private final GoldenScorer scorer;
  private final CitationChecker citations;

  public GoldenRun(Archive archive, GoldenScorer scorer, CitationChecker citations) {
    this.archive = archive;
    this.scorer = scorer;
    this.citations = citations;
  }

  public List<Row> run(List<Question> questions) {
    var rows = new ArrayList<Row>();
    for (Question q : questions) {
      // A fresh conversation per question: no question's memory leaks into the next.
      var ruling = archive.ask(q.question(), "golden-" + q.id() + "-" + UUID.randomUUID());
      rows.add(row(q, ruling));
      log.info("{} [{}] hit@{}={} rank={}", q.id(), q.stratum(), K, rows.getLast().score().hitAt(K), rows.getLast().score().firstHit());
    }
    return List.copyOf(rows);
  }

  Row row(Question q, Archive.Ruling ruling) {
    List<Document> top = ruling.retrieved().subList(0, Math.min(K, ruling.retrieved().size()));
    Score score = scorer.score(q.expected(), top);
    Double verified =
        ruling.mode() == Archive.Mode.DUO
            ? new QuoteResolver.Resolution(ruling.betaVerdicts(), ruling.quotes()).verifiedShare()
            : null;
    boolean staleRetrieved =
        top.stream().anyMatch(d -> q.stale().stream().anyMatch(a -> scorer.hit(a, d) != Hit.NONE));
    List<Quote> cited =
        ruling.mode() == Archive.Mode.DUO
            ? ruling.alpha().map(a -> citations.cited(a, ruling.quotes())).orElse(List.of())
            : ruling.quotes();
    // Stale only if a quotation Alpha relied on comes from the stale element itself, not merely
    // from a chunk that also happens to hold it.
    List<String> staleTexts =
        q.stale().stream().map(a -> scorer.elementText(a).map(QuoteResolver::normalise).orElse("")).toList();
    boolean staleCited =
        cited.stream()
            .map(quote -> QuoteResolver.normalise(quote.text()))
            .anyMatch(t -> staleTexts.stream().anyMatch(st -> !st.isEmpty() && st.contains(t)));
    boolean staleFlagged =
        ruling.alpha().map(a -> FLAGS_STALE.matcher(a.answer()).find()).orElse(false);
    return new Row(
        q,
        ruling,
        score,
        verified,
        Tally.of(ruling.alphaVerdicts()),
        staleRetrieved,
        staleCited,
        staleFlagged);
  }

  /** Writes the three files and returns the summary table. */
  public String write(List<Row> rows, Setup setup, Path dir) {
    String name =
        "episode-3-%s-%s-k%d"
            .formatted(
                setup.chatModel().replaceAll("[^A-Za-z0-9.-]", "_"),
                archive.mode().name().toLowerCase(Locale.ROOT),
                K);
    String summary = summary(rows, setup);
    try {
      Files.createDirectories(dir);
      Files.write(dir.resolve(name + ".csv"), csv(rows, setup));
      Files.write(dir.resolve(name + ".jsonl"), jsonLines(rows, setup));
      Files.writeString(dir.resolve(name + "-summary.md"), summary);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
    log.info("Wrote {}.csv, .jsonl and -summary.md to {}", name, dir);
    return summary;
  }

  static List<String> csv(List<Row> rows, Setup setup) {
    var lines = new ArrayList<String>();
    lines.add(
        "id,stratum,status,mode,hit_at_4,first_hit_rank,partial_at_4,first_partial_rank,"
            + "beta_quotes_traced,beta_verified_share,alpha_claims,supported,contradicted,"
            + "unsupported,unchecked,abstained,stale_retrieved,stale_cited,stale_as_current,"
            + "beta_prompt_tokens,alpha_prompt_tokens,millis,commit,chat_model,embedding_model,"
            + "prompts_sha");
    for (Row r : rows) {
      var t = r.alphaTally();
      lines.add(
          String.join(
              ",",
              r.question().id(),
              r.question().stratum(),
              r.question().status(),
              r.ruling().mode().name().toLowerCase(Locale.ROOT),
              bit(r.score().hitAt(K)),
              str(r.score().firstHit()),
              bit(r.score().partialAt(K)),
              str(r.score().firstPartial()),
              String.valueOf(r.ruling().quotes().size()),
              r.betaVerified() == null ? "" : "%.2f".formatted(r.betaVerified()),
              String.valueOf(t.claims()),
              String.valueOf(t.supported()),
              String.valueOf(t.contradicted()),
              String.valueOf(t.unsupported()),
              String.valueOf(t.unchecked()),
              bit(r.ruling().abstained()),
              bit(r.staleRetrieved()),
              bit(r.staleCited()),
              bit(r.staleAsCurrent()),
              str(r.ruling().betaPromptTokens()),
              str(r.ruling().alphaPromptTokens()),
              String.valueOf(r.ruling().millis()),
              setup.corpus().commit().substring(0, 7),
              setup.chatModel(),
              setup.embeddingModel(),
              setup.promptsHash()));
    }
    return lines;
  }

  static List<String> jsonLines(List<Row> rows, Setup setup) {
    var mapper = JsonMapper.shared();
    var lines = new ArrayList<String>();
    lines.add(mapper.writeValueAsString(Map.of("setup", setup)));
    for (Row r : rows) {
      var ruling = r.ruling();
      Map<String, Object> m = new LinkedHashMap<>();
      m.put("id", r.question().id());
      m.put("question", r.question().question());
      m.put("stratum", r.question().stratum());
      m.put("expected", r.question().expected());
      m.put(
          "retrieved",
          ruling.retrieved().stream()
              .map(d -> Map.of("address", Address.of(d).toString(), "score", d.getScore() == null ? 0 : d.getScore()))
              .toList());
      m.put("score", r.score());
      m.put("beta", ruling.beta().orElse(null));
      m.put("beta_verdicts", ruling.betaVerdicts());
      m.put("quotes", ruling.quotes());
      m.put("alpha_prompt", ruling.alphaPrompt());
      m.put("alpha", ruling.alpha().orElse(null));
      m.put("alpha_verdicts", ruling.alphaVerdicts());
      m.put("abstained", ruling.abstained());
      m.put("stale_cited", r.staleCited());
      m.put("stale_flagged", r.staleFlagged());
      m.put("millis", ruling.millis());
      lines.add(mapper.writeValueAsString(m));
    }
    return lines;
  }

  /** The table the article prints: one row per stratum, then the whole set. */
  static String summary(List<Row> rows, Setup setup) {
    var by = new LinkedHashMap<String, List<Row>>();
    for (String s : GoldenSet.STRATA) {
      by.put(s, new ArrayList<>());
    }
    rows.forEach(r -> by.computeIfAbsent(r.question().stratum(), k -> new ArrayList<>()).add(r));
    var out = new StringBuilder();
    out.append(
        "Commit %s · chat %s · embeddings %s · %d files, %d chunks · ingest %.1f min · largest chunk %d tokens%n%n"
            .formatted(
                setup.corpus().commit().substring(0, 7),
                setup.chatModel(),
                setup.embeddingModel(),
                setup.corpus().files(),
                setup.corpus().chunks(),
                setup.corpus().ingestMillis() / 60000.0,
                setup.corpus().largestChunkTokens()));
    out.append("| Stratum | Questions | Hit@4 | Partial@4 | MRR | Alpha abstained | Stale as current |\n");
    out.append("|---|---|---|---|---|---|---|\n");
    for (var e : by.entrySet()) {
      if (!e.getValue().isEmpty()) {
        out.append(line(e.getKey(), e.getValue()));
      }
    }
    out.append(line("all", rows));
    var answerable = rows.stream().filter(r -> r.question().answerable()).toList();
    var unanswerable = rows.stream().filter(r -> !r.question().answerable()).toList();
    var verified =
        rows.stream().map(Row::betaVerified).filter(v -> v != null).mapToDouble(Double::doubleValue).average();
    var millis = rows.stream().map(r -> r.ruling().millis()).sorted(Comparator.naturalOrder()).toList();
    out.append(
        "%nAbstained correctly on %d of %d unanswerable questions; abstained wrongly on %d of %d answerable ones.%n"
            .formatted(
                count(unanswerable, r -> r.ruling().abstained()),
                unanswerable.size(),
                count(answerable, r -> r.ruling().abstained()),
                answerable.size()));
    out.append(
        "Beta's quotations traced word for word: %s. Alpha's claims: %s.%n"
            .formatted(
                verified.isPresent() ? "%.0f%%".formatted(verified.getAsDouble() * 100) : "n/a",
                words(Tally.of(rows.stream().flatMap(r -> r.ruling().alphaVerdicts().stream()).toList()))));
    out.append(
        "Prompt tokens per question, mean %.0f. Time per question, p50 %.1f s, p95 %.1f s.%n"
            .formatted(
                rows.stream().mapToInt(Row::tokens).average().orElse(0),
                percentile(millis, 50) / 1000.0,
                percentile(millis, 95) / 1000.0));
    return out.toString();
  }

  private static String line(String name, List<Row> rows) {
    double hit = share(rows, r -> r.score().hitAt(K));
    double partial = share(rows, r -> r.score().partialAt(K));
    double mrr =
        rows.stream()
            .filter(r -> r.question().answerable())
            .mapToDouble(r -> r.score().reciprocalRank())
            .average()
            .orElse(0);
    boolean none = rows.stream().noneMatch(r -> r.question().answerable());
    return "| %s | %d | %s | %s | %s | %d | %d |%n"
        .formatted(
            name,
            rows.size(),
            none ? "n/a" : "%.0f%%".formatted(hit * 100),
            none ? "n/a" : "%.0f%%".formatted(partial * 100),
            none ? "n/a" : "%.2f".formatted(mrr),
            count(rows, r -> r.ruling().abstained()),
            count(rows, Row::staleAsCurrent));
  }

  /** Share of answerable rows that pass; unanswerable questions have nothing to retrieve. */
  private static double share(List<Row> rows, java.util.function.Predicate<Row> test) {
    var answerable = rows.stream().filter(r -> r.question().answerable()).toList();
    return answerable.isEmpty() ? 0 : (double) count(answerable, test) / answerable.size();
  }

  private static int count(List<Row> rows, java.util.function.Predicate<Row> test) {
    return (int) rows.stream().filter(test).count();
  }

  /** Nearest-rank percentile of a sorted list. */
  static long percentile(List<Long> sorted, int p) {
    if (sorted.isEmpty()) {
      return 0;
    }
    int rank = (int) Math.ceil(p / 100.0 * sorted.size());
    return sorted.get(Math.max(0, rank - 1));
  }

  private static String bit(boolean b) {
    return b ? "1" : "0";
  }

  private static String str(Object o) {
    return o == null ? "" : o.toString();
  }

  private static int value(Integer i) {
    return i == null ? 0 : i;
  }

  /** Short hash of the persona prompts, so a prompt change shows up in every row. */
  static String hash(List<String> prompts) {
    try {
      var md = java.security.MessageDigest.getInstance("SHA-256");
      for (String p : prompts) {
        md.update(p.getBytes(java.nio.charset.StandardCharsets.UTF_8));
      }
      return java.util.HexFormat.of().formatHex(md.digest()).substring(0, 12);
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }

  static String words(Tally t) {
    return "%d supported, %d contradicted, %d unsupported, %d unchecked"
        .formatted(t.supported(), t.contradicted(), t.unsupported(), t.unchecked());
  }
}
