"""RxNorm wrapper — normalize a drug name (brand) to RxCUI + ingredient (generic).

This is the cross-walk that lets you join SEC brand names (e.g. "Eliquis") to FDA
generic/ingredient names (e.g. "apixaban"). API: https://rxnav.nlm.nih.gov/
"""
import requests

BASE = "https://rxnav.nlm.nih.gov/REST"


def normalize(drug_name):
    """Return {'name', 'rxcui', 'ingredient'}; rxcui/ingredient are None if not found."""
    out = {"name": drug_name, "rxcui": None, "ingredient": None}
    r = requests.get(f"{BASE}/rxcui.json", params={"name": drug_name}, timeout=30)
    r.raise_for_status()
    ids = r.json().get("idGroup", {}).get("rxnormId") or []
    if not ids:
        return out
    out["rxcui"] = ids[0]

    # Resolve the ingredient (generic) name via related concepts (tty=IN).
    rr = requests.get(f"{BASE}/rxcui/{ids[0]}/related.json",
                      params={"tty": "IN"}, timeout=30)
    if rr.ok:
        for grp in rr.json().get("relatedGroup", {}).get("conceptGroup", []) or []:
            for c in grp.get("conceptProperties", []) or []:
                out["ingredient"] = c.get("name")
                return out
    return out
