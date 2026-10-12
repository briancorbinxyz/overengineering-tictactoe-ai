# Episode 2: incident report

*Seven rounds of fixing a model-free fact checker, in which the prompt fixes mostly
worked and the checker fixes kept inventing new ways to be wrong.*

This is the full log behind the short "Ship's Log: incident report" in
[Episode 2](../README.md). Every number comes from running this repository on
[Ollama](https://ollama.com), `mistral` on the `episode-2` branch and `qwen3:8b` on
`episode-2-qwen`, and auditing every flag by hand against the board.

| | |
|---|---|
| Runs measured | 62 |
| Rounds | 7 |
| Local models | 2 (`mistral`, `qwen3:8b`) |
| Share of flags that were real model errors | 46% in round 3, 89% in round 7 |
| Errors that survived every round | 1 |

## What was being measured

Episode 2 puts two commentators on a bot-versus-bot game of tic-tac-toe. Alpha
calls every move; Beta adds colour on quiet moves from a hand-written file. Both
reply as structured output, and both are checked by plain code with no model
involved: `GameFactChecker` against the game's own history, `QuoteChecker` against
the colour file.

The question each round was simple: when the checker says a claim is wrong, is it?
A flag is a *genuine* error when the board shows the model was wrong, and a *false
positive* when the claim was right and the checker misread it.

## How the checks work

The article describes `GameFactChecker`'s six questions. This is the detail behind
them, as of the last round (`353d4a9`).

**Which move a claim is about.** During the game, a claim is about the move named in
its text, or the current move if it names none. Its sources are not a guide: models
cite the move a move responds to, so a claim about move 8 sourced to move 7 is still
about move 8. Only in the post-game summary, where there is no current move, does a
claim with no move in its text take the move from its sources.

**Squares and lines.** `BoardVocabulary` maps phrases to squares, numbered 0 to 8
from the top left:

- corners: "the top-left corner", "a corner";
- edges: "the bottom edge", "bottom-middle", "bottom-centre", "centre-left";
- the centre: "the centre", "the center square", but not the "centre" inside
  "bottom-centre";
- "row R, column C", as the move reports say it;
- lines: "the top row", "the middle column", "the anti-diagonal", "the top-left to
  bottom-right diagonal", and two corners joined ("from top-right to bottom-right"),
  which name the row or column they share.

Lines are matched before squares, and each match is blanked before the next pattern
runs, so a diagonal is not also read as two corners. The square check is lenient on
purpose: a claim holds if the player has a mark on any square the phrase can mean,
after that move, so "X holds the centre" passes whether X took it now or earlier.

**Lines that cannot exist.** A "diagonal" between two corners that share a row or a
column, or a diagonal said to run along a row or a column, is contradicted whether or
not a win is claimed.

**Telling a claimed win from talk about winning.** A claim counts as a claimed win when
it uses a word such as "wins", "won", "victory" or "completes a line", and none of four
families of words that turn it into something else:

| Family | Examples |
|---|---|
| Stopping a win | block, stop, prevent, deny, thwart, foil, with every ending |
| A win that might come | threaten, would, could, might, almost, potential, promising, future, eventual |
| A win being worked towards | try, attempt, aim, seek, hope, set up, setup, towards, chase, pursue |
| A win denied | not, never, no, without, fail, unable, cannot, too late, short of, fell short |

Each verb is a stem with its endings (`prevent(?:s|ed|ing)?`), because listing word
forms one at a time missed a new inflection in four rounds running. The guard trades
recall for precision: "X wins, and O cannot recover" is skipped too, because of
"cannot".

**Asides.** Nothing checks an aside, so an aside that mentions a move number or a win
is flagged as unsupported: a fact must not hide in the joke.

**Echoes.** `EchoCheck` marks a claim as an echo when at least 80% of its words,
ignoring a short list of common words, already appear in the move report it was
given. Claims under three words never count. Beta's sentences are compared with the
move report only, so quoting its own colour line is not an echo.

**What each run records.** The CSV has one row per move, plus the post-game summary:

| Column | Meaning |
|---|---|
| `prompt_tokens` | As Ollama reports them; a validation retry adds its own usage |
| `claims`, `over_limit` | How many claims, and whether that broke the limit of three |
| `supported`, `contradicted`, `unsupported`, `unchecked` | Alpha's claims by verdict |
| `problems` | The checker's reason for each contradicted or unsupported claim |
| `checked_share` | The share of claims with anything checkable in them |
| `echoes`, `claim_repeats` | Claims that read the report back, or repeat an earlier claim |
| `aside`, `aside_repeat` | Alpha's joke, and whether it was already told this game |
| `beta_quote_verified`, `beta_stray_sources`, `beta_echoes`, `beta_aside_repeat` | The same questions for Beta |

The JSONL file holds the same rows in full, with every prompt, claim and source, and
the log prints the game's moves in the form `--game.moves` takes.

## The shape of it

| Round | Flags | Genuine model errors | Checker false positives | Share genuine |
|---|---:|---:|---:|---:|
| 3 | 13 | 6 | 7 | 46% |
| 4 | 33 | 2 | 31 | 6% |
| 5 | 12 | 8 | 4 | 67% |
| 6 | 10 | 7 | 3 | 70% |
| 7 | 9 | 8 | 1 | 89% |

Warnings about asides are left out throughout; those fire by design when a joke
smuggles in a checkable claim. Rounds 1 and 2 used earlier versions of the reply
schema and are not comparable. Round 4's attribution flags were audited by pattern
rather than one at a time.

The total shrank while the genuine share grew: the checker got quieter and more
right at the same time.

## Round by round

Each round names the commit its changes landed in.

### Round 1: baseline

Six runs on the code as first written, before the claims design. The checker
validated move references and player attribution, and nothing else.

- **Found:** Alpha never referred back to an earlier move during a game, not once
  in six runs, so the per-game memory was tested only by the post-game summary. A
  side script scoring named squares against the board put `mistral` at 4 of 10
  correct; nothing in the harness could see it.
- **Found:** at move 8 of a drawn game, `qwen3:8b` announced "O has completed a
  diagonal from top-left to bottom-right, securing a win". The board read
  `XXO / OOX / X.O`; that diagonal is X, O, O. The post-game summary repeated it,
  "Turning point move 8: O secures a diagonal win", because the invented win had
  been saved to memory and sent back on every later call. The checker of the day
  saw none of it.

### Round 2: claims and fact checkers (`f502dec`)

The reply moved from one `answer` plus a flat citation list to a list of `Claim`s,
each with its own sources, and a `FactChecker` returning a verdict for each. A win
check compared claimed wins against the board.

- **Fixed:** the win check caught what prompted it, the invented diagonal win.
- **Broke:** both models collapsed into reading the move report back. Report-only
  phrasing went from 0 of 10 rows to 9 or 10 of 10 for `mistral`, and Alpha told
  no jokes at all in one run. The verdict sheet looked perfect because of it: 21
  supported, 0 contradicted, and no commentary.

### Round 3: commentary, not transcription (`7e8ad65`)

The prompts asked for commentary on air in each persona's voice and forbade reading
the report back. `EchoCheck` counted claims whose words were already in the report,
so a clean verdict sheet had to be earned.

- **Fixed:** echoes fell to 0 across all ten runs, asides came back at 5 to 10 per
  run, and Beta's quotation was verified 3 of 3 everywhere.
- **Broke:** of twelve win flags, seven were hedged language read as a claim to
  have won: "potentially setting up a winning strategy", "is trying to complete a
  line", "not enough to win".

### Round 4: guards, caps and positive statements (`4d635d2`, `593ba46`)

The hedge guard grew four families of words. The limit of three claims moved into
the JSON schema. `MoveReport` began always writing `Turning point:` and `Result:`,
saying "none" rather than leaving the line out.

- **Fixed:** genuine invented wins went from five to zero. In drawn games `qwen3:8b`
  now said "completing the board without securing a win", which is right. The claim
  limit held in all ten runs, against replies of up to eight claims before.
- **Broke:** the share of genuine flags fell to 6%. A new rule, that a claim whose
  text names no move is about the move in its sources, produced 25 attribution
  false positives. And the shared schema's minimum of one claim pushed Beta to fill
  all three slots and to put labels in `sources`, breaking the quote check in three
  of five runs.

### Round 5: subjects, not antecedents (`3601888`)

Sources stopped standing in for a claim's subject during the game, keeping that only
for the post-game summary. Beta got its own `ColourCommentary` shape.
`BoardVocabulary` arrived, checking named squares and the line a win was made on.
`--game.moves` made exact replays possible.

- **Fixed:** attribution false positives went from 25 to 0. `BoardVocabulary`
  caught five genuine errors in its first outing, a class of error invisible for
  four rounds.
- **Remaining:** four win flags, each a word form the guard nearly covered.

### Round 6: repetition (no code change, `3601888`)

Twelve runs: three passes per model over two fixed move sequences, to find out how
much of the variation between runs came from the model and how much from chance.

- **Found:** eleven of twelve flagged errors appeared in exactly one pass of three.
  Counting contradictions per run had largely been counting noise. One error came
  back 3 of 3 times; see [the error that survived](#the-error-that-survived-every-round).
- **Found:** a bug in the vocabulary. A correct claim about the *bottom-centre*
  square was contradicted, because the pattern for "the centre" matched inside the
  compound.

### Round 7: compounds, stems and impossible lines (`353d4a9`)

Compound edge names resolve to their squares; each hedge family became word stems
with endings, so inflections could not be missed one at a time; and a line that
cannot exist is contradicted on its own.

- **Fixed:** 89% of flags were genuine. All three repaired families went silent.
  The impossible-line check caught its first real case, with a compound verdict:
  "says O has won, but after move 8 nobody has; calls top-right to bottom-right a
  diagonal, but those corners are the right column".

## Every checker mistake, and what caused it

Each one came from a reasonable-sounding assumption about how a model would use the
fields it was given.

| Seen | Fault | Cause | Fix |
|---|---|---|---|
| R2 | A perfect verdict sheet for commentary that said nothing | A fact checker rewards anything true, and nothing is truer than a copy of its own input | `EchoCheck`, so a clean sheet has to be earned |
| R3–R6 | Hedged talk about winning read as a claim to have won | A guard listing word forms one at a time; four rounds, four missed inflections (`aimed`, `preventing`, `setup`, "too late") | Each family as word stems with endings |
| R4 | 25 attribution flags, essentially all wrong | Sources assumed to name a claim's *subject*; models use them for *antecedents*, the move a move responds to | Text only during the game; sources stand in only in the summary |
| R4 | Beta's quotation unverifiable | A minimum of one claim on the `Commentary` shared with Alpha made Beta pad to three and put labels in `sources` | A separate `ColourCommentary` shape |
| R6 | A correct "bottom-centre" claim contradicted | The bare `centre` pattern matched inside the compound, and edge terms accepted only `middle` | Compound edge names, and a lookbehind on the bare form |
| R7 | One flag left: a post-game claim about a move the other player exploited | The summary still treats sources as the subject, and naming only the opponent is ordinary commentary | Open |

## The error that survived every round

One replayed sequence, `7,4,3,6,8,2`, is a game O wins on move 6. Its first move is
square 7, bottom-centre, and the report says so plainly:

```text
Move 1: X played row 3, column 2.
Turning point: none.
Result: none.
Board:
. . .
. . .
. X .
```

Across fifteen runs on that sequence, eight replies called it the centre:

```text
qwen3-8b  "X has claimed the center square, a strategic choice…"
qwen3-8b  "X has taken the center square, a strategic move…"
qwen3-8b  "X has secured the center, a strategic advantage…"
mistral   "X has taken the center position."
mistral   "X has taken the center square, a common opening move."
```

| Model | Runs on the sequence | Called it the centre | Rate |
|---|---:|---:|---:|
| `qwen3:8b` | 7 | 6 | 86% |
| `mistral` | 8 | 2 | 25% |

The runs that got it right suggested a tidy explanation. "Centre" names square 4 and
also means "the middle of" any line, so perhaps the models simply dropped a
qualifier: `mistral` got it right with "X playing in the center of the bottom row",
and `qwen3:8b` got it wrong with "X has secured the center". That explanation is
wrong, and the way it failed is the most useful thing in this report.

### Eight attempts to fix it

Each variant was run eight times against the real move-1 report on `qwen3:8b` at the
episode's temperature of 0.4. The right answer is the bottom-centre square.

| # | Intervention | Result |
|---|---|---|
| A | The current prompt, unchanged | asserted the centre 5/8 |
| B | The model chooses the square from a fixed list (a JSON-schema `enum`), before writing anything | chose `CENTRE` 8/8 |
| C | B, plus "write `{square}` where the square belongs" | placeholder used 0/8 |
| D | The report names it: "X played the bottom-centre square (row 3, column 2)" | name used 0/8 |
| E | D, plus "do not restate the coordinates" | name used 1/8 |
| F | E, plus the `enum` as a cross-check | enum still `CENTRE` 8/8 |
| G | "Never name a square, a row, a column or a diagonal" | named one anyway 7/8 |
| H | G, but lines allowed | named one anyway 8/8 |

Made to choose from a fixed list, the model chose the centre every time. Told the
answer outright in its own prompt, it would not use it. This is not a slip of the
tongue and not missing information: it is a prior strong enough to override the text
directly above it. One reply was half aware of the conflict: "a classic central
control play, though it's not quite the center square."

Ollama's structured output is constrained decoding: it masks any token that would
break the schema. Variant B shows its limit. The output is valid against the schema
and wrong. **Constrained decoding constrains structure, not truth.**

### The echo worry was unfounded

Putting the square's name in the report was held back for four rounds, on the theory
that handing the model a phrase invites it to copy. Across variants D to H,
`EchoCheck` flagged 0 of 80 claims. Given the name, the models still add meaning
("sets up potential for…", "limits immediate options"), so word overlap never
reaches the threshold. Round 2's collapse came from asking for claims with no
instruction about voice, not from facts being present in the report.

### Retry, or substitute?

A retry looked promising at first: the failed reply goes back as the assistant's
turn, the checker's verdict as the next user turn, with the same schema enforced on
the revision. With hand-written feedback that gave the coordinates, the right name
and the fact that the centre was empty, six of seven cases were corrected.

That number does not survive the feedback the system can actually give.
`GameFactChecker` says what is false, not what is true ("after move 1, X has no mark
on the centre"). On that alone, four retried cases produced one clean correction,
one unchanged reply, and two that swapped a wrong square for an overstated line:

```text
verdict only
  before  "X has established a central presence, which is a strategic advantage…"
  after   "X has placed a mark in row 3, column 2. This move does not affect the
           centre square."                              fixed, by transcribing

  before  "X has established a central presence…"
  after   "X has placed a mark in the central column. The central column is now
           occupied by X."                              new error: X holds 1 of 3
```

Pushed to be accurate about position, the model stops describing and copies the
coordinates: faithfulness bought by copying. A retry can introduce an error, so it
is not a safe automatic repair.

The safer option is deterministic substitution: when a claim is contradicted, do
not publish it, and send the program's own factual line in its place, through the
`Commentary.factual()` path that already exists for when the model cannot be
reached. **This is not implemented in the episode's code.** The checker reports
the error; it does not yet replace the claim.

A related improvement to `EchoCheck` is also open. It compares sets of words, which
measures coverage. Adding the longest copied run of words would separate *reusing
one supplied phrase* from *reading the report back*.

## What the replays changed

For the first four rounds the two models commentated different games, because MCTS
picks different moves each time, so any difference between them could have been the
model or the game. `--game.moves` replays a fixed sequence, and every run logs its
own moves in that form, so the same game can be put to both models.

That removed the game as a variable, and showed something larger underneath. The
same model on the same moves, three times:

| Round | Model, game | Metric | Pass 1 | Pass 2 | Pass 3 |
|---|---|---|---:|---:|---:|
| 6 | `qwen3:8b`, drawn | supported | 20 | 10 | 10 |
| 6 | `mistral`, won | claims | 7 | 20 | 13 |
| 7 | `mistral`, drawn | claims | 30 | 22 | 22 |
| 7 | `qwen3:8b`, won | checked share | 1.00 | 0.43 | 0.93 |

Nearly every accuracy measure sits inside that spread, so with three passes a
difference of averages between the models says little. Two consequences:

- **A claim about speed was withdrawn.** In round 6, latency separated the models
  cleanly on both sequences; in round 7 it separated them on neither. `qwen3:8b` is
  faster on pooled averages, about 12 seconds against 18 per call, but that is a
  pooled claim, not a per-round one.
- **The useful unit is the individual error, not the run total.** Keying each flag
  by the checker's reason and counting the passes it appears in separates a property
  of the model from a property of the sample. In round 6 that left one error worth
  keeping out of twelve flags: the bottom-centre error above. The one measure that
  does separate the models on aggregate is repeated claims on the longer game:
  `mistral` repeated claims in all six passes across rounds 6 and 7, `qwen3:8b` in
  none.

## Still open

- **One false positive left.** The post-game summary still reads sources as the
  subject, so a claim that the other player exploited a move is scored as
  attributing the move to them.
- **Beta occasionally cites Alpha.** In two of six `mistral` runs in round 7, Beta
  quoted the colour line perfectly and put Alpha's sentence in its sources. The
  prompt forbids "a name or a label" there, and Alpha's sentence is neither.
- **Speed needs pooling.** Rounds 6 and 7 together give six passes per model and
  game, enough to settle it without new runs.
- **How often each error recurs should be an output of the run.** It can be computed
  from the JSONL files, which record every prompt, claim and source for exactly this
  purpose.
- **Precision and echo are one measurement.** Copying buys faithfulness for free, so
  a verdict sheet means something only next to the echo count.
- **The square and line vocabulary is where the bugs live.** Two of the checker's
  false-positive families came from it.
- **Substitution** of contradicted claims, described above.

## Reproduce it

The two sequences used for the replay rounds:

| Name | Moves | Game |
|---|---|---|
| `SEQ_DEF` | `0,4,1,2,6,3,5,8,7` | drawn, 9 moves |
| `SEQ_RND` | `7,4,3,6,8,2` | O wins on move 6, on the anti-diagonal |

```bash
ollama pull mistral
ollama pull qwen3:8b

# mistral
git checkout episode-2
./gradlew bootRun --args='--game.moves=0,4,1,2,6,3,5,8,7'
./gradlew bootRun --args='--game.moves=7,4,3,6,8,2'

# qwen3:8b
git checkout episode-2-qwen
./gradlew bootRun --args='--game.moves=0,4,1,2,6,3,5,8,7'
./gradlew bootRun --args='--game.moves=7,4,3,6,8,2'
```

Each run writes a CSV and a JSONL file to `build/`, named after the model, mode and
memory window; the README describes the columns. To reproduce an earlier round, check
out the commit named in its heading. Run three passes of each before comparing
anything.

The checker's behaviour on the errors quoted here is pinned by unit tests:
`GameFactCheckerTest`, `BoardVocabularyTest`, `QuoteCheckerTest`, `EchoCheckTest`
and `ColourCommentaryTest` replay the claims themselves, and need neither Ollama nor
Spring.

Every flag quoted in this report was audited against the board by hand. Two further
runs were discarded after a stale branch meant `--game.moves` was silently ignored
and the replay never happened.
