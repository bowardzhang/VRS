#!/usr/bin/env python3
"""Download monthly new passenger-car registrations for Finland.

Source: Traficom (Finnish Transport and Communications Agency) "First
registrations of passenger cars", published as open data in the Traficom PxWeb
database and queried via its API (no key required). The table is broken down by
Region / Make / Driving power / Year / Month; we take mainland-Finland totals,
all driving powers, by make.

Writes ``data/Finland/traficom_monthly_brands.csv`` (year,month,brand,count).

Usage:
    python scripts/download_finland.py                 # backfill default range
    python scripts/download_finland.py --from 2025-01 --to 2026-06
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Finland"
OUT_CSV = OUT_DIR / "traficom_monthly_brands.csv"

API = ("https://trafi2.stat.fi/PXWeb/api/v1/en/TraFi/"
       "TraFi__Ensirekisteroinnit/")
DEFAULT_FROM = (2023, 9)

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}
# Aggregate rows that are not individual makes.
SKIP_MAKES = {"Passenger cars total", "Campervans total"}


def last_complete_month() -> tuple[int, int]:
    t = date.today()
    return (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)


def fetch(years: list[int], retries: int = 4) -> str:
    query = {
        "query": [
            {"code": "Maakunta", "selection": {"filter": "item", "values": ["MA1"]}},
            {"code": "Merkki", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Käyttövoima", "selection": {"filter": "item", "values": ["YH"]}},
            {"code": "Vuosi", "selection": {"filter": "item", "values": [str(y) for y in years]}},
            {"code": "Kuukausi", "selection": {"filter": "item",
             "values": [f"{m:02d}" for m in range(1, 13)]}},
        ],
        "response": {"format": "csv"},
    }
    body = json.dumps(query).encode("utf-8")
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8-sig")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return ""


def parse_wide(text: str, lo: tuple[int, int], hi: tuple[int, int]) -> dict:
    """Parse the wide CSV (one value column per 'YYYY MonthName') to long form."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    # First three columns are Region, Make, Driving power; rest are periods.
    periods: list[tuple[int, tuple[int, int]]] = []
    for i, h in enumerate(header[3:], start=3):
        parts = h.strip().strip('"').split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1] in MONTHS:
            periods.append((i, (int(parts[0]), MONTHS[parts[1]])))
    data: dict[tuple[int, int, str], int] = {}
    for row in reader:
        if len(row) < 4:
            continue
        make = row[1].strip()
        if make in SKIP_MAKES:
            continue
        for i, (y, m) in periods:
            if (y, m) < lo or (y, m) > hi:
                continue
            raw = row[i].strip()
            if raw in ("", "-", ".", ".."):
                continue
            try:
                cnt = int(raw.replace(" ", ""))
            except ValueError:
                continue
            if cnt:
                data[(y, m, make.upper())] = cnt
    return data


def write_csv(data: dict[tuple[int, int, str], int]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(data.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1], kv[0][2]))
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "brand", "count"])
        for (y, m, b), c in rows:
            w.writerow([y, m, b, c])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", help="start month YYYY-MM")
    ap.add_argument("--to", dest="to", help="end month YYYY-MM")
    args = ap.parse_args()
    start = tuple(map(int, args.frm.split("-"))) if args.frm else DEFAULT_FROM
    end = tuple(map(int, args.to.split("-"))) if args.to else last_complete_month()

    years = list(range(start[0], end[0] + 1))
    print(f"[fi] querying Traficom PxWeb for {years[0]}-{years[-1]} …")
    text = fetch(years)
    data = parse_wide(text, start, end)
    by_month: dict[tuple[int, int], int] = {}
    for (y, m, _), c in data.items():
        by_month[(y, m)] = by_month.get((y, m), 0) + c
    for ym in sorted(by_month):
        print(f"  {ym[0]}-{ym[1]:02d}: {by_month[ym]:,} cars")
    write_csv(data)
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(data)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
