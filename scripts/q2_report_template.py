#!/usr/bin/env python3
"""HTML template for the Q2 European market report (see build_q2_report.py).

Kept separate so the data builder stays readable. ``__DATA__`` is replaced with
the embedded JSON payload at build time; the page is otherwise fully static and
self-contained (no fetch / external assets), matching the other analysis pages.
"""

PAGE = r"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>2026 Q2 · European major-market auto analysis</title>
<style>
  :root {
    color-scheme: light dark;
    --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
    --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4;
    --good:#0a7a34; --bad:#c23a34;
  }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
    --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181;
    --good:#22b055; --bad:#e5675f;
  }}
  :root[data-theme="dark"] {
    --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181;
    --good:#22b055; --bad:#e5675f;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--page); color:var(--ink); line-height:1.5;
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif; -webkit-font-smoothing:antialiased; }
  .wrap { max-width:1080px; margin:0 auto; padding:32px 20px 90px; }
  .eyebrow { font-size:13px; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); margin:0 0 6px; }
  .back { color:var(--s1); text-decoration:none; font-size:13px; }
  .back:hover { text-decoration:underline; }
  h1 { font-size:clamp(24px,4vw,34px); margin:6px 0 6px; letter-spacing:-0.01em; }
  h1 .cn { color:var(--muted); font-weight:500; font-size:.62em; }
  .sub { color:var(--ink-2); margin:0; font-size:15px; }
  .callout { background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--s4);
    border-radius:10px; padding:13px 17px; margin-top:18px; font-size:13px; color:var(--ink-2); }
  .callout b { color:var(--ink); }
  .ov { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px; margin:24px 0 8px; }
  .ovcard { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }
  .ovcard .c { font-size:20px; }
  .ovcard .nm { font-size:12.5px; color:var(--ink-2); margin:2px 0 8px; }
  .ovcard .v { font-size:22px; font-weight:650; letter-spacing:-0.01em; font-variant-numeric:tabular-nums; }
  .ovcard .y { font-size:12.5px; margin-top:3px; font-variant-numeric:tabular-nums; }
  .up { color:var(--good); } .dn { color:var(--bad); } .flat { color:var(--muted); }
  section.card { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:22px 24px; margin-top:22px; }
  section.card > h2 { font-size:18px; margin:0 0 3px; letter-spacing:-0.01em; }
  section.card > h2 .cn { color:var(--muted); font-weight:500; font-size:.62em; }
  section.card .note { font-size:12.5px; color:var(--muted); margin:2px 0 16px; }
  .pills { display:flex; flex-wrap:wrap; gap:7px; margin-bottom:16px; }
  .pill { border:1px solid var(--border); background:var(--page); color:var(--ink-2); border-radius:999px;
    padding:5px 13px; font-size:12.5px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
  .pill:hover { border-color:var(--axis); }
  .pill[aria-pressed="true"] { background:var(--s1); border-color:var(--s1); color:#fff; }
  .tbl-scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  table.rank { border-collapse:collapse; width:100%; font-size:13px; min-width:440px; }
  table.rank th, table.rank td { padding:8px 10px; text-align:right; white-space:nowrap; }
  table.rank th.l, table.rank td.l { text-align:left; }
  table.rank thead th { color:var(--muted); font-weight:600; font-size:12px; border-bottom:1px solid var(--border); }
  table.rank tbody td { font-variant-numeric:tabular-nums; }
  table.rank tbody tr + tr td { border-top:1px solid var(--grid); }
  table.rank td.rk { color:var(--muted); width:26px; }
  table.rank .barcell { position:relative; }
  table.rank .bar { display:block; height:3px; border-radius:2px; margin-top:4px; background:var(--s1); opacity:.85; }
  .yoy { font-variant-numeric:tabular-nums; }
  .subgrid { display:grid; grid-template-columns:1fr; gap:16px; }
  .subcard { border:1px solid var(--border); border-radius:12px; padding:14px 16px; background:var(--page); }
  .subcard h3 { font-size:14px; margin:0 0 2px; } .subcard h3 .cn { color:var(--muted); font-weight:500; font-size:.7em; }
  .subcard .cov { font-size:11.5px; color:var(--muted); margin:0 0 10px; }
  .subcard table.rank { min-width:0; }
  .subcard table.rank th, .subcard table.rank td { padding:7px 6px; }
  .na { text-align:center; padding:26px 16px; color:var(--muted); font-size:13.5px; }
  footer.site { margin-top:42px; font-size:12.5px; color:var(--muted); }
  footer.site a { color:var(--s1); }
  .toggle { position:fixed; top:14px; right:14px; background:var(--surface); border:1px solid var(--border);
    color:var(--ink-2); border-radius:8px; padding:6px 10px; font-size:12px; cursor:pointer; }
</style>
</head>
<body>
<button class="toggle" id="themeToggle" aria-label="Toggle theme">◐ Theme</button>
<div class="wrap">
  <header>
    <p class="eyebrow">Quarterly market analysis</p>
    <a class="back" href="index.html">← Back to overview</a>
    <h1 id="pageTitle"></h1>
    <p class="sub" id="subtitle"></p>
  </header>

  <div class="callout" id="coverage"></div>

  <div class="ov" id="overview"></div>
  <p class="note" id="ovNote" style="font-size:12px;color:var(--muted);margin:4px 0 0"></p>

  <section class="card" id="sec-brands"></section>
  <section class="card" id="sec-models"></section>
  <section class="card" id="sec-origin"></section>
  <section class="card" id="sec-powertrain"></section>
  <section class="card" id="sec-bodytype"></section>
  <section class="card" id="sec-suppliers"></section>

  <footer class="site"><p id="footerText"></p></footer>
</div>

<script id="q2-data" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var D = {};
  try { D = JSON.parse(document.getElementById("q2-data").textContent || "{}"); } catch (e) {}
  var $ = function (id) { return document.getElementById(id); };
  var root = document.documentElement;
  $("themeToggle").addEventListener("click", function () {
    root.setAttribute("data-theme", root.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });
  var fmt = function (n) { return (n == null ? "–" : Number(n).toLocaleString("en-US")); };
  var flag = function (k) { return (D.flags || {})[k] || ""; };
  var label = function (k) { return (D.labels || {})[k] || k; };

  function yoyHtml(v) {
    if (v == null) return '<span class="flat">n/a</span>';
    var cls = v > 0.05 ? "up" : (v < -0.05 ? "dn" : "flat");
    var s = (v > 0 ? "+" : "") + v.toFixed(1) + "%";
    return '<span class="' + cls + '">' + s + '</span>';
  }
  function ppHtml(v) {
    if (v == null) return '<span class="flat">new</span>';
    var cls = v > 0.05 ? "up" : (v < -0.05 ? "dn" : "flat");
    return '<span class="' + cls + '">' + (v > 0 ? "+" : "") + v.toFixed(1) + ' pp</span>';
  }

  // ---------- header ----------
  var P = D.period || {};
  $("pageTitle").innerHTML = P.cur + " · European major-market auto analysis " +
    '<span class="cn">欧洲主要国家汽车市场分析</span>';
  document.title = P.cur + " · European major-market auto analysis";
  $("subtitle").textContent = "New passenger-car registrations, " + P.cur + " (" + P.note +
    ") with year-on-year change vs " + P.prior + ".";
  $("coverage").innerHTML = "<b>Coverage.</b> " + (D.coverage_note || "") +
    " Everything below is a real slice of the same national registration feeds used across this site.";

  // ---------- overview ----------
  $("overview").innerHTML = (D.overview || []).map(function (o) {
    return '<div class="ovcard"><div class="c">' + o.flag + '</div>' +
      '<div class="nm">' + o.label + '</div>' +
      '<div class="v">' + fmt(o.cur) + '</div>' +
      '<div class="y">YoY ' + yoyHtml(o.yoy) + '</div></div>';
  }).join("");
  $("ovNote").textContent = "Q2 2026 new registrations by country, largest first. " +
    "UK not shown — its quarterly data still ends Q1 2026.";

  // ---------- generic ranked-dimension section (count + YoY) ----------
  function rankSection(secId, block, opts) {
    opts = opts || {};
    var sec = $(secId);
    var state = { country: block.countries.indexOf("Total") >= 0 ? "Total" : block.countries[0] };
    sec.innerHTML =
      '<h2>' + opts.title + ' <span class="cn">' + opts.cn + '</span></h2>' +
      '<p class="note">' + opts.note + '</p>' +
      '<div class="pills"></div><div class="tbl-scroll"><table class="rank" id="' + secId + '-t"></table></div>';
    var pills = sec.querySelector(".pills");
    pills.innerHTML = block.countries.map(function (c) {
      return '<button class="pill" data-c="' + c + '">' + flag(c) + ' ' + label(c) + '</button>';
    }).join("");
    function draw() {
      Array.prototype.forEach.call(pills.children, function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-c") === state.country);
      });
      var rows = block.data[state.country] || [];
      var max = rows.reduce(function (m, r) { return Math.max(m, r.cur); }, 1);
      var head = '<thead><tr><th class="l">#</th><th class="l">' + opts.col + '</th>' +
        '<th>' + P.cur + '</th><th>' + P.prior + '</th><th>YoY</th></tr></thead>';
      var body = rows.map(function (r, i) {
        return '<tr><td class="rk">' + (i + 1) + '</td>' +
          '<td class="l barcell">' + r.name +
            '<span class="bar" style="width:' + (100 * r.cur / max) + '%"></span></td>' +
          '<td>' + fmt(r.cur) + '</td><td>' + fmt(r.prior) + '</td>' +
          '<td class="yoy">' + yoyHtml(r.yoy) + '</td></tr>';
      }).join("");
      $(secId + "-t").innerHTML = head + "<tbody>" + body + "</tbody>";
    }
    pills.addEventListener("click", function (e) {
      var b = e.target.closest(".pill"); if (!b) return;
      state.country = b.getAttribute("data-c"); draw();
    });
    draw();
  }

  rankSection("sec-brands", D.brands, {
    title: "Top-10 brands", cn: "品牌 Top10", col: "Brand",
    note: "Ranked by Q2 2026 registrations. " + D.brands.countries.filter(function(c){return c!=="Total";}).length +
      " countries; Total pools them."
  });
  rankSection("sec-models", D.models, {
    title: "Top-10 models", cn: "车型 Top10", col: "Model",
    note: "Only Germany and Spain publish monthly model-level data; Total is DE+ES pooled by normalised model name."
  });
  rankSection("sec-origin", D.origin, {
    title: "Top-8 brand origin countries", cn: "厂商所属国 Top8", col: "Origin",
    note: "Registrations grouped by each marque's country of origin (the car's nationality, not the owner group)."
  });

  // ---------- powertrain (share + count + YoY) ----------
  (function () {
    var block = D.powertrain, secId = "sec-powertrain";
    var sec = $(secId);
    var state = { country: "Total" };
    sec.innerHTML = '<h2>Powertrain mix <span class="cn">动力类型分布</span></h2>' +
      '<p class="note">Share of Q2 registrations by powertrain, with the YoY change in volume. ' +
      'Bucket granularity differs by national feed (e.g. Germany reports no separate HEV; Spain folds hybrids into “Other”).</p>' +
      '<div class="pills"></div><div class="tbl-scroll"><table class="rank" id="' + secId + '-t"></table></div>';
    var pills = sec.querySelector(".pills");
    pills.innerHTML = block.countries.map(function (c) {
      return '<button class="pill" data-c="' + c + '">' + flag(c) + ' ' + label(c) + '</button>';
    }).join("");
    var COL = { BEV:"#1baf7a", PHEV:"#2a78d6", HEV:"#7b5cd6", Petrol:"#eb6834", Diesel:"#8f8d86", Other:"#c3c2b7" };
    function draw() {
      Array.prototype.forEach.call(pills.children, function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-c") === state.country);
      });
      var rows = block.data[state.country] || [];
      var head = '<thead><tr><th class="l">Powertrain</th><th>' + P.cur + ' share</th>' +
        '<th>' + P.cur + '</th><th>' + P.prior + ' share</th><th>YoY vol</th></tr></thead>';
      var body = rows.map(function (r) {
        return '<tr><td class="l barcell"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' +
            (COL[r.name] || "#8f8d86") + ';margin-right:7px"></span>' + r.name +
            '<span class="bar" style="width:' + r.share_cur + '%;background:' + (COL[r.name] || "#8f8d86") + '"></span></td>' +
          '<td><b>' + r.share_cur.toFixed(1) + '%</b></td>' +
          '<td>' + fmt(r.cur) + '</td>' +
          '<td>' + r.share_prior.toFixed(1) + '%</td>' +
          '<td class="yoy">' + yoyHtml(r.yoy) + '</td></tr>';
      }).join("");
      $(secId + "-t").innerHTML = head + "<tbody>" + body + "</tbody>";
    }
    pills.addEventListener("click", function (e) {
      var b = e.target.closest(".pill"); if (!b) return;
      state.country = b.getAttribute("data-c"); draw();
    });
    draw();
  })();

  // ---------- body type (native taxonomy per country) ----------
  (function () {
    var block = D.body, secId = "sec-bodytype";
    var sec = $(secId);
    if (!block || !block.countries || !block.countries.length) { sec.style.display = "none"; return; }
    var state = { country: block.countries[0] };
    sec.innerHTML = '<h2>Body type <span class="cn">车身类型分布</span></h2>' +
      '<p class="note">Share of Q2 registrations by body type, with the YoY change in volume. ' +
      'Taxonomies differ by source and are <b>not pooled</b>: Germany uses KBA size-segments ' +
      '(includes an SUV class); the Netherlands uses RDW body codes (no distinct SUV — filed under estate/MPV).</p>' +
      '<div class="pills"></div><div class="tbl-scroll"><table class="rank" id="' + secId + '-t"></table></div>';
    var pills = sec.querySelector(".pills");
    pills.innerHTML = block.countries.map(function (c) {
      return '<button class="pill" data-c="' + c + '">' + flag(c) + ' ' + label(c) + '</button>';
    }).join("");
    var COL = { "Sedan & hatch":"#2a78d6", "SUV":"#1baf7a", "MPV & van":"#eda100",
      "Sports":"#e87ba4", "Other":"#c3c2b7", "Hatchback":"#2a78d6", "Sedan":"#4a3aa7",
      "Estate":"#1baf7a", "MPV":"#eda100", "Coupé":"#e87ba4", "Convertible":"#eb6834" };
    function draw() {
      Array.prototype.forEach.call(pills.children, function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-c") === state.country);
      });
      var rows = block.data[state.country] || [];
      var head = '<thead><tr><th class="l">Body type</th><th>' + P.cur + ' share</th>' +
        '<th>' + P.cur + '</th><th>' + P.prior + ' share</th><th>YoY vol</th></tr></thead>';
      var body = rows.map(function (r) {
        var col = COL[r.name] || "#8f8d86";
        return '<tr><td class="l barcell"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' +
            col + ';margin-right:7px"></span>' + r.name +
            '<span class="bar" style="width:' + r.share_cur + '%;background:' + col + '"></span></td>' +
          '<td><b>' + r.share_cur.toFixed(1) + '%</b></td><td>' + fmt(r.cur) + '</td>' +
          '<td>' + r.share_prior.toFixed(1) + '%</td>' +
          '<td class="yoy">' + yoyHtml(r.yoy) + '</td></tr>';
      }).join("");
      $(secId + "-t").innerHTML = head + "<tbody>" + body + "</tbody>";
    }
    pills.addEventListener("click", function (e) {
      var b = e.target.closest(".pill"); if (!b) return;
      state.country = b.getAttribute("data-c"); draw();
    });
    draw();
  })();

  // ---------- suppliers (installation rate + YoY pp) ----------
  (function () {
    var block = D.suppliers, secId = "sec-suppliers";
    var sec = $(secId);
    var COL = { Qualcomm:"#2a78d6", Samsung:"#4a3aa7", NVIDIA:"#1baf7a", Renesas:"#eb6834",
      AMD:"#e34948", NXP:"#eda100", MediaTek:"#e87ba4", Undisclosed:"#8f8d86", None:"#c3c2b7",
      Mobileye:"#00a7b5", Tesla:"#e34948", Denso:"#7b5cd6", Continental:"#2a78d6", Bosch:"#e34948",
      Valeo:"#1baf7a", "HL Klemove":"#eda100", "Veoneer/Magna":"#e87ba4" };
    var state = { country: "Total" };
    sec.innerHTML = '<h2>Supplier installation rate <span class="cn">汽车供应商上装率</span></h2>' +
      '<p class="note">Estimated supplier share of classified registrations per component (座舱/智驾/雷达), ' +
      'Q2 2026 with the YoY change in percentage points. Estimate from <code>data/vehicle_specs.csv</code>; ' +
      'Germany, Spain, Finland &amp; Netherlands (the monthly model feeds). LiDAR omitted — fitment is ≈0% in these markets.</p>' +
      '<div class="pills"></div><div class="subgrid" id="' + secId + '-grid"></div>';
    var pills = sec.querySelector(".pills");
    pills.innerHTML = block.countries.map(function (c) {
      return '<button class="pill" data-c="' + c + '">' + flag(c) + ' ' + label(c) + '</button>';
    }).join("");
    function draw() {
      Array.prototype.forEach.call(pills.children, function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-c") === state.country);
      });
      var dims = block.data[state.country] || [];
      $(secId + "-grid").innerHTML = dims.map(function (d) {
        var rows = d.rows.slice(0, 6);
        var max = rows.reduce(function (m, r) { return Math.max(m, r.share_cur); }, 1);
        var body = rows.map(function (r) {
          var col = COL[r.name] || "#8f8d86";
          return '<tr><td class="l barcell"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' +
              col + ';margin-right:7px"></span>' + r.name +
              '<span class="bar" style="width:' + (100 * r.share_cur / max) + '%;background:' + col + '"></span></td>' +
            '<td><b>' + r.share_cur.toFixed(1) + '%</b></td>' +
            '<td class="yoy">' + ppHtml(r.delta) + '</td></tr>';
        }).join("");
        return '<div class="subcard"><h3>' + d.title + ' <span class="cn">' + d.cn + '</span></h3>' +
          '<p class="cov">' + Math.round(d.coverage) + '% classified coverage</p>' +
          '<div class="tbl-scroll"><table class="rank"><thead><tr><th class="l">Supplier</th>' +
          '<th>' + P.cur + '</th><th>vs ' + P.prior + '</th></tr></thead><tbody>' + body + '</tbody></table></div></div>';
      }).join("");
    }
    pills.addEventListener("click", function (e) {
      var b = e.target.closest(".pill"); if (!b) return;
      state.country = b.getAttribute("data-c"); draw();
    });
    draw();
  })();

  $("footerText").innerHTML = "Sources: KBA (DE), DGT (ES), Traficom (FI), RDW (NL), Statistik Austria (AT), " +
    "SCB/Trafikanalys (SE), SDES (FR). Supplier mapping is an independent estimate " +
    "(<code>data/vehicle_specs.csv</code>). Q2 2026 = Apr–Jun; YoY vs Q2 2025.";
})();
</script>
</body>
</html>
"""
