#!/usr/bin/env python3
"""Download new car registrations for the United Kingdom (quarterly, by make).

Source: UK Department for Transport (DfT) vehicle licensing statistics, table
``VEH0160`` — vehicles registered for the first time by body type / make /
model. The Great Britain file (``df_VEH0160_GB.csv``) covers every quarter from
2001 Q1. DfT publishes new-registration data *quarterly* (not monthly), so the
UK is represented at quarterly resolution.

We keep body type = "Cars", sum over model/fuel by make and quarter, and write
the compact ``data/UnitedKingdom/uk_quarterly_brands.csv`` (year,quarter,brand,
count) — the ~28 MB source CSV itself is not committed.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "UnitedKingdom"
OUT_CSV = OUT_DIR / "uk_quarterly_brands.csv"
MODELS_CSV = OUT_DIR / "uk_models.csv"
MODELS_LATEST_CSV = OUT_DIR / "uk_models_latest.csv"
POWERTRAIN_CSV = OUT_DIR / "uk_powertrain.csv"
MODELS_SINCE = (2023, 3)  # (year, quarter) — brand/model detail window

# DfT Fuel label -> canonical powertrain bucket.
UK_FUEL = {
    "Petrol": "Petrol", "Diesel": "Diesel", "Battery electric": "BEV",
    "Plug-in hybrid electric (petrol)": "PHEV", "Plug-in hybrid electric (diesel)": "PHEV",
    "Hybrid electric (petrol)": "Hybrid", "Hybrid electric (diesel)": "Hybrid",
    "Fuel cell electric": "Other", "Range extended electric": "Other",
    "Gas": "Other", "Other fuel types": "Other",
}

SRC = "https://assets.publishing.service.gov.uk/media/6a54d2eea6586e258d371d72/df_VEH0160_GB.csv"
_COL = re.compile(r"^(\d{4})\s*Q([1-4])$")


def fetch(retries: int = 4) -> str:
    delay = 3.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(SRC, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read().decode("latin-1")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return ""


def parse(text: str, from_year: int) -> dict[tuple[int, int, str], int]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    periods: list[tuple[int, int, int]] = []  # (col_index, year, quarter)
    for i, h in enumerate(header):
        m = _COL.match(h.strip())
        if m and int(m.group(1)) >= from_year:
            periods.append((i, int(m.group(1)), int(m.group(2))))
    try:
        bt_i = header.index("BodyType")
        mk_i = header.index("Make")
    except ValueError:
        bt_i, mk_i = 0, 1
    data: dict[tuple[int, int, str], int] = {}
    for row in reader:
        if len(row) <= mk_i or row[bt_i].strip() != "Cars":
            continue
        make = row[mk_i].strip().upper()
        if not make:
            continue
        for i, y, q in periods:
            if i >= len(row):
                continue
            raw = row[i].strip().replace(",", "")
            if raw in ("", "-", "[c]", "[x]", "[z]", ".."):
                continue
            try:
                cnt = int(raw)
            except ValueError:
                continue
            if cnt:
                key = (y, q, make)
                data[key] = data.get(key, 0) + cnt
    return data


def parse_models(text: str) -> dict[tuple[str, str], int]:
    """(make, generic model) totals over the recent detail window."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    cols = []
    for i, h in enumerate(header):
        m = _COL.match(h.strip())
        if m and (int(m.group(1)), int(m.group(2))) >= MODELS_SINCE:
            cols.append(i)
    try:
        bt_i = header.index("BodyType"); mk_i = header.index("Make"); gm_i = header.index("GenModel")
    except ValueError:
        return {}
    out: dict[tuple[str, str], int] = {}
    for row in reader:
        if len(row) <= gm_i or row[bt_i].strip() != "Cars":
            continue
        make = row[mk_i].strip().upper()
        model = row[gm_i].strip().upper()
        if not make or not model:
            continue
        tot = 0
        for i in cols:
            if i < len(row):
                raw = row[i].strip().replace(",", "")
                if raw not in ("", "-", "[c]", "[x]", "[z]", ".."):
                    try:
                        tot += int(raw)
                    except ValueError:
                        pass
        if tot:
            out[(make, model)] = out.get((make, model), 0) + tot
    return out


def parse_powertrain(text: str, from_year: int) -> dict:
    """(year, quarter, canonical fuel) totals for Cars."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    periods = []
    for i, h in enumerate(header):
        m = _COL.match(h.strip())
        if m and int(m.group(1)) >= from_year:
            periods.append((i, int(m.group(1)), int(m.group(2))))
    try:
        bt_i = header.index("BodyType"); fu_i = header.index("Fuel")
    except ValueError:
        return {}
    out: dict[tuple[int, int, str], int] = {}
    for row in reader:
        if len(row) <= fu_i or row[bt_i].strip() != "Cars":
            continue
        fuel = UK_FUEL.get(row[fu_i].strip(), "Other")
        for i, y, q in periods:
            if i >= len(row):
                continue
            raw = row[i].strip().replace(",", "")
            if raw not in ("", "-", "[c]", "[x]", "[z]", ".."):
                try:
                    out[(y, q, fuel)] = out.get((y, q, fuel), 0) + int(raw)
                except ValueError:
                    pass
    return out


def parse_models_latest(text: str):
    """(year, quarter, make, genmodel, count) for the most recent quarter only."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    latest = None  # (col_index, year, quarter)
    for i, h in enumerate(header):
        m = _COL.match(h.strip())
        if m:
            yq = (int(m.group(1)), int(m.group(2)))
            if latest is None or yq > (latest[1], latest[2]):
                latest = (i, yq[0], yq[1])
    if not latest:
        return None, []
    ci, ly, lq = latest
    try:
        bt_i = header.index("BodyType"); mk_i = header.index("Make"); gm_i = header.index("GenModel")
    except ValueError:
        return None, []
    out: dict[tuple[str, str], int] = {}
    for row in reader:
        if len(row) <= max(gm_i, ci) or row[bt_i].strip() != "Cars":
            continue
        raw = row[ci].strip().replace(",", "")
        if raw in ("", "-", "[c]", "[x]", "[z]", ".."):
            continue
        try:
            c = int(raw)
        except ValueError:
            continue
        if c:
            key = (row[mk_i].strip().upper(), row[gm_i].strip().upper())
            out[key] = out.get(key, 0) + c
    return (ly, lq), out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-year", type=int, default=2019)
    args = ap.parse_args()
    print(f"[uk] downloading DfT VEH0160_GB (quarterly, cars) from {args.from_year} …")
    text = fetch()
    data = parse(text, args.from_year)
    by_q: dict[tuple[int, int], int] = {}
    for (y, q, _), c in data.items():
        by_q[(y, q)] = by_q.get((y, q), 0) + c
    for yq in sorted(by_q):
        print(f"  {yq[0]} Q{yq[1]}: {by_q[yq]:,} cars")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(data.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1], kv[0][2]))
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "quarter", "brand", "count"])
        for (y, q, b), c in rows:
            w.writerow([y, q, b, c])
    print(f"[write] {OUT_CSV.relative_to(REPO_ROOT)} ({len(rows)} rows)")

    models = parse_models(text)
    with MODELS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["brand", "model", "total"])
        for (mk, md), c in sorted(models.items(), key=lambda kv: -kv[1]):
            w.writerow([mk, md, c])
    print(f"[write] {MODELS_CSV.relative_to(REPO_ROOT)} ({len(models)} brand/model rows)")

    lyq, latest_models = parse_models_latest(text)
    with MODELS_LATEST_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "quarter", "brand", "model", "count"])
        if lyq:
            for (mk, md), c in sorted(latest_models.items(), key=lambda kv: -kv[1]):
                w.writerow([lyq[0], lyq[1], mk, md, c])
    print(f"[write] {MODELS_LATEST_CSV.relative_to(REPO_ROOT)} (latest {lyq}, {len(latest_models)} rows)")

    pt = parse_powertrain(text, args.from_year)
    with POWERTRAIN_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "quarter", "fuel", "count"])
        for (y, q, f), c in sorted(pt.items()):
            w.writerow([y, q, f, c])
    print(f"[write] {POWERTRAIN_CSV.relative_to(REPO_ROOT)} ({len(pt)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
