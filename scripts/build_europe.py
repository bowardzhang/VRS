#!/usr/bin/env python3
"""Emit ``docs/data/europe.json`` — the euro-area official registration headline.

Reads ``data/Europe/ecb_ea_total.csv`` (ACEA figures via the ECB Data Portal)
and produces a small block for the homepage: latest month + YoY, year-to-date +
YoY, and a monthly series for a sparkline. Attribution is carried in the block
so the page can credit ACEA / ECB.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "data" / "Europe" / "ecb_ea_total.csv"
OUT = REPO_ROOT / "docs" / "data" / "europe.json"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def main() -> int:
    if not SRC.exists():
        print(f"[europe] {SRC} missing; run download_ecb_eu.py first")
        return 0
    totals: dict[tuple[int, int], int] = {}
    with SRC.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            totals[(int(r["year"]), int(r["month"]))] = int(r["total"])
    if not totals:
        return 0

    periods = sorted(totals)
    last = periods[-1]
    ly, lm = last
    prev_year = totals.get((ly - 1, lm))
    yoy = (round(100 * (totals[last] - prev_year) / prev_year, 1)
           if prev_year else None)

    def ytd(year):
        return sum(v for (y, m), v in totals.items() if y == year and m <= lm)
    ytd_cur, ytd_prior = ytd(ly), ytd(ly - 1)
    ytd_yoy = round(100 * (ytd_cur - ytd_prior) / ytd_prior, 1) if ytd_prior else None

    series = [{"label": f"{MONTHS[m - 1]} {y}", "value": totals[(y, m)]}
              for (y, m) in periods[-48:]]

    payload = {
        "label": "Euro area (21)",
        "source": "ACEA, via ECB Data Portal (dataset CAR)",
        "source_url": "https://data.ecb.europa.eu/data/datasets/CAR",
        "note": ("Official euro-area total of new passenger-car registrations. "
                 "ACEA figures redistributed by the ECB; a euro-area aggregate "
                 "only — no per-country, powertrain or manufacturer detail."),
        "latest_period": f"{MONTHS[lm - 1]} {ly}",
        "latest": totals[last],
        "yoy": yoy,
        "ytd": ytd_cur,
        "ytd_year": ly,
        "ytd_yoy": ytd_yoy,
        "series": series,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[europe] wrote {OUT.relative_to(REPO_ROOT)} — latest "
          f"{payload['latest_period']} {payload['latest']:,} (YoY {yoy})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
