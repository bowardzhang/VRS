#!/usr/bin/env python3
"""Assemble a uniform multi-country "core" dataset for the site's country picker.

Reads each country's registration data and emits ``docs/data/countries.json`` —
a list of per-country cores with a comparable shape so the front-end can show,
for any selected subset of countries, a per-country historical trend and
aggregated brand / origin bars.

Because national sources differ in granularity and detail, the core is designed
around the common denominator:

- **quarters** — a full multi-year quarterly total series (the historical
  trend). Monthly sources (DE, NL, FI, FR) are aggregated to *complete* quarters;
  the UK source (DfT) is natively quarterly.
- **brand_totals / origin_totals** — registration-weighted, counted over a common
  recent window (from ``BRAND_WINDOW_START``) so cross-country brand shares are
  comparable. France is total-only (no open brand data) → ``has_brands=false``.

Brand names are canonicalised across registers (see ``eu_brands``).
Run after parse_germany.py + the per-country download_* scripts.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from eu_brands import canonical, origin

REPO_ROOT = Path(__file__).resolve().parent.parent
GERMANY_CSV = REPO_ROOT / "data" / "Germany" / "processed" / "germany_registrations.csv"
GERMANY_JSON = REPO_ROOT / "docs" / "data" / "germany.json"
NL_CSV = REPO_ROOT / "data" / "Netherlands" / "rdw_monthly_brands.csv"
FI_CSV = REPO_ROOT / "data" / "Finland" / "traficom_monthly_brands.csv"
FR_CSV = REPO_ROOT / "data" / "France" / "insee_monthly_total.csv"
UK_CSV = REPO_ROOT / "data" / "UnitedKingdom" / "uk_quarterly_brands.csv"
OUT = REPO_ROOT / "docs" / "data" / "countries.json"

# Count brands/origins only from this month onward, so every brand-capable
# country contributes the same window and the shares stay comparable.
BRAND_WINDOW_START = (2023, 9)


def _q(month: int) -> int:
    return (month - 1) // 3 + 1


def _in_brand_window_month(y: int, m: int) -> bool:
    return (y, m) >= BRAND_WINDOW_START


def _in_brand_window_quarter(y: int, q: int) -> bool:
    return (y, q) >= (BRAND_WINDOW_START[0], _q(BRAND_WINDOW_START[1]))


def _brand_window_label(start=BRAND_WINDOW_START) -> str:
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"since {names[start[1] - 1]} {start[0]}"


def _assemble(code, name, flag, source, source_url, *,
              quarter_total: dict[tuple[int, int], int],
              quarter_complete: dict[tuple[int, int], bool],
              brand_window: dict[str, int] | None) -> dict:
    qs = sorted(q for q, ok in quarter_complete.items() if ok and quarter_total.get(q))
    quarters = [{"q": f"{y}-Q{q}", "label": f"Q{q} {y}", "total": quarter_total[(y, q)]}
                for (y, q) in qs]
    has_brands = brand_window is not None
    brand_totals, origin_totals = [], []
    if has_brands:
        origins: dict[str, int] = defaultdict(int)
        for b, t in brand_window.items():
            origins[origin(b)] += t
        brand_totals = [{"brand": canonical(b), "total": t}
                        for b, t in sorted(brand_window.items(), key=lambda kv: -kv[1])
                        if canonical(b) != "OTHER"]
        origin_totals = [{"origin": o, "total": t}
                         for o, t in sorted(origins.items(), key=lambda kv: -kv[1])]
    return {
        "code": code, "name": name, "flag": flag,
        "source": source, "source_url": source_url,
        "granularity": "quarterly",
        "has_brands": has_brands,
        "brand_window_label": _brand_window_label() if has_brands else "",
        "window": f"{quarters[0]['label']} – {quarters[-1]['label']}" if quarters else "",
        "quarters": quarters,
        "total": sum(quarter_total[(y, q)] for (y, q) in qs),
        "brand_totals": brand_totals,
        "origin_totals": origin_totals,
    }


def _from_monthly(rows, code, name, flag, source, source_url, with_brands: bool) -> dict:
    """rows: iterable of (year, month, brand|None, count)."""
    q_total: dict[tuple[int, int], int] = defaultdict(int)
    q_months: dict[tuple[int, int], set] = defaultdict(set)
    brand_window: dict[str, int] = defaultdict(int)
    for y, m, brand, cnt in rows:
        q = (y, _q(m))
        q_total[q] += cnt
        q_months[q].add(m)
        if with_brands and brand and _in_brand_window_month(y, m):
            brand_window[canonical(brand)] += cnt
    q_complete = {q: len(q_months[q]) == 3 for q in q_total}
    return _assemble(code, name, flag, source, source_url,
                     quarter_total=q_total, quarter_complete=q_complete,
                     brand_window=(brand_window if with_brands else None))


def germany_core() -> dict:
    site = json.loads(GERMANY_JSON.read_text(encoding="utf-8"))
    monthly_total = {(mo["year"], mo["month"]): mo["total"]
                     for mo in site.get("months", []) if mo.get("total")}
    rows = []
    for (y, m), tot in monthly_total.items():
        rows.append((y, m, None, tot))  # total drives the quarterly series
    # brand detail from the tidy CSV (monthly brand_total rows)
    brand_rows = []
    with GERMANY_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["row_type"] != "brand_total" or r["drivetrain"] != "total" or not r["count_month"]:
                continue
            key = (int(r["year"]), int(r["month"]))
            if key not in monthly_total:
                continue
            brand_rows.append((key[0], key[1], r["brand"].strip(), int(r["count_month"])))
    # Build quarters from totals, brand window from brand rows.
    core = _from_monthly(rows, "DE", "Germany", "🇩🇪",
                         "Kraftfahrt-Bundesamt (KBA), table FZ 10.1",
                         "https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html",
                         with_brands=False)
    bw: dict[str, int] = defaultdict(int)
    for y, m, b, c in brand_rows:
        if _in_brand_window_month(y, m):
            bw[canonical(b)] += c
    # attach brands
    origins: dict[str, int] = defaultdict(int)
    for b, t in bw.items():
        origins[origin(b)] += t
    core["has_brands"] = True
    core["brand_window_label"] = _brand_window_label()
    core["brand_totals"] = [{"brand": b, "total": t} for b, t in sorted(bw.items(), key=lambda kv: -kv[1]) if b != "OTHER"]
    core["origin_totals"] = [{"origin": o, "total": t} for o, t in sorted(origins.items(), key=lambda kv: -kv[1])]
    return core


def csv_monthly_brands(path, code, name, flag, source, source_url) -> dict | None:
    if not path.exists():
        return None
    rows = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((int(r["year"]), int(r["month"]), r["brand"].strip(), int(r["count"])))
    return _from_monthly(rows, code, name, flag, source, source_url, with_brands=True)


def france_core() -> dict | None:
    if not FR_CSV.exists():
        return None
    rows = []
    with FR_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((int(r["year"]), int(r["month"]), None, int(r["total"])))
    return _from_monthly(rows, "FR", "France", "🇫🇷",
                         "INSEE / SDES (BDM series 010756763, national totals)",
                         "https://www.insee.fr/fr/statistiques/serie/010756763",
                         with_brands=False)


def uk_core() -> dict | None:
    if not UK_CSV.exists():
        return None
    q_total: dict[tuple[int, int], int] = defaultdict(int)
    brand_window: dict[str, int] = defaultdict(int)
    with UK_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            y, q, b, c = int(r["year"]), int(r["quarter"]), r["brand"].strip(), int(r["count"])
            q_total[(y, q)] += c
            if _in_brand_window_quarter(y, q):
                brand_window[canonical(b)] += c
    q_complete = {q: True for q in q_total}  # DfT publishes complete quarters only
    return _assemble("UK", "United Kingdom", "🇬🇧",
                     "UK Dept. for Transport, table VEH0160 (quarterly)",
                     "https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files",
                     quarter_total=q_total, quarter_complete=q_complete, brand_window=brand_window)


def main() -> int:
    countries = [germany_core()]
    for core in (
        csv_monthly_brands(NL_CSV, "NL", "Netherlands", "🇳🇱",
                           "RDW open data (Socrata dataset m9d7-ebf2)", "https://opendata.rdw.nl/"),
        csv_monthly_brands(FI_CSV, "FI", "Finland", "🇫🇮",
                           "Traficom / Statistics Finland (PxWeb open data)",
                           "https://trafi2.stat.fi/PXWeb/pxweb/en/TraFi/"),
        france_core(),
        uk_core(),
    ):
        if core:
            countries.append(core)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(countries, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = ", ".join(
        f"{c['code']}({len(c['quarters'])}q {c['window']}, {c['total']:,}"
        f"{'' if c['has_brands'] else ', total-only'})" for c in countries)
    print(f"[countries] wrote {OUT.relative_to(REPO_ROOT)}:\n  " + summary.replace(", ", ",\n  "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
