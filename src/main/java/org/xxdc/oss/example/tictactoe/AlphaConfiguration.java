package org.xxdc.oss.example.tictactoe;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.memory.ChatMemoryRepository;
import org.springframework.ai.chat.memory.MessageWindowChatMemory;
import org.springframework.ai.chat.prompt.ChatOptions;
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

  @Bean
  AlphaCommentaryPersona alpha(
      ChatClient alphaChatClient,
      @Value("classpath:colour/quiet-moves.md") Resource colour,
      @Value("${alpha.memory.max-messages:20}") int maxMessages) {
    return new AlphaCommentaryPersona(
        alphaChatClient, new EsportsLiveCommentaryPersona(), ColourLines.from(colour), maxMessages);
  }
}
