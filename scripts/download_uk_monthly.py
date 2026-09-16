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
    text = " ".join(teletype.extractText(p) for p in cell.getElementsByType(P)).strip()
    if text:
        return text
    # LibreOffice often stores dates/numbers as typed ODF attributes even when
    # the display text is absent/minimal.  Keeping these makes the parser
    # independent of the exact VEH9902 formatting.
    for attr in ("datevalue", "value", "stringvalue"):
        try:
            value = cell.getAttribute(attr)
        except Exception:
            value = None
        if value not in (None, ""):
            return str(value)
    return ""


def _cells(row) -> list[str]:
    out = []
    for c in row.getElementsByType(TableCell):
        repeat = int(c.getAttribute("numbercolumnsrepeated") or 1)
        out.extend([_text(c)] * min(repeat, 100))
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
        rf"\b{year}[-/ ]0?{month}(?:\b|[-/]\d{{1,2}})", rf"\b0?{month}[-/ ]{year}\b",
        rf"\b{year}\s+{name}\b", rf"\b{year}\s+{name[:3]}\b",
    ]
    return any(re.search(p, text, re.I) for p in patterns)


def _num(value: str) -> int | None:
    s = value.strip().replace(",", "").replace(" ", "")
    if re.fullmatch(r"\d+(?:\.0+)?", s):
        return int(float(s))
    return None


def _fuel_label(text: str) -> str | None:
    low = text.lower()
    for raw in sorted(FUEL, key=len, reverse=True):
        if raw in low:
            return FUEL[raw]
    return None


def parse_ods(blob: bytes, year: int, month: int):
    doc = load(BytesIO(blob))
    tables: list[list[list[str]]] = []
    for table in doc.spreadsheet.getElementsByType(Table):
        rows = []
        for row in table.getElementsByType(TableRow):
            vals = _cells(row)
            if any(v.strip() for v in vals):
                rows.append(vals)
        if rows:
            tables.append(rows)

    agg: dict[str, int] = defaultdict(int)
    debug = []
    for rows in tables:
        width = max(map(len, rows))
        # VEH9902 is a time-series table: months are columns, not rows.  Find
        # the release-month column by combining the first header rows vertically
        # so split headers such as "2026" / "August" are also recognised.
        target_cols = []
        for col in range(width):
            header = " | ".join(r[col] for r in rows[:20] if col < len(r) and r[col])
            if _period_matches(header, year, month):
                target_cols.append(col)
        if not target_cols:
            continue
        debug.append(target_cols)

        in_cars = False
        for vals in rows:
            label = " | ".join(vals[: min(target_cols)] if min(target_cols) > 0 else vals).strip()
            low = label.lower()
            # Body type is commonly a merged/grouped label followed by fuel rows.
            if re.search(r"\bcars?\b", low) and "light goods" not in low and "lgv" not in low:
                in_cars = True
            if "light goods" in low or re.search(r"\blgv", low):
                in_cars = False
            fuel = _fuel_label(label)
            if not in_cars or not fuel:
                continue
            values = []
            for col in target_cols:
                if col < len(vals):
                    n = _num(vals[col])
                    if n is not None and 0 <= n <= MAX_PLAUSIBLE:
                        values.append(n)
            # There should be one value for the release month. Duplicate header
            # matches are tolerated only when they resolve to the same number.
            values = list(dict.fromkeys(values))
            if len(values) == 1:
                agg[fuel] += values[0]

    total = sum(agg.values())
    if not agg or not MIN_PLAUSIBLE <= total <= MAX_PLAUSIBLE:
        raise RuntimeError(
            f"VEH9902 parse failed plausibility check: fuels={dict(agg)}, "
            f"total={total:,}, target_cols={debug}"
        )
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
