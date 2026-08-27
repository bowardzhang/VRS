<div align="center">

# VRS — Vehicle Registration Statistics

**European new-car registration data pipeline & open analytics**

[![GitHub Pages](https://img.shields.io/badge/hosted%20on-GitHub%20Pages-222?logo=github&logoColor=fff)](https://bowardzhang.github.io/VRS/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Data refresh](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fbowardzhang%2FVRS%2Frefs%2Fheads%2Fmain%2Fdocs%2Fdata%2Fgermany.json&query=%24.latest.year&label=latest%20DE%20data&color=1890ff&cacheSeconds=3600)](https://bowardzhang.github.io/VRS/)
[![Last pipeline run](https://img.shields.io/github/workflow/status/bowardzhang/VRS/Update%20registration%20data?label=pipeline&logo=githubactions&logoColor=fff)](https://github.com/bowardzhang/VRS/actions/workflows/update-data.yml)
[![Countries](https://img.shields.io/badge/countries-7-38bdf8?logo=openstreetmap&logoColor=fff)](https://bowardzhang.github.io/VRS/)
[![Repo size](https://img.shields.io/github/repo-size/bowardzhang/VRS?color=blueviolet)]()

**English** · [中文文档](#chinese)

</div>

---

VRS downloads, parses and publishes **monthly new-vehicle registration statistics** across major European markets — Germany, France, Spain, Netherlands, Finland, Austria, Sweden — as a self-contained static website. It also **estimates per-component supplier installation rates** (cockpit SoC, ADAS SoC, front radar, power semiconductor, LiDAR) by joining registration counts with a hand-curated model-to-platform mapping.

## Live site

**https://bowardzhang.github.io/VRS/** — a single `index.html` with all data baked in. No backend, no fetch, no external assets. Dark/light mode, interactive tooltips, country picker.

## Coverage

| Country | Source | Frequency | Detail level | Open data? |
|---------|--------|:---------:|--------------|:----------:|
| DE Germany | [KBA FZ 10.1](https://www.kba.de/DE/Statistik/Produktkatalog/produkte/Fahrzeuge/fz10/fz10_gentab.html) | monthly | brand, model, drivetrain | Y |
| ES Spain | [DGT](https://www.dgt.es/menusecundario/dgt-en-cifras/) MATRABA microdata | monthly | brand, model, fuel | Y |
| FR France | [INSEE BDM](https://www.insee.fr/fr/statistiques/serie/010756763) | monthly | national total only | Y |
| NL Netherlands | [RDW](https://opendata.rdw.nl/) Socrata API | monthly | brand, model, body | Y |
| FI Finland | [Traficom](https://tieto.traficom.fi/en) PxWeb | monthly | brand, model, powertrain | Y |
| AT Austria | Statistics Austria | monthly | brand | Y |
| SE Sweden | [SCB](https://www.scb.se/) | monthly | total, powertrain | Y |
| GB United Kingdom | [DfT VEH0160](https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files) | quarterly | brand, model, fuel | Y |

> **Note**: Italy is not yet covered (no open monthly brand-level feed). The UK is quarterly and lags by one quarter — Q2 2026 was still pending at publication time.

## Features

### Homepage (`docs/index.html`)

- **Latest month KPIs** — registrations, YTD, BEV/diesel share, YoY change
- **Brand ranking** — top brands with YoY comparison and brand logos
- **Model ranking** — top model series, split by drivetrain
- **Powertrain mix** — BEV/PHEV/HEV/petrol/diesel pie + YoY change
- **Trends over time** — multi-year line charts:
  - Brand trends (top marques over time)
  - Manufacturer origin trends (Germany, China, USA, Japan, Korea, ...)
  - Powertrain trends (BEV, PHEV, HEV, petrol, diesel)
  - Body-segment trends (SUV, sedan & hatch, MPV, sports)
- **Country picker** — multi-select, saved in a cookie, powers a Europe overview

### Deep-dive pages

| Page | Content |
|------|---------|
| `docs/analysis-china.html` | Chinese-origin brand penetration, monthly registrations, top models |
| `docs/analysis-ev.html` | BEV/PHEV/HEV trends, top models by category |
| `docs/analysis-soc.html` | Cockpit SoC installation-rate share by supplier |
| `docs/analysis-adas.html` | ADAS / perception SoC supplier share |
| `docs/analysis-radar.html` | Front-radar Tier-1 market share |
| `docs/analysis-power.html` | EV inverter power semiconductor (BEV-weighted) |
| `docs/analysis-lidar.html` | LiDAR fitment penetration & supplier split |
| `docs/analysis-q2-2026.html` | Q2 2026 quarterly snapshot — brands, models, origin, powertrain, suppliers |

### Quarterly analysis report

`docs/analysis-q2-2026-linkedin.md` generates an in-depth LinkedIn-ready analysis report each quarter. The latest edition covers:

- BEV share acceleration (DE 18.4% to 26.6%, FI 34.5% to 48.6%)
- Chinese OEM breakthrough: **7.2% pooled share**, +85.6% YoY, BYD alone >36k units
- Supplier installation-rate shifts: Qualcomm +1.7pp, STMicro (SiC) 3% to 9%, Infineon 96% to 90%
- SUV surpassing sedans in Germany (46.4% vs 42.3%)

## Data pipeline

### Architecture

```
KBA .xlsx ---download--> data/Germany/fz10_YYYY_MM.xlsx
                             |
                             +- parse -> data/Germany/processed/germany_registrations.csv
                             |            docs/data/germany.json
                             |
                             +- build -> docs/index.html
```

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/download_germany.py` | Fetch KBA FZ 10.1 workbooks |
| `scripts/parse_germany.py` | Parse workbooks into tidy CSV + JSON |
| `scripts/parse_segments.py` | Parse KBA FZ 11 body-segment trends |
| `scripts/download_netherlands.py` | Fetch RDW brand/model data |
| `scripts/download_finland.py` | Fetch Traficom brand/powertrain data |
| `scripts/download_france.py` | Fetch INSEE monthly totals |
| `scripts/download_spain.py` | Download & aggregate DGT microdata |
| `scripts/download_uk.py` | Fetch DfT quarterly data |
| `scripts/download_austria.py` | Fetch Austria monthly brand data |
| `scripts/download_sweden.py` | Fetch SCB totals + powertrain |
| `scripts/parse_suppliers.py` | Join vehicle_specs.csv into supplier install rates |
| `scripts/parse_suppliers_geo.py` | Cross-country supplier comparison (DE/ES/FI/NL/UK) |
| `scripts/build_supplier_pages.py` | Generate per-component HTML pages |
| `scripts/build_countries.py` | Assemble multi-country country picker JSON |
| `scripts/build_europe.py` | Assemble Europe overview JSON |
| `scripts/build_q2_report.py` | Generate Q2 vertical analysis (HTML + JSON) |
| `scripts/gen_report_md.py` | Generate Markdown report for LinkedIn |
| `scripts/build_site.py` | Bake all JSON into self-contained HTML pages |
| `scripts/supplier_normalize.py` | Model-name normalisation utilities |

### Quick start

```bash
git clone https://github.com/bowardzhang/VRS.git
cd VRS
pip install -r requirements.txt

# Download latest data
python scripts/download_germany.py --last 3
python scripts/download_germany.py --month 2026-06
# Parse
python scripts/parse_germany.py
python scripts/parse_segments.py
python scripts/parse_suppliers.py
python scripts/build_supplier_pages.py

# Other countries (no API key needed)
python scripts/download_netherlands.py --last 3
python scripts/download_finland.py --last 3

# Build multi-country core
python scripts/build_countries.py
python scripts/build_europe.py

# Build the Q2 report
python scripts/build_q2_report.py

# Build static site
python scripts/build_site.py
```

### GitHub Actions automation

Two workflows run autonomously:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `update-data.yml` | Monthly (8th, 06:00 UTC) + manual | Downloads latest KBA/RDW data, re-parses, rebuilds site, commits |
| `pages.yml` | On `docs/**` push | Publishes to GitHub Pages |

## Supplier installation-rate estimate

KBA reports *how many* of each model were registered but nothing about their electronics. `scripts/parse_suppliers.py` joins the registration counts to a hand-authored mapping in **`data/vehicle_specs.csv`** that estimates the supplier for each model's platform across:

- **Cockpit SoC** — Renesas (VW MQB), Qualcomm (BMW iDrive, Mini), NVIDIA (Mercedes MBUX), AMD (Tesla), Samsung (VW MEB)
- **ADAS / perception SoC** — Mobileye (~75% share), NVIDIA (Mercedes, Volvo), Denso (Toyota), Tesla FSD
- **Front-radar Tier-1** — Continental (~53%), Bosch, Valeo, HL Klemove, Denso
- **EV inverter power semi** (BEV-weighted) — Infineon (~90%), STMicro (Tesla SiC), BYD
- **LiDAR** — Valeo (Mercedes Drive Pilot), Luminar (Volvo EX90); <0.2% penetration

Coverage: **~83%** of registrations mapped; the rest report as *Unclassified*. The mapping is editable — corrections welcome via PR to `data/vehicle_specs.csv`.

> These are **estimates**. Cockpit SoC and LiDAR are the best-sourced; ADAS, power-semi and radar are lower-confidence OEM / platform-relationship estimates.

## Data licence

Registration data (c) respective national authorities (KBA, DGT, INSEE, RDW, Traficom, SCB, DfT). This repository redistributes the published figures for analysis; refer to each source site for terms of use. Code is MIT-licensed.

---

<div align="center">

## <a name="chinese"></a>中文说明

**VRS — 欧洲车辆注册统计**

自动下载并分析欧洲多国月度乘用车注册数据，生成自助式数据看板，并提供季度深度分析报告。

### 支持的市场

| 国家 | 数据来源 | 更新频率 | 内容粒度 |
|------|----------|:--------:|----------|
| DE 德国 | KBA FZ 10.1 | 月度 | 品牌、车型、动力 |
| ES 西班牙 | DGT MATRABA | 月度 | 品牌、车型、燃料 |
| FR 法国 | INSEE BDM | 月度 | 总量 |
| NL 荷兰 | RDW | 月度 | 品牌、车型、车身 |
| FI 芬兰 | Traficom | 月度 | 品牌、车型、动力 |
| AT 奥地利 | 统计局 | 月度 | 品牌 |
| SE 瑞典 | SCB | 月度 | 总量、动力 |

### 核心功能

- 多国总量总览 — 季度、品牌、来源国维度
- 时序趋势 — 品牌、动力类型、车身形态、来源国的多年度走势
- 电动化渗透深度 — BEV / PHEV / HEV 份额变化
- 中国品牌追踪 — BYD、MG、LEAPMOTOR 等在欧洲的注册量
- 供应商穿透分析 — 座舱域控芯片、智驾芯片、前向雷达、功率半导体的供应商上装率估算

### 最新季度洞察（2026 Q2）

| 指标 | 数据 |
|------|------|
| 德国 BEV 份额 | 26.6%（同比 +8.2pp）|
| 中国品牌合计份额 | 7.2%（同比 +3.1pp，+85.6%）|
| BYD Q2 注册量 | 36,718 辆（+154.9%）|
| 座舱 SoC — Qualcomm 份额 | 22.7%（+1.7pp）|
| 逆变器功率芯片 — STMicro（SiC）| 9.3%（+6.0pp）|

### 数据源授权

注册数据 (c) 各国主管机关（KBA、DGT、INSEE、RDW、Traficom、SCB、DfT）。本仓库仅作分析用途发布。代码采用 MIT 许可。

</div>
