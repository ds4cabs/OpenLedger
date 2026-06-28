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
def extract_top_product_revenue(filing_text, n=TOP_N_PRODUCTS):
    """Return [{'product', 'revenue', 'source_quote'}] for the top-n products."""
    if _gemini_available():
        try:
            return _gemini_extract(filing_text, n)
        except Exception:
            pass  # fall through to deterministic extractor
    return _fallback_extract(filing_text, n)


def _gemini_extract(filing_text, n):
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=(
            "You extract product-level revenue from SEC 10-K text. "
            "Return STRICT JSON only. NEVER invent numbers; if unsure, omit the item. "
            "Every item MUST include the exact source sentence you used."
        ),
    )
    prompt = (
        f"From the 10-K text below, extract the top {n} products by revenue.\n"
        'Return JSON exactly as: '
        '{"products":[{"product":"...","revenue":"...","source_quote":"..."}]}\n\n'
        f"TEXT:\n{_focus_revenue(filing_text)}"
    )
    raw = model.generate_content(prompt).text.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.M).strip()
    return json.loads(raw).get("products", [])[:n]


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


# --------------------------------------------------------------------------- #
# Job 2: write the comparison brief
# --------------------------------------------------------------------------- #
def write_brief(cards):
    """Return a Markdown comparison brief built from assembled issuer cards."""
    if _gemini_available():
        try:
            return _gemini_brief(cards)
        except Exception:
            pass
    return _fallback_brief(cards)


def _gemini_brief(cards):
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=(
            "You are a pharma equity analyst. Write a concise, investor-style "
            "comparison brief in Markdown. Cite each revenue figure with its source "
            "quote. Do NOT invent data that is not present in the input."
        ),
    )
    prompt = (
        "Issuer cards (JSON):\n" + json.dumps(cards, indent=2) +
        "\n\nWrite a 1-2 page comparison brief: a short summary per issuer, then a "
        "ranked table by revenue concentration. Keep every number traceable to its source."
    )
    return model.generate_content(prompt).text


def _fallback_brief(cards):
    """Deterministic Markdown brief (used when Gemini is unavailable)."""
    lines = ["# OpenLedger Comparison Brief", ""]
    if not _gemini_available():
        lines += ["> _Generated without Gemini (deterministic fallback). "
                  "Set `GEMINI_API_KEY` for the analyst-written version._", ""]
    for c in cards:
        lines.append(f"## {c['name']} ({c['ticker']})")
        meta = c.get("filing") or {}
        if meta:
            lines.append(f"*10-K filed {meta.get('filing_date')} — "
                         f"{meta.get('doc_url')}*")
        if c["products"]:
            lines.append("")
            lines.append("| Product | Revenue | Ingredient (RxNorm) | Source |")
            lines.append("|---|---|---|---|")
            for p in c["products"]:
                ing = (p.get("rxnorm") or {}).get("ingredient") or "—"
                src = (p.get("source_quote") or "").replace("|", "\\|")[:80]
                lines.append(f"| {p.get('product')} | {p.get('revenue')} | {ing} | {src} |")
        else:
            lines.append("\n_No products extracted._")
        if c.get("errors"):
            lines.append(f"\n<sub>diagnostics: {'; '.join(c['errors'])}</sub>")
        lines.append("")
    return "\n".join(lines)
