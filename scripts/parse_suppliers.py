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

# Ordering / palette hint for the supplier series (front-end may override).
SOC_ORDER = [
    "Qualcomm", "Samsung", "NVIDIA", "Renesas", "AMD",
    "NXP", "MediaTek", "Undisclosed", "None", "Unclassified",
]
ADAS_ORDER = ["Mobileye", "NVIDIA", "Tesla", "Denso", "Undisclosed", "None", "Unclassified"]
RADAR_ORDER = ["Continental", "Bosch", "Denso", "Valeo", "HL Klemove",
               "Veoneer/Magna", "Undisclosed", "None", "Unclassified"]
POWER_ORDER = ["Infineon", "STMicro", "onsemi", "BYD Semi", "Undisclosed",
               "None", "Unclassified"]


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
    """Return (year, month, brand, model, count_total, count_bev) per model row.

    Uses the ``drivetrain == 'total'`` rows for the full registration figure and
    the ``drivetrain == 'bev'`` rows for the battery-electric share (used to
    weight the EV traction-inverter power-semiconductor penetration).
    """
    totals: dict[tuple, int] = {}
    bevs: dict[tuple, int] = defaultdict(int)
    with REG_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["row_type"] != "model" or not row["model"]:
                continue
            dt = row["drivetrain"]
            if dt not in ("total", "bev"):
                continue
            try:
                cnt = int(row["count_month"] or 0)
            except ValueError:
                cnt = 0
            key = (int(row["year"]), int(row["month"]),
                   row["brand"].strip(), row["model"].strip())
            if dt == "total":
                if cnt > 0:
                    totals[key] = cnt
            else:  # bev
                if cnt > 0:
                    bevs[key] += cnt
    out: list[tuple[int, int, str, str, int, int]] = []
    for key, tot in totals.items():
        out.append((*key, tot, bevs.get(key, 0)))
    return out


# Dimension definitions: each maps a spec field -> supplier bucket, with a
# weight (registration base) and display metadata. The output shape is uniform
# so a single secondary-page template can render any of them.
DIMENSIONS = [
    {"key": "soc", "field": "soc_brand", "weight": "total", "order": SOC_ORDER,
     "title": "Cockpit SoC", "cn": "座舱域控芯片", "series": True,
     "base": "all registrations", "confidence": "better-sourced",
     "blurb": "In-vehicle infotainment / cockpit domain-controller (车机) compute silicon."},
    {"key": "adas", "field": "adas_soc", "weight": "total", "order": ADAS_ORDER,
     "title": "ADAS / perception SoC", "cn": "智驾感知芯片", "series": True,
     "base": "all registrations", "confidence": "directional estimate",
     "blurb": "Front-camera / driver-assistance perception processor."},
    {"key": "radar", "field": "radar_tier1", "weight": "total", "order": RADAR_ORDER,
     "title": "Front-radar Tier-1", "cn": "前向毫米波雷达", "series": False,
     "base": "all registrations", "confidence": "directional estimate",
     "blurb": "Front radar module supplier (ACC / AEB)."},
    {"key": "power", "field": "power_semi", "weight": "bev", "order": POWER_ORDER,
     "title": "EV inverter power-semi", "cn": "电驱功率半导体", "series": False,
     "base": "BEV registrations", "confidence": "directional estimate",
     "blurb": "Traction-inverter power module (SiC / IGBT), among battery-electric cars."},
    {"key": "lidar", "field": "__lidar__", "weight": "total", "order": None,
     "title": "LiDAR", "cn": "激光雷达", "series": False,
     "base": "all registrations", "confidence": "better-sourced",
     "penetration": True,
     "blurb": "LiDAR fitment (standard-config estimate) and its supplier."},
]


def _bucket(rec, field):
    if rec is None:
        return "Unclassified"
    if field == "__lidar__":
        li = (rec.get("lidar") or "").strip()
        if li in ("yes", "optional"):
            return (rec.get("lidar_brand") or "Unknown").strip() or "Unknown"
        return "No LiDAR"
    return (rec.get(field) or "").strip() or "Unclassified"


NON_SUPPLIER = {"Unclassified", "No LiDAR"}


def build_suppliers(specs: dict, counts: list) -> dict:
    months = sorted({(y, m) for y, m, *_ in counts})
    labels = [f"{MONTH_NAMES[m - 1]} {y}" for y, m in months]
    idx = {ym: i for i, ym in enumerate(months)}
    n = len(months)

    total_by_month = [0] * n
    bev_by_month = [0] * n

    # Per dimension: month series, and per-supplier per-model whole-window totals.
    by_month: dict[str, dict[str, list[int]]] = {
        d["key"]: defaultdict(lambda: [0] * n) for d in DIMENSIONS
    }
    model_wt: dict[str, dict[str, dict]] = {
        d["key"]: defaultdict(lambda: defaultdict(int)) for d in DIMENSIONS
    }

    for y, m, brand, model, cnt, bev in counts:
        i = idx[(y, m)]
        rec = specs.get((brand, model))
        total_by_month[i] += cnt
        bev_by_month[i] += bev
        for d in DIMENSIONS:
            w = bev if d["weight"] == "bev" else cnt
            if w <= 0:
                continue
            b = _bucket(rec, d["field"])
            by_month[d["key"]][b][i] += w
            model_wt[d["key"]][b][(brand, model)] += w

    grand_total = sum(total_by_month)
    bev_total = sum(bev_by_month)

    def base_for(d):
        return (bev_by_month, bev_total) if d["weight"] == "bev" else (total_by_month, grand_total)

    dims_out = []
    for d in DIMENSIONS:
        bm = by_month[d["key"]]
        base_by_month, base_total = base_for(d)
        window = {k: sum(v) for k, v in bm.items()}
        non_supplier = sum(window.get(k, 0) for k in NON_SUPPLIER)
        classified = base_total - non_supplier
        # per-supplier share + top models
        share = []
        for name in sorted(window, key=lambda b: (-window[b], b)):
            tot = window[name]
            top = sorted(model_wt[d["key"]][name].items(), key=lambda kv: -kv[1])[:6]
            share.append({
                "brand": name,
                "total": tot,
                "share_all": round(100 * tot / base_total, 2) if base_total else 0,
                "share_classified": (
                    round(100 * tot / classified, 2)
                    if classified and name not in NON_SUPPLIER else None
                ),
                "is_supplier": name not in NON_SUPPLIER,
                "top_models": [
                    {"brand": b, "model": mo, "total": w} for (b, mo), w in top
                ],
            })
        # monthly mix series (only where useful)
        series = []
        if d.get("series"):
            order = d["order"] or SOC_ORDER
            ordered = [b for b in order if b in bm] + [b for b in window if b not in (order or [])]
            series = [
                {
                    "name": name,
                    "share": [
                        round(100 * bm[name][i] / base_by_month[i], 2)
                        if base_by_month[i] else 0 for i in range(n)
                    ],
                }
                for name in ordered
            ]
        # penetration line (fitment rate) for LiDAR-style adoption dimensions
        penetration = None
        if d.get("penetration"):
            equipped = [0] * n
            for name, arr in bm.items():
                if name not in NON_SUPPLIER:
                    for i in range(n):
                        equipped[i] += arr[i]
            penetration = {
                "labels": labels,
                "pct": [round(100 * equipped[i] / base_by_month[i], 3)
                        if base_by_month[i] else 0 for i in range(n)],
            }

        dims_out.append({
            "key": d["key"], "title": d["title"], "cn": d["cn"],
            "base": d["base"], "confidence": d["confidence"], "blurb": d["blurb"],
            "base_total": base_total,
            "classified": classified,
            "coverage_pct": round(100 * classified / base_total, 1) if base_total else 0,
            "labels": labels,
            "share": share,
            "series": series,
            "penetration": penetration,
        })

    return {
        "note": (
            "Registration counts are official KBA figures; the electronics fields "
            "are per-model ESTIMATES mapped by vehicle platform / software "
            "generation (current new-model standard config). Cockpit SoC & LiDAR "
            "are better-sourced; ADAS SoC, EV power-semi and radar Tier-1 are "
            "lower-confidence OEM/platform-relationship estimates. See "
            "data/vehicle_specs.csv."
        ),
        "labels": labels,
        "total_registrations": grand_total,
        "bev_registrations": bev_total,
        "coverage_pct": next(dd["coverage_pct"] for dd in dims_out if dd["key"] == "soc"),
        "dimensions": dims_out,
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
