"""Regulatory texts: SEC rule releases, Federal Register, eCFR point-in-time, EUR-Lex, GOV.UK.

Each source in sources.json is one of:
  {"kind": "url", "url": ..., "fallbacks": [...]}           fetch the first URL that works
  {"kind": "federal-register", "document": "2023-03566"}    API JSON, then its raw text
  {"kind": "ecfr", "title": 17, "part": "240", "section": "240.15c6-1",
   "dates": ["2017-03-01", ...]}                            version list + the text on each date
  {"kind": "govuk", "path": "/government/publications/..."} GOV.UK Content API JSON
"""
from __future__ import annotations

import urllib.parse
from typing import List

from .polite import FetchError, PoliteClient

FR_API = "https://www.federalregister.gov/api/v1/documents/{doc}.json"
ECFR_VERSIONS = "https://www.ecfr.gov/api/versioner/v1/versions/title-{title}.json?{qs}"
ECFR_FULL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml?{qs}"
GOVUK_API = "https://www.gov.uk/api/content{path}"


def fetch_source(client: PoliteClient, src: dict) -> List[dict]:
    kind = src["kind"]
    out: List[dict] = []

    def keep(resp, role):
        out.append({"id": src["id"], "role": role, "url": resp.url, "file": str(resp.path),
                    "sha256": resp.sha256, "bytes": len(resp.body),
                    "redistribute": src.get("redistribute", False)})

    if kind == "url":
        last = None
        for url in [src["url"], *src.get("fallbacks", [])]:
            try:
                keep(client.get(url), "document")
                return out
            except FetchError as e:
                last = e
        raise FetchError(f"{src['id']}: no URL worked ({last})")

    if kind == "federal-register":
        meta = client.get(FR_API.format(doc=src["document"]), accept="application/json")
        keep(meta, "metadata")
        info = meta.json()
        for field, role in (("raw_text_url", "text"), ("body_html_url", "html")):
            if info.get(field):
                keep(client.get(info[field]), role)
        return out

    if kind == "ecfr":
        qs = urllib.parse.urlencode({"part": src["part"], "section": src["section"]})
        keep(client.get(ECFR_VERSIONS.format(title=src["title"], qs=qs),
                        accept="application/json"), "versions")
        for date in src.get("dates", []):
            try:
                keep(client.get(ECFR_FULL.format(date=date, title=src["title"], qs=qs),
                                accept="application/xml"), f"text@{date}")
            except FetchError as e:   # dates before ~2017 are not in the versioner
                out.append({"id": src["id"], "role": f"text@{date}", "error": str(e)})
        return out

    if kind == "govuk":
        keep(client.get(GOVUK_API.format(path=src["path"]), accept="application/json"),
             "content")
        return out

    raise ValueError(f"Unknown source kind {kind!r} in {src.get('id')}")
