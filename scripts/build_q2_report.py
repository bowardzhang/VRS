#!/usr/bin/env python3
"""Build the secondary page "2026 Q2 European major-market analysis".

For the current quarter (Q2 2026 = Apr–Jun) versus the same quarter a year
earlier (Q2 2025), this aggregates, per country and as a pooled total, the
dimensions the open data actually supports:

  1. Top-10 brands
  2. Top-10 models
  3. Top-8 manufacturer country-of-origin
  4. Powertrain mix
  5. Body type  — NOT available in any open feed; the section says so
  6. Supplier installation rate for the major electronic components

Data availability is uneven, so each dimension carries the set of countries it
can honestly cover (brands/origin: DE/ES/FI/NL/AT; powertrain: DE/ES/FI/SE;
models & suppliers: DE/ES — the only monthly model feeds). The UK is omitted
(SMMT quarterly data still ends Q1 2026); France has only a monthly total.
Everything is a real slice of the same registration feeds used elsewhere in the
site — nothing here is synthesised.

Writes a fully self-contained ``docs/analysis-q2-2026.html`` (data embedded).
Run after the per-country CSVs and parse_germany.py exist.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from eu_brands import canonical, origin  # noqa: E402
from supplier_normalize import SupplierMatcher, _norm_model  # noqa: E402
import parse_suppliers_geo as psg  # noqa: E402

DATA = REPO_ROOT / "data"
OUT_HTML = REPO_ROOT / "docs" / "analysis-q2-2026.html"

CUR = (2026, (4, 5, 6))
PRIOR = (2025, (4, 5, 6))

FLAG = {"Germany": "🇩🇪", "Spain": "🇪🇸", "Finland": "🇫🇮", "Netherlands": "🇳🇱",
        "Austria": "🇦🇹", "Sweden": "🇸🇪", "France": "🇫🇷",
        "UnitedKingdom": "🇬🇧", "Total": "🇪🇺"}
LABEL = {"Germany": "Germany", "Spain": "Spain", "Finland": "Finland",
         "Netherlands": "Netherlands", "Austria": "Austria", "Sweden": "Sweden",
         "France": "France", "UnitedKingdom": "United Kingdom", "Total": "Total"}


def yoy(cur, prior):
    if not prior:
        return None
    return round(100 * (cur - prior) / prior, 1)


def _period_q(period):
    """Map a monthly Q2 period -> (year, quarter). Months (4,5,6) -> Q2."""
    return (period[0], (period[1][0] - 1) // 3 + 1)


def uk_available() -> bool:
    """True once the UK source has the CURRENT quarter (e.g. 2026 Q2)."""
    y, q = _period_q(CUR)
    for r in _rows(DATA / "UnitedKingdom" / "uk_quarterly_brands.csv"):
        if int(r["year"]) == y and int(r["quarter"]) == q:
            return True
    return False


def _rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _in(period, y, m):
    return int(y) == period[0] and int(m) in period[1]


# ---------------- brands / origin (monthly brand feeds) ----------------

BRAND_FEEDS = {
    "Germany": None,  # from germany_registrations (row_type == brand)
    "Spain": (DATA / "Spain" / "es_monthly_brands.csv", "brand", "count"),
    "Finland": (DATA / "Finland" / "traficom_monthly_brands.csv", "brand", "count"),
    "Netherlands": (DATA / "Netherlands" / "rdw_monthly_brands.csv", "brand", "count"),
    "Austria": (DATA / "Austria" / "at_monthly_brands.csv", "brand", "count"),
}


def brand_counts(country, period):
    """canonical brand -> count for one country over a period."""
    out = defaultdict(int)
    if country == "Germany":
        # brand_total rows carry only YTD counts, so sum the model rows (which do
        # carry monthly counts) by brand instead.
        for r in _rows(DATA / "Germany" / "processed" / "germany_registrations.csv"):
            if r.get("row_type") != "model" or r.get("drivetrain") != "total" or not r.get("model"):
                continue
            if _in(period, r["year"], r["month"]):
                out[canonical(r["brand"])] += int(r["count_month"] or 0)
        return out
    if country == "UnitedKingdom":
        y, q = _period_q(period)
        for r in _rows(DATA / "UnitedKingdom" / "uk_quarterly_brands.csv"):
            if int(r["year"]) == y and int(r["quarter"]) == q:
                out[canonical(r["brand"])] += int(r["count"] or 0)
        return out
    spec = BRAND_FEEDS[country]
    path, bcol, ccol = spec
    for r in _rows(path):
        if _in(period, r["year"], r["month"]):
            out[canonical(r[bcol])] += int(r[ccol] or 0)
    return out


def top_series(cur_map, prior_map, n):
    rows = []
    for name in sorted(cur_map, key=lambda k: -cur_map[k])[:n]:
        c, p = cur_map[name], prior_map.get(name, 0)
        rows.append({"name": name, "cur": c, "prior": p, "yoy": yoy(c, p)})
    return rows


# ---------------- models (monthly model feeds: DE, ES) ----------------

def model_counts(country, period):
    out = defaultdict(int)
    if country == "Germany":
        for r in _rows(DATA / "Germany" / "processed" / "germany_registrations.csv"):
            if r.get("row_type") != "model" or r.get("drivetrain") != "total" or not r.get("model"):
                continue
            if _in(period, r["year"], r["month"]):
                label = f'{canonical(r["brand"])} {r["model"].strip()}'
                out[label] += int(r["count_month"] or 0)
    elif country == "Spain":
        for r in _rows(DATA / "Spain" / "es_monthly_models.csv"):
            if _in(period, r["year"], r["month"]):
                out[r["model"].strip().upper()] += int(r["count"] or 0)
    elif country == "Finland":
        for r in _rows(DATA / "Finland" / "traficom_models_monthly.csv"):
            if _in(period, r["year"], r["month"]):
                out[r["model_label"].strip().upper()] += int(r["count"] or 0)
    elif country == "Netherlands":
        # RDW's handelsbenaming sometimes already carries the brand ("TOYOTA
        # AYGO X"), sometimes not ("MODEL Y"); strip a redundant leading brand.
        for r in _rows(DATA / "Netherlands" / "rdw_models_monthly.csv"):
            if _in(period, r["year"], r["month"]):
                b = r["brand"].strip().upper()
                m = _strip_brand(r["model"].strip().upper(), b)
                out[f"{b} {m}"] += int(r["count"] or 0)
    elif country == "UnitedKingdom":
        # DfT GenModel already carries the make ("FORD PUMA"); strip it.
        y, q = _period_q(period)
        for r in _rows(DATA / "UnitedKingdom" / "uk_models_quarterly.csv"):
            if int(r["year"]) == y and int(r["quarter"]) == q:
                b = r["brand"].strip().upper()
                m = _strip_brand(r["model"].strip().upper(), b)
                out[f"{b} {m}"] += int(r["count"] or 0)
    return out


def _strip_brand(model_upper, brand):
    """Drop a leading brand token a feed bakes into the model string."""
    pref = brand.strip().upper()
    if pref and model_upper.startswith(pref + " "):
        return model_upper[len(pref) + 1:].strip()
    return model_upper


def model_counts_pooled(period):
    """DE+ES+FI+NL (+UK once published) pooled by canonical brand + model."""
    out = defaultdict(int)
    disp = {}
    def add(brand_raw, model_raw, cnt):
        b = canonical(brand_raw)
        mm = _strip_brand(model_raw.strip().upper(), brand_raw)
        key = (b, _norm_model(mm))
        out[key] += cnt
        disp.setdefault(key, f"{b} {mm.title()}")
    for r in _rows(DATA / "Germany" / "processed" / "germany_registrations.csv"):
        if r.get("row_type") == "model" and r.get("drivetrain") == "total" and r.get("model"):
            if _in(period, r["year"], r["month"]):
                add(r["brand"], r["model"], int(r["count_month"] or 0))
    for r in _rows(DATA / "Spain" / "es_monthly_models.csv"):
        if _in(period, r["year"], r["month"]):
            add(r["brand"], r["model"], int(r["count"] or 0))
    for r in _rows(DATA / "Finland" / "traficom_models_monthly.csv"):
        if _in(period, r["year"], r["month"]):
            lbl = r["model_label"].strip()
            add(lbl.split(" ")[0], lbl, int(r["count"] or 0))
    for r in _rows(DATA / "Netherlands" / "rdw_models_monthly.csv"):
        if _in(period, r["year"], r["month"]):
            add(r["brand"], r["model"], int(r["count"] or 0))
    # The UK is quarterly and lags: including it only for the *prior* period
    # would inflate the base and push every pooled model YoY negative, so it
    # joins the pool only once the current quarter is published as well.
    if uk_available():
        yq, qq = _period_q(period)
        for r in _rows(DATA / "UnitedKingdom" / "uk_models_quarterly.csv"):
            if int(r["year"]) == yq and int(r["quarter"]) == qq:
                add(r["brand"], r["model"], int(r["count"] or 0))
    return {disp[k]: v for k, v in out.items()}


# ---------------- powertrain ----------------

def powertrain_counts(country, period):
    """bucket -> count for one country over a period. Buckets vary by feed."""
    out = defaultdict(int)
    if country == "Germany":
        # Use germany.json's monthly grand totals, which carry the complete
        # split (BEV+PHEV+HEV+Petrol+Diesel == total). The supplementary
        # kba_monthly_powertrain.csv omits full hybrids (HEV), which would drop
        # ~28% of the market from the denominator and inflate every share.
        MAP = {"bev": "BEV", "plugin_hybrid": "PHEV", "hybrid": "HEV",
               "petrol": "Petrol", "diesel": "Diesel"}
        site = json.loads((REPO_ROOT / "docs" / "data" / "germany.json")
                          .read_text(encoding="utf-8"))
        for m in site.get("months", []):
            if _in(period, m["year"], m["month"]):
                for col, bucket in MAP.items():
                    out[bucket] += int(m.get(col) or 0)
    elif country == "UnitedKingdom":
        y, q = _period_q(period)
        for r in _rows(DATA / "UnitedKingdom" / "uk_powertrain.csv"):
            if int(r["year"]) == y and int(r["quarter"]) == q:
                b = "HEV" if r["fuel"] == "Hybrid" else r["fuel"]
                out[b] += int(r["count"] or 0)
    else:
        path = {"Spain": DATA / "Spain" / "es_monthly_powertrain.csv",
                "Finland": DATA / "Finland" / "traficom_powertrain.csv",
                "Sweden": DATA / "Sweden" / "se_powertrain.csv"}[country]
        REN = {"Hybrid": "HEV"}
        for r in _rows(path):
            if _in(period, r["year"], r["month"]):
                b = REN.get(r["fuel"], r["fuel"])
                out[b] += int(r["count"] or 0)
    return out


PT_ORDER = ["BEV", "PHEV", "HEV", "Petrol", "Diesel", "Other"]


def powertrain_rows(cur_map, prior_map):
    tot_c = sum(cur_map.values()) or 1
    tot_p = sum(prior_map.values()) or 1
    order = [b for b in PT_ORDER if b in cur_map] + [b for b in cur_map if b not in PT_ORDER]
    rows = []
    for name in order:
        c, p = cur_map.get(name, 0), prior_map.get(name, 0)
        rows.append({
            "name": name, "cur": c, "prior": p, "yoy": yoy(c, p),
            "share_cur": round(100 * c / tot_c, 1),
            "share_prior": round(100 * p / tot_p, 1),
        })
    return rows


# ---------------- body type ----------------

_MONTHNAME = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


def body_counts(country, period):
    """category -> count for one country over a period. Native taxonomy per feed."""
    out = defaultdict(int)
    if country == "Germany":
        # KBA FZ 11 size-segments mapped to body categories (segment_trends block).
        site = REPO_ROOT / "docs" / "data" / "germany.json"
        if not site.exists():
            return out
        st = json.loads(site.read_text(encoding="utf-8")).get("segment_trends") or {}
        labels = st.get("labels", [])
        idx = []
        for i, lab in enumerate(labels):
            parts = lab.split()
            if len(parts) == 2 and parts[0] in _MONTHNAME:
                y, m = int(parts[1]), _MONTHNAME[parts[0]]
                if _in(period, y, m):
                    idx.append(i)
        for s in st.get("series", []):
            vals = s.get("values", [])
            out[s["name"]] += sum(vals[i] for i in idx if i < len(vals))
    elif country == "Netherlands":
        for r in _rows(DATA / "Netherlands" / "rdw_body_monthly.csv"):
            if _in(period, r["year"], r["month"]):
                out[r["body"]] += int(r["count"] or 0)
    elif country == "Spain":
        for r in _rows(DATA / "Spain" / "es_monthly_body.csv"):
            if _in(period, r["year"], r["month"]):
                out[r["body"]] += int(r["count"] or 0)
    return out


def body_rows(cur_map, prior_map):
    tot_c = sum(cur_map.values()) or 1
    tot_p = sum(prior_map.values()) or 1
    rows = []
    for name in sorted(cur_map, key=lambda k: -cur_map[k]):
        c, p = cur_map[name], prior_map.get(name, 0)
        rows.append({
            "name": name, "cur": c, "prior": p, "yoy": yoy(c, p),
            "share_cur": round(100 * c / tot_c, 1),
            "share_prior": round(100 * p / tot_p, 1),
        })
    return rows


# ---------------- suppliers (Q2 model slice for DE, ES) ----------------

def supplier_model_rows(country, period):
    """(brand, model, count) list for one country restricted to the period."""
    rows = []
    if country == "Germany":
        for r in _rows(DATA / "Germany" / "processed" / "germany_registrations.csv"):
            if r.get("row_type") == "model" and r.get("drivetrain") == "total" and r.get("model"):
                if _in(period, r["year"], r["month"]):
                    c = int(r["count_month"] or 0)
                    if c > 0:
                        rows.append((r["brand"].strip(), r["model"].strip(), c))
    elif country == "Spain":
        for r in _rows(DATA / "Spain" / "es_monthly_models.csv"):
            if _in(period, r["year"], r["month"]):
                c = int(r["count"] or 0)
                if c > 0:
                    rows.append((r["brand"].strip(), r["model"].strip(), c))
    elif country == "Finland":
        for r in _rows(DATA / "Finland" / "traficom_models_monthly.csv"):
            if _in(period, r["year"], r["month"]):
                c = int(r["count"] or 0)
                if c > 0:
                    lbl = r["model_label"].strip()
                    rows.append((lbl.split(" ")[0], lbl, c))
    elif country == "Netherlands":
        for r in _rows(DATA / "Netherlands" / "rdw_models_monthly.csv"):
            if _in(period, r["year"], r["month"]):
                c = int(r["count"] or 0)
                if c > 0:
                    rows.append((r["brand"].strip(), r["model"].strip(), c))
    elif country == "UnitedKingdom":
        y, q = _period_q(period)
        for r in _rows(DATA / "UnitedKingdom" / "uk_models_quarterly.csv"):
            if int(r["year"]) == y and int(r["quarter"]) == q:
                c = int(r["count"] or 0)
                if c > 0:
                    rows.append((r["brand"].strip(), r["model"].strip(), c))
    return rows


def supplier_dims(specs, matcher, rows_cur, rows_prior):
    """Per component: installation-rate ranking with YoY pp delta."""
    dims = []
    for d in psg.DIMENSIONS:
        if d["kind"] != "share":   # skip LiDAR penetration here (≈0 in Q2)
            continue
        bc, _ = psg.bucket_country(specs, matcher, rows_cur, d["field"])
        bp, _ = psg.bucket_country(specs, matcher, rows_prior, d["field"])
        cur = psg.summarize(bc, sum(v for _, _, v in rows_cur), d["kind"])
        pri = psg.summarize(bp, sum(v for _, _, v in rows_prior), d["kind"])
        prior_share = {s["brand"]: s["share_classified"] for s in pri["share"]}
        ranked = []
        for s in cur["share"]:
            ps = prior_share.get(s["brand"])
            ranked.append({
                "name": s["brand"], "share_cur": s["share_classified"],
                "share_prior": ps,
                "delta": (round(s["share_classified"] - ps, 1) if ps is not None else None),
            })
        dims.append({"key": d["key"], "title": d["title"], "cn": d["cn"],
                     "coverage": cur["coverage_pct"], "rows": ranked})
    return dims


# ---------------- assemble ----------------

def build_payload():
    brand_countries = ["Germany", "Spain", "Finland", "Netherlands", "Austria"]
    pt_countries = ["Germany", "Spain", "Finland", "Sweden"]
    model_countries = ["Germany", "Spain", "Finland", "Netherlands"]
    body_countries = ["Germany", "Netherlands", "Spain"]
    # The UK (DfT, quarterly) is included automatically once the source has the
    # current quarter — until then it has no Q2 data and would show as zeros.
    if uk_available():
        brand_countries.append("UnitedKingdom")
        pt_countries.append("UnitedKingdom")
        model_countries.append("UnitedKingdom")

    # cache brand maps
    bc_cur = {c: brand_counts(c, CUR) for c in brand_countries}
    bc_pri = {c: brand_counts(c, PRIOR) for c in brand_countries}

    # ---- overview (Q2 total + YoY) for every country we can total ----
    overview = []
    def _sum(m):
        return sum(m.values())
    for c in brand_countries:
        overview.append({"key": c, "label": LABEL[c], "flag": FLAG[c],
                         "cur": _sum(bc_cur[c]), "prior": _sum(bc_pri[c]),
                         "yoy": yoy(_sum(bc_cur[c]), _sum(bc_pri[c]))})
    # Sweden & France from their totals feeds
    def _total_feed(path, period):
        return sum(int(r["total"] or 0) for r in _rows(path) if _in(period, r["year"], r["month"]))
    for c, path in [("Sweden", DATA / "Sweden" / "scb_monthly_total.csv"),
                    ("France", DATA / "France" / "insee_monthly_total.csv")]:
        cur = _total_feed(path, CUR); pri = _total_feed(path, PRIOR)
        overview.append({"key": c, "label": LABEL[c], "flag": FLAG[c],
                         "cur": cur, "prior": pri, "yoy": yoy(cur, pri)})
    overview.sort(key=lambda x: -x["cur"])

    # ---- brands ----
    def pooled(maps):
        out = defaultdict(int)
        for m in maps.values():
            for k, v in m.items():
                out[k] += v
        return out
    brands = {"countries": brand_countries + ["Total"], "data": {}}
    for c in brand_countries:
        brands["data"][c] = top_series(bc_cur[c], bc_pri[c], 10)
    brands["data"]["Total"] = top_series(pooled(bc_cur), pooled(bc_pri), 10)

    # ---- origin ----
    def to_origin(bmap):
        o = defaultdict(int)
        for b, v in bmap.items():
            o[origin(b) or "Other"] += v
        return o
    origin_d = {"countries": brand_countries + ["Total"], "data": {}}
    for c in brand_countries:
        origin_d["data"][c] = top_series(to_origin(bc_cur[c]), to_origin(bc_pri[c]), 8)
    origin_d["data"]["Total"] = top_series(
        to_origin(pooled(bc_cur)), to_origin(pooled(bc_pri)), 8)

    # ---- models ----
    models = {"countries": model_countries + ["Total"], "data": {}}
    for c in model_countries:
        models["data"][c] = top_series(model_counts(c, CUR), model_counts(c, PRIOR), 10)
    models["data"]["Total"] = top_series(
        model_counts_pooled(CUR), model_counts_pooled(PRIOR), 10)

    # ---- powertrain ----
    pt_cur = {c: powertrain_counts(c, CUR) for c in pt_countries}
    pt_pri = {c: powertrain_counts(c, PRIOR) for c in pt_countries}
    powertrain = {"countries": pt_countries + ["Total"], "data": {}}
    for c in pt_countries:
        powertrain["data"][c] = powertrain_rows(pt_cur[c], pt_pri[c])
    powertrain["data"]["Total"] = powertrain_rows(
        pooled(pt_cur), pooled(pt_pri))

    # ---- body type (native taxonomy per country; no pooled Total) ----
    body = {"countries": body_countries, "data": {}}
    for c in body_countries:
        body["data"][c] = body_rows(body_counts(c, CUR), body_counts(c, PRIOR))

    # ---- suppliers ----
    specs = psg.load_specs()
    matcher = SupplierMatcher(specs.keys())
    sup_countries = model_countries
    sup_rows_cur = {c: supplier_model_rows(c, CUR) for c in sup_countries}
    sup_rows_pri = {c: supplier_model_rows(c, PRIOR) for c in sup_countries}
    suppliers = {"countries": sup_countries + ["Total"], "data": {}}
    for c in sup_countries:
        suppliers["data"][c] = supplier_dims(specs, matcher, sup_rows_cur[c], sup_rows_pri[c])
    pooled_cur = [r for c in sup_countries for r in sup_rows_cur[c]]
    pooled_pri = [r for c in sup_countries for r in sup_rows_pri[c]]
    suppliers["data"]["Total"] = supplier_dims(specs, matcher, pooled_cur, pooled_pri)

    return {
        "period": {"cur": "Q2 2026", "prior": "Q2 2025", "note": "Apr–Jun"},
        "flags": FLAG, "labels": LABEL,
        "overview": overview,
        "brands": brands, "models": models, "origin": origin_d,
        "powertrain": powertrain, "body": body, "suppliers": suppliers,
        "coverage_note": (
            "Brands & origin: DE, ES, FI, NL, AT · Powertrain: DE, ES, FI, SE · "
            "Models & suppliers: DE, ES, FI, NL (the monthly model feeds) · "
            "Body type: DE (KBA size-segments), NL (RDW body) & ES (EU body "
            "codes), each in its own native taxonomy — not pooled. The UK (DfT, "
            "quarterly) joins the brand/model/origin/powertrain/supplier "
            "dimensions automatically once it publishes the quarter; France is "
            "total-only; Italy not covered."
        ),
    }


def main() -> int:
    payload = build_payload()
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = PAGE.replace("__DATA__", blob)
    OUT_HTML.write_text(html, encoding="utf-8")
    ov = payload["overview"]
    print(f"[q2] wrote {OUT_HTML.relative_to(REPO_ROOT)}")
    for o in ov:
        arrow = "" if o["yoy"] is None else f'{o["yoy"]:+.1f}%'
        print(f"  {o['flag']} {o['label']:12} {o['cur']:>8,} regs  YoY {arrow}")
    return 0


# The page template lives in a sibling module to keep this file focused on data.
from q2_report_template import PAGE  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
