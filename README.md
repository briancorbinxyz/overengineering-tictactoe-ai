# RAGs to Riches with Spring AI

The companion code for the *RAGs to Riches with Spring AI* series. Each episode
lives on its own branch, so you can check out exactly the code an article
describes and compare one episode with the next.

| Episode | Branch | What it adds | Stack |
|---|---|---|---|
| [1](https://briancorbinxyz.medium.com/rags-to-riches-with-spring-ai-episode-1-44d4f604b565) | [`episode-1`](../../tree/episode-1) | A commentator persona for over-engineered tic-tac-toe | Spring AI 1.0.2, Spring Boot 3.5.6 |
| 2 | [`episode-2`](../../tree/episode-2) | Alpha calls every move and Beta adds colour on quiet moves: a memory per commentator per game, structured output, and model-free fact checks of Alpha's claims and Beta's quotations | Spring AI 2.0.1, Spring Boot 4.1.1, Java 25 |
| 3 | `episode-3` (in progress) | Alpha and Beta move from tic-tac-toe to an archive of more than a million words: a deliberately naive RAG baseline, every answer traced back to its source, and a golden question set to measure later episodes against | Spring AI 2.0.1 |

Compare any two episodes on GitHub with
[`episode-1...episode-2`](../../compare/episode-1...episode-2).

Episodes 1 and 2 use the game from
[overengineering-tictactoe](https://github.com/briancorbinxyz/overengineering-tictactoe),
which stays pure Java; this repository consumes its published `tictactoe-api`
artifact and adds the AI. From Episode 3 the game is no longer needed.

Everything runs locally on [Ollama](https://ollama.com); no API keys.

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
```

Each run writes two files to `build/`, named `episode-2-<model>-<mode>-window-<N>`:

- `.csv`: one row per move plus the post-game summary, with prompt tokens, Alpha's
  claims counted by verdict (supported, contradicted, unsupported, unchecked) with
  the reason for each failure, how many claims only echo the move report, whether a
  reply went over three claims, whether Beta quoted its colour line exactly, and
  whether each aside repeats one already told in the game (the log prints a
  distinct-aside count per commentator);
- `.jsonl`: the same rows in full, with every prompt, claim and source.

A clean verdict sheet is only worth something if the echo count is low: a claim
that reads the report back is always true and says nothing.

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
| `Claim`, `Commentary` | What a commentator says: an unchecked aside, and claims each with its own sources |
| `FactChecker` | Checks claims against evidence and returns a verdict for each |
| `GameFactChecker` | Checks Alpha's claims against the game's history: moves, players, and claimed wins |
| `QuoteChecker` | Checks Beta's quotation against the colour file, word for word |
| `EchoCheck` | Counts claims that only read the move report back |
| `AlphaConfiguration` | Both `ChatClient`s, memory window, temperatures, solo or duo |
| `AppConfiguration` | Plays one game and writes the CSV |
