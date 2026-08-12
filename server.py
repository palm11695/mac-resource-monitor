#!/usr/bin/env python3
"""Live dashboard for mac-resource-monitor (stdlib only).

Serves http://127.0.0.1:8737 — the shell page polls /fragment on a
user-selectable interval and swaps the content in place (no full reload).
Binds to localhost only.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report

HOST = os.environ.get("RESMON_HOST", "127.0.0.1")
PORT = int(os.environ.get("RESMON_PORT", "8737"))

SHELL_TEMPLATE = """<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mac Resource Dashboard</title>
<style>__STYLE__</style></head><body>
<div class="header"><div class="header-in">
<div class="brand"><span class="mark">__BRAND_ICON__</span>Dashboard ทรัพยากรเครื่อง</div>
<div class="controls">
<div class="seg" id="range" role="group" aria-label="ช่วงข้อมูล">
<button data-v="1">1 ชม.</button>
<button data-v="6">6 ชม.</button>
<button data-v="24">24 ชม.</button>
<button data-v="168">7 วัน</button>
<button data-v="720">30 วัน</button>
</div>
<select id="every" aria-label="ความถี่การอัปเดต">
<option value="10">ทุก 10 วิ</option>
<option value="30">ทุก 30 วิ</option>
<option value="60">ทุก 1 นาที</option>
<option value="300">ทุก 5 นาที</option>
<option value="0">ไม่ refresh</option>
</select>
__THEME_BTN__
</div>
</div></div>
<div class="page">
<div id="status">__REFRESH_ICON__<span id="statusText">กำลังโหลด…</span></div>
<div id="content"></div>
</div>
<script>__JS__
(function () {
  var content = document.getElementById('content');
  var statusBox = document.getElementById('status');
  var statusText = document.getElementById('statusText');
  var rangeSeg = document.getElementById('range');
  var everyEl = document.getElementById('every');
  var rangeVal = '1';
  var timer = null;

  try {
    rangeVal = localStorage.getItem('resmon-range') || '1';
    everyEl.value = localStorage.getItem('resmon-every') || '10';
  } catch (e) {}
  if (!everyEl.value) everyEl.value = '10';
  var known = false;
  rangeSeg.querySelectorAll('button').forEach(function (b) {
    if (b.dataset.v === rangeVal) known = true;
  });
  if (!known) rangeVal = '1';

  function paintSeg() {
    rangeSeg.querySelectorAll('button').forEach(function (b) {
      b.classList.toggle('on', b.dataset.v === rangeVal);
    });
  }

  function save() {
    try {
      localStorage.setItem('resmon-range', rangeVal);
      localStorage.setItem('resmon-every', everyEl.value);
    } catch (e) {}
  }

  function load() {
    statusBox.classList.add('loading');
    fetch('/fragment?hours=' + rangeVal)
      .then(function (r) { if (!r.ok) throw 0; return r.text(); })
      .then(function (h) {
        var openIdx = [];
        content.querySelectorAll('details').forEach(function (d, i) {
          if (d.open) openIdx.push(i);
        });
        content.innerHTML = h;
        var ds = content.querySelectorAll('details');
        openIdx.forEach(function (i) { if (ds[i]) ds[i].open = true; });
        bindCharts();
        statusBox.classList.remove('loading');
        statusText.textContent = 'อัปเดตล่าสุด ' +
          new Date().toLocaleTimeString('th-TH') + ' • ' +
          everyEl.options[everyEl.selectedIndex].text;
      })
      .catch(function () {
        statusBox.classList.remove('loading');
        statusText.textContent = 'เชื่อมต่อ server ไม่ได้ — จะลองใหม่อัตโนมัติ';
      });
  }

  function arm() {
    if (timer) clearInterval(timer);
    var s = parseInt(everyEl.value, 10);
    if (s > 0) timer = setInterval(function () {
      if (!document.hidden) load();  // pause while tab is hidden
    }, s * 1000);
  }

  rangeSeg.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    rangeVal = b.dataset.v;
    paintSeg();
    save();
    load();
  });
  everyEl.addEventListener('change', function () { save(); arm(); load(); });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) load();
  });

  bindTheme();
  paintSeg();
  load();
  arm();
})();
</script>
</body></html>"""

SHELL = (SHELL_TEMPLATE
         .replace("__STYLE__", report.STYLE)
         .replace("__JS__", report.JS)
         .replace("__BRAND_ICON__", report.icon("activity", 15))
         .replace("__THEME_BTN__", report.theme_button())
         .replace("__REFRESH_ICON__", report.icon("refresh", 13, "sicon")))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self.send_html(SHELL)
        elif u.path == "/fragment":
            try:
                hours = float(parse_qs(u.query).get("hours", ["24"])[0])
            except ValueError:
                hours = 24.0
            hours = min(max(hours, 1 / 60), 24 * 90)
            body, _ = report.render_body(hours / 24)
            self.send_html(body if body is not None
                           else '<p class="muted">ยังไม่มีข้อมูลใน log — รอ sampler สักครู่</p>')
        else:
            self.send_error(404)

    def send_html(self, s):
        b = s.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *args):
        pass


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"resmon dashboard on http://{HOST}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
