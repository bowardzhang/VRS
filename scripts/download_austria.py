#!/usr/bin/env python3
"""Download monthly new passenger-car registrations for Austria.

Source: Statistics Austria (Statistik Austria) Open Government Data cube
``OGD_fkfzul0759_OD_PkwNZL_1`` — "Pkw-Neuzulassungen" (new passenger-car
registrations) by make and month. Published as plain CSVs (a fact table plus
classification files) with no key required.

The fact table has columns ``C-J59-0`` (make code), ``C-A10-0`` (month code,
e.g. ``A10-202601`` → 2026-01), ``C-EK7-0`` (vehicle type, single value =
passenger cars) and ``F-ISIS-1`` (count). Make codes are resolved via the
``…_C-J59-0.csv`` classification file, whose ``name`` looks like
``ALFA ROMEO (I) <070300>`` — we keep the part before the country parenthesis.

Powertrain and model detail are not in this open cube, so Austria is
represented at brand level.

Writes ``data/Austria/at_monthly_brands.csv`` (year,month,brand,count).

Usage:
    python scripts/download_austria.py                 # backfill default range
    python scripts/download_austria.py --from 2019-01
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Austria"
OUT_CSV = OUT_DIR / "at_monthly_brands.csv"

BASE = "https://data.statistik.gv.at/data/"
DATASET = "OGD_fkfzul0759_OD_PkwNZL_1"
FACT_URL = BASE + DATASET + ".csv"
MAKES_URL = BASE + DATASET + "_C-J59-0.csv"

DEFAULT_FROM = (2019, 1)
# Classification rows that are aggregates / non-makes rather than a real brand.
SKIP_MAKE_TOKENS = ("SONSTIGE", "INSGESAMT", "UNBEKANNT", "ÜBRIGE")


def last_complete_month() -> tuple[int, int]:
    t = date.today()
    return (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)


def fetch(url: str, retries: int = 4) -> str:
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8-sig", errors="replace")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return ""


def parse_makes(text: str) -> dict[str, str]:
    """code -> clean make name (strip the '(CC) <nnnnnn>' suffix)."""
    out: dict[str, str] = {}
    reader = csv.reader(io.StringIO(text), delimiter=";")
    next(reader, None)  # header
    for row in reader:
        if len(row) < 2:
            continue
        code = row[0].strip()
        # name is the German label in col 1; strip a trailing " (CC) <nnnn>".
        name = re.sub(r"\s*\([^)]*\)\s*<[^>]*>\s*$", "", row[1].strip())
        name = re.sub(r"\s*<[^>]*>\s*$", "", name).strip()
        if code and name:
            out[code] = name.upper()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", help="start month YYYY-MM")
    ap.add_argument("--to", dest="to", help="end month YYYY-MM")
    args = ap.parse_args()
    start = tuple(map(int, args.frm.split("-"))) if args.frm else DEFAULT_FROM
    end = tuple(map(int, args.to.split("-"))) if args.to else last_complete_month()

    print("[at] downloading Statistik Austria OGD make classification …")
    makes = parse_makes(fetch(MAKES_URL))
    print(f"  {len(makes)} make codes")
    print("[at] downloading fact table …")
    fact = fetch(FACT_URL)

    reader = csv.reader(io.StringIO(fact), delimiter=";")
    header = next(reader)
    idx = {h.strip(): i for i, h in enumerate(header)}
    mk_i = idx.get("C-J59-0", 0)
    tm_i = idx.get("C-A10-0", 1)
    val_i = idx.get("F-ISIS-1", len(header) - 1)

    data: dict[tuple[int, int, str], int] = defaultdict(int)
    for row in reader:
        if len(row) <= val_i:
            continue
        tm = row[tm_i].strip()          # e.g. A10-202601
        m = re.match(r"A10-(\d{4})(\d{2})$", tm)
        if not m:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        if (y, mo) < start or (y, mo) > end:
            continue
        brand = makes.get(row[mk_i].strip())
        if not brand or any(tok in brand for tok in SKIP_MAKE_TOKENS):
            continue
        raw = row[val_i].strip().replace(",", "")
        if raw in ("", "-", "."):
            continue
        try:
            cnt = int(float(raw))
        except ValueError:
            continue
        if cnt:
            data[(y, mo, brand)] += cnt

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(data.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1], kv[0][2]))
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "brand", "count"])
        for (y, mo, b), c in rows:
            w.writerow([y, mo, b, c])

    by_month: dict[tuple[int, int], int] = defaultdict(int)
    for (y, mo, _), c in data.items():
        by_month[(y, mo)] += c
    for ym in sorted(by_month):
        print(f"  {ym[0]}-{ym[1]:02d}: {by_month[ym]:,} cars")
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
