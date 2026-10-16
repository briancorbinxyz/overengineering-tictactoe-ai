"""cl100k_base, the tokenizer Spring AI's TokenTextSplitter uses (through jtokkit).

``tiktoken`` downloads the rank file from openaipublic.blob.core.windows.net on first use and
caches it. Offline, pass a local copy with ``--cl100k-file`` (jtokkit's jar bundles the same
file as ``com/knuddels/jtokkit/cl100k_base.tiktoken``); it is checked against the published
SHA-256 either way.

Without tiktoken the naive-chunk configurations cannot be rebuilt faithfully, and context
tokens fall back to an estimate of ceil(chars / 4), which the report labels.
"""

from __future__ import annotations

import math

CL100K_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
CL100K_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
CL100K_PAT = (
    r"""'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"""
)

_enc = None
_how = None


def load(path: str | None = None):
    """Returns the cl100k encoding, or None when tiktoken is not installed or the file cannot be had."""
    global _enc, _how
    if _enc is not None:
        return _enc
    try:
        import tiktoken
        from tiktoken.load import load_tiktoken_bpe
    except ImportError:
        _how = "estimate: ceil(chars/4) (tiktoken not installed)"
        return None
    try:
        ranks = load_tiktoken_bpe(path or CL100K_URL, expected_hash=CL100K_SHA256)
    except Exception as e:  # offline, blocked, or a wrong file
        _how = f"estimate: ceil(chars/4) (cl100k unavailable: {type(e).__name__})"
        return None
    _enc = tiktoken.Encoding(
        name="cl100k_base",
        pat_str=CL100K_PAT,
        mergeable_ranks=ranks,
        special_tokens={"<|endoftext|>": 100257},
    )
    _how = "cl100k_base via tiktoken (SHA-256 checked)"
    return _enc


def how() -> str:
    return _how or "not loaded"


def count(text: str) -> int:
    if _enc is not None:
        return len(_enc.encode_ordinary(text))
    return math.ceil(len(text) / 4)
