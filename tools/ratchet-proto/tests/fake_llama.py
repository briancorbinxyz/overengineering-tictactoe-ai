"""A stand-in for llama-server, for offline tests: the endpoints, request and response shapes and
error bodies of llama.cpp's tools/server (master 7182ef7), with a toy tokenizer and toy models.

    python tests/fake_llama.py --kind embed --alias nomic-embed-text-v1.5-f16 --port 8090

Tokens are words and punctuation; ``<|endoftext|>`` and ``<|im_end|>`` are special tokens. An
embedding is a hashed bag of words; a rerank score is the word overlap of query and document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EOT, IM_END, BOS = 151643, 151645, 1
SPECIAL = {"<|endoftext|>": EOT, "<|im_end|>": IM_END}
_TOK = re.compile(r"<\|endoftext\|>|<\|im_end\|>|\w+|[^\w\s]")


def word_id(w: str) -> int:
    return 1000 + int(hashlib.md5(w.lower().encode()).hexdigest()[:6], 16) % 50000


class Fake:
    def __init__(self, kind="embed", alias="test-model", add_bos=False, add_eos=None, ubatch=64, n_ctx=128,
                 model_path="", dim=16, rerank="overlap", shuffle=False):
        self.kind, self.alias, self.add_bos, self.add_eos = kind, alias, add_bos, add_eos
        self.ubatch, self.n_ctx, self.model_path, self.dim = ubatch, n_ctx, model_path, dim
        self.rerank, self.shuffle = rerank, shuffle
        self.requests = []  # (path, body)

    def tokenize(self, text: str, add_special: bool, parse_special: bool = True) -> list:
        out = []
        for t in _TOK.findall(text):
            out.append(SPECIAL[t] if (parse_special and t in SPECIAL) else word_id(t))
        if add_special:
            if self.add_bos:
                out = [BOS] + out
            if self.add_eos == "eot":
                out.append(EOT)
            elif self.add_eos == "other":
                out.append(IM_END)
        return out

    def vector(self, text: str) -> list:
        v = [0.0] * self.dim
        for t in _TOK.findall(text.lower()):
            v[word_id(t) % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def too_large(self, n: int):
        if n > self.ubatch:
            return 500, {"error": {"code": 500, "type": "server_error", "message":
                                   f"input ({n} tokens) is too large to process. increase the physical batch size "
                                   f"(current batch size: {self.ubatch})"}}
        if n > self.n_ctx:
            return 400, {"error": {"code": 400, "type": "exceed_context_size_error", "message":
                                   f"input ({n} tokens) is larger than the max context size ({self.n_ctx} tokens). skipping"}}
        return None

    def handle(self, method: str, path: str, body: dict | None):
        self.requests.append((path, body))
        if path == "/health":
            return 200, {"status": "ok"}
        if path in ("/v1/models", "/models"):
            return 200, {"object": "list", "data": [{"id": self.alias, "aliases": [self.alias], "object": "model",
                                                     "meta": {"n_params": 1234, "size": 5678, "n_embd": self.dim,
                                                              "n_ctx_train": 2048}}]}
        if path == "/props":
            return 200, {"model_path": self.model_path, "build_info": "fake-0",
                         "default_generation_settings": {"n_ctx": self.n_ctx}, "total_slots": 1}
        if path == "/tokenize":
            return 200, {"tokens": self.tokenize(body["content"], body.get("add_special", False),
                                                 body.get("parse_special", True))}
        if path in ("/v1/embeddings", "/embeddings"):
            if self.kind != "embed":
                return 501, {"error": {"code": 501, "type": "not_supported_error", "message":
                                       "This server does not support embeddings. Start it with `--embeddings`"}}
            inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
            data = []
            for i, t in enumerate(inputs):
                err = self.too_large(len(self.tokenize(t, True)))
                if err:
                    return err
                data.append({"embedding": self.vector(t), "index": i, "object": "embedding"})
            if self.shuffle:
                data.reverse()
            return 200, {"model": body.get("model", self.alias), "object": "list", "data": data,
                         "usage": {"prompt_tokens": 0, "total_tokens": 0}}
        if path in ("/v1/rerank", "/rerank", "/reranking", "/v1/reranking"):
            if self.kind != "rerank":
                return 501, {"error": {"code": 501, "type": "not_supported_error", "message":
                                       "This server does not support reranking. Start it with `--reranking`"}}
            q, docs = body["query"], body["documents"]
            res = []
            qw = {t.lower() for t in _TOK.findall(q)}
            for i, d in enumerate(docs):
                err = self.too_large(len(self.tokenize(q, False)) + len(self.tokenize(d, False)) + 4)
                if err:
                    return err
                dw = [t.lower() for t in _TOK.findall(d)]
                s = sum(1 for t in dw if t in qw) / (1 + len(dw)) if self.rerank == "overlap" else 0.5
                res.append({"index": i, "relevance_score": None if self.rerank == "null" else s})
            res.sort(key=lambda r: -(r["relevance_score"] or 0))
            return 200, {"model": self.alias, "object": "list", "results": res[: body.get("top_n", len(res))],
                         "usage": {"prompt_tokens": 0, "total_tokens": 0}}
        return 404, {"error": {"code": 404, "type": "not_found_error", "message": "File Not Found"}}


def serve(fake: Fake, port: int = 0):
    """Start in a daemon thread; returns (server, url). Call server.shutdown() when done."""

    class H(BaseHTTPRequestHandler):
        def _go(self, method):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            code, out = fake.handle(method, self.path, body)
            raw = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="embed")
    ap.add_argument("--alias", required=True)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--add-eos", default=None, choices=[None, "eot", "other"])
    ap.add_argument("--ubatch", type=int, default=2048)
    ap.add_argument("--n-ctx", type=int, default=2048)
    ap.add_argument("--model-path", default="")
    a = ap.parse_args()
    s, url = serve(Fake(a.kind, a.alias, add_eos=a.add_eos, ubatch=a.ubatch, n_ctx=a.n_ctx,
                        model_path=a.model_path, dim=64), a.port)
    print(f"fake llama-server ({a.kind}, {a.alias}) at {url}", flush=True)
    threading.Event().wait()
