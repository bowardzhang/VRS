#!/usr/bin/env python3
"""Download the UK DfT monthly *provisional* new-registration indicator.

DfT publishes VEH9902 monthly (cars + light goods vehicles, by body/fuel) as an
ODS file on the "Developing faster indicators of transport activity" page.
This feed is intentionally kept separate from download_uk.py / VEH0160, which
is the lagged quarterly accredited series with make/model detail.

Outputs (cars only):
  data/UnitedKingdom/uk_monthly_total.csv       year,month,total
  data/UnitedKingdom/uk_monthly_powertrain.csv  year,month,fuel,count

The GOV.UK page always links the newest ODS.  We discover that link at runtime,
so the daily workflow needs no URL change when a new month is published.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import requests
from odf.opendocument import load
from odf.table import Table, TableCell, TableRow
from odf.text import P

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "UnitedKingdom"
OUT_TOTAL = OUT_DIR / "uk_monthly_total.csv"
OUT_PT = OUT_DIR / "uk_monthly_powertrain.csv"
PAGE = "https://www.gov.uk/government/statistics/developing-faster-indicators-of-transport-activity"

FUEL = {
    "petrol": "Petrol", "diesel": "Diesel",
    "battery electric": "BEV", "zero emission": "BEV",
    "plug-in hybrid electric (petrol)": "PHEV",
    "plug-in hybrid electric (diesel)": "PHEV",
    "plug-in hybrid": "PHEV",
    "hybrid electric (petrol)": "Hybrid", "hybrid electric (diesel)": "Hybrid",
    "hybrid electric": "Hybrid", "fuel cell electric": "Other",
    "range extended electric": "Other", "other fuel types": "Other", "other": "Other",
}
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def _text(cell) -> str:
    parts = []
    for p in cell.getElementsByType(P):
        parts.append("".join(str(n) for n in p.childNodes))
    return " ".join(parts).strip()


def _cells(row) -> list[str]:
    out = []
    for c in row.getElementsByType(TableCell):
        repeat = int(c.getAttribute("numbercolumnsrepeated") or 1)
        val = _text(c)
        out.extend([val] * min(repeat, 50))
    return out


def discover() -> tuple[str, int, int]:
    r = requests.get(PAGE, timeout=60, headers={"User-Agent": "VRS/1.0"})
    r.raise_for_status()
    # Anchor text contains "Cars and light goods vehicles registered ...: August 2026".
    pat = re.compile(r'href="([^"]+\.ods[^"]*)"[^>]*>(.*?)</a>', re.I | re.S)
    candidates = []
    for href, html in pat.findall(r.text):
        label = re.sub(r"<[^>]+>", " ", html)
        label = re.sub(r"\s+", " ", label).strip()
        if "cars and light goods vehicles registered for the first time" not in label.lower():
            continue
        m = re.search(r"(" + "|".join(MONTHS) + r")\s+(20\d{2})", label, re.I)
        if m:
            candidates.append((int(m.group(2)), MONTHS[m.group(1).lower()], urljoin(PAGE, href)))
    if not candidates:
        # Stable table identifier used by DfT for this faster indicator.
        for href in re.findall(r'href="([^"]*VEH9902[^"]*\.ods[^"]*)"', r.text, re.I):
            candidates.append((0, 0, urljoin(PAGE, href)))
    if not candidates:
        raise RuntimeError("Could not discover the DfT VEH9902 ODS link")
    y, m, url = max(candidates)
    return url, y, m


def parse_ods(blob: bytes, hinted_year: int, hinted_month: int):
    doc = load(BytesIO(blob))
    rows = []
    for table in doc.spreadsheet.getElementsByType(Table):
        for row in table.getElementsByType(TableRow):
            vals = _cells(row)
            if any(v.strip() for v in vals):
                rows.append(vals)

    # VEH9902 layouts have changed slightly.  Parse semantically rather than by
    # fixed row numbers: retain rows mentioning Cars and a recognised fuel, then
    # take the registration count from the row's numeric cells.  Period normally
    # comes from the release title; if the sheet carries a Month/Year, use it.
    agg: dict[str, int] = defaultdict(int)
    for vals in rows:
        low = [v.strip().lower() for v in vals]
        joined = " | ".join(low)
        if not re.search(r"\bcars?\b", joined):
            continue
        fuel = None
        # Longest labels first avoids matching "hybrid electric" inside PHEV text.
        for raw in sorted(FUEL, key=len, reverse=True):
            if raw in joined:
                fuel = FUEL[raw]
                break
        if not fuel:
            continue
        nums = []
        for v in vals:
            s = v.strip().replace(",", "")
            if re.fullmatch(r"-?\d+(?:\.0+)?", s):
                n = int(float(s))
                if n >= 0:
                    nums.append(n)
        if not nums:
            continue
        # Registration count is the largest non-year integer on these compact tables.
        nums = [n for n in nums if not (2000 <= n <= 2100)]
        if nums:
            agg[fuel] += max(nums)

    if not agg:
        raise RuntimeError("VEH9902 downloaded, but no Cars/fuel rows could be parsed")
    if not hinted_year or not hinted_month:
        raise RuntimeError("VEH9902 period could not be determined from GOV.UK release title")
    return hinted_year, hinted_month, dict(agg)


def _read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    try:
        url, year, month = discover()
        print(f"[uk-monthly] {year}-{month:02d}: {url}")
        r = requests.get(url, timeout=90, headers={"User-Agent": "VRS/1.0"})
        r.raise_for_status()
        year, month, fuel = parse_ods(r.content, year, month)
    except Exception as exc:  # keep quarterly refresh alive if GOV.UK changes layout
        print(f"[uk-monthly] WARNING: {exc}", file=sys.stderr)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Upsert the newest provisional month.  Keeping previous releases locally
    # builds a true monthly history even though GOV.UK exposes only the latest file.
    pt = {(int(r["year"]), int(r["month"]), r["fuel"]): int(r["count"])
          for r in _read_existing(OUT_PT)}
    for f, c in fuel.items():
        pt[(year, month, f)] = c
    with OUT_PT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "month", "fuel", "count"])
        for (y, m, f), c in sorted(pt.items()):
            w.writerow([y, m, f, c])

    total = sum(fuel.values())
    totals = {(int(r["year"]), int(r["month"])): int(r["total"])
              for r in _read_existing(OUT_TOTAL)}
    totals[(year, month)] = total
    with OUT_TOTAL.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "month", "total"])
        for (y, m), c in sorted(totals.items()):
            w.writerow([y, m, c])
    print(f"[write] {OUT_TOTAL.relative_to(REPO_ROOT)}: {year}-{month:02d} = {total:,} cars")
    print(f"[write] {OUT_PT.relative_to(REPO_ROOT)}: {fuel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
