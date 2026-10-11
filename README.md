# RAGs to Riches with Spring AI

The companion code for the *RAGs to Riches with Spring AI* series. Each episode
lives on its own branch, so you can check out exactly the code an article
describes and compare one episode with the next.

| Episode | Branch | What it adds | Stack |
|---|---|---|---|
| [1](https://briancorbinxyz.medium.com/rags-to-riches-with-spring-ai-episode-1-44d4f604b565) | [`episode-1`](../../tree/episode-1) | A commentator persona for over-engineered tic-tac-toe | Spring AI 1.0.2, Spring Boot 3.5.6 |
| 2 | [`episode-2`](../../tree/episode-2) | Alpha calls every move and Beta adds colour on quiet moves: a memory per commentator per game, structured output, and model-free fact checks of Alpha's claims and Beta's quotations. [Incident report](../episode-2/docs/episode-2-incident-report.md): seven rounds of measuring them | Spring AI 2.0.1, Spring Boot 4.1.1, Java 25 |
| 3 | `episode-3` (in progress) | Alpha and Beta move from tic-tac-toe to an archive of more than a million words: a deliberately naive RAG baseline, every answer traced back to its source, and a golden question set to measure later episodes against | Spring AI 2.0.1 |

Compare any two episodes on GitHub with
[`episode-1...episode-2`](../../compare/episode-1...episode-2).

Episodes 1 and 2 use the game from
[overengineering-tictactoe](https://github.com/briancorbinxyz/overengineering-tictactoe),
which stays pure Java; this repository consumes its published `tictactoe-api`
artifact and adds the AI. From Episode 3 the game is no longer needed.

Everything runs locally on [Ollama](https://ollama.com); no API keys.

## This branch: `episode-2-qwen`

Episode 2 exactly as published, except the model is `qwen3:8b` (with its thinking
mode off) instead of `mistral`. It exists to compare the two on the same game; it
is not an episode. The CSV file names include the model, so runs from both branches
can sit side by side in `build/`:

```bash
ollama pull qwen3:8b
./gradlew bootRun                     # build/episode-2-qwen3-8b-duo-window-20.csv
git checkout episode-2 && ./gradlew bootRun   # build/episode-2-mistral-duo-window-20.csv
```

## Run Episode 2

```bash
git checkout episode-2
ollama pull mistral
ollama serve   # if it is not already running

./gradlew bootRun
# the same game shape with a six-message memory
./gradlew bootRun --args='--alpha.memory.max-messages=6'
# Alpha alone, no Beta
./gradlew bootRun --args='--commentary.mode=solo'
# a game someone can win (AlphaBeta against MCTS nearly always draws)
./gradlew bootRun --args='--game.x-strategy=RANDOM'
# replay a game move for move, to compare models on the same game
# (every run logs its own moves in this form)
./gradlew bootRun --args='--game.moves=4,0,8,2,1,7,6,3,5'
```

Each run writes two files to `build/`, named `episode-2-<model>-<mode>-window-<N>`:

- `.csv`: one row per move plus the post-game summary, with prompt tokens, Alpha's
  claims counted by verdict (supported, contradicted, unsupported, unchecked) with
  the reason for each failure, the share of claims that had anything checkable in
  them, how many claims only echo the move report or repeat an earlier claim,
  whether a reply went over three claims, whether each aside repeats one already
  told, and for Beta whether it quoted its colour line exactly, stray sources and
  echoes (the log prints distinct counts for asides and claims);
- `.jsonl`: the same rows in full, with every prompt, claim and source.

[`docs/episode-2-incident-report.md`](docs/episode-2-incident-report.md) is the
full log of how the checks were measured and fixed over seven rounds, with the two
replay sequences and the commands to reproduce them.

A clean verdict sheet is only worth something if the echo count is low and the
checked share is high: a claim that reads the report back is always true and says
nothing, and a claim with nothing checkable in it is never wrong.

`./gradlew test` needs no model: the context test skips the game, and the other
tests do not start Spring.

## Episode 2: what is where

| File | What it does |
|---|---|
| `persona/alpha.md` | Alpha's system prompt: voice, truth rules, output format |
| `persona/beta.md` | Beta's system prompt |
| `colour/quiet-moves.md` | Hand-written lines offered on quiet moves |
| `MoveReport` | The facts about one move, written as the user message |
| `AlphaCommentaryPersona` | Episode 1's decorator, plus a per-game `Broadcast` with memory |
| `BetaColourCommentator` | Beta: colour on quiet moves, with its quotation checked against the file |
| `Claim`, `Commentary` | What Alpha says: an unchecked aside, and claims each with its own sources |
| `ColourCommentary` | What Beta says: a sentence of colour, the quoted line, and an optional reaction |
| `FactChecker` | Checks claims against evidence and returns a verdict for each |
| `GameFactChecker` | Checks Alpha's claims against the game's history: moves, players, squares, and claimed wins and lines |
| `BoardVocabulary` | The words for squares and lines ("the centre", "the top row") and the squares they mean |
| `QuoteChecker` | Checks Beta's quotation against the colour file, word for word |
| `EchoCheck` | Counts claims that only read the move report back |
| `AlphaConfiguration` | Both `ChatClient`s, memory window, temperatures, solo or duo |
| `AppConfiguration` | Plays one game and writes the CSV |
