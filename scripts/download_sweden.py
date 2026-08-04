#!/usr/bin/env python3
"""Download monthly new passenger-car registrations for Sweden.

Source: Statistics Sweden (SCB) statistical database, table
``TK/TK1001/TK1001A/PersBilarDrivMedel`` — "New registered passenger cars, by
region, fuel and month" (the underlying figures are Trafikanalys'). Queried via
SCB's open PxWeb API (no key required). We take the whole-country region (``00``)
across every fuel, which yields both the monthly total and a powertrain split.

Make/model detail is *not* published in this open table (Trafikanalys releases
brand-level figures only as spreadsheets), so Sweden is represented as monthly
totals + powertrain — richer than an annual mix, but without brands.

Writes:
- ``data/Sweden/scb_monthly_total.csv``  (year,month,total)
- ``data/Sweden/se_powertrain.csv``      (year,month,fuel,count)

Usage:
    python scripts/download_sweden.py                 # backfill default range
    python scripts/download_sweden.py --from 2019-01
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Sweden"
TOTAL_CSV = OUT_DIR / "scb_monthly_total.csv"
POWERTRAIN_CSV = OUT_DIR / "se_powertrain.csv"

API = ("https://api.scb.se/OV0104/v1/doris/en/ssd/"
       "TK/TK1001/TK1001A/PersBilarDrivMedel")

# SCB Drivmedel code -> canonical powertrain bucket.
SE_FUEL = {
    "100": "Petrol",       # petrol
    "110": "Diesel",       # diesel
    "120": "BEV",          # electricity
    "130": "Hybrid",       # electric hybrid (non plug-in)
    "140": "PHEV",         # plug-in hybrid
    "150": "Other",        # ethanol / ethanol flexifuel
    "160": "Other",        # gas / gas flex
    "190": "Other",        # other fuels
}
FUEL_CODES = list(SE_FUEL)
DEFAULT_FROM = (2019, 1)


def last_complete_month() -> tuple[int, int]:
    t = date.today()
    return (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)


def month_codes(start: tuple[int, int], end: tuple[int, int]) -> list[str]:
    out, (y, m) = [], start
    while (y, m) <= end:
        out.append(f"{y}M{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def fetch(periods: list[str], retries: int = 4) -> dict:
    query = {
        "query": [
            {"code": "Region", "selection": {"filter": "item", "values": ["00"]}},
            {"code": "Drivmedel", "selection": {"filter": "item", "values": FUEL_CODES}},
            {"code": "Tid", "selection": {"filter": "item", "values": periods}},
        ],
        "response": {"format": "json"},
    }
    body = json.dumps(query).encode("utf-8")
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", help="start month YYYY-MM")
    ap.add_argument("--to", dest="to", help="end month YYYY-MM")
    args = ap.parse_args()
    start = tuple(map(int, args.frm.split("-"))) if args.frm else DEFAULT_FROM
    end = tuple(map(int, args.to.split("-"))) if args.to else last_complete_month()

    periods = month_codes(start, end)
    # SCB caps cells per call (~ regions*fuels*months); one region * 8 fuels keeps
    # us well within limits even for the full history, so query in one shot.
    print(f"[se] querying SCB PxWeb for {periods[0]}–{periods[-1]} ({len(periods)} months) …")
    payload = fetch(periods)

    pt: dict[tuple[int, int, str], int] = defaultdict(int)
    totals: dict[tuple[int, int], int] = defaultdict(int)
    for row in payload.get("data", []):
        _, fuel_code, tid = row["key"]
        raw = row["values"][0]
        if raw in ("", ".", "..", "-"):
            continue
        try:
            cnt = int(raw)
        except ValueError:
            continue
        y, m = int(tid[:4]), int(tid[5:])
        bucket = SE_FUEL.get(fuel_code, "Other")
        pt[(y, m, bucket)] += cnt
        totals[(y, m)] += cnt

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with TOTAL_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "total"])
        for (y, m) in sorted(totals):
            w.writerow([y, m, totals[(y, m)]])
    with POWERTRAIN_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "fuel", "count"])
        for (y, m, f) in sorted(pt):
            w.writerow([y, m, f, pt[(y, m, f)]])

    for (y, m) in sorted(totals):
        print(f"  {y}-{m:02d}: {totals[(y, m)]:,} cars")
    print(f"[write] {TOTAL_CSV.relative_to(REPO_ROOT)} ({len(totals)} months)")
    print(f"[write] {POWERTRAIN_CSV.relative_to(REPO_ROOT)} ({len(pt)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
