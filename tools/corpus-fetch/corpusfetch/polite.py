"""A polite, cached HTTP client for SEC EDGAR and regulatory sites. Standard library only.

SEC fair access (sec.gov/os/accessing-edgar-data, checked Oct 2026):
  * at most 10 requests per second, in total, across every machine you use;
  * a declared User-Agent naming you and giving a contact email;
  * Accept-Encoding: gzip, deflate.
Go over the limit and the SEC blocks your IP until your rate has stayed below the threshold
for 10 minutes; requests sent during the block extend it. So this client:
  * shares ONE token bucket across www.sec.gov, data.sec.gov and efts.sec.gov
    (default 5 req/s, refuses anything above 9);
  * refuses to run without a User-Agent that contains an email address;
  * on a throttle response (403/429 with the SEC's traffic-limit page, or a Retry-After),
    stops ALL requests for 11 minutes once, then gives up if it happens again;
  * on "Undeclared Automated Tool" aborts at once: the User-Agent is wrong, waiting won't help;
  * retries timeouts and 5xx with exponential backoff and jitter;
  * caches every response on disk, so a re-run sends no requests for what it already has;
  * appends one line per response to a manifest (URL, file, SHA-256, size, time), so the
    snapshot is reproducible and its provenance is recorded.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

SEC_HOSTS = ("www.sec.gov", "sec.gov", "data.sec.gov", "efts.sec.gov")
SEC_MAX_RATE = 9.0          # hard ceiling we allow ourselves; the SEC limit is 10
THROTTLE_PAUSE_S = 11 * 60  # the SEC's timeout is 10 minutes; wait a little longer
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class FetchError(RuntimeError):
    pass


class IdentityRejected(FetchError):
    """The SEC rejected the User-Agent. Fix it; waiting will not help."""


class Throttled(FetchError):
    """The SEC throttled us twice. Stop and come back later."""


class TokenBucket:
    """At most `rate` acquisitions per second, smoothed (no bursts)."""

    def __init__(self, rate: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.interval = 1.0 / rate
        self.clock, self.sleep = clock, sleep
        self.next_at = 0.0
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            wait = self.next_at - now
            if wait > 0:
                self.sleep(wait)
                now = self.clock()
            self.next_at = max(now, self.next_at) + self.interval

    def pause(self, seconds: float) -> None:
        """Hold every caller back for `seconds` (used after a throttle)."""
        with self.lock:
            self.next_at = max(self.next_at, self.clock() + seconds)


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    content_type: str
    path: Path
    sha256: str
    from_cache: bool
    file: str = ""  # path relative to the manifest's folder, as recorded in the manifest

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _decode(body: bytes, encoding: str) -> bytes:
    encoding = (encoding or "").lower()
    if encoding == "gzip" or body[:2] == b"\x1f\x8b":
        return gzip.decompress(body)
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def _cache_name(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    tail = Path(parsed.path).name or "index"
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", tail)[:80]
    return hashlib.sha256(url.encode()).hexdigest()[:16] + "_" + tail


class PoliteClient:
    def __init__(self, user_agent: str, cache_dir: Path, manifest: Path,
                 sec_rate: float = 5.0, other_rate: float = 2.0,
                 timeout: float = 30.0, max_attempts: int = 5,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 opener: Optional[urllib.request.OpenerDirector] = None,
                 log: Callable[[str], None] = lambda m: print(m, file=sys.stderr),
                 sec_hosts=SEC_HOSTS):
        if not user_agent or not EMAIL.search(user_agent):
            raise IdentityRejected(
                "Set a User-Agent with your name and a contact email, e.g. "
                "SEC_USER_AGENT='Jane Doe jane@example.com' (the SEC requires it).")
        if sec_rate > SEC_MAX_RATE:
            raise ValueError(f"sec_rate {sec_rate} is above the {SEC_MAX_RATE} req/s ceiling")
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = Path(manifest)
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self.timeout, self.max_attempts = timeout, max_attempts
        self.sleep, self.log = sleep, log
        self.sec_hosts = tuple(sec_hosts)
        self.sec_bucket = TokenBucket(sec_rate, clock, sleep)
        self.other_bucket = TokenBucket(other_rate, clock, sleep)
        self.opener = opener or urllib.request.build_opener()
        self.throttled_once = False
        self.requests_sent = 0

    # -- public -------------------------------------------------------------
    def get(self, url: str, accept: str = "*/*", refresh: bool = False) -> Response:
        path = self.cache_dir / _cache_name(url)
        meta = path.with_suffix(path.suffix + ".meta.json")
        if path.exists() and meta.exists() and not refresh:
            info = json.loads(meta.read_text())
            body = path.read_bytes()
            return Response(url, info["status"], body, info.get("content_type", ""), path,
                            hashlib.sha256(body).hexdigest(), True, self.relpath(path))
        status, body, ctype = self._fetch(url, accept)
        path.write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta.write_text(json.dumps({"url": url, "status": status, "content_type": ctype,
                                    "fetched_at": fetched_at}))
        with self.manifest.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"url": url, "file": self.relpath(path), "sha256": digest,
                                "bytes": len(body), "status": status,
                                "content_type": ctype, "fetched_at": fetched_at}) + "\n")
        return Response(url, status, body, ctype, path, digest, False, self.relpath(path))

    def relpath(self, path: Path) -> str:
        """A path relative to the manifest's folder, so the manifest can be committed and moved."""
        try:
            return Path(os.path.relpath(Path(path).resolve(), self.manifest.parent.resolve())).as_posix()
        except ValueError:  # different drive on Windows
            return Path(path).as_posix()

    def relink_manifest(self) -> int:
        """Rewrite absolute paths left in the manifest by earlier versions as relative ones."""
        if not self.manifest.exists():
            return 0
        lines, changed = [], 0
        for line in self.manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if os.path.isabs(row.get("file", "")):
                row["file"] = self.relpath(Path(row["file"]))
                changed += 1
            lines.append(json.dumps(row))
        if changed:
            self.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return changed

    def get_json(self, url: str, refresh: bool = False):
        return self.get(url, accept="application/json", refresh=refresh).json()

    # -- internals ------------------------------------------------------------
    def _is_sec(self, url: str) -> bool:
        host = urllib.parse.urlsplit(url).hostname or ""
        return host in self.sec_hosts

    def _fetch(self, url: str, accept: str):
        sec = self._is_sec(url)
        bucket = self.sec_bucket if sec else self.other_bucket
        attempt = 0
        while True:
            attempt += 1
            bucket.acquire()
            req = urllib.request.Request(url, headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": accept,
            })
            self.requests_sent += 1
            try:
                with self.opener.open(req, timeout=self.timeout) as r:
                    raw = r.read()
                    body = _decode(raw, r.headers.get("Content-Encoding", ""))
                    return r.status, body, r.headers.get("Content-Type", "")
            except urllib.error.HTTPError as e:
                raw = e.read() if hasattr(e, "read") else b""
                try:
                    body = _decode(raw, e.headers.get("Content-Encoding", "") if e.headers else "")
                except Exception:
                    body = raw
                text = body.decode("utf-8", errors="replace")
                if e.code in (403, 429):
                    if "Undeclared Automated Tool" in text:
                        raise IdentityRejected(
                            f"SEC rejected the User-Agent for {url}. Use your real name and "
                            "email, e.g. 'Jane Doe jane@example.com'.") from None
                    if sec or e.code == 429:
                        self._on_throttle(url, e.code, e.headers, bucket)
                        continue
                if e.code == 404:
                    raise FetchError(f"404 Not Found: {url}") from None
                if 500 <= e.code < 600 and attempt < self.max_attempts:
                    self._backoff(attempt, f"HTTP {e.code} for {url}")
                    continue
                raise FetchError(f"HTTP {e.code} for {url}: {text[:200]}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < self.max_attempts:
                    self._backoff(attempt, f"{type(e).__name__} for {url}: {e}")
                    continue
                raise FetchError(f"Giving up on {url}: {e}") from None

    def _on_throttle(self, url, code, headers, bucket):
        if self.throttled_once:
            raise Throttled(
                f"Throttled again (HTTP {code}) on {url}. Stopping. Wait at least 10 minutes, "
                "lower --sec-rate, and re-run: everything fetched so far is cached.")
        self.throttled_once = True
        retry_after = 0
        try:
            retry_after = int(headers.get("Retry-After", "0")) if headers else 0
        except ValueError:
            retry_after = 0
        pause = max(THROTTLE_PAUSE_S, retry_after)
        self.log(f"!! Throttled (HTTP {code}) on {url}. Pausing ALL requests for "
                 f"{pause // 60} min, as the SEC asks, then trying once more.")
        bucket.pause(pause)

    def _backoff(self, attempt: int, why: str):
        delay = min(60.0, 2 ** (attempt - 1)) * (0.5 + random.random() / 2)
        self.log(f"   retry {attempt}/{self.max_attempts - 1} in {delay:.1f}s ({why})")
        self.sleep(delay)
