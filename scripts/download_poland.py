#!/usr/bin/env python3
"""Download monthly new passenger-car registrations for Poland.

Source: CEPIK (Centralna Ewidencja Pojazdów i Kierowców) — the central vehicle
register — via its public open REST API (``api.cepik.gov.pl``), no key required.
The ``/pojazdy`` endpoint returns individual vehicle records; we request each
voivodeship for a month, keep passenger cars (``rodzaj-pojazdu`` =
``SAMOCHÓD OSOBOWY``) whose *first registration* falls in that month (used
imports keep an earlier first-registration date and so are excluded), and
aggregate by make (and make/model).

The API is record-level with no server-side grouping, so this is heavier than
the other national sources; it downloads incrementally and merges into the
existing CSVs, re-fetching only the trailing window each run.

Writes:
- ``data/Poland/cepik_monthly_brands.csv`` (year,month,brand,count)
- ``data/Poland/cepik_models.csv``         (brand,model,total  — recent window)

Usage:
    python scripts/download_poland.py                 # incremental default
    python scripts/download_poland.py --from 2024-01 --to 2026-06
    python scripts/download_poland.py --last 3        # trailing 3 months
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Poland"
OUT_CSV = OUT_DIR / "cepik_monthly_brands.csv"
MODELS_CSV = OUT_DIR / "cepik_models.csv"

API = "https://api.cepik.gov.pl/pojazdy"
# 16 voivodeships — TERYT 2-digit codes (required parameter, one call each).
WOJEWODZTWA = ["02", "04", "06", "08", "10", "12", "14", "16",
               "18", "20", "22", "24", "26", "28", "30", "32"]
PASSENGER = "SAMOCHÓD OSOBOWY"
DEFAULT_FROM = (2024, 1)          # modest backfill; heavy record-level source
MODELS_SINCE = (2024, 1)          # brand/model detail window
PAGE_SIZE = 500                    # CEPIK max


def last_complete_month() -> tuple[int, int]:
    t = date.today()
    return (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)


def month_range(a: tuple[int, int], b: tuple[int, int]):
    y, m = a
    while (y, m) <= b:
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def _last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def fetch_page(url: str, retries: int = 4) -> dict:
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VRS/1.0",
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except Exception as exc:  # noqa: BLE001 - network resilience
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return {}


def fetch_month(year: int, month: int):
    """Return (brand_counts, brandmodel_counts) for one month, all voivodeships."""
    lo = f"{year:04d}{month:02d}01"
    hi = f"{year:04d}{month:02d}{_last_day(year, month):02d}"
    brands: dict[str, int] = defaultdict(int)
    models: dict[tuple[str, str], int] = defaultdict(int)
    for woj in WOJEWODZTWA:
        params = {
            "wojewodztwo": woj,
            "data-od": lo,
            "data-do": hi,
            "typ-daty": "1",                       # first-registration date
            "pola": "marka,model,rodzaj-pojazdu",  # trim payload
            "limit": str(PAGE_SIZE),
        }
        url = API + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        pages = 0
        while url:
            payload = fetch_page(url)
            for rec in payload.get("data", []):
                a = rec.get("attributes", {})
                if (a.get("rodzaj-pojazdu") or "").strip().upper() != PASSENGER:
                    continue
                brand = (a.get("marka") or "").strip().upper()
                if not brand:
                    continue
                brands[brand] += 1
                model = (a.get("model") or "").strip().upper()
                if model:
                    models[(brand, model)] += 1
            nxt = (payload.get("links") or {}).get("next")
            url = urllib.parse.urljoin(API, nxt) if nxt else None
            pages += 1
            time.sleep(0.2)
        print(f"    woj {woj}: {pages} page(s)")
    return brands, models


def load_existing() -> dict[tuple[int, int, str], int]:
    data: dict[tuple[int, int, str], int] = {}
    if OUT_CSV.exists():
        with OUT_CSV.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                data[(int(r["year"]), int(r["month"]), r["brand"])] = int(r["count"])
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", help="start month YYYY-MM")
    ap.add_argument("--to", dest="to", help="end month YYYY-MM")
    ap.add_argument("--last", type=int, help="fetch only the trailing N complete months")
    args = ap.parse_args()

    end = last_complete_month()
    if args.to:
        end = tuple(map(int, args.to.split("-")))
    if args.last:
        y, m = end
        for _ in range(args.last - 1):
            m -= 1
            if m < 1:
                y, m = y - 1, 12
        start = (y, m)
    elif args.frm:
        start = tuple(map(int, args.frm.split("-")))
    else:
        start = DEFAULT_FROM

    data = load_existing()
    months = list(month_range(start, end))
    print(f"[pl] CEPIK: {len(months)} month(s) {start[0]}-{start[1]:02d} .. {end[0]}-{end[1]:02d}")
    model_acc: dict[tuple[str, str], int] = defaultdict(int)
    for y, m in months:
        print(f"  {y}-{m:02d} …")
        brands, models = fetch_month(y, m)
        for key in [k for k in data if k[0] == y and k[1] == m]:
            del data[key]
        for b, c in brands.items():
            data[(y, m, b)] = c
        if (y, m) >= MODELS_SINCE:
            for k, c in models.items():
                model_acc[k] += c
        print(f"    → {len(brands)} brands, {sum(brands.values()):,} cars")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(data.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1], kv[0][2]))
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "brand", "count"])
        for (y, m, b), c in rows:
            w.writerow([y, m, b, c])
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(rows)} rows)")

    # Models: merge freshly-fetched window with any existing rows outside it.
    existing_models: dict[tuple[str, str], int] = {}
    if MODELS_CSV.exists():
        with MODELS_CSV.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                existing_models[(r["brand"], r["model"])] = int(r["total"])
    existing_models.update(model_acc)
    if existing_models:
        with MODELS_CSV.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["brand", "model", "total"])
            for (b, mo), c in sorted(existing_models.items(), key=lambda kv: -kv[1]):
                w.writerow([b, mo, c])
        print(f"[write] {MODELS_CSV.relative_to(REPO_ROOT)} ({len(existing_models)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
