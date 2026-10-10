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
 * {@code build/alpha-episode-2-window-<N>.csv}: prompt tokens, citations, and whether they held up.
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
      @Value("${alpha.play-on-startup:true}") boolean play) {
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
        write(Path.of("build", "alpha-episode-2-window-" + window + ".csv"), rows);
      }
    };
  }

  private static void write(Path path, List<AlphaCommentaryPersona.MoveCommentary> rows)
      throws IOException {
    var lines = new ArrayList<String>();
    lines.add(
        "move,from_model,prompt_tokens,mentioned,invalid,out_of_sight,uncited,player_checks,"
            + "player_correct,answer");
    for (var r : rows) {
      var c = r.check();
      lines.add(
          String.join(
              ",",
              String.valueOf(r.move()),
              String.valueOf(r.fromModel()),
              r.promptTokens() == null ? "" : r.promptTokens().toString(),
              quote(c.mentioned().toString()),
              quote(c.invalid().toString()),
              quote(c.outOfSight().toString()),
              quote(c.uncited().toString()),
              String.valueOf(c.playerChecks()),
              String.valueOf(c.playerCorrect()),
              quote(r.commentary().answer())));
    }
    Files.createDirectories(path.getParent());
    Files.write(path, lines);
  }

  private static String quote(String s) {
    return "\"" + (s == null ? "" : s.replace("\"", "\"\"")) + "\"";
  }
}
