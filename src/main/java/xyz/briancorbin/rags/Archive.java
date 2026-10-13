package xyz.briancorbin.rags;

import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.ResponseEntity;
import org.springframework.ai.chat.client.advisor.vectorstore.QuestionAnswerAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import xyz.briancorbin.rags.FactChecker.Verdict;

/**
 * One question, one hand-off: Beta searches the archive and quotes it, the program traces the
 * quotations to their chunks, and Alpha answers from the traced quotations only.
 *
 * <p>Beta's {@link ChatClient} carries {@link QuestionAnswerAdvisor}, so every call to Beta is a
 * vector search followed by a prompt with the chunk texts pasted in. Alpha's carries no
 * retriever: Alpha never touches the archive, and it never sees a chunk, only quotations that
 * {@link QuoteResolver} found word for word in one. This replaces Episode 2's {@code Broadcast}.
 *
 * <p>In solo mode the retriever moves to Alpha, which searches, quotes and answers in one call,
 * and its quotations go through the same resolver.
 */
public final class Archive {

  private static final Logger log = LoggerFactory.getLogger(Archive.class);

  public enum Mode {
    DUO,
    SOLO
  }

  /** One model call: the reply if there was one, and what came with it. */
  public record Reply(
      Optional<Commentary> commentary, List<Document> retrieved, Integer promptTokens, long millis) {}

  /**
   * Everything that happened for one question, so it can be checked and written down.
   *
   * @param retrieved the chunks the search returned, best first; in duo mode Beta's, in solo
   *     mode Alpha's
   * @param beta Beta's reply, empty in solo mode or if Beta could not be reached
   * @param betaVerdicts the resolver's verdict on each of Beta's claims (Alpha's in solo mode)
   * @param quotes the quotations traced to a chunk, as Alpha was shown them
   * @param alpha Alpha's reply, empty if Alpha could not be reached
   * @param alphaVerdicts the citation check of each of Alpha's claims (the resolver's, in solo)
   * @param abstained Alpha said the answer is not in the archive and cited nothing
   */
  public record Ruling(
      String question,
      Mode mode,
      List<Document> retrieved,
      Optional<Commentary> beta,
      List<Verdict> betaVerdicts,
      List<Quote> quotes,
      Optional<Commentary> alpha,
      List<Verdict> alphaVerdicts,
      boolean abstained,
      Integer betaPromptTokens,
      Integer alphaPromptTokens,
      long betaMillis,
      long alphaMillis,
      String alphaPrompt) {

    public long millis() {
      return betaMillis + alphaMillis;
    }
  }

  private final ChatClient beta;
  private final ChatClient alpha;
  private final ChatClient alphaSolo;
  private final VectorStore store;
  private final QuoteResolver resolver;
  private final CitationChecker citations;
  private final Mode mode;

  public Archive(
      ChatClient beta,
      ChatClient alpha,
      ChatClient alphaSolo,
      VectorStore store,
      QuoteResolver resolver,
      CitationChecker citations,
      Mode mode) {
    this.beta = beta;
    this.alpha = alpha;
    this.alphaSolo = alphaSolo;
    this.store = store;
    this.resolver = resolver;
    this.citations = citations;
    this.mode = mode;
  }

  public Mode mode() {
    return mode;
  }

  /**
   * Answers one question. The conversation id keeps each commentator's memory separate, as in
   * Episode 2: {@code <id>:beta} and {@code <id>:alpha}. A golden run uses a fresh id per question,
   * so no question's memory leaks into the next.
   */
  public Ruling ask(String question, String conversationId) {
    log.info("Q: {}", question);
    return mode == Mode.SOLO ? solo(question, conversationId) : duo(question, conversationId);
  }

  private Ruling duo(String question, String conversationId) {
    // 1. Beta searches. The advisor runs the vector search and pastes the chunk texts in.
    Reply b = call(beta, conversationId + ":beta", question);
    List<Document> retrieved = b.retrieved().isEmpty() ? search(question) : b.retrieved();
    Commentary betaSaid = b.commentary().orElse(Commentary.factual("Beta found nothing it would quote."));
    say("Beta", betaSaid);

    // 2. The program traces every quotation to a retrieved chunk, or rejects it.
    QuoteResolver.Resolution resolution = resolver.resolve(betaSaid, retrieved);

    // 3. Alpha answers from the traced quotations, and only from them.
    String prompt = alphaPrompt(question, resolution.quotes());
    Reply a = call(alpha, conversationId + ":alpha", prompt);
    Commentary alphaSaid = a.commentary().orElse(Commentary.factual("Alpha is unavailable."));
    say("Alpha", alphaSaid);
    var alphaVerdicts = citations.checkAll(alphaSaid, resolution.quotes());

    return new Ruling(
        question,
        Mode.DUO,
        retrieved,
        b.commentary(),
        resolution.verdicts(),
        resolution.quotes(),
        a.commentary(),
        alphaVerdicts,
        a.commentary().isPresent() && citations.abstained(alphaSaid, resolution.quotes()),
        b.promptTokens(),
        a.promptTokens(),
        b.millis(),
        a.millis(),
        prompt);
  }

  private Ruling solo(String question, String conversationId) {
    Reply a = call(alphaSolo, conversationId + ":alpha", question);
    List<Document> retrieved = a.retrieved().isEmpty() ? search(question) : a.retrieved();
    Commentary alphaSaid = a.commentary().orElse(Commentary.factual("Alpha is unavailable."));
    say("Alpha", alphaSaid);
    QuoteResolver.Resolution resolution = resolver.resolve(alphaSaid, retrieved);
    boolean abstained =
        a.commentary().isPresent()
            && alphaSaid.claims().stream().anyMatch(CitationChecker::abstains)
            && resolution.quotes().isEmpty();
    return new Ruling(
        question,
        Mode.SOLO,
        retrieved,
        Optional.empty(),
        resolution.verdicts(),
        resolution.quotes(),
        a.commentary(),
        resolution.verdicts(),
        abstained,
        null,
        a.promptTokens(),
        0,
        a.millis(),
        question);
  }

  /** What Alpha is given: the question, and each traced quotation with its label and address. */
  static String alphaPrompt(String question, List<Quote> quotes) {
    if (quotes.isEmpty()) {
      return "Question: %s%n%nQuotations Beta traced to the archive: none.".formatted(question);
    }
    return "Question: %s%n%nQuotations Beta traced to the archive. Cite them by label.%n%s"
        .formatted(
            question,
            quotes.stream().map(Quote::toPrompt).collect(Collectors.joining(System.lineSeparator())));
  }

  /**
   * Calls a commentator and asks for a {@link Commentary}. As in Episode 2, a failure costs the
   * answer, not the run. The retrieved chunks come back in the response metadata, where {@link
   * QuestionAnswerAdvisor} puts them under {@code qa_retrieved_documents}.
   */
  private Reply call(ChatClient client, String conversationId, String user) {
    long start = System.nanoTime();
    try {
      ResponseEntity<ChatResponse, Commentary> response =
          client
              .prompt()
              .user(user)
              .advisors(a -> a.param(ChatMemory.CONVERSATION_ID, conversationId))
              .call()
              .responseEntity(
                  Commentary.class, spec -> spec.useProviderStructuredOutput().validateSchema());
      ChatResponse chat = response.response();
      List<Document> retrieved =
          chat == null
              ? List.of()
              : Objects.requireNonNullElse(
                  chat.getMetadata().<List<Document>>get(QuestionAnswerAdvisor.RETRIEVED_DOCUMENTS),
                  List.of());
      Integer tokens = chat == null ? null : chat.getMetadata().getUsage().getPromptTokens();
      return new Reply(Optional.ofNullable(response.entity()), retrieved, tokens, since(start));
    } catch (RuntimeException e) {
      log.warn("No reply ({}): {}", conversationId, e.getMessage());
      return new Reply(Optional.empty(), List.of(), null, since(start));
    }
  }

  /**
   * The advisor's own search, run directly. Used only when a chat call failed before the advisor
   * could report what it found, so a model failure is not counted as a retrieval miss.
   */
  private List<Document> search(String question) {
    return store.similaritySearch(SearchRequest.builder().query(question).build());
  }

  private static void say(String who, Commentary c) {
    log.info("  {}: {}", who, c.answer());
    if (c.hasAside()) {
      log.info("    ({})", c.aside());
    }
  }

  private static long since(long start) {
    return (System.nanoTime() - start) / 1_000_000;
  }
}
