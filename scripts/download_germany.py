#!/usr/bin/env python3
"""Download German monthly new-vehicle registration data (KBA table FZ 10.1).

Source: Kraftfahrt-Bundesamt (KBA)
  https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html

Table FZ 10.1 ("Neuzulassungen von Personenkraftwagen nach Marken und
Modellreihen") lists new passenger-car registrations by brand and model series,
broken down by fuel/drive type, for the reference month and the year to date.

The monthly workbooks are published as .xlsx files. This script downloads the
files for the requested reference months into ``data/Germany`` using the naming
convention ``fz10_<YYYY>_<MM>.xlsx``.

Usage examples
--------------
    # Download a single month
    python scripts/download_germany.py --month 2026-06

    # Download every month in a range (inclusive)
    python scripts/download_germany.py --from 2025-01 --to 2026-06

    # Download the most recent N months up to a given month
    python scripts/download_germany.py --to 2026-06 --last 12

Notes
-----
* KBA serves the files from ``www.kba.de``. If your environment enforces an
  egress network policy, that host must be on the allow-list or the download
  will fail with an HTTP 403 at the proxy.
* Existing files are skipped unless ``--force`` is given.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("This script requires the 'requests' package: pip install requests")

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Germany"

# KBA download location for the FZ 10 monthly workbooks. The ``v`` (version)
# query parameter changes per publication; we probe a small range of values.
BASE_URL = (
    "https://www.kba.de/SharedDocs/Downloads/DE/Statistik/Fahrzeuge/FZ10/"
    "fz10_{year}_{month:02d}.xlsx"
)
VERSION_CANDIDATES = ["", "?__blob=publicationFile"] + [
    f"?__blob=publicationFile&v={v}" for v in range(1, 8)
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/octet-stream,*/*"
    ),
}

# XLSX files are ZIP archives; every valid one starts with the "PK" signature.
XLSX_MAGIC = b"PK\x03\x04"


def month_iter(start: date, end: date):
    """Yield (year, month) tuples from start to end inclusive (day ignored)."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def parse_month(value: str) -> date:
    """Parse a ``YYYY-MM`` string into a date on the first of that month."""
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except Exception as exc:  # noqa: BLE001
        raise argparse.ArgumentTypeError(
            f"Invalid month '{value}', expected format YYYY-MM"
        ) from exc


def download_month(year: int, month: int, *, force: bool = False) -> bool:
    """Download one month's FZ 10.1 workbook. Return True on success/skip."""
    out_path = OUT_DIR / f"fz10_{year}_{month:02d}.xlsx"
    if out_path.exists() and not force:
        print(f"[skip] {out_path.name} already exists")
        return True

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = BASE_URL.format(year=year, month=month)

    for suffix in VERSION_CANDIDATES:
        url = base + suffix
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
        except requests.RequestException as exc:
            print(f"[warn] {url} -> {exc}")
            continue
        if resp.status_code == 200 and resp.content.startswith(XLSX_MAGIC):
            out_path.write_bytes(resp.content)
            print(f"[ok]   {out_path.name} ({len(resp.content):,} bytes) <- {url}")
            return True
        if resp.status_code == 403:
            print(
                f"[deny] {url} -> HTTP 403 (egress policy blocks www.kba.de). "
                "Add the host to your network allow-list and retry."
            )
            return False
    print(f"[miss] No downloadable workbook found for {year}-{month:02d}")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", type=parse_month, help="Single month YYYY-MM")
    parser.add_argument("--from", dest="from_", type=parse_month, help="Range start YYYY-MM")
    parser.add_argument("--to", type=parse_month, help="Range end YYYY-MM")
    parser.add_argument("--last", type=int, help="Download the last N months up to --to")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args(argv)

    if args.month:
        months = [(args.month.year, args.month.month)]
    elif args.to and args.last:
        end = args.to
        start_index = end.year * 12 + (end.month - 1) - (args.last - 1)
        start = date(start_index // 12, start_index % 12 + 1, 1)
        months = list(month_iter(start, end))
    elif args.from_ and args.to:
        months = list(month_iter(args.from_, args.to))
    else:
        parser.error("Specify --month, or --from/--to, or --to/--last")
        return 2

    ok = 0
    for year, month in months:
        if download_month(year, month, force=args.force):
            ok += 1
    print(f"\nDone: {ok}/{len(months)} month(s) available in {OUT_DIR}")
    return 0 if ok == len(months) else 1


if __name__ == "__main__":
    raise SystemExit(main())
