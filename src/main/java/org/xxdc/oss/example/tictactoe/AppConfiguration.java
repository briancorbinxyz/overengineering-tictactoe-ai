package org.xxdc.oss.example.tictactoe;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.xxdc.oss.example.BotPlayer;
import org.xxdc.oss.example.Game;
import org.xxdc.oss.example.HumanPlayer;
import org.xxdc.oss.example.PlayerNode;
import org.xxdc.oss.example.bot.BotStrategy;
import org.xxdc.oss.example.commentary.CommentaryPersona;

import java.lang.invoke.MethodHandles;

import static org.xxdc.oss.example.analysis.Analyzers.strategicTurningPoints;

@Configuration
public class AppConfiguration {

  private static final Logger log = LoggerFactory.getLogger(
      MethodHandles.lookup().lookupClass()
  );

  private final CommentaryPersona commentaryPersona;

  @Autowired
  public AppConfiguration(CommentaryPersona persona) {
    this.commentaryPersona = persona;
  }

  @Bean
  Game newStandardGame() {
    return new Game(
        3,
        false,
        new PlayerNode.Local<>("X", new HumanPlayer()),
        new PlayerNode.Local<>("O", new BotPlayer(BotStrategy.ALPHABETA)));
  }

  @Bean
  public CommandLineRunner runner(Game game, ChatClient.Builder builder) {
    return _ -> game.playWithAction(this::logLiveCommentary);
  }

  private void logLiveCommentary(Game game) {
    game.history()
        .stream()
        .skip(game.moveNumber() - 1L) // latest move state changes only
        .gather(strategicTurningPoints())
        .map(commentaryPersona::comment)
        .forEach(l -> log.info("Commentator: \"{}\"", l));
  }
}
