"""Episode 4 step 5: a cross-encoder over the top 50, through sentence-transformers.

``--reranker cross-encoder/ms-marco-MiniLM-L-6-v2`` loads the model from the Hugging Face hub
(or its local cache). Without sentence-transformers, or without the model, the reranker
configurations are skipped and the report says so. Pinned identifier hits are never reranked.
"""

from __future__ import annotations

import sys


class Reranker:
    def __init__(self, name: str, max_length: int = 512):
        from sentence_transformers import CrossEncoder

        self.name = name
        self.model = CrossEncoder(name, max_length=max_length)
        self.cache = {}

    def scores(self, query: str, passages: list) -> list:
        todo = [p for p in passages if (query, p) not in self.cache]
        if todo:
            out = self.model.predict([(query, p) for p in todo], batch_size=32, show_progress_bar=False)
            for p, s in zip(todo, out):
                self.cache[(query, p)] = float(s)
        return [self.cache[(query, p)] for p in passages]


def make(name: str | None):
    """(reranker or None, message)."""
    if not name or name == "none":
        return None, "no reranker requested"
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return None, f"reranker {name} skipped: sentence-transformers is not installed (pip install sentence-transformers)"
    try:
        return Reranker(name), f"reranker {name} via sentence-transformers"
    except Exception as e:  # no network, no cached model
        print(f"reranker {name} could not be loaded: {e}", file=sys.stderr)
        return None, f"reranker {name} skipped: could not be loaded ({type(e).__name__})"
