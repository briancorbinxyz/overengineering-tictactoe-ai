# Over-Engineering Tic-Tac-Toe with Spring AI

The companion code for the *RAGs to Riches with Spring AI* series. The game itself
lives in [overengineering-tictactoe](https://github.com/briancorbinxyz/overengineering-tictactoe),
which stays pure Java; this repository consumes its published `tictactoe-api`
artifact and adds the AI.

| Episode | What it adds |
|---|---|
| 1 | A commentator persona on Spring AI 1.0 and Spring Boot 3.5 |
| 2 | Alpha calls every move and Beta adds colour on quiet moves: a memory per commentator per game, structured output, and model-free checks of Alpha's back-references and Beta's quotations. Spring AI 2.0.1, Spring Boot 4.1.1 |

## Run Episode 2

```bash
ollama pull mistral
ollama serve   # if it is not already running

./gradlew bootRun
# the same game shape with a six-message memory
./gradlew bootRun --args='--alpha.memory.max-messages=6'
# Alpha alone, no Beta
./gradlew bootRun --args='--commentary.mode=solo'
```

Each run writes `build/episode-2-<mode>-window-<N>.csv`: one row per move plus the
post-game summary, with prompt tokens, the citation check, and Beta's line with
whether it quoted its colour exactly.

`./gradlew test` needs no model: the context test skips the game, and the other
tests do not start Spring.

## What is where

| File | What it does |
|---|---|
| `persona/alpha.md` | Alpha's system prompt: voice, truth rules, output format |
| `persona/beta.md` | Beta's system prompt |
| `colour/quiet-moves.md` | Hand-written lines offered on quiet moves |
| `MoveReport` | The facts about one move, written as the user message |
| `AlphaCommentaryPersona` | Episode 1's decorator, plus a per-game `Broadcast` with memory |
| `BetaColourCommentator` | Beta: colour on quiet moves, with its quotation checked against the file |
| `CitationCheck` | Checks back-references against the game's history |
| `AlphaConfiguration` | Both `ChatClient`s, memory window, temperatures, solo or duo |
| `AppConfiguration` | Plays one game and writes the CSV |
