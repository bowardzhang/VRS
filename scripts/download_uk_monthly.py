#!/usr/bin/env python3
"""Download DfT VEH9902 monthly provisional UK passenger-car registrations."""
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
    for cell in row.getElementsByType(TableCell):
        repeat = int(cell.getAttribute("numbercolumnsrepeated") or 1)
        out.extend([_text(cell)] * min(repeat, 100))
    return out


def discover() -> tuple[str, int, int]:
    r = requests.get(PAGE, timeout=60, headers={"User-Agent": "VRS/1.0"})
    r.raise_for_status()
    pat = re.compile(r'href="([^"]+\.ods[^"]*)"[^>]*>(.*?)</a>', re.I | re.S)
    candidates = []
    for href, html in pat.findall(r.text):
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
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
    return bool(re.search(rf"\b{name}\s+{year}\b", text, re.I))


def _num(value: str) -> int | None:
    s = value.strip().replace(",", "").replace(" ", "")
    return int(float(s)) if re.fullmatch(r"\d+(?:\.0+)?", s) else None


def parse_ods(blob: bytes, year: int, month: int):
    """Parse VEH9902a's documented long format.

    Current schema is Geography | Date | Units | Body Type | Fuel Type | Number | Notes.
    We locate those columns from the header rather than hard-coding indexes, then select
    exactly the requested month + Cars rows.  Fuel Type is currently OTHER/ZEV.
    """
    doc = load(BytesIO(blob))
    agg: dict[str, int] = defaultdict(int)
    matched_rows = []

    for table in doc.spreadsheet.getElementsByType(Table):
        rows = [_cells(row) for row in table.getElementsByType(TableRow)]
        header_idx = None
        cols = None
        for i, vals in enumerate(rows):
            norm = [v.strip().lower() for v in vals]
            required = ["geography", "date", "body type", "fuel type", "number"]
            if all(x in norm for x in required):
                header_idx = i
                cols = {x: norm.index(x) for x in required}
                break
        if header_idx is None or cols is None:
            continue

        for vals in rows[header_idx + 1:]:
            if max(cols.values()) >= len(vals):
                continue
            geography = vals[cols["geography"]].strip()
            date = vals[cols["date"]].strip()
            body = vals[cols["body type"]].strip()
            fuel_raw = vals[cols["fuel type"]].strip().upper()
            number = _num(vals[cols["number"]])
            if geography.lower() != "united kingdom":
                continue
            if not _period_matches(date, year, month):
                continue
            if body.lower() != "cars" or number is None:
                continue
            if not 0 <= number <= MAX_PLAUSIBLE:
                continue
            fuel = {"ZEV": "ZEV", "OTHER": "Non-ZEV"}.get(fuel_raw, fuel_raw)
            agg[fuel] += number
            matched_rows.append((date, body, fuel_raw, number))

    total = sum(agg.values())
    if not agg or not MIN_PLAUSIBLE <= total <= MAX_PLAUSIBLE:
        raise RuntimeError(
            f"VEH9902 parse failed: month={MONTH_NAMES[month-1]} {year}, "
            f"fuels={dict(agg)}, total={total:,}, matched_rows={matched_rows[:10]}"
        )
    print(f"[uk-monthly] matched {matched_rows}")
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
    pt = {(int(row["year"]), int(row["month"]), row["fuel"]): int(row["count"])
          for row in _read_existing(OUT_PT)
          if (int(row["year"]), int(row["month"])) != (year, month)}
    for f, c in fuel.items():
        pt[(year, month, f)] = c
    with OUT_PT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "month", "fuel", "count"])
        for (y, m, f), c in sorted(pt.items()): w.writerow([y, m, f, c])

    totals = {(int(row["year"]), int(row["month"])): int(row["total"])
              for row in _read_existing(OUT_TOTAL)
              if (int(row["year"]), int(row["month"])) != (year, month)}
    totals[(year, month)] = total
    with OUT_TOTAL.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "month", "total"])
        for (y, m), c in sorted(totals.items()): w.writerow([y, m, c])

    print(f"[write] {OUT_TOTAL.relative_to(REPO_ROOT)}: {year}-{month:02d} = {total:,} cars")
    print(f"[write] {OUT_PT.relative_to(REPO_ROOT)}: {fuel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
