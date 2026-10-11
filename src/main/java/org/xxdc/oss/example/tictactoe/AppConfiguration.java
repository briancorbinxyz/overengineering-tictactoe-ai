package org.xxdc.oss.example.tictactoe;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.xxdc.oss.example.BotPlayer;
import org.xxdc.oss.example.Game;
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

  /** The most claims a reply should make; the prompt asks for no more, and the CSV flags excess. */
  static final int CLAIM_LIMIT = 3;

  /**
   * AlphaBeta plays perfectly, so against MCTS almost every game is a draw. Set {@code
   * game.x-strategy=RANDOM} to see wins, and with them real win commentary for the checks.
   */
  Game newGame(BotStrategy x, BotStrategy o) {
    return new Game(
        3,
        false,
        new PlayerNode.Local<>("X", new BotPlayer(x)),
        new PlayerNode.Local<>("O", new BotPlayer(o)));
  }

  @Bean
  CommandLineRunner playOneGame(
      AlphaCommentaryPersona alpha,
      @Value("${alpha.memory.max-messages:20}") int window,
      @Value("${alpha.play-on-startup:true}") boolean play,
      @Value("${commentary.mode:duo}") String mode,
      @Value("${spring.ai.ollama.chat.model:mistral}") String model,
      @Value("${game.x-strategy:ALPHABETA}") BotStrategy x,
      @Value("${game.o-strategy:MCTS}") BotStrategy o) {
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
            + "beta_stray_sources");
    for (var r : rows) {
      var t = FactChecker.Tally.of(r.verdicts());
      int claims = r.commentary().claims().size();
      lines.add(
          String.join(
              ",",
              String.valueOf(r.move()),
              String.valueOf(r.fromModel()),
              r.promptTokens() == null ? "" : r.promptTokens().toString(),
              String.valueOf(claims),
              String.valueOf(claims > CLAIM_LIMIT),
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
              r.colour().map(b -> String.valueOf(b.straySources())).orElse("")));
    }
    Files.createDirectories(path.getParent());
    Files.write(path, lines);
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
