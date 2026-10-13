package xyz.briancorbin.rags;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;

class AddressTest {

  @Test
  void theSplittersZeroBasedIndexReadsFromOne() {
    var d =
        Document.builder()
            .text("x")
            .metadata(Map.of(Address.SOURCE, "specs/059/spec.html", "chunk_index", 0, "total_chunks", 7, "title", "Corpus"))
            .build();
    assertEquals(new Address("specs/059/spec.html", 1, 7, "Corpus"), Address.of(d));
    assertEquals("specs/059/spec.html, chunk 1 of 7", Address.of(d).toString());
  }

  @Test
  void numbersReloadedFromJsonMayBeAnyType() {
    var d =
        Document.builder()
            .text("x")
            .metadata(Map.of(Address.SOURCE, "a.html", "chunk_index", 2L, "total_chunks", 3.0))
            .build();
    assertEquals(new Address("a.html", 3, 3, ""), Address.of(d));
  }
}
