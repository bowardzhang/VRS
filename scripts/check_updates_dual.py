#!/usr/bin/env python3
"""Daily update detector with independent UK monthly + quarterly periods.

Wraps check_updates.py so existing country reporting stays unchanged while the
UK fast monthly feed and official quarterly feed can each trigger a notification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import check_updates as base

UK_MONTHLY = Path(__file__).resolve().parent.parent / "data/UnitedKingdom/uk_monthly_total.csv"
UK_MONTHLY_KEY = "UnitedKingdomMonthly"


def snapshot() -> dict:
    out = base.snapshot()
    out[UK_MONTHLY_KEY] = base._latest(UK_MONTHLY, "month")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", metavar="FILE")
    ap.add_argument("--compare", metavar="FILE")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.report:
        html, text = base.report_html(args.note), base.report_text(args.note)
        print(text)
        return 0

    if args.write:
        Path(args.write).write_text(json.dumps(snapshot()), encoding="utf-8")
        print(f"[check-updates] wrote dual-source snapshot to {args.write}")
        return 0

    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        after = snapshot()
        lines = []
        # Existing countries, including UK quarterly VEH0160.
        for c, (flag, _rel, kind) in base.SOURCES.items():
            b, a = before.get(c), after.get(c)
            if a and (b is None or a > b):
                label = "United Kingdom (quarterly official)" if c == "UnitedKingdom" else c
                lines.append(f"{flag} {label}: {base._label(kind, b)} → {base._label(kind, a)}")
        # UK monthly provisional VEH9902 is a separate update channel.
        b, a = before.get(UK_MONTHLY_KEY), after.get(UK_MONTHLY_KEY)
        if a and (b is None or a > b):
            lines.append(f"🇬🇧 United Kingdom (monthly provisional): {base._label('month', b)} → {base._label('month', a)}")

        summary = "\n".join(lines)
        updated = bool(lines)
        if updated:
            print(f"[check-updates] {len(lines)} feed update(s):")
            for line in lines:
                print("  " + line)
        else:
            print("[check-updates] no new periods.")
        base._emit_output(updated, len(lines), summary)
        return 0

    snap = snapshot()
    for c, (flag, _rel, kind) in base.SOURCES.items():
        print(f"{flag} {c}: {base._label(kind, snap[c])}")
    print(f"🇬🇧 UnitedKingdom monthly provisional: {base._label('month', snap[UK_MONTHLY_KEY])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
