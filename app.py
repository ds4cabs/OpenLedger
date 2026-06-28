"""OpenLedger PoC v1 — Streamlit dashboard.

Run:  streamlit run app.py

Flow: select issuer(s) -> SEC 10-K -> product revenue (Gemini-as-parser) ->
FDA / RxNorm / label enrichment -> issuer cards + downloadable comparison brief.
"""
import os
import streamlit as st

from config import ISSUERS
import pipeline

st.set_page_config(page_title="OpenLedger", layout="wide")
st.title("OpenLedger — Pharma Issuer Cards (PoC v1)")
st.caption("SEC 10-K → product revenue (Gemini-as-parser) → FDA / RxNorm enrichment → comparison brief")

with st.sidebar:
    st.header("Settings")
    use_sample = st.checkbox(
        "Use bundled sample filing (offline demo)", value=True,
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
            st.caption(f"10-K filed {meta.get('filing_date')} · {meta.get('doc_url')}")
        if card["products"]:
            st.table([{
                "Product": p.get("product"),
                "Revenue": p.get("revenue"),
                "Ingredient (RxNorm)": (p.get("rxnorm") or {}).get("ingredient") or "—",
                "Label": (p.get("label") or {}).get("title") or "—",
                "Source quote": (p.get("source_quote") or "")[:90],
            } for p in card["products"]])
        else:
            st.info("No products extracted (check SEC access / GEMINI_API_KEY, "
                    "or enable the sample filing in the sidebar).")
        if card.get("fda_products_sample"):
            with st.expander(f"openFDA products for {card['name']} (sample)"):
                st.table(card["fda_products_sample"])
        if card.get("errors"):
            with st.expander("Diagnostics"):
                st.write(card["errors"])

    st.markdown("---")
    st.header("Comparison Brief")
    st.markdown(result["brief_markdown"])
    st.download_button("⬇ Download brief (Markdown)", result["brief_markdown"],
                       file_name="openledger_brief.md", mime="text/markdown")
