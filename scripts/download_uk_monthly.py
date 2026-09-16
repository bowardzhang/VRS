#!/usr/bin/env python3
"""Download DfT VEH9902 monthly provisional UK passenger-car registrations.

The monthly feed is kept separate from VEH0160 quarterly official detail.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import requests
from odf.opendocument import load
from odf.table import Table, TableCell, TableRow
from odf.text import P
from odf import teletype

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "UnitedKingdom"
OUT_TOTAL = OUT_DIR / "uk_monthly_total.csv"
OUT_PT = OUT_DIR / "uk_monthly_powertrain.csv"
PAGE = "https://www.gov.uk/government/statistics/developing-faster-indicators-of-transport-activity"
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTHS = {m.lower(): i for i, m in enumerate(MONTH_NAMES, 1)}
# VEH9902 is principally a ZEV/non-ZEV faster indicator.  Keep labels specific:
# never match the bare word "other", which also occurs in notes/headings.
FUEL = {
    "battery electric": "BEV", "zero emission": "BEV",
    "plug-in hybrid electric (petrol)": "PHEV", "plug-in hybrid electric (diesel)": "PHEV",
    "plug-in hybrid": "PHEV", "hybrid electric (petrol)": "Hybrid",
    "hybrid electric (diesel)": "Hybrid", "hybrid electric": "Hybrid",
    "petrol": "Petrol", "diesel": "Diesel", "fuel cell electric": "Other",
    "range extended electric": "Other", "other fuel types": "Other",
    "non-zero emission": "Other",
}
MIN_PLAUSIBLE = 20_000
MAX_PLAUSIBLE = 600_000


def _text(cell) -> str:
    # odf.teletype extracts actual text nodes; str(node) can serialize XML and
    # was the source of false matches in the first parser.
    return " ".join(teletype.extractText(p) for p in cell.getElementsByType(P)).strip()


def _cells(row) -> list[str]:
    out = []
    for c in row.getElementsByType(TableCell):
        repeat = int(c.getAttribute("numbercolumnsrepeated") or 1)
        out.extend([_text(c)] * min(repeat, 50))
    return out


def discover() -> tuple[str, int, int]:
    r = requests.get(PAGE, timeout=60, headers={"User-Agent": "VRS/1.0"})
    r.raise_for_status()
    pat = re.compile(r'href="([^"]+\.ods[^"]*)"[^>]*>(.*?)</a>', re.I | re.S)
    candidates = []
    for href, html in pat.findall(r.text):
        label = re.sub(r"<[^>]+>", " ", html)
        label = re.sub(r"\s+", " ", label).strip()
        if "cars and light goods vehicles registered for the first time" not in label.lower():
            continue
        m = re.search(r"(" + "|".join(MONTH_NAMES) + r")\s+(20\d{2})", label, re.I)
        if m:
            candidates.append((int(m.group(2)), MONTHS[m.group(1).lower()], urljoin(PAGE, href)))
    if not candidates:
        raise RuntimeError("Could not discover a dated DfT VEH9902 ODS link")
    y, m, url = max(candidates)
    return url, y, m


def _period_matches(text: str, year: int, month: int) -> bool:
    name = MONTH_NAMES[month - 1]
    patterns = [
        rf"\b{name}\s+{year}\b", rf"\b{name[:3]}\s+{year}\b",
        rf"\b{year}[-/ ]0?{month}\b", rf"\b0?{month}[-/ ]{year}\b",
        rf"\b{year}\s+{name}\b", rf"\b{year}\s+{name[:3]}\b",
    ]
    return any(re.search(p, text, re.I) for p in patterns)


def _numeric_cells(vals: list[str]) -> list[int]:
    nums = []
    for v in vals:
        s = v.strip().replace(",", "").replace(" ", "")
        if re.fullmatch(r"\d+(?:\.0+)?", s):
            n = int(float(s))
            if not (2000 <= n <= 2100):
                nums.append(n)
    return nums


def parse_ods(blob: bytes, year: int, month: int):
    doc = load(BytesIO(blob))
    rows: list[list[str]] = []
    for table in doc.spreadsheet.getElementsByType(Table):
        for row in table.getElementsByType(TableRow):
            vals = _cells(row)
            if any(v.strip() for v in vals):
                rows.append(vals)

    # VEH9902 files contain historical months.  The previous implementation
    # summed every Cars row in the workbook, producing a bogus 10.3m headline.
    # Restrict extraction to rows/cells belonging to the release month.
    month_rows = [r for r in rows if _period_matches(" | ".join(r), year, month)]
    if not month_rows:
        raise RuntimeError(f"VEH9902 contains no rows identifiable as {year}-{month:02d}")

    agg: dict[str, int] = defaultdict(int)
    for vals in month_rows:
        joined = " | ".join(v.strip().lower() for v in vals)
        if not re.search(r"\bcars?\b", joined) or "light goods" in joined or "lgv" in joined:
            continue
        fuel = None
        for raw in sorted(FUEL, key=len, reverse=True):
            if raw in joined:
                fuel = FUEL[raw]
                break
        if not fuel:
            continue
        nums = _numeric_cells(vals)
        # A monthly passenger-car count is the plausible count, not percentages,
        # years, YTD totals or notes.  If ambiguous, fail rather than publish junk.
        plausible = [n for n in nums if 100 <= n <= MAX_PLAUSIBLE]
        if len(plausible) == 1:
            agg[fuel] += plausible[0]

    total = sum(agg.values())
    if not agg or not MIN_PLAUSIBLE <= total <= MAX_PLAUSIBLE:
        raise RuntimeError(f"VEH9902 parse failed plausibility check: fuels={dict(agg)}, total={total:,}")
    return year, month, dict(agg)


def _read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    url, year, month = discover()
    print(f"[uk-monthly] {year}-{month:02d}: {url}")
    r = requests.get(url, timeout=90, headers={"User-Agent": "VRS/1.0"})
    r.raise_for_status()
    year, month, fuel = parse_ods(r.content, year, month)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Remove any stale rows for this month before writing the newly validated set.
    pt = {(int(r["year"]), int(r["month"]), r["fuel"]): int(r["count"])
          for r in _read_existing(OUT_PT)
          if (int(r["year"]), int(r["month"])) != (year, month)}
    for f, c in fuel.items():
        pt[(year, month, f)] = c
    with OUT_PT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "month", "fuel", "count"])
        for (y, m, f), c in sorted(pt.items()): w.writerow([y, m, f, c])

    total = sum(fuel.values())
    totals = {(int(r["year"]), int(r["month"])): int(r["total"])
              for r in _read_existing(OUT_TOTAL)
              if (int(r["year"]), int(r["month"])) != (year, month)}
    totals[(year, month)] = total
    with OUT_TOTAL.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "month", "total"])
        for (y, m), c in sorted(totals.items()): w.writerow([y, m, c])
    print(f"[write] {OUT_TOTAL.relative_to(REPO_ROOT)}: {year}-{month:02d} = {total:,} cars")
    print(f"[write] {OUT_PT.relative_to(REPO_ROOT)}: {fuel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
