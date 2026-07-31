#!/usr/bin/env python3
"""Bake the parsed summary into the static page.

Reads ``docs/data/germany.json`` and injects it into the
``<script id="germany-data">`` placeholder in ``docs/index.html`` so the page
is fully self-contained (works over GitHub Pages, a local file, or any host,
with no fetch / CORS dependency).

Run ``scripts/parse_germany.py`` first to (re)generate the JSON, then this.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "docs" / "data" / "germany.json"
HTML_PATH = REPO_ROOT / "docs" / "index.html"

PLACEHOLDER_RE = re.compile(
    r'(<script id="germany-data" type="application/json">)(.*?)(</script>)',
    re.DOTALL,
)


def main() -> int:
    if not JSON_PATH.exists():
        print(f"Missing {JSON_PATH}; run scripts/parse_germany.py first")
        return 1
    data = JSON_PATH.read_text(encoding="utf-8")
    # Guard against the closing tag appearing inside the JSON payload.
    safe = data.replace("</", "<\\/")
    html = HTML_PATH.read_text(encoding="utf-8")
    if not PLACEHOLDER_RE.search(html):
        print("Could not find the germany-data placeholder in index.html")
        return 1
    html = PLACEHOLDER_RE.sub(lambda m: m.group(1) + safe + m.group(3), html, count=1)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"[write]  {HTML_PATH.relative_to(REPO_ROOT)} (data baked in, {len(safe):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
