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
from odf import teletype
from odf.opendocument import load
from odf.table import Table, TableCell, TableRow
from odf.text import P

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "UnitedKingdom"
OUT_TOTAL = OUT_DIR / "uk_monthly_total.csv"
OUT_PT = OUT_DIR / "uk_monthly_powertrain.csv"
PAGE = "https://www.gov.uk/government/statistics/developing-faster-indicators-of-transport-activity"
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTHS = {m.lower(): i for i, m in enumerate(MONTH_NAMES, 1)}
MIN_PLAUSIBLE = 20_000
MAX_PLAUSIBLE = 600_000

# Keep only labels actually present in the monthly table.  In particular,
# don't pretend that DfT's monthly ZEV/non-ZEV split is the same as the much
# richer quarterly fuel/powertrain classification.
FUEL = {
    "zero emission vehicles": "ZEV",
    "zero emission vehicle": "ZEV",
    "non-zero emission vehicles": "Non-ZEV",
    "non-zero emission vehicle": "Non-ZEV",
}


def _text(cell) -> str:
    text = " ".join(teletype.extractText(p) for p in cell.getElementsByType(P)).strip()
    if text:
        return text
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
    short = name[:3]
    yy = year % 100
    patterns = [
        rf"\b{name}\s+{year}\b", rf"\b{short}\s+{year}\b",
        rf"\b{name}[-/ ]{yy:02d}\b", rf"\b{short}[-/ ]{yy:02d}\b",
        rf"\b{year}[-/ ]0?{month}(?:\b|[-/]\d{{1,2}})",
        rf"\b0?{month}[-/ ]{year}\b", rf"\b0?{month}[-/ ]{yy:02d}\b",
        rf"\b{year}\s+{name}\b", rf"\b{year}\s+{short}\b",
    ]
    return any(re.search(p, text, re.I) for p in patterns)


def _num(value: str) -> int | None:
    s = value.strip().replace(",", "").replace(" ", "")
    if re.fullmatch(r"\d+(?:\.0+)?", s):
        return int(float(s))
    return None


def _fuel_label(text: str) -> str | None:
    low = text.lower()
    # Non-zero must be tested first because it contains "zero emission".
    for raw in sorted(FUEL, key=len, reverse=True):
        if raw in low:
            return FUEL[raw]
    return None


def parse_ods(blob: bytes, year: int, month: int):
    doc = load(BytesIO(blob))
    tables: list[tuple[str, list[list[str]]]] = []
    for table in doc.spreadsheet.getElementsByType(Table):
        rows = []
        for row in table.getElementsByType(TableRow):
            vals = _cells(row)
            if any(v.strip() for v in vals):
                rows.append(vals)
        if rows:
            tables.append((table.getAttribute("name") or "<unnamed>", rows))

    agg: dict[str, int] = defaultdict(int)
    direct_totals: list[int] = []
    debug_headers: list[str] = []

    for table_name, rows in tables:
        width = max(map(len, rows))
        target_cols = []
        for col in range(width):
            # VEH9902 has changed formatting over time.  Search a generous
            # header window and accept Aug-26 as well as August 2026 / ISO dates.
            header = " | ".join(r[col] for r in rows[:40] if col < len(r) and r[col])
            if _period_matches(header, year, month):
                target_cols.append(col)
        if not target_cols:
            sample = " || ".join(" | ".join(r[:12]) for r in rows[:15])
            debug_headers.append(f"{table_name}: {sample[:2500]}")
            continue

        first_target = min(target_cols)
        in_cars = False
        for vals in rows:
            label = " | ".join(vals[:first_target] if first_target > 0 else vals).strip()
            low = label.lower()
            if re.search(r"\bcars?\b", low) and "light goods" not in low and "lgv" not in low:
                in_cars = True
            if "light goods" in low or re.search(r"\blgv\b", low):
                in_cars = False
            if not in_cars:
                continue

            values = []
            for col in target_cols:
                if col < len(vals):
                    n = _num(vals[col])
                    if n is not None and 0 <= n <= MAX_PLAUSIBLE:
                        values.append(n)
            values = list(dict.fromkeys(values))
            if len(values) != 1:
                continue

            fuel = _fuel_label(label)
            if fuel:
                agg[fuel] += values[0]
            # Prefer an explicit Cars total row if the workbook supplies one.
            # It is safer than reconstructing a total from overlapping categories.
            if re.search(r"\bcars?\b", low) and not fuel and "total" in low:
                direct_totals.append(values[0])

    reconstructed = sum(agg.values())
    total = next((n for n in direct_totals if MIN_PLAUSIBLE <= n <= MAX_PLAUSIBLE), reconstructed)
    if not MIN_PLAUSIBLE <= total <= MAX_PLAUSIBLE:
        raise RuntimeError(
            "VEH9902 parse failed plausibility check: "
            f"fuels={dict(agg)}, direct_totals={direct_totals}, total={total:,}; "
            "headers=" + " /// ".join(debug_headers)[:7000]
        )
    return year, month, dict(agg), total


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
    year, month, fuel, total = parse_ods(r.content, year, month)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if fuel:
        pt = {(int(row["year"]), int(row["month"]), row["fuel"]): int(row["count"])
              for row in _read_existing(OUT_PT)
              if (int(row["year"]), int(row["month"])) != (year, month)}
        for f, c in fuel.items():
            pt[(year, month, f)] = c
        with OUT_PT.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh); w.writerow(["year", "month", "fuel", "count"])
            for (y, m, f), c in sorted(pt.items()):
                w.writerow([y, m, f, c])

    totals = {(int(row["year"]), int(row["month"])): int(row["total"])
              for row in _read_existing(OUT_TOTAL)
              if (int(row["year"]), int(row["month"])) != (year, month)}
    totals[(year, month)] = total
    with OUT_TOTAL.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "month", "total"])
        for (y, m), c in sorted(totals.items()):
            w.writerow([y, m, c])

    print(f"[write] {OUT_TOTAL.relative_to(REPO_ROOT)}: {year}-{month:02d} = {total:,} cars")
    if fuel:
        print(f"[write] {OUT_PT.relative_to(REPO_ROOT)}: {fuel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
