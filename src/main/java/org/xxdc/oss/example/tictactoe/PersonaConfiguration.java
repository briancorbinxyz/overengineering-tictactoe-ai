package org.xxdc.oss.example.tictactoe;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.xxdc.oss.example.commentary.CommentaryPersona;
import org.xxdc.oss.example.commentary.DefaultLiveCommentaryPersona;

@Configuration
public class PersonaConfiguration {
  @Bean
  public CommentaryPersona commentaryPersona(ChatClient.Builder chatClient) {
    return new AiCommentaryPersona(
        new DefaultLiveCommentaryPersona(),
        chatClient.build()
    );
  }
}
