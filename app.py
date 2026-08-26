"""OpenLedger PoC v1 — Streamlit dashboard.

Run:  streamlit run app.py

Flow: select issuer(s) -> SEC 10-K -> product revenue (Gemini-as-parser) ->
FDA / RxNorm / label enrichment -> issuer cards + downloadable comparison brief.
"""
import os
import io
import streamlit as st
import re
from markdown_pdf import MarkdownPdf, Section

from config import ISSUERS
import pipeline

def markdown_to_pdf(markdown_text: str) -> bytes:
    pdf = MarkdownPdf()

    pdf.add_section(
        Section(
            markdown_text,
            toc=False,
        )
    )

    output = io.BytesIO()
    pdf.save_bytes(output)

    return output.getvalue()

st.set_page_config(page_title="OpenLedger", layout="wide")
st.title("OpenLedger — Pharma Commercial Intelligence MVP")
st.caption("SEC 10-K → product revenue (Gemini-as-parser) → FDA / RxNorm enrichment → comparison brief")

with st.sidebar:
    st.header("Settings")
    use_sample = st.checkbox(
        "Use bundled sample filing (offline demo)", value=False,
        help="Skips SEC (which blocks some IPs). Uses an illustrative 10-K excerpt.")
    st.write("**Gemini:**", "enabled ✅" if os.environ.get("GEMINI_API_KEY")
             else "not set — using deterministic fallback")
    st.caption("Set GEMINI_API_KEY in the environment to enable the LLM parser/brief.")

selected = st.multiselect(
    "Select issuer(s):", options=list(ISSUERS.keys()),
    format_func=lambda t: f"{t} — {ISSUERS[t]['name']}", default=["PFE"])

if st.button("Build", type="primary") and selected:
    with st.spinner("Assembling issuer cards…"):
        result = pipeline.build_comparison(selected, use_sample=use_sample)

    for card in result["cards"]:
        st.subheader(f"{card['name']} ({card['ticker']})")

        meta = card.get("filing") or {}

        if meta:
            st.caption(
                f"10-K filed {meta.get('filing_date')} · "
                f"{meta.get('doc_url')}"
            )

        total_revenue = card.get("total_company_revenue") or {}
        revenue_metrics = card.get("revenue_metrics") or {}

        total_value = total_revenue.get("value")
        top_products_revenue = revenue_metrics.get(
            "top_products_revenue"
        )
        concentration = revenue_metrics.get(
            "top_products_concentration_pct"
        )

        fiscal_year = (
            card.get("fiscal_year")
            or total_revenue.get("fiscal_year")
            or "N/A"
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            if total_value:
                clean_total = str(total_value).replace(",", "")
                st.metric(
                    f"FY{fiscal_year} Total Revenue",
                    f"${float(clean_total):,.0f}M",
                )
            else:
                st.metric(
                    f"FY{fiscal_year} Total Revenue",
                    "N/A",
                )

        with col2:
            if top_products_revenue:
                clean_top = str(
                    top_products_revenue
                ).replace(",", "")

                st.metric(
                    "Top Products Revenue",
                    f"${float(clean_top):,.0f}M",
                )
            else:
                st.metric(
                    "Top Products Revenue",
                    "N/A",
                )

        with col3:
            if concentration is not None:
                st.metric(
                    "Top Products Concentration",
                    f"{float(concentration):.2f}%",
                )
            else:
                st.metric(
                    "Top Products Concentration",
                    "N/A",
                )

        if card.get("products"):
            st.markdown("#### Leading Products")

            product_rows = []

            for product in card["products"]:
                revenue = product.get("revenue")

                if revenue:
                    clean_revenue = str(
                        revenue
                    ).replace(",", "")

                    revenue_display = (
                        f"{float(clean_revenue):,.0f}"
                    )
                else:
                    revenue_display = "—"

                pct = product.get(
                    "revenue_concentration_pct"
                )

                product_rows.append(
                    {
                        "Product": product.get("product"),
                        "Revenue ($M)": revenue_display,
                        "% of Total Revenue": (
                            f"{float(pct):.2f}%"
                            if pct is not None
                            else "—"
                        ),
                        "Ingredient": (
                            (product.get("rxnorm") or {})
                            .get("ingredient")
                            or "N/A"
                        ),
                    }
                )

            st.table(product_rows)

            st.markdown("#### Product Details")

            for product in card["products"]:
                product_name = product.get(
                    "product",
                    "Unknown product",
                )

                with st.expander(product_name):
                    rxnorm_data = (
                        product.get("rxnorm")
                        or {}
                    )

                    label_data = (
                        product.get("label")
                        or {}
                    )

                    exclusivity_data = (
                        product.get("exclusivity")
                        or {}
                    )

                    pricing_data = (
                        product.get("pricing")
                        or {}
                    )

                    st.write(
                        "**SEC financial name:**",
                        product_name,
                    )

                    st.write(
                        "**Lookup name:**",
                        product.get("lookup_name")
                        or "—",
                    )

                    st.write(
                        "**RxNorm ingredient:**",
                        rxnorm_data.get("ingredient")
                        or "—",
                    )

                    st.write(
                        "**DailyMed label:**",
                        label_data.get("title")
                        or "—",
                    )

                    if label_data.get("url"):
                        st.markdown(
                            f"[Open full DailyMed label]"
                            f"({label_data['url']})"
                        )

                    st.markdown(
                        "##### DailyMed Structured Label"
                    )

                    if label_data.get("warning"):
                        st.markdown(
                            "**Boxed Warning**"
                        )
                        st.write(
                            label_data["warning"]
                        )
                    else:
                        st.write(
                            "**Boxed Warning:** N/A"
                        )

                    if label_data.get("indications"):
                        st.markdown(
                            "**Indications and Usage**"
                        )
                        st.write(
                            label_data["indications"]
                        )
                    else:
                        st.write(
                            "**Indications and Usage:** N/A"
                        )

                    if label_data.get("dosage"):
                        st.markdown(
                            "**Dosage and Administration**"
                        )
                        st.write(
                            label_data["dosage"]
                        )
                    else:
                        st.write(
                            "**Dosage and Administration:** N/A"
                        )

                    if label_data.get("contraindications"):
                        st.markdown(
                            "**Contraindications**"
                        )
                        st.write(
                            label_data["contraindications"]
                        )
                    else:
                        st.write(
                            "**Contraindications:** N/A"
                        )

                    if label_data.get(
                        "warnings_and_precautions"
                    ):
                        st.markdown(
                            "**Warnings and Precautions**"
                        )
                        st.write(
                            label_data[
                                "warnings_and_precautions"
                            ]
                        )
                    else:
                        st.write(
                            "**Warnings and Precautions:** N/A"
                        )

                    exclusivity_records = (
                        exclusivity_data.get(
                            "exclusivity"
                        )
                        or []
                    )

                    if exclusivity_records:
                        st.write(
                            "**Orange Book exclusivity:**"
                        )

                        st.table(
                            [
                                {
                                    "Ingredient": r.get(
                                        "Ingredient"
                                    ),
                                    "Trade Name": r.get(
                                        "Trade_Name"
                                    ),
                                    "Code": r.get(
                                        "Exclusivity_Code"
                                    ),
                                    "Date": r.get(
                                        "Exclusivity_Date"
                                    ),
                                }
                                for r
                                in exclusivity_records
                            ]
                        )
                    else:
                        st.write(
                            "**Orange Book exclusivity:** "
                            "No match found."
                        )

                    pricing = pricing_data.get(
                        "pricing"
                    )

                    if pricing:
                        st.write(
                            "**NADAC pricing:** "
                            f"{pricing.get('ndc_description', '—')} — "
                            f"${pricing.get('nadac_per_unit', '—')} "
                            f"per {pricing.get('pricing_unit', 'unit')} "
                            f"(effective "
                            f"{pricing.get('effective_date', '—')})"
                        )
                    else:
                        st.write(
                            "**NADAC pricing:** "
                            "No match found."
                        )

                    st.write(
                        "**SEC source:**",
                        product.get("source_id")
                        or "—",
                    )

                    source_quote = (
                        product.get("source_quote")
                        or "No source quote available."
                    )

                    clean_quote = re.sub(
                        r"\bnan\b",
                        "",
                        str(source_quote),
                        flags=re.IGNORECASE,
                    )

                    clean_quote = re.sub(
                        r"\s+",
                        " ",
                        clean_quote,
                    ).strip()

                    st.code(clean_quote)


        else:
            st.info(
                "No products extracted "
                "(check SEC access / GEMINI_API_KEY, "
                "or enable the sample filing in the sidebar)."
            )

        if card.get("fda_products_sample"):
            with st.expander(
                f"openFDA products for "
                f"{card['name']} (sample)"
            ):
                st.table(
                    card["fda_products_sample"]
                )

        if card.get("errors"):
            with st.expander("Diagnostics"):
                st.write(
                    card["errors"]
                )

    st.markdown("---")
    st.header("Comparison Brief")

    brief_markdown = result["brief_markdown"]
    brief_display = brief_markdown.replace("$", r"\$")

    st.markdown(brief_display)

    st.download_button(
        "⬇ Download brief (Markdown)",
        brief_markdown,
        file_name="openledger_brief.md",
        mime="text/markdown",
    )

    pdf_bytes = markdown_to_pdf(brief_markdown)

    st.download_button(
        "⬇ Download brief (PDF)",
        data=pdf_bytes,
        file_name="openledger_brief.pdf",
        mime="application/pdf",
    )