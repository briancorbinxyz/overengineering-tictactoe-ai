package org.xxdc.oss.example.tictactoe;

import org.springframework.ai.chat.client.ChatClient;
import org.xxdc.oss.example.analysis.StrategicTurningPoint;
import org.xxdc.oss.example.commentary.CommentaryPersona;

public class AiCommentaryPersona implements CommentaryPersona {

  private final CommentaryPersona delegate;

  private final ChatClient chatClient;

  public AiCommentaryPersona(CommentaryPersona delegate, ChatClient chatClient) {
    this.delegate = delegate;
    this.chatClient = chatClient;
  }

  @Override
  public String comment(StrategicTurningPoint strategicTurningPoint) {
    return chatClient.prompt(
            "Comment on the following strategic turning point " +
                "in a game of tic-tac-toe: " + delegate.comment(strategicTurningPoint))
        .call()
        .content();
  }
}
