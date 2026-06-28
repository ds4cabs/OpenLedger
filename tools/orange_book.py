"""FDA Orange Book wrapper — exclusivity / patent windows.  [STUB — TODO]

The Orange Book has NO REST API. Data ships as downloadable pipe-delimited files
(products.txt, patent.txt, exclusivity.txt):
    https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files

TODO (Shawn): download exclusivity.txt + products.txt once, join on Appl_No,
and look up by ingredient (from RxNorm) or brand name. Cache locally. For now
this stub returns a structured placeholder so the pipeline runs end-to-end.
"""


def get_orange_book_exclusivity(drug_name):
    return {
        "drug": drug_name,
        "exclusivity": None,
        "note": "TODO: load Orange Book data files (no REST API).",
    }
