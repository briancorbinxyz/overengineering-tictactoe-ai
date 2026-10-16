#!/usr/bin/env bash
# The full ratchet run on a Mac: nomic-embed-text and qwen3-embedding through Ollama, with the
# MiniLM cross-encoder. Writes results/mac-<model>.md and .jsonl next to this script.
#
#   ollama pull nomic-embed-text:v1.5 && ollama pull qwen3-embedding:0.6b
#   tools/ratchet-proto/run_mac.sh                 # spectastic at ../spectastic (next to the repo)
#   SPECTASTIC=/path/to/spectastic tools/ratchet-proto/run_mac.sh
#   WITH_PROXY=1 tools/ratchet-proto/run_mac.sh    # also the WordLlama proxy, for comparison
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
SPECTASTIC="${SPECTASTIC:-$REPO/../spectastic}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
RERANKER="${RERANKER:-cross-encoder/ms-marco-MiniLM-L-6-v2}"
PINNED=c64d41c2e5d0d42c4fefd1b506cb083b9812bf6c

[ -d "$SPECTASTIC/specs" ] || {
  echo "No spectastic checkout at $SPECTASTIC. Clone it next to the repo:"
  echo "  git clone --depth 1 --branch v0.1.0-pre.28 https://github.com/spectastic/spectastic.git $REPO/../spectastic"
  exit 1
}
AT="$(git -C "$SPECTASTIC" rev-parse HEAD 2>/dev/null || echo unknown)"
[ "$AT" = "$PINNED" ] || echo "WARNING: spectastic is at $AT, not the pinned $PINNED: the numbers are a new baseline."

curl -sf "$OLLAMA_URL/api/tags" >/dev/null || { echo "Ollama is not answering at $OLLAMA_URL: start it (ollama serve)."; exit 1; }
for m in nomic-embed-text:v1.5 qwen3-embedding:0.6b; do
  curl -sf "$OLLAMA_URL/api/tags" | grep -q "\"$m\"" || { echo "Missing model: ollama pull $m"; exit 1; }
done

if [ ! -x "$HERE/.venv/bin/python" ]; then
  python3 -m venv "$HERE/.venv"
fi
PY="$HERE/.venv/bin/python"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q numpy tiktoken sentence-transformers
if [ "${WITH_PROXY:-0}" = 1 ]; then "$PY" -m pip install -q wordllama; fi

# SQLite must have FTS5 (python.org and Homebrew builds do)
"$PY" -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)')" \
  || { echo "This Python's SQLite has no FTS5. Use a python.org or Homebrew Python."; exit 1; }

"$PY" -m unittest discover -s "$HERE/tests"

run() {  # embedder, output name
  echo "== $1"
  "$PY" "$HERE/run.py" --spectastic "$SPECTASTIC" --embedder "$1" --reranker "$RERANKER" \
    --ollama-url "$OLLAMA_URL" --out "$HERE/results/$2"
}
run ollama:nomic-embed-text:v1.5 mac-nomic-embed-text
run ollama:qwen3-embedding:0.6b mac-qwen3-embedding
if [ "${WITH_PROXY:-0}" = 1 ]; then run wordllama mac-proxy-wordllama; fi

echo
echo "Done. Check first, in results/mac-nomic-embed-text.md:"
echo "  - config A (naive chunks, nomic) gives Hit@4 9/44 and its top 4 matches Episode 3's on (nearly) all 50 questions;"
echo "  - the reranker line says 'via sentence-transformers', not 'skipped'."
echo "Then read the main-line verdicts. Results:"
ls -1 "$HERE"/results/mac-*.md
