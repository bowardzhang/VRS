#!/usr/bin/env python3
"""Generate one self-contained secondary page per supplier dimension.

Each page (``docs/analysis-soc.html``, ``-adas``, ``-radar``, ``-power``,
``-lidar``) renders the installation-rate ("上装率") stats for one automotive
electronic component from the ``suppliers.dimensions`` block written by
``scripts/parse_suppliers.py``, plus a per-supplier column breakdown of the
top-selling brands/models using each supplier.

The pages share a single template (kept in sync by regeneration); they carry
empty ``germany-data`` / ``brand-logos`` placeholders that ``build_site.py``
bakes. Run order:  parse_germany -> parse_suppliers -> build_supplier_pages ->
build_site.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"

# key -> output filename. Titles/copy come from suppliers.dimensions at runtime.
PAGES = {
    "soc": "analysis-soc.html",
    "adas": "analysis-adas.html",
    "radar": "analysis-radar.html",
    "power": "analysis-power.html",
    "lidar": "analysis-lidar.html",
}

TEMPLATE = r"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PAGE_TITLE__ · Germany supplier installation rate</title>
<style>
  :root {
    color-scheme: light dark;
    --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
    --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --good:#006300;
  }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
    --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --good:#0ca30c;
  }}
  :root[data-theme="dark"] {
    --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --good:#0ca30c;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--page); color:var(--ink); line-height:1.5;
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif; -webkit-font-smoothing:antialiased; }
  .wrap { max-width:1040px; margin:0 auto; padding:32px 20px 80px; }
  .eyebrow { font-size:13px; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); margin:0 0 6px; }
  .back { color:var(--s1); text-decoration:none; font-size:13px; }
  .back:hover { text-decoration:underline; }
  h1 { font-size:clamp(24px,4vw,34px); margin:6px 0 6px; letter-spacing:-0.01em; }
  .sub { color:var(--ink-2); margin:0; font-size:15px; }
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:26px 0 8px; }
  @media (max-width:720px){ .kpis { grid-template-columns:repeat(2,1fr); } }
  .kpi { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:16px 18px; }
  .kpi .label { font-size:12.5px; color:var(--ink-2); margin:0 0 8px; display:flex; align-items:center; gap:6px; }
  .kpi .dot { width:9px; height:9px; border-radius:3px; display:inline-block; }
  .kpi .value { font-size:26px; font-weight:650; letter-spacing:-0.01em; }
  .kpi .foot { font-size:12px; color:var(--muted); margin-top:4px; }
  section.card { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:22px 24px; margin-top:20px; }
  section.card h2 { font-size:18px; margin:0 0 2px; letter-spacing:-0.01em; }
  section.card .note { font-size:13px; color:var(--muted); margin:2px 0 18px; }
  .bars { display:flex; flex-direction:column; gap:9px; }
  .bar-row { display:grid; grid-template-columns:120px 1fr 120px; align-items:center; gap:10px; }
  @media (max-width:560px){ .bar-row { grid-template-columns:96px 1fr 92px; } }
  .bar-name { font-size:12.5px; color:var(--ink-2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:flex; align-items:center; gap:6px; }
  .bar-track { position:relative; height:22px; background:var(--grid); border-radius:4px; overflow:hidden; }
  .bar-fill { height:100%; border-radius:4px; min-width:2px; }
  .bar-val { font-size:12px; font-variant-numeric:tabular-nums; color:var(--ink-2); text-align:right; white-space:nowrap; }
  .swatch { width:11px; height:11px; border-radius:3px; display:inline-block; flex:0 0 11px; }
  .legend { display:flex; flex-wrap:wrap; gap:14px; margin-top:16px; font-size:12.5px; color:var(--ink-2); }
  .legend span { display:inline-flex; align-items:center; gap:6px; }
  .trend-wrap { position:relative; }
  svg.trend { width:100%; height:300px; display:block; overflow:visible; }
  .trend-axis text { fill:var(--muted); font-size:11px; }
  .trend-line { fill:none; stroke-width:2; }
  .crosshair { stroke:var(--axis); stroke-width:1; stroke-dasharray:3 3; opacity:0; }
  .tip { position:absolute; pointer-events:none; opacity:0; transition:opacity .08s; background:var(--ink); color:var(--surface);
    font-size:12px; padding:8px 11px; border-radius:7px; white-space:nowrap; transform:translate(-50%,-115%); z-index:5;
    box-shadow:0 4px 14px rgba(0,0,0,.18); line-height:1.55; }
  .tip .tt-row { display:flex; align-items:center; gap:7px; justify-content:space-between; }
  .tip .tt-sw { width:9px; height:9px; border-radius:2px; display:inline-block; }
  .tip .tt-head { font-weight:600; margin-bottom:4px; }
  /* per-supplier columns */
  .cols { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:16px; }
  .col { border:1px solid var(--border); border-radius:12px; padding:14px 15px; background:var(--page); }
  .col-head { display:flex; align-items:center; gap:8px; margin-bottom:4px; }
  .col-head .nm { font-weight:650; font-size:14px; }
  .col-sub { font-size:12px; color:var(--muted); margin-bottom:11px; font-variant-numeric:tabular-nums; }
  .mrow { display:grid; grid-template-columns:18px 1fr auto; align-items:center; gap:7px; margin-bottom:7px; }
  .mrow .mk { width:18px; height:18px; border-radius:4px; overflow:hidden; display:inline-flex; align-items:center; justify-content:center; background:var(--grid); }
  .mrow .mk img { width:18px; height:18px; object-fit:contain; }
  .mrow .mk span { font-size:8.5px; font-weight:700; color:#fff; }
  .mrow .nm2 { font-size:12.5px; color:var(--ink-2); overflow:hidden; }
  .mrow .nm2 .mdl { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .mrow .mini { height:4px; border-radius:2px; margin-top:3px; }
  .mrow .cnt { font-size:11.5px; color:var(--muted); font-variant-numeric:tabular-nums; }
  .callout { background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--s4); border-radius:10px; padding:14px 18px; margin-top:20px; font-size:13.5px; color:var(--ink-2); }
  .callout b { color:var(--ink); }
  footer.site { margin-top:40px; font-size:12.5px; color:var(--muted); }
  footer.site a { color:var(--s1); }
  .toggle { position:fixed; top:14px; right:14px; background:var(--surface); border:1px solid var(--border); color:var(--ink-2); border-radius:8px; padding:6px 10px; font-size:12px; cursor:pointer; }
</style>
</head>
<body>
<button class="toggle" id="themeToggle" aria-label="Toggle theme">◐ Theme</button>
<div class="wrap">
  <header>
    <p class="eyebrow" id="eyebrow">Supplier installation rate</p>
    <a class="back" href="index.html">← Back to Germany overview</a>
    <h1 id="pageTitle">__PAGE_TITLE__</h1>
    <p class="sub" id="subtitle"></p>
  </header>

  <div class="kpis" id="kpis"></div>
  <div class="callout" id="methodology"></div>

  <section class="card">
    <h2 id="shareTitle">Supplier share</h2>
    <p class="note" id="shareNote"></p>
    <div class="bars" id="shareBars"></div>
  </section>

  <section class="card" id="trendCard" style="display:none">
    <h2 id="trendTitle">Over time</h2>
    <p class="note" id="trendNote"></p>
    <div class="trend-wrap"><svg class="trend" id="trendChart" role="img"></svg><div class="tip" id="trendTip"></div></div>
    <div class="legend" id="trendLegend"></div>
  </section>

  <section class="card">
    <h2>Top-selling models per supplier</h2>
    <p class="note">For each major supplier, the highest-volume model series that use it (registration-weighted over the whole window).</p>
    <div class="cols" id="cols"></div>
  </section>

  <footer class="site"><p id="footerText"></p></footer>
</div>

<script id="component" type="application/json">{"key":"__COMPONENT_KEY__"}</script>
<script id="germany-data" type="application/json">{}</script>
<script id="brand-logos" type="application/json">{}</script>
<script>
(function () {
  "use strict";
  var DATA = {}, LOGOS = {}, CFG = {};
  try { DATA = JSON.parse(document.getElementById("germany-data").textContent || "{}"); } catch (e) {}
  try { LOGOS = JSON.parse(document.getElementById("brand-logos").textContent || "{}"); } catch (e) {}
  try { CFG = JSON.parse(document.getElementById("component").textContent || "{}"); } catch (e) {}
  var $ = function (id) { return document.getElementById(id); };
  var fmt = function (n) { return (n == null ? "–" : n.toLocaleString("en-US")); };
  var root = document.documentElement;
  $("themeToggle").addEventListener("click", function () {
    root.setAttribute("data-theme", root.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });

  var COLORS = {
    "Qualcomm":"#2a78d6","Samsung":"#4a3aa7","NVIDIA":"#1baf7a","Renesas":"#eb6834",
    "AMD":"#e34948","NXP":"#eda100","MediaTek":"#e87ba4","Undisclosed":"#8f8d86",
    "None":"#c3c2b7","Unclassified":"#d8d7d0","No LiDAR":"#c3c2b7","Unknown":"#8f8d86",
    "Mobileye":"#00a7b5","Tesla":"#e34948","Denso":"#7b5cd6","Continental":"#2a78d6",
    "Bosch":"#e34948","Valeo":"#1baf7a","HL Klemove":"#eda100","Veoneer/Magna":"#e87ba4",
    "Infineon":"#2a78d6","STMicro":"#eb6834","onsemi":"#4a3aa7","BYD Semi":"#1baf7a","Luminar":"#eda100"
  };
  var colorFor = function (b) { return COLORS[b] || "#8f8d86"; };
  var css = function (v) { return getComputedStyle(document.body).getPropertyValue(v).trim(); };

  var S = DATA.suppliers;
  var DIM = S && S.dimensions ? S.dimensions.filter(function (d) { return d.key === CFG.key; })[0] : null;
  if (!DIM) { $("subtitle").textContent = "No data baked in yet — run parse_suppliers.py, build_supplier_pages.py, build_site.py."; return; }

  var labels = DIM.labels;
  var isLidar = CFG.key === "lidar";
  $("pageTitle").innerHTML = DIM.title + ' <span style="color:var(--muted);font-weight:500;font-size:.6em">' + DIM.cn + '</span>';
  document.title = DIM.title + " · Germany supplier installation rate";
  $("eyebrow").textContent = "Supplier installation rate · " + DIM.cn;
  $("subtitle").textContent = (DATA.country || "Germany") + " · " + labels[0] + " – " + labels[labels.length - 1] +
    " · " + DIM.blurb;

  var suppliers = DIM.share.filter(function (s) { return s.is_supplier; });
  var leader = suppliers[0];

  // ----- KPIs -----
  var kpis;
  if (isLidar) {
    var pen = DIM.penetration.pct[DIM.penetration.pct.length - 1];
    kpis = [
      { label:"LiDAR penetration", dot:css("--s2"), value:(pen<1?pen.toFixed(2):pen.toFixed(1))+"%", foot:"latest month, standard config" },
      { label:"Leading supplier", dot:colorFor(leader.brand), value:leader.brand, foot:leader.share_classified+"% of LiDAR-equipped" },
      { label:"Suppliers seen", dot:css("--s1"), value:String(suppliers.length), foot:"among equipped models" },
      { label:"Equipped registrations", dot:css("--s3"), value:fmt(DIM.classified), foot:"of "+fmt(DIM.base_total) }
    ];
  } else {
    kpis = [
      { label:"Leading supplier", dot:colorFor(leader.brand), value:leader.brand, foot:leader.share_classified+"% of classified" },
      { label:"Runner-up", dot:colorFor((suppliers[1]||{}).brand), value:(suppliers[1]||{}).brand||"–", foot:(suppliers[1]?suppliers[1].share_classified+"%":"") },
      { label:"Suppliers seen", dot:css("--s1"), value:String(suppliers.length), foot:"distinct vendors" },
      { label:"Classified coverage", dot:css("--s3"), value:Math.round(DIM.coverage_pct)+"%", foot:fmt(DIM.classified)+" of "+fmt(DIM.base_total) }
    ];
  }
  $("kpis").innerHTML = kpis.map(function (k) {
    return '<div class="kpi"><p class="label"><span class="dot" style="background:'+k.dot+'"></span>'+k.label+
      '</p><div class="value">'+k.value+'</div><div class="foot">'+k.foot+'</div></div>';
  }).join("");

  $("methodology").innerHTML = "<b>How to read this.</b> Registration volumes are official KBA figures; the supplier is an " +
    "<b>estimate</b> mapped by vehicle platform / brand software generation (\"当年新款标配\"), not measured per car — this " +
    "dimension is <b>" + DIM.confidence + "</b>. Base: " + DIM.base + " (" + fmt(DIM.base_total) + "). " +
    "Source mapping: <code>data/vehicle_specs.csv</code>.";

  // ----- supplier share bars -----
  $("shareNote").textContent = isLidar
    ? "Share of LiDAR-equipped registrations by LiDAR supplier."
    : "Registration-weighted supplier share (of classified registrations).";
  var maxShare = Math.max.apply(null, suppliers.map(function (r) { return r.share_classified || 0; }));
  $("shareBars").innerHTML = suppliers.map(function (r) {
    var w = maxShare ? (100 * (r.share_classified || 0) / maxShare) : 0;
    return '<div class="bar-row"><div class="bar-name"><span class="swatch" style="background:'+colorFor(r.brand)+'"></span>'+r.brand+
      '</div><div class="bar-track"><div class="bar-fill" style="width:'+w+'%;background:'+colorFor(r.brand)+'"></div></div>'+
      '<div class="bar-val">'+(r.share_classified||0).toFixed(1)+'%&nbsp;·&nbsp;'+fmt(r.total)+'</div></div>';
  }).join("");

  // ----- per-supplier top-model columns -----
  $("cols").innerHTML = suppliers.map(function (s) {
    var maxM = Math.max.apply(null, s.top_models.map(function (m) { return m.total; }).concat([1]));
    var rows = s.top_models.map(function (m) {
      var logo = LOGOS[m.brand];
      var mk = logo ? '<span class="mk"><img src="'+logo+'" alt=""></span>'
        : '<span class="mk" style="background:'+colorFor(s.brand)+'"><span>'+(m.brand[0]||"?")+'</span></span>';
      var w = 100 * m.total / maxM;
      return '<div class="mrow">'+mk+
        '<div class="nm2"><span class="mdl">'+m.brand+' '+m.model+'</span>'+
        '<div class="mini" style="width:'+w+'%;background:'+colorFor(s.brand)+'"></div></div>'+
        '<span class="cnt">'+fmt(m.total)+'</span></div>';
    }).join("");
    return '<div class="col"><div class="col-head"><span class="swatch" style="background:'+colorFor(s.brand)+
      '"></span><span class="nm">'+s.brand+'</span></div>'+
      '<div class="col-sub">'+(s.share_classified||0).toFixed(1)+'% · '+fmt(s.total)+' regs</div>'+rows+'</div>';
  }).join("");

  // ================= charts =================
  var SVGNS = "http://www.w3.org/2000/svg";
  function el(nm, a) { var e = document.createElementNS(SVGNS, nm); for (var k in a) e.setAttribute(k, a[k]); return e; }
  function xAt(i, nn, L, W) { return nn <= 1 ? L : L + (W * i) / (nn - 1); }

  function drawStack(svg, tip, series) {
    svg.innerHTML = ""; var box = svg.getBoundingClientRect();
    var W = box.width || 900, H = box.height || 300, padL = 34, padR = 8, padT = 12, padB = 26;
    var plotW = W-padL-padR, plotH = H-padT-padB, nn = labels.length, g = el("g", {}); svg.appendChild(g);
    [0,25,50,75,100].forEach(function (v) {
      var y = padT+plotH*(1-v/100);
      g.appendChild(el("line",{x1:padL,y1:y,x2:W-padR,y2:y,stroke:css("--grid"),"stroke-width":1}));
      var t=el("text",{x:padL-6,y:y+3,"text-anchor":"end",class:"trend-axis"}); t.textContent=v+"%"; g.appendChild(t);
    });
    var step = Math.max(1, Math.round(nn/6));
    for (var i=0;i<nn;i+=step){ var x=xAt(i,nn,padL,plotW); var tx=el("text",{x:x,y:H-8,"text-anchor":"middle",class:"trend-axis"}); tx.textContent=labels[i]; g.appendChild(tx); }
    var cum=new Array(nn).fill(0);
    series.forEach(function (s) {
      var top=[],bot=[];
      for (var i=0;i<nn;i++){ var y0=cum[i],y1=cum[i]+(s.share[i]||0);
        bot.push([xAt(i,nn,padL,plotW),padT+plotH*(1-y0/100)]); top.push([xAt(i,nn,padL,plotW),padT+plotH*(1-y1/100)]); cum[i]=y1; }
      var d="M"+top.map(function(p){return p[0]+","+p[1];}).join("L")+"L"+bot.slice().reverse().map(function(p){return p[0]+","+p[1];}).join("L")+"Z";
      g.appendChild(el("path",{d:d,fill:colorFor(s.name),"fill-opacity":0.9}));
    });
    var cross=el("line",{class:"crosshair",y1:padT,y2:padT+plotH}); g.appendChild(cross);
    var hit=el("rect",{x:padL,y:padT,width:plotW,height:plotH,fill:"transparent"}); g.appendChild(hit);
    hit.addEventListener("mousemove",function(ev){ var rect=svg.getBoundingClientRect();
      var i=Math.max(0,Math.min(nn-1,Math.round((ev.clientX-rect.left-padL)/plotW*(nn-1)))); var x=xAt(i,nn,padL,plotW);
      cross.setAttribute("x1",x); cross.setAttribute("x2",x); cross.setAttribute("opacity",1);
      var rows=series.filter(function(s){return (s.share[i]||0)>=0.5;}).map(function(s){
        return '<div class="tt-row"><span><span class="tt-sw" style="background:'+colorFor(s.name)+'"></span>'+s.name+'</span><b>'+(s.share[i]||0).toFixed(1)+'%</b></div>';}).join("");
      tip.innerHTML='<div class="tt-head">'+labels[i]+'</div>'+rows; tip.style.left=x+"px"; tip.style.top=padT+"px"; tip.style.opacity=1;
    });
    hit.addEventListener("mouseleave",function(){cross.setAttribute("opacity",0); tip.style.opacity=0;});
  }

  function drawLine(svg, tip, values, color, ymax) {
    svg.innerHTML=""; var box=svg.getBoundingClientRect();
    var W=box.width||900,H=box.height||300,padL=40,padR=8,padT=12,padB=26;
    var plotW=W-padL-padR,plotH=H-padT-padB,nn=labels.length,g=el("g",{}); svg.appendChild(g);
    ymax=ymax||Math.max.apply(null,values)||1; var ticks=4;
    for (var t=0;t<=ticks;t++){ var v=ymax*t/ticks,y=padT+plotH*(1-v/ymax);
      g.appendChild(el("line",{x1:padL,y1:y,x2:W-padR,y2:y,stroke:css("--grid"),"stroke-width":1}));
      var lt=el("text",{x:padL-6,y:y+3,"text-anchor":"end",class:"trend-axis"}); lt.textContent=(ymax<=2?v.toFixed(2):Math.round(v))+"%"; g.appendChild(lt); }
    var step=Math.max(1,Math.round(nn/6));
    for (var i=0;i<nn;i+=step){ var x=xAt(i,nn,padL,plotW); var tx=el("text",{x:x,y:H-8,"text-anchor":"middle",class:"trend-axis"}); tx.textContent=labels[i]; g.appendChild(tx); }
    var pts=values.map(function(v,i){return [xAt(i,nn,padL,plotW),padT+plotH*(1-Math.min(v,ymax)/ymax)];});
    var area="M"+pts.map(function(p){return p[0]+","+p[1];}).join("L")+"L"+pts[nn-1][0]+","+(padT+plotH)+"L"+pts[0][0]+","+(padT+plotH)+"Z";
    g.appendChild(el("path",{d:area,fill:color,"fill-opacity":0.12}));
    g.appendChild(el("path",{d:"M"+pts.map(function(p){return p[0]+","+p[1];}).join("L"),class:"trend-line",stroke:color}));
    var cross=el("line",{class:"crosshair",y1:padT,y2:padT+plotH}); g.appendChild(cross);
    var dot=el("circle",{r:4,fill:css("--surface"),stroke:color,"stroke-width":2,opacity:0}); g.appendChild(dot);
    var hit=el("rect",{x:padL,y:padT,width:plotW,height:plotH,fill:"transparent"}); g.appendChild(hit);
    hit.addEventListener("mousemove",function(ev){ var rect=svg.getBoundingClientRect();
      var i=Math.max(0,Math.min(nn-1,Math.round((ev.clientX-rect.left-padL)/plotW*(nn-1)))); var p=pts[i];
      cross.setAttribute("x1",p[0]); cross.setAttribute("x2",p[0]); cross.setAttribute("opacity",1);
      dot.setAttribute("cx",p[0]); dot.setAttribute("cy",p[1]); dot.setAttribute("opacity",1);
      tip.innerHTML='<div class="tt-head">'+labels[i]+'</div><div class="tt-row"><span>'+values[i].toFixed(ymax<=2?3:1)+'%</span></div>';
      tip.style.left=p[0]+"px"; tip.style.top=p[1]+"px"; tip.style.opacity=1;
    });
    hit.addEventListener("mouseleave",function(){cross.setAttribute("opacity",0); dot.setAttribute("opacity",0); tip.style.opacity=0;});
  }

  var stackSeries = (DIM.series || []).filter(function (s) { return s.share.some(function (v) { return v > 0; }); });
  function renderTrend() {
    if (isLidar && DIM.penetration) {
      $("trendCard").style.display = "";
      $("trendTitle").textContent = "LiDAR penetration over time";
      $("trendNote").textContent = "Share of new registrations with LiDAR (standard + optional fitment).";
      var lmax = Math.max(0.5, Math.ceil(Math.max.apply(null, DIM.penetration.pct) * 2) / 2);
      drawLine($("trendChart"), $("trendTip"), DIM.penetration.pct, css("--s2"), lmax);
    } else if (stackSeries.length) {
      $("trendCard").style.display = "";
      $("trendTitle").textContent = "Supplier mix over time";
      $("trendNote").textContent = "Monthly share of new registrations by supplier (stacked to 100%).";
      $("trendLegend").innerHTML = stackSeries.map(function (s) {
        return '<span><span class="swatch" style="background:'+colorFor(s.name)+'"></span>'+s.name+'</span>';
      }).join("");
      drawStack($("trendChart"), $("trendTip"), stackSeries);
    }
  }
  renderTrend();

  $("footerText").innerHTML = "Registrations © Kraftfahrt-Bundesamt (KBA), table FZ 10.1. " +
    "Supplier mapping is an independent estimate (<code>data/vehicle_specs.csv</code>); corrections welcome.";

  var rt;
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(renderTrend, 150); });
})();
</script>
</body>
</html>
"""

# Human-readable page titles used in <title>/<h1> before JS runs (JS overrides).
TITLES = {
    "soc": "Cockpit SoC",
    "adas": "ADAS / perception SoC",
    "radar": "Front-radar Tier-1",
    "power": "EV inverter power semiconductor",
    "lidar": "LiDAR",
}


def main() -> int:
    for key, fname in PAGES.items():
        html = TEMPLATE.replace("__COMPONENT_KEY__", key).replace("__PAGE_TITLE__", TITLES[key])
        (DOCS / fname).write_text(html, encoding="utf-8")
        print(f"[pages] wrote docs/{fname} (key={key})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
