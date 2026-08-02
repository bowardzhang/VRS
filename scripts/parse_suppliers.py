#!/usr/bin/env python3
"""Join per-model cockpit / LiDAR configuration onto the KBA registration counts
and compute supplier "上装率" (installation / penetration rate) over time.

Reads
  * ``data/vehicle_specs.csv``                      — estimated per-model config
  * ``data/Germany/processed/germany_registrations.csv`` — monthly model counts

and writes a ``suppliers`` block into ``docs/data/germany.json`` for the static
site (``docs/analysis-suppliers.html``). Run *after* ``parse_germany.py`` (which
creates the CSV + base JSON); like ``parse_segments.py`` it only augments the
existing JSON.

The registration figures are official KBA counts; the configuration mapping is
an *estimate* keyed by vehicle platform / brand software generation — see the
header of ``data/vehicle_specs.csv``. Every model that is not in the spec file
is bucketed as ``Unclassified`` and reported separately, so the penetration
shares are always transparent about their coverage.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_CSV = REPO_ROOT / "data" / "vehicle_specs.csv"
REG_CSV = REPO_ROOT / "data" / "Germany" / "processed" / "germany_registrations.csv"
SITE_JSON = REPO_ROOT / "docs" / "data" / "germany.json"

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Ordering / palette hint for the SoC-brand series (front-end may override).
SOC_ORDER = [
    "Qualcomm", "Samsung", "NVIDIA", "Renesas", "AMD",
    "NXP", "MediaTek", "Undisclosed", "None", "Unclassified",
]


def load_specs() -> dict[tuple[str, str], dict]:
    """Parse the hand-authored spec CSV, skipping ``#`` comments / blank lines."""
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
            specs[(rec["brand"].strip(), rec["model"].strip())] = rec
    return specs


def load_monthly_counts() -> list[tuple[int, int, str, str, int]]:
    """Return (year, month, brand, model, count_month) for every model row.

    Uses the ``drivetrain == 'total'`` rows so each model is counted once per
    month with its full registration figure.
    """
    out: list[tuple[int, int, str, str, int]] = []
    with REG_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["row_type"] != "model" or not row["model"]:
                continue
            if row["drivetrain"] != "total":
                continue
            try:
                cnt = int(row["count_month"] or 0)
            except ValueError:
                cnt = 0
            if cnt <= 0:
                continue
            out.append(
                (int(row["year"]), int(row["month"]),
                 row["brand"].strip(), row["model"].strip(), cnt)
            )
    return out


def _soc_bucket(rec: dict | None) -> str:
    if rec is None:
        return "Unclassified"
    val = (rec.get("soc_brand") or "").strip()
    return val or "Unclassified"


def build_suppliers(specs: dict, counts: list) -> dict:
    months = sorted({(y, m) for y, m, *_ in counts})
    labels = [f"{MONTH_NAMES[m - 1]} {y}" for y, m in months]
    idx = {ym: i for i, ym in enumerate(months)}
    n = len(months)

    soc_by_month: dict[str, list[int]] = defaultdict(lambda: [0] * n)
    dc_by_month = {k: [0] * n for k in ("yes", "partial", "no", "Unclassified")}
    lidar_by_month = {k: [0] * n for k in ("yes", "optional", "no", "Unclassified")}
    total_by_month = [0] * n

    # Per-model rollup for the detail table (whole-window totals).
    model_totals: dict[tuple[str, str], int] = defaultdict(int)

    for y, m, brand, model, cnt in counts:
        i = idx[(y, m)]
        rec = specs.get((brand, model))
        total_by_month[i] += cnt
        model_totals[(brand, model)] += cnt

        soc_by_month[_soc_bucket(rec)][i] += cnt

        dc = (rec.get("domain_controller").strip() if rec else "") or "Unclassified"
        dc = dc if dc in dc_by_month else "Unclassified"
        dc_by_month[dc][i] += cnt

        li = (rec.get("lidar").strip() if rec else "") or "Unclassified"
        li = li if li in lidar_by_month else "Unclassified"
        lidar_by_month[li][i] += cnt

    grand_total = sum(total_by_month)
    classified_total = grand_total - sum(soc_by_month.get("Unclassified", [0] * n))

    # ---- Whole-window SoC supplier shares (of ALL and of classified) ----
    soc_window: dict[str, int] = {k: sum(v) for k, v in soc_by_month.items()}
    soc_share = []
    for brand in sorted(soc_window, key=lambda b: (-soc_window[b], b)):
        tot = soc_window[brand]
        soc_share.append({
            "brand": brand,
            "total": tot,
            "share_all": round(100 * tot / grand_total, 2) if grand_total else 0,
            "share_classified": (
                round(100 * tot / classified_total, 2)
                if classified_total and brand != "Unclassified" else None
            ),
        })

    # ---- Monthly SoC-mix series (share of that month's total) ----
    ordered = [b for b in SOC_ORDER if b in soc_by_month]
    ordered += [b for b in soc_window if b not in ordered]
    soc_series = [
        {
            "name": brand,
            "counts": soc_by_month[brand],
            "share": [
                round(100 * soc_by_month[brand][i] / total_by_month[i], 2)
                if total_by_month[i] else 0
                for i in range(n)
            ],
        }
        for brand in ordered
    ]

    # ---- Domain-controller adoption (share with a cockpit domain controller) ----
    dc_adoption = [
        round(100 * dc_by_month["yes"][i] / total_by_month[i], 2)
        if total_by_month[i] else 0
        for i in range(n)
    ]
    dc_window = {k: sum(v) for k, v in dc_by_month.items()}

    # ---- LiDAR penetration ----
    lidar_window = {k: sum(v) for k, v in lidar_by_month.items()}
    lidar_pen = [
        round(100 * (lidar_by_month["yes"][i] + lidar_by_month["optional"][i])
              / total_by_month[i], 3)
        if total_by_month[i] else 0
        for i in range(n)
    ]

    # ---- Detail table: top models with their estimated config ----
    top = sorted(model_totals.items(), key=lambda kv: -kv[1])[:60]
    detail = []
    for (brand, model), tot in top:
        rec = specs.get((brand, model))
        detail.append({
            "brand": brand,
            "model": model,
            "total": tot,
            "domain_controller": (rec.get("domain_controller") if rec else None),
            "soc_brand": _soc_bucket(rec) if rec else "Unclassified",
            "soc_family": (rec.get("soc_family") if rec else None) or "",
            "lidar": (rec.get("lidar") if rec else None),
            "confidence": (rec.get("confidence") if rec else None),
        })

    return {
        "note": (
            "Registration counts are official KBA figures; cockpit SoC and LiDAR "
            "are per-model ESTIMATES mapped by vehicle platform / software "
            "generation (current new-model standard config). See "
            "data/vehicle_specs.csv."
        ),
        "labels": labels,
        "total_registrations": grand_total,
        "classified_registrations": classified_total,
        "coverage_pct": round(100 * classified_total / grand_total, 1) if grand_total else 0,
        "soc_share": soc_share,
        "soc_series": soc_series,
        "dc_adoption": {"labels": labels, "pct": dc_adoption, "window": dc_window},
        "lidar": {"labels": labels, "pct": lidar_pen, "window": lidar_window},
        "top_models": detail,
    }


def main() -> int:
    if not SPECS_CSV.exists():
        print(f"Missing {SPECS_CSV}")
        return 1
    if not REG_CSV.exists():
        print(f"Missing {REG_CSV}; run scripts/parse_germany.py first")
        return 1
    if not SITE_JSON.exists():
        print(f"Missing {SITE_JSON}; run scripts/parse_germany.py first")
        return 1

    specs = load_specs()
    counts = load_monthly_counts()
    block = build_suppliers(specs, counts)

    site = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    site["suppliers"] = block
    SITE_JSON.write_text(
        json.dumps(site, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[suppliers] wrote suppliers block: {len(block['labels'])} months, "
        f"{block['coverage_pct']}% of registrations classified, "
        f"{len(specs)} spec rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
