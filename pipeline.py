"""Deterministic orchestration — assemble issuer cards and comparison briefs.

The LLM is used ONLY for the two jobs in agent.py. Everything here (fetching,
joining, enrichment) is plain, debuggable Python. Each external call is wrapped
in try/except so one failing source never kills the whole card.
"""

import os
import google.generativeai as genai

from config import ISSUERS
from tools import (
    sec_edgar,
    drugs_fda,
    rxnorm,
    dailymed,
    orange_book,
    nadac,
)

import agent

def _get_enrichment_lookup_name(product_name: str) -> str:
    """
    Convert SEC financial-reporting names into cleaner names
    for RxNorm, DailyMed, Orange Book, and NADAC lookups.
    """
    import re

    name = str(product_name or "").strip()

    if not name:
        return ""

    # Remove SEC/table footnote markers:
    # Zepbound(1) -> Zepbound
    name = re.sub(
        r"\(\d+\)\s*$",
        "",
        name,
    ).strip()

    # Prevnar family -> Prevnar
    if name.casefold().endswith(" family"):
        name = name[:-len(" family")].strip()

    # Keytruda/Keytruda Qlex -> Keytruda
    if "/" in name:
        name = name.split("/", 1)[0].strip()

    return name



def _get_fda_products_with_gemini(
    sponsor_name: str,
) -> list:
    """
    Use Gemini automatic function calling to retrieve the
    sponsor product list from openFDA / Drugs@FDA.
    """
    tool_results = {}

    def lookup_fda_products(sponsor: str):
        """Retrieve Drugs@FDA products associated with a sponsor."""
        print(f"[GEMINI TOOL CALL] openFDA: {sponsor}")

        result = drugs_fda.get_top_products_fda(
            sponsor
        )

        tool_results["fda_products"] = result

        return result

    model = genai.GenerativeModel(
        model_name=os.getenv(
            "GEMINI_MODEL",
            "gemini-3.5-flash-lite",
        ),
        tools=[
            lookup_fda_products,
        ],
    )

    chat = model.start_chat(
        enable_automatic_function_calling=True
    )

    chat.send_message(
        f"""
    Retrieve the Drugs@FDA product information for sponsor
    "{sponsor_name}".

    You must use the available lookup_fda_products tool.
    Do not answer using your own knowledge.
    """
        )



    return tool_results.get(
        "fda_products",
        [],
    )


def _get_10k_filing_with_gemini(
    ticker: str,
) -> dict:
    """
    Use Gemini automatic function calling to retrieve the
    issuer's 10-K filing from SEC EDGAR.
    """
    tool_results = {}

    def lookup_sec_10k(issuer_ticker: str):
        """Retrieve the latest 10-K filing for an issuer from SEC EDGAR."""
        print(
            f"[GEMINI TOOL CALL] SEC EDGAR: {issuer_ticker}"
        )

        filing = sec_edgar.get_10k_filing(
            issuer_ticker
        )

        # Keep the complete filing in Python rather than sending the entire document back through Gemini.
        tool_results["filing"] = filing

        meta = filing.get("meta") or {}

        # Gemini only needs confirmation that its tool call succeeded.
        return {
            "status": "success",
            "ticker": issuer_ticker,
            "filing_date": meta.get("filing_date"),
            "doc_url": meta.get("doc_url"),
        }

    model = genai.GenerativeModel(
        model_name=os.getenv(
            "GEMINI_MODEL",
            "gemini-3.5-flash-lite",
        ),
        tools=[
            lookup_sec_10k,
        ],
    )

    chat = model.start_chat(
        enable_automatic_function_calling=True
    )

    chat.send_message(
        f"""
Retrieve the latest 10-K filing for issuer ticker "{ticker}".

You must use the available lookup_sec_10k tool.
Do not answer using your own knowledge.
"""
    )

    filing = tool_results.get("filing")

    if not filing:
        raise RuntimeError(
            f"Gemini did not retrieve a 10-K filing for {ticker}."
        )

    return filing


def _enrich_products_with_gemini_tools(
    products: list[dict],
) -> dict:
    """
    Use one Gemini AFC session to enrich all validated products
    for an issuer.

    Gemini calls one enrich_product tool per product.
    That tool then runs RxNorm, DailyMed, Orange Book, and NADAC
    deterministically in Python.
    """

    tool_results = {}

    def enrich_product(drug_name: str):
        """
        Enrich one pharmaceutical product using RxNorm,
        DailyMed, FDA Orange Book, and NADAC.
        """
        print(
            f"[GEMINI TOOL CALL] Enrich product: {drug_name}"
        )

        result_bundle = {}

        # RxNorm
        print(
            f"[PYTHON TOOL] RxNorm: {drug_name}"
        )

        try:
            rxnorm_result = rxnorm.normalize(
                drug_name
            )
        except Exception as exc:
            rxnorm_result = {
                "error": str(exc)
            }

        result_bundle["rxnorm"] = rxnorm_result

        # DailyMed
        print(
            f"[PYTHON TOOL] DailyMed: {drug_name}"
        )

        try:
            label_result = (
                dailymed.get_dailymed_label(
                    drug_name
                )
            )
        except Exception as exc:
            label_result = {
                "error": str(exc)
            }

        result_bundle["label"] = label_result

        # Orange Book
        ingredient = (
            rxnorm_result.get("ingredient")
            if isinstance(
                rxnorm_result,
                dict,
            )
            else None
        )

        orange_book_lookup = (
            ingredient or drug_name
        )

        print(
            f"[PYTHON TOOL] Orange Book: "
            f"{orange_book_lookup}"
        )

        try:
            exclusivity_result = (
                orange_book
                .get_orange_book_exclusivity(
                    orange_book_lookup
                )
            )
        except Exception as exc:
            exclusivity_result = {
                "error": str(exc)
            }

        result_bundle[
            "exclusivity"
        ] = exclusivity_result

        # NADAC
        print(
            f"[PYTHON TOOL] NADAC: {drug_name}"
        )

        try:
            pricing_result = (
                nadac.get_drug_pricing(
                    drug_name
                )
            )
        except Exception as exc:
            pricing_result = {
                "error": str(exc)
            }

        # Add a deterministic display-formatted NADAC price.
        if isinstance(pricing_result, dict):
            pricing_data = pricing_result.get("pricing")

            if isinstance(pricing_data, dict):
                nadac_value = pricing_data.get("nadac_per_unit")

                if nadac_value is not None:
                    try:
                        pricing_data["nadac_display"] = (
                            f"${float(nadac_value):,.2f}"
                        )
                    except (TypeError, ValueError):
                        pricing_data["nadac_display"] = "N/A"
                else:
                    pricing_data["nadac_display"] = "N/A"

        result_bundle[
            "pricing"
        ] = pricing_result

        # Store the FULL results in Python.
        tool_results[
            drug_name
        ] = result_bundle

        # Give Gemini only a small response.
        # It does not need the huge DailyMed label.
        return {
            "status": "success",
            "drug_name": drug_name,
            "rxnorm_found": bool(
                rxnorm_result
                and not rxnorm_result.get("error")
            ),
            "dailymed_found": bool(
                label_result
                and not label_result.get("error")
            ),
            "orange_book_found": bool(
                exclusivity_result
                and not exclusivity_result.get("error")
            ),
            "nadac_found": bool(
                pricing_result
                and not pricing_result.get("error")
            ),
        }

    model = genai.GenerativeModel(
        model_name=os.getenv(
            "GEMINI_MODEL",
            "gemini-3.5-flash-lite",
        ),
        tools=[
            enrich_product,
        ],
    )

    chat = model.start_chat(
        enable_automatic_function_calling=True
    )

    product_names = [
        _get_enrichment_lookup_name(
            product.get("product", "")
        )
        for product in products
        if product.get("product")
    ]

    chat.send_message(
        f"""
Enrich all of these pharmaceutical products:

{product_names}

You have one tool named enrich_product.

You must call enrich_product exactly once
for EACH product in the list.

Use the product name exactly as supplied
as the drug_name argument.

Do not answer using outside knowledge.
Do not skip any products.
"""
    )

    # Verify Gemini called the tool for every product.
    for drug_name in product_names:
        if drug_name not in tool_results:
            print(
                f"[WARNING] Gemini did not call "
                f"enrich_product for {drug_name}"
            )

    return tool_results


def build_issuer_card(
    ticker: str,
    use_sample: bool = False,
) -> dict:
    """
    Build one issuer card.

    Pipeline:

        SEC 10-K
            -> structured Gemini financial extraction
            -> deterministic source validation
            -> deterministic revenue concentration metrics
            -> FDA/RxNorm/DailyMed/Orange Book/NADAC enrichment

    Gemini interprets the filing and identifies:
        - total company revenue
        - the leading individual products
        - each product's reported revenue

    Python handles:
        - source validation
        - arithmetic
        - API retrieval
        - enrichment
        - error handling
        - final card assembly
    """
    normalized_ticker = ticker.upper()

    info = ISSUERS.get(normalized_ticker)

    if not info:
        raise ValueError(
            f"Unknown issuer '{ticker}'. "
            "Add it to config.ISSUERS."
        )

    card = {
        "ticker": normalized_ticker,
        "name": info["name"],
        "filing": None,

        # New financial extraction fields.
        "fiscal_year": None,
        "total_company_revenue": None,
        "revenue_metrics": None,

        # Existing fields.
        "products": [],
        "fda_products_sample": [],
        "errors": [],
    }

    # This will hold the validated products returned by agent.py.
    extracted_products = []

    # Download the 10-K and extract financial information.
    try:
        if use_sample:
            filing = sec_edgar.get_sample_filing(
                normalized_ticker
            )
        else:
            filing = _get_10k_filing_with_gemini(
                normalized_ticker
            )

        card["filing"] = filing["meta"]

        revenue_result = agent.extract_top_product_revenue(
            filing_text=filing.get("text", ""),
            filing_html=filing.get("html"),
        )

        # The revised agent function returns a dictionary rather
        # than returning only a list of products.
        if not isinstance(revenue_result, dict):
            raise TypeError(
                "extract_top_product_revenue() must return a "
                "dictionary containing 'products', "
                "'total_company_revenue', and 'revenue_metrics'."
            )

        card["fiscal_year"] = revenue_result.get(
            "fiscal_year"
        )

        card["total_company_revenue"] = revenue_result.get(
            "total_company_revenue"
        )

        card["revenue_metrics"] = revenue_result.get(
            "revenue_metrics"
        )

        extracted_products = revenue_result.get(
            "products",
            [],
        )

        if not isinstance(extracted_products, list):
            raise TypeError(
                "The 'products' field returned by "
                "extract_top_product_revenue() must be a list."
            )

    except Exception as exc:
        card["errors"].append(
            f"SEC/parse: {exc}"
        )

        extracted_products = []

    # Retrieve sponsor products through Gemini AFC.
    try:
        card["fda_products_sample"] = (
            _get_fda_products_with_gemini(
                info["fda_sponsor"]
            )[:10]
        )

    except Exception as exc:
        card["fda_products_sample"] = []

        card["errors"].append(
            f"openFDA: {exc}"
        )

    # Enrich every validated product.
    try:
        issuer_tool_results = (
            _enrich_products_with_gemini_tools(
                extracted_products
            )
        )

    except Exception as exc:
        issuer_tool_results = {}

        card["errors"].append(
            f"Gemini product enrichment: {exc}"
        )
    
    for item in extracted_products:
        name = str(
            item.get("product", "")
        ).strip()

        enriched = dict(item)

        lookup_name = _get_enrichment_lookup_name(
            name
        )

        enriched["lookup_name"] = lookup_name

        if not name:
            card["errors"].append(
                "Product enrichment skipped because an extracted "
                "product did not contain a name."
            )

            # Preserve the product in the output even when its
            # name is missing.
            card["products"].append(enriched)
            continue


        # Gemini automatic function calling enrichment
        tool_results = issuer_tool_results.get(
            lookup_name,
            {},
        )

        # Preserve the existing issuer-card structure.
        enriched["rxnorm"] = tool_results.get(
            "rxnorm",
            {
                "name": name,
                "rxcui": None,
                "ingredient": None,
            },
        )

        enriched["label"] = tool_results.get(
            "label",
            {
                "drug": name,
                "setid": None,
                "title": None,
                "url": None,
                "warning": None,
                "indications": None,
                "dosage": None,
                "contraindications": None,
                "warnings_and_precautions": None,
            },
        )

        enriched["exclusivity"] = tool_results.get(
            "exclusivity",
            {
                "drug": name,
                "exclusivity": [],
                "note": "Orange Book lookup unavailable.",
            },
        )

        enriched["pricing"] = tool_results.get(
            "pricing",
            {
                "drug": name,
                "pricing": None,
                "note": "NADAC lookup unavailable.",
            },
        )

        card["products"].append(
            enriched
        )

    return card


def build_comparison(
    tickers: list[str],
    use_sample: bool = False,
) -> dict:
    """
    Build issuer cards for all requested tickers and ask the agent
    to synthesize the final comparison brief.

    All financial percentages should already be calculated and
    stored in each card before the cards reach write_brief().
    """
    cards = [
        build_issuer_card(
            ticker,
            use_sample=use_sample,
        )
        for ticker in tickers
    ]

    brief_markdown = agent.write_brief(
        cards
    )

    return {
        "cards": cards,
        "brief_markdown": brief_markdown,
    }

