"""Pluggable embedders with an on-disk vector cache.

``--embedder`` values:

- ``ollama:nomic-embed-text:v1.5``: HTTP to Ollama's ``/api/embed``. Documents get nomic's
  ``search_document: `` prefix and questions ``search_query: ``, exactly as Episode 3's
  ``PrefixedEmbeddingModel`` sends them.
- ``ollama:qwen3-embedding:0.6b``: documents as they are; questions as
  ``Instruct: <task>\\nQuery:<question>`` with the task sentence from the Qwen3-Embedding model
  card's example ("Given a web search query, retrieve relevant passages that answer the query").
  The card recommends writing a task sentence per use case; this harness keeps the card's default
  so nothing is tuned on the golden set.
- ``ollama:<any other model>``: no prefixes.
- ``wordllama``: WordLlama ``l2_supercat`` 256-d, the static token-embedding model bundled in the
  ``wordllama`` wheel. A PROXY only: a bag of token vectors, not a contextual encoder.

Vectors are cached in ``<cache>/emb/<model>.sqlite``, keyed by the SHA-256 of the model id and
the exact text sent (prefix included), so a changed prefix or chunk is re-embedded.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

QWEN3_TASK = "Given a web search query, retrieve relevant passages that answer the query"


class Embedder:
    name = "?"
    model_id = "?"  # what the cache is keyed by
    provenance = ""

    def doc_text(self, t: str) -> str:
        return t

    def query_text(self, q: str) -> str:
        return q

    def _embed(self, texts: list) -> np.ndarray:
        raise NotImplementedError

    def attach_cache(self, cache_dir: Path):
        cache_dir = Path(cache_dir) / "emb"
        cache_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9.-]+", "_", self.model_id)
        self.db = sqlite3.connect(str(cache_dir / f"{slug}.sqlite"))
        self.db.execute("create table if not exists v (h text primary key, dim int, vec blob)")
        self.truncated = 0

    batch = 32

    def embed(self, texts: list, label: str = "") -> np.ndarray:
        batch = self.batch
        keys = [hashlib.sha256((self.model_id + "\0" + t).encode()).hexdigest() for t in texts]
        have = {}
        for i in range(0, len(keys), 500):
            part = keys[i : i + 500]
            q = "select h, dim, vec from v where h in (%s)" % ",".join("?" * len(part))
            for h, d, b in self.db.execute(q, part):
                have[h] = np.frombuffer(b, dtype="<f4", count=d)
        todo = [i for i, k in enumerate(keys) if k not in have]
        if todo:
            print(f"  embedding {len(todo)} {label} texts with {self.name} ({len(texts) - len(todo)} cached)", file=sys.stderr)
        for s in range(0, len(todo), batch):
            idx = todo[s : s + batch]
            vecs = self._embed([texts[i] for i in idx])
            rows = []
            for i, v in zip(idx, vecs):
                v = np.asarray(v, dtype="<f4")
                have[keys[i]] = v
                rows.append((keys[i], len(v), v.tobytes()))
            self.db.executemany("insert or replace into v values (?,?,?)", rows)
            self.db.commit()
            if len(todo) > batch and (s // batch) % 20 == 0:
                print(f"    {min(s + batch, len(todo))}/{len(todo)}", file=sys.stderr)
        m = np.stack([have[k] for k in keys]).astype(np.float32)
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return m / norms

    def embed_docs(self, texts):
        return self.embed([self.doc_text(t) for t in texts], label="document")

    def embed_queries(self, texts):
        return self.embed([self.query_text(t) for t in texts], label="query")


class OllamaEmbedder(Embedder):
    def __init__(self, model: str, url: str = "http://localhost:11434"):
        self.model = model
        self.url = url.rstrip("/")
        self.name = f"ollama:{model}"
        self.digest = self._digest()
        self.model_id = f"ollama:{model}@{self.digest[:12]}"
        self.provenance = f"Ollama model {model}, digest {self.digest}"
        if model.startswith("nomic-embed-text"):
            self.doc_text = lambda t: "search_document: " + t
            self.query_text = lambda q: "search_query: " + q
        elif model.startswith("qwen3-embedding"):
            self.query_text = lambda q: f"Instruct: {QWEN3_TASK}\nQuery:{q}"

    def _post(self, path, body):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())

    def _digest(self) -> str:
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=10) as r:
                tags = json.loads(r.read())
        except OSError as e:
            raise SystemExit(f"Ollama is not reachable at {self.url}: {e}. Start it with `ollama serve`.")
        for m in tags.get("models", []):
            if m.get("name") == self.model or m.get("model") == self.model:
                return m.get("digest", "unknown")
        raise SystemExit(f"Ollama has no model {self.model}. Run: ollama pull {self.model}")

    def _embed(self, texts):
        try:
            return self._post("/api/embed", {"model": self.model, "input": texts, "truncate": False})["embeddings"]
        except urllib.error.HTTPError:
            if len(texts) > 1:
                return [self._embed([t])[0] for t in texts]
            # one text longer than the model's window: embed its head and count it
            self.truncated += 1
            return self._post("/api/embed", {"model": self.model, "input": texts, "truncate": True})["embeddings"]


class WordLlamaEmbedder(Embedder):
    """PROXY: WordLlama l2_supercat, 256-d, loaded from the files inside the installed wheel."""

    batch = 256

    def __init__(self):
        try:
            import wordllama
            from wordllama import WordLlama
            from wordllama.inference import WordLlamaInference
            from safetensors import safe_open
        except ImportError:
            raise SystemExit("wordllama is not installed: pip install wordllama")
        base = Path(wordllama.__file__).parent
        tok = WordLlama.load_tokenizer(base / "tokenizers" / "l2_supercat_tokenizer_config.json")
        wpath = base / "weights" / "l2_supercat_256.safetensors"
        with safe_open(str(wpath), framework="np", device="cpu") as f:
            emb = f.get_tensor("embedding.weight")
        self.wl = WordLlamaInference(emb, tok)
        ver = getattr(wordllama, "__version__", "?")
        sha = hashlib.sha256(wpath.read_bytes()).hexdigest()
        self.name = "wordllama"
        self.model_id = f"wordllama:l2_supercat_256@{ver}:{sha[:12]}"
        self.provenance = f"wordllama {ver}, l2_supercat_256.safetensors sha256 {sha} (bundled in the wheel; PROXY)"

    def _embed(self, texts):
        return self.wl.embed(texts, norm=True)


def make(spec: str, ollama_url: str) -> Embedder:
    if spec == "wordllama":
        return WordLlamaEmbedder()
    if spec.startswith("ollama:"):
        return OllamaEmbedder(spec[len("ollama:"):], ollama_url)
    raise SystemExit(f"unknown embedder {spec!r}: use ollama:<model> or wordllama")
