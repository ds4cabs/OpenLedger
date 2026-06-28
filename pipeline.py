"""Deterministic orchestration — assemble issuer cards and comparison briefs.

The LLM is used ONLY for the two jobs in agent.py. Everything here (fetching,
joining, enrichment) is plain, debuggable Python. Each external call is wrapped
in try/except so one failing source never kills the whole card.
"""
from config import ISSUERS
from tools import sec_edgar, drugs_fda, rxnorm, dailymed, orange_book, nadac
import agent


def build_issuer_card(ticker, use_sample=False):
    """Build one issuer card: 10-K -> top product revenue -> FDA/RxNorm/label enrichment."""
    info = ISSUERS.get(ticker.upper())
    if not info:
        raise ValueError(f"Unknown issuer '{ticker}'. Add it to config.ISSUERS.")

    card = {"ticker": ticker.upper(), "name": info["name"],
            "filing": None, "products": [], "fda_products_sample": [], "errors": []}

    # 1) 10-K -> top product revenue (Gemini-as-parser, or sample for offline demo)
    try:
        filing = (sec_edgar.get_sample_filing(ticker) if use_sample
                  else sec_edgar.get_10k_filing(ticker))
        card["filing"] = filing["meta"]
        revenue = agent.extract_top_product_revenue(filing["text"])
    except Exception as e:
        card["errors"].append(f"SEC/parse: {e}")
        revenue = []

    # 2) sponsor product list from openFDA (context + sanity check)
    try:
        card["fda_products_sample"] = drugs_fda.get_top_products_fda(info["fda_sponsor"])[:10]
    except Exception as e:
        card["errors"].append(f"openFDA: {e}")

    # 3) enrich each extracted product: RxNorm cross-walk + label + (stub) exclusivity/pricing
    for item in revenue:
        name = item.get("product", "")
        enriched = dict(item)
        try:
            enriched["rxnorm"] = rxnorm.normalize(name)
        except Exception as e:
            enriched["rxnorm"] = {"name": name, "rxcui": None, "ingredient": None}
            card["errors"].append(f"RxNorm {name}: {e}")
        try:
            enriched["label"] = dailymed.get_label(name)
        except Exception:
            enriched["label"] = {"drug": name, "setid": None}
        enriched["exclusivity"] = orange_book.get_orange_book_exclusivity(name)
        enriched["pricing"] = nadac.get_pricing(name)
        card["products"].append(enriched)

    return card


def build_comparison(tickers, use_sample=False):
    """Build cards for all tickers and a synthesized comparison brief."""
    cards = [build_issuer_card(t, use_sample=use_sample) for t in tickers]
    return {"cards": cards, "brief_markdown": agent.write_brief(cards)}
