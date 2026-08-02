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

    # Per-vendor, per-month registration tallies for each supplier dimension.
    # A dimension maps a spec field -> vendor bucket; "" / missing -> Unclassified.
    soc_by_month: dict[str, list[int]] = defaultdict(lambda: [0] * n)
    adas_by_month: dict[str, list[int]] = defaultdict(lambda: [0] * n)
    radar_by_month: dict[str, list[int]] = defaultdict(lambda: [0] * n)
    power_by_month: dict[str, list[int]] = defaultdict(lambda: [0] * n)  # BEV-weighted
    dc_by_month = {k: [0] * n for k in ("yes", "partial", "no", "Unclassified")}
    lidar_by_month = {k: [0] * n for k in ("yes", "optional", "no", "Unclassified")}
    total_by_month = [0] * n
    bev_by_month = [0] * n

    # Per-model rollup for the detail table (whole-window totals).
    model_totals: dict[tuple[str, str], int] = defaultdict(int)

    def bucket(rec, field):
        if rec is None:
            return "Unclassified"
        return (rec.get(field) or "").strip() or "Unclassified"

    for y, m, brand, model, cnt, bev in counts:
        i = idx[(y, m)]
        rec = specs.get((brand, model))
        total_by_month[i] += cnt
        bev_by_month[i] += bev
        model_totals[(brand, model)] += cnt

        soc_by_month[bucket(rec, "soc_brand")][i] += cnt
        adas_by_month[bucket(rec, "adas_soc")][i] += cnt
        radar_by_month[bucket(rec, "radar_tier1")][i] += cnt
        power_by_month[bucket(rec, "power_semi")][i] += bev  # weight by BEV regs

        dc = bucket(rec, "domain_controller")
        dc = dc if dc in dc_by_month else "Unclassified"
        dc_by_month[dc][i] += cnt

        li = bucket(rec, "lidar")
        li = li if li in lidar_by_month else "Unclassified"
        lidar_by_month[li][i] += cnt

    grand_total = sum(total_by_month)
    bev_total = sum(bev_by_month)
    classified_total = grand_total - sum(soc_by_month.get("Unclassified", [0] * n))

    def dimension(by_month, base_by_month, base_total, order=None):
        """Whole-window shares + monthly mix series for one supplier dimension."""
        window = {k: sum(v) for k, v in by_month.items()}
        classified = base_total - window.get("Unclassified", 0)
        share = []
        for name in sorted(window, key=lambda b: (-window[b], b)):
            tot = window[name]
            share.append({
                "brand": name,
                "total": tot,
                "share_all": round(100 * tot / base_total, 2) if base_total else 0,
                "share_classified": (
                    round(100 * tot / classified, 2)
                    if classified and name != "Unclassified" else None
                ),
            })
        ordered = [b for b in (order or SOC_ORDER) if b in by_month]
        ordered += [b for b in window if b not in ordered]
        series = [
            {
                "name": name,
                "counts": by_month[name],
                "share": [
                    round(100 * by_month[name][i] / base_by_month[i], 2)
                    if base_by_month[i] else 0
                    for i in range(n)
                ],
            }
            for name in ordered
        ]
        return {
            "share": share, "series": series,
            "classified": classified,
            "coverage_pct": round(100 * classified / base_total, 1) if base_total else 0,
        }

    soc = dimension(soc_by_month, total_by_month, grand_total)
    soc_share, soc_series = soc["share"], soc["series"]
    adas = dimension(adas_by_month, total_by_month, grand_total, ADAS_ORDER)
    radar = dimension(radar_by_month, total_by_month, grand_total, RADAR_ORDER)
    power = dimension(power_by_month, bev_by_month, bev_total, POWER_ORDER)

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
            "adas_soc": (rec.get("adas_soc") if rec else None) or "Unclassified",
            "power_semi": (rec.get("power_semi") if rec else None) or "Unclassified",
            "radar_tier1": (rec.get("radar_tier1") if rec else None) or "Unclassified",
            "confidence": (rec.get("confidence") if rec else None),
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
        "classified_registrations": classified_total,
        "coverage_pct": round(100 * classified_total / grand_total, 1) if grand_total else 0,
        "soc_share": soc_share,
        "soc_series": soc_series,
        "adas": {"share": adas["share"], "series": adas["series"],
                 "coverage_pct": adas["coverage_pct"]},
        "radar": {"share": radar["share"], "series": radar["series"],
                  "coverage_pct": radar["coverage_pct"]},
        "power_semi": {"share": power["share"], "series": power["series"],
                       "coverage_pct": power["coverage_pct"], "base": "BEV registrations"},
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
