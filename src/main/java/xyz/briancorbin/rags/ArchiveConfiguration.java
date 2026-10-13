package xyz.briancorbin.rags;

import java.nio.file.Path;
import java.util.Locale;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.client.advisor.vectorstore.QuestionAnswerAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.ollama.OllamaEmbeddingModel;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.io.Resource;

/**
 * The archive's parts: the embedding model, the vector store, the corpus, and the two
 * commentators with their advisors.
 */
@Configuration
class ArchiveConfiguration {

  /**
   * Spring AI's Ollama embedding model with nomic's task prefixes added. Primary, so anything that
   * asks for an {@code EmbeddingModel} gets the prefixed one.
   */
  @Bean
  @Primary
  PrefixedEmbeddingModel nomicEmbeddingModel(OllamaEmbeddingModel ollama) {
    return new PrefixedEmbeddingModel(ollama);
  }

  /** In memory, exact search over every vector, saved to and loaded from a JSON file. */
  @Bean
  SimpleVectorStore archiveStore(PrefixedEmbeddingModel embeddingModel) {
    return SimpleVectorStore.builder(embeddingModel).build();
  }

  @Bean
  SpecCorpus specCorpus(
      SimpleVectorStore store,
      PrefixedEmbeddingModel embeddingModel,
      @Value("${spectastic.path}") Path checkout,
      @Value("${spectastic.commit:}") String commit,
      @Value("${spring.ai.ollama.embedding.model}") String model) {
    return new SpecCorpus(
        checkout, store, embeddingModel, model, commit, Path.of("build", "archive"));
  }

  /**
   * Beta finds things. Its {@link QuestionAnswerAdvisor} searches the store on every call and
   * pastes the top four chunks into the prompt. The memory advisor runs first, so it stores the
   * question as asked, not with four chunks pasted under it.
   */
  @Bean
  ChatClient betaChatClient(
      ChatClient.Builder builder,
      ChatMemory chatMemory,
      SimpleVectorStore store,
      @Value("classpath:persona/beta.md") Resource persona) {
    return builder
        .defaultSystem(persona)
        // Copying wants a cool head; Beta's personality lives in the aside.
        .defaultOptions(ChatOptions.builder().temperature(0.3))
        .defaultAdvisors(
            MessageChatMemoryAdvisor.builder(chatMemory).build(),
            QuestionAnswerAdvisor.builder(store).build())
        .build();
  }

  /** Alpha answers. No retriever: Alpha sees only the quotations the program traced. */
  @Bean
  ChatClient alphaChatClient(
      ChatClient.Builder builder,
      ChatMemory chatMemory,
      @Value("classpath:persona/alpha.md") Resource persona) {
    return builder
        .defaultSystem(persona)
        .defaultOptions(ChatOptions.builder().temperature(0.4))
        .defaultAdvisors(MessageChatMemoryAdvisor.builder(chatMemory).build())
        .build();
  }

  /** Alpha alone, for {@code archive.mode=solo}: it searches, quotes and answers in one call. */
  @Bean
  ChatClient alphaSoloChatClient(
      ChatClient.Builder builder,
      ChatMemory chatMemory,
      SimpleVectorStore store,
      @Value("classpath:persona/alpha-solo.md") Resource persona) {
    return builder
        .defaultSystem(persona)
        .defaultOptions(ChatOptions.builder().temperature(0.3))
        .defaultAdvisors(
            MessageChatMemoryAdvisor.builder(chatMemory).build(),
            QuestionAnswerAdvisor.builder(store).build())
        .build();
  }

  @Bean
  QuoteResolver quoteResolver() {
    return new QuoteResolver();
  }

  @Bean
  CitationChecker citationChecker() {
    return new CitationChecker();
  }

  /** {@code archive.mode=duo} (the default): Beta finds, Alpha answers. {@code solo}: Alpha alone. */
  @Bean
  Archive archive(
      @Qualifier("betaChatClient") ChatClient beta,
      @Qualifier("alphaChatClient") ChatClient alpha,
      @Qualifier("alphaSoloChatClient") ChatClient alphaSolo,
      SimpleVectorStore store,
      QuoteResolver resolver,
      CitationChecker citations,
      @Value("${archive.mode:duo}") String mode) {
    return new Archive(
        beta,
        alpha,
        alphaSolo,
        store,
        resolver,
        citations,
        Archive.Mode.valueOf(mode.strip().toUpperCase(Locale.ROOT)));
  }
}
