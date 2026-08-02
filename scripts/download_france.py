#!/usr/bin/env python3
"""Download monthly new passenger-car registrations for France (national totals).

Source: INSEE Banque de données macroéconomiques (BDM), series ``010756763``
"Immatriculations de voitures particulières neuves – données brutes" (new
passenger-car registrations, raw monthly), fetched as SDMX-ML from the public
BDM endpoint (no key required). France's open data gives reliable national
*totals* with long history; brand-level detail is not openly published, so this
country is total-only.

Writes ``data/France/insee_monthly_total.csv`` (year,month,total).
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "France"
OUT_CSV = OUT_DIR / "insee_monthly_total.csv"

SERIES = "010756763"
URL = f"https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{SERIES}"

_OBS_A = re.compile(r'TIME_PERIOD="(\d{4})-(\d{2})"[^>]*?OBS_VALUE="([0-9.]+)"')
_OBS_B = re.compile(r'OBS_VALUE="([0-9.]+)"[^>]*?TIME_PERIOD="(\d{4})-(\d{2})"')


def fetch(retries: int = 4) -> str:
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return ""


def parse(xml: str) -> dict[tuple[int, int], int]:
    out: dict[tuple[int, int], int] = {}
    for y, m, v in _OBS_A.findall(xml):
        out[(int(y), int(m))] = int(round(float(v)))
    for v, y, m in _OBS_B.findall(xml):
        out.setdefault((int(y), int(m)), int(round(float(v))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", default="2019-01", help="start month YYYY-MM")
    ap.add_argument("--to", dest="to", help="end month YYYY-MM (default: all available)")
    args = ap.parse_args()
    lo = tuple(map(int, args.frm.split("-")))
    hi = tuple(map(int, args.to.split("-"))) if args.to else (9999, 12)

    data = parse(fetch())
    rows = sorted((ym, v) for ym, v in data.items() if lo <= ym <= hi)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "total"])
        for (y, m), v in rows:
            w.writerow([y, m, v])
    if rows:
        print(f"[fr] {rows[0][0][0]}-{rows[0][0][1]:02d} .. {rows[-1][0][0]}-{rows[-1][0][1]:02d}, "
              f"{len(rows)} months")
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
