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
 *   <li>When it says a player has won, does the board agree, and if it names the line, is it
 *       that line?
 *   <li>When it puts a player on a square ("X holds the centre"), does the player have a mark
 *       there?
 *   <li>Does every line it names exist? A "diagonal" from top-right to bottom-right is the right
 *       column.
 * </ol>
 *
 * <p>It checks what can be checked cheaply and exactly, and says so when it cannot. A claim that
 * X "took the corner" on a move where X took the centre still passes when X holds a corner from
 * earlier: the square check asks whether the player has a mark there, not when it was made.
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
   * that someone has won. Four families: stopping a win (blocks, preventing), a win that might come
   * (threatens, potential, a future win), a win being worked towards (aimed, trying, a setup), and
   * a win denied (not, without, too late).
   *
   * <p>Each verb is a stem with its endings, so a new inflection ("aimed", "preventing") does not
   * slip through. The guard trades recall for precision: "X wins, and O cannot recover" is
   * skipped too, because of "cannot".
   */
  private static final Pattern NOT_A_WIN_CLAIM =
      Pattern.compile(
          "(?i)\\b("
              // stopping a win
              + "block(?:s|ed|ing)?|stop(?:s|ped|ping)?|prevent(?:s|ed|ing)?"
              + "|den(?:y|ies|ied|ying)|thwart(?:s|ed|ing)?|foil(?:s|ed|ing)?"
              // a win that might come
              + "|threat(?:s|en|ens|ened|ening)?|would|could|might|nearly|almost|chances?"
              + "|potential(?:ly)?|possib(?:le|ly)|promis(?:e|es|ed|ing)|future|eventual(?:ly)?"
              // a win being worked towards
              + "|tr(?:y|ies|ied|ying)|attempt(?:s|ed|ing)?|aim(?:s|ed|ing)?|seek(?:s|ing)?|sought"
              + "|hop(?:e|es|ed|ing)|set(?:s|ting)? up|setups?|towards?"
              + "|chas(?:e|es|ed|ing)|pursu(?:e|es|ed|ing)"
              // a win denied
              + "|not|never|no|without|fail(?:s|ed|ing)?|unable|cannot|can't|won't|isn't|wasn't"
              + "|too late|short of|fell short|no one|nobody|neither)\\b");

  /**
   * What the claims are checked against.
   *
   * @param history the game's states; index m is the board after move m, index 0 the empty board
   * @param currentMove the move being commented on, or the last move after the game
   * @param earliestVisibleMove the oldest move report still in Alpha's memory window
   * @param summary true for the post-game summary, where there is no current move
   */
  public record Evidence(
      List<GameState> history, int currentMove, int earliestVisibleMove, boolean summary) {

    public Evidence {
      history = List.copyOf(history);
    }

    /** Evidence for commentary on a move during the game. */
    public Evidence(List<GameState> history, int currentMove, int earliestVisibleMove) {
      this(history, currentMove, earliestVisibleMove, false);
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
    // The move a claim is about is the one in its text. During the game, sources are not a
    // guide: models cite what a move responds to, so a claim about move 8 sourced to move 7 is
    // still about move 8. Only in the post-game summary, where there is no current move, does a
    // claim with no move in its text take the move from its sources: "O blocked an immediate
    // loss" with sources ["move 4"] is about move 4.
    Set<Integer> about = mentioned.isEmpty() && evidence.summary() ? cited : mentioned;
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

    // The move whose board the claim describes: the one it names, or the current one.
    int boardMove = about.size() == 1 ? about.iterator().next() : evidence.currentMove();
    boolean oneBoard = about.size() <= 1 && boardMove >= 1 && boardMove <= evidence.currentMove();
    var lines = BoardVocabulary.lines(claim.text());

    if (isWinClaim(claim.text()) && named.size() == 1 && oneBoard) {
      checksRun++;
      GameState state = evidence.history().get(boardMove);
      String player = named.getFirst();
      boolean won = state.lastPlayerHasChain() && state.lastPlayer().equals(player);
      if (!won) {
        contradicted.add(
            "says %s has won, but after move %d nobody has".formatted(player, boardMove));
      } else if (lines.size() == 1) {
        // A real win, but is it the line the claim names?
        var line = lines.getFirst();
        if (line.readings().stream().noneMatch(sq -> holdsAll(state, sq, player))) {
          contradicted.add("%s won, but not with %s".formatted(player, line.phrase()));
        }
      }
    }

    // A line that cannot exist is wrong whatever else the claim says, win or no win.
    for (String reason : BoardVocabulary.impossibleLines(claim.text())) {
      checksRun++;
      contradicted.add(reason);
    }

    var squares = BoardVocabulary.squares(claim.text());
    if (squares.size() == 1 && lines.isEmpty() && named.size() == 1 && oneBoard) {
      // Lenient on purpose: the claim holds if the player has a mark on any square the phrase
      // can mean, after that move. "X holds the centre" passes whether X took it now or earlier.
      checksRun++;
      GameState state = evidence.history().get(boardMove);
      var square = squares.getFirst();
      String player = named.getFirst();
      if (square.readings().getFirst().stream().noneMatch(i -> holds(state, i, player))) {
        contradicted.add(
            "after move %d, %s has no mark on %s".formatted(boardMove, player, square.phrase()));
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

  private static boolean holds(GameState state, int square, String player) {
    return player.equals(state.board().content()[square]);
  }

  private static boolean holdsAll(GameState state, Set<Integer> squares, String player) {
    return squares.stream().allMatch(i -> holds(state, i, player));
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
