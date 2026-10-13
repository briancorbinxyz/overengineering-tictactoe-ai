package xyz.briancorbin.rags;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import xyz.briancorbin.rags.FactChecker.Status;

class QuoteResolverTest {

  private final QuoteResolver resolver = new QuoteResolver();

  private static Document chunk(String source, int index, int total, String text) {
    return Document.builder()
        .text(text)
        .metadata(Map.of(Address.SOURCE, source, "chunk_index", index, "total_chunks", total, "title", "T"))
        .build();
  }

  private final List<Document> retrieved =
      List.of(
          chunk("specs/059-corpus-retrieval-scale/spec.html", 1, 3,
              "Requirements. Retrieval MUST NOT be built or activated while a corpus fits under the ~200k-token threshold; agentic search is the answer."),
          chunk("specs/051-knowledge-corpus/spec.html", 0, 2,
              "The corpus MUST NOT require a vector index or a runtime server to be usable — grep and glob are enough."));

  @Test
  void anExactQuotationIsTracedToItsChunk() {
    var claim = new Claim("No index below the threshold.",
        List.of("Retrieval MUST NOT be built or activated while a corpus fits under the ~200k-token threshold"));
    var v = resolver.check(claim, retrieved);
    assertEquals(Status.SUPPORTED, v.status());
    assertEquals("quoted from specs/059-corpus-retrieval-scale/spec.html, chunk 2 of 3", v.reason());
  }

  @Test
  void whitespaceTypographicDashesAndOnePairOfQuotesAreForgiven() {
    var claim = new Claim("x", List.of("\"require a vector   index or a runtime server to be usable - grep and glob\""));
    assertEquals(Status.SUPPORTED, resolver.check(claim, retrieved).status());
  }

  @Test
  void aParaphraseIsContradicted() {
    var claim = new Claim("x", List.of("Retrieval must never be built while the corpus is small"));
    var v = resolver.check(claim, retrieved);
    assertEquals(Status.CONTRADICTED, v.status());
    assertTrue(v.reason().startsWith("not word for word"));
  }

  @Test
  void aQuotationTooShortToTraceIsUnsupported() {
    var v = resolver.check(new Claim("x", List.of("MUST NOT")), retrieved);
    assertEquals(Status.UNSUPPORTED, v.status());
  }

  @Test
  void anInventedQuotationOutweighsAShortOneWhateverTheOrder() {
    var claim = new Claim("x", List.of("MUST NOT", "words that appear in no chunk whatsoever"));
    assertEquals(Status.CONTRADICTED, resolver.check(claim, retrieved).status());
  }

  @Test
  void aClaimWithNoQuotationIsUnchecked() {
    assertEquals(Status.UNCHECKED, resolver.check(new Claim("Nothing here answers it.", List.of()), retrieved).status());
  }

  @Test
  void onlySupportedClaimsBecomeLabelledQuotes() {
    var reply =
        new Commentary(
            "",
            List.of(
                new Claim("a", List.of("The corpus MUST NOT require a vector index")),
                new Claim("b", List.of("Retrieval MUST NOT be built or activated", "invented words that are nowhere at all")),
                new Claim("c", List.of("agentic search is the answer", "The corpus MUST NOT require a vector index"))));
    var resolution = resolver.resolve(reply, retrieved);
    assertEquals(
        List.of(Status.SUPPORTED, Status.CONTRADICTED, Status.SUPPORTED),
        resolution.verdicts().stream().map(FactChecker.Verdict::status).toList());
    // Claim b is dropped whole; the repeated quotation in c is one piece of evidence.
    assertEquals(List.of("Q1", "Q2"), resolution.quotes().stream().map(Quote::label).toList());
    assertEquals(2, resolution.quotes().get(0).rank());
    assertEquals(1, resolution.quotes().get(1).rank());
    assertEquals(2.0 / 3, resolution.verifiedShare(), 1e-9);
  }

  @Test
  void noQuotingClaimsMeansNoShare() {
    var reply = new Commentary("", List.of(new Claim("Nothing here answers it.", List.of())));
    assertNull(resolver.resolve(reply, retrieved).verifiedShare());
  }
}
