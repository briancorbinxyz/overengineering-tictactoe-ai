# corpus-fetch

Fetches the real, public layer of the finance corpus: SEC filings found by EDGAR full-text search, selected companies' 10-K/20-F/40-F filings, a few specific filings (Palantir's 2020 S-1, an Item 4.02 non-reliance notice), and the settlement-cycle rules from the SEC, Federal Register, eCFR, EUR-Lex, ESMA and GOV.UK.

It uses only the Python standard library (3.9 or later, which macOS already ships), so there is nothing to install.

## Run it

```bash
cd tools/corpus-fetch
export SEC_USER_AGENT="Your Name you@example.com"   # required by the SEC; use your real email
python3 -m corpusfetch plan        # how many requests, how long; sends nothing
python3 -m corpusfetch all         # search, filings, regs  (about 100 requests, a minute or two)
```

Or one part at a time: `search`, `filings`, `regs`. Everything lands in `data/finance-corpus/`:

| Path | What |
|---|---|
| `raw/` | Every response, as fetched, plus a `.meta.json` beside it. This is the cache. |
| `manifest.jsonl` | One line per response: URL, file, SHA-256, size, status, UTC time. Commit this. |
| `search/<query>.jsonl` | Full-text search hits, one per document, with the archive URL |
| `filings.jsonl` | The filings fetched, with ticker, form, filing date, report date and acceptance time |
| `regs.jsonl` | The regulatory texts fetched, with a `redistribute` flag |

Run it again whenever you like: anything already in `raw/` is read from disk, not requested.

## How it stays within the SEC's limits

The SEC allows at most **10 requests per second in total, across all your machines**, requires a **User-Agent with your name and email**, and blocks you for **10 minutes** if you exceed the rate, extending the block if you keep going. ([SEC: Accessing EDGAR Data](https://www.sec.gov/os/accessing-edgar-data))

- **One shared rate for every SEC host.** www.sec.gov, data.sec.gov and efts.sec.gov share a single token bucket: 5 requests/s by default, never more than 9 (`--sec-rate` refuses 10 or more). Other sites get 2/s (`--other-rate`).
- **No User-Agent, no run.** The client refuses to start without one that contains an email. If the SEC still answers "Undeclared Automated Tool", it stops at once, because waiting won't fix a bad header.
- **Throttled once: wait 11 minutes; throttled twice: stop.** On a 403 or 429 traffic-limit page, every request pauses for 11 minutes (longer if the server sends `Retry-After`), then it tries once more. A second throttle ends the run. Re-run later: the cache keeps everything fetched so far.
- **Transient errors back off.** Timeouts and 5xx responses get up to 4 retries with exponential backoff and jitter.
- **gzip is requested and decoded,** as the SEC asks.

## What to commit and what not to

- **Commit:** `manifest.jsonl`, the `*.jsonl` summaries, and the config. Together they pin exactly which bytes the corpus was built from.
- **SEC and US government texts:** the SEC says its information "may be copied or further distributed"; cite the SEC as the source. Company filings are public records, but the SEC says nothing explicit about the copyright in company-written text, so the series ships this script rather than bulk copies, as EDGAR-CORPUS-style datasets do.
- **EU texts:** reusable under CC BY 4.0 with "© European Union". **GOV.UK:** Open Government Licence v3.0.
- **Industry documents** (`redistribute: false`, such as the DTCC/SIFMA/ICI playbook, CSA and SEBI pages): keep them local, and cite them by link with your own summary.
- Only `data/finance-corpus/raw/` is git-ignored, so the manifest and summaries can be committed as they are.

Not legal advice.

## Change what it fetches

Edit `config/queries.json` (EDGAR full-text searches), `config/companies.json` (by ticker, or exact accession numbers) and `config/sources.json` (regulatory texts). Search syntax follows the [SEC full-text search FAQ](https://www.sec.gov/edgar/search/efts-faq.html): quotes for phrases, capitalised `OR` and `NOT`, coverage from 2001. A page is 100 hits, and the search stops at 10,000 results, so split long date ranges.

## Tests

```bash
python3 -m unittest discover -s tests
```

The 19 tests run against a local stand-in server, so they never contact the SEC. They cover the rate limiter, the User-Agent check, gzip, caching and the manifest, the 11-minute throttle pause and the stop on a second throttle, the "Undeclared Automated Tool" abort, retries, carrying on past a failed search, full-text search pagination and its HTTP-200 error bodies, submissions parsing, picking the main document from `index.json`, and eCFR dates that don't exist.

## Not yet verified against the live services

This was written where sec.gov, ecfr.gov, eur-lex and gov.uk are unreachable. The request formats come from the SEC's documentation and from two maintained open-source clients (edgartools and sec-edgar-downloader), but the first real run is the first live test. In particular:
- the eCFR point-in-time endpoint and its parameters;
- the 2023 T+1 rule PDF's URL (two fallbacks are configured);
- the EUR-Lex HTML URL (it may serve a cookie or bot page);
- whether every configured ticker's filings exist in the date windows.

Anything that fails is logged with `!!` and recorded in the output files; the rest of the run carries on.
