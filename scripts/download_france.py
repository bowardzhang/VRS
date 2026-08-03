#!/usr/bin/env python3
"""Download new passenger-car registrations for France.

Totals (monthly): INSEE Banque de données macroéconomiques (BDM), series
``010756763`` "Immatriculations de voitures particulières neuves – données
brutes", fetched as SDMX-ML (no key). Brand/model detail is not openly published
(it is processed commercially by AAA Data), so France is total-only for brands.

Powertrain (annual): the "Part de voitures particulières neuves par source
d'énergie" open dataset (Tableau de bord des mobilités durables / SDES) on
data.gouv.fr — France's only open powertrain breakdown is *annual*, so this is
kept separate and labelled as such.

Writes ``data/France/insee_monthly_total.csv`` and
``data/France/fr_powertrain_annual.csv``.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "France"
OUT_CSV = OUT_DIR / "insee_monthly_total.csv"
POWERTRAIN_CSV = OUT_DIR / "fr_powertrain_annual.csv"

SERIES = "010756763"
URL = f"https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{SERIES}"

# data.gouv.fr dataset holding the annual national energy-mix CSV.
ENERGY_DATASET_API = ("https://www.data.gouv.fr/api/1/datasets/"
                      "part-de-voitures-particulieres-vp-neuves-par-source-denergie/")
FR_FUEL = {
    "Electrique et hydrogène": "BEV",
    "Hybride rechargeable": "PHEV",
    "Essence - hybride NR": "Hybrid",
    "Diesel - hybride NR": "Hybrid",
    "Essence - thermique": "Petrol",
    "Diesel - thermique": "Diesel",
    "Gaz et ND": "Other",
}

_OBS_A = re.compile(r'TIME_PERIOD="(\d{4})-(\d{2})"[^>]*?OBS_VALUE="([0-9.]+)"')
_OBS_B = re.compile(r'OBS_VALUE="([0-9.]+)"[^>]*?TIME_PERIOD="(\d{4})-(\d{2})"')


def fetch(retries: int = 4) -> str:
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return ""


def _get(url: str, retries: int = 4) -> bytes:
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return b""


def fetch_powertrain() -> dict[tuple[int, str], int]:
    """Annual France-national energy mix (year, canonical fuel) -> vehicle count."""
    meta = json.loads(_get(ENERGY_DATASET_API).decode("utf-8"))
    fr_url = None
    for r in meta.get("resources", []):
        u = (r.get("url") or "")
        if u.endswith("energie-fr.csv") or u.endswith("energie_fr.csv"):
            fr_url = u
            break
    if not fr_url:
        return {}
    text = _get(fr_url).decode("utf-8-sig", errors="replace")
    out: dict[tuple[int, str], int] = defaultdict(int)
    for row in csv.DictReader(text.splitlines()):
        if (row.get("code_fr") or "").strip() != "FR_TOT":
            continue
        fuel = FR_FUEL.get((row.get("type_energie") or "").strip(), "Other")
        try:
            out[(int(row["annee"]), fuel)] += int(float(row["numerateur"]))
        except (ValueError, TypeError):
            pass
    return out


def parse(xml: str) -> dict[tuple[int, int], int]:
    out: dict[tuple[int, int], int] = {}
    for y, m, v in _OBS_A.findall(xml):
        out[(int(y), int(m))] = int(round(float(v)))
    for v, y, m in _OBS_B.findall(xml):
        out.setdefault((int(y), int(m)), int(round(float(v))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", default="2019-01", help="start month YYYY-MM")
    ap.add_argument("--to", dest="to", help="end month YYYY-MM (default: all available)")
    args = ap.parse_args()
    lo = tuple(map(int, args.frm.split("-")))
    hi = tuple(map(int, args.to.split("-"))) if args.to else (9999, 12)

    data = parse(fetch())
    rows = sorted((ym, v) for ym, v in data.items() if lo <= ym <= hi)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "month", "total"])
        for (y, m), v in rows:
            w.writerow([y, m, v])
    if rows:
        print(f"[fr] {rows[0][0][0]}-{rows[0][0][1]:02d} .. {rows[-1][0][0]}-{rows[-1][0][1]:02d}, "
              f"{len(rows)} months")
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(rows)} rows)")

    pt = fetch_powertrain()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with POWERTRAIN_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "fuel", "count"])
        for (y, f), c in sorted(pt.items()):
            w.writerow([y, f, c])
    yrs = sorted({y for y, _ in pt})
    print(f"[write] {POWERTRAIN_CSV.relative_to(REPO_ROOT)} ({len(pt)} rows, "
          f"{yrs[0] if yrs else '-'}..{yrs[-1] if yrs else '-'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
