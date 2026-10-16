"""Spring AI 2.0.1 ``TokenTextSplitter.doSplit`` with its defaults, ported line for line.

Defaults: chunkSize 800 tokens, minChunkSizeChars 350, minChunkLengthToEmbed 5,
maxNumChunks 10000, keepSeparator true, punctuation '.', '?', '!', '\\n', cl100k_base.
Java strings index UTF-16 code units, so the 350-character test and the length test count
UTF-16 units here too.
"""

from __future__ import annotations

CHUNK_SIZE = 800
MIN_CHUNK_SIZE_CHARS = 350
MIN_CHUNK_LENGTH_TO_EMBED = 5
MAX_NUM_CHUNKS = 10000
PUNCTUATION = (".", "?", "!", "\n")


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _java_trim(s: str) -> str:
    a, b = 0, len(s)
    while a < b and s[a] <= " ":
        a += 1
    while b > a and s[b - 1] <= " ":
        b -= 1
    return s[a:b]


def split(text: str, enc, chunk_size: int = CHUNK_SIZE) -> list[str]:
    if not _java_trim(text):
        return []
    tokens = enc.encode_ordinary(text)
    dec = lambda t: enc.decode_bytes(t).decode("utf-8", errors="replace")
    chunks: list[str] = []
    n = 0
    while tokens and n < MAX_NUM_CHUNKS:
        chunk = tokens[: min(chunk_size, len(tokens))]
        chunk_text = dec(chunk)
        if not _java_trim(chunk_text):
            tokens = tokens[len(chunk):]
            continue
        if len(tokens) > chunk_size:
            last = max(chunk_text.rfind(p) for p in PUNCTUATION)
            if last != -1 and _u16(chunk_text[:last]) > MIN_CHUNK_SIZE_CHARS:
                chunk_text = chunk_text[: last + 1]
        to_append = _java_trim(chunk_text)
        if _u16(to_append) > MIN_CHUNK_LENGTH_TO_EMBED:
            chunks.append(to_append)
        tokens = tokens[len(enc.encode_ordinary(chunk_text)):]
        n += 1
    if tokens:
        rest = _java_trim(dec(tokens).replace("\n", " "))
        if _u16(rest) > MIN_CHUNK_LENGTH_TO_EMBED:
            chunks.append(rest)
    return chunks
