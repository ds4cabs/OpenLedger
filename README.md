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
