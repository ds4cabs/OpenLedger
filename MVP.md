# OpenLedger — MVP Version (Gemini AI Agent · Interactive Dashboard)

**Intern:** Shawn Phan
**Level:** USF undergrad (Data Science), Intermediate Python
**Timeline:** 2–3 weeks (~48 hours)
**Paradigm:** **Interactive Dashboard** — Streamlit dashboard with issuer selectors, 10-K-derived commercial cards, Gemini-as-parser for revenue extraction.
**Database count:** **6** (expanded from 4 to add DailyMed for detailed top-product labels and RxNorm for cross-source drug normalization).

---

## The Agent

**What the agent does (two autonomous workflow points):**

1. **At ingestion:** Gemini parses 10-K filings to extract top-product revenue (LLM-as-parser, no XBRL).
2. **On user click:** agent calls 6 public databases to assemble issuer cards and synthesize comparison briefs.

**Input:** Issuer selection via Streamlit.
**Output:** Interactive cards + downloadable comparison brief.

**Tools (6 public databases):**

1. `get_10k_filing(issuer_ticker)` — **SEC EDGAR**.
2. `get_top_products_fda(issuer_name)` — **openFDA Drugs@FDA**.
3. `get_orange_book_exclusivity(drug_name)` — **FDA Orange Book**.
4. `get_drug_pricing(drug_name)` — **CMS NADAC**.
5. `get_dailymed_label(drug_name)` — **DailyMed API**: full label for top products (boxed warnings, indications, dosing — material for valuation).
6. `get_rxnorm_normalize(drug_name)` — **RxNorm API**: drug-name normalization across SEC filings (brand names) and FDA databases (generic / ingredient names).

Plus utility: `extract_top_product_revenue(filing_text, n=3)` via Gemini (LLM-as-parser).

**Example runs (≥3):**

- *Selection:* Pfizer alone. *Cards:* top-3-product revenue (LLM-parsed 10-K), FDA approval data, exclusivity windows, pricing, **full structured labels** for top products. *Brief:* single-issuer commercial card.
- *Selection:* Pfizer + Merck. *Brief:* comparative brief with normalized drug names across sources (RxNorm) and label content comparison (DailyMed).
- *Selection:* all 5 issuers. *Brief:* class brief ranked by revenue concentration and runway.

---

## Week-by-Week

**Week 1 (~16h):** Build 6 tool functions + Gemini-as-parser utility. Test on 5 issuers.
**Week 2 (~22h):** Clone dashboard sub-template. Streamlit UI + Gemini agent.
**Week 3 (~10h):** Test 3 interactions; PDF export; demo.

## What's OUT

10-Q/8-K filings, 200+ issuers, Medicaid Drug Pricing, ClinicalTrials.gov pipeline scanner, Europe PMC, daily-refreshed dashboard, 1,800-product matching.

## Stretch Goals

- 7th tool: `get_clinical_trials(issuer)` for competitive pipeline scan tab.

## Realistic CV Entry

*Built OpenLedger, a working interactive Streamlit dashboard with embedded Gemini AI agent integrating 6 public databases for pharma commercial intelligence.*

- Wrapped 6 public databases (SEC EDGAR, openFDA Drugs@FDA, FDA Orange Book, CMS NADAC, DailyMed, RxNorm) plus a Gemini-as-parser utility into a Streamlit dashboard.
- Built drug-name normalization across SEC filings and FDA databases using RxNorm, enabling clean issuer-to-product joins.

## Tech Stack

Python, `google-generativeai`, Streamlit, requests, pandas, markdown-pdf, SEC EDGAR API, openFDA / Drugs@FDA, FDA Orange Book, CMS Open Data, DailyMed API, RxNorm API.

---

## Shared Agent Skeleton (three paradigms, one Gemini primitive)

Every intern's agent uses Gemini's automatic function calling, but the interface layer differs by paradigm. The cohort uses **one starter repo with three sub-templates** that interns clone in week 1:

- **Dossier-generator template** — CLI script: takes structured args, runs the agent workflow autonomously, writes `*.md` + `*.json` to disk. Used by Beyza, Chin Hung, Christina, Shucheng, Xiaoxue.
- **Dashboard template** — Streamlit page with selectors and tables; the agent is invoked on button-click for specific synthesis tasks. Used by Aaron, Jason, Shawn.
- **Computation-engine template** — Streamlit form (or CLI) that takes structured analytical inputs, runs the agent workflow, produces a downloadable analytical report with plots. Used by Reuben, Kening, Natalie.

**Why no chat interfaces?** Scientists need reproducible, shareable artifacts. The agent dimension (Gemini-as-orchestrator, autonomous tool-calling across multiple public databases, synthesis across sources) is preserved in all three paradigms; only the deliverable shape changes.

**Christina** (OpenRepurpose evidence-and-validation module) owns the starter repo with all three sub-templates. The shared repo should also include pre-built wrappers for the most heavily-used databases (ChEMBL, openFDA FAERS, Open Targets, ClinVar) so multiple interns don't redo the same boilerplate.

### Reference snippet — Gemini function calling (same across all three paradigms)

```python
import google.generativeai as genai
import os
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

def my_tool(arg: str) -> dict:
    """One-line docstring Gemini uses to decide when to call this tool."""
    return {"result": ...}

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    tools=[my_tool, other_tool, ...],   # 4-8 tools per agent
    system_instruction=open("system_prompt.md").read(),
)
chat = model.start_chat(enable_automatic_function_calling=True)
response = chat.send_message("structured request — one shot, not a conversation")
```
