#!/usr/bin/env python3
"""Cross-country supplier installation-rate ("上装率") comparison.

The per-model electronics configuration in ``data/vehicle_specs.csv`` is keyed
by the German KBA vocabulary, and ``parse_suppliers.py`` joins it onto German
registrations only.  The Netherlands, Finland, the UK and Spain also publish
*model-level* registration counts, so the same estimate can be projected onto
those markets to compare, say, Qualcomm's cockpit-SoC share in Germany vs the
UK vs Spain.

This script joins the spec onto each country's model counts via
``supplier_normalize.SupplierMatcher`` (which reconciles the different naming
conventions), reuses the exact bucketing semantics of ``parse_suppliers.py``
(supplier share is taken over the *classified* volume, unmatched models fall
into ``Unclassified`` and are surfaced as a transparent coverage %), and writes
``docs/data/suppliers_geo.json`` for the secondary supplier pages.

Only the four *volume-weighted* dimensions (cockpit SoC, ADAS SoC, front radar,
LiDAR) are comparable across countries — the EV power-semiconductor dimension is
weighted by per-model BEV counts, which only the German feed carries, so it is
intentionally excluded here.

Run after the per-country model CSVs and ``parse_suppliers.py`` exist; ordering
in the monthly workflow: parse_germany -> parse_suppliers -> parse_suppliers_geo
-> build_supplier_pages -> build_site.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supplier_normalize import SupplierMatcher  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_CSV = REPO_ROOT / "data" / "vehicle_specs.csv"
OUT_JSON = REPO_ROOT / "docs" / "data" / "suppliers_geo.json"

# The volume-weighted dimensions, mirrored from parse_suppliers.DIMENSIONS but
# without the BEV-weighted power-semi dimension (no per-model BEV split abroad).
DIMENSIONS = [
    {"key": "soc", "field": "soc_brand", "title": "Cockpit SoC", "cn": "座舱域控芯片",
     "kind": "share", "blurb": "In-vehicle infotainment / cockpit domain-controller compute."},
    {"key": "adas", "field": "adas_soc", "title": "ADAS / perception SoC", "cn": "智驾感知芯片",
     "kind": "share", "blurb": "Front-camera / driver-assistance perception processor."},
    {"key": "radar", "field": "radar_tier1", "title": "Front-radar Tier-1", "cn": "前向毫米波雷达",
     "kind": "share", "blurb": "Front radar module supplier (ACC / AEB)."},
    {"key": "lidar", "field": "__lidar__", "title": "LiDAR", "cn": "激光雷达",
     "kind": "penetration", "blurb": "LiDAR fitment (standard-config estimate) and supplier."},
]

NON_SUPPLIER = {"Unclassified", "No LiDAR"}


def load_specs() -> dict[tuple[str, str], dict]:
    specs: dict[tuple[str, str], dict] = {}
    with SPECS_CSV.open(encoding="utf-8") as fh:
        header: list[str] | None = None
        for raw in fh:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            row = next(csv.reader([raw]))
            if header is None:
                header = row
                continue
            rec = dict(zip(header, row))
            specs[(rec["brand"].strip().upper(), rec["model"].strip().upper())] = rec
    return specs


def _bucket(rec, field):
    if rec is None:
        return "Unclassified"
    if field == "__lidar__":
        li = (rec.get("lidar") or "").strip()
        if li in ("yes", "optional"):
            return (rec.get("lidar_brand") or "Unknown").strip() or "Unknown"
        return "No LiDAR"
    return (rec.get(field) or "").strip() or "Unclassified"


# ---- per-country model loaders: each yields (brand, model, count) tuples ----

def _load_germany():
    path = REPO_ROOT / "data" / "Germany" / "processed" / "germany_registrations.csv"
    if not path.exists():
        return None
    tot: dict[tuple[str, str], int] = defaultdict(int)
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["row_type"] != "model" or not r["model"] or r["drivetrain"] != "total":
                continue
            try:
                c = int(r["count_month"] or 0)
            except ValueError:
                c = 0
            if c > 0:
                tot[(r["brand"].strip(), r["model"].strip())] += c
    return [(b, m, c) for (b, m), c in tot.items()]


def _load_simple(path: Path, brand_col: str, model_col: str, count_col: str):
    if not path.exists():
        return None
    out = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                c = int(r[count_col] or 0)
            except ValueError:
                c = 0
            if c > 0:
                out.append((r[brand_col].strip(), r[model_col].strip(), c))
    return out


def _load_finland():
    # No brand column: the brand is the first token of the model label.
    path = REPO_ROOT / "data" / "Finland" / "traficom_models.csv"
    if not path.exists():
        return None
    out = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            lbl = r["model_label"].strip()
            try:
                c = int(r["total"] or 0)
            except ValueError:
                c = 0
            if c > 0 and lbl:
                out.append((lbl.split(" ")[0], lbl, c))
    return out


def _load_spain():
    # Monthly rows -> aggregate to whole-window totals.
    path = REPO_ROOT / "data" / "Spain" / "es_monthly_models.csv"
    if not path.exists():
        return None
    tot: dict[tuple[str, str], int] = defaultdict(int)
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                c = int(r["count"] or 0)
            except ValueError:
                c = 0
            if c > 0:
                tot[(r["brand"].strip(), r["model"].strip())] += c
    return [(b, m, c) for (b, m), c in tot.items()]


COUNTRIES = [
    {"key": "Germany", "label": "Germany", "flag": "🇩🇪",
     "load": _load_germany, "source": "KBA FZ 10.1"},
    {"key": "UnitedKingdom", "label": "United Kingdom", "flag": "🇬🇧",
     "load": lambda: _load_simple(REPO_ROOT / "data" / "UnitedKingdom" / "uk_models.csv",
                                  "brand", "model", "total"),
     "source": "SMMT / DfT"},
    {"key": "Spain", "label": "Spain", "flag": "🇪🇸",
     "load": _load_spain, "source": "DGT microdata"},
    {"key": "Finland", "label": "Finland", "flag": "🇫🇮",
     "load": _load_finland, "source": "Traficom"},
    {"key": "Netherlands", "label": "Netherlands", "flag": "🇳🇱",
     "load": lambda: _load_simple(REPO_ROOT / "data" / "Netherlands" / "rdw_models.csv",
                                  "brand", "model", "total"),
     "source": "RDW"},
]


def bucket_country(specs, matcher, rows, field):
    """Return {bucket: volume} and total volume for one dimension/country."""
    buckets: dict[str, int] = defaultdict(int)
    total = 0
    for brand, model, cnt in rows:
        total += cnt
        key = matcher.resolve(brand, model)
        rec = specs.get(key) if key else None
        buckets[_bucket(rec, field)] += cnt
    return buckets, total


def summarize(buckets, total, kind):
    """Turn raw bucket volumes into the share/penetration payload for one cell."""
    non_supplier = sum(buckets.get(k, 0) for k in NON_SUPPLIER)
    classified = total - non_supplier
    share = []
    for name in sorted(buckets, key=lambda b: (-buckets[b], b)):
        if name in NON_SUPPLIER:
            continue
        v = buckets[name]
        share.append({
            "brand": name,
            "total": v,
            "share_classified": round(100 * v / classified, 2) if classified else 0,
        })
    cell = {
        "base_total": total,
        "classified": classified,
        "coverage_pct": round(100 * classified / total, 1) if total else 0,
        "share": share,
    }
    if kind == "penetration":
        # equipped = classified (everything not "No LiDAR"/"Unclassified")
        cell["penetration_pct"] = round(100 * classified / total, 3) if total else 0
    return cell


def main() -> int:
    if not SPECS_CSV.exists():
        print(f"Missing {SPECS_CSV}")
        return 1
    specs = load_specs()
    matcher = SupplierMatcher(specs.keys())

    # Load every available country once.
    loaded = []
    for c in COUNTRIES:
        rows = c["load"]()
        if rows:
            loaded.append((c, rows))
        else:
            print(f"[geo] {c['label']}: no model data, skipped")

    countries_meta = []
    # dim key -> country key -> cell
    cells: dict[str, dict[str, dict]] = {d["key"]: {} for d in DIMENSIONS}
    pooled_rows: list[tuple[str, str, int]] = []

    for c, rows in loaded:
        countries_meta.append({
            "key": c["key"], "label": c["label"], "flag": c["flag"],
            "source": c["source"], "total": sum(r[2] for r in rows),
        })
        pooled_rows.extend(rows)
        for d in DIMENSIONS:
            buckets, total = bucket_country(specs, matcher, rows, d["field"])
            cells[d["key"]][c["key"]] = summarize(buckets, total, d["kind"])

    # Pooled "Europe" across the loaded markets.
    if len(loaded) > 1:
        countries_meta.append({
            "key": "Europe", "label": f"Europe ({len(loaded)})", "flag": "🇪🇺",
            "source": "pooled", "total": sum(r[2] for r in pooled_rows),
        })
        for d in DIMENSIONS:
            buckets, total = bucket_country(specs, matcher, pooled_rows, d["field"])
            cells[d["key"]]["Europe"] = summarize(buckets, total, d["kind"])

    dims_out = []
    for d in DIMENSIONS:
        dims_out.append({
            "key": d["key"], "title": d["title"], "cn": d["cn"],
            "kind": d["kind"], "blurb": d["blurb"],
            "by_country": cells[d["key"]],
        })

    payload = {
        "note": (
            "Cross-country projection of the per-model electronics estimate in "
            "data/vehicle_specs.csv onto each market's model-level registrations. "
            "Model names are matched to the KBA config vocabulary; unmatched "
            "models fall into the coverage gap and are excluded from the shares. "
            "Windows differ by country (see each source), so compare SHARES, not "
            "absolute volumes. The power-semiconductor dimension is omitted "
            "abroad (needs per-model BEV split, German feed only)."
        ),
        "countries": countries_meta,
        "dimensions": dims_out,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[geo] wrote {OUT_JSON.relative_to(REPO_ROOT)} — "
          f"{len(countries_meta)} columns, {len(dims_out)} dimensions")
    for cm in countries_meta:
        soc = cells["soc"].get(cm["key"], {})
        print(f"  {cm['flag']} {cm['label']:16} {cm['total']:>9,} regs · "
              f"SoC coverage {soc.get('coverage_pct','?')}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
