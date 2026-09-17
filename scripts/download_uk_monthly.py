#!/usr/bin/env python3
"""Download DfT VEH9902 monthly provisional UK passenger-car registrations.

The latest VEH9902 workbook is a long-format time series. Parse every available
UK Cars month so the site can show a monthly historical trend, while keeping the
quarterly VEH0160 series separate and authoritative for detailed breakdowns.
"""
from __future__ import annotations
import csv, re
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin
import requests
from odf import teletype
from odf.opendocument import load
from odf.table import Table, TableCell, TableRow
from odf.text import P

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'data'/'UnitedKingdom'; OUT_TOTAL=OUT/'uk_monthly_total.csv'; OUT_PT=OUT/'uk_monthly_powertrain.csv'
PAGE='https://www.gov.uk/government/statistics/developing-faster-indicators-of-transport-activity'
MONTH_NAMES=['January','February','March','April','May','June','July','August','September','October','November','December']
MONTHS={m.lower():i for i,m in enumerate(MONTH_NAMES,1)}
MIN_PLAUSIBLE=20_000; MAX_PLAUSIBLE=600_000

def _text(c):
    t=' '.join(teletype.extractText(p) for p in c.getElementsByType(P)).strip()
    if t:return t
    for a in ('datevalue','value','stringvalue'):
        try:v=c.getAttribute(a)
        except Exception:v=None
        if v not in (None,''):return str(v)
    return ''

def _cells(row):
    out=[]
    for c in row.getElementsByType(TableCell):
        out.extend([_text(c)]*min(int(c.getAttribute('numbercolumnsrepeated') or 1),100))
    return out

def discover():
    r=requests.get(PAGE,timeout=60,headers={'User-Agent':'VRS/1.0'}); r.raise_for_status()
    pat=re.compile(r'href="([^"]+\.ods[^"]*)"[^>]*>(.*?)</a>',re.I|re.S); candidates=[]
    for href,html in pat.findall(r.text):
        label=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html)).strip()
        if 'cars and light goods vehicles registered for the first time' not in label.lower():continue
        m=re.search(r'('+'|'.join(MONTH_NAMES)+r')\s+(20\d{2})',label,re.I)
        if m:candidates.append((int(m.group(2)),MONTHS[m.group(1).lower()],urljoin(PAGE,href)))
    if not candidates:raise RuntimeError('Could not discover a dated DfT VEH9902 ODS link')
    return max(candidates)

def _num(v):
    s=v.strip().replace(',','').replace(' ','')
    return int(float(s)) if re.fullmatch(r'\d+(?:\.0+)?',s) else None

def _period(v):
    m=re.search(r'('+'|'.join(MONTH_NAMES)+r')\s+(20\d{2})',v,re.I)
    return (int(m.group(2)),MONTHS[m.group(1).lower()]) if m else None

def parse_all(blob):
    doc=load(BytesIO(blob)); agg=defaultdict(lambda:defaultdict(int))
    for table in doc.spreadsheet.getElementsByType(Table):
        rows=[_cells(r) for r in table.getElementsByType(TableRow)]; header=None; cols=None
        for i,vals in enumerate(rows):
            norm=[v.strip().lower() for v in vals]; req=['geography','date','body type','fuel type','number']
            if all(x in norm for x in req):header=i; cols={x:norm.index(x) for x in req}; break
        if header is None:continue
        for vals in rows[header+1:]:
            if max(cols.values())>=len(vals):continue
            if vals[cols['geography']].strip().lower()!='united kingdom' or vals[cols['body type']].strip().lower()!='cars':continue
            period=_period(vals[cols['date']]); number=_num(vals[cols['number']])
            if not period or number is None or not 0<=number<=MAX_PLAUSIBLE:continue
            raw=vals[cols['fuel type']].strip().upper(); fuel={'ZEV':'ZEV','OTHER':'Non-ZEV'}.get(raw,raw)
            agg[period][fuel]+=number
    valid={}
    for period,fuels in agg.items():
        total=sum(fuels.values())
        if MIN_PLAUSIBLE<=total<=MAX_PLAUSIBLE:valid[period]=(dict(fuels),total)
    if not valid:raise RuntimeError('VEH9902 contained no plausible UK Cars monthly rows')
    return valid

def main():
    release_y,release_m,url=discover(); print(f'[uk-monthly] release {release_y}-{release_m:02d}: {url}')
    r=requests.get(url,timeout=90,headers={'User-Agent':'VRS/1.0'}); r.raise_for_status(); months=parse_all(r.content)
    if (release_y,release_m) not in months:raise RuntimeError('Latest advertised VEH9902 month missing from parsed series')
    OUT.mkdir(parents=True,exist_ok=True)
    with OUT_TOTAL.open('w',encoding='utf-8',newline='') as fh:
        w=csv.writer(fh); w.writerow(['year','month','total'])
        for (y,m),(fuels,total) in sorted(months.items()):w.writerow([y,m,total])
    with OUT_PT.open('w',encoding='utf-8',newline='') as fh:
        w=csv.writer(fh); w.writerow(['year','month','fuel','count'])
        for (y,m),(fuels,total) in sorted(months.items()):
            for fuel,count in sorted(fuels.items()):w.writerow([y,m,fuel,count])
    latest=months[(release_y,release_m)]
    print(f'[write] {OUT_TOTAL.relative_to(ROOT)}: {len(months)} months; latest={release_y}-{release_m:02d} {latest[1]:,}')
    return 0

if __name__=='__main__':raise SystemExit(main())
