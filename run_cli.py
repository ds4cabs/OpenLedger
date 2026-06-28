"""Headless runner — build a brief without Streamlit (useful for testing / CI).

Examples:
    python run_cli.py PFE --sample
    python run_cli.py PFE MRK            # live SEC (needs non-blocked IP)
"""
import argparse
import json

import pipeline


def main():
    ap = argparse.ArgumentParser(description="OpenLedger CLI")
    ap.add_argument("tickers", nargs="+", help="Issuer tickers, e.g. PFE MRK")
    ap.add_argument("--sample", action="store_true",
                    help="Use bundled sample filing (offline; skips SEC)")
    ap.add_argument("--out", default="openledger_brief.md", help="Output Markdown path")
    ap.add_argument("--json", action="store_true", help="Also print raw card JSON")
    args = ap.parse_args()

    result = pipeline.build_comparison(args.tickers, use_sample=args.sample)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(result["brief_markdown"])
    print(f"Wrote {args.out}\n")
    print(result["brief_markdown"])
    if args.json:
        print("\n--- RAW CARDS ---")
        print(json.dumps(result["cards"], indent=2))


if __name__ == "__main__":
    main()
