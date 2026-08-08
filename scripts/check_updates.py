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


def snapshot() -> dict:
    return {c: _latest(REPO_ROOT / rel, kind)
            for c, (_flag, rel, kind) in SOURCES.items()}


def _emit_output(updated: bool, count: int, summary: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"updated={'true' if updated else 'false'}\n")
        fh.write(f"count={count}\n")
        fh.write("summary<<__SUMMARY_EOF__\n")
        fh.write(summary + ("\n" if summary else ""))
        fh.write("__SUMMARY_EOF__\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", metavar="FILE", help="snapshot latest periods to FILE")
    ap.add_argument("--compare", metavar="FILE", help="compare current periods to FILE")
    args = ap.parse_args()

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
