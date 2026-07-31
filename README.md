# VRS — Vehicle Registration Statistics

Downloads, analyses, and publishes monthly new-vehicle registration data for
major European countries as a static website.

**First country: Germany**, using the official
[Kraftfahrt-Bundesamt (KBA)](https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html)
table **FZ 10.1** — *Neuzulassungen von Personenkraftwagen nach Marken und
Modellreihen* (new passenger-car registrations by brand and model series).

## Pipeline

```
KBA .xlsx  ──download──►  data/Germany/fz10_YYYY_MM.xlsx
                              │
                              ├─ parse ─►  data/Germany/processed/germany_registrations.csv   (tidy, all drivetrains)
                              │            docs/data/germany.json                              (site summary)
                              │
                              └─ build ─►  docs/index.html                                     (self-contained static page)
```

Three small, dependency-light scripts, each runnable on its own:

| Script | Purpose |
|--------|---------|
| `scripts/download_germany.py` | Fetch the monthly FZ 10.1 workbooks from KBA into `data/Germany/`. |
| `scripts/parse_germany.py`    | Parse every workbook into a tidy CSV + a compact JSON summary. |
| `scripts/build_site.py`       | Bake the JSON into `docs/index.html` so the page is fully self-contained. |

### Historical powertrain series

`data/Germany/kba_monthly_powertrain.csv` holds a longer monthly series of new
registrations by drivetrain (BEV, diesel, plug-in hybrid and petrol),
**January 2021 – June 2026**. These are the official KBA FZ 10 figures — the
`source_url` column points at each month's workbook — assembled from the
open-source [`hboisgibault/ev-tracker`](https://github.com/hboisgibault/ev-tracker)
project, which parses the same KBA workbooks, while a direct KBA download is
unavailable in this environment (see the network note below). The June 2026
values were cross-checked against the locally held `fz10_2026_06.xlsx` and match
exactly.

`parse_germany.py` merges this series into the site so the *powertrain-mix-over-
time* chart spans several years; any month that also has a full FZ 10.1 workbook
locally uses the richer workbook figures (and keeps its brand / model detail).
As full workbooks are downloaded, they automatically take precedence over the
supplementary rows.

## Usage

```bash
pip install -r requirements.txt

# 1. Download data (see the network note below)
python scripts/download_germany.py --from 2025-01 --to 2026-06   # a range
python scripts/download_germany.py --month 2026-06               # one month
python scripts/download_germany.py --to 2026-06 --last 12        # last 12 months

# 2. Parse the workbooks -> CSV + JSON
python scripts/parse_germany.py

# 3. Rebuild the static page
python scripts/build_site.py
```

## The website

`docs/index.html` is a **self-contained** static page (data baked in — no fetch,
no external assets, light/dark aware). It shows, for the latest month:

- headline registrations (month + year-to-date), BEV share and diesel share;
- top brands and top model series (ranked bar charts);
- powertrain penetration (BEV, hybrid, plug-in hybrid, diesel);
- a **powertrain-mix-over-time** chart — one line per drivetrain (BEV, petrol,
  diesel, plug-in hybrid) across every month available, which appears
  automatically once two or more months of data are present.

Serve it with GitHub Pages (set Pages source to `/docs`) or open the file
directly. Rebuild after adding new months with steps 2–3 above.

## Network note (KBA host)

KBA serves the workbooks from `www.kba.de`. In sandboxed/CI environments with an
egress allow-list, that host must be permitted or the download fails with an
HTTP 403 at the proxy. Allow-list changes generally take effect only in a
**newly started** session/environment, not one already running.

## Data source & licence

Data © Kraftfahrt-Bundesamt, Flensburg. Table FZ 10.1. This repository
redistributes the published figures for analysis; refer to the KBA site for
terms of use.
