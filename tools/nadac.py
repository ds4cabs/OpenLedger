"""CMS NADAC drug pricing wrapper. 
NADAC (National Average Drug Acquisition Cost) is published on the Medicaid open
data portal (Socrata). Pricing is keyed by NDC, so you must first map the drug
(via RxNorm -> NDC) before querying.
    https://data.medicaid.gov/dataset?keyword=NADAC
"""


import os
import pandas as pd

_DATA_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "nadac"
)

_NADAC_FILE = os.path.join(_DATA_DIR, "nadac-national-average-drug-acquisition-cost-07-01-2026.csv")

_NADAC = None


def _load_nadac():
    """Load NADAC CSV once."""
    global _NADAC

    if _NADAC is None:
        nadac = pd.read_csv(_NADAC_FILE, dtype=str)

        # This will Convert the price and date columns into useful types
        nadac["NADAC Per Unit"] = pd.to_numeric(
            nadac["NADAC Per Unit"],
            errors="coerce"
        )

        nadac["Effective Date"] = pd.to_datetime(
            nadac["Effective Date"],
            errors="coerce"
        )

        _NADAC = nadac

    return _NADAC


def get_drug_pricing(drug_name):
    """Return representative NADAC unit pricing for a drug by NDC Description."""
    nadac = _load_nadac()
    query = drug_name.upper().strip()

    matches = nadac[
        nadac["NDC Description"].str.upper().str.contains(query, na=False)
    ].copy()

    if matches.empty:
        return {
            "drug": drug_name,
            "pricing": None,
            "note": "No NADAC match found by NDC Description.",
        }

    # This picks the most recent matching record
    matches = matches.sort_values("Effective Date", ascending=False)
    row = matches.iloc[0]

    return {
        "drug": drug_name,
        "pricing": {
            "ndc": row.get("NDC"),
            "ndc_description": row.get("NDC Description"),
            "nadac_per_unit": (
            float(row.get("NADAC Per Unit"))
            if pd.notna(row.get("NADAC Per Unit"))
                else None
),
            "effective_date": (
                row.get("Effective Date").strftime("%Y-%m-%d")
                if pd.notna(row.get("Effective Date"))
                else None
            ),
            "classification": row.get("Classification for Rate Setting"),
            "otc": row.get("OTC"),
        },
        "note": "Matched NADAC record by NDC Description.",
    }
