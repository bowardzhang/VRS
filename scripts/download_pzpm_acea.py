#!/usr/bin/env python3
"""Download ACEA monthly new-car registrations (all European markets) via PZPM.

ACEA's monthly press release is published as an .xlsx by PZPM (the Polish
automotive industry association), which — unlike ACEA's own PDF — is a clean,
structured workbook. The ``Market (monthly)`` sheet lists every European market
(EU27 + EFTA + UK) with the month's registrations split by power source
(BEV / PHEV / HEV / other / petrol / diesel) and a total.

VRS uses this as a *second tier*: the eight countries with their own open
national feeds keep those (with brand/model detail); every other European market
is filled from ACEA at country-total + powertrain level. ACEA data is © ACEA and
must be credited as the source wherever shown.

Scrapes the PZPM per-year listing pages for the monthly .xlsx links, downloads
new months incrementally, and writes
``data/Europe/acea_market.csv`` (year, month, country, total, bev, phev, hev,
other, petrol, diesel).
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Europe"
OUT_CSV = OUT_DIR / "acea_market.csv"

LISTING = ("https://www.pzpm.org.pl/en/Europe/EUROPE-Registrations-of-vehicles/"
           "PASSENGER-CARS/Year-{year}")
BASE = "https://www.pzpm.org.pl"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VRS/1.0"

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

# Aggregate rows in the sheet that are not individual countries.
AGGREGATES = {"EUROPEAN UNION", "EFTA", "EU + EFTA + UK", "EU15", "EU12",
              "EU27", "EU + EFTA", "EU14 + EFTA"}

# Value columns (0-indexed) per power source. Each source spans 3 cols: this
# year / last year / % change. We read BOTH years, so each monthly file yields
# the current month AND the year-earlier month (doubling the history for free).
CUR_COLS = {"bev": 1, "phev": 4, "hev": 7, "other": 10, "petrol": 13, "diesel": 16, "total": 19}
PRIOR_COLS = {k: v + 1 for k, v in CUR_COLS.items()}


def _get(url: str, retries: int = 4) -> bytes:
    delay = 3.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return b""


def list_month_files(year: int) -> dict[tuple[int, int], str]:
    """{(year, month): absolute xlsx url} for a PZPM year listing page."""
    try:
        html = _get(LISTING.format(year=year)).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] year {year} listing failed: {exc}", file=sys.stderr)
        return {}
    out: dict[tuple[int, int], str] = {}
    for href in re.findall(r'href="([^"]*Press_release_car_registrations[^"]*\.xlsx)"', html):
        m = re.search(r"registrations_([A-Za-z]+)_(\d{4})\.xlsx", href)
        if not m:
            continue
        mon = MONTHS.get(m.group(1))
        yr = int(m.group(2))
        if not mon:
            continue
        url = href if href.startswith("http") else BASE + href
        out[(yr, mon)] = url
    return out


def parse_workbook(blob: bytes, file_year: int, month: int) -> list[tuple]:
    """Parse the Market (monthly) sheet, returning both the current month and the
    year-earlier month: [(year, month, country, rec, is_current)]."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    ws = wb["Market (monthly)"] if "Market (monthly)" in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    out = []
    for r in rows[5:]:
        name = r[0]
        if not name or not str(name).strip():
            continue
        name = str(name).strip()
        if name.upper() in AGGREGATES or name[0].isdigit() or name.startswith("*"):
            continue

        def rec_for(colmap):
            def val(col):
                v = r[col] if col < len(r) else None
                try:
                    return int(round(float(v)))
                except (TypeError, ValueError):
                    return 0
            return {k: val(c) for k, c in colmap.items()}

        cur = rec_for(CUR_COLS)
        if cur["total"] > 0:
            out.append((file_year, month, name, cur, True))
        prior = rec_for(PRIOR_COLS)
        if prior["total"] > 0:
            out.append((file_year - 1, month, name, prior, False))
    return out


def load_existing() -> dict:
    data = {}
    if OUT_CSV.exists():
        with OUT_CSV.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                data[(int(r["year"]), int(r["month"]), r["country"])] = r
    return data


FIELDS = ["year", "month", "country", "total", "bev", "phev", "hev", "other", "petrol", "diesel"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", default="2024,2025,2026",
                    help="comma-separated PZPM listing years to scan")
    args = ap.parse_args()
    years = [int(y) for y in args.years.split(",")]

    # (year, month, country) -> row dict, and whether it came from a current-year
    # reading (which takes precedence over a year-earlier reading of the same key).
    existing = {k: (v, True) for k, v in load_existing().items()}

    available: dict[tuple[int, int], str] = {}
    for y in years:
        available.update(list_month_files(y))
    print(f"[acea] listing found {len(available)} monthly file(s) to fetch")

    for (fy, fm) in sorted(available):
        try:
            recs = parse_workbook(_get(available[(fy, fm)]), fy, fm)
        except Exception as exc:  # noqa: BLE001
            print(f"  {fy}-{fm:02d}: parse failed ({exc}), skipping", file=sys.stderr)
            continue
        n_cur = 0
        for (y, m, name, rec, is_current) in recs:
            key = (y, m, name)
            row = ({"year": y, "month": m, "country": name, **rec}, is_current)
            if is_current:
                existing[key] = row
                n_cur += 1
            elif key not in existing:      # don't overwrite a current reading
                existing[key] = row
        print(f"  file {fy}-{fm:02d}: {n_cur} countries (+ year-ago column)")
        time.sleep(0.3)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for key in sorted(existing, key=lambda k: (k[0], k[1], k[2])):
            row = existing[key][0]
            w.writerow({f: row[f] for f in FIELDS})
    months = sorted({(k[0], k[1]) for k in existing})
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(existing)} rows, "
          f"{len(months)} months {months[0][0]}-{months[0][1]:02d}..{months[-1][0]}-{months[-1][1]:02d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
