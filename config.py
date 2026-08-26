"""Configuration for OpenLedger PoC v1.

Edit ISSUERS to add companies. CIK is the SEC Central Index Key; `fda_sponsor`
is the (uppercase) sponsor string used to query openFDA Drugs@FDA.
"""
import os

# SEC requires a descriptive User-Agent with real contact info, and rate-limits
# to ~10 req/sec. See https://www.sec.gov/os/webmaster-faq#developers
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "OpenLedger-CABS spphan@dons.usfca.edu")

# PoC issuer universe. Pfizer is the reference issuer (start here); the rest are
# wired but you should verify each CIK / sponsor string as you expand.
ISSUERS = {
    "PFE":  {"name": "Pfizer",                "cik": "0000078003",  "fda_sponsor": "PFIZER"},
    "MRK":  {"name": "Merck",                 "cik": "0000310158",  "fda_sponsor": "MERCK"},
    "BMY":  {"name": "Bristol-Myers Squibb",  "cik": "0000014272",  "fda_sponsor": "BRISTOL"},
    "LLY":  {"name": "Eli Lilly",             "cik": "0000059478",  "fda_sponsor": "LILLY"},
    "ABBV": {"name": "AbbVie",                "cik": "0001551152",  "fda_sponsor": "ABBVIE"},
}

# Gemini is OPTIONAL. If GEMINI_API_KEY is unset, the app falls back to a
# deterministic (regex) extractor so it still runs for demos / first run.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

TOP_N_PRODUCTS = 3
