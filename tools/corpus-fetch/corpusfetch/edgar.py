"""EDGAR: ticker lookup, full-text search, company submissions and filing documents.

Interfaces as documented by the SEC and used by edgartools / sec-edgar-downloader (checked Oct 2026):
  * https://www.sec.gov/files/company_tickers.json  {"0": {"cik_str": 789019, "ticker": "MSFT", ...}}
  * https://efts.sec.gov/LATEST/search-index?q=..&forms=..&dateRange=custom&startdt=..&enddt=..&from=..
      100 hits per page whatever you ask for; from + 100 may not exceed 10,000;
      a failed query comes back as HTTP 200 with {"errorMessage": ...};
      each hit: _id = "{adsh}:{filename}", _source = {adsh, ciks[], display_names[], form,
      file_date, file_type, period_ending, items[], ...}
  * https://data.sec.gov/submissions/CIK##########.json  filings.recent = parallel column arrays;
      older pages listed in filings.files[] and fetched from the same /submissions/ path.
  * https://www.sec.gov/Archives/edgar/data/{cik}/{accession without dashes}/{file}
"""
from __future__ import annotations

import urllib.parse
from typing import Dict, Iterable, Iterator, List, Optional

from .polite import FetchError, PoliteClient

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh_nodash}/{filename}"
EFTS_PAGE = 100
EFTS_WINDOW = 10_000


def cik10(cik) -> str:
    return str(int(str(cik))).zfill(10)


def archive_url(cik, adsh: str, filename: str) -> str:
    return ARCHIVE_URL.format(cik=int(str(cik)), adsh_nodash=adsh.replace("-", ""),
                              filename=filename)


def load_tickers(client: PoliteClient) -> Dict[str, dict]:
    data = client.get_json(TICKERS_URL)
    return {row["ticker"].upper(): {"cik": int(row["cik_str"]), "title": row["title"]}
            for row in data.values()}


def efts_url(q: str, forms: Iterable[str] = (), start: Optional[str] = None,
             end: Optional[str] = None, ciks: Iterable = (), offset: int = 0) -> str:
    params = {"q": q}
    forms = [f for f in forms if f]
    if forms:
        params["forms"] = ",".join(forms)
    if start or end:
        params["dateRange"] = "custom"
        if start:
            params["startdt"] = start
        if end:
            params["enddt"] = end
    ciks = [cik10(c) for c in ciks]
    if ciks:
        params["ciks"] = ",".join(ciks)
    if offset:
        params["from"] = str(offset)
    return EFTS_URL + "?" + urllib.parse.urlencode(params)


def efts_search(client: PoliteClient, q: str, forms: Iterable[str] = (),
                start: Optional[str] = None, end: Optional[str] = None,
                ciks: Iterable = (), max_pages: int = 1) -> Iterator[dict]:
    """Yield one flat record per hit (a hit is one document of a filing)."""
    forms, ciks = list(forms), list(ciks)
    for page in range(max_pages):
        offset = page * EFTS_PAGE
        if offset + EFTS_PAGE > EFTS_WINDOW:
            break
        body = client.get_json(efts_url(q, forms, start, end, ciks, offset))
        if "errorMessage" in body:
            raise FetchError(f"EDGAR full-text search rejected the query {q!r}: "
                             f"{body['errorMessage']}")
        hits = body.get("hits", {})
        rows = hits.get("hits", [])
        for h in rows:
            src = h.get("_source", {})
            adsh = src.get("adsh") or h.get("_id", "").split(":", 1)[0]
            filename = h.get("_id", "").split(":", 1)[1] if ":" in h.get("_id", "") else ""
            cik_list = src.get("ciks") or []
            yield {
                "adsh": adsh,
                "filename": filename,
                "cik": int(cik_list[0]) if cik_list else None,
                "display_names": src.get("display_names", []),
                "form": src.get("form"),
                "file_type": src.get("file_type"),
                "file_date": src.get("file_date"),
                "period_ending": src.get("period_ending"),
                "items": src.get("items", []),
                "url": archive_url(cik_list[0], adsh, filename) if cik_list and filename else None,
            }
        total = hits.get("total", {}).get("value", 0)
        if len(rows) < EFTS_PAGE or offset + EFTS_PAGE >= total:
            break


def submissions(client: PoliteClient, cik, include_older: bool = False) -> List[dict]:
    """All filings for a company as a list of row dicts, newest first."""
    first = client.get_json(SUBMISSIONS_URL.format(name=f"CIK{cik10(cik)}.json"))
    pages = [first.get("filings", {}).get("recent", {})]
    if include_older:
        for f in first.get("filings", {}).get("files", []):
            pages.append(client.get_json(SUBMISSIONS_URL.format(name=f["name"])))
    rows: List[dict] = []
    for cols in pages:
        n = len(cols.get("accessionNumber", []))
        for i in range(n):
            rows.append({k: (v[i] if i < len(v) else None) for k, v in cols.items()
                         if isinstance(v, list)})
    rows.sort(key=lambda r: r.get("filingDate") or "", reverse=True)
    return rows


def select_filings(rows: List[dict], forms: Iterable[str], start: Optional[str] = None,
                   end: Optional[str] = None, limit: int = 1) -> List[dict]:
    forms = set(forms)
    picked = []
    for r in rows:
        if forms and r.get("form") not in forms:
            continue
        d = r.get("filingDate") or ""
        if start and d < start:
            continue
        if end and d > end:
            continue
        picked.append(r)
        if len(picked) >= limit:
            break
    return picked


def primary_from_index(index: dict, form: str = "") -> Optional[str]:
    """Guess the main document from a filing's index.json when we don't know its name."""
    items = index.get("directory", {}).get("item", [])
    htm = [i for i in items
           if i.get("name", "").lower().endswith((".htm", ".html"))
           and "-index" not in i.get("name", "")]
    if not htm:
        return None
    key = form.lower().replace("-", "").replace("/", "")
    named = [i for i in htm if key and key in i["name"].lower().replace("-", "")]
    pool = named or htm

    def size(i):
        try:
            return int(i.get("size") or 0)
        except ValueError:
            return 0
    return max(pool, key=size)["name"]


def fetch_filing(client: PoliteClient, cik, adsh: str, document: Optional[str] = None,
                 form: str = "") -> dict:
    """Fetch a filing's index.json and its main document. Returns what was saved."""
    index_url = archive_url(cik, adsh, "index.json")
    index = client.get_json(index_url)
    doc = document or primary_from_index(index, form)
    if not doc:
        raise FetchError(f"No HTML document found in {index_url}")
    if "/" in doc:          # xsl-rendered views (forms 3/4/5): take the raw file
        doc = doc.rsplit("/", 1)[-1]
    resp = client.get(archive_url(cik, adsh, doc))
    return {"cik": int(str(cik)), "adsh": adsh, "document": doc, "url": resp.url,
            "file": str(resp.path), "sha256": resp.sha256, "bytes": len(resp.body)}
