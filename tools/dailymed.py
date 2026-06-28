"""DailyMed wrapper — find the structured product label (SPL) for a drug.

PoC: returns the first matching SPL's setid + title (a link to the full label).
Extending to pull boxed warnings / indications text is a good next step.
API: https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm
"""
import requests

BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"


def get_label(drug_name):
    """Return {'drug', 'setid', 'title', 'url'}; fields are None if not found."""
    out = {"drug": drug_name, "setid": None, "title": None, "url": None}
    r = requests.get(f"{BASE}/spls.json",
                     params={"drug_name": drug_name, "pagesize": 1}, timeout=30)
    if not r.ok:
        return out
    data = r.json().get("data", [])
    if data:
        out["setid"] = data[0].get("setid")
        out["title"] = data[0].get("title")
        out["url"] = (f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm"
                      f"?setid={out['setid']}")
    return out
