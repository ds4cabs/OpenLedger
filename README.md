# OpenLedger

[![CABS: ds4cabs](https://img.shields.io/badge/CABS-ds4cabs-1f4b99?logo=github)](https://github.com/ds4cabs)
[![GitHub Pages: live](https://img.shields.io/badge/GitHub_Pages-live-brightgreen?logo=github)](https://ds4cabs.github.io/OpenLedger/)
![CABS: 2026](https://img.shields.io/badge/CABS-2026-6f42c1)
![status: MVP in progress](https://img.shields.io/badge/status-MVP_in_progress-f1c40f)
![type: Interactive Dashboard](https://img.shields.io/badge/type-Interactive_Dashboard-1f6feb)
![domain: Pharma Finance](https://img.shields.io/badge/domain-Pharma_Finance-0aa)

**Intern:** Shawn Phan
**Project Type:** Interactive Dashboard

## Overview
OpenLedger is a pharma commercial analytics dashboard that combines issuer filings, product-level FDA data, pricing, exclusivity, and label information to produce investor-style issuer cards and briefs.

## Deliverable
- Streamlit dashboard for issuer selection
- Issuer cards with top-product revenue, FDA product data, pricing, and exclusivity
- Downloadable comparison brief with normalized drug names across sources

## Core Tools
- SEC EDGAR
- Drugs@FDA (openFDA)
- FDA Orange Book
- CMS NADAC
- DailyMed
- RxNorm

## Tech Stack
Python, Streamlit, `google-generativeai`, pandas, requests, markdown export

## Notes
This project emphasizes issuer-level synthesis and drug-name normalization for comparative briefs.

---

## Getting Started — PoC v1 (starter code by ds4cabs)

This repo now contains a **runnable proof-of-concept** so you (Shawn) can build on a
working base instead of starting from a blank page. It's deliberately scoped per the
PoC strategy in issue #5: Pfizer-first, a few solid wrappers, a thin LLM layer, and a
downloadable brief. **Make it better — don't treat it as finished.**

### Run it
```bash
pip install -r requirements.txt

# Dashboard (recommended):
streamlit run app.py
#   -> in the sidebar, "Use bundled sample filing" is ON by default so it works
#      offline / even where SEC blocks the IP and even without a Gemini key.

# Or headless:
python run_cli.py PFE --sample        # offline demo
python run_cli.py PFE MRK             # live SEC (run from Colab; SEC blocks many cloud IPs)
```

### Enable Gemini (optional but recommended)
```bash
export GEMINI_API_KEY=your_key
```
Without it, the app uses a **deterministic regex fallback** so it always runs. With it,
Gemini does the two real jobs: parsing 10-K revenue and writing the brief.

### Architecture (what each file does)
| File | Role |
|---|---|
| `config.py` | Issuer universe (ticker → CIK → FDA sponsor), model name, knobs |
| `tools/sec_edgar.py` | Fetch latest 10-K text (+ offline `get_sample_filing`) |
| `tools/drugs_fda.py` | openFDA Drugs@FDA — sponsor's products ✅ |
| `tools/rxnorm.py` | RxNorm — brand → ingredient cross-walk ✅ |
| `tools/dailymed.py` | DailyMed — label lookup ✅ |
| `tools/orange_book.py` | Exclusivity — **STUB/TODO** (no REST API) |
| `tools/nadac.py` | CMS pricing — **STUB/TODO** (needs NDC mapping) |
| `agent.py` | The only LLM code: `extract_top_product_revenue`, `write_brief` (+ fallbacks) |
| `pipeline.py` | Deterministic orchestration: build cards + comparison |
| `app.py` | Streamlit dashboard | `run_cli.py` | headless runner |

### What works now vs. your TODO list
**Works:** end-to-end flow (10-K → top-3 product revenue → RxNorm/label enrichment →
issuer cards → downloadable Markdown brief), with offline sample + Gemini-optional design.

**Your next steps (good first Linear issues):**
1. Implement `tools/orange_book.py` (download + join the Orange Book data files).
2. Implement `tools/nadac.py` (RxNorm → NDC → CMS NADAC price).
3. Pull real label text (boxed warnings / indications) in `tools/dailymed.py`.
4. Add **source-span verification** for revenue numbers (the reliability story — see issue #6).
5. PDF export of the brief (`markdown-pdf`).
6. Verify all 5 issuers live from Colab; hand-check extracted revenue vs. the filings.

> ⚠️ `sample_data/PFE_10k_excerpt.txt` is **illustrative, not authoritative** — for offline
> demo only. Use the real SEC 10-K for any actual analysis.
