package xyz.briancorbin.rags;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.jsoup.Jsoup;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import xyz.briancorbin.rags.GoldenScorer.Hit;

class GoldenScorerTest {

  private static final Path ROOT = Path.of("src/test/resources/fixtures");
  private static final String FILE = "specs/001-demo/spec.html";
  private final GoldenScorer scorer = new GoldenScorer(ROOT);

  /** The page text exactly as the archive reads it. */
  private static String page() throws Exception {
    return Jsoup.parse(Files.readString(ROOT.resolve(FILE))).body().text();
  }

  private static Document chunk(String source, String text) {
    return Document.builder().text(text).metadata(Map.of(Address.SOURCE, source, "chunk_index", 0, "total_chunks", 1)).build();
  }

  @Test
  void aChunkHoldingTheWholeElementIsAHit() throws Exception {
    String text = page();
    assertEquals(Hit.FULL, scorer.hit(FILE + "#FR-001", chunk(FILE, text)));
  }

  @Test
  void aChunkHoldingHalfOrMoreIsAPartialHit() throws Exception {
    String text = page();
    String element = scorer.elementText(FILE + "#FR-001").orElseThrow();
    int start = text.indexOf(element);
    // The chunk boundary falls a third of the way into the requirement.
    String cut = text.substring(start + element.length() / 3);
    assertEquals(Hit.PARTIAL, scorer.hit(FILE + "#FR-001", chunk(FILE, cut)));
  }

  @Test
  void aChunkHoldingLessThanHalfIsAMiss() throws Exception {
    String text = page();
    String element = scorer.elementText(FILE + "#FR-001").orElseThrow();
    int start = text.indexOf(element);
    String cut = text.substring(0, start + element.length() / 4);
    assertEquals(Hit.NONE, scorer.hit(FILE + "#FR-001", chunk(FILE, cut)));
  }

  @Test
  void aChunkFromAnotherFileIsAMissWhateverItSays() throws Exception {
    assertEquals(Hit.NONE, scorer.hit(FILE + "#FR-001", chunk("specs/002-other/spec.html", page())));
  }

  @Test
  void ranksCountFromOneAndAFullHitIsAlsoPartial() throws Exception {
    String text = page();
    var other = chunk("specs/002-other/spec.html", "unrelated");
    var score = scorer.score(List.of(FILE + "#FR-002"), List.of(other, chunk(FILE, text)));
    assertEquals(2, score.firstHit());
    assertEquals(2, score.firstPartial());
    assertEquals(0.5, score.reciprocalRank(), 1e-9);
    assertTrue(score.hitAt(4));
    assertFalse(score.hitAt(1));
  }

  @Test
  void aMissScoresZero() {
    var score = scorer.score(List.of(FILE + "#FR-001"), List.of(chunk(FILE, "nothing relevant")));
    assertNull(score.firstHit());
    assertEquals(0, score.reciprocalRank());
  }
}
