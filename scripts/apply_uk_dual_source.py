#!/usr/bin/env python3
"""Overlay the UK monthly provisional feed onto countries.json.

The common country builder intentionally keeps the historical UK series,
brands and models on DfT VEH0160 (quarterly official).  This small post-build
step adds DfT VEH9902 (monthly provisional) as the UK headline/latest-month
feed without mixing the two periods.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COUNTRIES = ROOT / "docs" / "data" / "countries.json"
MONTHLY_TOTAL = ROOT / "data" / "UnitedKingdom" / "uk_monthly_total.csv"
MONTHLY_PT = ROOT / "data" / "UnitedKingdom" / "uk_monthly_powertrain.csv"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ORDER = ["BEV", "PHEV", "Hybrid", "Petrol", "Diesel", "Other"]
MONTHLY_URL = "https://www.gov.uk/government/statistics/developing-faster-indicators-of-transport-activity"
QUARTERLY_URL = "https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files"


def latest_month() -> tuple[int, int, int] | None:
    if not MONTHLY_TOTAL.exists():
        return None
    rows = list(csv.DictReader(MONTHLY_TOTAL.open(encoding="utf-8")))
    if not rows:
        return None
    row = max(rows, key=lambda r: (int(r["year"]), int(r["month"])))
    return int(row["year"]), int(row["month"]), int(row["total"])


def monthly_powertrain(y: int, m: int) -> dict:
    if not MONTHLY_PT.exists():
        return {"has": False, "shares": []}
    agg: dict[str, int] = defaultdict(int)
    with MONTHLY_PT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (int(r["year"]), int(r["month"])) == (y, m):
                agg[r["fuel"]] += int(r["count"])
    total = sum(agg.values())
    if not total:
        return {"has": False, "shares": []}
    fuels = ORDER + [f for f in agg if f not in ORDER]
    return {
        "has": True,
        "shares": [
            {"fuel": f, "total": agg[f], "pct": round(100 * agg[f] / total, 1)}
            for f in fuels if agg.get(f)
        ],
    }


def main() -> int:
    latest = latest_month()
    if latest is None:
        print("[uk-dual] no monthly feed yet; keeping quarterly-only UK presentation")
        return 0
    y, m, total = latest
    countries = json.loads(COUNTRIES.read_text(encoding="utf-8"))
    uk = next((c for c in countries if c.get("code") == "UK"), None)
    if uk is None:
        raise RuntimeError("UK core missing from countries.json")

    # Preserve the detailed quarterly snapshot produced by build_countries.py.
    quarterly = uk.get("latest") or {}
    quarterly_period = quarterly.get("period", uk.get("latest_period"))
    quarterly_total = quarterly.get("total", uk.get("latest_total"))
    if quarterly:
        quarterly["status"] = "official"
        quarterly["granularity"] = "quarterly"
        quarterly["source"] = "DfT VEH0160"

    label = f"{MONTHS[m - 1]} {y}"
    monthly = {
        "period": label,
        "year": y,
        "month": m,
        "total": total,
        "status": "provisional",
        "granularity": "monthly",
        "source": "DfT VEH9902",
        "source_url": MONTHLY_URL,
        "powertrain": monthly_powertrain(y, m),
    }

    # Headline becomes the freshest monthly provisional passenger-car figure.
    # Historical quarters, brand/model rankings and detailed `latest` remain
    # VEH0160 official-quarter data so periods are never silently mixed.
    uk["latest_period"] = label
    uk["latest_total"] = total
    uk["latest_status"] = "provisional"
    uk["latest_granularity"] = "monthly"
    uk["monthly_latest"] = monthly
    uk["quarterly_latest_period"] = quarterly_period
    uk["quarterly_latest_total"] = quarterly_total
    uk["dual_source"] = True
    uk["source"] = "UK DfT VEH9902 (monthly provisional) + VEH0160 (quarterly official detail)"
    uk["source_url"] = MONTHLY_URL
    uk["monthly_source_url"] = MONTHLY_URL
    uk["quarterly_source_url"] = QUARTERLY_URL

    COUNTRIES.write_text(json.dumps(countries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[uk-dual] headline={label} {total:,}; official detail={quarterly_period} {quarterly_total:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
