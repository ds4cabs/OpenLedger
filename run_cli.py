"""
Headless runner for OpenLedger.

Normal examples:
    python run_cli.py PFE --sample
    python run_cli.py PFE MRK
    python run_cli.py PFE --json

Filing-parser inspection:
    python run_cli.py PFE --inspect-filing

The --inspect-filing option downloads one live SEC filing, extracts candidate
revenue tables and sections, prints them, and exits before invoking Gemini or
the remaining OpenLedger enrichment pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys

import pipeline
from tools import filing_parser, sec_edgar

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="replace",
    )
def _build_argument_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command-line argument parser.
    """
    parser = argparse.ArgumentParser(
        description="OpenLedger CLI",
    )

    parser.add_argument(
        "tickers",
        nargs="+",
        help="Issuer tickers, such as PFE or PFE MRK",
    )

    parser.add_argument(
        "--sample",
        action="store_true",
        help=(
            "Use a bundled sample filing instead of downloading a live "
            "SEC filing."
        ),
    )

    parser.add_argument(
        "--out",
        default="openledger_brief.md",
        help="Output path for the generated Markdown brief.",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Also print the raw issuer-card JSON.",
    )

    parser.add_argument(
        "--inspect-filing",
        action="store_true",
        help=(
            "Inspect candidate revenue tables and text sections from one "
            "filing without calling Gemini or building an issuer card."
        ),
    )

    parser.add_argument(
        "--top-tables",
        type=int,
        default=4,
        help=(
            "Maximum number of candidate tables to show in filing inspection "
            "mode. Default: 4."
        ),
    )

    parser.add_argument(
        "--top-sections",
        type=int,
        default=3,
        help=(
            "Maximum number of narrative sections to show in filing "
            "inspection mode. Default: 3."
        ),
    )

    parser.add_argument(
        "--save-parser-context",
        default=None,
        help=(
            "Optional path where the complete structured parser context "
            "will be saved during filing inspection."
        ),
    )

    return parser


def _validate_arguments(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    """
    Validate combinations and values supplied on the command line.
    """
    if args.inspect_filing and len(args.tickers) != 1:
        parser.error(
            "--inspect-filing accepts exactly one ticker at a time."
        )

    if args.inspect_filing and args.sample:
        parser.error(
            "--inspect-filing requires a live SEC HTML filing. "
            "The bundled sample is plain text and does not contain HTML tables."
        )

    if args.top_tables < 0:
        parser.error("--top-tables cannot be negative.")

    if args.top_sections < 0:
        parser.error("--top-sections cannot be negative.")


def _print_table_candidate(table: dict) -> None:
    """
    Print one ranked candidate table.
    """
    print("\n" + "=" * 90)
    print(
        f"{table['table_id']} | "
        f"score={table['score']} | "
        f"{table['row_count']} rows x "
        f"{table['column_count']} columns"
    )

    reasons = table.get("reasons") or []

    if reasons:
        print("Ranking reasons:")
        for reason in reasons:
            print(f"  - {reason}")

    print("-" * 90)
    print(table["markdown"])
    print("=" * 90)


def _print_section_candidate(section: dict) -> None:
    """
    Print one ranked candidate narrative section.
    """
    print("\n" + "=" * 90)
    print(
        f"{section['section_id']} | "
        f"score={section['score']} | "
        f"matched phrase={section['matched_term']!r}"
    )

    heading = section.get("heading") or "(no heading detected)"
    print(f"Nearby heading: {heading}")

    reasons = section.get("reasons") or []

    if reasons:
        print("Ranking reasons:")
        for reason in reasons:
            print(f"  - {reason}")

    print("-" * 90)
    print(section["text"])
    print("=" * 90)


def _save_parser_context(
    path: str,
    context: str,
) -> None:
    """
    Save the exact structured context that would later be sent to Gemini.
    """
    with open(path, "w", encoding="utf-8") as file:
        file.write(context)

    print(f"\nSaved parser context to: {path}")


def inspect_filing(
    ticker: str,
    top_tables: int,
    top_sections: int,
    save_context_path: str | None,
) -> int:
    """
    Download and inspect one SEC filing.

    Returns:
        0 when inspection completes successfully.
        1 when downloading or parsing fails.
    """
    normalized_ticker = ticker.strip().upper()

    print(f"Downloading latest 10-K for {normalized_ticker}...")

    try:
        filing = sec_edgar.get_10k_filing(normalized_ticker)
    except Exception as exc:
        print(
            f"Could not download the filing for {normalized_ticker}: {exc}",
            file=sys.stderr,
        )
        return 1

    metadata = filing.get("meta") or {}
    raw_html = filing.get("html")
    filing_text = filing.get("text") or ""

    print("\nFILING METADATA")
    print("================")
    print(f"Ticker: {metadata.get('ticker', normalized_ticker)}")
    print(f"Filing date: {metadata.get('filing_date', 'unknown')}")
    print(f"Accession: {metadata.get('accession', 'unknown')}")
    print(f"Document URL: {metadata.get('doc_url', 'unknown')}")
    print(f"HTML characters: {len(raw_html) if raw_html else 0:,}")
    print(f"Plain-text characters: {len(filing_text):,}")

    if not raw_html:
        print(
            "\nThe downloaded filing did not include preserved HTML. "
            "Confirm that sec_edgar.py returns an 'html' field.",
            file=sys.stderr,
        )
        return 1

    print("\nExtracting and ranking candidate filing material...")

    try:
        parser_result = filing_parser.build_candidate_context(
            raw_html=raw_html,
            filing_text=filing_text,
            top_tables=top_tables,
            top_sections=top_sections,
        )
    except Exception as exc:
        print(
            f"Filing parser failed: {exc}",
            file=sys.stderr,
        )
        return 1

    diagnostics = parser_result.get("diagnostics") or {}
    tables = parser_result.get("tables") or []
    sections = parser_result.get("sections") or []
    context = parser_result.get("context") or ""

    print("\nPARSER DIAGNOSTICS")
    print("==================")
    print(f"Used HTML: {diagnostics.get('used_html')}")
    print(
        "Candidate tables included:",
        diagnostics.get("table_count", len(tables)),
    )
    print(
        "Candidate sections included:",
        diagnostics.get("section_count", len(sections)),
    )
    print(
        "Structured context characters:",
        f"{diagnostics.get('context_characters', len(context)):,}",
    )

    included_table_ids = diagnostics.get("included_table_ids") or []
    included_section_ids = diagnostics.get("included_section_ids") or []

    if included_table_ids:
        print(
            "Included table IDs:",
            ", ".join(included_table_ids),
        )

    if included_section_ids:
        print(
            "Included section IDs:",
            ", ".join(included_section_ids),
        )

    if tables:
        print("\n\nTOP CANDIDATE TABLES")
        print("====================")

        for table in tables:
            _print_table_candidate(table)
    else:
        print("\nNo candidate tables passed the ranking threshold.")

    if sections:
        print("\n\nTOP CANDIDATE SECTIONS")
        print("======================")

        for section in sections:
            _print_section_candidate(section)
    else:
        print("\nNo candidate narrative sections were found.")

    if save_context_path:
        try:
            _save_parser_context(
                path=save_context_path,
                context=context,
            )
        except OSError as exc:
            print(
                f"Could not save parser context: {exc}",
                file=sys.stderr,
            )
            return 1

    print(
        "\nInspection complete. Gemini and the remaining database tools "
        "were not called."
    )

    return 0


def run_normal_pipeline(args: argparse.Namespace) -> int:
    """
    Run the normal OpenLedger comparison pipeline.
    """
    try:
        result = pipeline.build_comparison(
            args.tickers,
            use_sample=args.sample,
        )
    except Exception as exc:
        print(
            f"OpenLedger pipeline failed: {exc}",
            file=sys.stderr,
        )
        return 1

    brief_markdown = result["brief_markdown"]

    try:
        with open(args.out, "w", encoding="utf-8") as file:
            file.write(brief_markdown)
    except OSError as exc:
        print(
            f"Could not write output file {args.out!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Wrote {args.out}\n")
    print(brief_markdown)

    if args.json:
        print("\n--- RAW CARDS ---")
        print(
            json.dumps(
                result["cards"],
                indent=2,
                ensure_ascii=False,
            )
        )

    return 0


def main() -> int:
    """
    Parse command-line arguments and run the selected operation.
    """
    parser = _build_argument_parser()
    args = parser.parse_args()

    _validate_arguments(
        parser=parser,
        args=args,
    )

    if args.inspect_filing:
        return inspect_filing(
            ticker=args.tickers[0],
            top_tables=args.top_tables,
            top_sections=args.top_sections,
            save_context_path=args.save_parser_context,
        )

    return run_normal_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())