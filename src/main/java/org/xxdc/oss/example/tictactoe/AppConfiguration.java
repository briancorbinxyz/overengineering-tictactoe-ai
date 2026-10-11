package org.xxdc.oss.example.tictactoe;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.function.ToIntFunction;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.xxdc.oss.example.BotPlayer;
import org.xxdc.oss.example.Game;
import org.xxdc.oss.example.GameState;
import org.xxdc.oss.example.PlayerNode;
import org.xxdc.oss.example.bot.BotStrategy;

/**
 * Plays one bot-versus-bot game with Alpha commentating, then writes two files to {@code build/},
 * named {@code episode-2-<model>-<mode>-window-<N>}:
 *
 * <ul>
 *   <li>{@code .csv}: one row per move, with prompt tokens, Alpha's claims counted by verdict and
 *       the reasons for any that failed, how many claims only echo the move report, and whether
 *       Beta quoted its colour line exactly;
 *   <li>{@code .jsonl}: the same rows in full, with every prompt, claim and source, so a failure
 *       can be diagnosed from the run itself.
 * </ul>
 */
@Configuration
public class AppConfiguration {

  private static final Logger log = LoggerFactory.getLogger(AppConfiguration.class);

  /**
   * AlphaBeta plays perfectly, so against MCTS almost every game is a draw. Set {@code
   * game.x-strategy=RANDOM} to see wins, and with them real win commentary for the checks.
   */
  Game newGame(ToIntFunction<GameState> x, ToIntFunction<GameState> o) {
    return new Game(
        3,
        false,
        new PlayerNode.Local<>("X", new BotPlayer(x)),
        new PlayerNode.Local<>("O", new BotPlayer(o)));
  }

  /** The named strategies are static fields on {@link BotStrategy}, not enum constants. */
  static ToIntFunction<GameState> strategy(String name) {
    return switch (name.strip().toUpperCase(Locale.ROOT)) {
      case "RANDOM" -> BotStrategy.RANDOM;
      case "MINIMAX" -> BotStrategy.MINIMAX;
      case "ALPHABETA" -> BotStrategy.ALPHABETA;
      case "MAXN" -> BotStrategy.MAXN;
      case "PARANOID" -> BotStrategy.PARANOID;
      case "MCTS" -> BotStrategy.MCTS;
      case "DEFAULT" -> BotStrategy.DEFAULT;
      default -> throw new IllegalArgumentException("unknown bot strategy: " + name);
    };
  }

  @Bean
  CommandLineRunner playOneGame(
      AlphaCommentaryPersona alpha,
      @Value("${alpha.memory.max-messages:20}") int window,
      @Value("${alpha.play-on-startup:true}") boolean play,
      @Value("${commentary.mode:duo}") String mode,
      @Value("${spring.ai.ollama.chat.model:mistral}") String model,
      @Value("${game.x-strategy:ALPHABETA}") String xStrategy,
      @Value("${game.o-strategy:MCTS}") String oStrategy) {
    var x = strategy(xStrategy);
    var o = strategy(oStrategy);
    return _ -> {
      if (!play) {
        return;
      }
      try (var game = newGame(x, o)) {
        var broadcast = alpha.broadcast(game);
        game.playWithAction(broadcast::onMove);
        var summary = broadcast.postGame(game);

        var rows = new ArrayList<>(broadcast.moves());
        rows.add(summary);
        // The model is in the name so runs on different models sit side by side.
        String name =
            "episode-2-%s-%s-window-%d"
                .formatted(model.replaceAll("[^A-Za-z0-9.]+", "-"), mode, window);
        writeCsv(Path.of("build", name + ".csv"), rows);
        writeJsonLines(Path.of("build", name + ".jsonl"), rows);
      }
    };
  }

  private static void writeCsv(Path path, List<AlphaCommentaryPersona.MoveCommentary> rows)
      throws IOException {
    var lines = new ArrayList<String>();
    lines.add(
        "move,from_model,prompt_tokens,claims,over_limit,echoes,supported,contradicted,"
            + "unsupported,unchecked,problems,aside,answer,beta_answer,beta_quote_verified,"
            + "beta_stray_sources,aside_repeat,beta_aside_repeat");
    var alphaAsides = new Asides();
    var betaAsides = new Asides();
    for (var r : rows) {
      var t = FactChecker.Tally.of(r.verdicts());
      boolean alphaRepeat = alphaAsides.repeats(r.commentary().aside());
      String betaRepeat =
          r.colour().map(b -> String.valueOf(betaAsides.repeats(b.commentary().aside()))).orElse("");
      int claims = r.commentary().claims().size();
      lines.add(
          String.join(
              ",",
              String.valueOf(r.move()),
              String.valueOf(r.fromModel()),
              r.promptTokens() == null ? "" : r.promptTokens().toString(),
              String.valueOf(claims),
              String.valueOf(claims > Commentary.MAX_CLAIMS),
              String.valueOf(EchoCheck.count(r.commentary(), r.prompt())),
              String.valueOf(t.supported()),
              String.valueOf(t.contradicted()),
              String.valueOf(t.unsupported()),
              String.valueOf(t.unchecked()),
              quote(String.join(" | ", t.problems())),
              quote(r.commentary().aside()),
              quote(r.commentary().answer()),
              quote(r.colour().map(b -> b.commentary().answer()).orElse("")),
              r.colour().map(b -> String.valueOf(b.quoteVerified())).orElse(""),
              r.colour().map(b -> String.valueOf(b.straySources())).orElse(""),
              String.valueOf(alphaRepeat),
              betaRepeat));
    }
    Files.createDirectories(path.getParent());
    Files.write(path, lines);
    log.info("Asides: Alpha {}, Beta {}", alphaAsides.summary(), betaAsides.summary());
  }

  /**
   * The asides one commentator has used in a game. A joke told twice is a weaker joke, and a model
   * with a memory of the game can still repeat itself; nothing else in the run would notice.
   */
  static final class Asides {
    private final Set<String> seen = new HashSet<>();
    private int told;

    /** True when this aside, ignoring case, spacing and punctuation, was already used. */
    boolean repeats(String aside) {
      String key =
          aside == null
              ? ""
              : aside.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", " ").strip();
      if (key.isEmpty()) {
        return false;
      }
      told++;
      return !seen.add(key);
    }

    String summary() {
      return "%d distinct of %d".formatted(seen.size(), told);
    }
  }

  /** One JSON object per row, written by hand so the episode needs no JSON library of its own. */
  private static void writeJsonLines(Path path, List<AlphaCommentaryPersona.MoveCommentary> rows)
      throws IOException {
    var lines = new ArrayList<String>();
    for (var r : rows) {
      var verdicts =
          r.verdicts().stream()
              .map(
                  v ->
                      "{\"claim\":%s,\"status\":%s,\"reason\":%s}"
                          .formatted(json(v.claim().text()), json(v.status().name()), json(v.reason())))
              .collect(Collectors.joining(",", "[", "]"));
      String beta =
          r.colour()
              .map(
                  b ->
                      "{\"prompt\":%s,\"offered\":%s,\"reply\":%s,\"quote_verified\":%s}"
                          .formatted(
                              json(b.prompt()),
                              json(b.offered()),
                              json(b.commentary()),
                              b.quoteVerified()))
              .orElse("null");
      lines.add(
          "{\"move\":%d,\"prompt\":%s,\"reply\":%s,\"verdicts\":%s,\"beta\":%s}"
              .formatted(r.move(), json(r.prompt()), json(r.commentary()), verdicts, beta));
    }
    Files.createDirectories(path.getParent());
    Files.write(path, lines);
  }

  private static String json(Commentary c) {
    var claims =
        c.claims().stream()
            .map(
                cl ->
                    "{\"text\":%s,\"sources\":%s}"
                        .formatted(
                            json(cl.text()),
                            cl.sources().stream()
                                .map(AppConfiguration::json)
                                .collect(Collectors.joining(",", "[", "]"))))
            .collect(Collectors.joining(",", "[", "]"));
    return "{\"aside\":%s,\"claims\":%s}".formatted(json(c.aside()), claims);
  }

  static String json(String s) {
    if (s == null) {
      return "null";
    }
    var out = new StringBuilder("\"");
    for (char ch : s.toCharArray()) {
      switch (ch) {
        case '"' -> out.append("\\\"");
        case '\\' -> out.append("\\\\");
        case '\n' -> out.append("\\n");
        case '\r' -> out.append("\\r");
        case '\t' -> out.append("\\t");
        default -> {
          if (ch < 0x20) {
            out.append("\\u%04x".formatted((int) ch));
          } else {
            out.append(ch);
          }
        }
      }
    }
    return out.append('"').toString();
  }

  private static String quote(String s) {
    return "\"" + (s == null ? "" : s.replace("\"", "\"\"")) + "\"";
  }
}
