/* Chart Viewer in a phone and a tablet: no errors, no sideways scroll, swipes, drag to pan, pinch zoom, chips, reason box. */
const http = require("http");
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const root = path.resolve(__dirname, "..");

function loadPlaywright() {
  const tries = ["playwright", process.env.PLAYWRIGHT_NODE_PATH, "/tmp/pw/node_modules/playwright", "/workspace/pw/node_modules/playwright"].filter(Boolean);
  for (const name of tries) {
    try { return require(name); } catch (e) { /* next */ }
  }
  return null;
}

function contentType(file) {
  if (file.endsWith(".html")) return "text/html; charset=utf-8";
  if (file.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (file.endsWith(".css")) return "text/css; charset=utf-8";
  if (file.endsWith(".csv")) return "text/csv; charset=utf-8";
  if (file.endsWith(".gz")) return "application/gzip";
  return "application/octet-stream";
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent((req.url || "/").split("?")[0]);
    const file = path.normalize(path.join(root, url));
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404);
      res.end("missing");
      return;
    }
    res.writeHead(200, { "Content-Type": contentType(file) });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function swipe(page, dx) {
  return page.evaluate((dx) => {
    const plot = document.getElementById("cvplot");
    const r = plot.getBoundingClientRect();
    const x0 = r.left + r.width / 2 - dx / 2;
    const y = r.top + r.height / 2;
    const mk = (x) => new Touch({ identifier: 1, target: plot, clientX: x, clientY: y });
    const fire = (type, t) => plot.dispatchEvent(new TouchEvent(type, {
      touches: type === "touchend" ? [] : [t], changedTouches: [t], bubbles: true, cancelable: true,
    }));
    fire("touchstart", mk(x0));
    fire("touchmove", mk(x0 + dx / 2));
    fire("touchend", mk(x0 + dx));
    return document.getElementById("cvstage")._cv.i;
  }, dx);
}

// Real touches through the browser, so Lightweight Charts sees them too.
// points is a list of [x, y] per finger; steps move each finger by dx, dy; ms is the time between steps.
async function realTouch(page, cdp, points, moves, ms) {
  const tp = (pts) => pts.map(([x, y], id) => ({ x, y, id, radiusX: 2, radiusY: 2, force: 1 }));
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: tp(points) });
  let cur = points;
  for (const step of moves) {
    cur = cur.map(([x, y], k) => [x + step[k][0], y + step[k][1]]);
    if (ms) await page.waitForTimeout(ms);
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: tp(cur) });
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForTimeout(400);
}

// How many daily bars the desk saved for a ticker (data/ohlc letter files), so the check
// works for a recently listed or renamed stock with a short history.
const savedCounts = new Map();
function savedBars(ticker) {
  const t = String(ticker || "").toUpperCase();
  const c = t.charAt(0);
  const group = c === "^" ? "_indexes" : (c >= "A" && c <= "Z" ? c : "0");
  if (!savedCounts.has(group)) {
    const counts = new Map();
    try {
      const text = zlib.gunzipSync(fs.readFileSync(path.join(root, "data", "ohlc", group + ".csv.gz"))).toString("utf8");
      text.split("\n").slice(1).forEach((line) => {
        const k = (line.split(",")[1] || "").trim().toUpperCase();
        if (k) counts.set(k, (counts.get(k) || 0) + 1);
      });
    } catch (e) { /* no file */ }
    savedCounts.set(group, counts);
  }
  return savedCounts.get(group).get(t) || 0;
}

async function viewState(page) {
  return page.evaluate(() => {
    const st = document.getElementById("cvstage")._cv;
    const r = st.chart ? st.chart.timeScale().getVisibleLogicalRange() : null;
    return { i: st.i, ticker: document.getElementById("cvstage").dataset.ticker, from: r ? r.from : null, to: r ? r.to : null,
      bars: st.bars.length, first: st.bars.length ? st.bars[0].date : "" };
  });
}

// Where the newest candle should land (the US rule): just left of the Why box, so the box does
// not cover the last candles. The empty space on the right is the box width plus 14 pixels, or
// 3 bars when the box is hidden. The first bar of the range sits at the left edge.
async function lastCandle(page) {
  return page.evaluate(() => {
    const st = document.getElementById("cvstage")._cv;
    const ts = st.chart.timeScale();
    const r = ts.getVisibleLogicalRange();
    const first = Math.max(0, Math.ceil(r.from));
    const n = st.bars.length;
    const sp = ts.options().barSpacing;
    const w = ts.width();
    const box = document.getElementById("cvreason");
    const shown = box && !box.hidden;
    let B = shown ? box.offsetWidth + 14 : 0;
    if (shown && box.classList.contains("open")) B = Math.min(B, 260);
    if (B && w - B < w * 0.35) B = w * 0.65;
    const xl = ts.logicalToCoordinate(n - 1);
    const host = document.getElementById("cvhost").getBoundingClientRect();
    const br = shown ? box.getBoundingClientRect() : null;
    return { ticker: document.getElementById("cvstage").dataset.ticker, w, sp, from: r.from, to: r.to, first,
      x0: ts.logicalToCoordinate(first), xl, gap: w - xl, want: B ? Math.max(B, 3 * sp) : 3 * sp,
      pageX: host.left + xl, boxLeft: br ? br.left : null, shownBars: n - first };
  });
}
async function checkFill(page, name, tag, wantShown) {
  await page.waitForTimeout(400);
  const f = await lastCandle(page);
  const bad = [];
  const tol = Math.max(6, f.sp * 1.5);
  if (!(f.x0 < tol)) bad.push(name + " " + tag + ": first bar is not at the left edge " + JSON.stringify(f));
  if (!(Math.abs(f.gap - f.want) < tol)) bad.push(name + " " + tag + ": last candle is not just left of the Why box (US rule) " + JSON.stringify(f));
  if (f.boxLeft != null && !(f.pageX < f.boxLeft)) bad.push(name + " " + tag + ": Why box covers the last candle " + JSON.stringify(f));
  if (wantShown !== false && !(f.shownBars > 40 && f.shownBars < 160)) bad.push(name + " " + tag + ": first view shows " + f.shownBars + " bars " + JSON.stringify(f));
  return bad;
}
// The newest candle lands in the same screen spot on 3 charts in a row.
async function checkSameSpot(page, name) {
  const bad = [];
  const spots = [];
  for (let k = 0; k < 3; k++) {
    if (k) { await page.click("#cvnext"); await waitOk(page); }
    bad.push(...(await checkFill(page, name, "chart " + (k + 1), false)));
    spots.push(await lastCandle(page));
  }
  const xs = spots.map((f) => f.pageX);
  const tol = Math.max(8, Math.max(...spots.map((f) => f.sp)) * 1.5);
  if (Math.max(...xs) - Math.min(...xs) > tol) bad.push(name + ": newest candle moves between charts " + JSON.stringify(spots.map((f) => [f.ticker, Math.round(f.pageX), Math.round(f.w)])));
  if (new Set(spots.map((f) => f.ticker)).size !== 3) bad.push(name + ": next did not change the chart " + JSON.stringify(spots.map((f) => f.ticker)));
  await page.evaluate(() => document.getElementById("cvstage")._cv.go(-2));
  await waitOk(page);
  return bad;
}

// A range the user dragged to stays after a turn of the device (a resize), like the US desk.
// A new chart and a range chip still put the first view back.
async function checkKeepRange(page, ctx, name) {
  const bad = [];
  const cdp = await ctx.newCDPSession(page);
  const b = await plotBox(page, "#cvplot");
  const cx = b.x + b.w * 0.45, cy = b.y + b.h * 0.45;
  const v0 = await viewState(page);
  await realTouch(page, cdp, [[cx - 60, cy]], Array.from({ length: 12 }, () => [[12, 0]]), 60);
  const v1 = await viewState(page);
  if (!(v1.from < v0.from - 3) || v1.ticker !== v0.ticker) bad.push(name + ": drag did not pan before the turn " + JSON.stringify([v0, v1]));
  const size = page.viewportSize();
  await page.setViewportSize({ width: size.height, height: size.width });
  await page.waitForTimeout(700);
  const v2 = await viewState(page);
  await page.setViewportSize(size);
  await page.waitForTimeout(700);
  const v3 = await viewState(page);
  if (Math.abs(v2.from - v1.from) > 0.6 || Math.abs(v2.to - v1.to) > 0.6) bad.push(name + ": turning the device threw away the dragged range " + JSON.stringify([v1, v2]));
  if (Math.abs(v3.from - v1.from) > 0.6 || Math.abs(v3.to - v1.to) > 0.6) bad.push(name + ": turning back threw away the dragged range " + JSON.stringify([v1, v3]));
  // A range chip clears the dragged range.
  await realTouch(page, cdp, [[cx - 60, cy]], Array.from({ length: 10 }, () => [[12, 0]]), 60);
  await page.click('[data-chip="r6"]');
  await page.waitForTimeout(300);
  if (await page.evaluate(() => !!(document.getElementById("cvstage")._cv.userRange && document.getElementById("cvstage")._cv.userRange()))) bad.push(name + ": range chip kept the dragged range");
  bad.push(...(await checkFill(page, name, "6M chip after a drag", false)));
  // A new chart opens on the first view.
  await realTouch(page, cdp, [[cx - 60, cy]], Array.from({ length: 10 }, () => [[12, 0]]), 60);
  await page.click("#cvnext");
  await waitOk(page);
  bad.push(...(await checkFill(page, name, "next chart after a drag", false)));
  await page.click("#cvprev");
  await waitOk(page);
  await cdp.detach();
  return bad;
}

async function plotBox(page, sel) {
  return page.evaluate((sel) => {
    const r = document.querySelector(sel).getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }, sel);
}

// The default: a slow one-finger drag pans the same chart, a quick flick changes it,
// a swipe on the header changes it, pinch zooms, and the Drag chip switches back.
async function checkTouch(page, ctx, name) {
  const bad = [];
  const cdp = await ctx.newCDPSession(page);
  await waitOk(page);
  await page.waitForTimeout(300);
  const chipText = await page.locator('[data-chip="drag"]').innerText();
  if (chipText !== "Drag: move chart") bad.push(name + ": drag chip says " + chipText);
  const b = await plotBox(page, "#cvplot");
  const cx = b.x + b.w * 0.45, cy = b.y + b.h * 0.45;
  const v0 = await viewState(page);
  const saved = savedBars(v0.ticker);
  if (v0.bars < Math.min(400, saved)) bad.push(name + ": only " + v0.bars + " of " + saved + " saved bars loaded, not the full saved history");
  if (!(v0.from > 1)) bad.push(name + ": first view should not show the whole history " + JSON.stringify(v0));
  // Slow drag to the right: older days come into view, same ticker.
  await realTouch(page, cdp, [[cx - 60, cy]], Array.from({ length: 12 }, () => [[12, 0]]), 60);
  const v1 = await viewState(page);
  if (v1.i !== v0.i || v1.ticker !== v0.ticker) bad.push(name + ": slow drag changed the chart " + JSON.stringify([v0, v1]));
  if (!(v1.from < v0.from - 3)) bad.push(name + ": slow drag did not pan back in time " + JSON.stringify([v0, v1]));
  // Tapping the reason box (Why) opens and closes it but keeps the panned view.
  if (await page.evaluate(() => !document.getElementById("cvreason").hidden)) {
    await page.tap("#cvreason");
    await page.waitForTimeout(250);
    await page.tap("#cvreason");
    await page.waitForTimeout(250);
    const vr = await viewState(page);
    if (Math.abs(vr.from - v1.from) > 0.5 || vr.i !== v1.i) bad.push(name + ": tapping the reason box reset the panned chart " + JSON.stringify([v1, vr]));
  }
  // Pinch out: fewer bars show.
  const w1 = v1.to - v1.from;
  await realTouch(page, cdp, [[cx - 40, cy], [cx + 40, cy]], Array.from({ length: 8 }, () => [[-15, 0], [15, 0]]), 30);
  const v2 = await viewState(page);
  if (v2.i !== v0.i) bad.push(name + ": pinch changed the chart");
  if (!(v2.to - v2.from < w1 * 0.9)) bad.push(name + ": pinch did not zoom " + JSON.stringify([w1, v2.to - v2.from]));
  // Quick flick right: next chart.
  await realTouch(page, cdp, [[cx - 80, cy]], [[[60, 0]], [[60, 0]], [[60, 0]]], 0);
  await waitOk(page);
  const v3 = await viewState(page);
  if (v3.i !== (v0.i + 1) % Math.max(1, (await page.evaluate(() => document.getElementById("cvstage")._cv.list.length)))) bad.push(name + ": quick flick did not go to the next chart " + JSON.stringify([v0.i, v3.i]));
  // Slow swipe on the header: next chart.
  const h = await plotBox(page, "#cvtk");
  await realTouch(page, cdp, [[h.x + 4, h.y + h.h / 2]], Array.from({ length: 8 }, () => [[20, 0]]), 60);
  await waitOk(page);
  const v4 = await viewState(page);
  if (v4.i === v3.i) bad.push(name + ": swipe on the header did not change the chart");
  // Chip bar: when it can scroll sideways (phones), a swipe there scrolls the chips and keeps
  // the chart. When every chip fits, a swipe there changes the chart.
  const cb = await page.evaluate(() => { const c = document.getElementById("cvchips"); const r = c.getBoundingClientRect();
    c.scrollLeft = 0; return { x: r.left, y: r.top, w: r.width, h: r.height, over: c.scrollWidth > c.clientWidth + 1,
      rows: new Set(Array.from(c.children).map((b) => Math.round(b.getBoundingClientRect().top))).size }; });
  if (name === "iphone-portrait" && (!cb.over || cb.rows !== 1)) bad.push(name + ": chip bar should be one row that scrolls " + JSON.stringify(cb));
  const c0 = await viewState(page);
  await realTouch(page, cdp, [[cb.x + cb.w * 0.8, cb.y + cb.h / 2]], Array.from({ length: 8 }, () => [[-20, 0]]), 60);
  await waitOk(page);
  const c1 = await viewState(page);
  const sl = await page.evaluate(() => document.getElementById("cvchips").scrollLeft);
  if (cb.over) {
    if (c1.i !== c0.i || c1.ticker !== c0.ticker) bad.push(name + ": swipe on a scrolling chip bar changed the chart " + JSON.stringify([c0.ticker, c1.ticker]));
    if (!(sl > 20)) bad.push(name + ": swipe on the chip bar did not scroll the chips, scrollLeft " + sl);
  } else if (c1.i === c0.i) bad.push(name + ": swipe on a chip bar that fits should change the chart");
  await page.evaluate(() => { document.getElementById("cvchips").scrollLeft = 0; });
  // Range chips.
  const pre = await viewState(page);
  await page.click('[data-chip="rall"]');
  await page.waitForTimeout(200);
  const all = await viewState(page);
  // All shows as much of the saved history as fits (the whole of it on a tablet), with the newest
  // candle in the same spot left of the Why box.
  if (!(all.from < pre.from - 100)) bad.push(name + ": All chip did not show more history " + JSON.stringify([pre, all]));
  if (name.indexOf("ipad") === 0 && !(all.from <= 0.5)) bad.push(name + ": All chip did not show the whole history " + JSON.stringify(all));
  bad.push(...(await checkFill(page, name, "All chip", false)).filter((t) => t.indexOf("left edge") < 0));
  await page.click('[data-chip="r3"]');
  await page.waitForTimeout(200);
  const m3 = await viewState(page);
  bad.push(...(await checkFill(page, name, "3M chip", false)));
  if (!(m3.from > 600 && m3.from < 710)) bad.push(name + ": 3M chip range " + JSON.stringify(m3));
  // Drag chip: back to Drag: next chart, saved; a slow drag on the chart now changes the chart.
  await page.click('[data-chip="drag"]');
  const flip = await page.evaluate(() => ({ text: document.querySelector('[data-chip="drag"]').innerText, saved: localStorage.getItem("desk-cv-drag-pan") }));
  if (flip.text !== "Drag: next chart" || flip.saved !== "false") bad.push(name + ": drag chip did not switch " + JSON.stringify(flip));
  const before = await viewState(page);
  await realTouch(page, cdp, [[cx - 60, cy]], Array.from({ length: 10 }, () => [[14, 0]]), 60);
  await waitOk(page);
  const after = await viewState(page);
  if (after.i === before.i) bad.push(name + ": with Drag: next chart a slow drag should change the chart");
  // Drag: next chart turns pinch zoom off.
  const pb = await viewState(page);
  await realTouch(page, cdp, [[cx - 40, cy - 20], [cx + 40, cy + 20]], Array.from({ length: 8 }, () => [[-15, 0], [15, 0]]), 30);
  const pa = await viewState(page);
  if (pa.i !== pb.i || Math.abs((pa.to - pa.from) - (pb.to - pb.from)) > 0.5) bad.push(name + ": pinch should do nothing with Drag: next chart " + JSON.stringify([pb, pa]));
  await page.click('[data-chip="drag"]');
  await realTouch(page, cdp, [[cx - 80, cy]], [[[60, 0]], [[60, 0]], [[60, 0]]], 0);
  await waitOk(page);
  // Only the last 6 charts stay in memory.
  for (let k = 0; k < 8; k++) { await page.click("#cvnext"); await waitOk(page); }
  const mem = await page.evaluate(() => { const st = document.getElementById("cvstage")._cv; return { recent: st.recent, files: st.cached() }; });
  if (mem.recent.length > 6) bad.push(name + ": more than 6 charts kept " + JSON.stringify(mem.recent));
  const groups = new Set(mem.recent.map((t) => (/^[A-Z]/.test(t) ? t[0] : "0")));
  if (mem.files.length > groups.size + 6) bad.push(name + ": bar files not forgotten " + JSON.stringify(mem.files));
  await cdp.detach();
  return bad;
}

async function waitOk(page) {
  await page.waitForFunction(() => {
    const s = document.getElementById("cvstage");
    return s && (s.dataset.state === "ok" || s.dataset.state === "nodata" || s.dataset.state === "empty");
  }, null, { timeout: 30000 });
}

async function check(browser, port, name, device, shotDir) {
  const bad = [];
  const base = process.env.CV_BASE ? process.env.CV_BASE.replace(/\/?$/, "/") : "http://127.0.0.1:" + port + "/site/";
  const ctx = await browser.newContext(device);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message || e)));
  page.on("console", (m) => { if (m.type() === "error" && !/favicon/.test(m.text())) errors.push(m.text()); });
  await page.goto(base + "chart-viewer.html", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  await waitOk(page);
  const first = await page.evaluate(() => {
    const st = document.getElementById("cvstage")._cv;
    return { n: st.list.length, i: st.i, ticker: st.list[0] && st.list[0].ticker };
  });
  if (first.n < 2) bad.push(name + ": list has " + first.n + " stocks");
  bad.push(...(await checkFill(page, name, "first view")));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 1) bad.push(name + ": sideways overflow " + overflow);

  // Full screen. Headless Chromium has the Fullscreen API; also try the iPhone fallback.
  await page.click("#cvfull");
  await page.waitForTimeout(400);
  const full = await page.evaluate(() => {
    const s = document.getElementById("cvstage");
    const r = s.getBoundingClientRect();
    return { on: s.classList.contains("cv-full"), w: r.width, h: r.height, vw: innerWidth, vh: innerHeight };
  });
  if (!full.on || Math.abs(full.w - full.vw) > 2 || Math.abs(full.h - full.vh) > 2) bad.push(name + ": full screen did not fill " + JSON.stringify(full));
  await waitOk(page);
  bad.push(...(await checkFill(page, name, "full screen")));
  bad.push(...(await checkSameSpot(page, name)));

  const right = await swipe(page, 160);
  await waitOk(page);
  if (right !== 1) bad.push(name + ": swipe right should go to the next chart, index " + right);
  const left = await swipe(page, -160);
  await waitOk(page);
  if (left !== 0) bad.push(name + ": swipe left should go back, index " + left);
  const slow = await page.evaluate(() => document.getElementById("cvstage")._cv.i);
  const small = await swipe(page, 20);
  if (small !== slow) bad.push(name + ": a tiny drag should not change the chart");
  await page.keyboard.press("ArrowRight");
  await waitOk(page);
  const key = await page.evaluate(() => document.getElementById("cvstage")._cv.i);
  if (key !== 1) bad.push(name + ": right key should go to the next chart");
  await page.keyboard.press("ArrowLeft");
  await waitOk(page);
  bad.push(...(await checkTouch(page, ctx, name)));
  await page.evaluate(() => document.getElementById("cvstage")._cv.go(-document.getElementById("cvstage")._cv.i));
  await waitOk(page);
  const counter = await page.locator("#cvcount").innerText();
  if (!/^1 of \d+$/.test(counter)) bad.push(name + ": counter says " + counter);

  // Moving average chips.
  const vis = () => page.evaluate(() => {
    const st = document.getElementById("cvstage")._cv;
    const out = {};
    Object.keys(st.mas).forEach((k) => { out[k] = st.mas[k].options().visible; });
    out.volume = st.vol.options().visible;
    return out;
  });
  const before = await vis();
  if (before.ma_10 || before.ma_20 || !before.ma_50 || !before.ma_150 || !before.ma_200 || !before.volume) bad.push(name + ": default averages wrong " + JSON.stringify(before));
  await page.click('[data-chip="ma_10"]');
  await page.click('[data-chip="ma_200"]');
  const after = await vis();
  if (!after.ma_10 || after.ma_200) bad.push(name + ": chips did not switch lines " + JSON.stringify(after));
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("desk-cv-ma") || "{}"));
  if (!stored.ma_10 || stored.ma_200) bad.push(name + ": chips not remembered");
  await page.click('[data-chip="ma_10"]');
  await page.click('[data-chip="ma_200"]');

  // Flip the swipe direction.
  await page.click('[data-chip="swipe"]');
  const flipped = await swipe(page, 160);
  await waitOk(page);
  if (flipped !== first.n - 1) bad.push(name + ": flipped swipe right should go back, index " + flipped);
  await page.click('[data-chip="swipe"]');
  await swipe(page, 160);
  await waitOk(page);

  // Reason box: lower right of the chart, left of the price scale.
  await page.waitForTimeout(200);
  const box = await page.evaluate(() => {
    const p = document.getElementById("cvplot").getBoundingClientRect();
    const el = document.getElementById("cvreason");
    if (el.hidden) return null;
    const r = el.getBoundingClientRect();
    return { right: p.right - r.right, bottom: p.bottom - r.bottom, left: r.left - p.left, top: r.top - p.top, w: r.width, h: r.height, pw: p.width, ph: p.height, text: el.innerText };
  });
  if (!box) bad.push(name + ": reason box missing");
  else {
    if (box.right > 120 || box.bottom > 70) bad.push(name + ": reason box not in the lower right " + JSON.stringify(box));
    if (box.w * box.h > box.pw * box.ph * 0.25 || box.w > box.pw * 0.65 || box.top < box.ph * 0.3) bad.push(name + ": reason box too big " + JSON.stringify(box));
    if (box.text.indexOf("\u2014") >= 0) bad.push(name + ": em-dash in reason box");
  }
  await page.click("#cvreason");
  const open = await page.evaluate(() => document.getElementById("cvreason").classList.contains("open"));
  if (!open) bad.push(name + ": reason box did not open");
  await page.click("#cvreason");
  if (shotDir) await page.screenshot({ path: path.join(shotDir, name + ".png") });
  await page.click("#cvexit");
  await page.waitForTimeout(300);
  const out = await page.evaluate(() => document.getElementById("cvstage").classList.contains("cv-full"));
  if (out) bad.push(name + ": exit did not leave full screen");

  // iPhone Safari fallback: no element Fullscreen API.
  await page.evaluate(() => {
    Object.defineProperty(document, "fullscreenEnabled", { value: false, configurable: true });
    Object.defineProperty(document, "webkitFullscreenEnabled", { value: false, configurable: true });
  });
  await page.click("#cvfull");
  await page.waitForTimeout(300);
  const fb = await page.evaluate(() => {
    const s = document.getElementById("cvstage");
    const r = s.getBoundingClientRect();
    return { fixed: s.classList.contains("cv-fixed"), pos: getComputedStyle(s).position, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight,
      nav: getComputedStyle(document.querySelector(".hdr")).visibility };
  });
  if (!fb.fixed || fb.pos !== "fixed" || Math.abs(fb.h - fb.vh) > 2 || fb.nav !== "hidden") bad.push(name + ": iPhone fallback " + JSON.stringify(fb));
  await waitOk(page);
  bad.push(...(await checkKeepRange(page, ctx, name)));
  await page.click("#cvexit");

  // A scanner page has the link, and it opens the viewer on that list.
  await page.goto(base + "vcp.html", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  const href = await page.getAttribute("#cvlink", "href");
  if (!/chart-viewer\.html\?list=vcp&t=/.test(href || "")) bad.push(name + ": VCP link is " + href);
  await page.goto(base + href, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  await waitOk(page);
  const want = new URLSearchParams(href.split("?")[1]).get("t");
  const got = await page.evaluate(() => ({ v: document.getElementById("cvlist").value, t: document.getElementById("cvstage").dataset.ticker }));
  if (got.v !== "vcp" || got.t !== want) bad.push(name + ": link opened " + JSON.stringify(got) + " not vcp " + want);
  if (errors.length) bad.push(name + ": " + errors.join(" | "));
  await ctx.close();
  return bad;
}

// iPad and iPhone Safari: never the element Fullscreen API (Safari adds a grey X over the
// stock name in the top left). The fixed layer fills the screen and the name stays clear.
async function checkIOS(browser, port, name, device) {
  const bad = [];
  const base = process.env.CV_BASE ? process.env.CV_BASE.replace(/\/?$/, "/") : "http://127.0.0.1:" + port + "/site/";
  const ctx = await browser.newContext(device);
  await ctx.addInitScript(() => {
    window.__fsCalls = 0;
    const spy = function () { window.__fsCalls++; return Promise.resolve(); };
    Element.prototype.requestFullscreen = spy;
    Element.prototype.webkitRequestFullscreen = spy;
    if (/Macintosh/.test(navigator.userAgent)) {
      Object.defineProperty(Navigator.prototype, "platform", { get: () => "MacIntel" });
      Object.defineProperty(Navigator.prototype, "maxTouchPoints", { get: () => 5 });
    }
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message || e)));
  await page.goto(base + "chart-viewer.html", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  await waitOk(page);
  await page.click("#cvfull");
  await page.waitForTimeout(400);
  const r = await page.evaluate(() => {
    const s = document.getElementById("cvstage");
    const b = s.getBoundingClientRect();
    const tk = document.getElementById("cvtk");
    const t = tk.getBoundingClientRect();
    const hit = document.elementFromPoint(t.left + 4, t.top + t.height / 2);
    const ex = document.getElementById("cvexit").getBoundingClientRect();
    return { calls: window.__fsCalls, fixed: s.classList.contains("cv-fixed"), full: s.classList.contains("cv-full"),
      native: !!document.fullscreenElement, w: b.width, h: b.height, vw: innerWidth, vh: innerHeight,
      text: tk.innerText, nameClear: !!hit && tk.contains(hit), exitRight: ex.left > innerWidth / 2 };
  });
  if (r.calls !== 0 || r.native) bad.push(name + ": requestFullscreen was called " + JSON.stringify(r));
  if (!r.fixed || !r.full || Math.abs(r.w - r.vw) > 2 || Math.abs(r.h - r.vh) > 2) bad.push(name + ": overlay did not fill " + JSON.stringify(r));
  if (!r.text || !r.nameClear) bad.push(name + ": ticker name covered " + JSON.stringify(r));
  if (!r.exitRight) bad.push(name + ": close X is not on the right " + JSON.stringify(r));
  if (bad.length) { await ctx.close(); return bad; }
  await page.click("#cvexit");
  await page.waitForTimeout(200);
  if (await page.evaluate(() => document.getElementById("cvstage").classList.contains("cv-full"))) bad.push(name + ": exit did not leave the overlay");
  if (errors.length) bad.push(name + ": " + errors.join(" | "));
  await ctx.close();
  return bad;
}

// The chart is drawn while it is still a few pixels wide (as on an iPhone before layout or while
// the overlay opens), then grows. The first view must still fill the width.
async function checkNarrowStart(browser, port, name, device) {
  const base = process.env.CV_BASE ? process.env.CV_BASE.replace(/\/?$/, "/") : "http://127.0.0.1:" + port + "/site/";
  const ctx = await browser.newContext(device);
  await ctx.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      const s = document.createElement("style");
      s.id = "narrow";
      s.textContent = ".cv-host{right:auto!important;width:40px!important}";
      document.head.appendChild(s);
    });
  });
  const page = await ctx.newPage();
  await page.goto(base + "chart-viewer.html", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  await waitOk(page);
  await page.waitForTimeout(500);
  await page.evaluate(() => document.getElementById("narrow").remove());
  const bad = await checkFill(page, name + " narrow start", "after it grows");
  await ctx.close();
  return bad;
}

async function main() {
  const pw = loadPlaywright();
  if (!pw) {
    console.log("skip: playwright is not installed");
    process.exit(2);
  }
  const shotDir = process.argv[2] || "";
  if (shotDir) fs.mkdirSync(shotDir, { recursive: true });
  // CV_BASE checks a live copy instead, for example https://patelnicknp.github.io/nicks-india-stock-desk/
  const live = process.env.CV_BASE || "";
  const server = live ? null : await serve();
  const port = server ? server.address().port : 0;
  const browser = await pw.chromium.launch({ args: ["--no-sandbox"] });
  const phone = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
  const devices = [
    ["iphone-portrait", phone],
    ["iphone-landscape", Object.assign({}, phone, { viewport: { width: 844, height: 390 } })],
    ["ipad-portrait", { viewport: { width: 820, height: 1180 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }],
    ["ipad-landscape", { viewport: { width: 1180, height: 820 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }],
  ];
  let bad = [];
  for (const [name, device] of devices) bad = bad.concat(await check(browser, port, name, device, shotDir));
  for (const [name, device] of devices) bad = bad.concat(await checkNarrowStart(browser, port, name, device));
  const ipadUA = "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";
  const ipadOS = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15";
  const iosDevices = [
    ["ipad-ua-landscape", { viewport: { width: 1180, height: 820 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, userAgent: ipadUA }],
    ["ipad-ua-portrait", { viewport: { width: 820, height: 1180 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, userAgent: ipadUA }],
    ["ipados-macintel", { viewport: { width: 1180, height: 820 }, deviceScaleFactor: 2, hasTouch: true, userAgent: ipadOS }],
  ];
  for (const [name, device] of iosDevices) bad = bad.concat(await checkIOS(browser, port, name, device));
  // Desktop keeps the real Fullscreen API.
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    await ctx.addInitScript(() => {
      window.__fsCalls = 0;
      const orig = Element.prototype.requestFullscreen;
      Element.prototype.requestFullscreen = function () { window.__fsCalls++; return orig.apply(this, arguments); };
    });
    const page = await ctx.newPage();
    const base = process.env.CV_BASE ? process.env.CV_BASE.replace(/\/?$/, "/") : "http://127.0.0.1:" + port + "/site/";
    await page.goto(base + "chart-viewer.html", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
    await waitOk(page);
    await page.click("#cvfull");
    await page.waitForTimeout(300);
    const calls = await page.evaluate(() => window.__fsCalls);
    if (calls !== 1) bad.push("desktop: requestFullscreen should be called once, got " + calls);
    await ctx.close();
  }
  await browser.close();
  if (server) server.close();
  if (bad.length) {
    console.log(bad.join("\n"));
    process.exit(1);
  }
  console.log("chart viewer ok on " + devices.map((d) => d[0]).concat(iosDevices.map((d) => d[0]), ["desktop"]).join(", "));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
