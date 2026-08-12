#!/usr/bin/env python3
"""Render HTML reports from mac-resource-monitor CSV logs.

CLI: python3 report.py [--days N] [--out report.html]  -> static self-contained file
Library: server.py imports render_body()/STYLE/JS to serve a live dashboard.
"""
import argparse
import csv
import glob
import html
import json
import os
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.environ.get("RESMON_LOG_DIR") or os.path.join(BASE, "logs")

# Lucide icons (lucide.dev, ISC license) as inline SVG — no CDN needed
ICONS = {
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
           '<path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/>'
           '<path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "memory": '<path d="M6 19v-3"/><path d="M10 19v-3"/><path d="M14 19v-3"/><path d="M18 19v-3"/>'
              '<path d="M8 11V9"/><path d="M16 11V9"/><path d="M12 11V9"/><path d="M2 15h20"/>'
              '<path d="M2 7a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v1.1a2 2 0 0 0 0 3.837V17a2 2 0 0 1'
              '-2 2H4a2 2 0 0 1-2-2v-5.1a2 2 0 0 0 0-3.837Z"/>',
    "harddrive": '<line x1="22" x2="2" y1="12" y2="12"/>'
                 '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89'
                 'A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
                 '<line x1="6" x2="6.01" y1="16" y2="16"/><line x1="10" x2="10.01" y1="16" y2="16"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "flame": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6'
             ' .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3'
             'a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/>'
                '<path d="M3 12A9 3 0 0 0 21 12"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
               '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/>'
           '<path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/>'
           '<path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "table": '<path d="M12 3v18"/><rect x="3" y="3" width="18" height="18" rx="2"/>'
             '<path d="M3 9h18"/><path d="M3 15h18"/>',
    "chevron": '<path d="m9 18 6-6-6-6"/>',
}


def icon(name, size=16, cls=""):
    return (f'<svg class="ic{" " + cls if cls else ""}" width="{size}" height="{size}" '
            f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def chead(ic, title):
    return f'<div class="chead">{icon(ic)}<h2>{html.escape(title)}</h2></div>'


def theme_button():
    return ('<button id="themeToggle" title="สลับโหมดสว่าง/มืด" aria-label="สลับโหมดสว่าง/มืด">'
            f'{icon("sun", 16, "icon-sun")}{icon("moon", 16, "icon-moon")}</button>')

# Reference dataviz palette (validated light/dark categorical slots 1-2)
STYLE = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --tint: rgba(11,11,11,0.045); --glass: rgba(249,249,247,0.82);
  --s1: #2a78d6; --s2: #eb6834;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --tint: rgba(255,255,255,0.06); --glass: rgba(13,13,13,0.78);
    --s1: #3987e5; --s2: #d95926;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19;
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --tint: rgba(255,255,255,0.06); --glass: rgba(13,13,13,0.78);
  --s1: #3987e5; --s2: #d95926;
}
#themeToggle .icon-sun { display: none; }
#themeToggle .icon-moon { display: block; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) #themeToggle .icon-sun { display: block; }
  :root:not([data-theme="light"]) #themeToggle .icon-moon { display: none; }
}
:root[data-theme="dark"] #themeToggle .icon-sun { display: block; }
:root[data-theme="dark"] #themeToggle .icon-moon { display: none; }
:root[data-theme="light"] #themeToggle .icon-sun { display: none; }
:root[data-theme="light"] #themeToggle .icon-moon { display: block; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
       font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
       -webkit-font-smoothing: antialiased; }
.ic { flex: none; display: block; }
.header { position: sticky; top: 0; z-index: 10; background: var(--glass);
          backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
          border-bottom: 1px solid var(--border); }
.header-in { max-width: 1040px; margin: 0 auto; padding: 10px 16px;
             display: flex; justify-content: space-between; align-items: center;
             gap: 12px; flex-wrap: wrap; }
.brand { display: flex; align-items: center; gap: 10px;
         font-size: 15px; font-weight: 650; letter-spacing: -0.01em; }
.brand .mark { width: 30px; height: 30px; border-radius: 9px; background: var(--s1);
               color: #fff; display: grid; place-items: center; flex: none; }
.controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.seg { display: inline-flex; background: var(--tint); border: 1px solid var(--border);
       border-radius: 10px; padding: 3px; gap: 2px; }
.seg button { border: 0; background: transparent; color: var(--ink-2); font: inherit;
              font-size: 12.5px; padding: 5px 10px; border-radius: 7px;
              cursor: pointer; white-space: nowrap; }
.seg button:hover { color: var(--ink); }
.seg button.on { background: var(--surface); color: var(--ink); font-weight: 600;
                 box-shadow: 0 1px 2px rgba(0,0,0,.12); }
select { appearance: none; -webkit-appearance: none; background: var(--surface);
         color: var(--ink); border: 1px solid var(--border); border-radius: 10px;
         padding: 6px 26px 6px 12px; font: inherit; font-size: 13px; cursor: pointer;
         background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="%23898781" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>');
         background-repeat: no-repeat; background-position: right 9px center; }
#themeToggle { width: 34px; height: 34px; display: grid; place-items: center;
               background: var(--surface); border: 1px solid var(--border);
               border-radius: 10px; color: var(--ink-2); cursor: pointer; padding: 0; }
#themeToggle:hover { color: var(--ink); }
button:focus-visible, select:focus-visible, summary:focus-visible {
  outline: 2px solid var(--s1); outline-offset: 2px; }
.page { max-width: 1040px; margin: 0 auto; padding: 20px 16px 48px; }
.sub { color: var(--ink-2); margin: 0 0 16px; font-size: 13px; }
.muted { color: var(--muted); }
#status { display: flex; align-items: center; gap: 6px; font-size: 12px;
          color: var(--muted); margin: 0 0 12px; font-variant-numeric: tabular-nums; }
@keyframes spin { to { transform: rotate(360deg); } }
#status.loading .sicon { animation: spin 1s linear infinite; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
         gap: 12px; margin-bottom: 16px; }
.tile { display: flex; align-items: center; gap: 12px; background: var(--surface);
        border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.tico { width: 38px; height: 38px; border-radius: 10px; background: var(--tint);
        color: var(--ink-2); display: grid; place-items: center; flex: none; }
.tile .v { font-size: 22px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.2; }
.tile .l { font-size: 12px; color: var(--ink-2); margin-top: 1px; }
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: 14px; padding: 18px; margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.chead { display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
         color: var(--muted); }
.chead h2 { font-size: 14px; font-weight: 600; margin: 0; color: var(--ink); }
.chart-wrap { position: relative; }
.chart-wrap svg, .card > svg { width: 100%; height: auto; display: block; }
.tick { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums;
        font-family: system-ui, -apple-system, sans-serif; }
.dlabel { fill: var(--ink-2); font-size: 12px;
          font-family: system-ui, -apple-system, sans-serif; }
.legend { display: flex; gap: 16px; font-size: 12px; color: var(--ink-2);
          margin-bottom: 8px; }
.legend i, .tip i { display: inline-block; width: 8px; height: 8px;
                    border-radius: 3px; margin-right: 6px; }
.tip { position: absolute; pointer-events: none; background: var(--surface);
       border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px;
       font-size: 12px; box-shadow: 0 6px 20px rgba(0,0,0,.16); z-index: 5;
       white-space: nowrap; }
.tip .t { color: var(--ink-2); margin-bottom: 4px; }
.tip b { font-variant-numeric: tabular-nums; }
details { margin-top: 10px; font-size: 12px; }
summary { display: flex; align-items: center; gap: 6px; color: var(--ink-2);
          cursor: pointer; list-style: none; width: fit-content;
          padding: 4px 8px; border-radius: 8px; }
summary:hover { background: var(--tint); color: var(--ink); }
summary::-webkit-details-marker { display: none; }
summary .chev { transition: transform .15s ease; }
details[open] summary .chev { transform: rotate(90deg); }
.tbl-scroll { overflow-x: auto; max-height: 320px; overflow-y: auto; margin-top: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
th { text-align: left; color: var(--ink-2); font-weight: 600;
     border-bottom: 1px solid var(--axis); padding: 7px 12px 7px 0;
     position: sticky; top: 0; background: var(--surface); }
td { border-bottom: 1px solid var(--grid); padding: 6px 12px 6px 0;
     font-variant-numeric: tabular-nums; }
tr:hover td { background: var(--tint); }
td.cmd { font-variant-numeric: normal; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 800px) { .grid2 { grid-template-columns: 1fr; } }
"""

JS = """
function bindTheme() {
  var root = document.documentElement;
  function apply(t) {
    if (t) root.setAttribute('data-theme', t);
    else root.removeAttribute('data-theme');
  }
  try { apply(localStorage.getItem('resmon-theme')); } catch (e) {}
  var btn = document.getElementById('themeToggle');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var eff = root.getAttribute('data-theme') ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var next = eff === 'dark' ? 'light' : 'dark';
    apply(next);
    try { localStorage.setItem('resmon-theme', next); } catch (e) {}
  });
}

function bindCharts() {
  document.querySelectorAll('.chart-wrap').forEach(function (w) {
    var tip = w.querySelector('.tip');
    var svg = w.querySelector('svg');
    var metaEl = w.querySelector('script.meta');

    function place(px, py, htmlStr) {
      tip.innerHTML = htmlStr;
      tip.style.display = 'block';
      var wr = w.getBoundingClientRect();
      var x = px + 12, y = py - 10;
      if (x + tip.offsetWidth > wr.width) x = px - tip.offsetWidth - 12;
      if (y < 0) y = 0;
      tip.style.left = x + 'px';
      tip.style.top = y + 'px';
    }

    if (metaEl) {  // line chart: crosshair + shared tooltip
      var m = JSON.parse(metaEl.textContent);
      var cross = svg.querySelector('.crosshair');
      var dots = svg.querySelectorAll('.hoverdot');
      var hide = function () {
        tip.style.display = 'none';
        cross.style.display = 'none';
        dots.forEach(function (d) { d.style.display = 'none'; });
      };
      svg.addEventListener('mousemove', function (e) {
        var r = svg.getBoundingClientRect();
        var sx = r.width / m.w;
        var x = (e.clientX - r.left) / sx;
        if (x < m.left - 4 || x > m.right + 4) return hide();
        var best = 0, bd = 1e9;
        for (var i = 0; i < m.xs.length; i++) {
          var d = Math.abs(m.xs[i] - x);
          if (d < bd) { bd = d; best = i; }
        }
        cross.style.display = '';
        cross.setAttribute('x1', m.xs[best]);
        cross.setAttribute('x2', m.xs[best]);
        var rows = '<div class="t">' + m.times[best] + '</div>';
        m.series.forEach(function (s, si) {
          dots[si].style.display = '';
          dots[si].setAttribute('cx', m.xs[best]);
          dots[si].setAttribute('cy', s.ys[best]);
          rows += '<div><i style="background:var(--' + s.var + ')"></i>' +
                  s.name + ': <b>' + s.vals[best].toLocaleString() + m.unit + '</b></div>';
        });
        place(m.xs[best] * sx, e.clientY - r.top, rows);
      });
      svg.addEventListener('mouseleave', hide);
    }

    svg.querySelectorAll('.bar').forEach(function (b) {
      b.addEventListener('mousemove', function (e) {
        var r = w.getBoundingClientRect();
        place(e.clientX - r.left, e.clientY - r.top,
              '<div class="t">' + b.dataset.tip + '</div>');
      });
      b.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
    });
  });
}
"""


def load_sys(days):
    rows = []
    cutoff = datetime.now() - timedelta(days=days)
    for path in sorted(glob.glob(os.path.join(LOG_DIR, "sys-*.csv"))):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    ts = datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%S")
                    if ts < cutoff:
                        continue
                    rows.append({
                        "ts": ts,
                        "cpu": float(r["cpu_pct"]),
                        "mem": float(r["mem_used_mb"]),
                        "swap": float(r["swap_used_mb"]),
                        "load1": float(r["load_1m"]),
                    })
                except (ValueError, KeyError):
                    continue
    rows.sort(key=lambda r: r["ts"])
    return rows


def load_proc(days):
    stats = {"cpu": {}, "mem": {}}
    n_samples = {"cpu": set(), "mem": set()}
    cutoff = datetime.now() - timedelta(days=days)
    for path in sorted(glob.glob(os.path.join(LOG_DIR, "proc-*.csv"))):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    ts = datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%S")
                    if ts < cutoff:
                        continue
                    metric, cmd, val = r["metric"], r["command"], float(r["value"])
                except (ValueError, KeyError):
                    continue
                if metric not in stats:
                    continue
                n_samples[metric].add(r["timestamp"])
                s = stats[metric].setdefault(cmd, {"sum": 0.0, "n": 0, "peak": 0.0})
                s["sum"] += val
                s["n"] += 1
                s["peak"] = max(s["peak"], val)
    return stats, {k: len(v) for k, v in n_samples.items()}


def percentile(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def bucket(rows, key, n=400):
    """Downsample to <= n points; each bucket is (mid timestamp, mean value)."""
    if len(rows) <= n:
        return [(r["ts"], r[key]) for r in rows]
    out = []
    size = len(rows) / n
    for b in range(n):
        chunk = rows[int(b * size):int((b + 1) * size)]
        if chunk:
            out.append((chunk[len(chunk) // 2]["ts"],
                        sum(r[key] for r in chunk) / len(chunk)))
    return out


def nice_ticks(vmax, count=4):
    if vmax <= 0:
        return [0, 1]
    raw = vmax / count
    mag = 10 ** len(str(int(raw))) / 10
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    ticks, v = [], 0.0
    while v <= vmax + 1e-9:
        ticks.append(v)
        v += step
    return ticks


def fmt_ts(ts, span_hours):
    return ts.strftime("%H:%M") if span_hours <= 36 else ts.strftime("%d %b %H:%M")


def line_chart(cid, title, series, unit, y_max=None, ic="activity"):
    """series: list of {name, var, points:[(ts, val)]} — renders SVG + hover meta."""
    W, H, L, R, T, B = 960, 260, 56, 130, 16, 30
    pts_all = [p for s in series for p in s["points"]]
    if not pts_all:
        return f'<div class="card"><h2>{html.escape(title)}</h2><p class="muted">ยังไม่มีข้อมูล</p></div>'
    t0 = min(p[0] for p in pts_all)
    t1 = max(p[0] for p in pts_all)
    span = max((t1 - t0).total_seconds(), 1)
    vmax = y_max if y_max else max(p[1] for p in pts_all) * 1.08
    ticks = nice_ticks(vmax)
    vmax = max(vmax, ticks[-1])

    def X(ts):
        return L + (ts - t0).total_seconds() / span * (W - L - R)

    def Y(v):
        return T + (1 - v / vmax) * (H - T - B)

    grid = "".join(
        f'<line x1="{L}" y1="{Y(t):.1f}" x2="{W - R}" y2="{Y(t):.1f}" stroke="var(--grid)" stroke-width="1"/>'
        f'<text x="{L - 8}" y="{Y(t) + 4:.1f}" text-anchor="end" class="tick">{t:g}</text>'
        for t in ticks)
    n_x = 5
    xticks = "".join(
        f'<text x="{L + i * (W - L - R) / (n_x - 1):.1f}" y="{H - 8}" text-anchor="middle" class="tick">'
        f'{fmt_ts(t0 + timedelta(seconds=span * i / (n_x - 1)), span / 3600)}</text>'
        for i in range(n_x))

    paths, dots, labels, meta_series = "", "", [], []
    for s in series:
        pts = s["points"]
        # break the line where samples are missing (sleep/agent stopped)
        gap_thr = max(3 * span / max(len(pts) - 1, 1), 600)
        d, prev_ts = "", None
        for ts, v in pts:
            cmd = "M" if prev_ts is None or (ts - prev_ts).total_seconds() > gap_thr else "L"
            d += f'{cmd}{X(ts):.1f},{Y(v):.1f} '
            prev_ts = ts
        paths += (f'<path d="{d}" fill="none" stroke="var(--{s["var"]})" '
                  f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        dots += (f'<circle class="hoverdot" r="4" fill="var(--{s["var"]})" '
                 f'stroke="var(--surface)" stroke-width="2" style="display:none"/>')
        labels.append({"name": s["name"], "var": s["var"], "y": Y(pts[-1][1])})
        meta_series.append({"name": s["name"], "var": s["var"],
                            "ys": [round(Y(v), 1) for _, v in pts],
                            "vals": [round(v, 1) for _, v in pts]})
    # direct labels at line ends, nudged apart if colliding
    labels.sort(key=lambda a: a["y"])
    for i in range(1, len(labels)):
        if labels[i]["y"] - labels[i - 1]["y"] < 14:
            labels[i]["y"] = labels[i - 1]["y"] + 14
    direct = "".join(
        f'<circle cx="{W - R + 8}" cy="{lb["y"]:.1f}" r="4" fill="var(--{lb["var"]})"/>'
        f'<text x="{W - R + 16}" y="{lb["y"] + 4:.1f}" class="dlabel">{html.escape(lb["name"])}</text>'
        for lb in labels)

    ref = series[0]["points"]
    meta = {"w": W, "left": L, "right": W - R, "top": T, "bottom": H - B, "unit": unit,
            "xs": [round(X(ts), 1) for ts, _ in ref],
            "times": [fmt_ts(ts, span / 3600) for ts, _ in ref],
            "series": meta_series}
    legend = ""
    if len(series) > 1:
        legend = '<div class="legend">' + "".join(
            f'<span><i style="background:var(--{s["var"]})"></i>{html.escape(s["name"])}</span>'
            for s in series) + "</div>"
    return f'''<div class="card">
{chead(ic, title)}{legend}
<div class="chart-wrap" data-chart="{cid}">
<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">
{grid}{xticks}
<line x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}" stroke="var(--axis)" stroke-width="1"/>
{paths}{direct}
<line class="crosshair" y1="{T}" y2="{H - B}" stroke="var(--axis)" stroke-width="1" style="display:none"/>
{dots}
</svg>
<div class="tip" style="display:none"></div>
<script type="application/json" class="meta">{json.dumps(meta)}</script>
</div>
{table_view(ref, series, unit)}
</div>'''


def table_view(ref, series, unit):
    head = "".join(f"<th>{html.escape(s['name'])} ({unit})</th>" for s in series)
    body = ""
    for i, (ts, _) in enumerate(ref):
        cells = "".join(f"<td>{s['points'][i][1]:,.1f}</td>" for s in series
                        if i < len(s["points"]))
        body += f"<tr><td>{ts.strftime('%d %b %H:%M')}</td>{cells}</tr>"
    return (f'<details><summary>{icon("chevron", 14, "chev")}{icon("table", 14)} ดูข้อมูลแบบตาราง</summary>'
            f'<div class="tbl-scroll"><table><thead><tr><th>เวลา</th>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div></details>')


def bar_chart(title, pairs, unit, ic="chart"):
    """pairs: [(label, value)] — hourly bars, rounded top, anchored to baseline."""
    W, H, L, R, T, B = 960, 220, 56, 16, 16, 30
    if not pairs:
        return ""
    vmax = max(v for _, v in pairs) * 1.15 or 1
    ticks = nice_ticks(vmax)
    vmax = max(vmax, ticks[-1])
    inner = W - L - R
    slot = inner / len(pairs)
    bw = slot * 0.7

    def Y(v):
        return T + (1 - v / vmax) * (H - T - B)

    grid = "".join(
        f'<line x1="{L}" y1="{Y(t):.1f}" x2="{W - R}" y2="{Y(t):.1f}" stroke="var(--grid)" stroke-width="1"/>'
        f'<text x="{L - 8}" y="{Y(t) + 4:.1f}" text-anchor="end" class="tick">{t:g}</text>'
        for t in ticks)
    bars, xlabels = "", ""
    r = 4
    for i, (lb, v) in enumerate(pairs):
        x = L + i * slot + (slot - bw) / 2
        y, y0 = Y(v), H - B
        hgt = y0 - y
        rr = min(r, hgt / 2, bw / 2)
        bars += (f'<path d="M{x:.1f},{y0:.1f} L{x:.1f},{y + rr:.1f} Q{x:.1f},{y:.1f} {x + rr:.1f},{y:.1f} '
                 f'L{x + bw - rr:.1f},{y:.1f} Q{x + bw:.1f},{y:.1f} {x + bw:.1f},{y + rr:.1f} '
                 f'L{x + bw:.1f},{y0:.1f} Z" fill="var(--s1)" class="bar" '
                 f'data-tip="{html.escape(lb)} น. — {v:,.1f}{unit}"/>')
        if i % 2 == 0:
            xlabels += (f'<text x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle" '
                        f'class="tick">{html.escape(lb)}</text>')
    return f'''<div class="card">
{chead(ic, title)}
<div class="chart-wrap">
<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">
{grid}{xlabels}
<line x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}" stroke="var(--axis)" stroke-width="1"/>
{bars}
</svg>
<div class="tip" style="display:none"></div>
</div>
</div>'''


def proc_table(title, data, total, unit, ic="flame"):
    rows = []
    for cmd, s in data.items():
        rows.append((cmd, s["sum"] / total if total else 0,
                     s["sum"] / s["n"], s["peak"], 100.0 * s["n"] / total if total else 0))
    rows.sort(key=lambda r: r[1], reverse=True)
    body = "".join(
        f"<tr><td class='cmd'>{html.escape(c)}</td><td>{avg:,.1f}</td>"
        f"<td>{peak:,.1f}</td><td>{pres:.0f}%</td></tr>"
        for c, _, avg, peak, pres in rows[:12])
    return f'''<div class="card">
{chead(ic, title)}
<div class="tbl-scroll"><table>
<thead><tr><th>โปรเซส</th><th>เฉลี่ย ({unit})</th><th>สูงสุด ({unit})</th><th>% ของเวลาที่ติด top 5</th></tr></thead>
<tbody>{body}</tbody></table></div>
</div>'''


def render_body(days):
    """Tiles + charts + tables for the last `days` days (fractions allowed).
    Returns (html, n_samples); html is None when there is no data yet."""
    rows = load_sys(days)
    proc, proc_totals = load_proc(days)
    if not rows:
        return None, 0

    cpu_vals = [r["cpu"] for r in rows]
    mem_vals = [r["mem"] for r in rows]
    tiles = [
        ("cpu", "CPU เฉลี่ย", f"{sum(cpu_vals) / len(cpu_vals):.1f}%"),
        ("gauge", "CPU P95", f"{percentile(cpu_vals, 0.95):.1f}%"),
        ("zap", "CPU สูงสุด", f"{max(cpu_vals):.1f}%"),
        ("memory", "RAM เฉลี่ย", f"{sum(mem_vals) / len(mem_vals) / 1024:.1f} GB"),
        ("memory", "RAM สูงสุด", f"{max(mem_vals) / 1024:.1f} GB"),
        ("harddrive", "Swap ล่าสุด", f"{rows[-1]['swap'] / 1024:.1f} GB"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="tico">{icon(ic, 18)}</div>'
        f'<div><div class="v">{v}</div><div class="l">{k}</div></div></div>'
        for ic, k, v in tiles)

    cpu_chart = line_chart(
        "cpu", "การใช้ CPU (% ของทั้งเครื่อง)",
        [{"name": "CPU", "var": "s1", "points": bucket(rows, "cpu")}], "%",
        y_max=100, ic="activity")
    mem_chart = line_chart(
        "mem", "หน่วยความจำ (MB)",
        [{"name": "RAM ที่ใช้", "var": "s1", "points": bucket(rows, "mem")},
         {"name": "Swap ที่ใช้", "var": "s2", "points": bucket(rows, "swap")}], " MB",
        ic="memory")

    by_hour = {}
    for r in rows:
        by_hour.setdefault(r["ts"].hour, []).append(r["cpu"])
    hour_pairs = [(f"{h:02d}", sum(v) / len(v)) for h, v in sorted(by_hour.items())]
    hour_chart = bar_chart("CPU เฉลี่ยตามชั่วโมงของวัน", hour_pairs, "%", ic="clock")

    span_txt = (f"{rows[0]['ts'].strftime('%d %b %Y %H:%M')} – "
                f"{rows[-1]['ts'].strftime('%d %b %Y %H:%M')} • {len(rows):,} ตัวอย่าง")

    body = f"""<p class="sub">{span_txt}</p>
<div class="tiles">{tiles_html}</div>
{cpu_chart}
{mem_chart}
{hour_chart}
<div class="grid2">
{proc_table("โปรเซสกิน CPU สูงสุด", proc["cpu"], proc_totals.get("cpu", 0), "%CPU", ic="flame")}
{proc_table("โปรเซสกิน RAM สูงสุด", proc["mem"], proc_totals.get("mem", 0), "MB", ic="database")}
</div>"""
    return body, len(rows)


def render_page(days):
    """Full static page. Returns (html, n_samples); html is None when no data."""
    body, n = render_body(days)
    if body is None:
        return None, 0
    doc = f"""<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mac Resource Report</title>
<style>{STYLE}</style></head><body>
<div class="header"><div class="header-in">
<div class="brand"><span class="mark">{icon("activity", 15)}</span>รายงานการใช้ทรัพยากรเครื่อง</div>
{theme_button()}
</div></div>
<div class="page">
{body}
</div>
<script>{JS}
bindTheme(); bindCharts();</script>
</body></html>"""
    return doc, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--out", default=os.path.join(BASE, "report.html"))
    args = ap.parse_args()
    doc, n = render_page(args.days)
    if doc is None:
        raise SystemExit("no data in logs/ yet — let the logger run first")
    with open(args.out, "w") as f:
        f.write(doc)
    print(f"wrote {args.out}  ({n:,} samples, last {args.days:g} days)")


if __name__ == "__main__":
    main()
