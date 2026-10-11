package org.xxdc.oss.example.tictactoe;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.ResponseEntity;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.model.ChatResponse;
import org.xxdc.oss.example.Game;
import org.xxdc.oss.example.GameState;
import org.xxdc.oss.example.analysis.StrategicTurningPoint;
import org.xxdc.oss.example.commentary.CommentaryPersona;

/**
 * Alpha, the series' ship's computer, as a tic-tac-toe commentator with a memory.
 *
 * <p>It still implements Episode 1's {@link CommentaryPersona}, and still decorates a scripted
 * persona, which it falls back to when the model cannot be reached. What is new is {@link
 * #broadcast(Game)}: a commentary that hears about every move, not just turning points, and
 * remembers the game it is watching.
 */
public final class AlphaCommentaryPersona implements CommentaryPersona {

  private static final Logger log = LoggerFactory.getLogger(AlphaCommentaryPersona.class);

  private final ChatClient chatClient;
  private final CommentaryPersona scripted;
  private final ColourLines colour;
  private final int memoryWindow;
  private final Optional<BetaColourCommentator> beta;
  private final GameFactChecker checker = new GameFactChecker();

  /**
   * @param beta the colour commentator, or empty for a single-commentator broadcast, in which case
   *     Alpha is offered the colour lines itself
   */
  public AlphaCommentaryPersona(
      ChatClient chatClient,
      CommentaryPersona scripted,
      ColourLines colour,
      int memoryWindow,
      Optional<BetaColourCommentator> beta) {
    this.chatClient = chatClient;
    this.scripted = scripted;
    this.colour = colour;
    this.memoryWindow = memoryWindow;
    this.beta = beta;
  }

  /**
   * One move's commentary, with what it cost and a verdict on each of Alpha's claims. {@code
   * colour} is Beta's contribution on a quiet move, when there is one.
   */
  public record MoveCommentary(
      int move,
      String prompt,
      Commentary commentary,
      Integer promptTokens,
      List<FactChecker.Verdict> verdicts,
      boolean fromModel,
      Optional<BetaColourCommentator.Colour> colour) {}

  /**
   * Episode 1's contract: comment on a turning point. The conversation id comes from the game's
   * {@code GameContext}, a scoped value bound for the duration of {@code Game.play}, so this only
   * works while a game is being played.
   */
  @Override
  public String comment(StrategicTurningPoint turningPoint) {
    Optional<String> gameId = Game.gameContext().map(c -> c.id() + ":alpha");
    if (gameId.isEmpty()) {
      return scripted.comment(turningPoint);
    }
    var prompt =
        "Move %d: %s %s.\nBoard:\n%s"
            .formatted(
                turningPoint.moveNumber(),
                turningPoint.playerMarker(),
                MoveReport.describe(turningPoint),
                MoveReport.render(turningPoint.gameState()));
    return ask(gameId.get(), prompt)
        .map(ResponseEntity::entity)
        .map(Commentary::answer)
        .orElseGet(() -> scripted.comment(turningPoint));
  }

  /** Starts commentary for one game. Pass {@code broadcast::onMove} to {@code playWithAction}. */
  public Broadcast broadcast(Game game) {
    return new Broadcast(game.id().toString());
  }

  /**
   * Commentary for one game. Each commentator has its own conversation, and so its own memory:
   * in a shared one, both would appear as "the assistant" and the model would blur who said what.
   */
  public final class Broadcast {

    private final String conversationId;
    private final String betaConversationId;
    private final List<MoveCommentary> moves = new ArrayList<>();
    private int quietMoves;

    private Broadcast(String gameId) {
      this.conversationId = gameId + ":alpha";
      this.betaConversationId = gameId + ":beta";
    }

    /** Called by the game after every move. */
    public void onMove(Game game) {
      List<GameState> history = List.copyOf(game.history());
      int n = game.moveNumber();
      GameState before = history.get(history.size() - 2);
      GameState after = history.getLast();

      // Pick the colour line first; who gets it depends on whether Beta is in the booth.
      var bare = MoveReport.of(before, after, n, Optional.empty());
      Optional<String> line = bare.quiet() ? colour.forQuietMove(quietMoves++) : Optional.empty();
      var report = beta.isPresent() ? bare : MoveReport.of(before, after, n, line);
      var prompt = report.toPrompt();
      var reply = ask(conversationId, prompt);
      var commentary =
          reply.map(ResponseEntity::entity).orElseGet(() -> Commentary.factual(report.plainLine()));
      var verdicts =
          checker.checkAll(
              commentary, new GameFactChecker.Evidence(history, n, earliestVisible(n)));
      log.info("Move {}: {}", n, commentary.answer());
      logProblems(verdicts);
      if (commentary.hasAside()) {
        log.info("  ({})", commentary.aside());
      }
      // Beta speaks on quiet moves only, after Alpha. Turning points are Alpha's.
      Optional<BetaColourCommentator.Colour> said =
          beta.flatMap(b -> line.map(l -> b.onQuietMove(betaConversationId, report, commentary, l)));
      moves.add(
          new MoveCommentary(
              n, prompt, commentary, promptTokens(reply), verdicts, answered(reply), said));
    }

    /** The post-game summary, from memory. Turning points are not re-sent. */
    public MoveCommentary postGame(Game game) {
      List<GameState> history = List.copyOf(game.history());
      int last = game.moveNumber();
      var prompt =
          "The game is over. Give the post-game summary: one claim per turning point you can"
              + " see in this conversation. Say what it meant for the game, put its move number in"
              + " the text (\"move 5\"), and put that move in the claim's sources.";
      var reply = ask(conversationId, prompt);
      var commentary =
          reply
              .map(ResponseEntity::entity)
              .orElseGet(() -> Commentary.factual("No summary: the model could not be reached."));
      var verdicts =
          checker.checkAll(
              commentary, new GameFactChecker.Evidence(history, last, earliestVisible(last + 1)));
      var mc =
          new MoveCommentary(
              last + 1,
              prompt,
              commentary,
              promptTokens(reply),
              verdicts,
              answered(reply),
              Optional.empty());
      log.info("Post-game: {}", commentary.answer());
      logProblems(verdicts);
      return mc;
    }

    public List<MoveCommentary> moves() {
      return List.copyOf(moves);
    }

    public String conversationId() {
      return conversationId;
    }
  }

  private static void logProblems(List<FactChecker.Verdict> verdicts) {
    for (var v : verdicts) {
      if (v.status() == FactChecker.Status.CONTRADICTED
          || v.status() == FactChecker.Status.UNSUPPORTED) {
        log.warn("  {}: {} ({})", v.status(), v.claim().text(), v.reason());
      }
    }
  }

  /**
   * The oldest move whose report is still in memory when Alpha answers about move n. Each move
   * is two messages (report and reply), so a window of W messages holds about W/2 moves.
   */
  int earliestVisible(int move) {
    return Math.max(1, move - memoryWindow / 2);
  }

  private Optional<ResponseEntity<ChatResponse, Commentary>> ask(
      String conversationId, String prompt) {
    try {
      return Optional.of(
          chatClient
              .prompt()
              .user(prompt)
              .advisors(a -> a.param(ChatMemory.CONVERSATION_ID, conversationId))
              .call()
              .responseEntity(
                  Commentary.class, spec -> spec.useProviderStructuredOutput().validateSchema()));
    } catch (RuntimeException e) {
      // The memory advisor stored the report before the call failed, so this conversation now
      // holds a report with no reply. The row is marked from_model=false; leave it out of any
      // comparison of windows.
      log.warn("Alpha is unavailable, falling back: {}", e.getMessage());
      return Optional.empty();
    }
  }

  private static boolean answered(Optional<ResponseEntity<ChatResponse, Commentary>> reply) {
    return reply.map(ResponseEntity::entity).isPresent();
  }

  /**
   * Prompt tokens as Ollama reports them. If a reply failed validation and was retried, Spring AI
   * adds up the usage of every attempt, so treat a sudden jump as a retry, not a longer prompt.
   */
  private static Integer promptTokens(Optional<ResponseEntity<ChatResponse, Commentary>> reply) {
    return reply
        .map(ResponseEntity::response)
        .map(r -> r.getMetadata().getUsage().getPromptTokens())
        .orElse(null);
  }
}
