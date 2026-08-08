#!/usr/bin/env python3
"""Download the euro-area total of new passenger-car registrations.

Source: ECB Data Portal dataset ``CAR`` (series
``M.I10.N.CREG.PC0000.4Z1.N.PN``) — monthly new passenger-car registrations for
the euro area (21 countries, current fixed composition), unadjusted. The
underlying figures are ACEA's, redistributed by the ECB under its open reuse
terms, so — unlike ACEA's own copyright-restricted press releases — this
aggregate can be reused with attribution.

This is a euro-area *aggregate only*: no per-country, powertrain or manufacturer
detail (those live only in ACEA's restricted PDFs). It gives VRS an official
Europe-wide headline total to sit alongside the national feeds.

Writes ``data/Europe/ecb_ea_total.csv`` (year, month, total).
"""
from __future__ import annotations

import csv
import io
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Europe"
OUT_CSV = OUT_DIR / "ecb_ea_total.csv"

# CAR / monthly / euro area 21 / unadjusted / car registration / new passenger
# car / provider ACEA-via-ECB / no transformation / persons-number unit.
SERIES = "M.I10.N.CREG.PC0000.4Z1.N.PN"
URL = f"https://data-api.ecb.europa.eu/service/data/CAR/{SERIES}?format=csvdata"
SINCE = (2019, 1)  # keep recent history, aligned with the national feeds


def fetch(retries: int = 4) -> str:
    delay = 3.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                URL, headers={"User-Agent": "VRS/1.0", "Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8-sig", errors="replace")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return ""


def main() -> int:
    print(f"[ea] downloading ECB CAR series {SERIES} …")
    rows_out: dict[tuple[int, int], int] = {}
    for r in csv.DictReader(io.StringIO(fetch())):
        tp = r.get("TIME_PERIOD", "")
        val = r.get("OBS_VALUE", "")
        if "-" not in tp or not val:
            continue
        try:
            y, m = int(tp[:4]), int(tp[5:7])
            v = int(round(float(val)))
        except ValueError:
            continue
        if (y, m) >= SINCE:
            rows_out[(y, m)] = v

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "total"])
        for (y, m) in sorted(rows_out):
            w.writerow([y, m, rows_out[(y, m)]])

    if rows_out:
        last = max(rows_out)
        print(f"  {len(rows_out)} months, latest {last[0]}-{last[1]:02d} = "
              f"{rows_out[last]:,} cars")
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(rows_out)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
