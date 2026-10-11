package org.xxdc.oss.example.tictactoe;

import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.ResponseEntity;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.model.ChatResponse;

/**
 * Beta, the colour commentator. Alpha calls the move; on quiet moves Beta adds context.
 *
 * <p>In this episode the context is one hand-written line, picked by the program. Beta must quote
 * it word for word in a claim's sources, and {@link QuoteChecker} compares it with the file: the
 * series' first verified quotation. From Episode 3, Beta has to find its material.
 */
public final class BetaColourCommentator {

  private static final Logger log = LoggerFactory.getLogger(BetaColourCommentator.class);

  private final ChatClient chatClient;
  private final QuoteChecker quotes;

  public BetaColourCommentator(ChatClient chatClient, ColourLines colour) {
    this.chatClient = chatClient;
    this.quotes = new QuoteChecker(colour);
  }

  /**
   * What Beta said, and whether its quotation is really in the colour file.
   *
   * @param commentary Beta's reply, or a plain fallback
   * @param offered the line Beta was given
   * @param quoteVerified true when a claim quotes the offered line exactly, and none quotes
   *     anything else
   * @param straySources claims whose sources are not the colour line, such as a label or a fact
   *     Beta added
   * @param fromModel false when the model could not be reached
   * @param prompt what Beta was sent
   */
  public record Colour(
      Commentary commentary,
      String offered,
      boolean quoteVerified,
      int straySources,
      boolean fromModel,
      String prompt) {}

  /**
   * Colour for one quiet move.
   *
   * @param conversationId Beta's own conversation for this game
   * @param report the move, as Alpha saw it
   * @param alphaLine what Alpha just said about it
   * @param line the colour line to use
   */
  public Colour onQuietMove(
      String conversationId, MoveReport report, Commentary alphaLine, String line) {
    var prompt =
        "Move report:\n%s\nAlpha just said: \"%s\"\nYour colour line: \"%s\"\n"
            .formatted(report.toPrompt(), alphaLine.answer(), line);
    Optional<Commentary> reply = ask(conversationId, prompt);
    var commentary = reply.orElseGet(() -> Commentary.factual(line));
    boolean verified = reply.isPresent() && quotes.quotesExactly(commentary, line);
    int stray = reply.isPresent() ? quotes.straySources(commentary, line) : 0;
    log.info("  Beta: {}", commentary.answer());
    if (commentary.hasAside()) {
      log.info("    ({})", commentary.aside());
    }
    return new Colour(commentary, line, verified, stray, reply.isPresent(), prompt);
  }

  private Optional<Commentary> ask(String conversationId, String prompt) {
    try {
      ResponseEntity<ChatResponse, Commentary> response =
          chatClient
              .prompt()
              .user(prompt)
              .advisors(a -> a.param(ChatMemory.CONVERSATION_ID, conversationId))
              .call()
              .responseEntity(
                  Commentary.class, spec -> spec.useProviderStructuredOutput().validateSchema());
      return Optional.ofNullable(response.entity());
    } catch (RuntimeException e) {
      log.warn("Beta is unavailable, the line goes out plain: {}", e.getMessage());
      return Optional.empty();
    }
  }
}
