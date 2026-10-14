"""Fetch the real, public layer of the finance corpus, politely.

  python3 -m corpusfetch plan                  # what would be requested, and how long it takes
  python3 -m corpusfetch search                # EDGAR full-text searches  -> search/*.jsonl
  python3 -m corpusfetch filings               # selected 10-K/20-F/8-K/S-1 documents -> filings.jsonl
  python3 -m corpusfetch regs                  # SEC, Federal Register, eCFR, EUR-Lex, GOV.UK -> regs.jsonl
  python3 -m corpusfetch all

Needs SEC_USER_AGENT="Your Name you@example.com" (or --user-agent). Everything is cached under
--out/raw, so re-running only fetches what is missing; manifest.jsonl records every response.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import edgar, regs
from .polite import FetchError, IdentityRejected, PoliteClient, Throttled

HERE = Path(__file__).resolve().parent.parent
CONFIG = HERE / "config"


def load(name: str):
    return json.loads((CONFIG / name).read_text())


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def plan(args) -> int:
    queries, companies, sources = load("queries.json"), load("companies.json"), load("sources.json")
    n_search = sum(q.get("max_pages", 1) for q in queries)
    n_filings = 1 + len(companies["by_ticker"]) + 2 * sum(
        c.get("limit", 1) for c in companies["by_ticker"]) + 2 * len(companies["explicit"])
    n_regs = 0
    for s in sources:
        n_regs += {"url": 1, "federal-register": 3, "govuk": 1}.get(s["kind"], 0)
        if s["kind"] == "ecfr":
            n_regs += 1 + len(s.get("dates", []))
    sec = n_search + n_filings + sum(1 for s in sources if s["kind"] == "url"
                                     and "sec.gov" in s["url"])
    other = n_regs - sum(1 for s in sources if s["kind"] == "url" and "sec.gov" in s["url"])
    print(f"Upper bound on requests: search {n_search}, filings {n_filings}, regs {n_regs}")
    print(f"  SEC hosts: about {sec} at {args.sec_rate}/s -> {sec / args.sec_rate:.0f} s minimum")
    print(f"  other hosts: about {other} at {args.other_rate}/s -> "
          f"{other / args.other_rate:.0f} s minimum")
    print("Cached responses are not re-requested, so a second run sends almost nothing.")
    return 0


def run_search(client, out: Path):
    for q in load("queries.json"):
        try:
            rows = list(edgar.efts_search(client, q["q"], q.get("forms", []), q.get("start"),
                                          q.get("end"), q.get("ciks", []), q.get("max_pages", 1)))
        except FetchError as err:
            print(f"!! search {q['id']}: {err}", file=sys.stderr)
            write_jsonl(out / "search" / f"{q['id']}.error.jsonl", [{"id": q["id"], "error": str(err)}])
            continue
        write_jsonl(out / "search" / f"{q['id']}.jsonl", rows)
        filings = len({r["adsh"] for r in rows})
        print(f"search {q['id']}: {len(rows)} hits in {filings} filings")


def run_filings(client, out: Path):
    cfg = load("companies.json")
    tickers = edgar.load_tickers(client)
    saved = []
    for c in cfg["by_ticker"]:
        t = c["ticker"].upper()
        by_cik = {v["cik"]: dict(v, ticker=k) for k, v in tickers.items()}
        if c.get("cik"):  # tickers change (BK became BNY); a CIK doesn't
            cik = int(c["cik"])
            title = by_cik.get(cik, {}).get("title", t)
        elif t in tickers:
            cik, title = tickers[t]["cik"], tickers[t]["title"]
        else:
            print(f"!! ticker {t} not in company_tickers.json (renamed? set \"cik\" in "
                  f"companies.json); skipped", file=sys.stderr)
            saved.append({"ticker": t, "error": "ticker not in company_tickers.json"})
            continue
        try:
            rows = edgar.submissions(client, cik, start=c.get("start"))
        except FetchError as err:
            print(f"!! {t}: {err}", file=sys.stderr)
            saved.append({"ticker": t, "error": str(err)})
            continue
        picked = edgar.select_filings(rows, c["forms"], c.get("start"), c.get("end"),
                                      c.get("limit", 1))
        if not picked:
            print(f"!! {t}: no {'/'.join(c['forms'])} filed in the window; nothing fetched",
                  file=sys.stderr)
        for f in picked:
            try:
                rec = edgar.fetch_filing(client, cik, f["accessionNumber"],
                                         f.get("primaryDocument"), f.get("form", ""))
            except FetchError as err:
                print(f"!! {t} {f['accessionNumber']}: {err}", file=sys.stderr)
                saved.append({"ticker": t, "adsh": f["accessionNumber"], "error": str(err)})
                continue
            rec.update({"ticker": t, "company": title, "form": f.get("form"),
                        "filing_date": f.get("filingDate"), "report_date": f.get("reportDate"),
                        "accepted": f.get("acceptanceDateTime"), "why": c.get("why", "")})
            saved.append(rec)
            print(f"filing {t} {rec['form']} {rec['filing_date']} -> {rec['document']}")
    for e in cfg["explicit"]:
        try:
            rec = edgar.fetch_filing(client, e["cik"], e["adsh"], e.get("document"),
                                     e.get("form", ""))
        except FetchError as err:
            print(f"!! {e['id']}: {err}", file=sys.stderr)
            continue
        rec.update({"id": e["id"], "form": e.get("form"), "why": e.get("why", "")})
        saved.append(rec)
        print(f"filing {e['id']} -> {rec['document']}")
    write_jsonl(out / "filings.jsonl", saved)


def run_regs(client, out: Path):
    saved = []
    for s in load("sources.json"):
        try:
            got = regs.fetch_source(client, s)
        except FetchError as err:
            print(f"!! {s['id']}: {err}", file=sys.stderr)
            saved.append({"id": s["id"], "error": str(err)})
            continue
        saved.extend(got)
        print(f"reg {s['id']}: {len(got)} file(s)")
    write_jsonl(out / "regs.jsonl", saved)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="corpusfetch", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["plan", "search", "filings", "regs", "all"])
    p.add_argument("--out", default="data/finance-corpus", type=Path)
    p.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT", ""))
    p.add_argument("--sec-rate", type=float, default=5.0,
                   help="requests/second to SEC hosts, shared (max 9; SEC limit is 10)")
    p.add_argument("--other-rate", type=float, default=2.0,
                   help="requests/second to every other host")
    args = p.parse_args(argv)
    if args.command == "plan":
        return plan(args)
    try:
        client = PoliteClient(args.user_agent, args.out / "raw", args.out / "manifest.jsonl",
                              sec_rate=args.sec_rate, other_rate=args.other_rate)
        fixed = client.relink_manifest()
        if fixed:
            print(f"manifest: {fixed} absolute paths made relative")
        if args.command in ("search", "all"):
            run_search(client, args.out)
        if args.command in ("filings", "all"):
            run_filings(client, args.out)
        if args.command in ("regs", "all"):
            run_regs(client, args.out)
    except (IdentityRejected, Throttled) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 2
    print(f"Done. {client.requests_sent} requests sent; manifest: {args.out / 'manifest.jsonl'}")
    return 0
