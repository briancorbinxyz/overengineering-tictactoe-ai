"""The llama.cpp embedder and reranker against a fake llama-server: request and response shapes,
per-model query/document formatting, the EOS rule, refusing over-long inputs, the cache key, and
the server flags run_5090.ps1 starts each model with."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from fake_llama import EOT, Fake, serve  # noqa: E402
from ratchet import embed as E  # noqa: E402
from ratchet import llamacpp as L  # noqa: E402
from ratchet import rerank as R  # noqa: E402

NOMIC = "nomic-embed-text-v1.5-f16"
QWEN = "qwen3-embedding-8b-q8_0"
BGE = "bge-reranker-v2-m3-fp16"
QRR = "qwen3-reranker-8b-q8_0"


class Base(unittest.TestCase):
    def start(self, **kw):
        self.fake = Fake(**kw)
        srv, url = serve(self.fake)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return url

    def sent(self, path):
        return [b for p, b in self.fake.requests if p == path]

    def embedder(self, alias, **kw):
        url = self.start(kind="embed", alias=alias, **kw)
        with contextlib.redirect_stderr(io.StringIO()):
            e = E.make(f"llamacpp:{alias}", "", url, Path(self.tmp.name))
        e.attach_cache(Path(self.tmp.name))
        self.addCleanup(e.db.close)
        return e

    def quiet(self, fn, *a):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a)


class Formatting(Base):
    def test_nomic_prefixes_reach_the_server(self):
        e = self.embedder(NOMIC)
        self.quiet(e.embed_docs, ["alpha beta"])
        self.quiet(e.embed_queries, ["what is alpha?"])
        inputs = [x for b in self.sent("/v1/embeddings") for x in b["input"]]
        self.assertEqual(["search_document: alpha beta", "search_query: what is alpha?"], inputs)

    def test_qwen3_query_instruct_and_plain_documents_with_eos_appended(self):
        e = self.embedder(QWEN, add_eos=None)  # GGUF without add_eos_token
        self.quiet(e.embed_docs, ["alpha beta"])
        self.quiet(e.embed_queries, ["what is alpha?"])
        inputs = [x for b in self.sent("/v1/embeddings") for x in b["input"]]
        self.assertEqual("alpha beta<|endoftext|>", inputs[0])
        self.assertEqual("Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
                         "Query:what is alpha?<|endoftext|>", inputs[1])
        for t in inputs:  # exactly one EOS, at the end, as the server tokenizes it
            toks = self.fake.tokenize(t, True)
            self.assertEqual(EOT, toks[-1])
            self.assertEqual(1, toks.count(EOT))
        self.assertIn("appended by the harness", e.provenance)

    def test_qwen3_eos_not_doubled_when_the_gguf_adds_it(self):
        e = self.embedder(QWEN, add_eos="eot")
        self.quiet(e.embed_docs, ["alpha beta"])
        self.assertEqual(["alpha beta"], self.sent("/v1/embeddings")[0]["input"])
        self.assertIn("added by the GGUF", e.provenance)

    def test_qwen3_refuses_a_gguf_that_appends_another_token(self):
        with self.assertRaises(SystemExit) as cm:
            self.embedder(QWEN, add_eos="other")
        self.assertIn("not guessing", str(cm.exception).lower())


class Shapes(Base):
    def test_vectors_follow_the_index_field_and_are_normalised(self):
        e = self.embedder(NOMIC, shuffle=True)
        texts = ["alpha", "beta gamma", "delta delta delta"]
        m = self.quiet(e.embed_docs, texts)
        self.assertEqual((3, 16), m.shape)
        for i, t in enumerate(texts):
            v = np.array(self.fake.vector("search_document: " + t))
            self.assertAlmostEqual(1.0, float(m[i] @ v / np.linalg.norm(v)), places=5)
        self.assertTrue(np.allclose(np.linalg.norm(m, axis=1), 1.0))

    def test_cached_vectors_are_not_requested_again(self):
        e = self.embedder(NOMIC)
        self.quiet(e.embed_docs, ["alpha", "beta"])
        n = len(self.sent("/v1/embeddings"))
        self.quiet(e.embed_docs, ["beta", "alpha"])
        self.assertEqual(n, len(self.sent("/v1/embeddings")))

    def test_alias_mismatch_is_refused(self):
        url = self.start(kind="embed", alias="qwen3.6-chat")
        with self.assertRaises(SystemExit) as cm:
            E.make(f"llamacpp:{NOMIC}", "", url, None)
        self.assertIn("not 'nomic-embed-text-v1.5-f16'", str(cm.exception))

    def test_unknown_alias_lists_the_known_ones(self):
        with self.assertRaises(SystemExit) as cm:
            L.model("no-such-model")
        self.assertIn(NOMIC, str(cm.exception))

    def test_a_reranker_alias_is_not_an_embedder(self):
        with self.assertRaises(SystemExit):
            L.model(BGE, "embed")


class NoTruncation(Base):
    def test_preflight_refuses_an_input_longer_than_the_limit(self):
        e = self.embedder(NOMIC, ubatch=4096, n_ctx=8)
        with self.assertRaises(SystemExit) as cm:
            self.quiet(e.embed_docs, ["short", " ".join(["word"] * 20)])
        msg = str(cm.exception)
        self.assertIn("longer than 8 tokens", msg)
        self.assertIn("Nothing is truncated", msg)
        self.assertEqual([], self.sent("/v1/embeddings"))

    def test_server_refusal_is_an_error_not_a_shorter_input(self):
        e = self.embedder(NOMIC, ubatch=8, n_ctx=64)
        e.check = lambda texts, label: None  # as if the preflight had missed it
        with self.assertRaises(SystemExit) as cm:
            self.quiet(e.embed_docs, [" ".join(["word"] * 20)])
        self.assertIn("too large to process", str(cm.exception))

    def test_slot_context_bounds_the_limit(self):
        e = self.embedder(NOMIC, ubatch=4096, n_ctx=100)
        self.assertEqual(100, e.limit)

    def test_server_error_flags_input_length(self):
        self.assertTrue(L.ServerError(400, "request (9 tokens) exceeds the available context size (8 tokens), try increasing it").too_long)
        self.assertTrue(L.ServerError(400, "x", "exceed_context_size_error").too_long)
        self.assertFalse(L.ServerError(500, "Loading model", "unavailable_error").too_long)


class Identity(Base):
    def test_model_id_holds_repo_quant_file_hash_and_pooling(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        gguf = Path(d.name) / "model.gguf"
        gguf.write_bytes(b"GGUF one")
        e = self.embedder(NOMIC, model_path=str(gguf))
        self.assertTrue(e.model_id.startswith("llamacpp:nomic-ai/nomic-embed-text-v1.5-GGUF:F16@sha256-"))
        self.assertTrue(e.model_id.endswith(":pool=mean"))
        import hashlib
        self.assertIn(hashlib.sha256(b"GGUF one").hexdigest()[:16], e.model_id)
        side = Path(self.tmp.name) / "gguf-sha256.json"
        self.assertTrue(side.exists())
        gguf.write_bytes(b"GGUF two, another file")
        self.assertNotEqual(self.quiet(L.file_sha256, str(gguf), Path(self.tmp.name)), hashlib.sha256(b"GGUF one").hexdigest())

    def test_unreadable_model_path_falls_back_to_size_and_params(self):
        e = self.embedder(NOMIC, model_path=os.path.join(tempfile.gettempdir(), "no-such-dir-ratchet", "missing.gguf"))
        self.assertIn("@size5678-params1234", e.model_id)


class Rerank(Base):
    def reranker(self, alias=BGE, **kw):
        url = self.start(kind="rerank", alias=alias, **kw)
        return R.make(f"llamacpp:{alias}", url, None)

    def test_scores_come_back_in_passage_order(self):
        rr, msg = self.reranker()
        q = "capital of France"
        docs = ["bananas are yellow", "the capital of France is Paris", "France"]
        s = rr.scores(q, docs)
        self.assertEqual(3, len(s))
        self.assertGreater(s[1], s[0])
        self.assertGreater(s[2], s[0])
        body = self.sent("/v1/rerank")[-1]
        self.assertEqual({"model", "query", "documents", "top_n"}, set(body))
        self.assertEqual(len(body["documents"]), body["top_n"])
        self.assertIn("sanity pair", msg)

    def test_cached_pairs_are_not_sent_again(self):
        rr, _ = self.reranker()
        rr.scores("q one", ["a b", "c d"])
        n = len(self.sent("/v1/rerank"))
        rr.scores("q one", ["c d", "a b", "a b"])
        self.assertEqual(n, len(self.sent("/v1/rerank")))

    def test_null_scores_stop_the_run(self):
        with self.assertRaises(SystemExit) as cm:
            self.reranker(alias=QRR, rerank="null")
        self.assertIn("unusable scores", str(cm.exception))

    def test_a_reranker_that_cannot_tell_relevant_from_irrelevant_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.reranker(alias=QRR, rerank="constant")
        self.assertIn("sanity pair", str(cm.exception))

    def test_too_long_pair_is_an_error(self):
        rr, _ = self.reranker(ubatch=40, n_ctx=200)
        with self.assertRaises(SystemExit) as cm:
            rr.scores("question", [" ".join(["word"] * 60)])
        self.assertIn("Nothing is truncated", str(cm.exception))

    def test_embedding_server_is_not_a_reranker(self):
        url = self.start(kind="embed", alias=BGE)
        with self.assertRaises(L.ServerError):
            R.make(f"llamacpp:{BGE}", url, None)


class Plan(unittest.TestCase):
    def test_every_model_is_started_whole_on_the_gpu_with_batch_at_least_the_longest_input(self):
        for m in L.MODELS.values():
            a = m.server_args(8090)
            self.assertEqual("99", a[a.index("-ngl") + 1], m.alias)
            self.assertEqual(a[a.index("-b") + 1], a[a.index("-ub") + 1])
            self.assertGreaterEqual(m.ubatch, 1200, m.alias)  # longest input: 801 cl100k tokens, with margin
            self.assertEqual(m.ctx * m.parallel, int(a[a.index("-c") + 1]))
            self.assertEqual(f"{m.repo}:{m.quant}", a[a.index("-hf") + 1])
            self.assertEqual(m.alias, a[a.index("-a") + 1])
            if m.kind == "embed":
                self.assertEqual(m.pooling, a[a.index("--pooling") + 1])
                self.assertNotIn("--reranking", a)
            else:
                self.assertIn("--reranking", a)
                self.assertNotIn("--embedding", a)

    def test_qwen3_embedders_pool_last_and_end_with_eos(self):
        for m in L.MODELS.values():
            if m.alias.startswith("qwen3-embedding"):
                self.assertEqual("last", m.pooling)
                self.assertEqual("<|endoftext|>", m.eos)
                self.assertEqual("{text}", m.doc)
                self.assertTrue(m.query.startswith("Instruct: ") and m.query.endswith("\nQuery:{text}"))

    def test_plan_uses_its_own_ports_and_known_models(self):
        p = L.plan(None, 8090, 8091)
        self.assertTrue(p)
        for r in p:
            self.assertIn("8090", r["embedder"]["args"])
            if r["reranker"]:
                self.assertIn("8091", r["reranker"]["args"])
        with self.assertRaises(SystemExit):
            L.plan(["nope"], 8090, 8091)

    def test_plan_cli_prints_json(self):
        import json
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            L.main(["plan", "--runs", "nomic"])
        self.assertEqual("nomic", json.loads(buf.getvalue())[0]["name"])


if __name__ == "__main__":
    unittest.main()
