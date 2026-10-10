package org.xxdc.oss.example.tictactoe;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;

/**
 * Checks Alpha's back-references against the game's own history.
 *
 * <p>Three questions, all answerable without a model:
 *
 * <ol>
 *   <li>Does every move Alpha mentions or cites exist, and come before this one?
 *   <li>Could Alpha see it? With a window of W messages, Alpha sees roughly the last W/2 move
 *       reports. A citation older than that is a memory it cannot have.
 *   <li>When a sentence names a move and exactly one player, is that the player who made it?
 * </ol>
 *
 * <p>It does not check everything a sentence claims; it checks what can be checked cheaply and
 * exactly. That is enough to tell remembering from guessing.
 */
public final class CitationCheck {

  private static final Pattern MOVE = Pattern.compile("(?i)\\bmove\\s+(\\d+)\\b");
  private static final Pattern SENTENCE = Pattern.compile("(?<=[.!?])\\s+");

  /** The outcome for one reply. */
  public record Result(
      Set<Integer> mentioned,
      List<Integer> invalid,
      List<Integer> outOfSight,
      List<Integer> uncited,
      int playerChecks,
      int playerCorrect) {

    public boolean clean() {
      return invalid.isEmpty() && outOfSight.isEmpty() && playerCorrect == playerChecks;
    }
  }

  /**
   * @param commentary Alpha's reply
   * @param currentMove the move being commented on (or the last move, after the game)
   * @param earliestVisibleMove the oldest move report still in Alpha's memory window
   * @param players markers in playing order, e.g. ["X", "O"]
   */
  public static Result check(
      Commentary commentary, int currentMove, int earliestVisibleMove, List<String> players) {
    Set<Integer> mentioned = movesIn(commentary.answer());
    Set<Integer> cited = new TreeSet<>();
    for (String c : commentary.citations()) {
      cited.addAll(movesIn(c));
    }
    Set<Integer> all = new TreeSet<>(mentioned);
    all.addAll(cited);

    var invalid = new ArrayList<Integer>();
    var outOfSight = new ArrayList<Integer>();
    for (int m : all) {
      if (m < 1 || m > currentMove) {
        invalid.add(m);
      } else if (m < earliestVisibleMove) {
        outOfSight.add(m);
      }
    }
    var uncited = new ArrayList<Integer>();
    for (int m : mentioned) {
      if (!cited.contains(m) && m != currentMove) {
        uncited.add(m);
      }
    }

    int checks = 0;
    int correct = 0;
    for (String sentence : SENTENCE.split(commentary.answer())) {
      Set<Integer> moves = movesIn(sentence);
      List<String> named = players.stream().filter(p -> namesPlayer(sentence, p)).toList();
      if (moves.size() == 1 && named.size() == 1) {
        int m = moves.iterator().next();
        if (m >= 1 && m <= currentMove) {
          checks++;
          if (playerOf(m, players).equals(named.getFirst())) {
            correct++;
          }
        }
      }
    }
    return new Result(mentioned, invalid, outOfSight, uncited, checks, correct);
  }

  /** Who made move n, given that players move in turn starting with the first marker. */
  static String playerOf(int move, List<String> players) {
    return players.get((move - 1) % players.size());
  }

  static Set<Integer> movesIn(String text) {
    Set<Integer> moves = new TreeSet<>();
    if (text == null) {
      return moves;
    }
    var m = MOVE.matcher(text);
    while (m.find()) {
      moves.add(Integer.parseInt(m.group(1)));
    }
    return moves;
  }

  private static boolean namesPlayer(String sentence, String marker) {
    return Pattern.compile("\\b" + Pattern.quote(marker) + "\\b").matcher(sentence).find();
  }

  private CitationCheck() {}
}
