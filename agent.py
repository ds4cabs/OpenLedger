"""Gemini layer — the ONLY two LLM jobs in the PoC:

  1) extract_top_product_revenue()  -- LLM-as-parser over 10-K text
  2) write_brief()                  -- synthesize a Markdown comparison brief

Both have a deterministic fallback, so the app runs WITHOUT a Gemini API key
(handy for first run / offline demo). Set GEMINI_API_KEY to enable Gemini.

Design note: everything else in the project is deterministic Python (see
pipeline.py). We keep the LLM surface area tiny on purpose — that's the PoC.
"""
import os
import re
import json
import copy
from tools import filing_parser

from config import GEMINI_MODEL, TOP_N_PRODUCTS




def _gemini_available():
    return bool(os.environ.get("GEMINI_API_KEY"))


def _focus_revenue(text, window=16000):
    """Slice text around the first 'revenue' mention to keep prompts small."""
    m = re.search(r"revenue", text, re.I)
    if not m:
        return text[:window]
    start = max(0, m.start() - 1500)
    return text[start:start + window]


# --------------------------------------------------------------------------- #
# Job 1: extract top-N product revenue
# --------------------------------------------------------------------------- #
from typing import Any

from tools import filing_parser
from tools.revenue_metrics import calculate_revenue_concentration


def extract_top_product_revenue(
    filing_text: str,
    filing_html: str | None = None,
    n: int = 3,
) -> dict[str, Any]:

    parser_result = filing_parser.build_candidate_context(
        raw_html=filing_html,
        filing_text=filing_text,
    )

    candidate_n = max(n * 3, 10)

    gemini_result = _gemini_extract(
    parser_result=parser_result,
    n=candidate_n,
)

    if not gemini_result.get("products"):
        print(
            "Gemini returned no products. "
            "Retrying extraction once..."
        )

        gemini_result = _gemini_extract(
            parser_result=parser_result,
            n=n,
        )

    gemini_result["products"] = (
        _correct_product_revenues_from_source(
            products=gemini_result.get("products", []),
            parser_result=parser_result,
        )
    )
    

    fiscal_year = gemini_result.get("fiscal_year")

    validated_products = _validate_structured_products(
        products=gemini_result.get("products", []),
        parser_result=parser_result,
        n=candidate_n,
    )

    validated_products = sorted(
        validated_products,
        key=lambda product: (
            parse_money_value(
                product.get("revenue")
            )
            or 0
        ),
        reverse=True,
    )[:n]

    def _revenue_sort_value(product):
        value = product.get("revenue", 0)

        try:
            return float(
                str(value)
                .replace(",", "")
                .replace("$", "")
                .strip()
            )
        except (TypeError, ValueError):
            return 0.0


    validated_products = sorted(
        validated_products,
        key=_revenue_sort_value,
        reverse=True,
    )[:n]

    validated_total_revenue = _validate_total_company_revenue(
        total_revenue=gemini_result.get("total_company_revenue"),
        parser_result=parser_result,
    )

    metrics = calculate_revenue_concentration(
        products=validated_products,
        total_company_revenue=validated_total_revenue,
    )

    return {
        "fiscal_year": fiscal_year,
        "total_company_revenue": validated_total_revenue,
        "products": metrics["products"],
        "revenue_metrics": {
            "denominator_type": metrics["denominator_type"],
            "denominator_value": metrics["denominator_value"],
            "denominator_unit": metrics["denominator_unit"],
            "fiscal_year": metrics["fiscal_year"],
            "top_products_revenue": metrics[
                "top_products_revenue"
            ],
            "top_products_concentration_pct": metrics[
                "top_products_concentration_pct"
            ],
            "note": metrics["note"],
        },
        "parser_diagnostics": parser_result.get("diagnostics", {}),
    }


def _gemini_extract(
    parser_result: dict,
    n: int,
) -> dict:
    import json
    import os

    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    genai.configure(api_key=api_key)

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    )

    print(f"Using Gemini model: {model_name}")

    model = genai.GenerativeModel(model_name)

    expected_json = f"""
Return only valid JSON using this exact structure:

{{
  "fiscal_year": 2025,
  "total_company_revenue": {{
    "label": "Total Revenues",
    "value": "48194",
    "unit": "USD millions",
    "fiscal_year": 2025,
    "source_id": "section_2"
  }},
  "products": [
    {{
      "product": "Example Product",
      "revenue": "1000",
      "unit": "USD millions",
      "fiscal_year": 2025,
      "source_id": "table_1"
    }}
  ]
}}

Rules:
1. Return exactly {n} individual products when possible.
2. total_company_revenue must represent total revenue or total sales
   for the entire company.
3. Do not use segment revenue, pharmaceutical revenue, geographic
   revenue, portfolio revenue, or the sum of selected products as
   total company revenue.
4. Use the newest fiscal year available.
5. Do not select totals, segments, regions, therapeutic areas,
   portfolios, or "other products" categories as products.
6. Preserve source_id exactly.
7. Return null for total_company_revenue when total company revenue
   is unavailable.
8. Copy every reported revenue value exactly as it appears in the
   cited source.
9. Do not add, subtract, sum, round, estimate, or reconcile revenue
   values.
10. If a row contains U.S., Outside U.S., and Total values, use the
    reported Total value exactly rather than calculating U.S. plus
    Outside U.S.
11. If the reported Total value conflicts with the arithmetic sum of
    component values, trust the reported Total value in the filing.
12. Select the individual products with the HIGHEST reported revenue
    for the newest fiscal year.

13. Rank candidate products by their explicitly reported Total revenue
    for that fiscal year and return the top {n} products.

14. Do not select a lower-revenue product when a higher-revenue
    individual product is present in the supplied structured context.

15. When a product row contains geographic or component values plus a
    reported Total, use only the reported Total for ranking.

16. The goal is the top {n} individual products by reported fiscal-year
    revenue, not merely any {n} products found in the filing.
"""


    prompt = f"""
company's SEC 10-K filing.

{expected_json}

CRITICAL EXTRACTION RULE:
Never recompute a reported Total column.

If the filing reports U.S. = 13651, Outside U.S. = 9315,
and Total = 22965, return 22965 exactly even though the components
arithmetically sum to a different number.

The value explicitly reported in the SEC filing's Total column is
authoritative. Copy that value exactly. Do not correct it, recalculate
it, round it, or replace it with a mathematically derived value.

IMPORTANT: Identify the top {n} individual products by their explicitly
reported Total revenue for the newest fiscal year shown in the structured
context. Do not return lower-ranked products if higher-revenue products
are visible.

STRUCTURED FILING CONTEXT:
{parser_result["context"]}
"""

    response = model.generate_content(prompt)
    raw_text = response.text.strip()

    if raw_text.startswith("```json"):
        raw_text = raw_text[len("```json"):].strip()

    if raw_text.startswith("```"):
        raw_text = raw_text[len("```"):].strip()

    if raw_text.endswith("```"):
        raw_text = raw_text[:-3].strip()

    parsed = json.loads(raw_text)

    if not isinstance(parsed, dict):
        raise ValueError("Gemini response must be a JSON object.")

    products = parsed.get("products", [])

    if not isinstance(products, list):
        raise ValueError(
            "Gemini response field 'products' must be a list."
        )

    parsed["products"] = products[:n]

    return parsed

def _extract_product_source_evidence(
    source_content,
    product,
    revenue_match,
    max_quote_chars=350,
):
    """
    Return a compact evidence quote containing the validated revenue value
    and the nearest occurrence of the product name when possible.
    """

    if not source_content:
        return ""

    revenue_start = revenue_match.start()
    revenue_end = revenue_match.end()

    # Find every occurrence of the product rather than automatically
    # using the first occurrence in a flattened SEC table.
    product_matches = list(
        re.finditer(
            re.escape(product),
            source_content,
            flags=re.IGNORECASE,
        )
    )

    # Prefer the nearest occurrence of the product that appears
    # BEFORE the validated revenue value.
    product_match = None

    if product_matches:
        product_matches_before_revenue = [
            match
            for match in product_matches
            if match.start() <= revenue_start
        ]

        if product_matches_before_revenue:
            product_match = max(
                product_matches_before_revenue,
                key=lambda match: match.start(),
            )
        else:
            # Fallback only if no product occurrence exists before revenue.
            product_match = min(
                product_matches,
                key=lambda match: abs(match.start() - revenue_start),
            )

    # Always center the evidence around the VALIDATED revenue value.
    half_window = max_quote_chars // 2

    start = max(
        0,
        revenue_start - half_window,
    )

    end = min(
        len(source_content),
        revenue_end + half_window,
    )

    # If the nearest product occurrence is reasonably close, expand the
    # excerpt enough to include both the product and validated revenue.
    if product_match is not None:
        combined_start = min(
            product_match.start(),
            revenue_start,
        )

        combined_end = max(
            product_match.end(),
            revenue_end,
        )

        span = combined_end - combined_start

        if span <= max_quote_chars:
            remaining = max_quote_chars - span

            start = max(
                0,
                combined_start - remaining // 2,
            )

            end = min(
                len(source_content),
                combined_end + remaining // 2,
            )

        else:
            # Product and validated revenue are too far apart to fit into
            # one compact contiguous quote. Preserve both pieces explicitly.
            product_context_start = product_match.start()

            product_context_end = min(
                len(source_content),
                product_match.end() + 80,
            )

            revenue_context_start = max(
                0,
                revenue_start - 80,
            )

            revenue_context_end = min(
                len(source_content),
                revenue_end + 80,
            )

            product_context = source_content[
                product_context_start:product_context_end
            ]

            revenue_context = source_content[
                revenue_context_start:revenue_context_end
            ]

            evidence = (
                product_context
                + " ... "
                + revenue_context
            )

            evidence = re.sub(
                r"(?:\bnan\b\s*)+",
                " ",
                evidence,
                flags=re.IGNORECASE,
            )

            evidence = re.sub(
                r"\s+",
                " ",
                evidence,
            ).strip()

            return evidence[:max_quote_chars]

    evidence = source_content[start:end]

    # Remove pandas empty-cell placeholders.
    evidence = re.sub(
        r"(?:\bnan\b\s*)+",
        " ",
        evidence,
        flags=re.IGNORECASE,
    )

    # Normalize whitespace.
    evidence = re.sub(
        r"\s+",
        " ",
        evidence,
    ).strip()

    # Final safeguard: the quote must contain the exact revenue value that
    # Python validated. If trimming somehow excluded it, fall back to a
    # revenue-centered excerpt.
    revenue_text = revenue_match.group(0)

    if revenue_text not in evidence:
        start = max(
            0,
            revenue_start - max_quote_chars // 2,
        )

        end = min(
            len(source_content),
            revenue_end + max_quote_chars // 2,
        )

        evidence = source_content[start:end]

        evidence = re.sub(
            r"(?:\bnan\b\s*)+",
            " ",
            evidence,
            flags=re.IGNORECASE,
        )

        evidence = re.sub(
            r"\s+",
            " ",
            evidence,
        ).strip()

    return evidence[:max_quote_chars]


def _normalize_product_name(value: str) -> str:
    value = value.casefold().strip()

    # Remove common SEC footnote markers such as:
    # Zepbound(1), Eliquis(a), Product (b)
    value = re.sub(
        r"\s*\([a-z0-9]+\)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()

def _validate_structured_products(
    products,
    parser_result,
    n,
):
    """
    Validate Gemini product-revenue results against structured filing sources.

    Validation strategy:

    1. Check Gemini's cited source_id first.
    2. If that source does not contain enough evidence, search the other
       structured candidate tables and sections.
    3. Accept the product only when one structured source contains:
           - the product name
           - the exact reported revenue value
           - the fiscal year
    4. If a different source validates the result, replace Gemini's source_id
       with the source that actually contains the evidence.

    Python verifies Gemini's interpretation; it does not choose products or
    revenue values independently.
    """

    source_map = {}

    # Build lookup for candidate tables.
    for table in parser_result.get("tables", []):
        table_id = table.get("table_id")

        if not table_id:
            continue

        source_map[table_id] = {
            "source_type": "table",
            "content": "\n\n".join(
                part
                for part in [
                    table.get("plain_text"),
                    table.get("markdown"),
                    table.get("text"),
                ]
                if part
            ),
        }

    # Build lookup for candidate sections.
    for section in parser_result.get("sections", []):
        section_id = section.get("section_id")

        if not section_id:
            continue

        source_map[section_id] = {
            "source_type": "section",
            "content": (
                section.get("text")
                or section.get("markdown")
                or section.get("plain_text")
                or ""
            ),
        }

    validated = []
    seen_products = set()

    for item in products:
        if not isinstance(item, dict):
            print(
                "Rejected extraction because the item was not a dictionary:",
                item,
            )
            continue

        product = str(
            item.get("product", "")
        ).strip()

        revenue = str(
            item.get("revenue", "")
        ).strip()

        unit = str(
            item.get("unit", "")
        ).strip()

        claimed_source_id = str(
            item.get("source_id", "")
        ).strip()

        fiscal_year = item.get("fiscal_year")

        if (
            not product
            or not revenue
            or not unit
            or not claimed_source_id
        ):
            print(
                "Rejected extraction because product, revenue, unit, "
                "or source_id was missing:",
                item,
            )
            continue

        product_key = product.casefold()

        if product_key in seen_products:
            print(
                f"Rejected duplicate product: {product}"
            )
            continue

        if fiscal_year is None:
            print(
                f"Rejected {product}: fiscal year was missing."
            )
            continue

        try:
            fiscal_year = int(fiscal_year)

        except (TypeError, ValueError):
            print(
                f"Rejected {product}: invalid fiscal year "
                f"{fiscal_year!r}."
            )
            continue

        revenue_patterns = _make_exact_revenue_patterns(
            revenue
        )

        if not revenue_patterns:
            print(
                f"Rejected {product}: could not build a revenue "
                f"validation pattern for {revenue!r}."
            )
            continue

        year_pattern = re.compile(
            rf"(?<!\d){re.escape(str(fiscal_year))}(?!\d)"
        )

        def validate_against_source(source_id):
            """
            Return validation evidence if one candidate source contains
            product + revenue + fiscal year. Otherwise return None.
            """
            source = source_map.get(source_id)

            if source is None:
                return None

            source_content = source["content"]

            if product_key not in source_content.casefold():
                return None

            revenue_match = None

            for pattern in revenue_patterns:
                candidate_match = pattern.search(
                    source_content
                )

                if candidate_match is not None:
                    revenue_match = candidate_match
                    break

            if revenue_match is None:
                return None

            if not year_pattern.search(source_content):
                return None

            evidence = _extract_product_source_evidence(
                source_content=source_content,
                product=product,
                revenue_match=revenue_match,
            )

            return {
                "source_id": source_id,
                "source_type": source["source_type"],
                "source_quote": evidence,
            }

        # -----------------------------------------------------
        # Prefer a structured table over a section.
        # -----------------------------------------------------
        matched_source = None

        for table in parser_result.get("tables", []):
            candidate_source_id = table.get("table_id")

            if not candidate_source_id:
                continue

            candidate_match = validate_against_source(
                candidate_source_id
            )

            if candidate_match is not None:
                matched_source = candidate_match

                if candidate_source_id != claimed_source_id:
                    print(
                        f"Corrected source for {product}: "
                        f"Gemini cited {claimed_source_id}, "
                        f"validated against {candidate_source_id}."
                    )

                break

        # -----------------------------------------------------
        # Fall back to Gemini's cited source if no table worked.
        # -----------------------------------------------------
        if matched_source is None:
            matched_source = validate_against_source(
                claimed_source_id
            )

        # -----------------------------------------------------
        # Second choice: another structured candidate
        # -----------------------------------------------------
        if matched_source is None:
            for candidate_source_id in source_map:
                if candidate_source_id == claimed_source_id:
                    continue

                matched_source = validate_against_source(
                    candidate_source_id
                )

                if matched_source is not None:
                    print(
                        f"Corrected source for {product}: "
                        f"Gemini cited {claimed_source_id}, "
                        f"validated against {candidate_source_id}."
                    )
                    break

        # No structured evidence found
        if matched_source is None:
            print(
                f"Rejected {product}: could not validate product, "
                f"revenue {revenue!r}, and FY{fiscal_year} together "
                "in any structured candidate source."
            )
            continue

        validated_item = {
            "product": product,
            "revenue": revenue,
            "unit": unit,
            "fiscal_year": fiscal_year,
            "source_id": matched_source["source_id"],
            "source_type": matched_source["source_type"],
            "source_quote": matched_source["source_quote"],
        }

        validated.append(
            validated_item
        )

        seen_products.add(
            product_key
        )

        print(
            f"Validated {product}: "
            f"{revenue} {unit}, FY{fiscal_year}, "
            f"using {matched_source['source_id']}."
        )

        if len(validated) >= n:
            break

    return validated[:n]


from typing import Any

from tools.revenue_metrics import parse_money_value


TOTAL_REVENUE_LABELS = {
    "total revenues",
    "total revenue",
    "total sales",
    "net revenues",
    "net revenue",
    "net sales",
    "revenue",
    "revenues",
}


def _validate_total_company_revenue(
    total_revenue: dict[str, Any] | None,
    parser_result: dict[str, Any],
) -> dict[str, Any] | None:
    if not total_revenue:
        return None

    label = str(
        total_revenue.get("label", "")
    ).strip()

    value = str(
        total_revenue.get("value", "")
    ).strip()

    claimed_source_id = str(
        total_revenue.get("source_id", "")
    ).strip()

    fiscal_year = total_revenue.get(
        "fiscal_year"
    )

    if (
        not label
        or not value
        or not claimed_source_id
    ):
        return None

    normalized_label = label.lower()

    # Validate that Gemini identified a company-level label
    if not any(
        allowed in normalized_label
        for allowed in TOTAL_REVENUE_LABELS
    ):
        print(
            "Rejected total revenue because the label was not "
            f"company-level: {label}"
        )
        return None

    excluded_terms = (
        "pharmaceutical",
        "segment",
        "portfolio",
        "oncology",
        "geographic",
        "international",
        "united states",
        "product",
    )

    if any(
        term in normalized_label
        for term in excluded_terms
    ):
        print(
            "Rejected total revenue because it appears to be "
            f"segment-level: {label}"
        )
        return None

    # Basic numeric validation
    parsed_value = parse_money_value(value)

    if parsed_value is None or parsed_value <= 0:
        print(
            "Rejected total revenue because the value was invalid: "
            f"{value!r}"
        )
        return None

    # Build structured source map
    source_map = {}

    for table in parser_result.get("tables", []):
        table_id = table.get("table_id")

        if not table_id:
            continue

        # Keep both representations available.
        source_map[table_id] = {
            "source_type": "table",
            "content": "\n\n".join(
                part
                for part in [
                    table.get("plain_text"),
                    table.get("markdown"),
                    table.get("text"),
                    table.get("content"),
                ]
                if part
            ),
        }

    for section in parser_result.get("sections", []):
        section_id = section.get("section_id")

        if not section_id:
            continue

        source_map[section_id] = {
            "source_type": "section",
            "content": "\n\n".join(
                part
                for part in [
                    section.get("text"),
                    section.get("markdown"),
                    section.get("plain_text"),
                    section.get("content"),
                ]
                if part
            ),
        }

    normalized_value = (
        value.replace(",", "")
        .replace("$", "")
        .strip()
    )

    # Validate one candidate source
    def validate_against_source(
        candidate_source_id: str,
    ):
        source = source_map.get(
            candidate_source_id
        )

        if source is None:
            return None

        source_text = source["content"]

        normalized_source = (
            source_text.lower()
            .replace(",", "")
            .replace("$", "")
        )

        # Label must appear in the candidate source.
        if normalized_label not in normalized_source:
            return None

        # Exact reported value must appear.
        if normalized_value not in normalized_source:
            return None

        # Fiscal year must appear.
        if fiscal_year is not None:
            if str(fiscal_year) not in normalized_source:
                return None

        evidence = _extract_total_revenue_evidence(
            source_text=source_text,
            search_label=label,
            search_value=value,
        )

        return {
            "source_id": candidate_source_id,
            "source_type": source["source_type"],
            "source_quote": evidence,
        }

    # First choice: Gemini's cited source, if it is a table
    matched_source = None

    claimed_source = source_map.get(
        claimed_source_id
    )

    if (
        claimed_source is not None
        and claimed_source.get("source_type") == "table"
    ):
        matched_source = validate_against_source(
            claimed_source_id
        )

    # Second choice: any matching structured table
    if matched_source is None:
        for candidate_source_id, candidate_source in source_map.items():
            if candidate_source.get("source_type") != "table":
                continue

            if candidate_source_id == claimed_source_id:
                continue

            matched_source = validate_against_source(
                candidate_source_id
            )

            if matched_source is not None:
                print(
                    "Corrected source for total company revenue: "
                    f"Gemini cited {claimed_source_id}, "
                    f"validated against {candidate_source_id}."
                )
                break

    # Third choice: Gemini's cited prose section
    if matched_source is None:
        matched_source = validate_against_source(
            claimed_source_id
        )

    # Fourth choice: any other structured candidate
    if matched_source is None:
        for candidate_source_id in source_map:
            if candidate_source_id == claimed_source_id:
                continue

            matched_source = validate_against_source(
                candidate_source_id
            )

            if matched_source is not None:
                print(
                    "Corrected source for total company revenue: "
                    f"Gemini cited {claimed_source_id}, "
                    f"validated against {candidate_source_id}."
                )
                break

    # No structured evidence found
    if matched_source is None:
        print(
            "Rejected total revenue because no structured "
            "candidate source contained the label, value, "
            f"and FY{fiscal_year} together."
        )
        return None

    # Return validated result
    validated = dict(
        total_revenue
    )

    validated["source_id"] = (
        matched_source["source_id"]
    )

    validated["source_type"] = (
        matched_source["source_type"]
    )

    validated["source_quote"] = (
        matched_source["source_quote"]
    )

    print(
        f"Validated total company revenue: {value} "
        f"{total_revenue.get('unit', 'USD millions')}, "
        f"FY{fiscal_year}, using "
        f"{matched_source['source_id']}."
    )

    return validated



def _extract_total_revenue_evidence(
    source_text: str,
    search_label: str,
    search_value: str,
    radius: int = 300,
) -> str:
    if not source_text:
        return ""

    normalized_value = (
        str(search_value)
        .replace(",", "")
        .replace("$", "")
        .strip()
    )

    # Build equivalent value forms.
    value_forms = {
        normalized_value,
    }

    try:
        numeric_value = int(float(normalized_value))
        value_forms.add(str(numeric_value))
        value_forms.add(f"{numeric_value:,}")
    except (TypeError, ValueError):
        pass

    # Prefer locating the actual revenue value.
    value_index = -1

    for value_form in value_forms:
        match = re.search(
            rf"(?<![\d.,])\$?\s*{re.escape(value_form)}(?:\.0)?(?![\d.,])",
            source_text,
            flags=re.IGNORECASE,
        )

        if match:
            value_index = match.start()
            break

    # Fall back to the label only if the value cannot be found.
    if value_index == -1:
        lower_text = source_text.lower()
        value_index = lower_text.find(
            search_label.lower()
        )

    if value_index == -1:
        value_index = 0

    start = max(
        0,
        value_index - radius,
    )

    end = min(
        len(source_text),
        value_index + radius,
    )

    excerpt = source_text[start:end]

    # Remove pandas empty-cell placeholders.
    excerpt = re.sub(
        r"\bnan\b",
        "",
        excerpt,
        flags=re.IGNORECASE,
    )

    # Normalize whitespace.
    excerpt = re.sub(
        r"\s+",
        " ",
        excerpt,
    ).strip()

    return excerpt



def _make_exact_revenue_patterns(revenue):
    """
    Build exact regex patterns for a reported revenue value.

    Supports equivalent comma formatting:

        "14443"  -> matches "14443" and "14,443"
        "14,443" -> matches "14,443" and "14443"
        "$14,443" -> matches both formatspython run_cli.py BMY --json

    This function does NOT round, estimate, or change units.
    """

    revenue_text = str(revenue).strip()

    if not revenue_text:
        return []

    cleaned = (
        revenue_text
        .replace("$", "")
        .replace(",", "")
        .strip()
    )

    try:
        numeric_value = int(cleaned)
    except ValueError:
        # Handle decimal values without altering them.
        try:
            float(cleaned)
        except ValueError:
            return []

        patterns = [
            re.compile(
                rf"(?<![\d.,])"
                rf"{re.escape(cleaned)}"
                rf"(?![\d.,])",
                flags=re.IGNORECASE,
            )
        ]

        return patterns

    # Example:
    # 14443 -> "14443"
    plain_value = str(numeric_value)

    # Example:
    # 14443 -> "14,443"
    comma_value = f"{numeric_value:,}"

    candidate_values = {
        plain_value,
        comma_value,
    }

    patterns = []

    for candidate in candidate_values:
        patterns.append(
            re.compile(
                rf"(?<![\d.,])"
                rf"{re.escape(candidate)}"
                rf"(?![\d.,])",
                flags=re.IGNORECASE,
            )
        )

    return patterns

def _extract_source_evidence(
    source_content,
    product,
    revenue_match,
    surrounding_chars=500,
):
    """
    Return a compact excerpt containing the product and matched revenue value.
    """
    product_match = re.search(
        re.escape(product),
        source_content,
        flags=re.IGNORECASE,
    )

    if product_match is None:
        start = max(
            0,
            revenue_match.start() - surrounding_chars,
        )

        end = min(
            len(source_content),
            revenue_match.end() + surrounding_chars,
        )

        return source_content[start:end].strip()

    evidence_start = max(
        0,
        min(
            product_match.start(),
            revenue_match.start(),
        ) - surrounding_chars,
    )

    evidence_end = min(
        len(source_content),
        max(
            product_match.end(),
            revenue_match.end(),
        ) + surrounding_chars,
    )

    return source_content[
        evidence_start:evidence_end
    ].strip()


def _fallback_extract(filing_text, n):
    """Naive regex extractor — DEMO-GRADE ONLY (no validation, may misattribute).
    Finds 'Name ... $X million/billion' patterns. Replace with Gemini for real use."""
    focus = _focus_revenue(filing_text, 12000)
    pat = re.compile(
        r"([A-Z][A-Za-z0-9\-]{2,30})[^.\n]{0,40}?\$?\s?([\d,]+(?:\.\d+)?)\s?(million|billion)"
    )
    skip = {"the", "total", "net", "other", "united", "company", "revenues", "revenue"}
    seen, out = set(), []
    for m in pat.finditer(focus):
        name = m.group(1)
        if name.lower() in skip or name in seen:
            continue
        seen.add(name)
        out.append({
            "product": name,
            "revenue": f"${m.group(2)} {m.group(3)}",
            "source_quote": m.group(0).strip(),
        })
        if len(out) >= n:
            break
    return out


# Job 2: write the comparison brief
def write_brief(cards):
    """Return a Markdown comparison brief built from assembled issuer cards."""
    if _gemini_available():
        try:
            return _gemini_brief(cards)
        except Exception as e:
            print(f"Gemini brief generation failed: {e}")
    return _fallback_brief(cards)


def _gemini_brief(cards):
    import google.generativeai as genai

    genai.configure(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=(
            "You are a pharma equity analyst. Write a concise, investor-style "
            "comparison brief in Markdown. "
            "All revenue concentration calculations in the issuer cards have "
            "already been calculated deterministically by Python. "
            "Use those supplied calculations exactly. "
            "Do NOT recalculate revenue concentration percentages. "
            "Do NOT invent data that is not present in the input. "
            "Cite each revenue figure with its supplied source quote. "
            "Do not add a report date, analyst name, firm name, or other metadata "
            "unless it is explicitly present in the input."
            "Do not introduce company facts, customer concentration, market structure, "
            "competitive risks, wholesalers, distributors, growth rates, or other "
            "business commentary unless that information is explicitly present in the issuer card input."
        ),
    )

    # Generates the ranked tables
    ranked_rows = []

    for card in cards:
        issuer_name = card.get("name", "Unknown issuer")
        ticker = card.get("ticker", "")

        issuer_label = (
            f"{issuer_name} ({ticker})"
            if ticker
            else issuer_name
        )

        for product in card.get("products", []):
            pct = product.get("revenue_concentration_pct")

            if pct is None:
                continue

            try:
                pct_value = float(pct)
            except (TypeError, ValueError):
                continue

            ranked_rows.append(
                {
                    "issuer": issuer_label,
                    "product": product.get("product", "Unknown product"),
                    "revenue": product.get("revenue", "N/A"),
                    "pct": pct_value,
                }
            )

    ranked_rows.sort(
        key=lambda row: row["pct"],
        reverse=True,
    )

    table_lines = [
        "## Ranked Revenue Concentration Table",
        "",
        "| Product | Issuer | Revenue (USD millions) | % of Total Company Revenue |",
        "|---|---|---:|---:|",
    ]

    for row in ranked_rows:
        table_lines.append(
            f"| {row['product']} | "
            f"{row['issuer']} | "
            f"{row['revenue']} | "
            f"{row['pct']:.2f}% |"
        )

    ranked_revenue_table = "\n".join(table_lines)


    # Clean source quotes before sending issuer cards to Gemini.
    clean_cards = copy.deepcopy(cards)

    for card in clean_cards:
        total_revenue = card.get("total_company_revenue") or {}

        if total_revenue.get("source_quote"):
            total_revenue["source_quote"] = re.sub(
                r"\bnan\b",
                "",
                str(total_revenue["source_quote"]),
                flags=re.IGNORECASE,
            )

            total_revenue["source_quote"] = re.sub(
                r"\s+",
                " ",
                total_revenue["source_quote"],
            ).strip()

        for product in card.get("products", []):
            if product.get("source_quote"):
                product["source_quote"] = re.sub(
                    r"\bnan\b",
                    "",
                    str(product["source_quote"]),
                    flags=re.IGNORECASE,
                )

                product["source_quote"] = re.sub(
                    r"\s+",
                    " ",
                    product["source_quote"],
                ).strip()


    # Prompt for the LLM
    issuer_count = len(clean_cards)

    prompt = (
    "Issuer cards (JSON):\n"
        + json.dumps(clean_cards, indent=2)
        + "\n\n"
        f"The input contains exactly {issuer_count} issuer cards. "
        f"When stating the number of issuers analyzed, say exactly {issuer_count}. "
        "Do not infer or invent a different issuer count.\n\n"
        "Write a concise 1-2 page investor-style comparison brief.\n\n"

        "FINANCIAL CALCULATION RULES:\n"
        "1. Revenue extraction and source validation have already occurred.\n"
        "2. Revenue concentration percentages have already been calculated "
        "deterministically by Python.\n"
        "3. For each product, use the supplied "
        "`revenue_concentration_pct` value exactly.\n"
        "4. For the combined concentration of an issuer's selected products, "
        "use `revenue_metrics.top_products_concentration_pct` exactly.\n"
        "5. The denominator used for concentration is supplied in "
        "`revenue_metrics.denominator_value`.\n"
        "6. The denominator type is supplied in "
        "`revenue_metrics.denominator_type`.\n"
        "7. Do NOT calculate percentages yourself.\n"
        "8. Do NOT divide a product's revenue by the sum of the selected "
        "products.\n"
        "9. Do NOT substitute pharmaceutical-segment revenue, portfolio "
        "revenue, geographic revenue, therapeutic-area revenue, or another "
        "denominator for total company revenue.\n"
        "10. If `revenue_concentration_pct` is null, display N/A and explain "
        "that validated total company revenue was unavailable.\n"
        "11. If `top_products_concentration_pct` is null, do not estimate it.\n"
        "12. Preserve the fiscal year supplied in the issuer card.\n"
        "13. Keep every revenue number traceable to its supplied source.\n"
        "14. Do not invent missing revenue, pricing, exclusivity, indication, "
        "label, or other product information.\n"
        "15. Treat each enrichment source independently. A missing Orange Book "
        "match does not imply that NADAC, DailyMed, or RxNorm data is missing.\n"
        "16. Never say that a source has no match if the issuer card contains "
        "data from that source.\n"
        "17. When summarizing missing data, name only the specific source that "
        "is missing. For example, say 'Orange Book match not found' rather than "
        "'Orange Book and NADAC matches not found' if NADAC pricing is present.\n"
        "18. Treat the issuer cards as the complete factual source for the brief.\n"
        "19. Do not use outside knowledge, remembered company information, or facts "
        "that are not explicitly contained in the issuer cards.\n"
        "20. Do not infer customer concentration, wholesaler dependence, market share, "
        "portfolio risk, or competitive position unless the issuer card explicitly "
        "contains that information.\n"
        "21. A company or distributor name appearing only inside a DailyMed label "
        "title does not support claims about that company's customer relationships "
        "or regulatory information.\n\n"
        "22. When a supplied field is null or missing, display N/A rather than "
        "the literal words null, None, or an empty value.\n"
        "23. When discussing an issuer's combined top-products concentration, "
        "make clear that the percentage refers to all selected leading products "
        "in the issuer card, not just a subset of them.\n"
        "24. When discussing Orange Book data, describe the supplied dates as "
        "'regulatory exclusivity records' or 'apparent regulatory runway.' Do not "
        "state that commercial runway definitely extends to a date. Do not use "
        "subjective adjectives or comparative terms such as 'extensive', 'strong', "
        "'long', 'longer', 'short', 'shorter', 'significant', or similar qualitative "
        "descriptions of runway. Compare the supplied exclusivity dates directly instead.\n"
        "25. Keep SEC evidence quotes concise in the comparison brief. For product "
        "revenue evidence, the quote MUST include both the product name and its "
        "validated revenue value. Do not remove the product name when shortening an "
        "evidence quote. Preserve an ellipsis (`...`) when the supplied evidence uses "
        "one to connect the product-name fragment to the validated revenue fragment. "
        "For total-company revenue evidence, include the revenue metric name and its "
        "validated value. Exclude unrelated metrics such as net income, earnings per "
        "share, percentages, or unrelated table rows. Prefer roughly 5 to 20 words "
        "when possible.\n"
        "26. When NADAC pricing contains `nadac_display`, use that exact numeric "
        "display value in the brief. Describe it only as the 'NADAC price' or "
        "'NADAC unit price'. Never mention the field names `nadac_display` or "
        "`nadac_per_unit` anywhere in the brief, including in parentheses.\n"
        "27. Format revenue amounts as exactly '$X million', where X is the supplied "
        "revenue value formatted with thousands separators. Never place an additional "
        "currency symbol between the numeric value and the word 'million'.\n"
        "28. In multi-issuer comparison briefs, when DailyMed structured label data is "
        "available, include at least one concise comparison of supplied label content "
        "across issuers, such as differences in indications. Use only information "
        "contained in the issuer cards and do not infer clinical superiority.\n"

        "BRIEF STRUCTURE:\n"
        "1. Start with a short overall summary.\n"
        "2. Include a short section for each issuer.\n"
        "3. For each issuer, report validated total company revenue when "
        "available.\n"
        "4. Discuss the issuer's extracted leading products and their "
        "reported revenue.\n"
        "5. Include the supplied revenue concentration percentage for each "
        "product when available.\n"
        "6. Include relevant RxNorm, Orange Book, NADAC, and DailyMed "
        "information when present in the issuer card.\n"
        "7. Do NOT generate the ranked revenue concentration table yourself and "
        "do NOT write a heading for it. Insert only the exact placeholder "
        "[[RANKED_REVENUE_TABLE]] where that entire section should appear.\n"
        "8. The placeholder already includes the section heading and table. "
        "Do not add another heading before or after it, and do not alter, reproduce, "
        "reorder, or replace the placeholder with your own table.\n"
        "9. Label concentration as '% of Total Company Revenue'.\n"
        "10. Include a short Commercial Runway section based only on the supplied "
        "Orange Book exclusivity records.\n"
        "11. Compare products or issuers using the supplied Orange Book exclusivity "
        "dates when available. Treat later exclusivity dates as indicating longer "
        "apparent runway. Refer to these only as Orange Book exclusivity records or "
        "regulatory exclusivity records. Do not describe them as patent dates or patent "
        "exclusivities unless patent data is explicitly supplied in the issuer cards. "
        "Do not invent patent-expiry dates, generic-entry dates, or commercial "
        "assumptions that are not present in the issuer cards.\n"
        "12. If exclusivity data is unavailable for a product, state N/A rather than "
        "inferring runway from outside knowledge.\n"
        "13. Use N/A rather than calculating an alternative percentage when "
        "total company revenue is unavailable.\n"
        "14. End with a concise set of key takeaways supported by the input."
    )

    brief = model.generate_content(prompt).text

    if "[[RANKED_REVENUE_TABLE]]" in brief:
        brief = brief.replace(
            "[[RANKED_REVENUE_TABLE]]",
            ranked_revenue_table,
        )
    else:
        brief += "\n\n" + ranked_revenue_table

    return brief


def _fallback_brief(cards):
    """Deterministic Markdown brief used when Gemini is unavailable."""
    lines = ["# OpenLedger Comparison Brief", ""]

    if not _gemini_available():
        lines += [
            "> _Generated without Gemini (deterministic fallback). "
            "Set `GEMINI_API_KEY` for the analyst-written version._",
            "",
        ]

    for card in cards:
        lines.append(f"## {card['name']} ({card['ticker']})")

        meta = card.get("filing") or {}
        if meta:
            lines.append(
                f"*10-K filed {meta.get('filing_date')} — "
                f"{meta.get('doc_url')}*"
            )

        if not card.get("products"):
            lines.append("")
            lines.append("_No products extracted._")
            lines.append("")
            continue

        for product in card["products"]:
            product_name = product.get("product") or "Unknown product"
            revenue = product.get("revenue") or "—"
            unit = product.get("unit") or ""
            source = product.get("source_quote") or "—"

            rxnorm_data = product.get("rxnorm") or {}
            ingredient = rxnorm_data.get("ingredient") or "—"

            pricing_result = product.get("pricing") or {}
            pricing = pricing_result.get("pricing") or {}

            price = pricing.get("nadac_per_unit")
            pricing_unit = pricing.get("pricing_unit")
            effective_date = pricing.get("effective_date")

            if price is not None:
                price_text = f"${price} per {pricing_unit or 'unit'}"
                if effective_date:
                    price_text += f" as of {effective_date}"
            else:
                price_text = "No NADAC match"

            exclusivity_result = product.get("exclusivity") or {}
            exclusivity_records = exclusivity_result.get("exclusivity") or []

            exclusivity_dates = sorted({
                record.get("Exclusivity_Date")
                for record in exclusivity_records
                if record.get("Exclusivity_Date")
            })

            exclusivity_text = (
                ", ".join(exclusivity_dates)
                if exclusivity_dates
                else "No Orange Book exclusivity match"
            )

            label = product.get("label") or {}
            indications = label.get("indications") or "—"
            warning = (
                label.get("warning")
                or label.get("warnings_and_precautions")
                or "—"
            )

            lines.extend([
                "",
                f"### {product_name}",
                "",
                f"- **Revenue:** {revenue} {unit}".rstrip(),
                f"- **Ingredient:** {ingredient}",
                f"- **NADAC pricing:** {price_text}",
                f"- **Exclusivity dates:** {exclusivity_text}",
                f"- **Indications:** {indications}",
                f"- **Major warning:** {warning}",
                f"- **Revenue source:** {source}",
            ])

        if card.get("errors"):
            lines.append("")
            lines.append(
                f"<sub>diagnostics: {'; '.join(card['errors'])}</sub>"
            )

        lines.append("")

    return "\n".join(lines)


def _correct_product_revenues_from_source(
    products,
    parser_result,
):
    """
    Correct Gemini product revenue values using the explicitly reported
    Total value in the cited structured SEC table.

    Gemini still determines the product and source. Python only replaces
    the revenue when the cited table provides an unambiguous reported
    Total value for that product.
    """

    table_map = {
        table.get("table_id"): table
        for table in parser_result.get("tables", [])
        if table.get("table_id")
    }

    corrected_products = []

    for item in products:
        item = dict(item)

        product = str(
            item.get("product", "")
        ).strip()

        source_id = str(
            item.get("source_id", "")
        ).strip()

        if not product or not source_id:
            corrected_products.append(item)
            continue

        table = table_map.get(source_id)

        # If Gemini cited a section or the cited table does not contain
        # the product, search the other candidate tables for the product.
        if (
            table is None
            or product.casefold()
            not in str(table.get("plain_text", "")).casefold()
        ):
            table = None

            for candidate_table in parser_result.get("tables", []):
                candidate_text = str(
                    candidate_table.get("plain_text", "")
                )

                if product.casefold() in candidate_text.casefold():
                    table = candidate_table
                    source_id = candidate_table.get("table_id")
                    break

        if table is None:
            corrected_products.append(item)
            continue

        plain_text = str(
            table.get("plain_text", "")
        )

        # Only attempt correction when the cited table actually
        # contains the product.
        if product.casefold() not in plain_text.casefold():
            corrected_products.append(item)
            continue

        # Find the product's location.
        product_match = re.search(
            re.escape(product),
            plain_text,
            flags=re.IGNORECASE,
        )

        if product_match is None:
            corrected_products.append(item)
            continue

        # Limit the search to the product row / nearby text rather than
        # scanning the entire table for unrelated values.
        start = product_match.start()

        next_product_positions = []

        for other_item in products:
            other_product = str(
                other_item.get("product", "")
            ).strip()

            if (
                not other_product
                or other_product.casefold() == product.casefold()
            ):
                continue

            other_match = re.search(
                re.escape(other_product),
                plain_text[start + 1:],
                flags=re.IGNORECASE,
            )

            if other_match:
                next_product_positions.append(
                    start + 1 + other_match.start()
                )

        if next_product_positions:
            end = min(next_product_positions)
        else:
            end = min(
                len(plain_text),
                start + 1000,
            )

        product_context = plain_text[start:end]


        # Look for the reported Total value in the product context.
        # The parser repeats values, so grab numeric candidates and
        # compare them with Gemini's value. This helper should remain
        # conservative: only make a correction when a clear filing
        # total is identifiable.
        numbers = re.findall(
            r"(?<!\d)(\d{3,})(?!\d)",
            product_context,
        )

        gemini_revenue = str(
            item.get("revenue", "")
        ).replace(",", "").strip()

        # Special safeguard: if the SEC context contains a value that is
        # only 1 away from Gemini's value, prefer the SEC-reported value.
        # This handles filing totals such as:
        # U.S. 13651 + Outside U.S. 9315, reported Total 22965,
        # while Gemini incorrectly recomputes 22966.
        try:
            gemini_int = int(gemini_revenue)
        except ValueError:
            corrected_products.append(item)
            continue

        nearby_candidates = []

        for number in numbers:
            try:
                value = int(number)
            except ValueError:
                continue

            if abs(value - gemini_int) <= 1:
                nearby_candidates.append(value)

        if len(nearby_candidates) == 1:
            corrected_value = nearby_candidates[0]

            if corrected_value != gemini_int:
                print(
                    f"Corrected {product} revenue from "
                    f"{gemini_int} to {corrected_value} "
                    f"using {source_id}."
                )

                item["revenue"] = str(
                    corrected_value
                )

        corrected_products.append(item)

    return corrected_products

