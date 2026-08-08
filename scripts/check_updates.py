#!/usr/bin/env python3
"""Detect per-country data updates for the daily watch workflow.

Each country's committed data carries a latest period — a month (most) or a
quarter (UK). This script snapshots those latest periods before the daily
downloads (``--write``) and, after the downloads + parsing have refreshed the
CSVs, compares the new latest periods against that snapshot (``--compare``).

A country counts as "updated" only when its latest period *advances* (a genuinely
new month/quarter is published) — not when an existing period is merely revised.
That keeps the email notification to real new data.

``--compare`` writes ``updated`` / ``count`` / ``summary`` to ``$GITHUB_OUTPUT``
so the workflow can decide whether to email. Exit code is always 0.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# country -> (flag, csv path relative to repo, period kind). The CSV must carry
# ``year`` plus ``month`` (kind="month") or ``quarter`` (kind="quarter").
SOURCES = {
    "Germany":       ("🇩🇪", "data/Germany/processed/germany_registrations.csv", "month"),
    "Netherlands":   ("🇳🇱", "data/Netherlands/rdw_monthly_brands.csv", "month"),
    "Finland":       ("🇫🇮", "data/Finland/traficom_monthly_brands.csv", "month"),
    "Spain":         ("🇪🇸", "data/Spain/es_monthly_brands.csv", "month"),
    "Sweden":        ("🇸🇪", "data/Sweden/scb_monthly_total.csv", "month"),
    "Austria":       ("🇦🇹", "data/Austria/at_monthly_brands.csv", "month"),
    "France":        ("🇫🇷", "data/France/insee_monthly_total.csv", "month"),
    "UnitedKingdom": ("🇬🇧", "data/UnitedKingdom/uk_quarterly_brands.csv", "quarter"),
    "Euro area":     ("🇪🇺", "data/Europe/ecb_ea_total.csv", "month"),
    "ACEA (all Europe)": ("🇪🇺", "data/Europe/acea_market.csv", "month"),
}


def _latest(path: Path, kind: str):
    """Return the latest [year, n] period in a CSV, or None."""
    if not path.exists():
        return None
    col = "month" if kind == "month" else "quarter"
    best = None
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                yn = [int(r["year"]), int(r[col])]
            except (KeyError, ValueError, TypeError):
                continue
            if best is None or yn > best:
                best = yn
    return best


def _label(kind: str, yn) -> str:
    if not yn:
        return "none"
    return f"{yn[0]}-{yn[1]:02d}" if kind == "month" else f"{yn[0]} Q{yn[1]}"


def _period_totals(country: str) -> dict:
    """{(year, n): registered cars} for one country over its whole series."""
    _flag, rel, kind = SOURCES[country]
    path = REPO_ROOT / rel
    agg: dict = {}
    if not path.exists():
        return agg
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                key = (int(r["year"]), int(r["month" if kind == "month" else "quarter"]))
            except (KeyError, ValueError, TypeError):
                continue
            if country == "Germany":
                # only the per-model "total" rows carry the monthly count
                if r.get("row_type") != "model" or r.get("drivetrain") != "total" or not r.get("model"):
                    continue
                cnt = int(r.get("count_month") or 0)
            elif "total" in r:      # scb / insee national-total feeds
                cnt = int(r.get("total") or 0)
            else:                    # brand feeds
                cnt = int(r.get("count") or 0)
            agg[key] = agg.get(key, 0) + cnt
    return agg


def report_rows() -> list[dict]:
    """Per-country coverage + latest-period cars + cumulative total."""
    rows = []
    for c, (flag, _rel, kind) in SOURCES.items():
        totals = _period_totals(c)
        if not totals:
            continue
        periods = sorted(totals)
        lo, hi = periods[0], periods[-1]
        rows.append({
            "flag": flag, "country": c, "kind": kind,
            "coverage": f"{_label(kind, list(lo))} → {_label(kind, list(hi))}",
            "latest": _label(kind, list(hi)),
            "latest_cars": totals[hi],
            "cumulative": sum(totals.values()),
        })
    return rows


def report_html(note: str = "") -> str:
    rows = report_rows()
    head = (f'<p style="font:14px system-ui,sans-serif;color:#333">{note.replace(chr(10), "<br>")}</p>'
            if note else "")
    trs = "".join(
        f'<tr>'
        f'<td style="padding:6px 12px">{r["flag"]} {r["country"]}</td>'
        f'<td style="padding:6px 12px;color:#555">{r["coverage"]}</td>'
        f'<td style="padding:6px 12px;font-weight:600">{r["latest"]}</td>'
        f'<td style="padding:6px 12px;text-align:right;font-variant-numeric:tabular-nums">{r["latest_cars"]:,}</td>'
        f'<td style="padding:6px 12px;text-align:right;color:#555;font-variant-numeric:tabular-nums">{r["cumulative"]:,}</td>'
        f'</tr>'
        for r in rows
    )
    return (
        head +
        '<table style="border-collapse:collapse;font:13px system-ui,sans-serif">'
        '<thead><tr style="text-align:left;border-bottom:2px solid #ddd">'
        '<th style="padding:6px 12px">Country</th>'
        '<th style="padding:6px 12px">Coverage</th>'
        '<th style="padding:6px 12px">Latest</th>'
        '<th style="padding:6px 12px;text-align:right">Cars (latest)</th>'
        '<th style="padding:6px 12px;text-align:right">Cumulative</th>'
        '</tr></thead><tbody>' + trs + '</tbody></table>'
    )


def report_text(note: str = "") -> str:
    lines = [note] if note else []
    for r in report_rows():
        lines.append(f'{r["flag"]} {r["country"]}: latest {r["latest"]} = '
                     f'{r["latest_cars"]:,} cars · coverage {r["coverage"]} · '
                     f'cumulative {r["cumulative"]:,}')
    return "\n".join(lines)


def snapshot() -> dict:
    return {c: _latest(REPO_ROOT / rel, kind)
            for c, (_flag, rel, kind) in SOURCES.items()}


def _gh_multiline(fh, name: str, value: str) -> None:
    fh.write(f"{name}<<__{name.upper()}_EOF__\n{value}\n__{name.upper()}_EOF__\n")


def _emit_output(updated: bool, count: int, summary: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    # Bake the shared report so the daily email reuses the same template.
    note = ("New registration data was published for:\n" + summary) if updated else ""
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"updated={'true' if updated else 'false'}\n")
        fh.write(f"count={count}\n")
        _gh_multiline(fh, "summary", summary)
        _gh_multiline(fh, "report_html", report_html(note))
        _gh_multiline(fh, "report_text", report_text(note))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", metavar="FILE", help="snapshot latest periods to FILE")
    ap.add_argument("--compare", metavar="FILE", help="compare current periods to FILE")
    ap.add_argument("--report", action="store_true",
                    help="emit the per-country coverage/totals table (report_html/report_text)")
    ap.add_argument("--note", default="", help="optional note line prepended to a report")
    args = ap.parse_args()

    if args.report:
        html = report_html(args.note)
        text = report_text(args.note)
        print(text)
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                _gh_multiline(fh, "report_html", html)
                _gh_multiline(fh, "report_text", text)
        return 0

    if args.write:
        Path(args.write).write_text(json.dumps(snapshot()), encoding="utf-8")
        print(f"[check-updates] wrote snapshot to {args.write}")
        return 0

    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        after = snapshot()
        lines = []
        for c, (flag, _rel, kind) in SOURCES.items():
            b = before.get(c)
            a = after.get(c)
            if a and (b is None or a > b):
                lines.append(f"{flag} {c}: {_label(kind, b)} → {_label(kind, a)}")
        summary = "\n".join(lines)
        updated = bool(lines)
        if updated:
            print(f"[check-updates] {len(lines)} country update(s):")
            for ln in lines:
                print("  " + ln)
        else:
            print("[check-updates] no new periods.")
        _emit_output(updated, len(lines), summary)
        return 0

    # No mode: just print the current snapshot for a human.
    for c, (flag, _rel, kind) in SOURCES.items():
        print(f"{flag} {c}: {_label(kind, snapshot()[c])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
