#!/usr/bin/env python3
"""Assemble a uniform multi-country "core" dataset for the site's country picker.

Reads each country's registration data and emits ``docs/data/countries.json`` —
a list of per-country cores with a comparable shape (monthly totals, brand
totals, origin totals) so the front-end can aggregate any selected subset of
countries. Brand names are canonicalised across registers (see ``eu_brands``).

Country-specific deep dives (German KBA segments, the supplier installation-rate
pages) stay in ``germany.json``; this file only powers the cross-country
overview and the top-right country selector.

Run after ``parse_germany.py`` and ``download_netherlands.py``.
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
OUT = REPO_ROOT / "docs" / "data" / "countries.json"

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _label(y: int, m: int) -> str:
    return f"{MONTH_ABBR[m - 1]} {y}"


def _core(code, name, flag, source, source_url,
          monthly_total: dict[tuple[int, int], int],
          brand_month: dict[tuple[int, int], dict[str, int]]) -> dict:
    keys = sorted(monthly_total)
    months = [{"ym": f"{y:04d}-{m:02d}", "label": _label(y, m), "total": monthly_total[(y, m)]}
              for (y, m) in keys]
    brand_totals: dict[str, int] = defaultdict(int)
    origin_totals: dict[str, int] = defaultdict(int)
    for (_, _), bm in brand_month.items():
        for brand, cnt in bm.items():
            cb = canonical(brand)
            brand_totals[cb] += cnt
            origin_totals[origin(brand)] += cnt
    brands = [{"brand": b, "total": t}
              for b, t in sorted(brand_totals.items(), key=lambda kv: -kv[1])]
    origins = [{"origin": o, "total": t}
               for o, t in sorted(origin_totals.items(), key=lambda kv: -kv[1])]
    window = f"{months[0]['label']} – {months[-1]['label']}" if months else ""
    return {
        "code": code, "name": name, "flag": flag,
        "source": source, "source_url": source_url,
        "window": window, "months": months,
        "brand_totals": brands, "origin_totals": origins,
        "total": sum(monthly_total.values()),
    }


def germany_core() -> dict:
    # Authoritative monthly totals from the built summary; brand detail from CSV.
    site = json.loads(GERMANY_JSON.read_text(encoding="utf-8"))
    monthly_total: dict[tuple[int, int], int] = {}
    for mo in site.get("months", []):
        if mo.get("total"):
            monthly_total[(mo["year"], mo["month"])] = mo["total"]
    brand_month: dict[tuple[int, int], dict[str, int]] = defaultdict(dict)
    with GERMANY_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["row_type"] != "brand_total" or r["drivetrain"] != "total":
                continue
            if not r["count_month"]:
                continue
            key = (int(r["year"]), int(r["month"]))
            if key not in monthly_total:
                continue  # keep brands aligned to the detailed-total window
            brand_month[key][r["brand"].strip()] = int(r["count_month"])
    return _core("DE", "Germany", "🇩🇪",
                 "Kraftfahrt-Bundesamt (KBA), table FZ 10.1",
                 "https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html",
                 monthly_total, brand_month)


def csv_core(csv_path, code, name, flag, source, source_url) -> dict | None:
    """Core from a simple year,month,brand,count CSV (NL, FI, …)."""
    if not csv_path.exists():
        return None
    monthly_total: dict[tuple[int, int], int] = defaultdict(int)
    brand_month: dict[tuple[int, int], dict[str, int]] = defaultdict(dict)
    with csv_path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (int(r["year"]), int(r["month"]))
            cnt = int(r["count"])
            b = r["brand"].strip()
            monthly_total[key] += cnt
            brand_month[key][b] = brand_month[key].get(b, 0) + cnt
    return _core(code, name, flag, source, source_url, dict(monthly_total), brand_month)


def main() -> int:
    countries = [germany_core()]
    for core in (
        csv_core(NL_CSV, "NL", "Netherlands", "🇳🇱",
                 "RDW open data (Socrata dataset m9d7-ebf2)", "https://opendata.rdw.nl/"),
        csv_core(FI_CSV, "FI", "Finland", "🇫🇮",
                 "Traficom / Statistics Finland (PxWeb open data)",
                 "https://trafi2.stat.fi/PXWeb/pxweb/en/TraFi/"),
    ):
        if core:
            countries.append(core)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(countries, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = ", ".join(f"{c['code']}({len(c['months'])}mo, {c['total']:,})" for c in countries)
    print(f"[countries] wrote {OUT.relative_to(REPO_ROOT)}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
