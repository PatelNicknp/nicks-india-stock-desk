/* Every site page at a 390px phone width must not scroll sideways. */
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
  if (file.endsWith(".png")) return "image/png";
  if (file.endsWith(".webmanifest")) return "application/manifest+json";
  if (file.endsWith(".svg")) return "image/svg+xml";
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
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}


/* The Chart Viewer shows "EPS nn" next to the RS chip for a rated stock, green at 80+,
   and no EPS chip for a stock with no rating. */
async function main() {
  const pw = loadPlaywright();
  if (!pw) { console.log("skip: playwright is not installed"); process.exit(2); }
  const rows = fs.readFileSync(path.join(root, "data", "eps_ratings.csv"), "utf8").split("\n").slice(1)
    .map((l) => l.split(",")).filter((c) => c[0]);
  const rated = new Map(rows.filter((c) => c[1] !== "").map((c) => [c[0], Number(c[1])]));
  const server = await serve();
  const port = server.address().port;
  const browser = await pw.chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  await page.goto("http://127.0.0.1:" + port + "/site/chart-viewer.html", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body[data-ready='1']", { timeout: 30000 });
  await page.waitForTimeout(800);
  const bad = [];
  let seenRated = 0, seenBlank = 0;
  for (let i = 0; i < 25 && (seenRated < 3 || seenBlank < 1); i++) {
    const info = await page.evaluate(() => {
      const el = document.getElementById("cveps");
      const rs = document.getElementById("cvrs");
      return {
        ticker: (document.getElementById("cvtk") || {}).textContent || "",
        hidden: !el || el.hidden, text: el ? el.textContent : "", hot: !!(el && el.classList.contains("hot")),
        afterRs: !!(el && rs && rs.nextElementSibling === el),
      };
    });
    const t = String(info.ticker).trim().toUpperCase();
    if (t && rated.has(t)) {
      seenRated++;
      const n = rated.get(t);
      if (info.hidden || info.text !== "EPS " + Math.round(n)) bad.push(t + " expected EPS " + n + " got " + info.text);
      if (info.hot !== (n >= 80)) bad.push(t + " green should be " + (n >= 80));
      if (!info.afterRs) bad.push(t + " EPS chip is not next to the RS chip");
    } else if (t) {
      seenBlank++;
      if (!info.hidden) bad.push(t + " has no rating but shows " + info.text);
    }
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(250);
  }
  await browser.close();
  server.close();
  if (!seenRated) bad.push("no rated stock was checked");
  if (bad.length) { console.log(bad.join("\n")); process.exit(1); }
  console.log("ok rated " + seenRated + " blank " + seenBlank);
}
main().catch((err) => { console.error(err); process.exit(1); });
