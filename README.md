# VRS — Vehicle Registration Statistics

Downloads, analyses, and publishes monthly new-vehicle registration data for
major European countries as a static website.

Countries currently covered:

- **🇩🇪 Germany** — official
  [Kraftfahrt-Bundesamt (KBA)](https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html)
  table **FZ 10.1** — *Neuzulassungen von Personenkraftwagen nach Marken und
  Modellreihen* (new passenger-car registrations by brand and model series).
- **🇳🇱 Netherlands** — [RDW](https://opendata.rdw.nl/) (Rijksdienst voor het
  Wegverkeer) open data, the national vehicle register, via its Socrata API
  (dataset `m9d7-ebf2`). New registrations are proxied by *first admission this
  month* of a passenger car.
- **🇫🇮 Finland** — [Traficom](https://tieto.traficom.fi/en) / Statistics
  Finland *first registrations of passenger cars* by make, via the Traficom
  PxWeb open-data API (no key required).

The site aggregates any selected subset of countries — a **🌍 country picker**
in the top-right (multi-select, defaults to all, saved in a cookie) drives an
*Europe overview* (total registrations by country, top brands and manufacturer
origin across the selection). Country-specific deep dives (German KBA body
segments, the supplier installation-rate pages) are shown when that country is
in scope.

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
| `scripts/download_netherlands.py` | Fetch monthly new passenger-car counts by brand from the RDW Socrata API into `data/Netherlands/`. |
| `scripts/download_finland.py` | Fetch monthly first-registration counts by make from the Traficom PxWeb API into `data/Finland/`. |
| `scripts/parse_suppliers.py`  | Join `data/vehicle_specs.csv` to the counts and add a per-component supplier installation-rate (`suppliers.dimensions`) block to the JSON. |
| `scripts/build_supplier_pages.py` | Generate one self-contained secondary page per component (`analysis-soc/adas/radar/power/lidar.html`) from a shared template. |
| `scripts/build_countries.py`  | Assemble a uniform multi-country core (`docs/data/countries.json`) that powers the country picker + Europe overview. |
| `scripts/build_site.py`       | Bake the JSON into `docs/*.html` so the pages are fully self-contained. |

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
python scripts/parse_segments.py       # body-segment trends (FZ 11)
python scripts/parse_suppliers.py      # per-component supplier installation rate
python scripts/build_supplier_pages.py # generate the per-component secondary pages

# 1b. Other countries (open data — no API key required)
python scripts/download_netherlands.py # RDW (or --last N for trailing months)
python scripts/download_finland.py      # Traficom / Statistics Finland
python scripts/build_countries.py       # assemble the multi-country core

# 3. Rebuild the static pages
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

Two chart titles on the homepage link to secondary analysis pages:

- **`docs/analysis-china.html`** (from the *manufacturer-origin* chart) drills
  into **Chinese-origin marques**: monthly registrations, market-share trend,
  per-brand trends, and the top Chinese brands and model series. Data: the
  `china` block from `build_origin_analysis()`.
- **`docs/analysis-ev.html`** (from the *powertrain* chart) drills into
  **electrified drivetrains** — BEV, hybrid and plug-in hybrid: per-category
  count and market-share trends, and the top model series in each category.
  Data: the `ev` block from `build_ev_analysis()`.
- **Supplier statistics** (the *供应商统计* tile section on the homepage) links to
  one secondary page per automotive electronic component, each estimating that
  component's **supplier installation rate (“上装率”)** by weighting a per-model
  configuration estimate with the KBA registration counts:
  - **`docs/analysis-soc.html`** — cockpit domain-controller (“车机”) SoC;
  - **`docs/analysis-adas.html`** — ADAS / front-camera perception SoC;
  - **`docs/analysis-radar.html`** — front-radar Tier-1;
  - **`docs/analysis-power.html`** — EV traction-inverter power semiconductor
    (weighted by BEV registrations);
  - **`docs/analysis-lidar.html`** — LiDAR fitment & supplier.

  Each page shows the supplier share, a mix-over-time (or penetration) chart,
  and — per major supplier — the **top-selling model series that use it**. Data:
  the `suppliers.dimensions` block written by `scripts/parse_suppliers.py`;
  pages generated by `scripts/build_supplier_pages.py`.

### Supplier installation-rate estimate

KBA reports *how many* of each model were registered but nothing about their
electronics. `scripts/parse_suppliers.py` joins the registration counts to a
hand-authored, editable estimate in **`data/vehicle_specs.csv`** that maps each
model to the suppliers of its **current-generation platform / brand software
stack** across several components:

- **Cockpit SoC** — e.g. VW MQB → Renesas *MIB3*, VW MEB → Samsung *Exynos Auto*,
  Mercedes *MBUX* → NVIDIA, BMW *iDrive 8/9* + Mini → Qualcomm, Tesla → AMD.
- **ADAS / perception SoC** — Mobileye dominates Europe; NVIDIA (Mercedes,
  Volvo EX90), Tesla (own FSD), Denso (Toyota).
- **EV inverter power semiconductor** (weighted by BEV registrations) — Infineon,
  STMicro (Tesla SiC), BYD (own).
- **Front-radar Tier-1** — Continental, Bosch, Valeo, HL Klemove, Denso.
- **LiDAR** — Valeo (Mercedes Drive Pilot), Luminar (Volvo EX90); effectively
  absent from standard configs, so penetration stays near zero.

Silicon is set by the platform, not the individual trim, so this platform-level
mapping is the tractable approach; each row carries a `confidence` and short
note, and any unmapped model is reported as *Unclassified* (≈92 % of
registrations are classified). **Cockpit SoC / LiDAR are the best-sourced; ADAS,
power-semi and radar are lower-confidence OEM/platform-relationship estimates.**
The parser emits, per component, the supplier share, a monthly series, and the
top-selling models for each supplier. **Figures for the electronics are
estimates; corrections to `data/vehicle_specs.csv` are welcome.** Run it after
`parse_germany.py`, then `build_supplier_pages.py`, then `build_site.py`.

Both add their block to `germany.json`, show logos + year-over-year change, and
are baked self-contained by `build_site.py` (which injects `germany.json` +
`data/brand_logos.json` into every page in its `PAGES` list), so the sub-pages
update on the same monthly schedule as the homepage.

Brand- and origin-level charts span the months backed by a full workbook; the
powertrain chart also uses the supplementary series, so it reaches back to 2021.

Serve it with GitHub Pages (Pages source `/docs`, or the included Actions
workflow) or open the file directly. Rebuild after adding new months with steps
2–3 above.

## Automated updates (GitHub Actions)

Two workflows keep the published site current with no manual work:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `.github/workflows/update-data.yml` | Monthly (cron, 8th at 06:00 UTC) + manual | Downloads the latest KBA workbooks **and RDW (Netherlands) data**, re-parses, rebuilds the site, and commits `data/Germany` + `data/Netherlands` + `docs`. |
| `.github/workflows/pages.yml`       | On `docs/**` push, after a data update, or manual | Publishes `docs/` to GitHub Pages. |

GitHub's runners have open internet access, so they can reach `www.kba.de`
directly (unlike a locked-down local/sandbox environment). The downloader finds
each month's real `.xlsx` link from its KBA landing page, so it is not affected
by the unpredictable `?__blob=publicationFile&v=N` version parameter.

**Initial 3-year backfill:** run the *Update registration data* workflow
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
