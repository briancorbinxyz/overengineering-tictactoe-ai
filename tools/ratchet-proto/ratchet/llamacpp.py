"""llama.cpp backends: the model lineup for the RTX 5090 runs, the llama-server flags for each
model, and a small HTTP client for the server's embeddings, rerank and tokenize endpoints.

Standard library only, so ``run_5090.ps1`` can ask for the plan before numpy is installed::

    python ratchet/llamacpp.py plan              # JSON: every run, its models and server flags
    python ratchet/llamacpp.py plan --runs nomic,qwen3-emb-8b
    python ratchet/llamacpp.py list              # the same, for people

What was checked, and where (see README, "Run on the RTX 5090"):

- Server flags, endpoints and error messages: llama.cpp ``tools/server`` and ``common/arg.cpp`` at
  master 7182ef7 (2026-10-16). ``/v1/embeddings`` tokenizes each input with special tokens added
  and parsed; it returns ``{"data": [{"embedding": [...], "index": i}], "usage": ...}``. An input
  that does not fit is refused, never cut: a non-causal model (BERT, XLM-R) needs the whole input
  in one physical batch (``-ub``), HTTP 500 "input (N tokens) is too large to process. increase
  the physical batch size"; any model needs it in the slot's context, HTTP 400
  ``exceed_context_size_error``. With ``--embedding`` the server sets ``-b`` to ``-ub``.
- ``/v1/rerank`` takes ``{"query", "documents", "top_n"}`` and returns ``{"results": [{"index",
  "relevance_score"}]}`` sorted by score. A GGUF with a ``rerank`` chat template (Qwen3-Reranker
  converted by a recent ``convert_hf_to_gguf.py``) is prompted through that template and scored
  as softmax(yes, no)[yes]; other rerankers get ``[BOS] query [EOS] [SEP] doc [EOS]``.
- Repositories, quants and sizes: each model's Hugging Face page (``sources`` below).
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import http.client
import json
import math
import os
import sys
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

QWEN3_TASK = "Given a web search query, retrieve relevant passages that answer the query"

LLAMA_SRC = "llama.cpp master 7182ef7 (2026-10-16): tools/server/server-context.cpp, server-common.cpp, common/arg.cpp"


@dataclass(frozen=True)
class Model:
    alias: str
    kind: str  # "embed" | "rerank"
    repo: str
    quant: str  # the -hf tag; llama.cpp matches it case-insensitively against the file name
    file: str  # the file that tag selects, from the repo's file listing
    size_gb: float  # download size, from the repo's file listing
    pooling: str  # mean | last | rank
    ctx: int = 2048  # per-slot context; the server gets -c ctx*parallel
    ubatch: int = 2048  # -ub and -b: at least the longest input, in this model's tokens
    parallel: int = 8  # -np
    query: str = "{text}"  # how a question is sent ({text} is the question)
    doc: str = "{text}"  # how a passage is sent
    eos: str | None = None  # a token every input must end with (last-token pooling reads it)
    sources: tuple = ()
    note: str = ""

    @property
    def hf(self) -> str:
        return f"{self.repo}:{self.quant}"

    def server_args(self, port: int, host: str = "127.0.0.1") -> list:
        args = ["-hf", self.hf, "-a", self.alias, "--host", host, "--port", str(port),
                "-ngl", "99", "-c", str(self.ctx * self.parallel), "-np", str(self.parallel),
                "-b", str(self.ubatch), "-ub", str(self.ubatch)]
        if self.kind == "embed":
            args += ["--embedding", "--pooling", self.pooling]
        else:
            args += ["--reranking"]
        return args

    def format_query(self, q: str) -> str:
        return self.query.replace("{text}", q)

    def format_doc(self, d: str) -> str:
        return self.doc.replace("{text}", d)


MODELS = {m.alias: m for m in [
    Model("nomic-embed-text-v1.5-f16", "embed", "nomic-ai/nomic-embed-text-v1.5-GGUF", "F16",
          "nomic-embed-text-v1.5.f16.gguf", 0.27, "mean", ctx=2048, ubatch=2048,
          query="search_query: {text}", doc="search_document: {text}",
          sources=("https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF",),
          note="2048-token native context (no YaRN extension); same prefixes as Episode 3"),
    Model("qwen3-embedding-8b-q8_0", "embed", "Qwen/Qwen3-Embedding-8B-GGUF", "Q8_0",
          "Qwen3-Embedding-8B-Q8_0.gguf", 8.05, "last",
          query="Instruct: " + QWEN3_TASK + "\nQuery:{text}", eos="<|endoftext|>",
          sources=("https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF",
                   "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
                   "https://huggingface.co/Qwen/Qwen3-Embedding-8B/discussions/1"),
          note="4096-d; last-token pooling on <|endoftext|>"),
    Model("qwen3-embedding-8b-f16", "embed", "Qwen/Qwen3-Embedding-8B-GGUF", "F16",
          "Qwen3-Embedding-8B-f16.gguf", 15.1, "last",
          query="Instruct: " + QWEN3_TASK + "\nQuery:{text}", eos="<|endoftext|>",
          sources=("https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF",),
          note="unquantised; 15.1 GB"),
    Model("qwen3-embedding-4b-q8_0", "embed", "Qwen/Qwen3-Embedding-4B-GGUF", "Q8_0",
          "(the Q8_0 file; name not checked)", 4.28, "last",
          query="Instruct: " + QWEN3_TASK + "\nQuery:{text}", eos="<|endoftext|>",
          sources=("https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF",),
          note="2560-d"),
    Model("bge-reranker-v2-m3-fp16", "rerank", "gpustack/bge-reranker-v2-m3-GGUF", "FP16",
          "bge-reranker-v2-m3-FP16.gguf", 1.16, "rank",
          sources=("https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF",),
          note="XLM-RoBERTa cross-encoder; scores are raw logits"),
    Model("qwen3-reranker-8b-q8_0", "rerank", "ethicalabs/Qwen3-Reranker-8B-GGUF", "Q8_0",
          "Qwen3-Reranker-8B.Q8_0.gguf", 8.05, "rank",
          sources=("https://huggingface.co/ethicalabs/Qwen3-Reranker-8B-GGUF",),
          note="third-party conversion that carries the rerank template and yes/no head; scores are "
               "P(yes); most other Qwen3-Reranker GGUFs lack them and score garbage, so the harness "
               "refuses a reranker that fails a sanity pair"),
]}


@dataclass(frozen=True)
class Run:
    name: str
    embedder: str
    reranker: str | None
    default: bool = True
    why: str = ""


RUNS = [
    Run("nomic", "nomic-embed-text-v1.5-f16", "bge-reranker-v2-m3-fp16",
        why="anchor: config A should give ~9/44 and Episode 3's top 4; S1-S4, X, H rows comparable with the Mac"),
    Run("qwen3-emb-8b", "qwen3-embedding-8b-q8_0", "bge-reranker-v2-m3-fp16",
        why="the main stronger-embedder test"),
    Run("qwen3-emb-8b-qwen3-rr", "qwen3-embedding-8b-q8_0", "qwen3-reranker-8b-q8_0",
        why="the same embedder with an LLM reranker"),
    Run("qwen3-emb-4b", "qwen3-embedding-4b-q8_0", "bge-reranker-v2-m3-fp16",
        why="is 8B needed, or does 4B tell the same story"),
    Run("qwen3-emb-8b-f16", "qwen3-embedding-8b-f16", "bge-reranker-v2-m3-fp16", default=False,
        why="optional: Q8_0 vs unquantised"),
]
RUN_BY_NAME = {r.name: r for r in RUNS}


def model(alias: str, kind: str | None = None) -> Model:
    if alias not in MODELS:
        raise SystemExit(f"unknown llama.cpp model alias {alias!r}; known: {', '.join(MODELS)} "
                         f"(add one to MODELS in ratchet/llamacpp.py, with its card's query/document format)")
    m = MODELS[alias]
    if kind and m.kind != kind:
        raise SystemExit(f"{alias} is a {m.kind} model, not a{'n' if kind == 'embed' else ''} {kind} model")
    return m


def plan(names: list | None, embed_port: int, rerank_port: int) -> list:
    if names:
        bad = [n for n in names if n not in RUN_BY_NAME]
        if bad:
            raise SystemExit(f"unknown run(s) {', '.join(bad)}; known: {', '.join(RUN_BY_NAME)}")
        runs = [RUN_BY_NAME[n] for n in names]
    else:
        runs = [r for r in RUNS if r.default]
    out = []
    for r in runs:
        e = model(r.embedder, "embed")
        x = model(r.reranker, "rerank") if r.reranker else None
        out.append({
            "name": r.name, "why": r.why,
            "embedder": {"alias": e.alias, "hf": e.hf, "file": e.file, "size_gb": e.size_gb, "port": embed_port,
                         "url": f"http://127.0.0.1:{embed_port}", "args": e.server_args(embed_port)},
            "reranker": None if x is None else {
                "alias": x.alias, "hf": x.hf, "file": x.file, "size_gb": x.size_gb, "port": rerank_port,
                "url": f"http://127.0.0.1:{rerank_port}", "args": x.server_args(rerank_port)},
            "gb": round(e.size_gb + (x.size_gb if x else 0), 2),
        })
    return out


# --- HTTP client -------------------------------------------------------------------------------

class ServerError(Exception):
    def __init__(self, status: int, message: str, kind: str = ""):
        super().__init__(f"HTTP {status}: {message}")
        self.status, self.message, self.kind = status, message, kind

    @property
    def too_long(self) -> bool:
        m = self.message.lower()
        return (self.kind == "exceed_context_size_error" or "too large to process" in m
                or "context size" in m or "max context" in m or "physical batch size" in m)


class Server:
    """JSON over HTTP/1.1 with one keep-alive connection per thread: tens of thousands of /tokenize
    calls would otherwise leave as many sockets in TIME_WAIT (Windows runs out of ephemeral ports)."""

    def __init__(self, url: str, timeout: float = 900):
        self.url = url.rstrip("/")
        self.timeout = timeout
        u = urllib.parse.urlsplit(self.url)
        self.host, self.port = u.hostname or "127.0.0.1", u.port or 80
        self.local = threading.local()

    def _conn(self, fresh: bool = False):
        c = getattr(self.local, "conn", None)
        if c is None or fresh:
            if c is not None:
                c.close()
            c = self.local.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        return c

    def _req(self, path: str, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        for attempt in (0, 1):
            c = self._conn(fresh=attempt > 0)
            try:
                c.request("GET" if data is None else "POST", path, body=data, headers=headers)
                r = c.getresponse()
                raw = r.read().decode("utf-8", "replace")
                break
            except (http.client.RemoteDisconnected, http.client.BadStatusLine, ConnectionResetError,
                    BrokenPipeError, ConnectionAbortedError):
                c.close()
                self.local.conn = None
                if attempt:
                    raise
        if r.status >= 400:
            try:
                err = json.loads(raw).get("error", {})
                msg, kind = err.get("message", raw), err.get("type", "")
            except (ValueError, AttributeError):
                msg, kind = raw, ""
            raise ServerError(r.status, msg, kind)
        return json.loads(raw)

    def get(self, path):
        return self._req(path)

    def post(self, path, body):
        return self._req(path, body)

    def reachable(self, what: str):
        try:
            self.get("/health")
        except ServerError as e:
            raise SystemExit(f"llama-server at {self.url} is not ready ({e}); {what}")
        except OSError as e:
            raise SystemExit(f"llama-server is not reachable at {self.url}: {e}. {what}")

    def model_info(self) -> dict:
        d = self.get("/v1/models")
        rows = d.get("data") or []
        return rows[0] if rows else {}

    def check_alias(self, alias: str):
        """Refuse to talk to a server that is not serving this alias (say, a chat model on another port)."""
        info = self.model_info()
        names = {info.get("id")} | set(info.get("aliases") or [])
        if alias not in names:
            raise SystemExit(f"llama-server at {self.url} serves {sorted(n for n in names if n)}, not {alias!r}. "
                             f"Start it with: llama-server {' '.join(MODELS[alias].server_args(port_of(self.url)))}")

    def props(self) -> dict:
        try:
            return self.get("/props")
        except ServerError:
            return {}

    def tokenize(self, text: str, add_special: bool) -> list:
        toks = self.post("/tokenize", {"content": text, "add_special": add_special, "parse_special": True})["tokens"]
        return [t["id"] if isinstance(t, dict) else t for t in toks]


def port_of(url: str) -> int:
    tail = url.rstrip("/").rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else 80


def file_sha256(path: str, cache_dir: Path | None) -> str:
    """SHA-256 of a GGUF, remembered by (path, size, mtime) so a 15 GB file is hashed once."""
    st = os.stat(path)
    key = f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}"
    side = Path(cache_dir) / "gguf-sha256.json" if cache_dir else None
    known = {}
    if side and side.exists():
        try:
            known = json.loads(side.read_text(encoding="utf-8"))
        except ValueError:
            known = {}
    if key in known:
        return known[key]
    print(f"  hashing {path} ({st.st_size / 1e9:.1f} GB, once)", file=sys.stderr)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 23), b""):
            h.update(block)
    known[key] = h.hexdigest()
    if side:
        side.parent.mkdir(parents=True, exist_ok=True)
        side.write_text(json.dumps(known, indent=1), encoding="utf-8")
    return known[key]


def gguf_identity(srv: Server, m: Model, cache_dir: Path | None) -> tuple:
    """(model_id for cache keys, provenance line). The id holds repo:quant, the GGUF's SHA-256 when
    the file the server loaded is readable here, and the pooling the vectors were made with."""
    props, info = srv.props(), srv.model_info()
    meta = info.get("meta") or {}
    path = props.get("model_path") or ""
    sha = None
    if path and os.path.isfile(path):
        sha = file_sha256(path, cache_dir)
    ident = f"sha256-{sha[:16]}" if sha else f"size{meta.get('size', '?')}-params{meta.get('n_params', '?')}"
    model_id = f"llamacpp:{m.hf}@{ident}:pool={m.pooling}"
    prov = (f"llama.cpp {m.hf} as `{m.alias}` (pooling {m.pooling}); file {path or '?'}; "
            f"sha256 {sha or 'not readable here, identified by size and parameter count'}; "
            f"{meta.get('n_params', '?')} params, n_embd {meta.get('n_embd', '?')}, n_ctx_train {meta.get('n_ctx_train', '?')}; "
            f"slot context {slot_ctx(props) or '?'}; server build {props.get('build_info', '?')}")
    return model_id, prov


def slot_ctx(props: dict) -> int | None:
    n = (props.get("default_generation_settings") or {}).get("n_ctx")
    return int(n) if n else None


def input_limit(srv: Server, m: Model) -> int:
    """The longest input the server will take whole: the physical batch, and the slot's context."""
    n = slot_ctx(srv.props())
    return min(m.ubatch, n) if n else m.ubatch


def eos_suffix(srv: Server, eos: str) -> tuple:
    """Make every input end with exactly one ``eos`` token, whatever the GGUF's add_eos flag says.

    Returns (text to append, how). The reference tokenizer appends it (Qwen3-Embedding's
    tokenizer.json TemplateProcessing); a GGUF may or may not carry ``add_eos_token``. Probed through
    ``/tokenize`` with the same add_special/parse_special the embeddings endpoint uses."""
    eos_ids = srv.tokenize(eos, add_special=False)
    if len(eos_ids) != 1:
        raise SystemExit(f"{eos} is not one special token in this GGUF's vocabulary ({eos_ids}); not guessing")
    probe = "Which spec owns the run budget?"
    plain = srv.tokenize(probe, add_special=False)
    full = srv.tokenize(probe, add_special=True)
    start = next((i for i in range(len(full) - len(plain) + 1) if full[i:i + len(plain)] == plain), None)
    if start is None:
        raise SystemExit(f"could not line up /tokenize output with and without special tokens: {plain} vs {full}")
    tail = full[start + len(plain):]
    if tail == eos_ids:
        return "", f"{eos} added by the GGUF's tokenizer (add_eos_token)"
    if tail:
        raise SystemExit(f"this GGUF appends token(s) {tail}, not {eos} ({eos_ids[0]}): last-token pooling would "
                         f"read the wrong token. Not guessing; use a GGUF whose tokenizer matches the model card.")
    check = srv.tokenize(probe + eos, add_special=True)
    if check[-1:] != eos_ids or (len(check) > 1 and check[-2:-1] == eos_ids):
        raise SystemExit(f"appending {eos} as text does not give exactly one trailing {eos} token: {check[-3:]}")
    return eos, f"{eos} appended by the harness (the GGUF does not add it)"


def count_tokens(srv: Server, texts: list, threads: int = 8) -> list:
    """Token counts as the embeddings endpoint will see them (special tokens added and parsed)."""
    with cf.ThreadPoolExecutor(threads) as ex:
        return list(ex.map(lambda t: len(srv.tokenize(t, add_special=True)), texts))


def too_long_exit(alias: str, detail: str):
    m = MODELS.get(alias)
    flags = f"-ub/-b {m.ubatch}, per-slot context {m.ctx}" if m else "?"
    raise SystemExit(f"{detail}\nNothing is truncated: raise `ubatch` (and `ctx`) for {alias} in "
                     f"ratchet/llamacpp.py (now {flags}) and restart its llama-server.")


def check_scores(scores: list, n: int, what: str) -> list:
    if len(scores) != n or any(s is None or not isinstance(s, (int, float)) or not math.isfinite(s) for s in scores):
        raise SystemExit(f"{what}: the server returned unusable scores ({scores[:5]}...). A GGUF converted without "
                         f"its rerank head scores null or garbage; use one listed in ratchet/llamacpp.py.")
    return scores


# --- CLI for run_5090.ps1 ----------------------------------------------------------------------

def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="llama.cpp model lineup and server flags for run_5090.ps1")
    ap.add_argument("cmd", choices=["plan", "list"])
    ap.add_argument("--runs", default="", help="comma-separated run names (default: the default lineup)")
    ap.add_argument("--embed-port", type=int, default=8090)
    ap.add_argument("--rerank-port", type=int, default=8091)
    a = ap.parse_args(argv)
    p = plan([x for x in a.runs.split(",") if x], a.embed_port, a.rerank_port)
    if a.cmd == "plan":
        print(json.dumps(p, indent=1))
        return
    for r in RUNS:
        mark = "default " if r.default else "optional"
        print(f"{r.name:24s} {mark} {r.embedder} + {r.reranker or 'no reranker'}  ({r.why})")
    print()
    for m in MODELS.values():
        print(f"{m.alias:28s} {m.kind:6s} {m.hf:46s} {m.size_gb:6.2f} GB  {m.file}")
    print()
    for r in p:
        for role in ("embedder", "reranker"):
            if r[role]:
                print(f"[{r['name']}] llama-server " + " ".join(r[role]["args"]))


if __name__ == "__main__":
    main()

