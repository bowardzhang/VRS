#!/usr/bin/env python3
"""Download new car registrations for the United Kingdom (quarterly, by make).

Source: UK Department for Transport (DfT) vehicle licensing statistics,
``df_VEH0160_UK`` — vehicles registered for the first time in the United
Kingdom by body type / make / model / fuel.  The UK file is deliberately used
instead of the Great Britain file so this dataset includes Northern Ireland and
matches the site's "United Kingdom" label.

We keep body type = "Cars", sum over model/fuel by make and quarter, and write
the compact ``data/UnitedKingdom/uk_quarterly_brands.csv`` plus model and
powertrain detail files.  The source CSV itself is not committed.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "UnitedKingdom"
OUT_CSV = OUT_DIR / "uk_quarterly_brands.csv"
MODELS_CSV = OUT_DIR / "uk_models.csv"
MODELS_LATEST_CSV = OUT_DIR / "uk_models_latest.csv"
MODELS_QUARTERLY_CSV = OUT_DIR / "uk_models_quarterly.csv"
POWERTRAIN_CSV = OUT_DIR / "uk_powertrain.csv"
MODELS_SINCE = (2023, 3)

UK_FUEL = {
    "Petrol": "Petrol", "Diesel": "Diesel", "Battery electric": "BEV",
    "Plug-in hybrid electric (petrol)": "PHEV", "Plug-in hybrid electric (diesel)": "PHEV",
    "Hybrid electric (petrol)": "Hybrid", "Hybrid electric (diesel)": "Hybrid",
    "Fuel cell electric": "Other", "Range extended electric": "Other",
    "Gas": "Other", "Other fuel types": "Other",
}

# DfT's current UK VEH0160 file (updated 15 July 2026).  This is the UK scope,
# not df_VEH0160_GB.
SRC = "https://assets.publishing.service.gov.uk/media/6a54d2eca6586e258d371d71/df_VEH0160_UK.csv"
_COL = re.compile(r"^(\d{4})\s*Q([1-4])$")


def fetch(retries: int = 4) -> str:
    delay = 3.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(SRC, headers={"User-Agent": "VRS/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read().decode("latin-1")
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"  [retry {attempt+1}] {exc}", file=sys.stderr)
            time.sleep(delay); delay *= 2
    return ""


def _periods(header, from_year=0, since=None):
    out=[]
    for i,h in enumerate(header):
        m=_COL.match(h.strip())
        if not m: continue
        yq=(int(m.group(1)),int(m.group(2)))
        if yq[0] >= from_year and (since is None or yq >= since): out.append((i,*yq))
    return out


def _ival(row,i):
    if i>=len(row): return None
    raw=row[i].strip().replace(",","")
    if raw in ("","-","[c]","[x]","[z]",".."): return None
    try: return int(raw)
    except ValueError: return None


def parse(text, from_year):
    reader=csv.reader(io.StringIO(text)); header=next(reader); periods=_periods(header,from_year)
    bt_i=header.index("BodyType"); mk_i=header.index("Make"); data={}
    for row in reader:
        if len(row)<=mk_i or row[bt_i].strip()!="Cars": continue
        make=row[mk_i].strip().upper()
        if not make: continue
        for i,y,q in periods:
            cnt=_ival(row,i)
            if cnt: data[(y,q,make)]=data.get((y,q,make),0)+cnt
    return data


def parse_models(text):
    reader=csv.reader(io.StringIO(text)); header=next(reader); cols=[i for i,_,_ in _periods(header,since=MODELS_SINCE)]
    bt_i=header.index("BodyType"); mk_i=header.index("Make"); gm_i=header.index("GenModel"); out={}
    for row in reader:
        if len(row)<=gm_i or row[bt_i].strip()!="Cars": continue
        key=(row[mk_i].strip().upper(),row[gm_i].strip().upper())
        if not all(key): continue
        tot=sum((_ival(row,i) or 0) for i in cols)
        if tot: out[key]=out.get(key,0)+tot
    return out


def parse_models_quarterly(text):
    reader=csv.reader(io.StringIO(text)); header=next(reader); periods=_periods(header,since=MODELS_SINCE)
    bt_i=header.index("BodyType"); mk_i=header.index("Make"); gm_i=header.index("GenModel"); out={}
    for row in reader:
        if len(row)<=gm_i or row[bt_i].strip()!="Cars": continue
        mk=row[mk_i].strip().upper(); md=row[gm_i].strip().upper()
        if not mk or not md: continue
        for i,y,q in periods:
            c=_ival(row,i)
            if c: out[(y,q,mk,md)]=out.get((y,q,mk,md),0)+c
    return out


def parse_powertrain(text,from_year):
    reader=csv.reader(io.StringIO(text)); header=next(reader); periods=_periods(header,from_year)
    bt_i=header.index("BodyType"); fu_i=header.index("Fuel"); out={}
    for row in reader:
        if len(row)<=fu_i or row[bt_i].strip()!="Cars": continue
        fuel=UK_FUEL.get(row[fu_i].strip(),"Other")
        for i,y,q in periods:
            c=_ival(row,i)
            if c: out[(y,q,fuel)]=out.get((y,q,fuel),0)+c
    return out


def parse_models_latest(text):
    reader=csv.reader(io.StringIO(text)); header=next(reader); periods=_periods(header)
    if not periods: return None,{}
    ci,ly,lq=max(periods,key=lambda x:(x[1],x[2])); bt_i=header.index("BodyType"); mk_i=header.index("Make"); gm_i=header.index("GenModel"); out={}
    for row in reader:
        if len(row)<=max(gm_i,ci) or row[bt_i].strip()!="Cars": continue
        c=_ival(row,ci)
        if c:
            key=(row[mk_i].strip().upper(),row[gm_i].strip().upper()); out[key]=out.get(key,0)+c
    return (ly,lq),out


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--from-year",type=int,default=2019); args=ap.parse_args()
    print(f"[uk] downloading DfT VEH0160_UK (quarterly, cars) from {args.from_year} …")
    text=fetch(); data=parse(text,args.from_year); by_q={}
    for (y,q,_),c in data.items(): by_q[(y,q)]=by_q.get((y,q),0)+c
    for yq in sorted(by_q): print(f"  {yq[0]} Q{yq[1]}: {by_q[yq]:,} cars")
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    rows=sorted(data.items(),key=lambda kv:(kv[0][0],kv[0][1],-kv[1],kv[0][2]))
    with OUT_CSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh); w.writerow(["year","quarter","brand","count"])
        for (y,q,b),c in rows: w.writerow([y,q,b,c])
    models=parse_models(text)
    with MODELS_CSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh); w.writerow(["brand","model","total"])
        for (mk,md),c in sorted(models.items(),key=lambda kv:-kv[1]): w.writerow([mk,md,c])
    lyq,lm=parse_models_latest(text)
    with MODELS_LATEST_CSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh); w.writerow(["year","quarter","brand","model","count"])
        if lyq:
            for (mk,md),c in sorted(lm.items(),key=lambda kv:-kv[1]): w.writerow([lyq[0],lyq[1],mk,md,c])
    mq=parse_models_quarterly(text)
    with MODELS_QUARTERLY_CSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh); w.writerow(["year","quarter","brand","model","count"])
        for (y,q,mk,md),c in sorted(mq.items(),key=lambda kv:(kv[0][0],kv[0][1],-kv[1])): w.writerow([y,q,mk,md,c])
    pt=parse_powertrain(text,args.from_year)
    with POWERTRAIN_CSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh); w.writerow(["year","quarter","fuel","count"])
        for (y,q,f),c in sorted(pt.items()): w.writerow([y,q,f,c])
    print(f"[write] UK quarterly: {len(rows)} brand rows, {len(mq)} model-quarter rows, {len(pt)} powertrain rows")
    return 0

if __name__=="__main__": raise SystemExit(main())
