#!/usr/bin/env python3
"""Download monthly new passenger-car registrations for the Netherlands.

Source: RDW (Rijksdienst voor het Wegverkeer) open data — the national vehicle
register — via its Socrata API, dataset ``m9d7-ebf2`` (Gekentekende voertuigen).
No API key required; the host has open internet access from GitHub runners.

"New registration" is proxied by *first admission this month* — a passenger car
(``voertuigsoort = Personenauto``) whose ``datum_eerste_toelating`` falls in the
month. Used imports keep their original (older) first-admission date and so are
naturally excluded. One grouped query per month returns the complete
count-by-brand breakdown, which is merged into
``data/Netherlands/rdw_monthly_brands.csv`` (columns: year,month,brand,count).

Usage:
    python scripts/download_netherlands.py                     # backfill default range
    python scripts/download_netherlands.py --from 2025-01 --to 2026-06
    python scripts/download_netherlands.py --last 3            # trailing 3 months
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Netherlands"
OUT_CSV = OUT_DIR / "rdw_monthly_brands.csv"
MODELS_CSV = OUT_DIR / "rdw_models.csv"
MODELS_LATEST_CSV = OUT_DIR / "rdw_models_latest.csv"

RESOURCE = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
DEFAULT_FROM = (2023, 9)  # align with the German FZ 10.1 window start
MODELS_SINCE = "20230901"  # brand/model detail window (comparable across countries)


def month_range(a: tuple[int, int], b: tuple[int, int]):
    y, m = a
    while (y, m) <= b:
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def last_complete_month() -> tuple[int, int]:
    """The most recent fully-elapsed month (previous calendar month)."""
    t = date.today()
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return y, m


def fetch_month(year: int, month: int, retries: int = 4) -> list[tuple[str, int]]:
    lo = f"{year:04d}{month:02d}01"
    # last day: first day of next month minus a day, but string compare on
    # YYYYMMDD works with an inclusive upper bound of YYYYMM31.
    hi = f"{year:04d}{month:02d}31"
    where = (
        "voertuigsoort='Personenauto' AND "
        f"datum_eerste_toelating >= '{lo}' AND datum_eerste_toelating <= '{hi}'"
    )
    params = {
        "$select": "merk,count(kenteken)",
        "$where": where,
        "$group": "merk",
        "$order": "count_kenteken DESC",
        "$limit": "2000",
    }
    url = RESOURCE + "?" + urllib.parse.urlencode(params, safe="",
                                                  quote_via=urllib.parse.quote)
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                import json
                rows = json.load(resp)
            out = []
            for r in rows:
                brand = (r.get("merk") or "").strip().upper()
                cnt = int(r.get("count_kenteken") or 0)
                if brand and cnt:
                    out.append((brand, cnt))
            return out
        except Exception as exc:  # noqa: BLE001 - network resilience
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {year}-{month:02d}: {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return []


def fetch_models(retries: int = 4) -> list[tuple[str, str, int]]:
    """One grouped query: (brand, model) totals since MODELS_SINCE."""
    params = {
        "$select": "merk,handelsbenaming,count(kenteken)",
        "$where": ("voertuigsoort='Personenauto' AND "
                   f"datum_eerste_toelating >= '{MODELS_SINCE}'"),
        "$group": "merk,handelsbenaming",
        "$order": "count_kenteken DESC",
        "$limit": "6000",
    }
    url = RESOURCE + "?" + urllib.parse.urlencode(params, safe="", quote_via=urllib.parse.quote)
    delay = 2.0
    for attempt in range(retries):
        try:
            import json
            req = urllib.request.Request(url, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                rows = json.load(resp)
            out = []
            for r in rows:
                brand = (r.get("merk") or "").strip().upper()
                model = (r.get("handelsbenaming") or "").strip().upper()
                cnt = int(r.get("count_kenteken") or 0)
                if brand and model and cnt:
                    out.append((brand, model, cnt))
            return out
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [models retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return []


def write_models(rows: list[tuple[str, str, int]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with MODELS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["brand", "model", "total"])
        for b, m, c in sorted(rows, key=lambda r: -r[2]):
            w.writerow([b, m, c])


def fetch_models_month(year: int, month: int, retries: int = 4) -> list[tuple[str, str, int]]:
    """(brand, model) counts for a single month (latest-period snapshot)."""
    lo, hi = f"{year:04d}{month:02d}01", f"{year:04d}{month:02d}31"
    params = {
        "$select": "merk,handelsbenaming,count(kenteken)",
        "$where": ("voertuigsoort='Personenauto' AND "
                   f"datum_eerste_toelating >= '{lo}' AND datum_eerste_toelating <= '{hi}'"),
        "$group": "merk,handelsbenaming",
        "$order": "count_kenteken DESC",
        "$limit": "6000",
    }
    url = RESOURCE + "?" + urllib.parse.urlencode(params, safe="", quote_via=urllib.parse.quote)
    delay = 2.0
    for attempt in range(retries):
        try:
            import json
            req = urllib.request.Request(url, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                rows = json.load(resp)
            out = []
            for r in rows:
                brand = (r.get("merk") or "").strip().upper()
                model = (r.get("handelsbenaming") or "").strip().upper()
                cnt = int(r.get("count_kenteken") or 0)
                if brand and model and cnt:
                    out.append((brand, model, cnt))
            return out
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [models-latest retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return []


def load_existing() -> dict[tuple[int, int, str], int]:
    data: dict[tuple[int, int, str], int] = {}
    if OUT_CSV.exists():
        with OUT_CSV.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                data[(int(row["year"]), int(row["month"]), row["brand"])] = int(row["count"])
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
    ap.add_argument("--last", type=int, help="fetch only the trailing N complete months")
    args = ap.parse_args()

    end = last_complete_month()
    if args.to:
        y, m = map(int, args.to.split("-"))
        end = (y, m)
    if args.last:
        # walk back N-1 months from end
        y, m = end
        for _ in range(args.last - 1):
            m -= 1
            if m < 1:
                y, m = y - 1, 12
        start = (y, m)
    elif args.frm:
        y, m = map(int, args.frm.split("-"))
        start = (y, m)
    else:
        start = DEFAULT_FROM

    data = load_existing()
    months = list(month_range(start, end))
    print(f"[nl] fetching {len(months)} month(s) {start[0]}-{start[1]:02d} .. {end[0]}-{end[1]:02d}")
    for y, m in months:
        rows = fetch_month(y, m)
        # replace this month's rows entirely (handles revisions)
        for key in [k for k in data if k[0] == y and k[1] == m]:
            del data[key]
        for brand, cnt in rows:
            data[(y, m, brand)] = cnt
        print(f"  {y}-{m:02d}: {len(rows)} brands, {sum(c for _, c in rows):,} cars")
        time.sleep(0.3)

    write_csv(data)
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(data)} rows)")

    models = fetch_models()
    write_models(models)
    print(f"[write] {MODELS_CSV.relative_to(REPO_ROOT)} ({len(models)} brand/model rows)")

    ly, lm = max(data)[:2] if data else last_complete_month()
    latest = fetch_models_month(ly, lm)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with MODELS_LATEST_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "brand", "model", "count"])
        for b, mo, c in sorted(latest, key=lambda r: -r[2]):
            w.writerow([ly, lm, b, mo, c])
    print(f"[write] {MODELS_LATEST_CSV.relative_to(REPO_ROOT)} (latest {ly}-{lm:02d}, {len(latest)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
