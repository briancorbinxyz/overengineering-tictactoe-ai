# Over-Engineering Tic-Tac-Toe with Spring AI

The companion code for the *RAGs to Riches with Spring AI* series. The game itself
lives in [overengineering-tictactoe](https://github.com/briancorbinxyz/overengineering-tictactoe),
which stays pure Java; this repository consumes its published `tictactoe-api`
artifact and adds the AI.

| Episode | What it adds |
|---|---|
| 1 | A commentator persona on Spring AI 1.0 and Spring Boot 3.5 |
| 2 | Alpha: commentary on every move, a memory per game, structured output, and a model-free check of its back-references. Spring AI 2.0.1, Spring Boot 4.1.1 |

## Run Episode 2

```bash
ollama pull mistral
ollama serve   # if it is not already running

./gradlew bootRun
# the same game shape with a six-message memory
./gradlew bootRun --args='--alpha.memory.max-messages=6'
```

Each run writes `build/alpha-episode-2-window-<N>.csv`: one row per move plus the
post-game summary, with prompt tokens and the citation check.

`./gradlew test` needs no model: the context test skips the game, and the other
tests do not start Spring.

## What is where

| File | What it does |
|---|---|
| `persona/alpha.md` | The system prompt: voice, truth rules, output format |
| `colour/quiet-moves.md` | Hand-written lines offered on quiet moves |
| `MoveReport` | The facts about one move, written as the user message |
| `AlphaCommentaryPersona` | Episode 1's decorator, plus a per-game `Broadcast` with memory |
| `CitationCheck` | Checks back-references against the game's history |
| `AlphaConfiguration` | `ChatClient`, memory window, temperature |
| `AppConfiguration` | Plays one game and writes the CSV |
