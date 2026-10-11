# Colour for quiet moves
#
# One line is offered on each move that is not a strategic turning point: to Beta,
# or to Alpha when it commentates alone.
# Lines are used in order and never repeated within a game. This is deliberately
# not retrieval: the program picks the line, not the model. From Episode 3, Beta
# has to find its own.
# Every line here should be checkable; sources are in the article.

- Played perfectly by both sides, tic-tac-toe is always a draw.
- Counting every game until someone wins or the board fills, there are 255,168 possible games of 3x3 tic-tac-toe.
- Up to rotation and reflection, a game of 3x3 tic-tac-toe can finish on only 138 distinct boards.
- In 1952 A. S. Douglas wrote OXO, noughts and crosses for Cambridge's EDSAC computer, one of the earliest games played on a computer.
- In 1961 Donald Michie built MENACE, which learned noughts and crosses from 304 matchboxes of coloured beads.
- In Britain the game is called noughts and crosses.
- A fork is a move that creates two winning threats at once. The opponent can only block one.
- The classic rule-based strategy, in order: win, block, fork, block a fork, take the centre, take the opposite corner, take a corner, take a side.
- On a 3x3 board the centre square lies on four winning lines, a corner on three and a side square on two.
- Alpha-beta pruning gets the same answer as minimax while skipping branches that cannot change it.
- Monte Carlo tree search picks moves by playing many random games to the end and keeping score.
