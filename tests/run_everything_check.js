/* Today page: Run everything opens the update workflow in a new tab and does not start it. */
const http = require("http");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const URL = "https://github.com/PatelNicknp/nicks-india-stock-desk/actions/workflows/update.yml";

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
  if (file.endsWith(".json")) return "application/json; charset=utf-8";
  if (file.endsWith(".png")) return "image/png";
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

function rgb(c) {
  const m = /rgba?\(([^)]+)\)/.exec(c || "");
  if (!m) return null;
  return m[1].split(",").map((n) => Number(n.trim()))[0];
}

async function openToday(browser, site, extra) {
  const ctx = await browser.newContext(Object.assign({
    viewport: { width: 1280, height: 800 },
  }, extra || {}));
  await ctx.addInitScript(() => { try { localStorage.setItem("desk-theme", "light"); } catch (e) { /* ignore */ } });
  const page = await ctx.newPage();
  const calls = [];
  page.on("request", (req) => {
    const u = req.url();
    if (/api\.github\.com|workflow_dispatch|token|secret/i.test(u)) calls.push(u);
  });
  return { ctx, page, calls };
}

async function ready(page, site) {
  await page.goto(site + "index.html", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body[data-ready='1'], body[data-ready='error']", { timeout: 30000 });
}

async function main() {
  const pw = loadPlaywright();
  if (!pw) {
    console.log("skip: playwright is not installed");
    process.exit(2);
  }
  const server = await serve();
  const site = "http://127.0.0.1:" + server.address().port + "/site/";
  const browser = await pw.chromium.launch({ args: ["--no-sandbox"] });
  const bad = [];
  try {
    const desk = await openToday(browser, site);
    await ready(desk.page, site);
    const info = await desk.page.evaluate((want) => {
      const a = document.getElementById("run-everything");
      const stamp = document.getElementById("last-update");
      const upd = document.querySelector(".hdracts .upd");
      const chip = document.querySelector(".upd");
      const cs = a ? getComputedStyle(a) : null;
      const chipCs = chip ? getComputedStyle(chip) : null;
      return {
        theme: document.documentElement.getAttribute("data-theme"),
        text: a ? a.textContent : "",
        tag: a ? a.tagName : "",
        href: a ? a.href : "",
        target: a ? a.getAttribute("target") : "",
        rel: a ? a.getAttribute("rel") : "",
        onclick: a ? a.getAttribute("onclick") : "missing",
        next: stamp && upd ? upd.textContent.replace(/\s+/g, " ").trim() : "",
        bg: cs ? cs.backgroundColor : "",
        color: cs ? cs.color : "",
        radius: cs ? cs.borderRadius : "",
        weight: cs ? cs.fontWeight : "",
        chipBg: chipCs ? chipCs.backgroundColor : "",
        chipRadius: chipCs ? chipCs.borderRadius : "",
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        missing: Desk.lastUpdateWhen(null),
        blank: Desk.lastUpdateWhen({ updated_pt: "  " }),
        both: Desk.lastUpdateWhen({ updated_pt: "2026-11-11 00:09 IST · 2026-11-10 10:39 PT" }),
        ist: Desk.lastUpdateWhen({ updated_pt: "2026-11-11 16:30 IST" }),
        tito: document.body.innerText.indexOf("Tito Option") >= 0,
        want: want,
      };
    }, URL);
    if (info.theme !== "light") bad.push("theme " + info.theme);
    if (info.text !== "Run everything") bad.push("label " + info.text);
    if (info.tag !== "A") bad.push("tag " + info.tag);
    if (info.href !== URL) bad.push("href " + info.href);
    if (info.target !== "_blank") bad.push("target " + info.target);
    if ((info.rel || "").indexOf("noopener") < 0) bad.push("rel " + info.rel);
    if (info.onclick) bad.push("onclick " + info.onclick);
    if (info.next.indexOf("Last update: ") !== 0) bad.push("stamp " + info.next);
    if (info.next.indexOf("IST") < 0 || info.next.indexOf("PT") < 0) bad.push("zones " + info.next);
    if (info.next.indexOf("not available") >= 0) bad.push("time missing " + info.next);
    if (info.bg !== info.chipBg) bad.push("button bg " + info.bg + " vs chip " + info.chipBg);
    if (info.radius !== "6px" || info.chipRadius !== "6px") bad.push("radius " + info.radius);
    if (String(info.weight) !== "700") bad.push("weight " + info.weight);
    if (rgb(info.bg) !== 255) bad.push("light panel " + info.bg);
    if (rgb(info.color) > 80) bad.push("light text " + info.color);
    if (info.overflow > 1) bad.push("desktop overflow " + info.overflow);
    if (info.missing !== "not available" || info.blank !== "not available") bad.push("blank " + info.missing);
    if (info.both.indexOf("IST") < 0 || info.both.indexOf("PT") < 0) bad.push("format " + info.both);
    if (info.ist.indexOf("IST") < 0 || info.ist.indexOf("PT") >= 0) bad.push("ist only " + info.ist);
    if (info.tito) bad.push("tito button exists");
    await desk.page.evaluate(() => {
      document.getElementById("run-everything").addEventListener("click", (e) => e.preventDefault());
    });
    await desk.page.click("#run-everything");
    if (desk.calls.length) bad.push("page called " + desk.calls.join(", "));
    await desk.ctx.close();

    const phone = await openToday(browser, site, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    await ready(phone.page, site);
    const narrow = await phone.page.evaluate(() => ({
      text: (document.getElementById("run-everything") || {}).textContent || "",
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    }));
    if (narrow.text !== "Run everything") bad.push("phone label " + narrow.text);
    if (narrow.overflow > 1) bad.push("phone overflow " + narrow.overflow);
    await phone.ctx.close();

    const other = await openToday(browser, site);
    await other.page.goto(site + "help.html", { waitUntil: "domcontentloaded" });
    await other.page.waitForSelector("body[data-ready='1'], body[data-ready='error']", { timeout: 30000 });
    const help = await other.page.evaluate(() => ({
      run: !!document.getElementById("run-everything"),
      updated: (document.getElementById("updated") || {}).textContent || "",
    }));
    if (help.run) bad.push("help page has the button");
    if (!help.updated || help.updated === "…") bad.push("help stamp " + help.updated);
    await other.ctx.close();

    const off = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    await off.addInitScript(() => { try { localStorage.setItem("desk-theme", "light"); } catch (e) { /* ignore */ } });
    const offPage = await off.newPage();
    await offPage.route("**/settings.csv", async (route) => {
      const res = await route.fetch();
      const body = (await res.text()).replace("feature.run_everything,True", "feature.run_everything,False");
      await route.fulfill({ status: 200, contentType: "text/csv; charset=utf-8", body: body });
    });
    await ready(offPage, site);
    const hidden = await offPage.evaluate(() => ({
      run: !!document.getElementById("run-everything"),
      updated: !!document.getElementById("updated"),
    }));
    if (hidden.run) bad.push("switch off still shows the button");
    if (!hidden.updated) bad.push("switch off hid the normal stamp");
    await off.close();

    const miss = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    await miss.addInitScript(() => { try { localStorage.setItem("desk-theme", "light"); } catch (e) { /* ignore */ } });
    const missPage = await miss.newPage();
    await missPage.route("**/meta.json", (route) => route.fulfill({ status: 404, contentType: "text/plain", body: "missing" }));
    await ready(missPage, site);
    const gone = await missPage.evaluate(() => {
      const el = document.getElementById("last-update");
      const box = el ? el.parentElement.textContent.replace(/\s+/g, " ").trim() : "";
      return box;
    });
    if (gone !== "Last update: not available") bad.push("missing meta " + gone);
    await miss.close();
  } finally {
    await browser.close();
    server.close();
  }
  if (bad.length) {
    console.log(bad.join("\n"));
    process.exit(1);
  }
  console.log("run everything ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
