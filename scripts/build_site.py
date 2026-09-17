#!/usr/bin/env python3
"""Bake parsed JSON into static pages and install the UK dual-frequency trend UI."""
from __future__ import annotations
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; DOCS=ROOT/'docs'
BLOCKS={'germany-data':DOCS/'data'/'germany.json','brand-logos':DOCS/'data'/'brand_logos.json','countries-data':DOCS/'data'/'countries.json','suppliers-geo':DOCS/'data'/'suppliers_geo.json','europe-data':DOCS/'data'/'europe.json'}
PAGES=['index.html','analysis-china.html','analysis-ev.html','analysis-soc.html','analysis-adas.html','analysis-radar.html','analysis-power.html','analysis-lidar.html']

def bake(html,bid,payload):
    rx=re.compile(r'(<script id="'+re.escape(bid)+r'" type="application/json">)(.*?)(</script>)',re.DOTALL)
    if not rx.search(html):return html,False
    safe=payload.replace('</','<\\/')
    return rx.sub(lambda m:m.group(1)+safe+m.group(3),html,count=1),True

def install_monthly_ui(html):
    # Add a separate monthly-provisional chart below the existing quarterly charts.
    old='''    if (!blocks) return "";\n    return '<h4 style="margin-top:6px">Historical trends <span style="text-transform:none;font-weight:400;color:var(--muted)">— quarterly</span></h4>' +\n      '<div class="cd-trends">' + blocks + '</div>';'''
    new='''    if (!blocks && !c.monthly_trends) return "";\n    var quarterly = blocks ? '<h4 style="margin-top:6px">Historical trends <span style="text-transform:none;font-weight:400;color:var(--muted)">— official quarterly</span></h4><div class="cd-trends">' + blocks + '</div>' : '';\n    var monthly = c.monthly_trends ? '<h4 style="margin-top:22px">Monthly registrations <span style="text-transform:none;font-weight:400;color:var(--muted)">— provisional · DfT VEH9902</span></h4><div class="cd-trends">' + chartCell("Cars registered", "tm_" + c.code, "lm_" + c.code) + '</div>' : '';\n    return quarterly + monthly;'''
    if old in html:html=html.replace(old,new,1)
    draw='''    cs.forEach(function (c) {\n      if (c.brand_trends && $("tb_" + c.code))'''
    draw_new='''    cs.forEach(function (c) {\n      if (c.monthly_trends && $("tm_" + c.code)) drawLines($("tm_" + c.code), $("lm_" + c.code), $("tip_tm_" + c.code), c.monthly_trends, function () { return "#2a78d6"; });\n      if (c.brand_trends && $("tb_" + c.code))'''
    if draw in html:html=html.replace(draw,draw_new,1)
    return html

def main():
    if not (DOCS/'data'/'germany.json').exists():return 1
    payloads={k:p.read_text(encoding='utf-8') for k,p in BLOCKS.items() if p.exists()}
    for name in PAGES:
        path=DOCS/name
        if not path.exists():continue
        html=path.read_text(encoding='utf-8'); baked=[]
        if name=='index.html':html=install_monthly_ui(html)
        for bid,payload in payloads.items():
            html,ok=bake(html,bid,payload)
            if ok:baked.append(bid)
        if 'germany-data' not in baked:print(f'[warn] {name}: no germany-data placeholder; skipped'); continue
        path.write_text(html,encoding='utf-8'); print(f'[write] docs/{name} (baked: {", ".join(baked)})')
    return 0
if __name__=='__main__':raise SystemExit(main())
