package org.xxdc.oss.example.tictactoe;

import java.util.Optional;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.memory.ChatMemoryRepository;
import org.springframework.ai.chat.memory.MessageWindowChatMemory;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.xxdc.oss.example.commentary.EsportsLiveCommentaryPersona;

@Configuration
class AlphaConfiguration {

  /**
   * Spring AI auto-configures a 20-message window. Declaring our own lets the window size be a
   * property, so the same game can be replayed with less memory.
   */
  @Bean
  ChatMemory chatMemory(
      ChatMemoryRepository repository, @Value("${alpha.memory.max-messages:20}") int maxMessages) {
    return MessageWindowChatMemory.builder()
        .chatMemoryRepository(repository)
        .maxMessages(maxMessages)
        .build();
  }

  @Bean
  ChatClient alphaChatClient(
      ChatClient.Builder builder,
      ChatMemory chatMemory,
      @Value("classpath:persona/alpha.md") Resource persona) {
    return builder
        .defaultSystem(persona)
        // 2.0 takes a builder here, and no longer picks a temperature for you.
        .defaultOptions(ChatOptions.builder().temperature(0.4))
        .defaultAdvisors(MessageChatMemoryAdvisor.builder(chatMemory).build())
        .build();
  }

  /**
   * Beta, the colour commentator. Its own system prompt and a warmer temperature; it shares the
   * memory store with Alpha but always under its own conversation id.
   */
  @Bean
  ChatClient betaChatClient(
      ChatClient.Builder builder,
      ChatMemory chatMemory,
      @Value("classpath:persona/beta.md") Resource persona) {
    return builder
        .defaultSystem(persona)
        .defaultOptions(ChatOptions.builder().temperature(0.7))
        .defaultAdvisors(MessageChatMemoryAdvisor.builder(chatMemory).build())
        .build();
  }

  @Bean
  ColourLines colourLines(@Value("classpath:colour/quiet-moves.md") Resource colour) {
    return ColourLines.from(colour);
  }

  /**
   * {@code commentary.mode=duo} (the default) puts Beta in the booth for colour on quiet moves;
   * {@code solo} leaves Alpha alone, with the colour lines offered to Alpha instead.
   */
  @Bean
  AlphaCommentaryPersona alpha(
      @Qualifier("alphaChatClient") ChatClient alphaChatClient,
      @Qualifier("betaChatClient") ChatClient betaChatClient,
      ColourLines colourLines,
      @Value("${alpha.memory.max-messages:20}") int maxMessages,
      @Value("${commentary.mode:duo}") String mode) {
    Optional<BetaColourCommentator> beta =
        "solo".equalsIgnoreCase(mode)
            ? Optional.empty()
            : Optional.of(new BetaColourCommentator(betaChatClient, colourLines));
    return new AlphaCommentaryPersona(
        alphaChatClient, new EsportsLiveCommentaryPersona(), colourLines, maxMessages, beta);
  }
}
