package org.xxdc.oss.example.tictactoe;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import org.xxdc.oss.example.GameState;

/**
 * Checks Alpha's claims against the game's own history, with no model involved.
 *
 * <p>For each claim it asks:
 *
 * <ol>
 *   <li>Does every move it mentions or cites exist, and come no later than this one?
 *   <li>Could Alpha see it? With a window of W messages, Alpha sees about the last W/2 move
 *       reports. A move older than that is a memory Alpha cannot have.
 *   <li>Is every earlier move it mentions also in its sources?
 *   <li>When it names one move and one player, is that the player who made the move?
 *   <li>When it says a player has won, does the board agree?
 * </ol>
 *
 * <p>It checks what can be checked cheaply and exactly, and says so when it cannot. A claim that
 * X "took the corner" on a move where X took the centre passes, because squares are not checked.
 * The win check is lexical: it looks for words like "wins" and skips sentences about blocking,
 * threats or what might happen, so an unusual phrasing can slip past it.
 */
public final class GameFactChecker implements FactChecker<GameFactChecker.Evidence> {

  private static final Pattern MOVE = Pattern.compile("(?i)\\bmove\\s+(\\d+)\\b");
  private static final Pattern WIN =
      Pattern.compile(
          "(?i)\\b(wins|won|win|winning|victory|victorious|three in a row"
              + "|complete[sd]? (?:a|the|its) (?:row|column|diagonal|line))\\b");
  /**
   * Words that turn a sentence about winning into something else, so it is not checked as a claim
   * that someone has won. Four families: stopping a win (blocks, prevents), a win that might come
   * (threatens, could, potentially), a win being worked towards (trying, setting up, aims), and a
   * win denied (not, never, fails). The guard trades recall for precision: "X wins, and O cannot
   * recover" is skipped too, because of "cannot".
   */
  private static final Pattern NOT_A_WIN_CLAIM =
      Pattern.compile(
          "(?i)\\b("
              // stopping a win
              + "block|blocks|blocked|blocking|stop|stops|stopped|prevent|prevents|prevented"
              + "|deny|denies|denied"
              // a win that might come
              + "|threat|threats|threatens|would|could|might|nearly|almost|chance"
              + "|potential|potentially|possible|possibly"
              // a win being worked towards
              + "|try|tries|tried|trying|attempt|attempts|attempting|aim|aims|aiming"
              + "|seek|seeks|seeking|hope|hopes|hoping|set up|sets up|setting up|towards?"
              // a win denied
              + "|not|never|fail|fails|failed|unable|cannot|can't|won't|isn't|wasn't"
              + "|no one|nobody|neither)\\b");

  /**
   * What the claims are checked against.
   *
   * @param history the game's states; index m is the board after move m, index 0 the empty board
   * @param currentMove the move being commented on, or the last move after the game
   * @param earliestVisibleMove the oldest move report still in Alpha's memory window
   */
  public record Evidence(List<GameState> history, int currentMove, int earliestVisibleMove) {

    public Evidence {
      history = List.copyOf(history);
    }

    List<String> players() {
      return history.getLast().playerMarkers();
    }

    /** Who made move n: players move in turn, starting with the first marker. */
    String playerOf(int move) {
      var players = players();
      return players.get((move - 1) % players.size());
    }
  }

  @Override
  public Verdict check(Claim claim, Evidence evidence) {
    var contradicted = new ArrayList<String>();
    var unsupported = new ArrayList<String>();
    int checksRun = 0;

    Set<Integer> mentioned = movesIn(claim.text());
    Set<Integer> cited = new TreeSet<>();
    for (String source : claim.sources()) {
      cited.addAll(movesIn(source));
    }
    Set<Integer> all = new TreeSet<>(mentioned);
    all.addAll(cited);

    for (int m : all) {
      checksRun++;
      if (m < 1 || m > evidence.currentMove()) {
        contradicted.add("move " + m + " has not been played");
      } else if (m < evidence.earliestVisibleMove()) {
        unsupported.add("move " + m + " is outside Alpha's memory window");
      }
    }
    for (int m : mentioned) {
      if (!cited.contains(m) && m != evidence.currentMove()) {
        unsupported.add("mentions move " + m + " without citing it");
      }
    }

    List<String> named = evidence.players().stream().filter(p -> names(claim.text(), p)).toList();
    // The move a claim is about: the one in its text, or, when the text names none, the one in
    // its sources. "O blocked an immediate loss" with sources ["move 4"] is about move 4.
    Set<Integer> about = mentioned.isEmpty() ? cited : mentioned;
    if (about.size() == 1 && named.size() == 1) {
      int m = about.iterator().next();
      if (m >= 1 && m <= evidence.currentMove()) {
        checksRun++;
        String actual = evidence.playerOf(m);
        if (!actual.equals(named.getFirst())) {
          contradicted.add(
              "move %d was %s's, not %s's".formatted(m, actual, named.getFirst()));
        }
      }
    }

    if (isWinClaim(claim.text()) && named.size() == 1) {
      int m = about.size() == 1 ? about.iterator().next() : evidence.currentMove();
      if (about.size() <= 1 && m >= 1 && m <= evidence.currentMove()) {
        checksRun++;
        GameState state = evidence.history().get(m);
        String player = named.getFirst();
        boolean won = state.lastPlayerHasChain() && state.lastPlayer().equals(player);
        if (!won) {
          contradicted.add("says %s has won, but after move %d nobody has".formatted(player, m));
        }
      }
    }

    if (!contradicted.isEmpty()) {
      return new Verdict(claim, Status.CONTRADICTED, String.join("; ", contradicted));
    }
    if (!unsupported.isEmpty()) {
      return new Verdict(claim, Status.UNSUPPORTED, String.join("; ", unsupported));
    }
    if (checksRun == 0) {
      return new Verdict(claim, Status.UNCHECKED, "nothing checkable against the game");
    }
    return new Verdict(claim, Status.SUPPORTED, "consistent with the game's history");
  }

  /** Also flags an aside that makes a checkable claim, since asides are never checked. */
  @Override
  public List<Verdict> checkAll(Commentary commentary, Evidence evidence) {
    var verdicts = new ArrayList<>(FactChecker.super.checkAll(commentary, evidence));
    String aside = commentary.aside();
    if (!movesIn(aside).isEmpty() || isWinClaim(aside)) {
      verdicts.add(
          new Verdict(
              new Claim(aside, List.of()),
              Status.UNSUPPORTED,
              "the aside makes a claim about the game, where nothing checks it"));
    }
    return List.copyOf(verdicts);
  }

  static boolean isWinClaim(String text) {
    return text != null && WIN.matcher(text).find() && !NOT_A_WIN_CLAIM.matcher(text).find();
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

  private static boolean names(String text, String marker) {
    return Pattern.compile("\\b" + Pattern.quote(marker) + "\\b").matcher(text).find();
  }
}
