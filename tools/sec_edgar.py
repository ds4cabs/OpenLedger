"""SEC EDGAR wrapper — fetch a company's latest 10-K filing as plain text.

SEC requires a descriptive User-Agent (config.SEC_USER_AGENT) and rate-limits to
~10 req/sec. Docs: https://www.sec.gov/os/webmaster-faq#developers

NOTE: SEC blocks many datacenter / cloud IPs with HTTP 403. It works fine from
Colab and normal networks. If you get 403, use the bundled sample (see
`get_sample_filing`) or run from Colab.
"""
import os
import re
import requests

from config import SEC_USER_AGENT, ISSUERS

HEADERS = {"User-Agent": SEC_USER_AGENT}
_SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_data")


def _cik10(cik):
    return str(cik).lstrip("0").zfill(10)


def get_cik(ticker):
    """Resolve a ticker to a 10-digit CIK (uses config first, then SEC map)."""
    t = ticker.upper()
    if t in ISSUERS:
        return _cik10(ISSUERS[t]["cik"])
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    for row in r.json().values():
        if row["ticker"].upper() == t:
            return _cik10(row["cik_str"])
    raise ValueError(f"Ticker not found in SEC map: {ticker}")


def get_latest_10k_meta(ticker):
    """Return metadata for the most recent 10-K: accession, date, doc_url."""
    cik = get_cik(ticker)
    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            acc_nodash = recent["accessionNumber"][i].replace("-", "")
            doc = recent["primaryDocument"][i]
            return {
                "accession": recent["accessionNumber"][i],
                "filing_date": recent["filingDate"][i],
                "doc_url": (f"https://www.sec.gov/Archives/edgar/data/"
                            f"{int(cik)}/{acc_nodash}/{doc}"),
            }
    raise ValueError(f"No 10-K found for {ticker}")


def _strip_html(html):
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&#160;", " ").replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def get_10k_filing(ticker, max_chars=200_000):
    """Return {'meta': ..., 'text': ...} for the latest 10-K (HTML stripped,
    truncated to max_chars to keep LLM prompts small)."""
    meta = get_latest_10k_meta(ticker)
    r = requests.get(meta["doc_url"], headers=HEADERS, timeout=60)
    r.raise_for_status()
    return {"meta": meta, "text": _strip_html(r.text)[:max_chars]}


def get_sample_filing(ticker):
    """Offline fallback: load a bundled illustrative 10-K excerpt from
    sample_data/. Used so the dashboard demos end-to-end without network/SEC."""
    path = os.path.join(_SAMPLE_DIR, f"{ticker.upper()}_10k_excerpt.txt")
    if not os.path.exists(path):
        path = os.path.join(_SAMPLE_DIR, "PFE_10k_excerpt.txt")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return {"meta": {"accession": "SAMPLE", "filing_date": "sample",
                     "doc_url": f"(bundled sample: {os.path.basename(path)})"},
            "text": text}
