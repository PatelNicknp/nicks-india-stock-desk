/* Light mode on a phone and an iPad: every page turns light, text keeps contrast, the toggle works. */
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

function serve() {
  const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".csv": "text/csv", ".gz": "application/gzip" };
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent((req.url || "/").split("?")[0]);
    const file = path.normalize(path.join(root, url));
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404);
      res.end("missing");
      return;
    }
    res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

// Dark-mode text colours that would be hard to read on white.
const PALE = ["rgb(230, 235, 245)", "rgb(195, 203, 219)", "rgb(34, 197, 94)", "rgb(245, 158, 11)", "rgb(124, 156, 255)", "rgb(201, 210, 227)"];

async function main() {
  const pw = loadPlaywright();
  if (!pw) {
    console.log("skip: playwright is not installed");
    process.exit(2);
  }
  const base = process.env.LM_BASE ? process.env.LM_BASE.replace(/\/?$/, "/") : "";
  const server = base ? null : await serve();
  const site = base || "http://127.0.0.1:" + server.address().port + "/site/";
  const pages = fs.readdirSync(path.join(root, "site")).filter((n) => n.endsWith(".html")).sort();
  const browser = await pw.chromium.launch({ args: ["--no-sandbox"] });
  const bad = [];
  const devices = [
    ["phone", { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }],
    ["ipad", { viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true }],
  ];
  for (const [dn, dev] of devices) {
    const ctx = await browser.newContext(dev);
    await ctx.addInitScript(() => { try { if (!sessionStorage.getItem("lm-set")) { localStorage.setItem("desk-theme", "light"); sessionStorage.setItem("lm-set", "1"); } } catch (e) { /* ignore */ } });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e.message || e)));
    for (const name of (dn === "phone" ? pages : ["index.html", "vcp.html", "chart-viewer.html", "breadth.html", "scorecard.html", "heatmaps.html"])) {
      errors.length = 0;
      await page.goto(site + name, { waitUntil: "domcontentloaded" });
      await page.waitForSelector("body[data-ready='1'], body[data-ready='error']", { timeout: 30000 });
      await page.waitForTimeout(300);
      const info = await page.evaluate((pale) => {
        const doc = document.documentElement;
        const out = { theme: doc.getAttribute("data-theme"), bg: getComputedStyle(document.body).backgroundColor, overflow: doc.scrollWidth - doc.clientWidth, pale: [] };
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n;
        while ((n = walker.nextNode()) && out.pale.length < 3) {
          if (!n.nodeValue.trim()) continue;
          const el = n.parentElement;
          if (!el || !el.offsetParent) continue;
          const cs = getComputedStyle(el);
          if (pale.indexOf(cs.color) >= 0) out.pale.push(el.tagName + "." + el.className + " " + cs.color + " '" + n.nodeValue.trim().slice(0, 30) + "'");
        }
        // Contrast of every visible text against the colour behind it, at least 4.5 to 1.
        const rgb = (c) => { const m = /rgba?\(([^)]+)\)/.exec(c || ""); if (!m) return null; const p = m[1].split(",").map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
        const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
        const over = (top, base) => ({ r: top.r * top.a + base.r * (1 - top.a), g: top.g * top.a + base.g * (1 - top.a), b: top.b * top.a + base.b * (1 - top.a), a: 1 });
        const behind = (el) => {
          const layers = [];
          for (let e = el; e; e = e.parentElement) {
            const c = rgb(getComputedStyle(e).backgroundColor);
            if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
          }
          let base = { r: 243, g: 245, b: 249, a: 1 };
          for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
          return base;
        };
        const faded = (el) => { for (let e = el; e; e = e.parentElement) { if (Number(getComputedStyle(e).opacity) < 1) return true; } return false; };
        out.low = [];
        const w2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let t;
        while ((t = w2.nextNode()) && out.low.length < 4) {
          if (!t.nodeValue.trim()) continue;
          const el = t.parentElement;
          if (!el || !el.getClientRects().length || el.closest("[hidden], canvas, svg, .px-host, .cv-host, option, :disabled")) continue;
          const cs = getComputedStyle(el);
          if (cs.visibility === "hidden" || faded(el)) continue;
          const fg = rgb(cs.color);
          if (!fg) continue;
          const bg = behind(el);
          const L1 = lum(over(fg, bg)), L2 = lum(bg);
          const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
          if (ratio < 4.5) out.low.push(ratio.toFixed(2) + " " + el.tagName + "." + String(el.className).slice(0, 20) + " " + cs.color + " '" + t.nodeValue.trim().slice(0, 24) + "'");
        }
        out.toggle = !!document.querySelector('#themerow [data-theme-pick="light"].on');
        return out;
      }, PALE);
      const tag = dn + " " + name;
      if (info.theme !== "light" || info.bg !== "rgb(243, 245, 249)") bad.push(tag + ": not light " + JSON.stringify(info));
      if (info.overflow > 1) bad.push(tag + ": sideways overflow " + info.overflow);
      if (info.pale.length) bad.push(tag + ": pale text on white " + info.pale.join(" | "));
      if (info.low.length) bad.push(tag + ": contrast under 4.5 " + info.low.join(" | "));
      if (!info.toggle) bad.push(tag + ": theme toggle missing or not on Light");
      if (errors.length) bad.push(tag + ": " + errors[0]);
    }
    // The toggle switches back to dark and remembers it.
    await page.goto(site + "index.html", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
    await page.evaluate(() => document.querySelector('[data-theme-pick="dark"]').click());
    await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
    await page.waitForTimeout(300);
    const dark = await page.evaluate(() => ({ theme: document.documentElement.getAttribute("data-theme"), saved: localStorage.getItem("desk-theme"), bg: getComputedStyle(document.body).backgroundColor }));
    if (dark.theme !== null || dark.saved !== "dark" || dark.bg !== "rgb(11, 15, 23)") bad.push(dn + ": Dark button did not switch back " + JSON.stringify(dark));
    await ctx.close();
  }
  // With nothing saved the desk starts dark, and Match device follows the device.
  const fresh = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: "light" });
  const fp = await fresh.newPage();
  await fp.goto(site + "index.html", { waitUntil: "domcontentloaded" });
  await fp.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  if (await fp.evaluate(() => document.documentElement.getAttribute("data-theme")) !== null) bad.push("a new visitor should start dark");
  await fp.evaluate(() => localStorage.setItem("desk-theme", "auto"));
  await fp.reload({ waitUntil: "domcontentloaded" });
  await fp.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  if (await fp.evaluate(() => document.documentElement.getAttribute("data-theme")) !== "light") bad.push("Match device should follow a light device");
  await fresh.close();
  await browser.close();
  if (server) server.close();
  if (bad.length) {
    console.log(bad.join("\n"));
    process.exit(1);
  }
  console.log("light mode ok on " + pages.length + " pages");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
