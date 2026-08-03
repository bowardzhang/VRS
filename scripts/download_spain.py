#!/usr/bin/env python3
"""Download monthly new passenger-car registrations for Spain (DGT microdata).

Source: DGT (Dirección General de Tráfico) "Microdatos de Matriculaciones de
Vehículos (mensual)" — open per-vehicle registration microdata, one fixed-width
text file per month in a ZIP (no key required). We keep NEW passenger cars
(``COD_TIPO == '40'`` turismo, ``IND_NUEVO_USADO == 'N'``) and aggregate to
brand, model and fuel counts per month — the ~155 MB raw file is never stored.

Fixed-width field offsets (0-indexed) from the MATRABA record layout:
  MARCA_ITV  17:47   MODELO_ITV 47:69   COD_TIPO 91:93
  COD_PROPULSION_ITV 93   IND_NUEVO_USADO 178
DGT's fuel code does not separate hybrids (they fall under petrol/diesel), so
the powertrain buckets are Petrol / Diesel / BEV / Other.

Writes (all incremental, keyed by month):
  data/Spain/es_monthly_brands.csv     (year,month,brand,count)
  data/Spain/es_monthly_models.csv     (year,month,brand,model,count)
  data/Spain/es_monthly_powertrain.csv (year,month,fuel,count)
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "Spain"
BRANDS_CSV = OUT_DIR / "es_monthly_brands.csv"
MODELS_CSV = OUT_DIR / "es_monthly_models.csv"
POWERTRAIN_CSV = OUT_DIR / "es_monthly_powertrain.csv"

URL = ("https://www.dgt.es/microdatos/salida/{y}/{m}/vehiculos/"
       "matriculaciones/export_mensual_mat_{y}{m:02d}.zip")
DEFAULT_FROM = (2023, 9)

FUEL = {"0": "Petrol", "1": "Diesel", "2": "BEV"}  # else -> Other


def last_complete_month() -> tuple[int, int]:
    t = date.today()
    return (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)


def month_range(a, b):
    y, m = a
    while (y, m) <= b:
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def fetch_month(year: int, month: int, retries: int = 3):
    """Return (brands, models, fuels) counters for NEW turismos, or None if 404."""
    url = URL.format(y=year, m=month)
    delay = 3.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                blob = resp.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None  # month not published yet
            if attempt == retries - 1:
                raise
            time.sleep(delay); delay *= 2
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay); delay *= 2

    brands: dict[str, int] = defaultdict(int)
    models: dict[tuple[str, str], int] = defaultdict(int)
    fuels: dict[str, int] = defaultdict(int)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        with z.open(name) as raw:
            for line in io.TextIOWrapper(raw, encoding="latin-1", newline=""):
                # NEW passenger cars only
                if line[91:93] != "40" or line[178:179] != "N":
                    continue
                brand = line[17:47].strip()
                if not brand:
                    continue
                model = line[47:69].strip()
                brands[brand] += 1
                if model:
                    models[(brand, model)] += 1
                fuels[FUEL.get(line[93:94], "Other")] += 1
    return brands, models, fuels


def _load(path, keycols):
    rows = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for r in csv.reader(fh):
                if r and r[0] == "year":
                    continue
                rows[tuple(r[:keycols])] = r
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="frm", help="start month YYYY-MM")
    ap.add_argument("--to", dest="to", help="end month YYYY-MM")
    ap.add_argument("--refresh-last", type=int, default=1,
                    help="re-fetch the trailing N already-stored months (revisions)")
    args = ap.parse_args()
    start = tuple(map(int, args.frm.split("-"))) if args.frm else DEFAULT_FROM
    end = tuple(map(int, args.to.split("-"))) if args.to else last_complete_month()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    brand_rows = _load(BRANDS_CSV, 3)
    model_rows = _load(MODELS_CSV, 4)
    fuel_rows = _load(POWERTRAIN_CSV, 3)

    have = sorted({(int(k[0]), int(k[1])) for k in brand_rows})
    all_months = list(month_range(start, end))
    missing = [ym for ym in all_months if ym not in have]
    refresh = have[-args.refresh_last:] if args.refresh_last and have else []
    todo = sorted(set(missing) | set(m for m in refresh if start <= m <= end))
    print(f"[es] {len(have)} months stored; fetching {len(todo)} "
          f"({len(missing)} new, {len(set(refresh) & set(todo))} refresh)")

    for y, m in todo:
        res = fetch_month(y, m)
        if res is None:
            print(f"  {y}-{m:02d}: not published yet, skipping")
            continue
        brands, models, fuels = res
        for d, keyn in ((brand_rows, 3), (model_rows, 4), (fuel_rows, 3)):
            for k in [kk for kk in d if int(kk[0]) == y and int(kk[1]) == m]:
                del d[k]
        for b, c in brands.items():
            brand_rows[(str(y), str(m), b)] = [y, m, b, c]
        for (b, mo), c in models.items():
            model_rows[(str(y), str(m), b, mo)] = [y, m, b, mo, c]
        for fl, c in fuels.items():
            fuel_rows[(str(y), str(m), fl)] = [y, m, fl, c]
        print(f"  {y}-{m:02d}: {sum(brands.values()):,} cars, "
              f"{len(brands)} brands, {len(models)} models")

    def write(path, header, rows):
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            for r in sorted(rows.values(), key=lambda r: (int(r[0]), int(r[1]),
                            -int(r[-1]))):
                w.writerow(r)

    write(BRANDS_CSV, ["year", "month", "brand", "count"], brand_rows)
    write(MODELS_CSV, ["year", "month", "brand", "model", "count"], model_rows)
    write(POWERTRAIN_CSV, ["year", "month", "fuel", "count"], fuel_rows)
    print(f"[write] {BRANDS_CSV.relative_to(REPO_ROOT)} ({len(brand_rows)}), "
          f"models ({len(model_rows)}), powertrain ({len(fuel_rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
