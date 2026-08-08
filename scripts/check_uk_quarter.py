#!/usr/bin/env python3
"""Detect when the UK DfT source publishes a new quarter (e.g. 2026 Q2).

Downloads the DfT VEH0160 CSV (same source as ``download_uk.py``), finds the
latest quarter it exposes, and compares it with the latest quarter already
committed to ``data/UnitedKingdom/uk_quarterly_brands.csv``. If the source is
ahead, a new quarter has been published.

Used by the daily ``uk-q2-watch`` GitHub Action to decide whether to ingest the
new data and send an email. Writes ``new_quarter``/``quarter``/``latest_committed``
to ``$GITHUB_OUTPUT`` (when set) and prints a human-readable summary. Exit code
is always 0 — "no new quarter" is a normal outcome, not a failure.
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import download_uk as uk  # reuse fetch(), SRC, _COL

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMITTED = REPO_ROOT / "data" / "UnitedKingdom" / "uk_quarterly_brands.csv"


def _source_latest() -> tuple[int, int] | None:
    text = uk.fetch()
    header = next(csv.reader([text.splitlines()[0]]))
    quarters = []
    for h in header:
        m = uk._COL.match(h.strip())
        if m:
            quarters.append((int(m.group(1)), int(m.group(2))))
    return max(quarters) if quarters else None


def _committed_latest() -> tuple[int, int] | None:
    if not COMMITTED.exists():
        return None
    qs = []
    with COMMITTED.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            qs.append((int(r["year"]), int(r["quarter"])))
    return max(qs) if qs else None


def _emit(new_quarter: bool, quarter: str, committed: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"new_quarter={'true' if new_quarter else 'false'}\n")
            fh.write(f"quarter={quarter}\n")
            fh.write(f"latest_committed={committed}\n")


def main() -> int:
    src = _source_latest()
    committed = _committed_latest()
    src_s = f"{src[0]} Q{src[1]}" if src else "none"
    com_s = f"{committed[0]} Q{committed[1]}" if committed else "none"
    if src is None:
        print("[uk-watch] could not read source; treating as no change")
        _emit(False, "", com_s)
        return 0
    new = committed is None or src > committed
    print(f"[uk-watch] source latest = {src_s} · committed latest = {com_s} · "
          f"new quarter = {new}")
    _emit(new, src_s, com_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
