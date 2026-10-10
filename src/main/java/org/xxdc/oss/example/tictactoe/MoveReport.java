package org.xxdc.oss.example.tictactoe;

import java.util.Optional;
import org.xxdc.oss.example.GameState;
import org.xxdc.oss.example.analysis.StrategicTurningPoint;

/**
 * The facts about one move, written as the user message Alpha receives.
 *
 * <p>Episode 1 only spoke at strategic turning points because {@code CommentaryPersona} is only
 * ever called with one. A move report exists for every move, and carries the turning point when
 * there is one.
 */
public record MoveReport(
    int moveNumber,
    String player,
    int row,
    int column,
    Optional<StrategicTurningPoint> turningPoint,
    String board,
    Optional<String> result,
    Optional<String> colour) {

  /**
   * Builds the report for the move that turned {@code before} into {@code after}.
   *
   * @param before the state before the move
   * @param after the state after the move
   * @param moveNumber the number of the move, starting at 1
   * @param colour a line of colour to offer if the move is quiet
   */
  public static MoveReport of(
      GameState before, GameState after, int moveNumber, Optional<String> colour) {
    int d = after.board().dimension();
    var turningPoint = StrategicTurningPoint.from(before, after, moveNumber);
    var result = result(after);
    boolean quiet = turningPoint.isEmpty() && result.isEmpty();
    return new MoveReport(
        moveNumber,
        after.lastPlayer(),
        after.lastMove() / d + 1,
        after.lastMove() % d + 1,
        turningPoint,
        render(after),
        result,
        quiet ? colour : Optional.empty());
  }

  /** True when nothing strategic happened on this move. */
  public boolean quiet() {
    return turningPoint.isEmpty() && result.isEmpty();
  }

  /** The text sent to the model. Plain text, no template variables. */
  public String toPrompt() {
    var out = new StringBuilder();
    out.append("Move ")
        .append(moveNumber)
        .append(": ")
        .append(player)
        .append(" played row ")
        .append(row)
        .append(", column ")
        .append(column)
        .append(".\n");
    turningPoint.ifPresent(
        tp ->
            out.append("Turning point: ")
                .append(player)
                .append(' ')
                .append(describe(tp))
                .append(".\n"));
    result.ifPresent(r -> out.append("Result: ").append(r).append(".\n"));
    out.append("Board:\n").append(board);
    colour.ifPresent(c -> out.append("Colour you may use: ").append(c).append('\n'));
    return out.toString();
  }

  /** A factual line for when the model is unavailable. */
  public String plainLine() {
    var line = "Move %d: %s to row %d, column %d".formatted(moveNumber, player, row, column);
    if (turningPoint.isPresent()) {
      line += ", and " + player + " " + describe(turningPoint.get());
    }
    return line + ".";
  }

  static String describe(StrategicTurningPoint turningPoint) {
    return switch (turningPoint) {
      case StrategicTurningPoint.GameWon won -> "wins the game";
      case StrategicTurningPoint.CenterSquareControl centre -> "takes the centre square";
      case StrategicTurningPoint.ImmediateLossPrevention block -> "blocks an immediate loss";
    };
  }

  private static Optional<String> result(GameState state) {
    if (state.lastPlayerHasChain()) {
      return Optional.of(state.lastPlayer() + " wins");
    }
    if (!state.hasMovesAvailable()) {
      return Optional.of("draw, the board is full");
    }
    return Optional.empty();
  }

  /** A compact board, one row per line, "." for an empty square. */
  static String render(GameState state) {
    int d = state.board().dimension();
    String[] cells = state.board().content();
    var out = new StringBuilder();
    for (int r = 0; r < d; r++) {
      var row = new java.util.ArrayList<String>(d);
      for (int c = 0; c < d; c++) {
        String v = cells[r * d + c];
        row.add(v == null || v.isEmpty() ? "." : v);
      }
      out.append(String.join(" ", row)).append('\n');
    }
    return out.toString();
  }
}
