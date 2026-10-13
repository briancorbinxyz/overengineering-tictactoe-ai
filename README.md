# RAGs to Riches with Spring AI

The companion code for the *RAGs to Riches with Spring AI* series. Each episode
lives on its own branch, so you can check out exactly the code an article
describes and compare one episode with the next.

| Episode | Branch | What it adds | Stack |
|---|---|---|---|
| [1](https://briancorbinxyz.medium.com/rags-to-riches-with-spring-ai-episode-1-44d4f604b565) | [`episode-1`](../../tree/episode-1) | A commentator persona for over-engineered tic-tac-toe | Spring AI 1.0.2, Spring Boot 3.5.6 |
| 2 | [`episode-2`](../../tree/episode-2) | Alpha calls every move and Beta adds colour on quiet moves: a memory per commentator per game, structured output, and model-free fact checks of Alpha's claims and Beta's quotations. [Incident report](../episode-2/docs/episode-2-incident-report.md): seven rounds of measuring them | Spring AI 2.0.1, Spring Boot 4.1.1, Java 25 |
| 3 | [`episode-3`](../../tree/episode-3) (draft) | Alpha and Beta move from tic-tac-toe to spectastic's specifications, about a million words: a deliberately naive RAG baseline with Spring AI's defaults, every quotation traced back to its file and chunk in code, and a 50-question golden set that later episodes are measured against | Spring AI 2.0.1, Spring Boot 4.1.1, Java 25 |

Compare any two episodes on GitHub with
[`episode-1...episode-2`](../../compare/episode-1...episode-2).

Episodes 1 and 2 use the game from
[overengineering-tictactoe](https://github.com/briancorbinxyz/overengineering-tictactoe),
which stays pure Java; this repository consumes its published `tictactoe-api`
artifact and adds the AI. From Episode 3 the game is no longer needed.

Everything runs locally on [Ollama](https://ollama.com); no API keys.
Episodes 1 and 2 use `mistral`; from Episode 3 the chat model is `qwen3:8b`.

## Run Episode 3

You need [Ollama](https://ollama.com) 0.31.2 or later, two models, and spectastic's
specifications at the pinned tag, checked out next to this repository:

```bash
git checkout episode-3
ollama pull qwen3:8b
ollama pull nomic-embed-text:v1.5
git clone --depth 1 --branch v0.1.0-pre.28 https://github.com/spectastic/spectastic.git ../spectastic

# the embedding demo: a few sentences, and how alike each pair is
./gradlew bootRun --args='--archive.run=demo'
# build the archive once (minutes); later runs load build/archive/ instead
./gradlew bootRun --args='--archive.run=ingest'
# one question
./gradlew bootRun --args='--archive.run=ask --archive.question="Why will spectastic not build a search index for a small corpus?"'
# a conversation at the terminal; an empty line ends it
./gradlew bootRun --args='--archive.run=ask'
# the golden set: the baseline Episode 4 must beat
./gradlew bootRun
# the same with Alpha alone, searching and answering in one call
./gradlew bootRun --args='--archive.mode=solo'
```

The golden run writes three files to `build/`, named `episode-3-<model>-<mode>-k4`:

- `.csv`: one row per question: whether a retrieved chunk held the expected element
  whole (hit) or at least half of it (partial), the rank of the first of each, how
  many of Beta's quotations were traced word for word, Alpha's claims by verdict,
  whether Alpha abstained, whether a withdrawn or superseded record was presented as
  current, prompt tokens (which include any schema-validation retries) and time;
- `.jsonl`: the same in full, with every retrieved chunk, quotation and claim;
- `-summary.md`: the per-stratum table, ready to paste.

Every row records the spectastic commit, both model names and a hash of the prompts.
If any of them change, the numbers are a new baseline, not a comparison.

The golden set is in `src/main/resources/golden/questions.jsonl`; its format is
described in [`golden/README.md`](src/main/resources/golden/README.md).

`./gradlew test` needs no model and no checkout. With `../spectastic` present, one test
also checks that every golden-set address names a real element.

## Episode 3: what is where

| File | What it does |
|---|---|
| `SpecCorpus` | Extract, transform, load: reads every HTML file under `specs/`, stamps its address into the metadata, splits it into 800-token chunks and stores them; saves the store to `build/archive/` |
| `PrefixedEmbeddingModel` | Adds the `search_document:` and `search_query:` prefixes nomic-embed-text was trained with |
| `ArchiveConfiguration` | The vector store, and the two `ChatClient`s: Beta's with `QuestionAnswerAdvisor`, Alpha's without |
| `Archive` | One question: Beta searches and quotes, quotations are traced, Alpha answers from them |
| `QuoteResolver` | Finds each of Beta's quotations, word for word, in a retrieved chunk, and takes its address from that chunk |
| `CitationChecker` | Checks that Alpha cites only quotations it was given, by label |
| `Address`, `Quote` | Where a passage came from: file, chunk number, title |
| `GoldenSet`, `GoldenScorer`, `GoldenRun` | The questions, the hit and partial-hit rule, and the run that writes the baseline |
| `EmbeddingDemo` | Embeds six sentences and prints how alike each pair is |
| `persona/alpha.md`, `persona/beta.md`, `persona/alpha-solo.md` | The system prompts |
| `Claim`, `Commentary`, `FactChecker` | Unchanged from Episode 2 |

## Run Episode 2

(On the `episode-2` branch.)

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

(On the `episode-2` branch.)

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
