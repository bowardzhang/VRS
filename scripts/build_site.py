#!/usr/bin/env python3
"""Bake parsed data into the static pages.

Injects ``docs/data/germany.json`` into the ``<script id="germany-data">``
placeholder, and ``docs/data/brand_logos.json`` into the optional
``<script id="brand-logos">`` placeholder, of every page listed in ``PAGES`` so
each page is fully self-contained (works over GitHub Pages, a local file, or any
host, with no fetch / CORS dependency).

Run ``scripts/parse_germany.py`` (and ``parse_segments.py``) first to (re)generate
the JSON, then this.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
JSON_PATH = DOCS / "data" / "germany.json"
LOGOS_PATH = DOCS / "data" / "brand_logos.json"
COUNTRIES_PATH = DOCS / "data" / "countries.json"
SUPPLIERS_GEO_PATH = DOCS / "data" / "suppliers_geo.json"
EUROPE_PATH = DOCS / "data" / "europe.json"

# Pages to bake into. The main page must exist; secondary pages are optional.
PAGES = ["index.html", "analysis-china.html", "analysis-ev.html",
         "analysis-soc.html", "analysis-adas.html", "analysis-radar.html",
         "analysis-power.html", "analysis-lidar.html"]

BLOCKS = {
    "germany-data": JSON_PATH,
    "brand-logos": LOGOS_PATH,
    "countries-data": COUNTRIES_PATH,
    "suppliers-geo": SUPPLIERS_GEO_PATH,
    "europe-data": EUROPE_PATH,
}


def _placeholder_re(block_id: str) -> re.Pattern:
    return re.compile(
        r'(<script id="' + re.escape(block_id) + r'" type="application/json">)'
        r"(.*?)(</script>)",
        re.DOTALL,
    )


def bake(html: str, block_id: str, payload: str) -> tuple[str, bool]:
    rx = _placeholder_re(block_id)
    if not rx.search(html):
        return html, False
    safe = payload.replace("</", "<\\/")  # guard against a stray closing tag
    return rx.sub(lambda m: m.group(1) + safe + m.group(3), html, count=1), True


def main() -> int:
    if not JSON_PATH.exists():
        print(f"Missing {JSON_PATH}; run scripts/parse_germany.py first")
        return 1
    payloads = {bid: p.read_text(encoding="utf-8") for bid, p in BLOCKS.items()
                if p.exists()}

    for name in PAGES:
        path = DOCS / name
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        baked = []
        for bid, payload in payloads.items():
            html, ok = bake(html, bid, payload)
            if ok:
                baked.append(bid)
        if "germany-data" not in baked:
            print(f"[warn]  {name}: no germany-data placeholder; skipped")
            continue
        path.write_text(html, encoding="utf-8")
        print(f"[write]  docs/{name} (baked: {', '.join(baked)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
