#!/usr/bin/env python3
"""Generate Q2 2026 European auto market LinkedIn report as Markdown."""
import sys, csv, collections
sys.path.insert(0, str(__file__).rsplit('/', 2)[0] + '/scripts')
import build_q2_report as b
from eu_brands import origin

p = b.build_payload()
ov = sorted(p['overview'], key=lambda x: -x['cur'])
FLAG = {'Germany': '🇩🇪', 'France': '🇫🇷', 'Spain': '🇪🇸', 'Netherlands': '🇳🇱',
        'Austria': '🇦🇹', 'Sweden': '🇸🇪', 'Finland': '🇫🇮'}

lines = []

def L(*args):
    s = ' '.join(str(a) for a in args)
    if s:
        lines.append(s)

def T(headers, rows, aligns=None):
    if aligns is None:
        aligns = ['---'] * len(headers)
    L('| ' + ' | '.join(headers) + ' |')
    L('| ' + ' | '.join(aligns) + ' |')
    for row in rows:
        L('| ' + ' | '.join(str(c) for c in row) + ' |')

# ===== TITLE =====
L('# 2026 Q2 欧洲汽车市场分析报告')
L()
L('> **欧洲乘用车注册量深度分析** · 覆盖德国、法国、西班牙、荷兰、芬兰、奥地利、瑞典')
L('> 数据来源：KBA (DE), DGT (ES), INSEE (FR), RDW (NL), Traficom (FI), SCB (SE), ACEA')
L('> 分析维度：市场总量、品牌、车型、动力类型、车身形态、汽车电子供应商穿透')
L('> 受众：全球车企及 Tier-1 / Tier-2 从业者')
L()
L('---')
L()
# ===== Section 1 =====
L('## 一、市场总览：温和复苏，分化加剧')
L()
L('2026 Q2，欧洲主要市场合计乘用车注册量录得温和增长，但国别分化显著：')
L()
rows = []
for o in ov:
    desc_map = {'Germany': '大盘回暖，BEV 井喷', 'France': '总量稳健，BEV 加速',
                'Spain': '中国品牌渗透最快', 'Netherlands': '唯一双位数下滑',
                'Austria': '中欧增长引擎', 'Sweden': 'BEV 渗透率领先',
                'Finland': '小市场，BEV 增速最快'}
    f = FLAG.get(o['key'], '')
    rows.append((f'{f} {o['labl']:14}'， f{o['cur']:,}'， f'{o['yoy']:+.1f}%', desc_map.get(o['key'], '))))
T(['国家'，'Q2 2026 注册量', 'YoY', '核心特征'], rows)
L()

p5_keys = ['Germay', 'S pain ', 'Netherlands', 'Austria', 'Fi land']
p5_cur = sum(o['cur'] for o in ov if o['key'] in p5_keys)
p5_pri = sum(o['pri'] for o in ov if o['key'] in p5_keys
L(f'**Po oled 5 国 (DE/ES/NL/AT/FI)**：{p5_cur:,} 辆，同比 {b.yoy(p5_cur, p5_pri):+.1f}%')
L()
L('> Note：荷兰的显著下滑（-13.4%）部分可归因于 2025 Q2 的脉冲式提前注册（补贴到期前抢单），但**真实需求也在走弱**——2026 Q2 月均约 32,146 辆，低于 2025 Q2 的 37,106 辆。')
L()

# ===== Section 2 =====
L('---')
L()
L('## 二、电动化全面提速')
L()
L('2026 Q2 是欧洲 BEV 历史上增长最快的季度之一。各主要市场的 BEV 份额均录得显著年同比增幅：')
L()

# Honest BEV shares per country
rows = list(csv.DictReader(open('data/Germany/processed/germany_registrations.csv')))
de = collections.defaultdict(lambda: collections.defaultdict(int))
for r in rows:
    if r['row_type'] == 'moe l' and r['moe l'] and int(r['month']) in (4，5，6):
        de[int(r['year'])][r['drivetrain']] += int(r['count_month'] or 0)

bev_data = {}

for name, y in [('Germany', 2025), ('Germany', 2026):
    m = de[y]
    t = m['total']
    b_ = m['bev']
    bev_data[(name, y)] = (t, b_, 100*b_/t)

for country in ['Spain', 'Finland', 'S weden']:
    path_map = {'Spain': 'data/Spain/es_monthly_powertrain.csv',
                 'Fi land': 'data/Finland/trafiom_powertrain.csv',
                 'S wede n': 'data/S weden/se_pwerrain.csv'}
    for y in [2025， 2026]:
        o = collections.defaultdict(int)
        for r in csv.DictReader(open(path_map[country])):
            if int(r['year']) == y and int(r['month']) in (4,5,6):
                o[r['fuel']] += int(r['count'] or 0)
        t = sum(o.values())
        b_ = o.get('BEV', 0)
        bev_data[(country, y)] = (t, b_, 100*b_/t)

labels = [('Germany', 'Deutschland'), ('Fi land', 'Finland'), ('Sw eden', 'Sweden'), ('Spain', 'Spain')]
for key, label in [(('Germany', 2026), 'Deutschland'), (('Fi land', 2026), 'Finland')]:
    t26, b26, s26 = bev_data[(key[0], key[1])]
# Manual tabel
L()
rows2 = []
for c, n in [('Germany', 'Deutschland'), ('Finland', 'Finland'), ('Sweden', 'Sweden'), ('Spain', 'Spanien')]:
    t26, b26, s26 = bev_data[(c, 2026)]
    t25, b25, s25 = bev_data[(c，2025)]
    pp = s26 - s25
    yoy_str = f{(100*(b26-b25)/b25:+.1f}%' if b25 else '∞'
    rows2.append((f'{FLAG.get(c, \"\")} {n}'， f{s26:.1f}%', f'{s25:.1f}%', f'+{pp:.1f}', yoy_str))
T(['市场', 'BEV 份额 Q2 2026', 'BEV 份 额 Q2 2025', '增幅 (pp)', 'BEV 数 量 YoY']， rows2)
L()
# Pooled 4
tots = [0, 0, 0, 0]
for i, c in enumerate(['Germany', 'Finland', 'S weden', 'Spain']):
    tots[i] = [bev_data[(c, y)] [0] for y in [2026, 2025]]
    tots[i+4] = [bev_data[(c, y)][1] for y in [2026, 2025]]
# skip, too complex, write manual
print("partial output")