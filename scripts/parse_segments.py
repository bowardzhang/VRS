#!/usr/bin/env python3
"""Parse KBA FZ 11 (Segmente) workbooks into a body-segment monthly series.

Reads every ``data/Germany/fz11_<YYYY>_<MM>.xlsx`` workbook, extracts each
segment's monthly total, maps the KBA segments to body-shape categories
(sedan/hatch, SUV, MPV/van, sports, other) and augments
``docs/data/germany.json`` with a ``segment_trends`` block for the static site.

FZ 11 has a narrower column layout than FZ 10.1, so this parser does not reuse
``parse_germany.parse_workbook``: it locates the "Insgesamt" (total) column from
the header and reads the segment subtotal rows (label ending "ZUSAMMEN"). Run it
after ``parse_germany.py`` and before ``build_site.py``.

Rich diagnostics are printed to stderr (chosen sheet, header, and the leading
rows of the newest workbook) so the exact structure is visible in CI logs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

from parse_germany import MONTH_NAMES, _pick_sheet, _num, _n

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
CATEGORY_ORDER = ["Sedan & hatch", "SUV", "MPV & van", "Sports", "Other"]

GRAND_TOTAL = "NEUZULASSUNGEN INSGESAMT"


def categorise(label: str) -> str | None:
    up = label.upper()
    for key, cat in SEGMENT_CATEGORY:
        if key in up:
            return cat
    return None


def _label(row, upto: int = 4) -> str:
    """Join the leading string cells of a row into one label."""
    parts = [str(c).strip() for c in row[:upto] if isinstance(c, str) and c.strip()]
    return " ".join(parts)


def _first_number(row) -> float | None:
    """First numeric cell in a row — the Insgesamt (monthly total) column.

    FZ 11 prefixes an extra segment column, so the total is not at a fixed index;
    on a segment subtotal row the first number is the segment's monthly total.
    """
    for c in row:
        v = _num(c)
        if v is not None:
            return v
    return None


def parse_fz11(path: Path, *, dump: bool = False) -> dict[str, float]:
    """Return {segment label: monthly total} for one FZ 11 workbook."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = _pick_sheet(wb)
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()

    if dump:
        print(f"[segments] sheet='{ws.title}' rows={len(rows)}", file=sys.stderr)
        for i, row in enumerate(rows[:28]):
            lab = _label(row, 6)
            if lab:
                print(f"[segments]   r{i}: '{lab[:48]}' | first_num={_first_number(row)}",
                      file=sys.stderr)

    segs: dict[str, float] = {}
    for row in rows:
        label = _label(row).upper()
        if not label or GRAND_TOTAL in label:
            continue
        if label.endswith("ZUSAMMEN"):
            seg = label[: -len("ZUSAMMEN")].strip()
            val = _first_number(row)
            if seg and val is not None:
                segs[seg] = val
    return segs


def main() -> int:
    files = sorted(DATA_DIR.glob("fz11_*.xlsx"))
    if not files:
        print("[segments] no fz11_*.xlsx workbooks found; skipping.")
        return 0
    if not SITE_JSON.exists():
        print(f"[segments] {SITE_JSON} missing; run parse_germany.py first")
        return 1

    month_cats: list[dict] = []
    for idx, path in enumerate(files):
        m = FILE_RE.search(path.name)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        try:
            segs = parse_fz11(path, dump=(idx == len(files) - 1))
        except Exception as exc:  # noqa: BLE001
            print(f"[segments] ERROR parsing {path.name}: {exc}", file=sys.stderr)
            continue
        print(f"[segments] {path.name}: {len(segs)} segments -> {sorted(segs)}",
              file=sys.stderr)

        cats: dict[str, float] = {}
        for label, total in segs.items():
            cat = categorise(label)
            if cat is None:
                print(f"[segments] WARN unmapped segment '{label}' ({path.name})",
                      file=sys.stderr)
                cat = "Other"
            cats[cat] = cats.get(cat, 0) + total
        if cats:
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
