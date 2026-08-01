#!/usr/bin/env python3
"""Parse KBA FZ 11 (Segmente) workbooks into a body-segment monthly series.

Reads every ``data/Germany/fz11_<YYYY>_<MM>.xlsx`` workbook, extracts each
segment's monthly total, maps the KBA segments to body-shape categories
(sedan/hatch, SUV, MPV/van, sports, other) and augments
``docs/data/germany.json`` with a ``segment_trends`` block for the static site.

FZ 11 uses the same column template as FZ 10.1, so we reuse
``parse_germany.parse_workbook`` (its ``_pick_sheet`` selects the FZ 11 sheet
because it is the only non-cover sheet). Run this after ``parse_germany.py`` and
before ``build_site.py``.

Diagnostics are printed to stderr so the exact segment labels are visible in CI
logs; any segment label that does not map to a category is reported as a WARN.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from parse_germany import (
    MONTH_NAMES,
    GRAND_TOTAL_KEY,
    parse_workbook,
    _n,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "Germany"
SITE_JSON = REPO_ROOT / "docs" / "data" / "germany.json"
FILE_RE = re.compile(r"fz11_(\d{4})_(\d{2})\.xlsx$", re.IGNORECASE)

# KBA segment label (matched as an UPPER-case substring) -> body category.
# Order matters: more specific keys first (e.g. "OBERE MITTELKLASSE").
SEGMENT_CATEGORY: list[tuple[str, str]] = [
    ("MINIS", "Sedan & hatch"),
    ("KLEINWAGEN", "Sedan & hatch"),
    ("KOMPAKT", "Sedan & hatch"),
    ("OBERE MITTELKLASSE", "Sedan & hatch"),
    ("MITTELKLASSE", "Sedan & hatch"),
    ("OBERKLASSE", "Sedan & hatch"),
    ("SUV", "SUV"),
    ("GELÄNDEWAGEN", "SUV"),
    ("GELAENDEWAGEN", "SUV"),
    ("GELANDEWAGEN", "SUV"),
    ("SPORTWAGEN", "Sports"),
    ("MINI-VANS", "MPV & van"),
    ("MINIVANS", "MPV & van"),
    ("GROSSRAUM", "MPV & van"),
    ("VAN", "MPV & van"),
    ("UTILITIES", "Other"),
    ("WOHNMOBILE", "Other"),
    ("SONSTIGE", "Other"),
]
# Display order (largest / most relevant first) and colours for the site.
CATEGORY_ORDER = ["Sedan & hatch", "SUV", "MPV & van", "Sports", "Other"]


def categorise(label: str) -> str | None:
    up = label.upper()
    for key, cat in SEGMENT_CATEGORY:
        if key in up:
            return cat
    return None


def segment_totals(rows: list[dict]) -> dict[str, float]:
    """{segment label: monthly total} from one FZ 11 workbook's parsed rows.

    Prefers the segment subtotal rows (label ending 'ZUSAMMEN'); if the workbook
    has none, falls back to summing the model rows under each segment header.
    """
    subtotals: dict[str, float] = {}
    summed: dict[str, float] = {}
    current: str | None = None
    for r in rows:
        brand = (r["brand"] or "").strip()
        up = brand.upper()
        total = r["metrics"]["total"]["month"]
        if up == GRAND_TOTAL_KEY:
            continue
        if r["kind"] == "brand_total" and total is not None:
            subtotals[brand[:-len("ZUSAMMEN")].strip() or brand] = total
            current = None
        elif up.endswith("ZUSAMMEN") and total is not None:  # aggregate e.g. SONSTIGE
            subtotals[brand[:-len("ZUSAMMEN")].strip() or brand] = total
        elif r["kind"] == "model":
            seg = current if current else brand
            if brand and r["model"]:  # a segment header carries its first model
                current = brand
                seg = brand
            if total is not None and seg:
                summed[seg] = summed.get(seg, 0) + total
    return subtotals if len(subtotals) >= 3 else summed


def main() -> int:
    files = sorted(DATA_DIR.glob("fz11_*.xlsx"))
    if not files:
        print("[segments] no fz11_*.xlsx workbooks found; skipping.")
        return 0
    if not SITE_JSON.exists():
        print(f"[segments] {SITE_JSON} missing; run parse_germany.py first")
        return 1

    month_cats: list[dict] = []
    for path in files:
        m = FILE_RE.search(path.name)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        try:
            _, _, rows = parse_workbook(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[segments] ERROR parsing {path.name}: {exc}", file=sys.stderr)
            continue
        segs = segment_totals(rows)
        print(f"[segments] {path.name}: {len(segs)} segments -> "
              f"{sorted(segs)}", file=sys.stderr)

        cats: dict[str, float] = {}
        for label, total in segs.items():
            cat = categorise(label)
            if cat is None:
                print(f"[segments] WARN unmapped segment '{label}' "
                      f"({path.name})", file=sys.stderr)
                cat = "Other"
            cats[cat] = cats.get(cat, 0) + total
        month_cats.append({"year": year, "month": month, "cats": cats})

    if not month_cats:
        print("[segments] no segments parsed; leaving germany.json unchanged")
        return 0

    month_cats.sort(key=lambda mo: (mo["year"], mo["month"]))
    labels = [f"{MONTH_NAMES[mo['month'] - 1]} {mo['year']}" for mo in month_cats]
    present = [c for c in CATEGORY_ORDER
              if any(mo["cats"].get(c) for mo in month_cats)]
    series = [
        {"name": c, "values": [_n(mo["cats"].get(c)) for mo in month_cats]}
        for c in present
    ]

    site = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    site["segment_trends"] = {"labels": labels, "series": series}
    SITE_JSON.write_text(json.dumps(site, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[segments] wrote segment_trends: {len(labels)} months, "
          f"categories {present}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
