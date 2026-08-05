#!/usr/bin/env python3
"""Assemble a uniform multi-country "core" dataset for the site's country picker.

Reads each country's registration data and emits ``docs/data/countries.json`` —
a list of per-country cores with a comparable shape so the front-end can show,
for any selected subset of countries, a per-country historical trend and
aggregated brand / origin bars.

Because national sources differ in granularity and detail, the core is designed
around the common denominator:

- **quarters** — a full multi-year quarterly total series (the historical
  trend). Monthly sources (DE, NL, FI, FR) are aggregated to *complete* quarters;
  the UK source (DfT) is natively quarterly.
- **brand_totals / origin_totals** — registration-weighted, counted over a common
  recent window (from ``BRAND_WINDOW_START``) so cross-country brand shares are
  comparable. France is total-only (no open brand data) → ``has_brands=false``.

Brand names are canonicalised across registers (see ``eu_brands``).
Run after parse_germany.py + the per-country download_* scripts.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from eu_brands import ALIASES, BRAND_ORIGIN, canonical, origin

REPO_ROOT = Path(__file__).resolve().parent.parent
GERMANY_CSV = REPO_ROOT / "data" / "Germany" / "processed" / "germany_registrations.csv"
GERMANY_JSON = REPO_ROOT / "docs" / "data" / "germany.json"
NL_CSV = REPO_ROOT / "data" / "Netherlands" / "rdw_monthly_brands.csv"
NL_MODELS = REPO_ROOT / "data" / "Netherlands" / "rdw_models.csv"
FI_CSV = REPO_ROOT / "data" / "Finland" / "traficom_monthly_brands.csv"
FI_MODELS = REPO_ROOT / "data" / "Finland" / "traficom_models.csv"
FR_CSV = REPO_ROOT / "data" / "France" / "insee_monthly_total.csv"
UK_CSV = REPO_ROOT / "data" / "UnitedKingdom" / "uk_quarterly_brands.csv"
UK_MODELS = REPO_ROOT / "data" / "UnitedKingdom" / "uk_models.csv"
FI_PT = REPO_ROOT / "data" / "Finland" / "traficom_powertrain.csv"
UK_PT = REPO_ROOT / "data" / "UnitedKingdom" / "uk_powertrain.csv"
FR_PT = REPO_ROOT / "data" / "France" / "fr_powertrain_annual.csv"
ES_CSV = REPO_ROOT / "data" / "Spain" / "es_monthly_brands.csv"
ES_MODELS = REPO_ROOT / "data" / "Spain" / "es_monthly_models.csv"
ES_PT = REPO_ROOT / "data" / "Spain" / "es_monthly_powertrain.csv"
ES_BODY = REPO_ROOT / "data" / "Spain" / "es_monthly_body.csv"
NL_BODY = REPO_ROOT / "data" / "Netherlands" / "rdw_body_monthly.csv"
NL_MODELS_LATEST = REPO_ROOT / "data" / "Netherlands" / "rdw_models_latest.csv"
FI_MODELS_LATEST = REPO_ROOT / "data" / "Finland" / "traficom_models_latest.csv"
UK_MODELS_LATEST = REPO_ROOT / "data" / "UnitedKingdom" / "uk_models_latest.csv"
SE_CSV = REPO_ROOT / "data" / "Sweden" / "scb_monthly_total.csv"
SE_PT = REPO_ROOT / "data" / "Sweden" / "se_powertrain.csv"
AT_CSV = REPO_ROOT / "data" / "Austria" / "at_monthly_brands.csv"
PL_CSV = REPO_ROOT / "data" / "Poland" / "cepik_monthly_brands.csv"
PL_MODELS = REPO_ROOT / "data" / "Poland" / "cepik_models.csv"
OUT = REPO_ROOT / "docs" / "data" / "countries.json"

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
              "Oct", "Nov", "Dec"]

POWERTRAIN_ORDER = ["BEV", "PHEV", "Hybrid", "Petrol", "Diesel", "Other"]

# Raw brand names (incl. multi-word aliases) longest-first, for splitting a
# "BRAND MODEL" label and for stripping a brand prefix from a model string.
BRAND_PREFIXES = sorted(
    {b.upper() for b in list(ALIASES) + list(ALIASES.values())
     + list(BRAND_ORIGIN)}, key=len, reverse=True)


def _clean_model(brand_raw: str, model_raw: str) -> str:
    """Strip a leading brand token from a model string (e.g. FORD PUMA -> PUMA)."""
    m = model_raw.strip().upper()
    for pref in (brand_raw.strip().upper(), canonical(brand_raw)):
        if pref and m.startswith(pref + " "):
            return m[len(pref) + 1:].strip()
    return m


def _split_label(label: str) -> tuple[str, str]:
    """Split a 'BRAND MODEL' label into (canonical brand, model)."""
    lab = label.strip().upper()
    for pref in BRAND_PREFIXES:
        if lab == pref or lab.startswith(pref + " "):
            return canonical(pref), lab[len(pref):].strip()
    parts = lab.split(" ", 1)
    return canonical(parts[0]), (parts[1] if len(parts) > 1 else "")


def _top_models(triples, limit: int = 15) -> list[dict]:
    """triples: iterable of (canonical_brand, clean_model, total) -> ranked list."""
    agg: dict[tuple[str, str], int] = defaultdict(int)
    for cb, cm, t in triples:
        if cb == "OTHER" or not cm:
            continue
        agg[(cb, cm)] += t
    return [{"brand": b, "model": m, "total": t}
            for (b, m), t in sorted(agg.items(), key=lambda kv: -kv[1])[:limit]]


def powertrain_for(code: str) -> dict:
    """Canonical powertrain shares (or has=False). Period differs by source."""
    agg: dict[str, int] = defaultdict(int)
    period = _brand_window_label()
    if code == "FI" and FI_PT.exists():
        with FI_PT.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if (int(r["year"]), int(r["month"])) >= BRAND_WINDOW_START:
                    agg[r["fuel"]] += int(r["count"])
    elif code == "UK" and UK_PT.exists():
        with UK_PT.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if (int(r["year"]), int(r["quarter"])) >= (BRAND_WINDOW_START[0], _q(BRAND_WINDOW_START[1])):
                    agg[r["fuel"]] += int(r["count"])
    elif code == "ES" and ES_PT.exists():
        with ES_PT.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if (int(r["year"]), int(r["month"])) >= BRAND_WINDOW_START:
                    agg[r["fuel"]] += int(r["count"])
    elif code == "SE" and SE_PT.exists():
        with SE_PT.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if (int(r["year"]), int(r["month"])) >= BRAND_WINDOW_START:
                    agg[r["fuel"]] += int(r["count"])
    elif code == "FR" and FR_PT.exists():
        # France open data is annual only — use the latest available year.
        rows = list(csv.DictReader(FR_PT.open(encoding="utf-8")))
        if not rows:
            return {"has": False, "shares": []}
        latest = max(int(r["year"]) for r in rows)
        for r in rows:
            if int(r["year"]) == latest:
                agg[r["fuel"]] += int(r["count"])
        period = f"{latest} (annual)"
    else:
        return {"has": False, "shares": []}
    tot = sum(agg.values()) or 1
    order = POWERTRAIN_ORDER + [f for f in agg if f not in POWERTRAIN_ORDER]
    shares = [{"fuel": f, "total": agg[f], "pct": round(100 * agg[f] / tot, 1)}
              for f in order if agg.get(f)]
    return {"has": True, "shares": shares, "period": period}


BODY_ORDER = ["Hatchback", "Estate", "Sedan", "MPV & SUV", "MPV", "SUV",
              "Coupé", "Convertible", "Sedan & hatch", "MPV & van", "Sports", "Other"]
_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def body_for(code: str) -> dict:
    """Body-type shares over the comparable window, where openly published.

    Spain (EU body codes) and the Netherlands (RDW body codes) publish it;
    neither has a distinct SUV bucket. Germany keeps its own KBA size-segment
    chart, so it is not duplicated here.
    """
    src = {"ES": ES_BODY, "NL": NL_BODY}.get(code)
    if not src or not src.exists():
        return {"has": False, "shares": []}
    agg: dict[str, int] = defaultdict(int)
    months: set = set()
    with src.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ym = (int(r["year"]), int(r["month"]))
            if ym >= BRAND_WINDOW_START:
                agg[r["body"]] += int(r["count"])
                months.add(ym)
    if not agg:
        return {"has": False, "shares": []}
    tot = sum(agg.values()) or 1
    order = [b for b in BODY_ORDER if b in agg] + [b for b in agg if b not in BODY_ORDER]
    shares = [{"body": b, "total": agg[b], "pct": round(100 * agg[b] / tot, 1)}
              for b in order if agg.get(b)]
    lo, hi = min(months), max(months)
    period = (f"{_MONTH_ABBR[lo[1] - 1]} {lo[0]} – {_MONTH_ABBR[hi[1] - 1]} {hi[0]}"
              if lo != hi else f"{_MONTH_ABBR[lo[1] - 1]} {lo[0]}")
    return {"has": True, "shares": shares, "period": period}


ORIGIN_ORDER = ["Germany", "Japan", "France", "South Korea", "USA", "Czechia",
                "Spain", "Sweden", "China", "Italy", "United Kingdom", "Other"]


def _complete_quarters_from_months(months: set) -> list:
    q_months: dict[tuple[int, int], set] = defaultdict(set)
    for (y, m) in months:
        q_months[(y, _q(m))].add(m)
    return sorted(q for q, ms in q_months.items() if len(ms) == 3)


def _brand_qrows(code):
    """Return (rows[(y,q,brand_raw,count)], complete_quarters) for a country."""
    monthly = {"NL": NL_CSV, "FI": FI_CSV, "ES": ES_CSV, "AT": AT_CSV, "PL": PL_CSV}
    if code in monthly and monthly[code].exists():
        rows_m = []
        months = set()
        with monthly[code].open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                y, m = int(r["year"]), int(r["month"])
                months.add((y, m))
                rows_m.append((y, _q(m), r["brand"].strip(), int(r["count"])))
        cq = set(_complete_quarters_from_months(months))
        return [r for r in rows_m if (r[0], r[1]) in cq], sorted(cq)
    if code == "UK" and UK_CSV.exists():
        rows, qs = [], set()
        with UK_CSV.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                y, q = int(r["year"]), int(r["quarter"])
                qs.add((y, q))
                rows.append((y, q, r["brand"].strip(), int(r["count"])))
        return rows, sorted(qs)
    return [], []


def _fuel_qrows(code):
    monthly = {"FI": FI_PT, "ES": ES_PT, "SE": SE_PT}
    if code in monthly and monthly[code].exists():
        rows_m, months = [], set()
        with monthly[code].open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                y, m = int(r["year"]), int(r["month"])
                months.add((y, m))
                rows_m.append((y, _q(m), r["fuel"].strip(), int(r["count"])))
        cq = set(_complete_quarters_from_months(months))
        return [r for r in rows_m if (r[0], r[1]) in cq], sorted(cq)
    if code == "UK" and UK_PT.exists():
        rows, qs = [], set()
        with UK_PT.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                y, q = int(r["year"]), int(r["quarter"])
                qs.add((y, q))
                rows.append((y, q, r["fuel"].strip(), int(r["count"])))
        return rows, sorted(qs)
    return [], []


def _trend_series(rows, quarters, keyfn, order=None, top_n=None):
    """rows: (y,q,rawkey,count). -> {labels, series:[{name, values}]}."""
    if not quarters:
        return None
    qidx = {q: i for i, q in enumerate(quarters)}
    n = len(quarters)
    by_key: dict[str, list[int]] = defaultdict(lambda: [0] * n)
    totals: dict[str, int] = defaultdict(int)
    for y, q, raw, c in rows:
        if (y, q) not in qidx:
            continue
        k = keyfn(raw)
        by_key[k][qidx[(y, q)]] += c
        totals[k] += c
    if top_n:
        keep = [k for k, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:top_n]]
        other = [0] * n
        for k, arr in by_key.items():
            if k not in keep:
                for i in range(n):
                    other[i] += arr[i]
        series = [{"name": k, "values": by_key[k]} for k in keep]
        if any(other):
            series.append({"name": "Other", "values": other})
    else:
        names = order if order else sorted(totals, key=lambda k: -totals[k])
        names = [k for k in names if k in by_key]
        if order:  # append any present-but-unordered keys
            names += [k for k in by_key if k not in names]
        series = [{"name": k, "values": by_key[k]} for k in names if any(by_key[k])]
    labels = [f"Q{q} {y}" for (y, q) in quarters]
    return {"labels": labels, "series": series}


def trends_for(core: dict) -> None:
    code = core["code"]
    if code == "DE":
        return
    if core.get("has_brands"):
        bq, cq = _brand_qrows(code)
        if bq:
            core["brand_trends"] = _trend_series(bq, cq, canonical, top_n=6)
            core["origin_trends"] = _trend_series(bq, cq, origin, top_n=7)
    # Powertrain trend is available even for total-only countries (e.g. Sweden),
    # whose whole value-add is a monthly fuel split.
    fq, fcq = _fuel_qrows(code)
    if fq:
        core["powertrain_trends"] = _trend_series(fq, fcq, lambda f: f, order=POWERTRAIN_ORDER)


def models_for(code: str) -> list[dict]:
    if code == "NL" and NL_MODELS.exists():
        with NL_MODELS.open(encoding="utf-8") as fh:
            return _top_models((canonical(r["brand"]), _clean_model(r["brand"], r["model"]),
                                int(r["total"])) for r in csv.DictReader(fh))
    if code == "UK" and UK_MODELS.exists():
        with UK_MODELS.open(encoding="utf-8") as fh:
            return _top_models((canonical(r["brand"]), _clean_model(r["brand"], r["model"]),
                                int(r["total"])) for r in csv.DictReader(fh))
    if code == "FI" and FI_MODELS.exists():
        with FI_MODELS.open(encoding="utf-8") as fh:
            out = []
            for r in csv.DictReader(fh):
                cb, cm = _split_label(r["model_label"])
                out.append((cb, cm, int(r["total"])))
            return _top_models(out)
    if code == "ES" and ES_MODELS.exists():
        with ES_MODELS.open(encoding="utf-8") as fh:
            return _top_models(
                (canonical(r["brand"]), _clean_model(r["brand"], r["model"]), int(r["count"]))
                for r in csv.DictReader(fh)
                if (int(r["year"]), int(r["month"])) >= BRAND_WINDOW_START)
    if code == "PL" and PL_MODELS.exists():
        with PL_MODELS.open(encoding="utf-8") as fh:
            return _top_models((canonical(r["brand"]), _clean_model(r["brand"], r["model"]),
                                int(r["total"])) for r in csv.DictReader(fh))
    if code == "DE":
        triples = []
        with GERMANY_CSV.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["row_type"] != "model" or r["drivetrain"] != "total" or not r["count_month"]:
                    continue
                if (int(r["year"]), int(r["month"])) < BRAND_WINDOW_START:
                    continue
                triples.append((canonical(r["brand"]), r["model"].strip().upper(), int(r["count_month"])))
        return _top_models(triples)
    return []

# Count brands/origins only from this month onward, so every brand-capable
# country contributes the same window and the shares stay comparable.
BRAND_WINDOW_START = (2023, 9)


def _q(month: int) -> int:
    return (month - 1) // 3 + 1


def _in_brand_window_month(y: int, m: int) -> bool:
    return (y, m) >= BRAND_WINDOW_START


def _in_brand_window_quarter(y: int, q: int) -> bool:
    return (y, q) >= (BRAND_WINDOW_START[0], _q(BRAND_WINDOW_START[1]))


def _brand_window_label(start=BRAND_WINDOW_START) -> str:
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"since {names[start[1] - 1]} {start[0]}"


def _assemble(code, name, flag, source, source_url, *,
              quarter_total: dict[tuple[int, int], int],
              quarter_complete: dict[tuple[int, int], bool],
              brand_window: dict[str, int] | None) -> dict:
    qs = sorted(q for q, ok in quarter_complete.items() if ok and quarter_total.get(q))
    quarters = [{"q": f"{y}-Q{q}", "label": f"Q{q} {y}", "total": quarter_total[(y, q)]}
                for (y, q) in qs]
    has_brands = brand_window is not None
    brand_totals, origin_totals = [], []
    if has_brands:
        origins: dict[str, int] = defaultdict(int)
        for b, t in brand_window.items():
            origins[origin(b)] += t
        brand_totals = [{"brand": canonical(b), "total": t}
                        for b, t in sorted(brand_window.items(), key=lambda kv: -kv[1])
                        if canonical(b) != "OTHER"]
        origin_totals = [{"origin": o, "total": t}
                         for o, t in sorted(origins.items(), key=lambda kv: -kv[1])]
    return {
        "code": code, "name": name, "flag": flag,
        "source": source, "source_url": source_url,
        "granularity": "quarterly",
        "has_brands": has_brands,
        "brand_window_label": _brand_window_label() if has_brands else "",
        "window": f"{quarters[0]['label']} – {quarters[-1]['label']}" if quarters else "",
        "quarters": quarters,
        "total": sum(quarter_total[(y, q)] for (y, q) in qs),
        "brand_totals": brand_totals,
        "origin_totals": origin_totals,
    }


def _from_monthly(rows, code, name, flag, source, source_url, with_brands: bool) -> dict:
    """rows: iterable of (year, month, brand|None, count)."""
    q_total: dict[tuple[int, int], int] = defaultdict(int)
    q_months: dict[tuple[int, int], set] = defaultdict(set)
    brand_window: dict[str, int] = defaultdict(int)
    for y, m, brand, cnt in rows:
        q = (y, _q(m))
        q_total[q] += cnt
        q_months[q].add(m)
        if with_brands and brand and _in_brand_window_month(y, m):
            brand_window[canonical(brand)] += cnt
    q_complete = {q: len(q_months[q]) == 3 for q in q_total}
    return _assemble(code, name, flag, source, source_url,
                     quarter_total=q_total, quarter_complete=q_complete,
                     brand_window=(brand_window if with_brands else None))


def germany_core() -> dict:
    site = json.loads(GERMANY_JSON.read_text(encoding="utf-8"))
    monthly_total = {(mo["year"], mo["month"]): mo["total"]
                     for mo in site.get("months", []) if mo.get("total")}
    rows = []
    for (y, m), tot in monthly_total.items():
        rows.append((y, m, None, tot))  # total drives the quarterly series
    # brand detail from the tidy CSV (monthly brand_total rows)
    brand_rows = []
    with GERMANY_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["row_type"] != "brand_total" or r["drivetrain"] != "total" or not r["count_month"]:
                continue
            key = (int(r["year"]), int(r["month"]))
            if key not in monthly_total:
                continue
            brand_rows.append((key[0], key[1], r["brand"].strip(), int(r["count_month"])))
    # Build quarters from totals, brand window from brand rows.
    core = _from_monthly(rows, "DE", "Germany", "🇩🇪",
                         "Kraftfahrt-Bundesamt (KBA), table FZ 10.1",
                         "https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html",
                         with_brands=False)
    bw: dict[str, int] = defaultdict(int)
    for y, m, b, c in brand_rows:
        if _in_brand_window_month(y, m):
            bw[canonical(b)] += c
    # attach brands
    origins: dict[str, int] = defaultdict(int)
    for b, t in bw.items():
        origins[origin(b)] += t
    core["has_brands"] = True
    core["brand_window_label"] = _brand_window_label()
    core["brand_totals"] = [{"brand": b, "total": t} for b, t in sorted(bw.items(), key=lambda kv: -kv[1]) if b != "OTHER"]
    core["origin_totals"] = [{"origin": o, "total": t} for o, t in sorted(origins.items(), key=lambda kv: -kv[1])]
    return core


def csv_monthly_brands(path, code, name, flag, source, source_url) -> dict | None:
    if not path.exists():
        return None
    rows = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((int(r["year"]), int(r["month"]), r["brand"].strip(), int(r["count"])))
    return _from_monthly(rows, code, name, flag, source, source_url, with_brands=True)


def france_core() -> dict | None:
    if not FR_CSV.exists():
        return None
    rows = []
    with FR_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((int(r["year"]), int(r["month"]), None, int(r["total"])))
    return _from_monthly(rows, "FR", "France", "🇫🇷",
                         "INSEE / SDES (BDM series 010756763, national totals)",
                         "https://www.insee.fr/fr/statistiques/serie/010756763",
                         with_brands=False)


def sweden_core() -> dict | None:
    if not SE_CSV.exists():
        return None
    rows = []
    with SE_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((int(r["year"]), int(r["month"]), None, int(r["total"])))
    return _from_monthly(rows, "SE", "Sweden", "🇸🇪",
                         "Statistics Sweden (SCB) / Trafikanalys (PxWeb open data)",
                         "https://www.statistikdatabasen.scb.se/",
                         with_brands=False)


def uk_core() -> dict | None:
    if not UK_CSV.exists():
        return None
    q_total: dict[tuple[int, int], int] = defaultdict(int)
    brand_window: dict[str, int] = defaultdict(int)
    with UK_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            y, q, b, c = int(r["year"]), int(r["quarter"]), r["brand"].strip(), int(r["count"])
            q_total[(y, q)] += c
            if _in_brand_window_quarter(y, q):
                brand_window[canonical(b)] += c
    q_complete = {q: True for q in q_total}  # DfT publishes complete quarters only
    return _assemble("UK", "United Kingdom", "🇬🇧",
                     "UK Dept. for Transport, table VEH0160 (quarterly)",
                     "https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files",
                     quarter_total=q_total, quarter_complete=q_complete, brand_window=brand_window)


def _top_brands(pairs, limit: int = 12) -> list[dict]:
    """pairs: iterable of (brand_raw, count) -> ranked canonical brand list."""
    agg: dict[str, int] = defaultdict(int)
    for b, c in pairs:
        cb = canonical(b)
        if cb == "OTHER":
            continue
        agg[cb] += c
    return [{"brand": b, "total": t}
            for b, t in sorted(agg.items(), key=lambda kv: -kv[1])[:limit]]


def _latest_models(code: str, y: int, p: int) -> list[dict]:
    """Top models for the latest period (month for NL/FI/ES, quarter for UK)."""
    if code == "NL" and NL_MODELS_LATEST.exists():
        with NL_MODELS_LATEST.open(encoding="utf-8") as fh:
            return _top_models((canonical(r["brand"]), _clean_model(r["brand"], r["model"]),
                                int(r["count"])) for r in csv.DictReader(fh))
    if code == "UK" and UK_MODELS_LATEST.exists():
        with UK_MODELS_LATEST.open(encoding="utf-8") as fh:
            return _top_models((canonical(r["brand"]), _clean_model(r["brand"], r["model"]),
                                int(r["count"])) for r in csv.DictReader(fh))
    if code == "FI" and FI_MODELS_LATEST.exists():
        out = []
        with FI_MODELS_LATEST.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                cb, cm = _split_label(r["model_label"])
                out.append((cb, cm, int(r["count"])))
        return _top_models(out)
    if code == "ES" and ES_MODELS.exists():
        with ES_MODELS.open(encoding="utf-8") as fh:
            return _top_models(
                (canonical(r["brand"]), _clean_model(r["brand"], r["model"]), int(r["count"]))
                for r in csv.DictReader(fh)
                if (int(r["year"]), int(r["month"])) == (y, p))
    if code == "PL" and PL_MODELS.exists():
        # Poland's model file is a recent-window cumulative total, not per-month.
        with PL_MODELS.open(encoding="utf-8") as fh:
            return _top_models((canonical(r["brand"]), _clean_model(r["brand"], r["model"]),
                                int(r["total"])) for r in csv.DictReader(fh))
    return []


def _latest_powertrain(code: str, kind: str, y: int, p: int) -> dict:
    """Powertrain shares for one period (month or quarter). has=False if absent."""
    agg: dict[str, int] = defaultdict(int)
    if kind == "month" and code == "FI" and FI_PT.exists():
        src, key = FI_PT, "month"
    elif kind == "month" and code == "ES" and ES_PT.exists():
        src, key = ES_PT, "month"
    elif kind == "month" and code == "SE" and SE_PT.exists():
        src, key = SE_PT, "month"
    elif kind == "quarter" and code == "UK" and UK_PT.exists():
        src, key = UK_PT, "quarter"
    else:
        return {"has": False, "shares": []}
    with src.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (int(r["year"]), int(r[key])) == (y, p):
                agg[r["fuel"]] += int(r["count"])
    tot = sum(agg.values())
    if not tot:
        return {"has": False, "shares": []}
    order = POWERTRAIN_ORDER + [f for f in agg if f not in POWERTRAIN_ORDER]
    shares = [{"fuel": f, "total": agg[f], "pct": round(100 * agg[f] / tot, 1)}
              for f in order if agg.get(f)]
    return {"has": True, "shares": shares}


def latest_for(code: str) -> dict | None:
    """Most-recent single-period snapshot (month for NL/FI/ES, quarter for UK).

    Mirrors Germany's card, which leads with the latest month's top brands /
    models / powertrain before the historical trends. France is total-only and
    has no brand/model detail, so it is skipped.
    """
    monthly = {"NL": NL_CSV, "FI": FI_CSV, "ES": ES_CSV, "AT": AT_CSV, "PL": PL_CSV}
    if code in monthly and monthly[code].exists():
        rows = list(csv.DictReader(monthly[code].open(encoding="utf-8")))
        if not rows:
            return None
        y, m = max((int(r["year"]), int(r["month"])) for r in rows)
        brands = [(r["brand"].strip(), int(r["count"])) for r in rows
                  if (int(r["year"]), int(r["month"])) == (y, m)]
        return {
            "period": f"{MONTH_ABBR[m - 1]} {y}",
            "total": sum(c for _, c in brands),
            "top_brands": _top_brands(brands),
            "top_models": _latest_models(code, y, m),
            "powertrain": _latest_powertrain(code, "month", y, m),
        }
    if code == "UK" and UK_CSV.exists():
        rows = list(csv.DictReader(UK_CSV.open(encoding="utf-8")))
        if not rows:
            return None
        y, q = max((int(r["year"]), int(r["quarter"])) for r in rows)
        brands = [(r["brand"].strip(), int(r["count"])) for r in rows
                  if (int(r["year"]), int(r["quarter"])) == (y, q)]
        return {
            "period": f"Q{q} {y}",
            "total": sum(c for _, c in brands),
            "top_brands": _top_brands(brands),
            "top_models": _latest_models("UK", y, q),
            "powertrain": _latest_powertrain("UK", "quarter", y, q),
        }
    return None


def main() -> int:
    countries = [germany_core()]
    for core in (
        csv_monthly_brands(NL_CSV, "NL", "Netherlands", "🇳🇱",
                           "RDW open data (Socrata dataset m9d7-ebf2)", "https://opendata.rdw.nl/"),
        csv_monthly_brands(FI_CSV, "FI", "Finland", "🇫🇮",
                           "Traficom / Statistics Finland (PxWeb open data)",
                           "https://trafi2.stat.fi/PXWeb/pxweb/en/TraFi/"),
        csv_monthly_brands(ES_CSV, "ES", "Spain", "🇪🇸",
                           "DGT microdatos de matriculaciones (mensual)",
                           "https://www.dgt.es/menusecundario/dgt-en-cifras/"),
        csv_monthly_brands(AT_CSV, "AT", "Austria", "🇦🇹",
                           "Statistik Austria — Kfz-Neuzulassungen (OGD)",
                           "https://data.statistik.gv.at/web/catalog.jsp"),
        csv_monthly_brands(PL_CSV, "PL", "Poland", "🇵🇱",
                           "CEPIK — central vehicle register (open API)",
                           "https://api.cepik.gov.pl/"),
        france_core(),
        sweden_core(),
        uk_core(),
    ):
        if core:
            countries.append(core)
    for core in countries:
        core["top_models"] = models_for(core["code"]) if core["has_brands"] else []
        core["powertrain"] = powertrain_for(core["code"])
        core["body"] = body_for(core["code"])
        if core["code"] != "DE" and core["has_brands"]:
            snap = latest_for(core["code"])
            if snap:
                core["latest"] = snap
        trends_for(core)
        # calendar year-to-date (latest year in the quarterly series)
        if core["quarters"]:
            latest_year = int(core["quarters"][-1]["q"][:4])
            core["ytd"] = sum(q["total"] for q in core["quarters"]
                              if int(q["q"][:4]) == latest_year)
            core["ytd_year"] = latest_year
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(countries, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = ", ".join(
        f"{c['code']}({len(c['quarters'])}q {c['window']}, {c['total']:,}"
        f"{'' if c['has_brands'] else ', total-only'})" for c in countries)
    print(f"[countries] wrote {OUT.relative_to(REPO_ROOT)}:\n  " + summary.replace(", ", ",\n  "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
