"""FDA Orange Book wrapper — exclusivity / patent windows.

The Orange Book has NO REST API. Data ships as downloadable text files
(products.txt, patent.txt, exclusivity.txt):
    https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files

This wrapper loads locally cached products.txt and exclusivity.txt files,
joins them on Appl_Type, Appl_No, and Product_No, then looks up records by
ingredient or trade name.
"""

import os
import pandas as pd

_DATA_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "orange_book"
)

_PRODUCTS_FILE = os.path.join(_DATA_DIR, "products.txt")
_EXCLUSIVITY_FILE = os.path.join(_DATA_DIR, "exclusivity.txt")

_ORANGE_BOOK = None


def _load_orange_book():
    """Load and merge Orange Book products/exclusivity files once."""
    global _ORANGE_BOOK

    if _ORANGE_BOOK is None:
        products = pd.read_csv(_PRODUCTS_FILE, sep="~", dtype=str)
        exclusivity = pd.read_csv(_EXCLUSIVITY_FILE, sep="~", dtype=str)

        _ORANGE_BOOK = products.merge(
            exclusivity,
            on=["Appl_Type", "Appl_No", "Product_No"],
            how="left"
        )

    return _ORANGE_BOOK


def get_orange_book_exclusivity(drug_name):
    """
    Return Orange Book exclusivity records for a drug by exact
    ingredient or trade-name match.
    """
    orange_book = _load_orange_book()

    normalized_query = str(
        drug_name or ""
    ).strip().casefold()

    if not normalized_query:
        return {
            "drug": drug_name,
            "exclusivity": [],
            "note": "No Orange Book match found.",
        }

    ingredient_matches = (
        orange_book["Ingredient"]
        .fillna("")
        .str.strip()
        .str.casefold()
        == normalized_query
    )

    trade_name_matches = (
        orange_book["Trade_Name"]
        .fillna("")
        .str.strip()
        .str.casefold()
        == normalized_query
    )

    matches = orange_book[
        ingredient_matches | trade_name_matches
    ]

    matches = matches[
        matches["Exclusivity_Code"].notna()
        | matches["Exclusivity_Date"].notna()
    ]

    if matches.empty:
        return {
            "drug": drug_name,
            "exclusivity": [],
            "note": "No Orange Book match found.",
        }

    records = matches[
        [
            "Ingredient",
            "Trade_Name",
            "Appl_Type",
            "Appl_No",
            "Product_No",
            "Exclusivity_Code",
            "Exclusivity_Date",
        ]
    ].drop_duplicates().to_dict(
        orient="records"
    )

    return {
        "drug": drug_name,
        "exclusivity": records,
        "note": (
            "Matched Orange Book records by exact "
            "ingredient or trade name."
        ),
    }
