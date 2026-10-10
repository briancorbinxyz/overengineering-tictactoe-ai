package org.xxdc.oss.example.tictactoe;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/** Loads the context without playing a game, so it needs no running Ollama. */
@SpringBootTest(properties = "alpha.play-on-startup=false")
class AppTests {

  @Test
  void contextLoads() {}
}
