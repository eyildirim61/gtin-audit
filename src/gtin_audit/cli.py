"""Command line entry point: ``gtin-audit products.csv``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .checks import RULES, audit, summarize
from .loader import FIELDS, LoaderError, load_records
from .report import write_csv, write_html


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gtin-audit",
        description="Audit product master data for barcode (GTIN/EAN/UPC) and packaging errors.",
    )
    p.add_argument("input", help="CSV or XLSX export of products")
    p.add_argument("-o", "--out-dir", default="gtin_audit_report", help="where to write the report (default: %(default)s)")
    p.add_argument("--sheet", help="sheet name for XLSX files (default: first sheet)")
    for field in FIELDS:
        flag = field.replace("_", "-")
        p.add_argument(f"--{flag}-col", dest=f"{field}_col", metavar="HEADER", help=f"column header to use as {field}")
    p.add_argument(
        "--no-fill-down",
        action="store_true",
        help="treat rows with only box data as separate products instead of extra packaging lines",
    )
    p.add_argument(
        "--fail-on",
        choices=("error", "warning", "never"),
        default="never",
        help="exit with code 1 if issues of this severity (or worse) exist; useful in CI",
    )
    p.add_argument("-q", "--quiet", action="store_true", help="only print the report paths")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    overrides = {f: getattr(args, f"{f}_col") for f in FIELDS}

    try:
        records, columns = load_records(args.input, args.sheet, overrides, fill_down=not args.no_fill_down)
    except LoaderError as exc:
        print(f"gtin-audit: {exc}", file=sys.stderr)
        return 2

    issues = audit(records, has_box_column="box_barcode" in columns)
    if "box_barcode" not in columns and not args.quiet:
        print("Note: no box barcode column found; box checks are skipped.")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = write_csv(issues, out_dir / "issues.csv")
    html_path = write_html(issues, records, Path(args.input).name, columns, out_dir / "report.html")

    summary = summarize(issues)
    sev = summary["by_severity"]
    if not args.quiet:
        print(f"Columns: " + ", ".join(f"{f} <- '{h}'" for f, h in columns.items()))
        print(f"Checked {len(records)} rows: {sev['error']} errors, {sev['warning']} warnings, {sev['info']} info")
        for code, count in sorted(summary["by_code"].items(), key=lambda kv: -kv[1]):
            print(f"  {count:>5}  {code:<24} {RULES[code][1]}")
    print(f"Report: {html_path}")
    print(f"CSV:    {csv_path}")

    if args.fail_on == "error" and sev["error"]:
        return 1
    if args.fail_on == "warning" and (sev["error"] or sev["warning"]):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
