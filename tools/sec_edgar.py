"""
SEC EDGAR wrapper.

Downloads a company's latest 10-K filing and preserves both:

1. The original HTML, which can later be parsed into structured tables.
2. A plain-text version, which keeps the existing pipeline compatible.

SEC requires a descriptive User-Agent configured through
config.SEC_USER_AGENT.

SEC may block datacenter or cloud IP addresses with HTTP 403. If that
happens, run locally, use Colab, or use the bundled sample filing.
"""

from __future__ import annotations

import html as html_module
import os
import re
from typing import Any

import requests

from config import ISSUERS, SEC_USER_AGENT


HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}

DATA_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

_SAMPLE_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "sample_data",
)

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_TEXT_CHARS = 200_000


def _cik10(cik: str | int) -> str:
    """
    Convert a CIK into the SEC's 10-digit zero-padded format.

    Example:
        78003 -> "0000078003"
    """
    return str(cik).lstrip("0").zfill(10)


def get_cik(ticker: str) -> str:
    """
    Resolve a ticker symbol to a 10-digit SEC CIK.

    The local config is checked first. If the ticker is not present there,
    the SEC company ticker mapping is used.
    """
    normalized_ticker = ticker.strip().upper()

    if not normalized_ticker:
        raise ValueError("Ticker cannot be empty.")

    if normalized_ticker in ISSUERS:
        return _cik10(ISSUERS[normalized_ticker]["cik"])

    response = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    ticker_map = response.json()

    for row in ticker_map.values():
        row_ticker = str(row.get("ticker", "")).upper()

        if row_ticker == normalized_ticker:
            return _cik10(row["cik_str"])

    raise ValueError(
        f"Ticker not found in SEC company ticker map: {normalized_ticker}"
    )


def get_latest_10k_meta(ticker: str) -> dict[str, str]:
    """
    Return metadata for the issuer's most recent 10-K.

    Returned fields:
        ticker
        cik
        accession
        filing_date
        primary_document
        doc_url
    """
    normalized_ticker = ticker.strip().upper()
    cik = get_cik(normalized_ticker)

    submissions_url = (
        f"https://data.sec.gov/submissions/CIK{cik}.json"
    )

    response = requests.get(
        submissions_url,
        headers=DATA_HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    submissions = response.json()
    recent = submissions.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_documents = recent.get("primaryDocument", [])

    for index, form in enumerate(forms):
        if form != "10-K":
            continue

        accession = accession_numbers[index]
        accession_without_dashes = accession.replace("-", "")
        primary_document = primary_documents[index]

        doc_url = (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/"
            f"{accession_without_dashes}/"
            f"{primary_document}"
        )

        return {
            "ticker": normalized_ticker,
            "cik": cik,
            "accession": accession,
            "filing_date": filing_dates[index],
            "primary_document": primary_document,
            "doc_url": doc_url,
        }

    raise ValueError(
        f"No 10-K filing was found for ticker {normalized_ticker}."
    )


def _strip_html(raw_html: str) -> str:
    """
    Convert SEC filing HTML into readable plain text.

    This function is retained for backward compatibility and fallback use.

    It is no longer the only representation of the filing. The original HTML
    is also returned by get_10k_filing so table structure can be processed
    later.
    """
    if not raw_html:
        return ""

    text = re.sub(
        r"(?is)<(script|style|noscript).*?>.*?</\1>",
        " ",
        raw_html,
    )

    # Add spacing around common block and table elements before removing tags.
    # This reduces cases where values from separate cells are joined together.
    text = re.sub(
        r"(?i)</?(?:p|div|section|article|header|footer|"
        r"h[1-6]|table|thead|tbody|tfoot|tr|ul|ol|li|br)[^>]*>",
        "\n",
        text,
    )

    text = re.sub(
        r"(?i)</?(?:td|th)[^>]*>",
        " | ",
        text,
    )

    text = re.sub(
        r"(?s)<[^>]+>",
        " ",
        text,
    )

    text = html_module.unescape(text)

    # Normalize non-breaking spaces and unusual SEC whitespace.
    text = (
        text.replace("\xa0", " ")
        .replace("\u2007", " ")
        .replace("\u202f", " ")
    )

    # Normalize spaces while retaining useful line boundaries.
    cleaned_lines = []

    for line in text.splitlines():
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()

        if cleaned_line:
            cleaned_lines.append(cleaned_line)

    return "\n".join(cleaned_lines)


def _download_filing_html(doc_url: str) -> str:
    """
    Download the original HTML for a filing document.
    """
    response = requests.get(
        doc_url,
        headers=HEADERS,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    if not response.encoding:
        response.encoding = response.apparent_encoding or "utf-8"

    return response.text


def get_10k_filing(
    ticker: str,
    max_chars: int | None = DEFAULT_MAX_TEXT_CHARS,
) -> dict[str, Any]:
    """
    Download and return the latest 10-K filing.

    Returned structure:

        {
            "meta": {...},
            "html": "<original SEC filing HTML>",
            "text": "plain-text filing representation",
            "source_type": "sec_html"
        }

    Important:
        `html` is preserved without truncation so later code can inspect
        tables, headings, rows, columns, and inline filing structure.

        `text` may be truncated with max_chars to preserve compatibility with
        the existing Gemini prompt and prevent oversized fallback inputs.

    Args:
        ticker:
            Issuer ticker symbol, such as "PFE".

        max_chars:
            Maximum number of plain-text characters to return.

            Use None to return all extracted plain text. This does not affect
            the original HTML.
    """
    normalized_ticker = ticker.strip().upper()

    if not normalized_ticker:
        raise ValueError("Ticker cannot be empty.")

    meta = get_latest_10k_meta(normalized_ticker)
    raw_html = _download_filing_html(meta["doc_url"])
    filing_text = _strip_html(raw_html)

    if max_chars is not None:
        if max_chars <= 0:
            raise ValueError("max_chars must be greater than zero or None.")

        filing_text = filing_text[:max_chars]

    return {
        "meta": meta,
        "html": raw_html,
        "text": filing_text,
        "source_type": "sec_html",
    }


def get_sample_filing(ticker: str) -> dict[str, Any]:
    """
    Load a bundled sample 10-K excerpt for offline testing.

    Sample files are currently plain-text excerpts, so `html` is set to None.
    This allows the rest of the pipeline to distinguish a text-only sample
    from a live HTML filing.

    The existing pipeline can continue using filing["text"] without changes.
    """
    normalized_ticker = ticker.strip().upper()

    if not normalized_ticker:
        raise ValueError("Ticker cannot be empty.")

    requested_path = os.path.join(
        _SAMPLE_DIR,
        f"{normalized_ticker}_10k_excerpt.txt",
    )

    if os.path.exists(requested_path):
        sample_path = requested_path
    else:
        sample_path = os.path.join(
            _SAMPLE_DIR,
            "PFE_10k_excerpt.txt",
        )

    if not os.path.exists(sample_path):
        raise FileNotFoundError(
            "No bundled sample filing was found. Expected a file at "
            f"{sample_path}"
        )

    with open(sample_path, encoding="utf-8") as file:
        filing_text = file.read()

    sample_filename = os.path.basename(sample_path)

    return {
        "meta": {
            "ticker": normalized_ticker,
            "cik": None,
            "accession": "SAMPLE",
            "filing_date": "sample",
            "primary_document": sample_filename,
            "doc_url": f"(bundled sample: {sample_filename})",
        },
        "html": None,
        "text": filing_text,
        "source_type": "sample_text",
    }