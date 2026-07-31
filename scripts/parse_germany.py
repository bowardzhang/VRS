#!/usr/bin/env python3
"""Parse KBA FZ 10.1 workbooks into a tidy dataset for analysis / the website.

Reads every ``data/Germany/fz10_<YYYY>_<MM>.xlsx`` workbook, extracts the
brand / model-series rows from the ``FZ 10.1`` sheet, and writes:

* ``data/Germany/processed/germany_registrations.csv`` — one tidy row per
  (month, brand, model, drivetrain) with the monthly count, year-to-date
  count and share.
* ``docs/data/germany.json`` — a compact summary consumed by the static site
  (monthly totals, brand rankings, fuel-mix and top models).

The reference month is taken from the file name, not from the German month
label inside the sheet, so the parser is language- and layout-stable.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "Germany"
PROCESSED_DIR = DATA_DIR / "processed"
SITE_DATA_DIR = REPO_ROOT / "docs" / "data"

SHEET_NAME = "FZ 10.1"
FILE_RE = re.compile(r"fz10_(\d{4})_(\d{2})\.xlsx$", re.IGNORECASE)

# Column of the *monthly* value for each drivetrain group. The next two
# columns hold the year-to-date value and the share (%). See row 8/9 headers.
DRIVETRAINS: dict[str, int] = {
    "total": 4,
    "diesel": 7,
    "hybrid_incl_plugin": 10,
    "petrol_hybrid_incl_plugin": 13,
    "diesel_hybrid_incl_plugin": 16,
    "hybrid_excl_plugin": 19,
    "petrol_hybrid_excl_plugin": 22,
    "diesel_hybrid_excl_plugin": 25,
    "plugin_hybrid": 28,
    "petrol_plugin_hybrid": 31,
    "diesel_plugin_hybrid": 34,
    "bev": 37,
    "awd": 40,
    "cabriolet": 43,
}

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Rows in column 2 that are aggregates rather than individual brands.
GRAND_TOTAL_KEY = "NEUZULASSUNGEN INSGESAMT"
OTHER_KEY = "SONSTIGE ZUSAMMEN"


def _num(value) -> float | None:
    """Coerce a KBA cell to a number; '-' / blanks / text become None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text in {"", "-", ".", "x", "X"}:
        return None
    text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_workbook(path: Path) -> tuple[int, int, list[dict]]:
    """Return (year, month, rows) for one FZ 10.1 workbook."""
    m = FILE_RE.search(path.name)
    if not m:
        raise ValueError(f"Unexpected file name: {path.name}")
    year, month = int(m.group(1)), int(m.group(2))

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[SHEET_NAME]

    rows: list[dict] = []
    current_brand: str | None = None
    for row in ws.iter_rows(min_row=10, values_only=True):
        # Cells are 0-indexed here; workbook column N -> row[N-1].
        brand_cell = (row[1] or "").strip() if isinstance(row[1], str) else row[1]
        model_cell = (row[2] or "").strip() if isinstance(row[2], str) else row[2]
        total_month = _num(row[3])

        if not brand_cell and not model_cell and total_month is None:
            continue

        label = str(brand_cell or "").strip()
        upper = label.upper()

        # Aggregate rows.
        if upper == GRAND_TOTAL_KEY or upper == OTHER_KEY:
            record_brand, record_model, kind = label, "", "aggregate"
        elif upper.endswith("ZUSAMMEN"):
            # Brand subtotal row, e.g. "ALFA ROMEO ZUSAMMEN".
            record_brand = label[: -len("ZUSAMMEN")].strip()
            record_model, kind = "", "brand_total"
            current_brand = record_brand
        elif label:
            # New brand header with its first model in column 3.
            current_brand = label
            record_brand, record_model, kind = label, str(model_cell or "").strip(), "model"
        else:
            # Continuation model row for the current brand.
            record_brand = current_brand or ""
            record_model, kind = str(model_cell or "").strip(), "model"

        metrics: dict[str, dict] = {}
        for name, col in DRIVETRAINS.items():
            metrics[name] = {
                "month": _num(row[col - 1]),
                "ytd": _num(row[col]),
                "share": _num(row[col + 1]),
            }
        rows.append(
            {
                "brand": record_brand,
                "model": record_model,
                "kind": kind,
                "metrics": metrics,
            }
        )
    wb.close()
    return year, month, rows


def write_tidy_csv(all_rows: list[dict]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "germany_registrations.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["year", "month", "brand", "model", "row_type", "drivetrain",
             "count_month", "count_ytd", "share_pct"]
        )
        for r in all_rows:
            for name, mvals in r["metrics"].items():
                if mvals["month"] is None and mvals["ytd"] is None:
                    continue
                writer.writerow(
                    [r["year"], r["month"], r["brand"], r["model"], r["kind"],
                     name, mvals["month"], mvals["ytd"], mvals["share"]]
                )
    return out


def _n(x):
    """Render a numeric metric as int when whole, else float, else None."""
    if x is None:
        return None
    return int(x) if float(x).is_integer() else x


def build_site_json(months: list[dict]) -> dict:
    """Assemble the compact summary the static site renders."""
    months.sort(key=lambda mo: (mo["year"], mo["month"]))
    monthly_summary = []
    for mo in months:
        rows = mo["rows"]
        total_row = next(
            (r for r in rows if r["brand"].upper() == GRAND_TOTAL_KEY), None
        )
        brand_totals = [r for r in rows if r["kind"] == "brand_total"]

        def brand_metric(r, key):
            return r["metrics"][key]["month"] or 0

        brands_sorted = sorted(
            brand_totals, key=lambda r: brand_metric(r, "total"), reverse=True
        )
        top_brands = [
            {
                "brand": r["brand"],
                "total": _n(r["metrics"]["total"]["month"]),
                "bev": _n(r["metrics"]["bev"]["month"]),
                "diesel": _n(r["metrics"]["diesel"]["month"]),
                "plugin_hybrid": _n(r["metrics"]["plugin_hybrid"]["month"]),
            }
            for r in brands_sorted[:15]
        ]

        models = [r for r in rows if r["kind"] == "model"]
        top_models = sorted(
            models, key=lambda r: r["metrics"]["total"]["month"] or 0, reverse=True
        )[:15]
        top_models_out = [
            {
                "brand": r["brand"],
                "model": r["model"],
                "total": _n(r["metrics"]["total"]["month"]),
                "bev": _n(r["metrics"]["bev"]["month"]),
            }
            for r in top_models
        ]

        grand = total_row["metrics"] if total_row else None
        monthly_summary.append(
            {
                "year": mo["year"],
                "month": mo["month"],
                "label": f"{MONTH_NAMES[mo['month'] - 1]} {mo['year']}",
                "total": _n(grand["total"]["month"]) if grand else None,
                "total_ytd": _n(grand["total"]["ytd"]) if grand else None,
                "bev": _n(grand["bev"]["month"]) if grand else None,
                "diesel": _n(grand["diesel"]["month"]) if grand else None,
                "plugin_hybrid": _n(grand["plugin_hybrid"]["month"]) if grand else None,
                "hybrid_incl_plugin": _n(grand["hybrid_incl_plugin"]["month"]) if grand else None,
                "top_brands": top_brands,
                "top_models": top_models_out,
            }
        )

    latest = monthly_summary[-1] if monthly_summary else None
    return {
        "country": "Germany",
        "source": "Kraftfahrt-Bundesamt (KBA), table FZ 10.1",
        "source_url": (
            "https://www.kba.de/DE/Statistik/Produktkatalog/produkte/"
            "Fahrzeuge/fz10/fz10_gentab.html"
        ),
        "metric": "New passenger-car registrations (Neuzulassungen)",
        "months": monthly_summary,
        "latest": latest,
    }


def main() -> int:
    files = sorted(DATA_DIR.glob("fz10_*.xlsx"))
    if not files:
        print(f"No workbooks found in {DATA_DIR}")
        return 1

    all_rows: list[dict] = []
    months: list[dict] = []
    for path in files:
        year, month, rows = parse_workbook(path)
        for r in rows:
            all_rows.append({"year": year, "month": month, **r})
        months.append({"year": year, "month": month, "rows": rows})
        print(f"[parsed] {path.name}: {len(rows)} rows")

    csv_path = write_tidy_csv(all_rows)
    print(f"[write]  {csv_path.relative_to(REPO_ROOT)} ({len(all_rows)} records)")

    site = build_site_json(months)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    json_path = SITE_DATA_DIR / "germany.json"
    json_path.write_text(json.dumps(site, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[write]  {json_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
