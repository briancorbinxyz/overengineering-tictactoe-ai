package xyz.briancorbin.rags;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class GoldenRunTest {

  @Test
  void percentilesUseTheNearestRank() {
    var sorted = List.of(100L, 200L, 300L, 400L, 500L, 600L, 700L, 800L, 900L, 1000L);
    assertEquals(500L, GoldenRun.percentile(sorted, 50));
    assertEquals(1000L, GoldenRun.percentile(sorted, 95));
    assertEquals(0L, GoldenRun.percentile(List.of(), 95));
  }

  @Test
  void anyPromptChangeChangesTheHash() {
    assertEquals(12, GoldenRun.hash(List.of("a", "b")).length());
    assertNotEquals(GoldenRun.hash(List.of("a", "b")), GoldenRun.hash(List.of("a", "c")));
  }
}
