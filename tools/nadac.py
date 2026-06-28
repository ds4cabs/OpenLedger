"""CMS NADAC drug pricing wrapper.  [STUB — TODO]

NADAC (National Average Drug Acquisition Cost) is published on the Medicaid open
data portal (Socrata). Pricing is keyed by NDC, so you must first map the drug
(via RxNorm -> NDC) before querying.
    https://data.medicaid.gov/dataset?keyword=NADAC

TODO (Shawn): pick the latest NADAC dataset id, query by NDC description, and
return a representative unit price. Stub keeps the pipeline running end-to-end.
"""


def get_pricing(drug_name):
    return {
        "drug": drug_name,
        "unit_price": None,
        "note": "TODO: query CMS NADAC by NDC (map via RxNorm first).",
    }
