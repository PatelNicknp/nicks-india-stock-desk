/* Chart Viewer in a phone and a tablet: no errors, no sideways scroll, swipes, chips, reason box. */
const http = require("http");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

function loadPlaywright() {
  const tries = ["playwright", process.env.PLAYWRIGHT_NODE_PATH, "/tmp/pw/node_modules/playwright"].filter(Boolean);
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
