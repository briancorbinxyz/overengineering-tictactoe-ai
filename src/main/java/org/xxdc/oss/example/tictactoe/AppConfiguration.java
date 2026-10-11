package org.xxdc.oss.example.tictactoe;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.xxdc.oss.example.BotPlayer;
import org.xxdc.oss.example.Game;
import org.xxdc.oss.example.PlayerNode;
import org.xxdc.oss.example.bot.BotStrategy;

/**
 * Plays one bot-versus-bot game with Alpha commentating, then writes a per-move record to
 * {@code build/episode-2-<mode>-window-<N>.csv}: prompt tokens, a count of Alpha's claims by
 * verdict with the reasons for any that failed, and whether Beta quoted its colour line exactly.
 */
@Configuration
public class AppConfiguration {

  Game newStandardGame() {
    return new Game(
        3,
        false,
        new PlayerNode.Local<>("X", new BotPlayer(BotStrategy.ALPHABETA)),
        new PlayerNode.Local<>("O", new BotPlayer(BotStrategy.MCTS)));
  }

  @Bean
  CommandLineRunner playOneGame(
      AlphaCommentaryPersona alpha,
      @Value("${alpha.memory.max-messages:20}") int window,
      @Value("${alpha.play-on-startup:true}") boolean play,
      @Value("${commentary.mode:duo}") String mode) {
    return _ -> {
      if (!play) {
        return;
      }
      try (var game = newStandardGame()) {
        var broadcast = alpha.broadcast(game);
        game.playWithAction(broadcast::onMove);
        var summary = broadcast.postGame(game);

        var rows = new ArrayList<>(broadcast.moves());
        rows.add(summary);
        write(Path.of("build", "episode-2-" + mode + "-window-" + window + ".csv"), rows);
      }
    };
  }

  private static void write(Path path, List<AlphaCommentaryPersona.MoveCommentary> rows)
      throws IOException {
    var lines = new ArrayList<String>();
    lines.add(
        "move,from_model,prompt_tokens,claims,supported,contradicted,unsupported,unchecked,"
            + "problems,answer,beta_answer,beta_quote_verified");
    for (var r : rows) {
      var t = FactChecker.Tally.of(r.verdicts());
      lines.add(
          String.join(
              ",",
              String.valueOf(r.move()),
              String.valueOf(r.fromModel()),
              r.promptTokens() == null ? "" : r.promptTokens().toString(),
              String.valueOf(t.claims()),
              String.valueOf(t.supported()),
              String.valueOf(t.contradicted()),
              String.valueOf(t.unsupported()),
              String.valueOf(t.unchecked()),
              quote(String.join(" | ", t.problems())),
              quote(r.commentary().answer()),
              quote(r.colour().map(b -> b.commentary().answer()).orElse("")),
              r.colour().map(b -> String.valueOf(b.quoteVerified())).orElse("")));
    }
    Files.createDirectories(path.getParent());
    Files.write(path, lines);
  }

  private static String quote(String s) {
    return "\"" + (s == null ? "" : s.replace("\"", "\"\"")) + "\"";
  }
}
