"""Offline tests: a local HTTP server stands in for the SEC, so no real request is ever sent."""
import gzip
import http.server
import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpusfetch import cli, edgar, regs  # noqa: E402
from corpusfetch.polite import (IdentityRejected, PoliteClient, Throttled,  # noqa: E402
                                TokenBucket, FetchError)

UA = "Test Person test@example.com"


class FakeSec(http.server.BaseHTTPRequestHandler):
    routes = {}      # path -> list of (status, body bytes, headers); popped in order, last repeats
    seen = []

    def do_GET(self):
        FakeSec.seen.append((self.path, dict(self.headers)))
        key = self.path
        if key not in FakeSec.routes:
            key = self.path.split("?", 1)[0]
        queue = FakeSec.routes.get(key)
        if not queue:
            self.send_response(404)
            self.end_headers()
            return
        status, body, headers = queue.pop(0) if len(queue) > 1 else queue[0]
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def gz(obj) -> bytes:
    raw = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
    return gzip.compress(raw)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeSec)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeSec.routes, FakeSec.seen = {}, []
        self.tmp = Path(tempfile.mkdtemp())
        self.sleeps = []
        self.logs = []
        self.client = PoliteClient(UA, self.tmp / "raw", self.tmp / "manifest.jsonl",
                                   sec_rate=9, sleep=self.sleeps.append,
                                   log=self.logs.append, sec_hosts=("127.0.0.1",))

    def route(self, path, *responses):
        FakeSec.routes[path] = list(responses)


class TokenBucketTest(unittest.TestCase):
    def test_spaces_requests_at_the_rate(self):
        t = [0.0]
        slept = []

        def sleep(s):
            slept.append(s)
            t[0] += s
        b = TokenBucket(5, clock=lambda: t[0], sleep=sleep)
        for _ in range(6):
            b.acquire()
        self.assertAlmostEqual(t[0], 1.0, places=6)   # 6 requests at 5/s take 1 s
        self.assertTrue(all(abs(s - 0.2) < 1e-9 for s in slept))

    def test_pause_holds_everyone(self):
        t = [100.0]
        slept = []
        b = TokenBucket(5, clock=lambda: t[0], sleep=lambda s: slept.append(s))
        b.pause(660)
        b.acquire()
        self.assertAlmostEqual(slept[0], 660, places=6)


class IdentityTest(unittest.TestCase):
    def test_refuses_without_email(self):
        with self.assertRaises(IdentityRejected):
            PoliteClient("my scraper", Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "m")

    def test_refuses_rate_above_ceiling(self):
        with self.assertRaises(ValueError):
            PoliteClient(UA, Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "m", sec_rate=10)


class ClientTest(Base):
    def test_gzip_cache_manifest_and_headers(self):
        self.route("/files/company_tickers.json",
                   (200, gz({"0": {"cik_str": 2098, "ticker": "ACU", "title": "ACME UNITED CORP"}}),
                    {"Content-Encoding": "gzip", "Content-Type": "application/json"}))
        url = self.base + "/files/company_tickers.json"
        first = self.client.get_json(url)
        second = self.client.get_json(url)
        self.assertEqual(first, second)
        self.assertEqual(len(FakeSec.seen), 1, "second call must come from the cache")
        headers = FakeSec.seen[0][1]
        self.assertEqual(headers["User-Agent"], UA)
        self.assertIn("gzip", headers["Accept-Encoding"])
        lines = (self.tmp / "manifest.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["url"], url)
        self.assertTrue(json.loads(lines[0])["file"].startswith("raw/"),
                        "manifest paths are relative, so the manifest can be committed")

    def test_relink_makes_old_absolute_paths_relative(self):
        absolute = str((self.tmp / "raw" / "abc_x.json").resolve())
        (self.tmp / "manifest.jsonl").write_text(
            json.dumps({"url": "u", "file": absolute}) + "\n"
            + json.dumps({"url": "v", "file": "raw/def_y.json"}) + "\n")
        self.assertEqual(self.client.relink_manifest(), 1)
        files = [json.loads(l)["file"] for l in
                 (self.tmp / "manifest.jsonl").read_text().splitlines()]
        self.assertEqual(files, ["raw/abc_x.json", "raw/def_y.json"])

    def test_throttle_pauses_eleven_minutes_then_succeeds(self):
        page = b"<title>You've Exceeded the SEC's Traffic Limit</title>"
        self.route("/x", (429, page, {}), (200, b"ok", {}))
        r = self.client.get(self.base + "/x")
        self.assertEqual(r.body, b"ok")
        self.assertTrue(any(s >= 659 for s in self.sleeps), self.sleeps)

    def other_site_client(self):
        return PoliteClient(UA, self.tmp / "raw2", self.tmp / "manifest2.jsonl",
                            sleep=self.sleeps.append, log=self.logs.append, sec_hosts=())

    def test_other_site_429_waits_as_asked_without_the_sec_pause(self):
        client = self.other_site_client()
        self.route("/archive", (429, b"slow down", {"Retry-After": "3"}), (200, b"pdf", {}))
        self.assertEqual(client.get(self.base + "/archive").body, b"pdf")
        self.assertIn(3, self.sleeps)
        self.assertFalse(any(s >= 600 for s in self.sleeps), self.sleeps)
        self.assertFalse(client.throttled_once, "another site's 429 is no strike against the SEC")

    def test_other_site_long_retry_after_skips_the_url(self):
        client = self.other_site_client()
        self.route("/busy", (429, b"", {"Retry-After": "3600"}))
        with self.assertRaises(FetchError):
            client.get(self.base + "/busy")
        self.assertEqual(self.sleeps, [])

    def test_sec_throttle_is_not_swallowed_by_fallbacks(self):
        page = b"You've Exceeded the SEC's Traffic Limit"
        self.route("/a", (429, page, {}), (429, page, {}))
        src = {"id": "t", "kind": "url", "url": self.base + "/a", "fallbacks": [self.base + "/b"]}
        with self.assertRaises(Throttled):
            regs.fetch_source(self.client, src)
        self.assertNotIn("/b", [p for p, _ in FakeSec.seen], "must stop, not try the next URL")

    def test_second_throttle_stops(self):
        page = b"You've Exceeded the SEC's Traffic Limit"
        self.route("/y", (403, page, {}))
        with self.assertRaises(Throttled):
            self.client.get(self.base + "/y")

    def test_undeclared_tool_aborts_without_waiting(self):
        self.route("/z", (403, b"Your Request Originates from an Undeclared Automated Tool", {}))
        with self.assertRaises(IdentityRejected):
            self.client.get(self.base + "/z")
        self.assertFalse(any(s >= 600 for s in self.sleeps))

    def test_retries_5xx_then_succeeds(self):
        self.route("/flaky", (503, b"busy", {}), (200, b"fine", {}))
        self.assertEqual(self.client.get(self.base + "/flaky").body, b"fine")

    def test_404_is_an_error_and_not_cached(self):
        with self.assertRaises(FetchError):
            self.client.get(self.base + "/missing")
        self.assertFalse((self.tmp / "manifest.jsonl").exists())


class EdgarTest(Base):
    def setUp(self):
        super().setUp()
        self._saved = (edgar.EFTS_URL, edgar.SUBMISSIONS_URL, edgar.ARCHIVE_URL)
        edgar.EFTS_URL = self.base + "/LATEST/search-index"
        edgar.SUBMISSIONS_URL = self.base + "/submissions/{name}"
        edgar.ARCHIVE_URL = self.base + "/Archives/edgar/data/{cik}/{adsh_nodash}/{filename}"

    def tearDown(self):
        edgar.EFTS_URL, edgar.SUBMISSIONS_URL, edgar.ARCHIVE_URL = self._saved

    def test_efts_url_parameters(self):
        url = edgar.efts_url('"T+1"', ["10-K", "20-F"], "2023-01-01", "2025-12-31", [2098], 100)
        self.assertIn("q=%22T%2B1%22", url)
        self.assertIn("forms=10-K%2C20-F", url)
        self.assertIn("dateRange=custom", url)
        self.assertIn("ciks=0000002098", url)
        self.assertIn("from=100", url)

    def test_efts_parses_hits_and_stops_on_short_page(self):
        hit = {"_id": "0000002098-25-000010:acu-20241231.htm",
               "_source": {"adsh": "0000002098-25-000010", "ciks": ["0000002098"],
                           "display_names": ["ACME UNITED CORP  (ACU)  (CIK 0000002098)"],
                           "form": "10-K", "file_date": "2025-03-07", "file_type": "10-K"}}
        self.route("/LATEST/search-index",
                   (200, json.dumps({"hits": {"total": {"value": 1}, "hits": [hit]}}).encode(), {}))
        rows = list(edgar.efts_search(self.client, '"Acme United"', ["10-K"], max_pages=3))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cik"], 2098)
        self.assertTrue(rows[0]["url"].endswith("/2098/000000209825000010/acu-20241231.htm"))
        self.assertEqual(len(FakeSec.seen), 1, "a short page must end pagination")

    def test_efts_error_message_with_200_raises(self):
        self.route("/LATEST/search-index",
                   (200, json.dumps({"errorType": "ResponseError",
                                     "errorMessage": "bad date"}).encode(), {}))
        with self.assertRaises(FetchError):
            list(edgar.efts_search(self.client, "x", start="2024-13-01"))

    def test_submissions_select_and_fetch(self):
        recent = {"accessionNumber": ["0000002098-25-000010", "0000002098-24-000008",
                                      "0000002098-25-000020"],
                  "filingDate": ["2025-03-07", "2024-03-08", "2025-05-01"],
                  "form": ["10-K", "10-K", "10-Q"],
                  "primaryDocument": ["acu-20241231.htm", "acu-20231231.htm", "acu-q1.htm"],
                  "reportDate": ["2024-12-31", "2023-12-31", "2025-03-31"]}
        self.route("/submissions/CIK0000002098.json",
                   (200, json.dumps({"cik": "2098", "filings": {"recent": recent, "files": []}}).encode(), {}))
        rows = edgar.submissions(self.client, 2098)
        picked = edgar.select_filings(rows, ["10-K"], limit=2)
        self.assertEqual([p["filingDate"] for p in picked], ["2025-03-07", "2024-03-08"])
        index = {"directory": {"item": [
            {"name": "0000002098-25-000010-index.html", "size": ""},
            {"name": "acu-20241231.htm", "size": "900000"},
            {"name": "ex21.htm", "size": "2000"}]}}
        self.route("/Archives/edgar/data/2098/000000209825000010/index.json",
                   (200, json.dumps(index).encode(), {}))
        self.route("/Archives/edgar/data/2098/000000209825000010/acu-20241231.htm",
                   (200, b"<html>10-K</html>", {}))
        rec = edgar.fetch_filing(self.client, 2098, picked[0]["accessionNumber"],
                                 picked[0]["primaryDocument"], "10-K")
        self.assertEqual(rec["document"], "acu-20241231.htm")
        self.assertEqual(rec["bytes"], len(b"<html>10-K</html>"))

    def test_submissions_reads_older_pages_only_when_recent_falls_short(self):
        recent = {"accessionNumber": ["0000093751-26-000100"], "filingDate": ["2026-02-20"],
                  "form": ["10-K"], "primaryDocument": ["stt-2025.htm"]}
        files = [{"name": "CIK0000093751-submissions-001.json",
                  "filingFrom": "2023-06-01", "filingTo": "2025-11-30"},
                 {"name": "CIK0000093751-submissions-002.json",
                  "filingFrom": "2001-01-01", "filingTo": "2023-05-31"}]
        older = {"accessionNumber": ["0000093751-24-000010"], "filingDate": ["2024-02-16"],
                 "form": ["10-K"], "primaryDocument": ["stt-2023.htm"]}
        self.route("/submissions/CIK0000093751.json",
                   (200, json.dumps({"filings": {"recent": recent, "files": files}}).encode(), {}))
        self.route("/submissions/CIK0000093751-submissions-001.json",
                   (200, json.dumps(older).encode(), {}))
        rows = edgar.submissions(self.client, 93751, start="2024-01-01")
        picked = edgar.select_filings(rows, ["10-K"], "2024-01-01", "2024-12-31")
        self.assertEqual([p["primaryDocument"] for p in picked], ["stt-2023.htm"])
        asked = [path for path, _ in FakeSec.seen]
        self.assertNotIn("/submissions/CIK0000093751-submissions-002.json", asked,
                         "a page that ends before the window must not be fetched")
        FakeSec.seen.clear()
        edgar.submissions(self.client, 93751, start="2026-01-01")
        self.assertEqual(len(FakeSec.seen), 0, "recent page reaches back far enough: no more requests")

    def test_primary_from_index_prefers_form_name_then_size(self):
        idx = {"directory": {"item": [{"name": "d1-index.htm", "size": ""},
                                      {"name": "d123d8k.htm", "size": "5000"},
                                      {"name": "dex31.htm", "size": "90000"}]}}
        self.assertEqual(edgar.primary_from_index(idx, "8-K"), "d123d8k.htm")
        self.assertEqual(edgar.primary_from_index(idx, ""), "dex31.htm")


class RegsTest(Base):
    def test_url_source_uses_fallback(self):
        self.route("/good.pdf", (200, b"%PDF", {}))
        out = regs.fetch_source(self.client, {"id": "r", "kind": "url",
                                              "url": self.base + "/gone.pdf",
                                              "fallbacks": [self.base + "/good.pdf"]})
        self.assertEqual(out[0]["url"], self.base + "/good.pdf")

    def test_ecfr_missing_date_is_recorded_not_fatal(self):
        saved = (regs.ECFR_VERSIONS, regs.ECFR_FULL)
        regs.ECFR_VERSIONS = self.base + "/versions/title-{title}.json?{qs}"
        regs.ECFR_FULL = self.base + "/full/{date}/title-{title}.xml?{qs}"
        try:
            self.route("/versions/title-17.json", (200, b'{"content_versions": []}', {}))
            self.route("/full/2017-09-06/title-17.xml", (200, b"<SECTION/>", {}))
            out = regs.fetch_source(self.client, {"id": "e", "kind": "ecfr", "title": 17,
                                                  "part": "240", "section": "240.15c6-1",
                                                  "dates": ["2016-01-01", "2017-09-06"]})
        finally:
            regs.ECFR_VERSIONS, regs.ECFR_FULL = saved
        roles = {o["role"]: o for o in out}
        self.assertIn("error", roles["text@2016-01-01"])
        self.assertIn("sha256", roles["text@2017-09-06"])


class PlanTest(unittest.TestCase):
    def test_plan_runs_on_shipped_config(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(["plan"]), 0)
        self.assertIn("Upper bound on requests", buf.getvalue())


if __name__ == "__main__":
    unittest.main()


class CarryOnTest(Base):
    def test_search_error_is_recorded_and_run_continues(self):
        saved_url, saved_load = edgar.EFTS_URL, cli.load
        edgar.EFTS_URL = self.base + "/LATEST/search-index"
        cli.load = lambda name: [{"id": "bad", "q": "x"}, {"id": "good", "q": "y"}]
        FakeSec.routes["/LATEST/search-index?q=x"] = [(200, b'{"errorMessage": "nope"}', {})]
        FakeSec.routes["/LATEST/search-index?q=y"] = [(200, b'{"hits": {"total": {"value": 0}, "hits": []}}', {})]
        try:
            with redirect_stdout(io.StringIO()):
                import contextlib
                with contextlib.redirect_stderr(io.StringIO()):
                    cli.run_search(self.client, self.tmp)
        finally:
            edgar.EFTS_URL, cli.load = saved_url, saved_load
        self.assertTrue((self.tmp / "search" / "bad.error.jsonl").exists())
        self.assertTrue((self.tmp / "search" / "good.jsonl").exists())
