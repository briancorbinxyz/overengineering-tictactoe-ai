package xyz.briancorbin.rags;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/** Loads the context without running anything, so it needs no Ollama and no checkout. */
@SpringBootTest(properties = "archive.run=none")
class AppTests {

  @Test
  void contextLoads() {}
}
