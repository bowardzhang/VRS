#!/usr/bin/env python3
"""Overlay UK monthly provisional data onto countries.json, separately from quarterly detail."""
from __future__ import annotations
import csv,json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
COUNTRIES=ROOT/'docs'/'data'/'countries.json'; MONTHLY_TOTAL=ROOT/'data'/'UnitedKingdom'/'uk_monthly_total.csv'; MONTHLY_PT=ROOT/'data'/'UnitedKingdom'/'uk_monthly_powertrain.csv'
MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
MONTHLY_URL='https://www.gov.uk/government/statistics/developing-faster-indicators-of-transport-activity'; QUARTERLY_URL='https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files'
MIN_PLAUSIBLE=20_000; MAX_PLAUSIBLE=600_000

def monthly_rows():
    if not MONTHLY_TOTAL.exists():return []
    out=[]
    with MONTHLY_TOTAL.open(encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            y,m,total=int(r['year']),int(r['month']),int(r['total'])
            if MIN_PLAUSIBLE<=total<=MAX_PLAUSIBLE:out.append((y,m,total))
    return sorted(out)

def monthly_powertrain(y,m):
    if not MONTHLY_PT.exists():return {'has':False,'shares':[]}
    agg=defaultdict(int)
    with MONTHLY_PT.open(encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            if (int(r['year']),int(r['month']))==(y,m):agg[r['fuel']]+=int(r['count'])
    total=sum(agg.values())
    if not MIN_PLAUSIBLE<=total<=MAX_PLAUSIBLE:return {'has':False,'shares':[]}
    return {'has':True,'shares':[{'fuel':f,'total':c,'pct':round(100*c/total,1)} for f,c in sorted(agg.items())]}

def main():
    rows=monthly_rows()
    if not rows:print('[uk-dual] no valid monthly feed; keeping quarterly-only UK presentation'); return 0
    y,m,total=rows[-1]; countries=json.loads(COUNTRIES.read_text(encoding='utf-8')); uk=next((c for c in countries if c.get('code')=='UK'),None)
    if uk is None:raise RuntimeError('UK core missing from countries.json')
    quarterly=uk.get('latest') or {}; quarterly_period=quarterly.get('period',uk.get('latest_period')); quarterly_total=quarterly.get('total',uk.get('latest_total'))
    if quarterly:quarterly.update({'status':'official','granularity':'quarterly','source':'DfT VEH0160'})
    label=f'{MONTHS[m-1]} {y}'
    uk['latest_period']=label; uk['latest_total']=total; uk['latest_status']='provisional'; uk['latest_granularity']='monthly'
    uk['monthly_latest']={'period':label,'year':y,'month':m,'total':total,'status':'provisional','granularity':'monthly','source':'DfT VEH9902','source_url':MONTHLY_URL,'powertrain':monthly_powertrain(y,m)}
    uk['monthly_trends']={'labels':[f'{MONTHS[mm-1]} {yy}' for yy,mm,_ in rows],'series':[{'name':'Registrations','values':[v for _,_,v in rows]}],'status':'provisional','granularity':'monthly','source':'DfT VEH9902'}
    uk['quarterly_latest_period']=quarterly_period; uk['quarterly_latest_total']=quarterly_total; uk['dual_source']=True
    uk['source']='UK DfT VEH9902 (monthly provisional) + VEH0160 (quarterly official detail)'; uk['source_url']=MONTHLY_URL; uk['monthly_source_url']=MONTHLY_URL; uk['quarterly_source_url']=QUARTERLY_URL
    COUNTRIES.write_text(json.dumps(countries,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'[uk-dual] monthly history={len(rows)} points; headline={label} {total:,}; official detail={quarterly_period} {quarterly_total:,}')
    return 0
if __name__=='__main__':raise SystemExit(main())
