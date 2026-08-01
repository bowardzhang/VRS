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
no external assets, light/dark aware, interactive tooltips).

**Latest month** — headline registrations (month + year-to-date), BEV/diesel
share, top brands and top model series (ranked bar charts), and powertrain
penetration.

**Trends over time** — interactive multi-year charts (crosshair + tooltip),
built from every month of detail available:

- **by brand** — monthly registrations for the largest brands (multi-line);
- **by manufacturer origin** — monthly registrations grouped by the marque's
  country of origin (Germany, China, USA, Japan, South Korea, France, Czechia,
  Spain, …), shown as a stacked area;
- **by powertrain** — one line per drivetrain (petrol, diesel, BEV, plug-in
  hybrid, hybrid);
- **by body segment** — one line per body shape (sedan & hatch, SUV, MPV & van,
  sports, other), from KBA table **FZ 11 (Segmente)** parsed by
  `scripts/parse_segments.py` (KBA size/segment classes grouped into shapes).

The latest-month brand and model charts also show **year-over-year** change vs
the same month a year earlier, each brand/model marked with its logo (open-source
brand icons where available, a colored monogram otherwise). The page defaults to
the light theme. The latest-month powertrain split is shown as a **pie** of the
five mutually-exclusive drivetrains with per-slice year-over-year change.

### Deep-dive sub-pages

The **manufacturer-origin** chart title links to a secondary analysis page.
`docs/analysis-china.html` drills into **Chinese-origin marques**: monthly
registrations, market-share trend, per-brand trends, and the top Chinese brands
and model series (with logos and year-over-year change). Its data comes from the
`china` block that `parse_germany.py` (`build_origin_analysis`) adds to
`germany.json`; `build_site.py` bakes `germany.json` + `data/brand_logos.json`
into every page in its `PAGES` list, so sub-pages stay self-contained and update
on the same monthly schedule.

Brand- and origin-level charts span the months backed by a full workbook; the
powertrain chart also uses the supplementary series, so it reaches back to 2021.

Serve it with GitHub Pages (Pages source `/docs`, or the included Actions
workflow) or open the file directly. Rebuild after adding new months with steps
2–3 above.

## Automated updates (GitHub Actions)

Two workflows keep the published site current with no manual work:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `.github/workflows/update-data.yml` | Monthly (cron, 8th at 06:00 UTC) + manual | Downloads the latest KBA workbooks, re-parses, rebuilds the page, and commits `data/Germany` + `docs`. |
| `.github/workflows/pages.yml`       | On `docs/**` push, after a data update, or manual | Publishes `docs/` to GitHub Pages. |

GitHub's runners have open internet access, so they can reach `www.kba.de`
directly (unlike a locked-down local/sandbox environment). The downloader finds
each month's real `.xlsx` link from its KBA landing page, so it is not affected
by the unpredictable `?__blob=publicationFile&v=N` version parameter.

**Initial 3-year backfill:** run the *Update KBA registration data* workflow
manually (Actions tab → Run workflow) with **months = `36`**. The monthly
schedule then fetches the trailing three months each run (skipping files already
present) so newly published and late-revised months are picked up automatically.

## Network note (KBA host)

KBA serves the workbooks from `www.kba.de`. In sandboxed/CI environments with an
egress allow-list, that host must be permitted or the download fails with an
HTTP 403 at the proxy. Allow-list changes generally take effect only in a
**newly started** session/environment, not one already running. GitHub Actions
runners are not subject to this restriction (see *Automated updates* above).

## Data source & licence

Data © Kraftfahrt-Bundesamt, Flensburg. Table FZ 10.1. This repository
redistributes the published figures for analysis; refer to the KBA site for
terms of use.
