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
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Finland"
OUT_CSV = OUT_DIR / "traficom_monthly_brands.csv"
MODELS_CSV = OUT_DIR / "traficom_models.csv"
MODELS_LATEST_CSV = OUT_DIR / "traficom_models_latest.csv"
MODELS_MONTHLY_CSV = OUT_DIR / "traficom_models_monthly.csv"
POWERTRAIN_CSV = OUT_DIR / "traficom_powertrain.csv"

API = ("https://trafi2.stat.fi/PXWeb/api/v1/en/TraFi/"
       "TraFi__Ensirekisteroinnit/")

# Traficom driving-power label -> canonical powertrain bucket.
FI_FUEL = {
    "Petrol": "Petrol", "Petrol/Ethanol": "Petrol",
    "Diesel": "Diesel", "Diesel/Biodiesel": "Diesel",
    "Electricity": "BEV",
    "Petrol/Electricity (plug-in hybrid)": "PHEV",
    "Diesel/Electricity (plug-in hybrid)": "PHEV",
    "Hydrogen": "Other", "Natural gas (CNG)": "Other", "Petrol/CNG": "Other",
}
MODELS_API = ("https://trafi2.stat.fi/PXWeb/api/v1/en/TraFi/"
              "Ensirekisteroinnit/050_ensirek_tau_105.px")
MODELS_SINCE = "2023M09"  # brand/model detail window
DEFAULT_FROM = (2019, 1)  # full history (one cheap PxWeb query)

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


def _models_csv_text(retries: int = 4) -> str:
    """Fetch the by-Model table (050) CSV: models × the last 40 months."""
    query = {
        "query": [
            {"code": "Alue", "selection": {"filter": "item", "values": ["MA1"]}},
            {"code": "Mallisarja", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Käyttövoima", "selection": {"filter": "item", "values": ["YH"]}},
            {"code": "Kuukausi", "selection": {"filter": "top", "values": ["40"]}},
        ],
        "response": {"format": "csv"},
    }
    body = json.dumps(query).encode("utf-8")
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                MODELS_API, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8-sig", errors="replace")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [models retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return ""


def _is_model_label(label: str) -> bool:
    return bool(label) and not label.lower().endswith(" total") and label != "Passenger cars total"


def fetch_models(text: str | None = None) -> list[tuple[str, int]]:
    """(model_label, total) since MODELS_SINCE from the by-Model table (050)."""
    text = text if text is not None else _models_csv_text()
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    cols = [i for i, h in enumerate(header[3:], start=3)
            if re.match(r"^\d{4}M\d{2}$", h.strip().strip('"')) and h.strip().strip('"') >= MODELS_SINCE]
    out: list[tuple[str, int]] = []
    for row in reader:
        if len(row) < 4 or not _is_model_label(row[1].strip()):
            continue
        tot = 0
        for i in cols:
            raw = row[i].strip()
            if raw not in ("", "-", ".", ".."):
                try:
                    tot += int(raw.replace(" ", ""))
                except ValueError:
                    pass
        if tot:
            out.append((row[1].strip().upper(), tot))
    return out


def fetch_models_monthly(text: str | None = None) -> list[tuple[int, int, str, int]]:
    """(year, month, model_label, count) per month since MODELS_SINCE — the same
    050 table as fetch_models but keeping the monthly split rather than summing."""
    text = text if text is not None else _models_csv_text()
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    months = []  # (col_index, year, month)
    for i, h in enumerate(header[3:], start=3):
        code = h.strip().strip('"')
        if re.match(r"^\d{4}M\d{2}$", code) and code >= MODELS_SINCE:
            months.append((i, int(code[:4]), int(code[5:])))
    out: list[tuple[int, int, str, int]] = []
    for row in reader:
        if len(row) < 4 or not _is_model_label(row[1].strip()):
            continue
        label = row[1].strip().upper()
        for i, y, m in months:
            raw = row[i].strip()
            if raw not in ("", "-", ".", ".."):
                try:
                    c = int(raw.replace(" ", ""))
                except ValueError:
                    continue
                if c:
                    out.append((y, m, label, c))
    return out


def write_models_monthly(rows: list[tuple[int, int, str, int]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with MODELS_MONTHLY_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "model_label", "count"])
        for y, m, label, c in sorted(rows, key=lambda r: (r[0], r[1], -r[3])):
            w.writerow([y, m, label, c])


def fetch_models_latest(retries: int = 4):
    """(month_code, [(model_label, count)]) for the single most recent month."""
    query = {
        "query": [
            {"code": "Alue", "selection": {"filter": "item", "values": ["MA1"]}},
            {"code": "Mallisarja", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Käyttövoima", "selection": {"filter": "item", "values": ["YH"]}},
            {"code": "Kuukausi", "selection": {"filter": "top", "values": ["1"]}},
        ],
        "response": {"format": "csv"},
    }
    body = json.dumps(query).encode("utf-8")
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                MODELS_API, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                text = resp.read().decode("utf-8-sig", errors="replace")
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [models-latest retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    col = None
    month_code = None
    for i, h in enumerate(header[3:], start=3):
        code = h.strip().strip('"')
        if re.match(r"^\d{4}M\d{2}$", code):
            col, month_code = i, code
            break
    out: list[tuple[str, int]] = []
    if col is None:
        return None, out
    for row in reader:
        if len(row) <= col:
            continue
        label = row[1].strip()
        if not label or label.lower().endswith(" total") or label == "Passenger cars total":
            continue
        raw = row[col].strip()
        if raw in ("", "-", ".", ".."):
            continue
        try:
            c = int(raw.replace(" ", ""))
        except ValueError:
            continue
        if c:
            out.append((label.upper(), c))
    return month_code, out


def write_models_latest(month_code: str | None, rows: list[tuple[str, int]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    year, month = ("", "")
    if month_code:
        year, month = int(month_code[:4]), int(month_code[5:])
    with MODELS_LATEST_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "model_label", "count"])
        for label, c in sorted(rows, key=lambda r: -r[1]):
            w.writerow([year, month, label, c])


def fetch_powertrain(years: list[int], retries: int = 4) -> dict:
    """Passenger-cars total by driving power and month -> canonical fuel buckets."""
    query = {
        "query": [
            {"code": "Maakunta", "selection": {"filter": "item", "values": ["MA1"]}},
            {"code": "Merkki", "selection": {"filter": "item", "values": ["YH"]}},
            {"code": "Käyttövoima", "selection": {"filter": "item",
             "values": ["01", "02", "04", "05", "13", "38", "39", "40", "44", "48"]}},
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
                text = resp.read().decode("utf-8-sig", errors="replace")
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [powertrain retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    periods = []  # (col, year, month)
    for i, h in enumerate(header[3:], start=3):
        parts = h.strip().strip('"').split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1] in MONTHS:
            periods.append((i, int(parts[0]), MONTHS[parts[1]]))
    data: dict[tuple[int, int, str], int] = defaultdict(int)
    for row in reader:
        if len(row) < 4:
            continue
        fuel = FI_FUEL.get(row[2].strip(), "Other")
        for i, y, m in periods:
            raw = row[i].strip()
            if raw not in ("", "-", ".", ".."):
                try:
                    data[(y, m, fuel)] += int(raw.replace(" ", ""))
                except ValueError:
                    pass
    return data


def write_powertrain(data: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with POWERTRAIN_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "fuel", "count"])
        for (y, m, f), c in sorted(data.items()):
            w.writerow([y, m, f, c])


def write_models(rows: list[tuple[str, int]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with MODELS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model_label", "total"])
        for label, c in sorted(rows, key=lambda r: -r[1]):
            w.writerow([label, c])


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

    models_text = _models_csv_text()
    models = fetch_models(models_text)
    write_models(models)
    print(f"[write] {MODELS_CSV.relative_to(REPO_ROOT)} ({len(models)} model rows)")

    models_monthly = fetch_models_monthly(models_text)
    write_models_monthly(models_monthly)
    print(f"[write] {MODELS_MONTHLY_CSV.relative_to(REPO_ROOT)} ({len(models_monthly)} rows)")

    mc, latest = fetch_models_latest()
    write_models_latest(mc, latest)
    print(f"[write] {MODELS_LATEST_CSV.relative_to(REPO_ROOT)} (latest {mc}, {len(latest)} rows)")

    pt = fetch_powertrain(years)
    write_powertrain(pt)
    print(f"[write] {POWERTRAIN_CSV.relative_to(REPO_ROOT)} ({len(pt)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
