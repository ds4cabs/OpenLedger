"""openFDA Drugs@FDA wrapper — products marketed by a sponsor.

API: https://open.fda.gov/apis/drug/drugsfda/  (no key needed for low volume)
"""
import requests

BASE = "https://api.fda.gov/drug/drugsfda.json"


def get_top_products_fda(sponsor_name, limit=100):
    """Return a deduped list of brand-name products for a sponsor:
    [{'brand_name', 'marketing_status', 'dosage_form', 'route'}]."""
    params = {"search": f'sponsor_name:"{sponsor_name}"', "limit": limit}
    r = requests.get(BASE, params=params, timeout=30)
    if r.status_code == 404:   # openFDA returns 404 for "no matches"
        return []
    r.raise_for_status()
    out = {}
    for res in r.json().get("results", []):
        for p in res.get("products", []):
            bn = (p.get("brand_name") or "").strip()
            if not bn:
                continue
            out.setdefault(bn.title(), {
                "brand_name": bn.title(),
                "marketing_status": p.get("marketing_status"),
                "dosage_form": p.get("dosage_form"),
                "route": p.get("route"),
            })
    return list(out.values())
