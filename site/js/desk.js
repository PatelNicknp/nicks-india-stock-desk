/* Nick's India Stock Desk. Reads published CSVs. No broker calls and no new market requests. */
(function () {
  const UP = "#22C55E";
  const DN = "#EF4444";
  const AM = "#F59E0B";
  const AC = "#7C9CFF";
  const MU = "#8B96AD";
  const TX = "#E6EBF5";
  const RESEARCH = "Research only. Not a recommendation to buy or sell. This desk never places trades. Stocks only, no option contracts.";
  const NAV = [
    ["Overview", [
      ["Today", "index.html", "today"],
      ["FII and DII", "flows.html", "flows"],
      ["Top stocks", "top-stocks.html", "top"],
      ["Buy setups", "buy-setups.html", "buysetups"],
      ["Stock scorecard", "scorecard.html", "scorecard"],
      ["Watchlist and portfolio", "watchlist.html", "watchlist"],
      ["Alerts", "alerts.html", "alerts"],
      ["Backtest", "backtest.html", "backtest"],
    ]],
    ["Charts", [
      ["Chart Viewer", "chart-viewer.html", "chartviewer"],
    ]],
    ["Scanners", [
      ["Growth", "growth.html", "growth"],
      ["Quality", "quality.html", "quality"],
      ["Dividend", "dividend.html", "dividend"],
      ["Liquid stocks", "wheel.html", "wheel"],
      ["VCP", "vcp.html", "vcp"],
      ["CANSLIM", "canslim.html", "canslim"],
      ["Box breakout", "box.html", "box"],
      ["Flag breakout", "flag.html", "flag"],
      ["Qullamaggie breakout", "qullamaggie.html", "qullamaggie"],
      ["Marios breakout", "marios.html", "marios"],
      ["Episodic Pivot", "episodic_pivot.html", "episodic"],
      ["Gap Up", "gap_up.html", "gapup"],
      ["Leaders", "leaders.html", "leaders"],
      ["52-week", "52-week.html", "week52"],
      ["High volume", "high-volume.html", "highvol"],
    ]],
    ["Earnings", [
      ["Calendar", "earnings-calendar.html", "calendar"],
      ["Strength heatmap", "earnings-heatmap.html", "heatmap"],
      ["Report cards", "earnings-cards.html", "cards"],
    ]],
    ["Sentiment", [
      ["Put/call ratio", "put-call.html", "putcall"],
      ["Put and call walls", "walls.html", "walls"],
      ["Analyst ratings", "analysts.html", "analysts"],
      ["Shareholding", "thirteen-f.html", "thirteen"],
      ["India mood", "aaii.html", "aaii"],
      ["Insider trading", "insiders.html", "insiders"],
      ["Headline sentiment", "headlines.html", "headlines"],
      ["Auto vs FMCG", "xly-xlp.html", "xly"],
    ]],
    ["Financials", [
      ["Summary", "financials.html", "financials"],
      ["Earnings tracker", "earnings-tracker.html", "tracker"],
      ["Company financials", "company-financials.html", "company"],
      ["Dividend fundamentals", "dividend-fundamentals.html", "divfund"],
    ]],
    ["Macro", [
      ["Sector rotation", "sector-rotation.html", "rotation"],
      ["Macro screener", "macro.html", "macro"],
      ["Sector macro scores", "sector-macro.html", "secmacro"],
      ["Historical P/E", "historical-pe.html", "histpe"],
    ]],
    ["Technicals", [
      ["52-week breakouts", "breakouts.html", "breakouts"],
      ["Trends", "trends.html", "trends"],
      ["Pullbacks", "pullbacks.html", "pullbacks"],
      ["Gainers and losers", "gainers.html", "gainers"],
      ["Breadth", "breadth.html", "breadth"],
      ["Sector performance", "sector-performance.html", "secperf"],
      ["Heatmaps", "heatmaps.html", "heatmaps"],
    ]],
    ["System", [
      ["Data updates", "updates.html", "updates"],
      ["Help", "help.html", "help"],
    ]],
  ];


  // Light mode. Dark is the default. The choice (dark, light, or auto to match the device)
  // is kept in localStorage under desk-theme. CSS colours swap through variables in
  // desk.css. Colours written into the page by the scripts are swapped by themeRemap,
  // and chart colours go through tc. Turn the toggle off with feature.light_mode.
  const LIGHT = {"#0B0F17": "#F3F5F9", "#121826": "#FFFFFF", "#0F1420": "#F7F8FB", "#1A2236": "#E8EDF7", "#1E293B": "#DDE3EC", "#161E2E": "#E8EDF7", "#2A3550": "#C5CEDD", "#243049": "#D3DAE6", "#3A4560": "#B3BDCE", "#E6EBF5": "#111827", "#C3CBDB": "#374151", "#C9D2E3": "#374151", "#AEB7C8": "#4B5563", "#8B96AD": "#586174", "#5B6680": "#565E6C", "#7C9CFF": "#3355D6", "#F59E0B": "#9A4A06", "#EF4444": "#B42318", "#22C55E": "#12703A", "#D6A64A": "#865205", "RGBA(0,0,0,.35)": "rgba(15,23,42,.12)", "RGBA(0,0,0,.5)": "rgba(15,23,42,.35)", "RGBA(11,15,23,.9)": "rgba(255,255,255,.94)", "RGBA(11,15,23,.78)": "rgba(255,255,255,.86)", "RGBA(11,15,23,.74)": "rgba(255,255,255,.84)", "RGBA(11,15,23,.55)": "rgba(255,255,255,.7)", "RGBA(42,53,80,.9)": "rgba(148,163,184,.75)", "RGBA(42,53,80,.8)": "rgba(148,163,184,.7)", "RGBA(42,53,80,.7)": "rgba(148,163,184,.55)", "#283146": "#E3E8F0", "#7F1D1D": "#FECACA", "#B91C1C": "#FCA5A5", "#14532D": "#DCFCE7", "#166534": "#BBF7D0", "#38BDF8": "#0369A1", "#E879F9": "#A21CAF", "#A78BFA": "#6D28D9", "#FBBF24": "#9A4A06", "#FB923C": "#C2410C", "#F472B6": "#BE185D", "#34D399": "#047857", "#2DD4BF": "#0F766E", "#C084FC": "#7E22CE", "#FB7185": "#BE123C", "#94A3B8": "#526070", "#1F9D55": "#12703A", "#D14343": "#B42318", "RGBA(34,197,94,.65)": "rgba(22,163,74,.45)", "RGBA(239,68,68,.65)": "rgba(220,38,38,.4)", "RGBA(34,197,94,.45)": "rgba(22,163,74,.4)", "RGBA(239,68,68,.45)": "rgba(220,38,38,.35)", "RGBA(124,156,255,.10)": "rgba(51,85,214,.10)"};
  const THEME_KEY = "desk-theme";
  const THEMES = ["dark", "light", "auto"];
  function storedTheme() {
    try { const v = localStorage.getItem(THEME_KEY); if (THEMES.indexOf(v) >= 0) return v; } catch (e) { /* storage can be blocked */ }
    return "";
  }
  function deviceLight() {
    try { return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches); } catch (e) { return false; }
  }
  function resolveTheme(choice) {
    return choice === "light" || (choice === "auto" && deviceLight()) ? "light" : "dark";
  }
  let themeChoice = storedTheme() || "dark";
  let THEME = resolveTheme(themeChoice);
  function setThemeAttr() {
    const root = document.documentElement;
    if (THEME === "light") root.setAttribute("data-theme", "light");
    else root.removeAttribute("data-theme");
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", THEME === "light" ? LIGHT["#0B0F17"] : "#0B0F17");
  }
  setThemeAttr();
  const COLOR_RE = /#[0-9a-fA-F]{6}\b|rgba?\([^)]*\)/g;
  function hex2(n) { return ("0" + Math.max(0, Math.min(255, Number(n) || 0)).toString(16)).slice(-2).toUpperCase(); }
  function lightOf(m) {
    const key = m.toUpperCase().replace(/\s+/g, "");
    if (LIGHT[key]) return LIGHT[key];
    const rgb = /^RGB\((\d+),(\d+),(\d+)\)$/.exec(key);
    if (rgb) { const h = "#" + hex2(rgb[1]) + hex2(rgb[2]) + hex2(rgb[3]); if (LIGHT[h]) return LIGHT[h]; }
    const rgba = /^RGBA\((\d+),(\d+),(\d+),([\d.]+)\)$/.exec(key);
    if (rgba) {
      const a = String(Number(rgba[4])).replace(/^0\./, ".");
      const k2 = "RGBA(" + rgba[1] + "," + rgba[2] + "," + rgba[3] + "," + a + ")";
      if (LIGHT[k2]) return LIGHT[k2];
    }
    return m;
  }
  function tc(c) {
    if (THEME !== "light" || typeof c !== "string") return c;
    return c.replace(COLOR_RE, lightOf);
  }
  // Swap colours inside a chart config in place. Functions and canvases are left alone.
  function tcDeep(obj, seen) {
    if (THEME !== "light" || !obj || typeof obj !== "object") return obj;
    seen = seen || new Set();
    if (seen.has(obj) || (typeof Node !== "undefined" && obj instanceof Node)) return obj;
    seen.add(obj);
    const keys = Array.isArray(obj) ? obj.keys() : Object.keys(obj);
    for (const k of keys) {
      const v = obj[k];
      if (typeof v === "string") obj[k] = tc(v);
      else if (v && typeof v === "object" && (Array.isArray(v) || Object.getPrototypeOf(v) === Object.prototype)) tcDeep(v, seen);
    }
    return obj;
  }
  const THEME_ATTRS = ["style", "fill", "stroke", "stop-color"];
  function remapEl(el) {
    if (!el || el.nodeType !== 1) return;
    THEME_ATTRS.forEach((a) => {
      const v = el.getAttribute(a);
      if (v) { const nv = tc(v); if (nv !== v) el.setAttribute(a, nv); }
    });
  }
  function remapTree(root) {
    if (!root || root.nodeType !== 1) return;
    remapEl(root);
    root.querySelectorAll("[style],[fill],[stroke],[stop-color]").forEach(remapEl);
  }
  let themeObserver = null;
  function themeRemap() {
    if (THEME !== "light" || themeObserver || typeof MutationObserver === "undefined") return;
    remapTree(document.body);
    themeObserver = new MutationObserver((list) => {
      list.forEach((m) => {
        if (m.type === "attributes") remapEl(m.target);
        else m.addedNodes.forEach((n) => remapTree(n));
      });
    });
    themeObserver.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: THEME_ATTRS });
  }
  function applyTheme() {
    if (!featureOn("feature.light_mode")) themeChoice = "dark";
    else if (!storedTheme()) {
      const row = SETTINGS.find((r) => r.setting === "light_mode.default_theme");
      const d = row ? String(row.value || "").trim().toLowerCase() : "";
      themeChoice = THEMES.indexOf(d) >= 0 ? d : "dark";
    }
    if (themeChoice === "auto" && !matchDeviceOn()) themeChoice = "dark";
    THEME = resolveTheme(themeChoice);
    setThemeAttr();
    if (typeof Chart !== "undefined") {
      Chart.defaults.color = tc(MU);
      Chart.defaults.borderColor = tc("#1E293B");
    }
    themeRemap();
  }
  function matchDeviceOn() {
    const row = SETTINGS.find((r) => r.setting === "light_mode.match_device_option");
    return !row || String(row.value).toLowerCase() !== "false";
  }
  function themeToggleHtml() {
    if (!featureOn("feature.light_mode")) return "";
    const b = (v, label) => '<button type="button" data-theme-pick="' + v + '"' + (themeChoice === v ? ' class="on" aria-pressed="true"' : ' aria-pressed="false"') + ">" + esc(label) + "</button>";
    return '<div class="themerow" id="themerow"><span class="lab">Theme</span><div class="seg">' +
      b("dark", "Dark") + b("light", "Light") + (matchDeviceOn() ? b("auto", "Match device") : "") + "</div></div>";
  }
  function wireThemeToggle() {
    const row = document.getElementById("themerow");
    if (row) {
      row.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-theme-pick]");
        if (!btn) return;
        const v = btn.getAttribute("data-theme-pick");
        try { localStorage.setItem(THEME_KEY, v); } catch (err) { /* storage can be blocked */ }
        if (resolveTheme(v) === THEME) {
          themeChoice = v;
          row.querySelectorAll("[data-theme-pick]").forEach((x) => {
            const on = x.getAttribute("data-theme-pick") === v;
            x.classList.toggle("on", on);
            x.setAttribute("aria-pressed", on ? "true" : "false");
          });
          return;
        }
        location.reload();
      });
    }
    if (themeChoice === "auto" && window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: light)");
      const onChange = () => { if (resolveTheme("auto") !== THEME) location.reload(); };
      if (mq.addEventListener) mq.addEventListener("change", onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
  }
  // Lightweight Charts with the theme colours applied to the chart, its series, and its data.
  function tvCreate(host, opts) {
    const chart = LightweightCharts.createChart(host, tcDeep(opts));
    if (THEME !== "light") return chart;
    const add = chart.addSeries.bind(chart);
    chart.addSeries = (type, o, pane) => {
      const series = pane == null ? add(type, tcDeep(o || {})) : add(type, tcDeep(o || {}), pane);
      const setData = series.setData.bind(series);
      series.setData = (data) => setData((data || []).map((p) => (p && typeof p.color === "string" ? Object.assign({}, p, { color: tc(p.color) }) : p)));
      const line = series.createPriceLine.bind(series);
      series.createPriceLine = (o2) => line(tcDeep(Object.assign({}, o2)));
      const apply = series.applyOptions.bind(series);
      series.applyOptions = (o2) => apply(tcDeep(Object.assign({}, o2)));
      return series;
    };
    return chart;
  }

  const cache = new Map();
  const charts = [];
  const SPD = {
    "^CNXIT": "IT", "^NSEBANK": "Bank", "^CNXAUTO": "Auto", "^CNXPHARMA": "Pharma",
    "^CNXFMCG": "FMCG", "^CNXMETAL": "Metal", "^CNXREALTY": "Realty", "^CNXENERGY": "Energy",
    "^CNXMEDIA": "Media", "^CNXPSUBANK": "PSU Bank", "^CNXFIN": "Financials", "^CNXINFRA": "Infra",
  };

  function csvUrl(name) {
    if (location.hostname.endsWith("github.io")) {
      return "https://raw.githubusercontent.com/PatelNicknp/nicks-india-stock-desk/main/data/" + name;
    }
    return new URL("../data/" + name, location.href).href;
  }

  function loadCsv(name) {
    if (!cache.has(name)) {
      cache.set(name, new Promise((resolve, reject) => {
        if (typeof Papa === "undefined") {
          reject(new Error("PapaParse did not load"));
          return;
        }
        Papa.parse(csvUrl(name), {
          download: true,
          header: true,
          skipEmptyLines: "greedy",
          complete: (res) => {
            const fatal = (res.errors || []).filter((e) => e.code !== "UndetectableDelimiter");
            if ((!res.data || !res.data.length) && fatal.length) {
              reject(new Error(name + ": " + fatal[0].message));
              return;
            }
            resolve((res.data || []).map(cleanRow));
          },
          error: (err) => reject(err instanceof Error ? err : new Error(String(err))),
        });
      }));
    }
    return cache.get(name);
  }

  function candleGroup(ticker) {
    const text = String(ticker || "").toUpperCase();
    if (text.charAt(0) === "^") return "_indexes";
    const c = text.charAt(0);
    if (c >= "A" && c <= "Z") return c;
    return "0";
  }

  function gunzipResponse(res) {
    if (!res.body || typeof DecompressionStream === "undefined") {
      throw new Error("gzip");
    }
    return new Response(res.body.pipeThrough(new DecompressionStream("gzip"))).text();
  }

  function parseCsvText(text) {
    return new Promise((resolve, reject) => {
      Papa.parse(text, {
        header: true,
        skipEmptyLines: "greedy",
        complete: (res) => resolve((res.data || []).map(cleanRow)),
        error: (err) => reject(err instanceof Error ? err : new Error(String(err))),
      });
    });
  }

  function loadLetterBars(group) {
    const key = "ohlc/" + group + ".csv.gz";
    if (!cache.has(key)) {
      const job = fetch(csvUrl(key)).then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return gunzipResponse(res);
      }).then(parseCsvText).catch((err) => {
        cache.delete(key);
        throw err;
      });
      cache.set(key, job);
    }
    return cache.get(key);
  }

  function loadTickerBars(ticker) {
    const want = String(ticker || "").trim().toUpperCase();
    return loadLetterBars(candleGroup(want)).then((rows) =>
      rows.filter((r) => String(r.ticker || "").trim().toUpperCase() === want)
    ).catch(() => loadCsv("ohlc/" + want + ".csv"));
  }

  function cleanRow(row) {
    const o = {};
    Object.keys(row).forEach((k) => {
      const key = String(k).replace(/^\uFEFF/, "").trim();
      let v = row[k];
      if (v == null) { o[key] = ""; return; }
      v = String(v).trim();
      const low = v.toLowerCase();
      if (!v || low === "nan" || low === "none" || low === "null" || low === "nat") o[key] = "";
      else o[key] = v;
    });
    return o;
  }

  function isBlank(v) {
    return v == null || String(v).trim() === "";
  }
  function num(v) {
    if (isBlank(v)) return null;
    const n = Number(String(v).replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function na() { return '<span class="na">–</span>'; }
  function fmt(v, d) {
    const n = num(v);
    if (n == null) return null;
    return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function compact(v) {
    const n = num(v);
    if (n == null) return null;
    const a = Math.abs(n);
    const sign = n < 0 ? "-" : "";
    if (a >= 1e12) return sign + (a / 1e12).toFixed(1) + "T";
    if (a >= 1e9) return sign + (a / 1e9).toFixed(1) + "B";
    if (a >= 1e6) return sign + (a / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return sign + (a / 1e3).toFixed(1) + "K";
    return fmt(n, a >= 100 ? 0 : 2);
  }
  function band(s) {
    if (s >= 12) return "#166534";
    if (s >= 9) return "#14532D";
    if (s >= 5) return "#283146";
    if (s >= 1) return "#7F1D1D";
    return "#B91C1C";
  }
  function ptsColor(v) {
    if (v == null) return null;
    if (v >= 2) return "#166534";
    if (v >= 1) return "#14532D";
    if (v > -1) return "#283146";
    if (v > -2) return "#7F1D1D";
    return "#B91C1C";
  }
  function retColor(n) {
    if (n == null) return MU;
    if (n > 0) return UP;
    if (n < 0) return DN;
    return TX;
  }
  function formatUpdated(s) {
    const text = String(s || "");
    const re = /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?:\s*(IST|PT|ET))?/g;
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const bits = [];
    let m;
    while ((m = re.exec(text))) {
      let h = Number(m[4]);
      const ap = h >= 12 ? "PM" : "AM";
      h = h % 12 || 12;
      const zone = m[6] || (bits.length ? "PT" : "IST");
      bits.push(months[Number(m[2]) - 1] + " " + Number(m[3]) + ", " + h + ":" + m[5] + " " + ap + " " + zone);
    }
    if (!bits.length) return text || "n/a";
    return bits.join(" · ");
  }
  function latestChecked(rows) {
    let best = "";
    (rows || []).forEach((r) => { if ((r.checked_pt || "") > best) best = r.checked_pt; });
    return best;
  }
  function realRows(rows) {
    return (rows || []).filter((r) => r.data_status !== "MISSING");
  }
  function statusOf(rows) {
    const bad = (rows || []).find((r) => r.data_status === "MISSING" || r.data_status === "PARTIAL");
    return bad || null;
  }
  function banner() {
    // Loud PARTIAL and MISSING banners are retired. A failed file load uses .banner.miss in boot.
    return "";
  }
  function feedHtml(rows) {
    const bad = statusOf(rows);
    if (!bad || bad.data_status !== "MISSING") return "";
    const note = bad.note ? " · " + bad.note : "";
    return '<div class="feed">' + esc(bad.data_status + note) + "</div>";
  }
  function placeFeed(box, rows) {
    if (!box) return;
    const html = feedHtml(rows);
    if (html) box.insertAdjacentHTML("beforeend", html);
  }
  function noteOf(rows) {
    const r = (rows || []).find((x) => x.note);
    return r ? r.note : "";
  }

  function scoreHtml(v) {
    const n = num(v);
    if (n == null) return na();
    const shown = Number.isInteger(n) ? String(n) : fmt(n, 1);
    return '<span class="scorepill" style="background:' + band(n) + '">' + esc(shown) + "</span>";
  }
  function scoreFill(v) {
    const n = num(v);
    if (n == null) return na();
    const shown = Number.isInteger(n) ? String(n) : fmt(n, 1);
    return '<span class="scorefill" style="background:' + band(n) + '">' + esc(shown) + "</span>";
  }
  function tickerHtml(v) {
    if (isBlank(v)) return na();
    return '<a class="tk" href="scorecard.html?t=' + encodeURIComponent(v) + '">' + esc(v) + "</a>";
  }
  function etfHtml(v) {
    if (isBlank(v)) return na();
    return '<span class="tk">' + esc(v) + "</span>";
  }
  function colored(text, color, lite) {
    if (isBlank(text)) return na();
    return '<span class="pill' + (lite ? " lite" : "") + '" style="color:' + color + '">' + esc(text) + "</span>";
  }
  function verdictHtml(v) {
    const map = { BUY: UP, HOLD: AM, AVOID: DN, "Not scored yet": MU };
    return colored(v, map[v] || TX);
  }
  function trendHtml(v) {
    const map = {
      Uptrend: UP, Downtrend: DN, Extended: AM, Sideways: MU, Mixed: MU,
      "In entry zone": AC, Breakout: TX, Pullback: TX,
    };
    return colored(v, map[v] || TX, true);
  }
  function setupHtml(v) {
    const map = { "BROKEN OUT today": UP, READY: AM, WATCHING: MU, "IN TRADE": AC, CLOSED: MU, SELL: DN, "SELL 1/3": AM, EXIT: DN, STOPPED: DN, HOLD: MU,
      "EP TODAY": UP, "EP FADED": AM, "DELAYED WATCH": MU, "SELL PART": AM, "NO FOLLOW-THROUGH": AM, "Too wide, skip": DN, OK: MU };
    return colored(v, map[v] || TX);
  }
  function freshHtml(v) {
    const map = { FRESH: MU, PARTIAL: AM, STALE: DN, OK: MU, CACHED: MU, MISSING: AM };
    const label = v === "FRESH" ? "Fresh" : v;
    return colored(label, map[v] || TX, true);
  }
  function passHtml(v) {
    const s = String(v || "");
    if (isBlank(s)) return na();
    const up = s.toUpperCase();
    if (up === "PASS" || s === "yes" || s === "strict") return colored(s, UP);
    if (up === "FAIL" || s === "no") return colored(s, DN);
    if (s === "soft") return colored(s, AM);
    return esc(s);
  }
  function signedPts(n) {
    if (n > 0) return "+" + (Number.isInteger(n) ? String(n) : fmt(n, 1));
    if (n < 0) return "−" + (Number.isInteger(n) ? String(Math.abs(n)) : fmt(Math.abs(n), 1));
    return "0";
  }
  function pointsHtml(v) {
    const n = num(v);
    if (n == null) return na();
    const bg = ptsColor(n) || "#283146";
    return '<span class="pts" style="background:' + bg + '">' + esc(signedPts(n)) + "</span>";
  }
  function pointsLabelHtml(v) {
    if (isBlank(v) || v === "n/a") return na();
    const map = { "plus 2": 2, "plus 1": 1, "zero": 0, "minus 1": -1, "minus 2": -2 };
    if (Object.prototype.hasOwnProperty.call(map, v)) return pointsHtml(map[v]);
    const n = num(v);
    if (n == null) return na();
    return pointsHtml(n);
  }
  function gradeHtml(v) {
    const fills = { A: "#166534", B: "#14532D", C: "#283146", D: "#7F1D1D", F: "#B91C1C" };
    if (isBlank(v)) return na();
    return '<span class="gradechip" style="background:' + (fills[v] || "#283146") + '">' + esc(v) + "</span>";
  }
  function holdHtml(v) {
    const map = { "Below stop": DN, Weakening: AM, "Earnings soon": AC, "On track": MU };
    return colored(v, map[v] || TX);
  }
  function kindHtml(v) {
    const map = {
      score_jump: ["Score jump", "#C3CBDB"],
      verdict_change: ["Verdict change", AM],
      score_cross: ["Crossed buy line", "#C3CBDB"],
      entry_zone: ["Entry zone", AC],
      breakout: ["Breakout", UP],
      new_stock: ["New stock", "#C3CBDB"],
      info: ["Note", MU],
    };
    const pair = map[v] || [v, "#C3CBDB"];
    return colored(pair[0], pair[1], true);
  }
  function zoneHtml(v) {
    const map = { Fear: DN, Greed: UP, Neutral: AM, "Risk on": UP, "Risk off": DN };
    return colored(v, map[v] || AM);
  }
  function toneHtml(v) {
    const n = num(v);
    if (n == null) return na();
    const bg = n > 0 ? "#14532D" : n < 0 ? "#7F1D1D" : "#283146";
    return '<span class="pts" style="background:' + bg + '">' + esc(signedPts(n)) + "</span>";
  }
  function flagHtml(v, col) {
    if (isBlank(v)) return na();
    const yes = (col && col.yes) || UP;
    const no = (col && col.no) || MU;
    const n = num(v);
    if (n === 1 || v === "yes" || v === "true") return colored("Yes", yes);
    if (n === 0 || v === "no" || v === "false") return colored("No", no);
    return esc(v);
  }
  function moneyHtml(v, d, colorRet) {
    const n = num(v);
    if (n == null) return na();
    const sign = n < 0 ? "-₹" : (colorRet && n > 0 ? "+₹" : "₹");
    const text = sign + fmt(Math.abs(n), d == null ? 2 : d);
    if (!colorRet) return esc(text);
    return '<span style="color:' + retColor(n) + '">' + esc(text) + "</span>";
  }
  function pctHtml(v, d, colorRet) {
    const n = num(v);
    if (n == null) return na();
    const text = (colorRet && n > 0 ? "+" : "") + fmt(n, d == null ? 2 : d) + "%";
    if (!colorRet) return esc(text);
    return '<span style="color:' + retColor(n) + '">' + esc(text) + "</span>";
  }
  function heatPct(v, d) {
    const n = num(v);
    if (n == null) return na();
    const mag = Math.min(Math.abs(n) / 5, 1);
    const bg = n > 0 ? "rgba(34,197,94," + (0.18 + mag * 0.55) + ")" : n < 0 ? "rgba(239,68,68," + (0.18 + mag * 0.55) + ")" : "transparent";
    const text = (n > 0 ? "+" : "") + fmt(n, d == null ? 1 : d) + "%";
    return '<span class="heat" style="background:' + bg + '">' + esc(text) + "</span>";
  }
  function distHtml(v) {
    const n = num(v);
    if (n == null) return na();
    const color = n > 0 ? AM : n < 0 ? DN : UP;
    return '<span style="color:' + color + '">' + esc(fmt(n, 2) + "%") + "</span>";
  }

  function cell(row, col) {
    const v = row[col.key];
    const d = col.dec == null ? 2 : col.dec;
    switch (col.kind) {
      case "ticker": return tickerHtml(v);
      case "etf": return etfHtml(v);
      case "score": return scoreFill(v);
      case "scorejump": {
        const a = isBlank(row.score_prev) ? na() : esc(String(row.score_prev).replace(/\.0$/, ""));
        const b = isBlank(row.score) ? na() : esc(String(row.score).replace(/\.0$/, ""));
        return a + " → " + b;
      }
      case "verdict": return verdictHtml(v);
      case "pending": {
        if (String(v || "").toLowerCase() !== "yes") return "";
        return '<span class="pill" style="color:#8B96AD">Financials pending</span>';
      }
      case "trend": return trendHtml(v);
      case "quad": {
        const map = { Leading: "#22C55E", Weakening: "#F59E0B", Lagging: "#EF4444", Improving: "#7C9CFF" };
        return colored(v, map[v] || TX, true);
      }
      case "setup": return setupHtml(v);
      case "fresh": return freshHtml(v);
      case "pass": return passHtml(v);
      case "points": return pointsHtml(v);
      case "plabel": return pointsLabelHtml(v);
      case "grade": return gradeHtml(v);
      case "hold": return holdHtml(v);
      case "kind": return kindHtml(v);
      case "zone": return zoneHtml(v);
      case "tone": return toneHtml(v);
      case "signal": return toneHtml(v);
      case "flag": return flagHtml(v, col);
      case "owns": {
        if (v === "yes") return '<span style="color:#F59E0B;font-weight:700">yes</span>';
        if (v === "no") return '<span style="color:#5B6680">no</span>';
        return na();
      }
      case "delta": {
        const n = num(v);
        if (n == null) return na();
        const text = n > 0 ? "+" + fmt(n, d) : (n < 0 ? "−" + fmt(Math.abs(n), d) : "0");
        return '<span style="color:' + retColor(n) + '">' + esc(text) + "</span>";
      }
      case "money": return moneyHtml(v, d, !!col.color);
      case "compact": return isBlank(v) ? na() : esc(compact(v));
      case "dollars": {
        const c = compact(v);
        if (c == null) return na();
        const n = num(v);
        return esc((n < 0 ? "-₹" : "₹") + String(c).replace(/^-/, ""));
      }
      case "pct": return pctHtml(v, d, col.color === true);
      case "multiple": {
        const n = num(v);
        if (n == null || Math.abs(n) > 500) return na();
        return esc(fmt(n, d));
      }
      case "ratiox": {
        const n = num(v);
        if (n == null) return na();
        const text = (n >= 10 ? fmt(n, 0) : fmt(n, 1)) + "x";
        const color = n >= 5 ? AM : n >= 2 ? UP : TX;
        return '<span style="color:' + color + ';font-weight:700">' + esc(text) + "</span>";
      }
      case "codesc": {
        const name = isBlank(v) ? "" : '<span class="coname">' + esc(v) + "</span>";
        const desc = isBlank(row.description) ? "" : '<span class="codesc" title="' + esc(row.description) + '">' + esc(row.description) + "</span>";
        const flag = String(row.split_check || "").toLowerCase() === "yes"
          ? '<span class="pill lite" style="color:#F59E0B" title="The price jumped more than 35% in one day in the last 50 sessions. That is usually a split or bonus, so the volume ratio may be too high.">Split or bonus?</span>' : "";
        if (!name && !desc && !flag) return na();
        return '<span class="cobox">' + name + desc + flag + "</span>";
      }
      case "updown": {
        const s = String(v || "").toLowerCase();
        if (s === "up") return '<span class="pill" style="color:' + UP + '">' + (col.short ? "Buying" : "Up · buying") + "</span>";
        if (s === "down") return '<span class="pill" style="color:' + DN + '">' + (col.short ? "Selling" : "Down · selling") + "</span>";
        if (s === "flat") return '<span class="pill" style="color:' + MU + '">Flat</span>';
        return na();
      }
      case "abovema": {
        const s = String(v || "").toLowerCase();
        if (s === "yes") return '<span style="color:' + UP + '">Above</span>';
        if (s === "no") return '<span style="color:' + DN + '">Below</span>';
        return na();
      }
      case "volx": {
        const n = num(v);
        if (n == null) return na();
        const text = fmt(n, d);
        return n >= 1.5 ? '<span style="color:#22C55E;font-weight:700">' + esc(text) + "</span>" : esc(text);
      }
      case "retrace": {
        const n = num(v);
        if (n == null) return na();
        const color = n >= 50 ? AM : TX;
        return '<span style="color:' + color + '">' + esc(fmt(n, d) + "%") + "</span>";
      }
      case "strengthbar": {
        const n = num(v);
        if (n == null) return na();
        const w = Math.max(4, Math.min(72, n * 0.72));
        return '<span class="bar" style="width:' + w + 'px"></span>' + esc(fmt(n, 0));
      }
      case "rangepos": {
        const n = num(v);
        if (n == null) return na();
        const clamped = Math.max(0, Math.min(100, n));
        const w = Math.max(0, Math.round(clamped / 100 * 88));
        const color = clamped >= 95 ? UP : clamped <= 15 ? DN : AC;
        return '<span class="track" title="' + esc(fmt(n, 0)) + '"><span class="fill" style="width:' + w + 'px;background:' + color + '"></span></span> ' + esc(fmt(n, 0));
      }
      case "daybar": {
        const n = num(v);
        if (n == null) return na();
        const w = Math.max(4, Math.min(88, Math.abs(n) / 3 * 88));
        const color = n >= 0 ? "#1F9D55" : "#D14343";
        return '<span class="track"><span class="fill" style="width:' + w + 'px;background:' + color + '"></span></span>';
      }
      case "shortdate": {
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v || ""));
        if (!m) return isBlank(v) ? na() : esc(v);
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        return esc(months[Number(m[2]) - 1] + " " + Number(m[3]));
      }
      case "fy": {
        const m = /^(\d{4})/.exec(String(v || ""));
        return m ? esc("FY" + m[1].slice(2)) : na();
      }
      case "of8": {
        const m = String(v || "").match(/(\d+)\s*of\s*(\d+)/i);
        if (m) return esc(m[1] + "/" + m[2]);
        return isBlank(v) ? na() : esc(v);
      }
      case "itrend": {
        const s = String(v || "").toLowerCase();
        if (!s) return na();
        const color = s === "up" ? UP : s === "down" ? DN : MU;
        return '<span style="color:' + color + '">' + esc(v) + "</span>";
      }
      case "market": {
        const word = marketWord(v);
        if (!word) return na();
        return '<span style="color:' + marketColor(word) + ';font-weight:700">' + esc(word) + "</span>";
      }
      case "shares": {
        const sn = num(v);
        if (sn == null) return na();
        return esc(Math.round(sn).toLocaleString("en-US"));
      }
      case "heatpct": return heatPct(v, d);
      case "dist": return distHtml(v);
      case "num": {
        if (num(v) == null) return na();
        const text = fmt(v, d);
        if (col.tone === "stop") return '<span style="color:#EF4444">' + esc(text) + "</span>";
        if (col.tone === "target") return '<span style="color:#22C55E">' + esc(text) + "</span>";
        return esc(text);
      }
      case "count": {
        const cn = num(v);
        if (cn == null) return na();
        const text = fmt(cn, 0);
        if (cn > 0 && col.up) return '<span style="color:' + col.up + ';font-weight:700">' + esc(text) + "</span>";
        return esc(text);
      }
      case "side": {
        const s = String(v || "").toLowerCase();
        if (s === "call") return '<span style="color:#22C55E;font-weight:700">Call</span>';
        if (s === "put") return '<span style="color:#EF4444;font-weight:700">Put</span>';
        return isBlank(v) ? na() : esc(v);
      }
      case "result": {
        const s = String(v || "").toLowerCase();
        if (!s) return na();
        const color = s === "beat" ? UP : s === "miss" ? DN : MU;
        return '<span style="color:' + color + '">' + esc(v) + "</span>";
      }
      case "earnlabel": {
        const s = String(v || "").toLowerCase();
        if (!s) return na();
        let color = TX;
        if (s.indexOf("incomplete") >= 0) color = "#D6A64A";
        else if (s.indexOf("miss") >= 0) color = DN;
        else if (s.indexOf("beat") >= 0) color = UP;
        else if (s.indexOf("inline") >= 0 || s.indexOf("in line") >= 0) color = MU;
        return '<span style="color:' + color + '">' + esc(v) + "</span>";
      }
      case "surprise": {
        const n = num(v);
        if (n == null) return na();
        const sig = num(row.signal);
        const color = sig == null ? MU : sig > 0 ? UP : sig < 0 ? DN : MU;
        const body = compact(Math.abs(n));
        const sign = n > 0 ? "+" : n < 0 ? "−" : "";
        return '<span style="color:' + color + '">' + esc(sign + body) + "</span>";
      }
      case "signedcompact": {
        const n = num(v);
        if (n == null) return na();
        const body = compact(Math.abs(n));
        const sign = n > 0 ? "+" : n < 0 ? "−" : "";
        return '<span style="color:' + retColor(n) + '">' + esc(sign + body) + "</span>";
      }
      case "onoff": {
        const s = String(v || "").toLowerCase();
        if (s === "true" || s === "yes" || s === "1") return '<span style="color:#22C55E">On</span>';
        if (s === "false" || s === "no" || s === "0") return '<span style="color:#8B96AD">Off</span>';
        return isBlank(v) ? na() : esc(v);
      }
      case "checked": return isBlank(v) ? na() : esc(formatUpdated(v));
      case "item": return isBlank(v) ? na() : '<span style="font-weight:700;color:#E6EBF5">' + esc(v) + "</span>";
      case "muted": return isBlank(v) ? na() : '<span style="color:#8B96AD">' + esc(v) + "</span>";
      case "date": {
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v || ""));
        if (!m) return isBlank(v) ? na() : esc(v);
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        return esc(months[Number(m[2]) - 1] + " " + Number(m[3]) + ", " + m[1]);
      }
      case "ownpts": {
        const sector = String(row.note || "").toLowerCase().indexOf("sector") >= 0;
        if (sector || isBlank(v)) {
          return na() + (sector ? ' <span class="tag">sector used</span>' : "");
        }
        return pointsHtml(v);
      }
      case "owncap": {
        const n = num(v);
        if (n == null) return na();
        if (n >= 100 || String(row.note || "").toLowerCase().indexOf("capped") >= 0) {
          return '<span style="color:#8B96AD" title="Dash = not shown. The free source counts some holders twice, so the total can top 100%.">–</span>';
        }
        return esc(fmt(n, d) + "%");
      }
      default:
        return isBlank(v) ? na() : esc(v);
    }
  }

  function align(col) {
    if (col.align) return col.align;
    if (["num", "pct", "money", "compact", "dist", "heatpct", "shares", "ratiox"].indexOf(col.kind) >= 0) return "num";
    if (["score", "points", "plabel", "grade", "flag", "tone", "signal"].indexOf(col.kind) >= 0) return "c";
    return "";
  }

  function compare(a, b, col, dir) {
    const va = a[col.key];
    const vb = b[col.key];
    const numeric = ["num", "pct", "money", "compact", "dollars", "dist", "score", "points", "tone", "signal", "flag", "heatpct", "delta", "multiple", "volx", "retrace", "strengthbar", "daybar", "rangepos", "scorejump", "count", "signedcompact", "of8", "owncap", "ratiox"].indexOf(col.kind) >= 0;
    let c = 0;
    if (numeric) {
      const pull = (value) => {
        if (col.kind === "of8") {
          const m = String(value || "").match(/(\d+)/);
          return m ? Number(m[1]) : null;
        }
        if (col.kind === "owncap") {
          const n = num(value);
          if (n != null && n >= 100) return null;
          return n;
        }
        return num(value);
      };
      const na_ = pull(va);
      const nb_ = pull(vb);
      if (na_ == null && nb_ == null) return 0;
      if (na_ == null) return 1;
      if (nb_ == null) return -1;
      c = col.abs ? Math.abs(na_) - Math.abs(nb_) : na_ - nb_;
    } else {
      const ea = String(va == null ? "" : va).trim();
      const eb = String(vb == null ? "" : vb).trim();
      if (!ea && !eb) return 0;
      if (!ea) return 1;
      if (!eb) return -1;
      c = ea.localeCompare(eb, undefined, { numeric: true, sensitivity: "base" });
    }
    return dir === "asc" ? c : -c;
  }

  function marketWord(text) {
    const s = String(text || "").trim();
    if (!s || s.toLowerCase() === "not verified") return "";
    const u = s.toUpperCase();
    if (u.indexOf("UPTREND") === 0 || u.indexOf("CONFIRM") === 0 || u.indexOf("UP") === 0) return "Uptrend";
    if (u.indexOf("UNDER") === 0 || u.indexOf("MIXED") === 0) return "Under pressure";
    if (u.indexOf("CORRECT") === 0 || u.indexOf("DOWN") === 0) return "Correction";
    return "";
  }
  function marketColor(word) {
    if (word === "Uptrend") return "#22C55E";
    if (word === "Under pressure") return "#F59E0B";
    if (word === "Correction") return "#EF4444";
    return "#8B96AD";
  }

  let expandSlot = null;
  function pricePanel(sub) {
    return '<div class="panel pad" data-px-panel><div class="rowhead wrap"><div><div class="ptitle">Price</div><div class="psub">' +
      esc(sub || "Daily bars") + '</div></div><div class="pxtools" data-px-tools></div></div><div class="pxmas" data-px-mas></div><div class="chart-box pxchart"><div class="px-host" data-px-host><div class="px-legend" data-px-legend></div></div></div><p class="cap" data-px-cap></p></div>';
  }
  function expandKeyOf(row, opts) {
    if (opts.expandKey) return String(opts.expandKey(row) || "");
    return [row.ticker || "", row.kind || "", row.published || "", row.quarter || "", row.owner || "", row.earnings_date || "",
      String(row.headline || "").slice(0, 80), String(row.text || "").slice(0, 80)].join("|");
  }
  function fitOpenDrop(host) {
    const sc = host.querySelector(".buy-scroll");
    const drop = host.querySelector(".buydrop");
    if (sc && drop) drop.style.width = sc.clientWidth + "px";
  }
  function autoLines(row, opts) {
    if (typeof opts.lines === "function") return opts.lines(row) || [];
    if (opts.lines) return opts.lines;
    const lines = [];
    const lo = num(row.entry_low);
    const hi = num(row.entry_high);
    if (lo != null && hi != null) lines.push({ zone: [lo, hi], color: "rgba(124,156,255,.10)", labelColor: "#F59E0B", label: "Entry" });
    if (num(row.pivot) != null) lines.push({ value: num(row.pivot), color: "#F59E0B", label: "Buy point" });
    if (num(row.stop) != null) lines.push({ value: num(row.stop), color: "#EF4444", label: "Stop" });
    const tgt = num(row.trade_target != null && row.trade_target !== "" ? row.trade_target : row.target);
    if (tgt != null) lines.push({ value: tgt, color: "#22C55E", label: "Target" });
    if (num(row.high_52w) != null) lines.push({ value: num(row.high_52w), color: "#22C55E", label: "52w high" });
    if (num(row.low_52w) != null) lines.push({ value: num(row.low_52w), color: "#EF4444", label: "52w low" });
    return lines;
  }
  function paintOpenChart(host, row, opts) {
    const panel = host.querySelector("[data-px-panel]");
    if (!panel || !row || !row.ticker) return;
    fitOpenDrop(host);
    const lines = autoLines(row, opts);
    requestAnimationFrame(() => {
      if (!panel.isConnected) return;
      fitOpenDrop(host);
      drawPriceChart(panel, { ticker: row.ticker, lines: lines });
    });
  }
  function expandNotes(row, parked) {
    return parked.map((c) => {
      const v = row[c.key];
      if (isBlank(v)) return "";
      return '<p class="whytext"><span class="droplab">' + esc(c.label) + "</span> " + esc(v) + "</p>";
    }).join("");
  }
  function expandStory(row, opts, parked) {
    if (typeof opts.detail === "function") return "";
    const parkedKeys = {};
    parked.forEach((c) => { parkedKeys[c.key] = true; });
    return ["why", "reason"].map((key) => {
      if (parkedKeys[key] || isBlank(row[key])) return "";
      return '<p class="whytext">' + esc(row[key]) + "</p>";
    }).join("");
  }
  function expandHtml(row, opts, parked) {
    const custom = typeof opts.detail === "function" ? (opts.detail(row) || "") : "";
    const benchName = row && row.rs_benchmark ? String(row.rs_benchmark) : "";
    const benchLine = benchName ? " Relative strength uses " + benchName + "." : "";
    const sub = (typeof opts.priceSub === "function" ? opts.priceSub(row) : (opts.priceSub || "Daily candles in rupees. Turn the averages on or off above the chart.")) + benchLine;
    const company = isBlank(row.company) ? "" : ' <span class="mut">' + esc(row.company) + "</span>";
    return '<div class="buydrop"><div class="buyid">' + tickerHtml(row.ticker) + company + "</div>" +
      expandNotes(row, parked) + expandStory(row, opts, parked) + custom + pricePanel(sub) + "</div>";
  }
  if (typeof window !== "undefined" && !window.__rowDropFit) {
    window.__rowDropFit = true;
    window.addEventListener("resize", () => {
      document.querySelectorAll(".buydrop").forEach((drop) => {
        const sc = drop.closest(".buy-scroll");
        if (sc) drop.style.width = sc.clientWidth + "px";
      });
    });
  }

  function drawTable(host, opts) {
    const rows = opts.rows || [];
    const columns = opts.columns;
    const state = opts.state;
    const pageSize = opts.pageSize || 25;
    const expandable = opts.expandable !== false && featureOn("feature.row_charts") &&
      (columns || []).some((c) => c.key === "ticker" && !c.hidden);
    const hasDetail = expandable || typeof opts.detail === "function";
    host._tableOpts = opts;
    if (expandSlot && !expandSlot.host.isConnected) expandSlot = null;
    if (typeof opts.beforeDraw === "function") opts.beforeDraw();
    const oldPanel = host.querySelector("[data-px-panel]");
    if (oldPanel) dropTv(oldPanel);
    const sorted = rows.slice().sort((a, b) => {
      const col = columns.find((c) => c.key === state.sort) || columns[0];
      let c = compare(a, b, col, state.dir);
      if (c === 0 && state.sort2) {
        const col2 = columns.find((x) => x.key === state.sort2);
        if (col2) c = compare(a, b, col2, state.dir2 || "asc");
      }
      return c;
    });
    const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
    if (state.page >= pages) state.page = pages - 1;
    if (state.page < 0) state.page = 0;
    const start = state.page * pageSize;
    const view = sorted.slice(start, start + pageSize);
    const parked = expandable ? columns.filter((c) => !c.hidden && (c.wrap || c.inDetail)) : [];
    const shown = columns.filter((c) => !c.hidden && parked.indexOf(c) < 0);
    if (expandable && expandSlot && expandSlot.host === host && !rows.some((r) => expandKeyOf(r, opts) === expandSlot.key)) expandSlot = null;
    const liveKey = expandable && expandSlot && expandSlot.host === host ? expandSlot.key : "";
    const head = (hasDetail ? '<th class="exp"></th>' : "") + shown.map((c) => {
      const mark = state.sort === c.key ? '<span class="sort">' + (state.dir === "asc" ? "▲" : "▼") + "</span>" : "";
      const cls = [align(c), c.hide === "md" ? "hide-md" : "", c.ellipsis ? "ellip" : ""].filter(Boolean).join(" ");
      return '<th class="' + cls + '" data-k="' + esc(c.key) + '">' + esc(c.label) + mark + "</th>";
    }).join("");
    const body = view.map((r, i) => {
      const tds = shown.map((c) => {
        const cls = [align(c), c.wrap ? "wrap" : "", c.kind === "score" ? "score" : "", c.hide === "md" ? "hide-md" : "", c.ellipsis ? "ellip" : ""].filter(Boolean).join(" ");
        const width = c.width ? " style=\"width:" + c.width + "\"" : "";
        const raw = r[c.key];
        const tip = c.ellipsis && raw != null && String(raw).trim() !== "" ? ' title="' + esc(String(raw)) + '"' : "";
        return "<td class=\"" + cls + "\"" + width + tip + ">" + cell(r, c) + "</td>";
      }).join("");
      const picked = opts.pick && opts.pick === (r.ticker || "") && opts.pick !== "";
      const mine = expandKeyOf(r, opts);
      const opened = expandable ? (!!liveKey && mine === liveKey) : (hasDetail && opts.open && opts.open === (r.ticker || "") && opts.open !== "");
      const on = (picked || opened) ? " selrow" : "";
      if (!hasDetail) return '<tr data-i="' + (start + i) + '" class="' + on + '">' + tds + "</tr>";
      const zebra = i % 2 === 0 ? "z0" : "z1";
      const name = r.ticker || "details";
      const exp = '<td class="exp"><button type="button" class="rowexp" aria-expanded="' + (opened ? "true" : "false") +
        '" aria-label="' + esc((opened ? "Hide " : "Show ") + name) + '"><span class="rowchev' + (opened ? " open" : "") + '"></span></button></td>';
      let html = '<tr data-i="' + (start + i) + '" class="datarow ' + zebra + on + '">' + exp + tds + "</tr>";
      if (opened) {
        const inner = expandable ? expandHtml(r, opts, parked) : opts.detail(r);
        html += '<tr class="detailrow"><td colspan="' + (shown.length + 1) + '">' + inner + "</td></tr>";
      }
      return html;
    }).join("");
    const empty = rows.length ? "" : '<div class="empty">' + esc(opts.empty || "No rows match these filters.") + "</div>";
    const from = rows.length ? start + 1 : 0;
    const to = Math.min(start + pageSize, rows.length);
    const showFoot = opts.foot !== false && rows.length > pageSize;
    host.innerHTML =
      (opts.title ? '<div class="pad headrow" style="padding-bottom:0"><div class="ptitle">' + esc(opts.title) + "</div>" +
        (opts.sub ? '<div class="psub">' + esc(opts.sub) + "</div>" : "") + "</div>" : "") +
      '<div class="scroll' + (hasDetail ? " buy-scroll" : "") + '"><table' + (hasDetail ? (' class="buys' + (opts.fit ? " buyfit" : "") + '"') : "") + '><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      empty +
      (showFoot ? '<div class="foot"><span>' + from + "–" + to + " of " + rows.length + '</span><div class="pg">' +
      '<button type="button" data-pg="prev"' + (state.page <= 0 ? " disabled" : "") + ">‹</button>" +
      '<button type="button" data-pg="next"' + (state.page >= pages - 1 ? " disabled" : "") + ">›</button></div></div>" : "");
    host.querySelectorAll("th[data-k]").forEach((th) => {
      th.addEventListener("click", () => {
        const k = th.getAttribute("data-k");
        if (!k) return;
        if (state.sort === k) state.dir = state.dir === "asc" ? "desc" : "asc";
        else { state.sort = k; state.dir = "desc"; }
        drawTable(host, opts);
      });
    });
    host.querySelectorAll("[data-pg]").forEach((b) => {
      b.addEventListener("click", () => {
        state.page += b.getAttribute("data-pg") === "next" ? 1 : -1;
        drawTable(host, opts);
      });
    });
    if (expandable) {
      host.querySelectorAll("tbody tr.datarow").forEach((tr) => {
        tr.addEventListener("click", (ev) => {
          const link = ev.target.closest("a");
          if (link) ev.preventDefault();
          const row = sorted[Number(tr.getAttribute("data-i"))];
          if (!row) return;
          const key = expandKeyOf(row, opts);
          const next = liveKey === key ? "" : key;
          const prev = expandSlot && expandSlot.host;
          expandSlot = next ? { host: host, key: next } : null;
          if (prev && prev !== host && prev.isConnected && prev._tableOpts) drawTable(prev, prev._tableOpts);
          if (typeof opts.onPick === "function") opts.onPick(row);
          else drawTable(host, opts);
        });
      });
    } else if (opts.onPick) {
      host.querySelectorAll(hasDetail ? "tbody tr.datarow" : "tbody tr").forEach((tr) => {
        tr.addEventListener("click", (ev) => {
          if (ev.target.closest("a")) return;
          const i = Number(tr.getAttribute("data-i"));
          opts.onPick(sorted[i]);
        });
      });
    }
    host._sorted = sorted;
    if (typeof opts.afterDraw === "function") opts.afterDraw(host);
    if (expandable && liveKey) {
      const row = view.find((r) => expandKeyOf(r, opts) === liveKey);
      if (row) paintOpenChart(host, row, opts);
    }
  }

  function uniq(rows, key) {
    const s = new Set();
    rows.forEach((r) => { if (!isBlank(r[key])) s.add(r[key]); });
    return Array.from(s).sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }));
  }
  function indexTokens(rows) {
    const s = new Set();
    rows.forEach((r) => {
      String(r.index_membership || "").split("/").forEach((p) => {
        const t = p.trim();
        if (t) s.add(t);
      });
    });
    return Array.from(s).sort();
  }
  function selectedMulti(root, id) {
    const box = root.querySelector('[data-filter="' + id + '"]');
    if (!box) return null;
    const all = Array.from(box.querySelectorAll("input[type=checkbox]"));
    const on = all.filter((x) => x.checked).map((x) => x.value);
    if (on.length === all.length) return null;
    return on;
  }
  function fieldVal(root, id) {
    const el = root.querySelector('[data-filter="' + id + '"]');
    if (!el) return "";
    return el.value;
  }

  function multiHtml(id, label, options, picked) {
    const set = picked ? new Set(picked) : null;
    const checks = options.map((o) => {
      const on = !set || set.has(o);
      return '<label><input type="checkbox" value="' + esc(o) + '"' + (on ? " checked" : "") + "> " + esc(o) + "</label>";
    }).join("");
    const shown = multiLabel(options, set);
    return '<div class="filter" data-id="' + esc(id) + '"><button type="button" class="dd">' + esc(label) +
      ' <span class="dmut">' + esc(shown) + '</span></button><div class="pop" data-filter="' + esc(id) + '">' + checks + "</div></div>";
  }
  function prettyOpt(s) {
    if (s === "BROKEN OUT today") return "broken out";
    if (s === "READY") return "Ready";
    const text = String(s || "");
    return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
  }
  function multiLabel(options, set) {
    if (!set || set.size === options.length) return "All";
    if (!set.size) return "None";
    if (set.size === 2 && set.has("READY") && set.has("BROKEN OUT today")) return "Ready + broken out";
    if (set.size <= 2) return Array.from(set).map(prettyOpt).join(", ");
    return set.size + " selected";
  }
  function selectHtml(id, label, options, value, opt) {
    opt = opt || {};
    const items = options.map((o) => (o && typeof o === "object") ? o : { value: o, label: o });
    const opts = (opt.all === false ? [] : ['<option value="">All</option>']).concat(items.map((o) =>
      '<option value="' + esc(o.value) + '"' + (String(o.value) === String(value) ? " selected" : "") + ">" + esc(o.label) + "</option>"));
    return '<label class="ctl"><span class="lab">' + esc(label) + '</span><select data-filter="' + esc(id) + '">' + opts.join("") + "</select></label>";
  }
  function searchHtml(id, label, listId, values) {
    const opts = values.slice(0, 800).map((v) => "<option value=\"" + esc(v) + "\"></option>").join("");
    return '<label class="ctl"><span class="lab">' + esc(label) +
      '</span><input data-filter="' + esc(id) + '" list="' + esc(listId) + '" placeholder="All">' +
      '<datalist id="' + esc(listId) + '">' + opts + "</datalist></label>";
  }
  function rangeHtml(id, label, min, max, value, step) {
    return '<label class="ctl"><span class="lab">' + esc(label) +
      '</span><input type="number" data-filter="' + esc(id) + '" min="' + min + '" max="' + max +
      '" step="' + (step || "any") + '" value="' + value + '"></label>';
  }
  function pairHtml(idLo, idHi, label, lo, hi) {
    return '<label class="ctl wide"><span class="lab">' + esc(label) +
      '</span><input type="number" data-filter="' + esc(idLo) + '" value="' + lo + '">' +
      '<input type="number" data-filter="' + esc(idHi) + '" value="' + hi + '"></label>';
  }
  function dateHtml(id, label, value) {
    return '<label class="ctl"><span class="lab">' + esc(label) +
      '</span><input type="date" data-filter="' + esc(id) + '" value="' + esc(value || "") + '"></label>';
  }

  function wireFilters(root, onChange) {
    root.addEventListener("change", onChange);
    root.addEventListener("input", (e) => {
      if (e.target.matches("input[type=number], input[type=text], input.dd")) onChange();
    });
    root.querySelectorAll(".filter > button").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const parent = btn.parentElement;
        const open = parent.classList.contains("open");
        document.querySelectorAll(".filter.open").forEach((n) => n.classList.remove("open"));
        if (!open) parent.classList.add("open");
      });
    });
    root.querySelectorAll(".pop").forEach((pop) => {
      pop.addEventListener("click", (e) => e.stopPropagation());
    });
    root.querySelectorAll(".filter").forEach((box) => {
      box.addEventListener("change", () => {
        const all = Array.from(box.querySelectorAll("input[type=checkbox]"));
        const on = all.filter((x) => x.checked);
        const label = box.querySelector(".dmut");
        if (label) {
          const picked = new Set(on.map((x) => x.value));
          label.textContent = multiLabel(all.map((x) => x.value), on.length === all.length ? null : picked);
        }
      });
    });
  }
  document.addEventListener("click", () => {
    document.querySelectorAll(".filter.open").forEach((n) => n.classList.remove("open"));
  });

  function matchMulti(row, key, picked) {
    if (!picked) return true;
    return picked.indexOf(row[key]) >= 0;
  }
  function matchContains(row, key, picked) {
    if (!picked) return true;
    const v = row[key] || "";
    return picked.some((p) => v.indexOf(p) >= 0);
  }
  function matchText(row, key, q) {
    if (!q) return true;
    return String(row[key] || "").toLowerCase().indexOf(String(q).trim().toLowerCase()) >= 0;
  }
  function matchMin(row, key, min) {
    if (min == null || min === "" || Number.isNaN(Number(min))) return true;
    const n = num(row[key]);
    if (n == null) return false;
    return n >= Number(min);
  }

  const tvCharts = [];
  function tvStillOnScreen(chart) {
    try {
      if (typeof chart.chartElement !== "function") return false;
      const el = chart.chartElement();
      return !!(el && el.isConnected);
    } catch (e) {
      return false;
    }
  }
  function destroyCharts() {
    while (charts.length) {
      const c = charts.pop();
      try { c.destroy(); } catch (e) { /* already gone */ }
    }
    for (let i = tvCharts.length - 1; i >= 0; i--) {
      const c = tvCharts[i];
      if (tvStillOnScreen(c)) continue;
      tvCharts.splice(i, 1);
      try { c.remove(); } catch (e) { /* already gone */ }
    }
  }
  function basePlugins(legend) {
    return {
      legend: legend === false ? { display: false } : {
        display: true,
        labels: { color: MU, boxWidth: 12, font: { size: 12 } },
      },
      tooltip: { intersect: false },
    };
  }
  function axis() {
    return {
      ticks: { color: MU, maxRotation: 0, autoSkip: true },
      grid: { color: "#1E293B" },
    };
  }
  function makeChart(canvas, config) {
    if (!canvas || typeof Chart === "undefined") return null;
    config.options = config.options || {};
    // Draw the final values immediately. The default entrance animation
    // starts every point at 0, so a breadth line of 68% first appears near 15%.
    config.options.animation = false;
    tcDeep(config);
    const c = new Chart(canvas, config);
    charts.push(c);
    return c;
  }
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function monthLabel(s, spanYears) {
    const m = /^(\d{4})-(\d{2})/.exec(String(s || ""));
    if (!m) return s;
    if (spanYears >= 3) return m[1];
    return MONTHS[Number(m[2]) - 1];
  }
  function dateTicks(labels) {
    let span = 0;
    if (labels && labels.length > 1) {
      const a = Date.parse(labels[0]);
      const b = Date.parse(labels[labels.length - 1]);
      if (Number.isFinite(a) && Number.isFinite(b)) span = (b - a) / (365.25 * 86400000);
    }
    return {
      maxRotation: 0,
      autoSkip: false,
      color: MU,
      callback(v) {
        const a = monthLabel(this.getLabelForValue(v), span);
        const b = v > 0 ? monthLabel(this.getLabelForValue(v - 1), span) : null;
        return a !== b ? a : null;
      },
    };
  }
  function lineLegend() {
    return {
      display: true,
      position: "top",
      align: "end",
      labels: { usePointStyle: true, pointStyle: "line", boxWidth: 14, color: MU, font: { size: 11 } },
    };
  }
  function lineChart(canvas, labels, series, extra) {
    extra = extra || {};
    const x = Object.assign(axis(), { ticks: dateTicks(labels) }, extra.x || {});
    makeChart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: series.map((s) => ({
          label: s.label,
          data: s.data,
          borderColor: s.color,
          backgroundColor: s.color,
          spanGaps: !!s.spanGaps,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: extra.layout || {},
        plugins: Object.assign({ legend: extra.legend === false ? { display: false } : lineLegend(), tooltip: { intersect: false } }, extra.plugins || {}),
        scales: {
          x: x,
          y: Object.assign(axis(), extra.y || {}),
        },
      },
    });
  }
  function barChart(canvas, labels, data, colors, extra) {
    extra = extra || {};
    const horizontal = !!extra.horizontal;
    const category = labels.length <= 20 ? { ticks: { autoSkip: false, color: MU, maxRotation: 0 } } : {};
    const nums = (data || []).map(Number).filter((n) => Number.isFinite(n));
    const lo = nums.length ? Math.min.apply(null, nums.concat([0])) : 0;
    const hi = nums.length ? Math.max.apply(null, nums.concat([0])) : 0;
    const valueExtra = Object.assign({}, extra.y || {});
    const xExtra = Object.assign({}, extra.x || {});
    if (horizontal && extra.labels) {
      const span = Math.max(hi - lo, 1e-9);
      const pad = span * 0.15;
      if (xExtra.suggestedMin == null) xExtra.suggestedMin = lo - pad;
      if (xExtra.suggestedMax == null) xExtra.suggestedMax = hi + pad;
    } else if (horizontal && lo < 0 && xExtra.suggestedMin == null) xExtra.suggestedMin = lo * 1.35;
    if (!horizontal && lo < 0 && valueExtra.suggestedMin == null) valueExtra.suggestedMin = lo * 1.35;
    const valueAxis = Object.assign(axis(), valueExtra);
    const catAxis = Object.assign(axis(), category, extra.cat || {});
    const plugins = Object.assign(basePlugins(false), extra.labels ? { barLabels: { dec: extra.dec == null ? 1 : extra.dec, suffix: extra.suffix || "", level: !!extra.level, money: !!extra.money } } : {});
    makeChart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: extra.label || "",
          data: data,
          backgroundColor: colors,
          borderWidth: 0,
        }],
      },
      options: {
        indexAxis: horizontal ? "y" : "x",
        responsive: true,
        maintainAspectRatio: false,
        plugins: plugins,
        scales: horizontal
          ? { x: Object.assign(valueAxis, xExtra), y: catAxis }
          : { x: Object.assign(catAxis, extra.x || {}), y: valueAxis },
      },
    });
  }
  function comboChart(canvas, labels, bars, line) {
    const datasets = (bars || []).map((b) => ({
      type: "bar",
      label: b.label,
      data: b.data,
      backgroundColor: b.color,
      borderWidth: 0,
      order: 2,
      maxBarThickness: 8,
    }));
    if (line) {
      datasets.push({
        type: "line",
        label: line.label,
        data: line.data,
        borderColor: line.color,
        backgroundColor: line.color,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0,
        order: 1,
      });
    }
    makeChart(canvas, {
      type: "bar",
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: lineLegend(), tooltip: { intersect: false } },
        scales: {
          x: Object.assign(axis(), { ticks: dateTicks(labels) }),
          y: axis(),
        },
      },
    });
  }

  const hlines = {
    id: "hlines",
    afterDraw(chart) {
      const raw = chart.options.plugins && chart.options.plugins.hlines;
      const lines = Array.isArray(raw) ? raw : [];
      const area = chart.chartArea;
      const y = chart.scales.y;
      if (!area || !y) return;
      const ctx = chart.ctx;
      const labels = [];
      lines.forEach((ln) => {
        if (ln.zone && ln.zone.length === 2 && Number.isFinite(ln.zone[0]) && Number.isFinite(ln.zone[1])) {
          const y1 = y.getPixelForValue(ln.zone[0]);
          const y2 = y.getPixelForValue(ln.zone[1]);
          const top = Math.max(area.top, Math.min(y1, y2));
          const bot = Math.min(area.bottom, Math.max(y1, y2));
          ctx.save();
          ctx.fillStyle = tc(ln.color || "rgba(124,156,255,.10)");
          ctx.fillRect(area.left, top, area.right - area.left, Math.max(1, bot - top));
          ctx.restore();
          labels.push({ yy: (top + bot) / 2, text: ln.label || "", color: ln.labelColor || "#7C9CFF" });
          return;
        }
        if (ln.value == null || !Number.isFinite(ln.value)) return;
        const yy = y.getPixelForValue(ln.value);
        if (yy < area.top || yy > area.bottom) return;
        ctx.save();
        ctx.strokeStyle = tc(ln.color);
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(area.left, yy);
        ctx.lineTo(area.right, yy);
        ctx.stroke();
        ctx.restore();
        labels.push({ yy: yy, text: ln.label || "", color: ln.color || MU });
      });
      labels.sort((a, b) => a.yy - b.yy);
      let last = -1e9;
      ctx.save();
      ctx.font = "11px Roboto, Arial, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      labels.forEach((lb) => {
        let yy = lb.yy;
        if (yy - last < 13) yy = last + 13;
        if (yy > area.bottom) yy = area.bottom;
        last = yy;
        ctx.fillStyle = tc(lb.color);
        ctx.fillText(lb.text, area.right - 6, yy);
      });
      ctx.restore();
    },
  };
  function levelText(v, opt) {
    const dec = opt.dec == null ? 1 : opt.dec;
    const abs = Math.abs(v);
    const body = abs >= 1000 ? String(compact(abs) || "").replace(/^-/, "") : abs.toFixed(dec);
    if (opt.money) return (v < 0 ? "−₹" : "₹") + String(body).replace(/\.0(?=[KMBT]|$)/, "");
    return body + (opt.suffix || "");
  }
  const barLabels = {
    id: "barLabels",
    afterDatasetsDraw(chart) {
      const opt = chart.options.plugins && chart.options.plugins.barLabels;
      if (!opt) return;
      const indexes = opt.lines ? chart.data.datasets.map((_, i) => i) : [0];
      const ctx = chart.ctx;
      const horizontal = chart.options.indexAxis === "y";
      const area = chart.chartArea;
      ctx.save();
      ctx.font = "11px Roboto, Arial, sans-serif";
      ctx.textBaseline = "middle";
      indexes.forEach((di) => {
        const meta = chart.getDatasetMeta(di);
        const ds = chart.data.datasets[di];
        if (!meta || !meta.data || meta.data.length >= 15 || !ds) return;
        meta.data.forEach((el, i) => {
          const v = Number(ds.data[i]);
          if (!Number.isFinite(v) || !el) return;
          const dec = opt.dec == null ? 1 : opt.dec;
          let text;
          if (opt.level) {
            text = levelText(v, opt);
            ctx.fillStyle = tc("#C3CBDB");
          } else {
            const body = Math.abs(v) >= 1000 ? compact(v) : v.toFixed(dec);
            text = (v > 0 ? "+" : v < 0 ? "−" : "") + String(body).replace(/^-/, "") + (opt.suffix || "");
            ctx.fillStyle = tc(v > 0 ? UP : v < 0 ? DN : MU);
          }
          if (horizontal && area) {
            // Light grey, just outside the bar tip, so a red bar does not hide red text.
            ctx.fillStyle = tc("#C3CBDB");
            const textW = ctx.measureText(text).width;
            if (v < 0) {
              ctx.textAlign = "right";
              const x = Math.max(area.left + textW, el.x - 4);
              ctx.fillText(text, x, el.y);
            } else {
              ctx.textAlign = "left";
              const x = Math.min(area.right - textW, el.x + 4);
              ctx.fillText(text, x, el.y);
            }
          } else {
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText(text, el.x, el.y - 2);
          }
        });
      });
      ctx.restore();
    },
  };
  if (typeof Chart !== "undefined") {
    Chart.defaults.animation = false;
    if (Chart.defaults.transitions && Chart.defaults.transitions.active && Chart.defaults.transitions.active.animation) {
      Chart.defaults.transitions.active.animation.duration = 0;
    }
    Chart.defaults.font.family = "Roboto, Arial, sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = MU;
    Chart.register(hlines, barLabels);
  }

  function lastNDays(rows, dateKey, days) {
    const dates = rows.map((r) => r[dateKey]).filter(Boolean).sort();
    if (!dates.length) return rows;
    const end = dates[dates.length - 1];
    const cut = new Date(end + "T00:00:00Z");
    cut.setUTCDate(cut.getUTCDate() - days);
    const iso = cut.toISOString().slice(0, 10);
    return rows.filter((r) => r[dateKey] >= iso);
  }
  function seriesNum(rows, key) {
    return rows.map((r) => num(r[key]));
  }

  function alertDataRows(rows) {
    return realRows(rows).filter((r) => r.kind && r.kind !== "info");
  }
  function quietMessage(rows) {
    const list = rows || [];
    const info = list.find((r) => String(r.kind || "") === "info");
    const fromInfo = info ? String(info.text || info.note || "").trim() : "";
    if (fromInfo) return fromInfo;
    const noted = list.find((r) => String(r.note || "").trim());
    if (noted) return String(noted.note).trim();
    return "No changes since the last run.";
  }
  function showQuiet(host, text, title) {
    if (!host) return;
    host.innerHTML = (title ? '<div class="pad" style="padding-bottom:0"><div class="ptitle">' + esc(title) + "</div></div>" : "") +
      '<div class="empty">' + esc(text) + "</div>";
  }

  const MA_DEFS = [
    { id: "sma21", label: "SMA 21", kind: "sma", n: 21, color: "#7C9CFF" },
    { id: "sma50", label: "SMA 50", kind: "sma", n: 50, color: "#C3CBDB" },
    { id: "sma150", label: "SMA 150", kind: "sma", n: 150, color: "#F59E0B" },
    { id: "sma200", label: "SMA 200", kind: "sma", n: 200, color: "#E879F9" },
    { id: "ema21", label: "EMA 21", kind: "ema", n: 21, color: "#38BDF8" },
    { id: "ema50", label: "EMA 50", kind: "ema", n: 50, color: "#F472B6" },
    { id: "ema150", label: "EMA 150", kind: "ema", n: 150, color: "#34D399" },
    { id: "ema200", label: "EMA 200", kind: "ema", n: 200, color: "#FB923C" },
  ];
  // Moving average colours (chart_colors block of config.json, same as the US desk): MA 10 green, 20 orange,
  // 50 blue, 150 yellow, 200 red. These defaults match config.json, so a settings file without the rows still
  // draws the same colours. Light mode uses slightly darker shades so each line shows on white.
  // A length that is not listed keeps the colour it is given here (the row charts' SMA 21 and the EMA lines).
  const MA_COLORS = { "10": "#22c55e", "20": "#f97316", "50": "#3b82f6", "150": "#eab308", "200": "#ef4444" };
  const MA_COLORS_LIGHT = { "10": "#16a34a", "20": "#ea580c", "50": "#2563eb", "150": "#ca8a04", "200": "#dc2626" };
  function maColor(n, fallback) {
    const key = String(n);
    const block = THEME === "light" ? "ma_colors_light" : "ma_colors";
    const row = SETTINGS.find((r) => r.setting === "chart_colors." + block + "." + key);
    const v = row ? String(row.value == null ? "" : row.value).trim() : "";
    if (/^#[0-9a-fA-F]{6}$/.test(v)) return v;
    return (THEME === "light" ? MA_COLORS_LIGHT : MA_COLORS)[key] || fallback;
  }
  function maDefColor(def) { return def.kind === "sma" ? maColor(def.n, def.color) : def.color; }
  const MA_DEFAULT = { sma21: false, sma50: true, sma150: false, sma200: true, ema21: true, ema50: false, ema150: false, ema200: false };

  let tvPromise = null;
  function tvReady() {
    return typeof LightweightCharts !== "undefined" && !!LightweightCharts.createChart;
  }
  function ensureTv() {
    if (tvReady()) return Promise.resolve();
    if (!tvPromise) {
      tvPromise = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "vendor/lightweight-charts/lightweight-charts.standalone.production.js";
        s.onload = () => { if (tvReady()) resolve(); else reject(new Error("price chart did not load")); };
        s.onerror = () => reject(new Error("price chart failed to load"));
        document.head.appendChild(s);
      });
    }
    return tvPromise;
  }
  function maState() {
    const out = Object.assign({}, MA_DEFAULT);
    try {
      const raw = JSON.parse(localStorage.getItem("desk-ma") || "");
      if (raw && typeof raw === "object") {
        MA_DEFS.forEach((d) => { if (typeof raw[d.id] === "boolean") out[d.id] = raw[d.id]; });
      }
    } catch (e) { /* storage can be blocked or hold an older value */ }
    return out;
  }
  function storeMa(state) {
    try { localStorage.setItem("desk-ma", JSON.stringify(state)); } catch (e) { /* ignore */ }
  }
  function storedChoice(key, fallback, allowed) {
    try {
      const v = localStorage.getItem(key);
      if (allowed.indexOf(v) >= 0) return v;
    } catch (e) { /* storage can be blocked */ }
    return fallback;
  }
  function storeChoice(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
  }
  function priceStyle() { return storedChoice("desk-price-style", "candles", ["line", "candles"]); }
  function priceRange() { return storedChoice("desk-price-range", "6M", ["3M", "6M", "1Y", "All"]); }
  function dropTv(panel) {
    const c = panel._tv;
    if (!c) return;
    const i = tvCharts.indexOf(c);
    if (i >= 0) tvCharts.splice(i, 1);
    try { c.remove(); } catch (e) { /* already gone */ }
    panel._tv = null;
  }
  function barsFromRows(rows) {
    const sorted = (rows || []).filter((r) => num(r.close) != null).slice()
      .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    let prev = null;
    return sorted.map((r) => {
      const c = num(r.close);
      let o = num(r.open);
      let prior = false;
      if (o == null) {
        if (prev != null) { o = prev; prior = true; }
        else o = c;
      }
      const h0 = num(r.high);
      const l0 = num(r.low);
      const bar = {
        date: r.date, o: o, h: h0 == null ? Math.max(o, c) : h0, l: l0 == null ? Math.min(o, c) : l0, c: c,
        v: num(r.volume), prior: prior,
      };
      prev = c;
      return bar;
    });
  }
  function smaValues(closes, n) {
    const out = new Array(closes.length).fill(null);
    let sum = 0;
    for (let i = 0; i < closes.length; i++) {
      sum += closes[i];
      if (i >= n) sum -= closes[i - n];
      if (i >= n - 1) out[i] = sum / n;
    }
    return out;
  }
  function emaValues(closes, n) {
    const out = new Array(closes.length).fill(null);
    const k = 2 / (n + 1);
    let prev = null;
    let seed = 0;
    for (let i = 0; i < closes.length; i++) {
      if (i < n) {
        seed += closes[i];
        if (i === n - 1) {
          prev = seed / n;
          out[i] = prev;
        }
        continue;
      }
      prev = closes[i] * k + prev * (1 - k);
      out[i] = prev;
    }
    return out;
  }
  function maSeries(closes, def) {
    return def.kind === "ema" ? emaValues(closes, def.n) : smaValues(closes, def.n);
  }
  function timeKey(t) {
    if (!t) return "";
    if (typeof t === "string") return t.slice(0, 10);
    if (typeof t === "object" && t.year) {
      return t.year + "-" + String(t.month).padStart(2, "0") + "-" + String(t.day).padStart(2, "0");
    }
    return "";
  }
  function levelSpecs(lines) {
    const out = [];
    (lines || []).forEach((line) => {
      if (line.zone && line.zone.length === 2) {
        const lo = Math.min(line.zone[0], line.zone[1]);
        const hi = Math.max(line.zone[0], line.zone[1]);
        const color = line.labelColor || AM;
        out.push({ price: lo, color: color, title: "Entry low" });
        out.push({ price: hi, color: color, title: "Entry high" });
      } else if (line.value != null && isFinite(line.value)) {
        const title = String(line.label || "Level").replace(/\s+[\d.,–+-]+$/, "").trim() || "Level";
        out.push({ price: line.value, color: line.color || AM, title: title });
      }
    });
    return out;
  }
  function rangeWindow(bars, range) {
    const end = bars[bars.length - 1].date;
    if (range === "All") return { from: bars[0].date, to: end, fit: true };
    const months = range === "3M" ? 3 : range === "1Y" ? 12 : 6;
    const cut = new Date(end + "T00:00:00Z");
    cut.setUTCMonth(cut.getUTCMonth() - months);
    const iso = cut.toISOString().slice(0, 10);
    let from = bars[0].date;
    for (let i = 0; i < bars.length; i++) {
      if (bars[i].date >= iso) { from = bars[i].date; break; }
    }
    return { from: from, to: end, fit: from === end };
  }
  function applyRange(chart, bars, range) {
    if (!bars.length) return;
    const win = rangeWindow(bars, range);
    try {
      chart.panes().forEach((pane) => {
        try { pane.priceScale("right").applyOptions({ autoScale: true }); } catch (e) { /* pane has no scale yet */ }
      });
      if (win.fit) chart.timeScale().fitContent();
      else chart.timeScale().setVisibleRange({ from: win.from, to: win.to });
    } catch (e) {
      try { chart.timeScale().fitContent(); } catch (err) { /* chart is gone */ }
    }
  }
  function legendHtml(bar, prevClose, averages) {
    if (!bar) return "";
    const up = prevClose == null ? bar.c >= bar.o : bar.c >= prevClose;
    const cls = up ? "up" : "dn";
    const px = (n) => esc(fmt(n, 2) || "–");
    let html = "<div><b class=\"" + cls + "\">O</b> " + px(bar.o) +
      "  <b class=\"" + cls + "\">H</b> " + px(bar.h) +
      "  <b class=\"" + cls + "\">L</b> " + px(bar.l) +
      "  <b class=\"" + cls + "\">C</b> " + px(bar.c) +
      "  <b>V</b> " + esc(compact(bar.v) || "–") + "</div>";
    if (averages.length) {
      html += "<div>" + averages.map((a) =>
        '<span style="color:' + a.color + '">' + esc(a.label) + " " + px(a.value) + "</span>"
      ).join("  ") + "</div>";
    }
    return html;
  }
  function paintPrice(panel, bars, lines, token) {
    if (panel._token !== token || !panel.isConnected) return;
    const cap = panel.querySelector("[data-px-cap]");
    const host = panel.querySelector("[data-px-host]");
    const legend = panel.querySelector("[data-px-legend]");
    dropTv(panel);
    if (!host || !bars.length) {
      if (legend) legend.innerHTML = "";
      if (cap) cap.textContent = "No saved daily bars for this name.";
      return;
    }
    const draw = () => {
      if (panel._token !== token || !panel.isConnected || !tvReady()) return;
      const LC = LightweightCharts;
      const style = priceStyle();
      const mas = maState();
      const closes = bars.map((b) => b.c);
      const averages = {};
      MA_DEFS.forEach((def) => { averages[def.id] = maSeries(closes, def); });
      const byDate = new Map();
      bars.forEach((b, i) => byDate.set(b.date, i));
      const chart = tvCreate(host, {
        autoSize: true,
        layout: {
          background: { type: "solid", color: "#121826" },
          textColor: MU,
          fontFamily: "Roboto, Arial, sans-serif",
          fontSize: 12,
          attributionLogo: true,
          panes: { separatorColor: "#1E293B", enableResize: true },
        },
        grid: { vertLines: { color: "#1E293B" }, horzLines: { color: "#1E293B" } },
        crosshair: { mode: LC.CrosshairMode.Magnet },
        rightPriceScale: { borderColor: "#1E293B" },
        timeScale: { borderColor: "#1E293B", rightOffset: 4 },
        handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true, axisDoubleClickReset: true },
        kineticScroll: { touch: true, mouse: false },
      });
      panel._tv = chart;
      tvCharts.push(chart);
      const priceOpts = { priceLineVisible: false, lastValueVisible: true };
      let priceSeries;
      if (style === "line") {
        priceSeries = chart.addSeries(LC.LineSeries, Object.assign({ color: TX, lineWidth: 2 }, priceOpts));
        priceSeries.setData(bars.map((b) => ({ time: b.date, value: b.c })));
      } else {
        priceSeries = chart.addSeries(LC.CandlestickSeries, Object.assign({
          upColor: UP, downColor: DN, borderUpColor: UP, borderDownColor: DN, wickUpColor: UP, wickDownColor: DN,
        }, priceOpts));
        priceSeries.setData(bars.map((b) => ({ time: b.date, open: b.o, high: b.h, low: b.l, close: b.c })));
      }
      const vol = chart.addSeries(LC.HistogramSeries, {
        priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false,
      }, 1);
      vol.setData(bars.filter((b) => b.v != null).map((b) => ({
        time: b.date, value: b.v, color: b.c >= b.o ? "rgba(34,197,94,.65)" : "rgba(239,68,68,.65)",
      })));
      const panes = chart.panes();
      if (panes[0]) panes[0].setStretchFactor(3);
      if (panes[1]) panes[1].setStretchFactor(1);
      levelSpecs(lines).forEach((level) => {
        priceSeries.createPriceLine({
          price: level.price, color: level.color, lineWidth: 1, lineStyle: LC.LineStyle.Dashed,
          axisLabelVisible: true, title: level.title,
        });
      });
      MA_DEFS.forEach((def) => {
        if (!mas[def.id]) return;
        const series = chart.addSeries(LC.LineSeries, {
          color: maDefColor(def), lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        });
        const data = [];
        averages[def.id].forEach((value, i) => {
          if (value != null) data.push({ time: bars[i].date, value: value });
        });
        series.setData(data);
      });
      const showLegend = (key) => {
        if (!legend) return;
        let i = key ? byDate.get(key) : bars.length - 1;
        if (i == null) i = bars.length - 1;
        const bar = bars[i];
        const prev = i > 0 ? bars[i - 1].c : null;
        const shown = MA_DEFS.filter((def) => mas[def.id] && averages[def.id][i] != null).map((def) => ({
          label: def.label, color: maDefColor(def), value: averages[def.id][i],
        }));
        legend.innerHTML = legendHtml(bar, prev, shown);
      };
      showLegend("");
      chart.subscribeCrosshairMove((param) => {
        if (panel._token !== token) return;
        showLegend(param && param.time ? timeKey(param.time) : "");
      });
      if (host._fit) host.removeEventListener("dblclick", host._fit);
      host._fit = (event) => {
        event.preventDefault();
        applyRange(chart, bars, priceRange());
      };
      host.addEventListener("dblclick", host._fit);
      requestAnimationFrame(() => {
        if (panel._token !== token || !panel.isConnected) return;
        applyRange(chart, bars, priceRange());
      });
      if (!cap) return;
      let text = style === "line"
        ? "Close, with volume underneath."
        : "Green is an up day and red is a down day. Volume sits underneath.";
      if (bars.some((b) => b.prior)) {
        text += " Opens are not in the saved prices yet, so each candle starts at the prior close.";
      }
      text += " Averages are calculated in the browser from the saved daily bars.";
      cap.innerHTML = esc(text) + ' Charting by <a href="https://www.tradingview.com/">TradingView</a> Lightweight Charts™.';
    };
    ensureTv().then(draw).catch(() => {
      if (panel._token !== token) return;
      if (cap) cap.textContent = "The price chart could not load.";
    });
  }
  // One plain line about what the company does. Read once from company_lines.csv.
  let companyLineMap = null;
  function companyLines() {
    if (!companyLineMap) {
      companyLineMap = loadCsv("company_lines.csv").then((rows) => {
        const m = new Map();
        (rows || []).forEach((r) => { if (r.ticker && r.line) m.set(String(r.ticker).toUpperCase(), r.line); });
        return m;
      }).catch(() => new Map());
    }
    return companyLineMap;
  }
  function fillCompanyLine(el, ticker) {
    if (!el) return;
    const want = String(ticker || "").trim().toUpperCase();
    el.dataset.colineFor = want;
    if (!want || !featureOn("feature.company_line")) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    companyLines().then((m) => {
      if (el.dataset.colineFor !== want) return;
      const line = m.get(want) || "";
      el.textContent = line;
      el.hidden = !line;
    });
  }
  function companyLineHtml(id) {
    return '<p class="coline" data-coline' + (id ? ' id="' + esc(id) + '"' : "") + ' hidden></p>';
  }
  function panelCompanyLine(panel, ticker) {
    let el = panel.querySelector(":scope > [data-coline]");
    if (!el) {
      panel.insertAdjacentHTML("afterbegin", companyLineHtml());
      el = panel.querySelector(":scope > [data-coline]");
      const head = panel.querySelector(":scope > .rowhead");
      if (head) head.after(el);
    }
    fillCompanyLine(el, ticker);
  }
  function drawPriceChart(panel, opts) {
    if (!panel) return;
    opts = opts || {};
    panelCompanyLine(panel, opts.ticker);
    const tools = panel.querySelector("[data-px-tools]");
    const chips = panel.querySelector("[data-px-mas]");
    const cap = panel.querySelector("[data-px-cap]");
    if (!tools) return;
    const style = priceStyle();
    const range = priceRange();
    const mas = maState();
    const btn = (group, value, label, on) =>
      '<button type="button" data-g="' + group + '" data-v="' + esc(value) + '"' + (on ? ' class="on"' : "") + ">" + esc(label) + "</button>";
    tools.innerHTML =
      '<div class="seg">' + btn("style", "line", "Line", style === "line") + btn("style", "candles", "Candles", style === "candles") + "</div>" +
      '<div class="seg">' + ["3M", "6M", "1Y", "All"].map((r) => btn("range", r, r, range === r)).join("") + "</div>" +
      '<div class="seg"><button type="button" data-g="reset" data-v="reset">Reset</button></div>';
    if (chips) {
      chips.innerHTML = MA_DEFS.map((def) =>
        '<button type="button" class="machip' + (mas[def.id] ? " on" : "") + '" data-ma="' + def.id + '" aria-pressed="' + (mas[def.id] ? "true" : "false") + '">' +
        '<i style="background:' + maDefColor(def) + '"></i>' + esc(def.label) + "</button>"
      ).join("");
    }
    const rerun = () => drawPriceChart(panel, opts);
    tools.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        const group = button.getAttribute("data-g");
        const value = button.getAttribute("data-v");
        if (group === "style") storeChoice("desk-price-style", value);
        if (group === "range") storeChoice("desk-price-range", value);
        if (group === "reset" && panel._tv && panel._bars) {
          applyRange(panel._tv, panel._bars, priceRange());
          return;
        }
        rerun();
      });
    });
    if (chips) {
      chips.querySelectorAll("button").forEach((button) => {
        button.addEventListener("click", () => {
          const next = maState();
          const id = button.getAttribute("data-ma");
          next[id] = !next[id];
          storeMa(next);
          rerun();
        });
      });
    }
    const ticker = String(opts.ticker || "").trim().toUpperCase();
    const token = (panel._token || 0) + 1;
    panel._token = token;
    const show = (rows) => {
      if (panel._token !== token || !panel.isConnected) return;
      const bars = barsFromRows(rows);
      panel._bars = bars;
      paintPrice(panel, bars, opts.lines || [], token);
    };
    if (panel._ticker === ticker && panel._rows) {
      show(panel._rows);
      return;
    }
    if (cap) cap.textContent = "";
    if (!ticker) {
      dropTv(panel);
      if (cap) cap.textContent = "No saved daily bars for this name.";
      return;
    }
    loadTickerBars(ticker).then((rows) => {
      if (panel._token !== token) return;
      panel._ticker = ticker;
      panel._rows = rows || [];
      show(panel._rows);
    }).catch(() => {
      if (panel._token !== token) return;
      dropTv(panel);
      if (cap) cap.textContent = "No saved daily bars for " + ticker + ".";
    });
  }

  // ---------------------------------------------------------------- Chart Viewer
  // One stock at a time, full screen, swipe to move. Every stock comes from the scanner
  // files the desk already publishes, and the bars come from the saved ohlc files.
  // No new downloads. Switches live in the chart_viewer block of config.json.
  // Which rows count: pattern scanners count any status except CLOSED (WATCHING and
  // DELAYED WATCH only with include_watching, CLOSED only with include_closed). Growth,
  // Quality, Dividend, Liquid stocks and Pullbacks count rows that pass. High volume counts
  // the rows its page lists by default. 52-week counts a new high, a new low, or near the high.
  // Gap Up counts every stock still holding its gap (chart_viewer.include_gap_up).
  // Buy setups and the Watchlist are shown in the reason box but do not add to the count.
  const CV_WATCHING = ["WATCHING", "DELAYED WATCH"];
  const CV_SOURCES = [
    { id: "vcp", label: "VCP", short: "VCP", file: "scanner_vcp.csv", href: "vcp.html", kind: "pattern" },
    { id: "canslim", label: "CANSLIM", short: "CANSLIM", file: "scanner_canslim.csv", href: "canslim.html", kind: "pattern" },
    { id: "box", label: "Box breakout", short: "Box", file: "scanner_box.csv", href: "box.html", kind: "pattern" },
    { id: "flag", label: "Flag breakout", short: "Flag", file: "scanner_flag.csv", href: "flag.html", kind: "pattern" },
    { id: "qullamaggie", label: "Qullamaggie breakout", short: "Qullamaggie", file: "scanner_qullamaggie.csv", href: "qullamaggie.html", kind: "pattern" },
    { id: "marios", label: "Marios breakout", short: "Marios", file: "scanner_marios.csv", href: "marios.html", kind: "pattern" },
    { id: "episodic", label: "Episodic Pivot", short: "EP", file: "scanner_episodic_pivot.csv", href: "episodic_pivot.html", kind: "pattern" },
    { id: "gapup", label: "Gap Up", short: "Gap Up", file: "scanner_gap_up.csv", href: "gap_up.html", kind: "gap", opt: "include_gap_up" },
    { id: "leaders", label: "Leaders", short: "Leaders", file: "scanner_leaders.csv", href: "leaders.html", kind: "pattern" },
    { id: "week52", label: "52-week highs and lows", short: "52-week", file: "scanner_52w.csv", href: "52-week.html", kind: "w52" },
    { id: "breakouts", label: "52-week breakouts", short: "Breakouts", file: "breakouts.csv", href: "breakouts.html", kind: "brk" },
    { id: "highvol", label: "High volume", short: "High volume", file: "high_volume.csv", href: "high-volume.html", kind: "hv" },
    { id: "pullbacks", label: "Pullbacks", short: "Pullbacks", file: "pullbacks.csv", href: "pullbacks.html", kind: "passes", word: "PULLBACK" },
    { id: "growth", label: "Growth", short: "Growth", file: "scanner_growth.csv", href: "growth.html", kind: "passes", word: "PASSES" },
    { id: "quality", label: "Quality", short: "Quality", file: "scanner_quality.csv", href: "quality.html", kind: "passes", word: "PASSES" },
    { id: "dividend", label: "Dividend", short: "Dividend", file: "scanner_dividend.csv", href: "dividend.html", kind: "passes", word: "PASSES" },
    { id: "wheel", label: "Liquid stocks", short: "Liquid", file: "scanner_wheel.csv", href: "wheel.html", kind: "passes", word: "PASSES" },
  ];
  const CV_BUY = { id: "buysetups", label: "Buy setups", short: "Buy setups", file: "buy_setups.csv", href: "buy-setups.html", kind: "buy", extra: true };
  const CV_WATCH = { id: "watchlist", label: "Watchlist", short: "Watchlist", file: "watchlist.csv", href: "watchlist.html", kind: "watch", extra: true };
  const CV_FILES = CV_SOURCES.concat([CV_BUY, CV_WATCH]).map((s) => s.file);
  const CV_MAS = [
    { id: "ma_10", label: "10", n: 10, color: "#38BDF8" },
    { id: "ma_20", label: "20", n: 20, color: "#7C9CFF" },
    { id: "ma_50", label: "50", n: 50, color: "#C3CBDB" },
    { id: "ma_150", label: "150", n: 150, color: "#F59E0B" },
    { id: "ma_200", label: "200", n: 200, color: "#E879F9" },
  ];
  // Same keys and defaults as the US desk.
  const CV_DEFAULTS = {
    list_picker: true, include_watching: true, include_closed: false, include_buy_setups: true, include_watchlist: true, include_gap_up: true,
    scanner_links: true, fullscreen: true, native_fullscreen_ios: false, swipe: true, swipe_right_is_next: true, flip_toggle: true,
    chart_touch_pan: true, drag_mode_toggle: true, swipe_min_px: 80, swipe_max_ms: 300, swipe_ratio: 1.5,
    arrows: true, keyboard: true, counter: true, preload_next: true,
    ma_chips: true, ma_10: false, ma_20: false, ma_50: true, ma_150: true, ma_200: true,
    volume: true, volume_toggle: true, reason_box: true, reason_box_toggle: true,
    reason_max_chars: 110, reason_collapsed_items: 3, company_line: true, day_change: true,
    range_months: 6, range_months_phone: 3, range_chips: true, group_toggle: true, default_group: "technical",
  };
  function cvOpt(key) {
    const fallback = CV_DEFAULTS[key];
    const row = SETTINGS.find((r) => r.setting === "chart_viewer." + key);
    if (!row || isBlank(row.value)) return fallback;
    const s = String(row.value).trim();
    if (typeof fallback === "boolean") return s.toLowerCase() === "true";
    if (typeof fallback === "number") { const n = Number(s); return Number.isFinite(n) ? n : fallback; }
    return s;
  }
  function cvYes(v) { return String(v || "").toLowerCase() === "yes"; }
  function cvShort(text, max) {
    const t = String(text || "").replace(/\s+/g, " ").replace(/\u2014/g, ", ").trim();
    if (!max || t.length <= max) return t;
    const cut = t.slice(0, max);
    const sp = cut.lastIndexOf(" ");
    return (sp > max * 0.6 ? cut.slice(0, sp) : cut).replace(/[,.;:\s]+$/, "") + "...";
  }
  // What one scanner row says: is it in, its status, and its reason.
  function cvEntry(src, r) {
    const n = (v, d) => fmt(v, d);
    switch (src.kind) {
      case "pattern": {
        const s = String(r.status || "").trim();
        if (!s) return null;
        if (s === "CLOSED" && !cvOpt("include_closed")) return null;
        if (CV_WATCHING.indexOf(s) >= 0 && !cvOpt("include_watching")) return null;
        return { status: s, reason: r.reason || "", strength: num(r.strength) };
      }
      case "buy": {
        const why = (r.setup_sources ? r.setup_sources + ". " : "") + (r.reason || "");
        return { status: r.best_status || "READY", reason: cvYes(r.listed) ? why : "Not listed today: the market check failed. " + why, strength: null };
      }
      case "w52": {
        const hi = cvYes(r.new_high_today), lo = cvYes(r.new_low_today), near = cvYes(r.near_high);
        if (!hi && !lo && !near) return null;
        const status = hi ? "NEW HIGH today" : lo ? "NEW LOW today" : "NEAR HIGH";
        let reason = hi ? "Closed at a new 52-week high today." : lo ? "Closed at a new 52-week low today." :
          "Close is " + n(Math.abs(num(r.pct_from_high) || 0), 1) + "% under the 52-week high.";
        if (num(r.volume_ratio) != null) reason += " Volume " + n(r.volume_ratio, 1) + " times the 50-day average.";
        return { status: status, reason: reason, strength: null };
      }
      case "brk": {
        let reason = "Within " + n(Math.abs(num(r.dist_52w_high_pct) || 0), 1) + "% of the 52-week high.";
        if (num(r.volume_ratio) != null) reason += " Volume " + n(r.volume_ratio, 1) + " times normal.";
        return { status: "NEAR 52-WEEK HIGH", reason: reason, strength: null };
      }
      case "hv": {
        if (!cvYes(r.passes_default)) return null;
        const up = String(r.day_type || "").toLowerCase().indexOf("down") < 0 && (num(r.day_pct) || 0) >= 0;
        const reason = "Volume " + n(r.volume_ratio, 1) + " times the 50-day average, price " +
          ((num(r.day_pct) || 0) >= 0 ? "up " : "down ") + n(Math.abs(num(r.day_pct) || 0), 2) + "% today." + (r.meaning ? " " + r.meaning : "");
        return { status: (up ? "UP DAY " : "DOWN DAY ") + n(r.volume_ratio, 1) + "x", reason: reason, strength: null };
      }
      case "gap": {
        const s = String(r.status || "").trim();
        if (s !== "GAP UP today" && s !== "GAP HOLDING") return null;
        const g = num(r.gap_pct);
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(r.gap_date || ""));
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const day = m ? months[Number(m[2]) - 1] + " " + Number(m[3]) : String(r.gap_date || "");
        let reason = "Gap Up " + (g == null ? "" : n(g, 1) + "% ") + "on " + day + ", holding.";
        if (num(r.volume_ratio) != null) reason += " Volume " + n(r.volume_ratio, 1) + "x the 50-day average.";
        if (num(r.hold_level) != null) reason += " Hold level ₹" + n(r.hold_level, 2) + ".";
        return { status: s, reason: reason, strength: null };
      }
      case "passes":
        if (!cvYes(r.passes)) return null;
        return { status: src.word, reason: r.why || "", strength: null };
      case "watch":
        return { status: "WATCHLIST", reason: "On your watchlist." + (r.timing ? " Trend: " + r.timing + "." : ""), strength: null };
      default:
        return null;
    }
  }
  function cvCount(rec) { return rec.hits.filter((h) => !h.extra).length; }
  // group: "technical" or "fundamental" keeps only that group's scanners, so the All list, the
  // counts and the reason box use that group alone. Buy setups and the Watchlist still add their
  // line to stocks already on the list. No group: every scanner, as before.
  function cvBuild(files, group) {
    const lists = {};
    const all = new Map();
    const add = (src, into, rows, onlyKnown) => {
      realRows(rows || []).forEach((r) => {
        const ticker = String(r.ticker || "").trim().toUpperCase();
        if (!ticker) return;
        const e = cvEntry(src, r);
        if (!e) return;
        let rec = into.get(ticker);
        if (!rec && onlyKnown) return;
        const item = { src: src.id, label: src.short, status: e.status, reason: e.reason, strength: e.strength, extra: !!src.extra };
        if (!rec) {
          rec = { ticker: ticker, company: String(r.company || ""), hits: [], strength: null, score: num(r.score) };
          into.set(ticker, rec);
        }
        if (!rec.company && r.company) rec.company = String(r.company);
        if (rec.score == null && num(r.score) != null) rec.score = num(r.score);
        if (rec.hits.some((h) => h.src === src.id)) return;
        if (src.extra) rec.hits.unshift(item);
        else rec.hits.push(item);
        if (e.strength != null && (rec.strength == null || e.strength > rec.strength)) rec.strength = e.strength;
      });
    };
    const order = (arr) => arr.slice().sort((a, b) =>
      (cvCount(b) - cvCount(a)) ||
      ((b.strength == null ? -1 : b.strength) - (a.strength == null ? -1 : a.strength)) ||
      ((b.score == null ? -99 : b.score) - (a.score == null ? -99 : a.score)) ||
      (a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0));
    const sources = CV_SOURCES.filter((s) => featureOn(FEATURE[s.id]) && (!s.opt || cvOpt(s.opt)) && (!group || groupOf(s.id) === group));
    const singles = {};
    sources.forEach((src) => {
      add(src, all, files[src.file]);
      const one = new Map();
      add(src, one, files[src.file]);
      singles[src.id] = Array.from(one.keys());
    });
    const buyOn = cvOpt("include_buy_setups") && featureOn(FEATURE.buysetups);
    const watchOn = cvOpt("include_watchlist") && featureOn(FEATURE.watchlist);
    // Buy setups and the Watchlist only add a line to the reason box of stocks already counted.
    if (buyOn) add(CV_BUY, all, files[CV_BUY.file], true);
    if (watchOn) add(CV_WATCH, all, files[CV_WATCH.file], true);
    lists.all = order(Array.from(all.values()));
    sources.forEach((src) => { lists[src.id] = order(singles[src.id].map((t) => all.get(t))); });
    const choices = [{ id: "all", label: group ? "All " + group + " stocks" : "All scanner stocks" }];
    const own = (src) => {
      const m = new Map();
      add(src, m, files[src.file]);
      return Array.from(m.values()).map((rec) => all.get(rec.ticker) || rec);
    };
    if (buyOn) { lists.buysetups = order(own(CV_BUY)); choices.push({ id: "buysetups", label: "Buy setups" }); }
    sources.forEach((s) => choices.push({ id: s.id, label: s.label }));
    if (watchOn && realRows(files[CV_WATCH.file] || []).length) {
      lists.watchlist = own(CV_WATCH);
      choices.push({ id: "watchlist", label: "Watchlist" });
    }
    return { lists: lists, choices: choices };
  }
  function cvStore(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* storage can be blocked */ } }
  function cvRead(key) { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; } }
  function cvStatusColor(s) {
    const t = String(s || "");
    if (/BROKEN OUT|NEW HIGH|EP TODAY|UP DAY|GAP UP|GAP HOLDING/.test(t)) return UP;
    if (/READY|NEAR|HIGH ON VOLUME|PULLBACK|WATCHING|SELL PART/.test(t)) return AM;
    if (/NEW LOW|DOWN DAY/.test(t)) return DN;
    if (/IN TRADE|PASSES|WATCHLIST/.test(t)) return AC;
    return MU;
  }
  function cvLinkHtml(listId, ticker) {
    if (!featureOn("feature.chart_viewer") || !cvOpt("scanner_links")) return "";
    const href = "chart-viewer.html?list=" + encodeURIComponent(listId) + (ticker ? "&t=" + encodeURIComponent(ticker) : "");
    return '<a class="cvlink" id="cvlink" data-list="' + esc(listId) + '" href="' + esc(href) + '">Open in Chart Viewer</a>';
  }
  function placeViewerLink(pageId) {
    if (pageId !== CV_WATCH.id && pageId !== CV_BUY.id && !CV_SOURCES.some((s) => s.id === pageId)) return;
    const html = cvLinkHtml(pageId, "");
    const page = document.getElementById("page");
    if (html && page) page.insertAdjacentHTML("beforebegin", '<div class="cvlinkrow">' + html + "</div>");
  }
  // A scanner page calls this when the picked row changes, so the link starts there.
  function setViewerStart(ticker) {
    const a = document.getElementById("cvlink");
    if (!a) return;
    const list = a.getAttribute("data-list");
    a.setAttribute("href", "chart-viewer.html?list=" + encodeURIComponent(list) + (ticker ? "&t=" + encodeURIComponent(String(ticker).toUpperCase()) : ""));
  }

  // Looks and works like the US desk's Chart Viewer (site/js/viewer.js there): the same header,
  // chip bar, reason box, swipes and first view, with the India lists, ₹ prices and NSE bars.
  // How many empty bars to leave on the right so a box of boxPx does not cover the last candles
  // (same rule as the US desk's padBars). With no box it is 3 bars.
  function cvPadBars(visibleBars, plotPx, boxPx) {
    if (!(visibleBars > 0) || !(plotPx > 0) || !(boxPx > 0)) return 3;
    if (plotPx - boxPx < plotPx * 0.35) boxPx = plotPx * 0.65;
    return Math.max(3, (boxPx * visibleBars) / (plotPx - boxPx));
  }
  // Where a touch started: "bar" (the header row, or a chip bar that fits, so a sideways swipe
  // changes the chart), "scroll" (a chip bar wider than the screen: it scrolls and never changes
  // the chart), or "chart" (the chart itself, where only a quick flick changes it).
  function cvSwipeZone(inHeader, inTools, toolsScrollWidth, toolsClientWidth) {
    if (inHeader) return "bar";
    if (inTools) return toolsScrollWidth > toolsClientWidth + 1 ? "scroll" : "bar";
    return "chart";
  }
  function cvSavedGroup() {
    try { const v = localStorage.getItem("desk-cv-group"); return GROUP_IDS.indexOf(v) >= 0 ? v : ""; } catch (e) { return ""; }
  }
  function renderChartViewer(ctx) {
    const params = new URLSearchParams(location.search);
    // Technical | Fundamental switch (feature.split_tech_fund and chart_viewer.group_toggle).
    // The last choice is kept on this device; chart_viewer.default_group is the first choice.
    // A link from a scanner page opens that scanner's group.
    const grouped = splitOn() && cvOpt("group_toggle");
    let group = null;
    if (grouped) {
      const def = String(cvOpt("default_group") || "").toLowerCase();
      group = cvSavedGroup() || (GROUP_IDS.indexOf(def) >= 0 ? def : "technical");
      const asked = params.get("list") || "";
      const askedGroup = CV_SOURCES.some((s) => s.id === asked) ? groupOf(asked) : "";
      if (GROUP_IDS.indexOf(askedGroup) >= 0) group = askedGroup;
    }
    const builds = {};
    const buildFor = (g) => builds[g || "_"] || (builds[g || "_"] = cvBuild(ctx.files, g));
    let built = buildFor(group);
    let listId = params.get("list") || "all";
    if (!built.lists[listId]) listId = "all";
    const ma = {};
    const savedMa = cvRead("desk-cv-ma") || {};
    CV_MAS.forEach((d) => { ma[d.id] = typeof savedMa[d.id] === "boolean" ? savedMa[d.id] : cvOpt(d.id); });
    const savedVol = cvOpt("volume_toggle") ? cvRead("desk-cv-volume") : null;
    let volOn = typeof savedVol === "boolean" ? savedVol : cvOpt("volume");
    const savedSwipe = cvOpt("flip_toggle") ? cvRead("desk-cv-swipe-right-next") : null;
    let rightIsNext = typeof savedSwipe === "boolean" ? savedSwipe : cvOpt("swipe_right_is_next");
    const reasonAllowed = cvOpt("reason_box");
    const swipeOn = cvOpt("swipe");
    const fewItems = Math.max(1, cvOpt("reason_collapsed_items"));
    const savedReason = reasonAllowed && cvOpt("reason_box_toggle") ? cvRead("desk-cv-reason") : null;
    let reasonOn = reasonAllowed && (typeof savedReason === "boolean" ? savedReason : true);
    let reasonOpen = false;
    // Drag: move chart (pan back and forward in time, pinch to zoom) or Drag: next chart, where
    // the chart ignores one-finger drags and pinch zoom is off. The Drag chip (drag_mode_toggle)
    // flips it and the choice is saved on this device.
    const dragToggle = swipeOn && cvOpt("drag_mode_toggle");
    const savedPan = dragToggle ? cvRead("desk-cv-drag-pan") : null;
    let dragPan = typeof savedPan === "boolean" ? savedPan : cvOpt("chart_touch_pan");
    const CV_RANGES = [{ id: "r3", label: "3M", months: 3 }, { id: "r6", label: "6M", months: 6 }, { id: "r12", label: "1Y", months: 12 }, { id: "rall", label: "All", months: 0 }];
    let rangePick = null;
    const maxChars = cvOpt("reason_max_chars");

    const optionsHtml = () => built.choices.map((c) => {
      const count = (built.lists[c.id] || []).length;
      return '<option value="' + esc(c.id) + '"' + (c.id === listId ? " selected" : "") + ">" + esc(c.label + " (" + count + ")") + "</option>";
    }).join("");
    const segHtml = () => GROUP_IDS.map((g) => '<button type="button" data-grp="' + g + '" class="' + (g === group ? "on" : "") +
      '" aria-pressed="' + (g === group ? "true" : "false") + '">' + esc(GROUP_NAMES[g]) + "</button>").join("");
    const chip = (id, label, color, on, cls) =>
      '<button type="button" class="cvchip' + (cls ? " " + cls : "") + (on ? " on" : "") + '" data-chip="' + id + '" aria-pressed="' + (on ? "true" : "false") + '">' +
      (color ? '<i style="background:' + color + '"></i>' : "") + esc(label) + "</button>";
    const chipsHtml = () =>
      (cvOpt("ma_chips") ? CV_MAS.map((d) => chip(d.id, "MA " + d.n, maColor(d.n, d.color), ma[d.id])).join("") : "") +
      (cvOpt("volume_toggle") ? chip("volume", "Vol", "", volOn) : "") +
      (reasonAllowed && cvOpt("reason_box_toggle") ? chip("reason", "Why", "", reasonOn) : "") +
      (swipeOn && cvOpt("flip_toggle") ? chip("swipe", rightIsNext ? "Swipe right: next" : "Swipe left: next", "", false, "cvflip") : "") +
      (dragToggle ? chip("drag", "Drag: " + (dragPan ? "move chart" : "next chart"), "", dragPan) : "") +
      (cvOpt("range_chips") ? CV_RANGES.map((r) => chip(r.id, r.label, "", rangePick === r.months, "cvrange")).join("") : "");
    const showBlurb = cvOpt("company_line") && featureOn("feature.company_line");
    ctx.page.innerHTML =
      '<div class="cvbar">' + (grouped ? '<div class="seg cvseg" id="cvseg" role="group" aria-label="Technical or fundamental">' + segHtml() + "</div>" : "") +
      (cvOpt("list_picker") ? '<label class="cvpick"><span class="lab">List</span><select id="cvlist" aria-label="Which list">' + optionsHtml() + "</select></label>" : "") +
      (cvOpt("fullscreen") ? '<button type="button" class="cvbtn cvgo" id="cvfull">Full screen</button>' : "") + "</div>" +
      '<p class="cap" id="cvsum"></p>' +
      '<section class="cv-stage" id="cvstage" aria-label="Chart Viewer" tabindex="-1">' +
      '<div class="cv-top"><div class="cv-id"><div class="cv-line"><span class="cv-tk" id="cvtk"></span><span class="cv-co" id="cvco"></span></div>' +
      (showBlurb ? '<div class="cv-blurb" id="cvblurb" hidden></div>' : "") + "</div>" +
      '<div class="cv-px" id="cvpx"></div>' +
      (cvOpt("counter") ? '<div class="cv-count" id="cvcount"></div>' : "") +
      '<button type="button" class="cv-exit" id="cvexit" aria-label="Close full screen">✕</button></div>' +
      '<div class="cv-chips" id="cvchips"></div>' +
      '<div class="cv-plot" id="cvplot"><div class="cv-host" id="cvhost"></div>' +
      '<div class="cv-msg" id="cvmsg" hidden></div>' +
      (reasonAllowed ? '<div class="cv-reason" id="cvreason" role="button" tabindex="0" aria-expanded="false" aria-label="Why this stock is listed. Tap to open or close." hidden></div>' : "") +
      (cvOpt("arrows") ? '<button type="button" class="cv-arrow cv-prev" id="cvprev" aria-label="Previous chart">‹</button>' +
        '<button type="button" class="cv-arrow cv-next" id="cvnext" aria-label="Next chart">›</button>' : "") +
      "</div></section>" +
      '<p class="cap">Daily bars saved by the desk. Averages are worked out in your browser. ' +
      (swipeOn ? "Swipe " + (rightIsNext ? "right" : "left") + " for the next chart. " +
        (dragPan ? "Drag the chart slowly to see older days, and flick fast or swipe on the top row to change the chart. " : "") : "") +
      'Charting by <a href="https://www.tradingview.com/">TradingView</a> Lightweight Charts™.</p>';

    const stage = document.getElementById("cvstage");
    const host = document.getElementById("cvhost");
    const msg = document.getElementById("cvmsg");
    const reasonEl = document.getElementById("cvreason");
    const chipsEl = document.getElementById("cvchips");
    const st = { list: built.lists[listId] || [], i: 0, token: 0, chart: null, price: null, vol: null, mas: {}, bars: [], group: group, built: built };
    stage._cv = st;
    const start = String(params.get("t") || "").toUpperCase();
    if (start) {
      const at = st.list.findIndex((r) => r.ticker === start);
      if (at >= 0) st.i = at;
    }
    const summary = () => {
      const sum = document.getElementById("cvsum");
      const c = built.choices.find((x) => x.id === listId);
      const n = st.list.length;
      sum.textContent = n ? (c ? c.label : "List") + ": " + n + " stock" + (n === 1 ? "" : "s") + (listId === "all" ? ", the ones on the most scanners first." : ".")
        : "No stocks on this list today.";
    };
    const paintChips = () => {
      const scroll = chipsEl.scrollLeft;
      chipsEl.innerHTML = chipsHtml();
      chipsEl.hidden = !chipsEl.innerHTML;
      chipsEl.scrollLeft = scroll;
    };

    // ---- Reason box: which scanners list the stock, its status and why.
    const reasonHtml = (rec) => {
      if (!rec.hits.length) return '<div class="cv-why-h">Why it is here</div><div class="cv-why-r">Not on a scanner list today.</div>';
      const count = cvCount(rec);
      const few = reasonOpen ? rec.hits : rec.hits.slice(0, fewItems);
      const hidden = rec.hits.length - few.length;
      return '<div class="cv-why-h">Why it is here' + (count ? " (" + count + " scanner" + (count === 1 ? "" : "s") + ")" : "") + "</div>" +
        few.map((h) => '<div class="cv-why-i"><span class="cv-why-l">' + esc(h.label) + '</span> <span class="cv-why-s" style="color:' + cvStatusColor(h.status) + '">' +
          esc(h.status) + "</span>" + (h.reason ? '<div class="cv-why-r">' + esc(reasonOpen ? cvShort(h.reason) : cvShort(h.reason, maxChars)) + "</div>" : "") + "</div>").join("") +
        '<div class="cv-why-x">' + (reasonOpen ? "Tap to make it small" : (hidden ? "+ " + hidden + " more. " : "") + "Tap to read all") + "</div>";
    };
    const placeReason = () => {
      if (!reasonEl || !st.chart || reasonEl.hidden) return;
      let psw = 56, tsh = 26;
      try { psw = st.chart.priceScale("right").width() || psw; } catch (e) { /* not drawn yet */ }
      try { tsh = st.chart.timeScale().height() || tsh; } catch (e) { /* not drawn yet */ }
      reasonEl.style.right = (psw + 6) + "px";
      reasonEl.style.bottom = (tsh + 6) + "px";
    };
    const paintReason = () => {
      if (!reasonEl) return;
      const rec = st.list[st.i];
      reasonEl.hidden = !reasonOn || !rec;
      if (reasonEl.hidden) return;
      reasonEl.classList.toggle("open", reasonOpen);
      reasonEl.setAttribute("aria-expanded", reasonOpen ? "true" : "false");
      reasonEl.innerHTML = reasonHtml(rec);
      requestAnimationFrame(placeReason);
    };

    // ---- First view. The chart holds every saved daily bar, so a drag can go back in time.
    // range_months (or range_months_phone when the chart is under 520 pixels wide), or a range chip,
    // picks the first view: the first bar of the range on the left edge, and on the right just enough
    // empty bars that the Why box does not cover the last candles, so the newest candle lands just
    // left of the box, in the same spot on every chart (the US rule). With the box hidden the gap is
    // 3 bars. It is set with bar numbers
    // after the data is in and only once the chart has its real width, and set again on every chart,
    // swipe, resize, range chip and full screen, like the US desk. Opening or closing the Why box
    // keeps the view. If it were set while the chart was still a few pixels wide,
    // the bars would be packed at the smallest spacing and stay squeezed against the right edge.
    const boxPad = () => (!reasonEl || reasonEl.hidden || !st.chart ? 0 : reasonEl.offsetWidth + 14);
    let viewW = 0;
    const cvRange = (bars, w) => {
      const months = rangePick != null ? rangePick : Math.max(1, w < 520 ? cvOpt("range_months_phone") : cvOpt("range_months"));
      const last = bars.length - 1;
      let from = 0;
      if (months) {
        const cut = new Date(bars[last].date + "T00:00:00Z");
        cut.setUTCMonth(cut.getUTCMonth() - months);
        const iso = cut.toISOString().slice(0, 10);
        from = Math.max(0, bars.findIndex((b) => b.date >= iso));
      }
      const pad = cvPadBars(last - from + 1, w, reasonOpen ? Math.min(boxPad(), 260) : boxPad());
      let lo = from - 0.5, hi = last + pad;
      // All on a phone can need bars thinner than the chart allows (0.3 px). Then show as much
      // history as fits and keep the newest candle in the same spot left of the Why box.
      const sp = w / (hi - lo);
      if (sp < 0.3) { hi = last + (pad * sp) / 0.3; lo = hi - w / 0.3; }
      st.pad = hi - last;
      setRange({ from: lo, to: hi });
      const want = lastSet;
      // The price scale can grow a few pixels once the new range is drawn, which cuts the first
      // bars off the left (seen with the All chip). Set the same range once more on the next frame.
      const chart = st.chart;
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => {
        if (st.chart === chart && lastSet && lastSet.from === want.from && lastSet.to === want.to) setRange(want);
      });
    };
    // A range the user dragged or pinched to on this chart (same as the US desk). It is read when a
    // finger or the mouse lets go of the chart, and only counts when it differs from the view set
    // last. A resize, a turn of the device or full screen keeps it; a new chart or a range chip
    // clears it and puts the first view back. Turning Vol on or off keeps it.
    let userRange = null;
    let carryRange = null;
    let lastSet = null;
    let pressTimer = 0;
    const setRange = (r) => {
      lastSet = { from: r.from, to: r.to };
      try { st.chart.timeScale().setVisibleLogicalRange(lastSet); } catch (e) { /* chart is gone */ }
    };
    const readUserRange = () => {
      if (!st.chart || !lastSet) return;
      let lr = null;
      try { lr = st.chart.timeScale().getVisibleLogicalRange(); } catch (e) { return; }
      if (lr && (Math.abs(lr.from - lastSet.from) > 0.5 || Math.abs(lr.to - lastSet.to) > 0.5)) {
        userRange = { from: lr.from, to: lr.to };
        lastSet = { from: lr.from, to: lr.to };
      }
    };
    st.userRange = () => userRange;
    // Put the right view back: the dragged range if there is one, else the first view, but only once
    // the chart is at least 120 px wide. A chart still being laid out waits for the next resize.
    const applyView = (fresh) => {
      if (!st.chart || !st.bars.length) return;
      placeReason();
      if (fresh) userRange = null;
      let w = 0;
      try { w = st.chart.timeScale().width(); } catch (e) { w = 0; }
      if (userRange && Number.isFinite(userRange.from) && Number.isFinite(userRange.to) && userRange.to > userRange.from) { setRange(userRange); return; }
      if (w < 120) { viewW = 0; return; }
      viewW = w;
      cvRange(st.bars, w);
    };
    st.applyView = applyView;
    let viewRaf = 0;
    const viewSoon = () => {
      cancelAnimationFrame(viewRaf);
      viewRaf = requestAnimationFrame(() => { viewRaf = requestAnimationFrame(() => applyView()); });
    };
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(viewSoon).observe(host);
    window.addEventListener("orientationchange", () => setTimeout(() => applyView(), 250));
    const pressOn = () => { clearTimeout(pressTimer); };
    const pressOff = () => { clearTimeout(pressTimer); pressTimer = setTimeout(readUserRange, 120); };
    ["pointerdown", "touchstart"].forEach((ev) => host.addEventListener(ev, pressOn, { passive: true, capture: true }));
    ["pointerup", "pointercancel", "touchend", "touchcancel"].forEach((ev) => host.addEventListener(ev, pressOff, { passive: true, capture: true }));
    host.addEventListener("wheel", pressOff, { passive: true, capture: true });

    // ---- The chart: made new for each stock, like the US desk, so nothing carries over.
    const panOptions = () => ({
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: dragPan, vertTouchDrag: false },
      handleScale: { mouseWheel: true, pinch: dragPan, axisPressedMouseMove: true, axisDoubleClickReset: true },
      kineticScroll: { touch: false, mouse: false },
    });
    const applyPan = () => { if (st.chart) st.chart.applyOptions(panOptions()); stage.classList.toggle("pan", dragPan); };
    const dropChart = () => {
      if (st.chart) {
        try { st.chart.remove(); } catch (e) { /* already gone */ }
        const k = tvCharts.indexOf(st.chart);
        if (k >= 0) tvCharts.splice(k, 1);
      }
      st.chart = null; st.price = null; st.vol = null; st.mas = {};
      viewW = 0;
    };
    const draw = (bars) => {
      dropChart();
      const LC = LightweightCharts;
      const chart = tvCreate(host, Object.assign({
        autoSize: true,
        layout: { background: { type: "solid", color: "#0B0F17" }, textColor: MU, fontFamily: "Roboto, Arial, sans-serif", fontSize: 11,
          attributionLogo: false, panes: { separatorColor: "#1E293B", separatorHoverColor: "rgba(0,0,0,0)", enableResize: false } },
        grid: { vertLines: { color: "#161E2E" }, horzLines: { color: "#161E2E" } },
        crosshair: { mode: LC.CrosshairMode.Magnet },
        rightPriceScale: { borderColor: "#1E293B", scaleMargins: { top: 0.08, bottom: 0.06 } },
        timeScale: { borderColor: "#1E293B", rightOffset: 4, minBarSpacing: 0.3 },
      }, panOptions()));
      tvCharts.push(chart);
      st.chart = chart;
      userRange = carryRange;
      carryRange = null;
      lastSet = null;
      st.price = chart.addSeries(LC.CandlestickSeries, {
        upColor: UP, downColor: DN, borderUpColor: UP, borderDownColor: DN, wickUpColor: UP, wickDownColor: DN,
        priceLineVisible: false, lastValueVisible: true,
      });
      st.price.setData(bars.map((b) => ({ time: b.date, open: b.o, high: b.h, low: b.l, close: b.c })));
      const closes = bars.map((b) => b.c);
      CV_MAS.forEach((d) => {
        const s = chart.addSeries(LC.LineSeries, { color: maColor(d.n, d.color), lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false, visible: !!ma[d.id] });
        const data = [];
        smaValues(closes, d.n).forEach((v, i) => { if (v != null) data.push({ time: bars[i].date, value: v }); });
        s.setData(data);
        st.mas[d.id] = s;
      });
      if (volOn) {
        st.vol = chart.addSeries(LC.HistogramSeries, { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false }, 1);
        st.vol.setData(bars.filter((b) => b.v != null).map((b) => ({
          time: b.date, value: b.v, color: b.c >= b.o ? "rgba(34,197,94,.45)" : "rgba(239,68,68,.45)",
        })));
        const panes = chart.panes();
        if (panes[0]) panes[0].setStretchFactor(4);
        if (panes[1]) panes[1].setStretchFactor(1);
      }
      requestAnimationFrame(() => applyView());
    };

    const header = (rec, bars) => {
      document.getElementById("cvtk").textContent = rec ? rec.ticker : "";
      document.getElementById("cvco").textContent = rec ? rec.company : "";
      const blurb = document.getElementById("cvblurb");
      if (blurb) fillCompanyLine(blurb, rec ? rec.ticker : "");
      const px = document.getElementById("cvpx");
      const count = document.getElementById("cvcount");
      if (count) count.textContent = st.list.length ? (st.i + 1) + " of " + st.list.length : "0 of 0";
      if (!bars || !bars.length) { px.innerHTML = ""; return; }
      const last = bars[bars.length - 1];
      const prev = bars.length > 1 ? bars[bars.length - 2].c : null;
      const pct = prev ? (last.c / prev - 1) * 100 : null;
      px.innerHTML = "<b>₹" + esc(fmt(last.c, 2)) + "</b>" + (pct == null || !cvOpt("day_change") ? "" :
        ' <span class="' + (pct >= 0 ? "up" : "dn") + '">' + (pct >= 0 ? "+" : "") + esc(fmt(pct, 2)) + "%</span>");
    };
    const say = (text) => { msg.hidden = !text; msg.textContent = text || ""; };

    // Keep only the last 6 charts in memory (this one, the next and back ones, and a few just
    // seen), so a long swipe through a list stays light on an iPad. A saved letter file is
    // forgotten once none of the kept charts need it.
    const CV_KEEP = 6;
    st.recent = [];
    const remember = (ticker) => {
      const out = st.recent.filter((t) => t !== ticker);
      out.push(ticker);
      const drop = [];
      while (out.length > CV_KEEP) drop.push(out.shift());
      st.recent = out;
      drop.forEach((t) => {
        cache.delete("ohlc/" + t + ".csv");
        const g = candleGroup(t);
        if (!out.some((k) => candleGroup(k) === g)) cache.delete("ohlc/" + g + ".csv.gz");
      });
    };
    st.cached = () => Array.from(cache.keys()).filter((k) => k.indexOf("ohlc/") === 0);
    const preload = () => {
      if (!cvOpt("preload_next") || st.list.length < 2) return;
      [1, -1].forEach((step) => {
        const rec = st.list[(st.i + step + st.list.length) % st.list.length];
        if (rec) { remember(rec.ticker); loadTickerBars(rec.ticker).catch(() => {}); }
      });
    };
    const show = () => {
      const token = ++st.token;
      const rec = st.list[st.i];
      stage.dataset.ticker = rec ? rec.ticker : "";
      if (rec && history.replaceState) {
        const q = new URLSearchParams(location.search);
        q.set("list", listId); q.set("t", rec.ticker);
        history.replaceState(null, "", location.pathname + "?" + q.toString());
      }
      paintReason();
      if (!rec) {
        header(null, null);
        dropChart();
        st.bars = [];
        say("No stocks on this list today. Pick another list.");
        stage.dataset.state = "empty";
        return;
      }
      header(rec, null);
      remember(rec.ticker);
      ensureTv().then(() => loadTickerBars(rec.ticker)).then((rows) => {
        if (token !== st.token) return;
        const bars = barsFromRows(rows);
        st.bars = bars;
        header(rec, bars);
        if (!bars.length) {
          dropChart();
          say("No saved chart for " + rec.ticker + ". Swipe for the next one.");
          stage.dataset.state = "nodata";
        } else {
          say("");
          draw(bars);
          stage.dataset.state = "ok";
        }
        requestAnimationFrame(placeReason);
        preload();
      }).catch(() => {
        if (token !== st.token) return;
        dropChart();
        st.bars = [];
        say("No saved chart for " + rec.ticker + ". Swipe for the next one.");
        stage.dataset.state = "nodata";
        preload();
      });
    };
    const go = (step) => {
      if (!st.list.length) return;
      st.i = (st.i + step + st.list.length) % st.list.length;
      reasonOpen = false;
      show();
    };
    st.go = go;

    paintChips();
    summary();
    chipsEl.addEventListener("click", (e) => {
      const b = e.target.closest("[data-chip]");
      if (!b) return;
      const id = b.getAttribute("data-chip");
      const range = CV_RANGES.find((r) => r.id === id);
      if (range) { rangePick = range.months; paintChips(); applyView(true); return; }
      if (id === "volume") { volOn = !volOn; cvStore("desk-cv-volume", volOn); paintChips(); if (st.bars.length && st.chart) { carryRange = userRange; draw(st.bars); } return; }
      if (id === "reason") { reasonOn = !reasonOn; cvStore("desk-cv-reason", reasonOn); paintChips(); paintReason(); return; }
      if (id === "swipe") { rightIsNext = !rightIsNext; cvStore("desk-cv-swipe-right-next", rightIsNext); }
      else if (id === "drag") { dragPan = !dragPan; cvStore("desk-cv-drag-pan", dragPan); applyPan(); }
      else if (ma[id] != null) { ma[id] = !ma[id]; cvStore("desk-cv-ma", ma); if (st.mas[id]) st.mas[id].applyOptions({ visible: !!ma[id] }); }
      paintChips();
    });
    if (reasonEl) {
      // Opening or closing the box never moves the chart, so a panned view stays where it is.
      const toggleReason = (e) => { if (e) e.stopPropagation(); reasonOpen = !reasonOpen; paintReason(); };
      reasonEl.addEventListener("click", toggleReason);
      reasonEl.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleReason(e); } });
    }
    const prevBtn = document.getElementById("cvprev");
    const nextBtn = document.getElementById("cvnext");
    if (prevBtn) prevBtn.addEventListener("click", () => go(-1));
    if (nextBtn) nextBtn.addEventListener("click", () => go(1));
    const listEl = document.getElementById("cvlist");
    const segEl = document.getElementById("cvseg");
    if (segEl) segEl.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-grp]");
      if (!b || b.getAttribute("data-grp") === group) return;
      group = b.getAttribute("data-grp");
      try { localStorage.setItem("desk-cv-group", group); } catch (err) { /* storage can be blocked */ }
      built = buildFor(group);
      if (!built.lists[listId]) listId = "all";
      st.group = group;
      st.built = built;
      segEl.innerHTML = segHtml();
      if (listEl) { listEl.innerHTML = optionsHtml(); listEl.value = listId; }
      st.list = built.lists[listId] || [];
      st.i = 0;
      reasonOpen = false;
      summary();
      show();
    });
    if (listEl) listEl.addEventListener("change", (e) => {
      listId = e.target.value;
      st.list = built.lists[listId] || [];
      st.i = 0;
      reasonOpen = false;
      summary();
      show();
    });

    // Swipes. A swipe must be swipe_min_px or more and swipe_ratio times more sideways than up
    // or down. On the chart itself, with Drag: move chart (chart_touch_pan), a one-finger drag pans
    // the same chart and two fingers zoom, so only a quick flick (faster than swipe_max_ms) changes
    // the chart; a slow drag never does. With Drag: next chart, any swipe on the chart changes it.
    // A swipe that starts on the header row (ticker, price and counter) always changes the chart.
    // On the chip bar it changes the chart only when every chip fits; a chip bar wider than the
    // screen just scrolls. A swipe that starts on the reason box, an arrow or the list picker is
    // ignored. Two fingers (pinch) never change the chart.
    let touch = null;
    stage.addEventListener("touchstart", (e) => {
      if (!swipeOn || e.touches.length !== 1 || e.target.closest(".cv-reason, .cv-arrow, select")) { touch = null; return; }
      const inTools = chipsEl.contains(e.target);
      const zone = cvSwipeZone(!!e.target.closest(".cv-top"), inTools, inTools ? chipsEl.scrollWidth : 0, inTools ? chipsEl.clientWidth : 0);
      if (zone === "scroll") { touch = null; return; }
      const t = e.touches[0];
      touch = { x: t.clientX, y: t.clientY, at: Date.now(), inChart: zone === "chart" };
    }, { passive: true, capture: true });
    stage.addEventListener("touchmove", (e) => {
      if (!touch) return;
      if (e.touches.length !== 1) { touch = null; return; }
      if (touch.inChart && dragPan) return;
      const t = e.touches[0];
      const dx = t.clientX - touch.x, dy = t.clientY - touch.y;
      if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy) && e.cancelable) e.preventDefault();
    }, { passive: false, capture: true });
    stage.addEventListener("touchend", (e) => {
      if (!touch) return;
      const t = e.changedTouches[0];
      const dx = t.clientX - touch.x, dy = t.clientY - touch.y, ms = Date.now() - touch.at;
      const inChart = touch.inChart;
      touch = null;
      if (e.touches.length) return;
      if (Math.abs(dx) < cvOpt("swipe_min_px") || Math.abs(dx) < Math.abs(dy) * cvOpt("swipe_ratio")) return;
      if (inChart && dragPan && ms > cvOpt("swipe_max_ms")) return;
      const right = dx > 0;
      go(right === rightIsNext ? 1 : -1);
    }, { passive: true, capture: true });
    stage.addEventListener("touchcancel", () => { touch = null; }, { passive: true, capture: true });
    stage.classList.toggle("pan", dragPan);

    // Full screen: the real Fullscreen API on desktop. iPhone Safari does not have it
    // and iPad Safari covers the name with its own X, so there the viewer fills the screen as a fixed layer over the menu and header.
    const fsEl = () => document.fullscreenElement || document.webkitFullscreenElement || null;
    const isFull = () => fsEl() === stage || stage.classList.contains("cv-fixed");
    const markFull = () => {
      const on = isFull();
      stage.classList.toggle("cv-full", on);
      document.body.classList.toggle("cv-lock", on);
      const fb = document.getElementById("cvfull");
      if (fb) fb.textContent = on ? "Exit full screen" : "Full screen";
      requestAnimationFrame(placeReason);
      viewSoon();
    };
    // iPad and iPhone Safari put their own grey close X in the top left over the stock name,
    // so there we always use the fixed layer (our close X stays on the right).
    // iPadOS reports itself as MacIntel, so touch points tell it apart from a Mac.
    const isIOS = () => {
      const ua = navigator.userAgent || "";
      return /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1);
    };
    const nativeOk = () => !isIOS() || cvOpt("native_fullscreen_ios");
    const enter = () => {
      const req = stage.requestFullscreen || stage.webkitRequestFullscreen;
      const fallback = () => { stage.classList.add("cv-fixed"); markFull(); };
      if (nativeOk() && req && (document.fullscreenEnabled || document.webkitFullscreenEnabled)) {
        try {
          const p = req.call(stage);
          if (p && p.catch) p.catch(fallback);
        } catch (e) { fallback(); }
      } else fallback();
    };
    const leave = () => {
      if (stage.classList.contains("cv-fixed")) { stage.classList.remove("cv-fixed"); markFull(); }
      if (fsEl()) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        if (exit) { try { const p = exit.call(document); if (p && p.catch) p.catch(() => {}); } catch (e) { /* ignore */ } }
      }
    };
    st.enter = enter;
    st.leave = leave;
    document.addEventListener("fullscreenchange", markFull);
    document.addEventListener("webkitfullscreenchange", markFull);
    const fullBtn = document.getElementById("cvfull");
    if (fullBtn) fullBtn.addEventListener("click", () => (isFull() ? leave() : enter()));
    document.getElementById("cvexit").addEventListener("click", leave);
    window.addEventListener("resize", () => requestAnimationFrame(placeReason));
    if (cvOpt("keyboard")) {
      document.addEventListener("keydown", (e) => {
        const tag = (e.target && e.target.tagName) || "";
        if (/INPUT|SELECT|TEXTAREA/.test(tag)) return;
        if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
        else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
        else if (e.key === "Escape" && stage.classList.contains("cv-fixed")) leave();
      });
    }
    show();
  }

  // Technical and Fundamental. With feature.split_tech_fund on, the menu shows the screeners
  // under two headings and the Chart Viewer gets a Technical | Fundamental switch. Each page id
  // below can be moved with scanner_groups.<id> in config.json ("technical" or "fundamental").
  // The order here is the menu order. Off: one combined menu and one All list, as before.
  const GROUP_DEFAULTS = {
    vcp: "technical", box: "technical", flag: "technical", qullamaggie: "technical", marios: "technical",
    episodic: "technical", gapup: "technical", week52: "technical", breakouts: "technical", highvol: "technical",
    pullbacks: "technical", trends: "technical", wheel: "technical",
    canslim: "fundamental", leaders: "fundamental", growth: "fundamental", quality: "fundamental",
    dividend: "fundamental", divfund: "fundamental", scorecard: "fundamental", top: "fundamental",
  };
  const GROUP_IDS = ["technical", "fundamental"];
  const GROUP_NAMES = { technical: "Technical", fundamental: "Fundamental" };
  function splitOn() { return featureOn("feature.split_tech_fund"); }
  function groupOf(id) {
    // Any other word keeps that page where it was and out of both groups (same as the US desk).
    const row = SETTINGS.find((r) => r.setting === "scanner_groups." + id);
    if (row && !isBlank(row.value)) {
      const v = String(row.value).trim().toLowerCase();
      return GROUP_IDS.indexOf(v) >= 0 ? v : "";
    }
    return GROUP_DEFAULTS[id] || "";
  }
  // The menu. Split: the Scanners heading becomes Technical and Fundamental, and every page in
  // GROUP_DEFAULTS moves under its group. The rest of the old Technicals heading (gainers and
  // losers, breadth, sector performance, heatmaps) is market-wide, so it is called Market.
  function navGroups() {
    if (!splitOn()) return NAV;
    const items = {};
    NAV.forEach((g) => g[1].forEach((it) => { items[it[2]] = it; }));
    const grouped = new Set(Object.keys(GROUP_DEFAULTS).filter((id) => items[id] && groupOf(id)));
    const pick = (g) => Object.keys(GROUP_DEFAULTS).filter((id) => items[id] && groupOf(id) === g).map((id) => items[id]);
    const out = [];
    NAV.forEach(([name, list]) => {
      if (name === "Scanners") {
        GROUP_IDS.forEach((g) => out.push([GROUP_NAMES[g], pick(g)]));
        return;
      }
      const rest = list.filter((it) => !grouped.has(it[2]));
      if (rest.length) out.push([name === "Technicals" ? "Market" : name, rest]);
    });
    return out;
  }

  function navOn(items) {
    return items.filter((it) => !FEATURE[it[2]] || featureOn(FEATURE[it[2]]));
  }
  const SEARCH_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 16.5L20.5 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  let deskNames = null;
  function deskList() {
    if (deskNames) return Promise.resolve(deskNames);
    return loadCsv("scores.csv").then((rows) => {
      deskNames = realRows(rows).filter((r) => r.ticker).map((r) => ({
        ticker: String(r.ticker).trim().toUpperCase(),
        company: String(r.company || ""),
        score: r.score,
        verdict: String(r.verdict || ""),
      }));
      return deskNames;
    });
  }
  function searchRank(q, row) {
    const query = q.toLowerCase();
    const ticker = row.ticker.toLowerCase();
    const company = row.company.toLowerCase();
    if (ticker.startsWith(query)) return 0;
    if (company.startsWith(query)) return 1;
    if (company.split(/[^a-z0-9]+/).some((w) => w && w.startsWith(query))) return 2;
    if (ticker.indexOf(query) >= 0) return 3;
    if (company.indexOf(query) >= 0) return 4;
    return -1;
  }
  function searchHits(q, rows) {
    const ranked = [];
    rows.forEach((row) => {
      const rank = searchRank(q, row);
      if (rank >= 0) ranked.push([rank, row]);
    });
    ranked.sort((a, b) => a[0] - b[0] || (a[1].ticker < b[1].ticker ? -1 : a[1].ticker > b[1].ticker ? 1 : 0));
    return ranked.slice(0, 8).map((pair) => pair[1]);
  }
  function wireSearch(setNav) {
    const input = document.getElementById("q");
    const pop = document.getElementById("qlist");
    const btn = document.getElementById("qbtn");
    const narrowQ = window.matchMedia("(max-width: 1179px)");
    let active = 0;
    let hits = [];
    function place() {
      const search = document.getElementById("search");
      if (narrowQ.matches) document.querySelector(".hdr").insertBefore(search, document.querySelector(".titles"));
      else {
        document.getElementById("qslot").appendChild(search);
        document.body.classList.remove("search-open");
        btn.setAttribute("aria-expanded", "false");
      }
    }
    function position() {
      if (!pop || pop.hidden) return;
      const rect = input.getBoundingClientRect();
      const width = Math.min(360, Math.max(rect.width, 260), window.innerWidth - 16);
      let left = rect.left;
      if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
      pop.style.left = left + "px";
      pop.style.top = Math.round(rect.bottom + 4) + "px";
      pop.style.width = Math.round(width) + "px";
    }
    function paint(message, rows) {
      hits = rows || [];
      if (!input.value.trim() && !message) {
        pop.hidden = true;
        pop.innerHTML = "";
        input.setAttribute("aria-expanded", "false");
        input.removeAttribute("aria-activedescendant");
        return;
      }
      if (message) {
        pop.innerHTML = '<div class="qmiss">' + esc(message) + "</div>";
        pop.hidden = false;
        input.setAttribute("aria-expanded", "true");
        input.removeAttribute("aria-activedescendant");
        position();
        return;
      }
      if (!hits.length) {
        pop.hidden = true;
        pop.innerHTML = "";
        input.setAttribute("aria-expanded", "false");
        return;
      }
      if (active >= hits.length) active = 0;
      pop.innerHTML = hits.map((row, i) => {
        const color = row.verdict === "BUY" ? UP : row.verdict === "HOLD" ? AM : row.verdict === "AVOID" ? DN : row.verdict === "Not scored yet" ? MU : TX;
        const score = num(row.score);
        const scoreText = score == null ? "–" : (Number.isInteger(score) ? String(score) : fmt(score, 1));
        return '<button type="button" class="qrow' + (i === active ? " on" : "") + '" role="option" id="qopt' + i + '" data-t="' + esc(row.ticker) + '" aria-selected="' + (i === active ? "true" : "false") + '">' +
          '<span class="tk">' + esc(row.ticker) + '</span><span class="qname">' + esc(row.company || "") + "</span>" +
          '<span class="qscore">' + esc(scoreText) + '</span><span class="pill" style="color:' + color + '">' + esc(row.verdict || "–") + "</span></button>";
      }).join("");
      pop.hidden = false;
      input.setAttribute("aria-expanded", "true");
      input.setAttribute("aria-activedescendant", "qopt" + active);
      const current = document.getElementById("qopt" + active);
      if (current) {
        const top = current.offsetTop;
        if (top < pop.scrollTop) pop.scrollTop = top;
        else if (top + current.offsetHeight > pop.scrollTop + pop.clientHeight) pop.scrollTop = top + current.offsetHeight - pop.clientHeight;
      }
      position();
    }
    function renderList() {
      const q = input.value.trim();
      if (!q) { paint("", []); return; }
      deskList().then((rows) => {
        if (input.value.trim() !== q) return;
        const found = searchHits(q, rows);
        if (!found.length) paint("Not in the desk's " + rows.length + " stocks", []);
        else paint("", found);
      }).catch(() => {
        if (input.value.trim() !== q) return;
        paint("The desk list could not load.", []);
      });
    }
    function openSearch() {
      if (narrowQ.matches) {
        setNav(false);
        document.body.classList.add("search-open");
        btn.setAttribute("aria-expanded", "true");
      }
      input.focus();
      if (input.value.trim()) renderList();
    }
    function closeSearch() {
      document.body.classList.remove("search-open");
      btn.setAttribute("aria-expanded", "false");
      paint("", []);
    }
    place();
    if (narrowQ.addEventListener) narrowQ.addEventListener("change", () => { place(); position(); });
    btn.addEventListener("click", () => {
      if (document.body.classList.contains("search-open")) closeSearch();
      else openSearch();
    });
    input.addEventListener("input", () => { active = 0; renderList(); });
    input.addEventListener("focus", () => { if (input.value.trim()) renderList(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && hits.length) {
        e.preventDefault();
        active = (active + 1) % hits.length;
        paint("", hits);
      } else if (e.key === "ArrowUp" && hits.length) {
        e.preventDefault();
        active = (active - 1 + hits.length) % hits.length;
        paint("", hits);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (hits[active]) location.href = "scorecard.html?t=" + encodeURIComponent(hits[active].ticker);
      } else if (e.key === "Escape") {
        e.preventDefault();
        input.value = "";
        closeSearch();
        input.blur();
      }
    });
    pop.addEventListener("mousedown", (e) => { e.preventDefault(); });
    pop.addEventListener("click", (e) => {
      const row = e.target.closest(".qrow");
      if (row) location.href = "scorecard.html?t=" + encodeURIComponent(row.getAttribute("data-t"));
    });
    document.addEventListener("keydown", (e) => {
      const tag = (e.target && e.target.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea" || (e.target && e.target.isContentEditable);
      const slash = e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey;
      const chord = (e.metaKey || e.ctrlKey) && !e.altKey && (e.key === "k" || e.key === "K");
      if (slash || chord) {
        e.preventDefault();
        openSearch();
      }
    });
    document.addEventListener("click", (e) => {
      if (e.target.closest("#search") || e.target.closest("#qbtn") || e.target.closest("#qlist")) return;
      if (narrowQ.matches) closeSearch();
      else paint("", []);
    });
    window.addEventListener("resize", position);
    deskList().catch(() => {});
  }
  function renderShell(page) {
    const menuGroups = navGroups();
    const groups = menuGroups.map(([name, items]) => {
      const shown = navOn(items);
      if (!shown.length) return "";
      const open = shown.some((it) => it[2] === page.id);
      const links = open ? shown.map((it) => {
        return '<a class="item' + (it[2] === page.id ? " sel" : "") + '" href="' + it[1] + '">' + esc(it[0]) + "</a>";
      }).join("") : "";
      return '<div class="group" data-open="' + (open ? "1" : "0") + '">' +
        '<button type="button" class="grp" aria-expanded="' + (open ? "true" : "false") + '"><span class="chev">' +
        (open ? "▾" : "▸") + "</span>" + esc(name) + '<span class="cnt">' + shown.length + "</span></button>" +
        '<div class="items"' + (open ? "" : ' hidden') + ">" + links + "</div></div>";
    }).join("");
    document.getElementById("app").innerHTML =
      '<div class="scrim" id="scrim"></div>' +
      '<div class="app"><nav class="nav" id="nav"><a class="brand" href="index.html"><span class="logo">N</span><span>Nick\'s India Stock Desk</span></a>' +
      '<div id="qslot"><div class="qwrap" id="search"><input id="q" type="search" placeholder="Search stocks" autocomplete="off" spellcheck="false" enterkeyhint="search" aria-label="Search stocks" role="combobox" aria-autocomplete="list" aria-controls="qlist" aria-expanded="false" title="Search stocks. Press / or Ctrl+K">' +
      '<div class="qpop" id="qlist" role="listbox" hidden></div></div></div>' + themeToggleHtml() +
      groups + "</nav><div class=\"main\"><div class=\"hdr\">" +
      '<button type="button" class="menu-btn" id="menu" aria-label="Open menu" aria-controls="nav" aria-expanded="false">☰</button>' +
      '<button type="button" class="search-btn" id="qbtn" aria-label="Search stocks" aria-expanded="false" aria-controls="q">' + SEARCH_ICON + "</button>" +
      "<div class=\"titles\"><h1>" + esc(page.title) + "</h1><div class=\"rl\">" + esc(RESEARCH) + "</div></div>" +
      '<div class="upd">Updated <b id="updated">…</b></div></div><div id="page"></div></div></div>';
    document.getElementById("nav").addEventListener("click", (e) => {
      const btn = e.target.closest(".grp");
      if (!btn) {
        if (e.target.closest("a.item")) document.body.classList.remove("nav-open");
        return;
      }
      const group = btn.parentElement;
      const items = group.querySelector(".items");
      const open = items.hasAttribute("hidden");
      if (open) {
        const name = btn.textContent.replace(/[▾▸]/g, "").replace(/\d+$/, "").trim();
        const spec = menuGroups.find((g) => g[0] === name);
        if (spec && !items.childElementCount) {
          items.innerHTML = navOn(spec[1]).map((it) => {
            return '<a class="item' + (it[2] === page.id ? " sel" : "") + '" href="' + it[1] + '">' + esc(it[0]) + "</a>";
          }).join("");
        }
        items.removeAttribute("hidden");
        btn.querySelector(".chev").textContent = "▾";
        btn.setAttribute("aria-expanded", "true");
      } else {
        items.setAttribute("hidden", "");
        btn.querySelector(".chev").textContent = "▸";
        btn.setAttribute("aria-expanded", "false");
      }
    });
    const menu = document.getElementById("menu");
    const scrim = document.getElementById("scrim");
    const setNav = (open) => {
      document.body.classList.toggle("nav-open", open);
      menu.setAttribute("aria-expanded", open ? "true" : "false");
      menu.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    };
    menu.addEventListener("click", () => {
      const open = !document.body.classList.contains("nav-open");
      setNav(open);
      if (open) document.body.classList.remove("search-open");
    });
    scrim.addEventListener("click", () => setNav(false));
    document.getElementById("nav").addEventListener("click", (e) => {
      if (e.target.closest("a.item")) setNav(false);
    });
    wireSearch(setNav);
    wireThemeToggle();
  }

  function findPage(id) {
    for (let i = 0; i < NAV.length; i++) {
      for (let j = 0; j < NAV[i][1].length; j++) {
        if (NAV[i][1][j][2] === id) return { id: id, title: NAV[i][1][j][0], href: NAV[i][1][j][1] };
      }
    }
    return null;
  }

  const FEATURE = {
    flows: "feature.fii_dii_flows",
    top: "feature.top_stocks",
    scorecard: "feature.scorecard",
    watchlist: "feature.watchlist_portfolio",
    alerts: "feature.alerts",
    backtest: "feature.backtest",
    growth: "feature.scanner_growth",
    quality: "feature.scanner_quality",
    dividend: "feature.scanner_dividend",
    wheel: "feature.scanner_wheel",
    vcp: "feature.scanner_vcp",
    canslim: "feature.scanner_canslim",
    box: "feature.scanner_box",
    flag: "feature.scanner_flag",
    qullamaggie: "feature.scanner_qullamaggie",
    marios: "feature.scanner_marios",
    episodic: "feature.scanner_episodic_pivot",
    gapup: "feature.scanner_gap_up",
    leaders: "feature.scanner_leaders",
    week52: "feature.scanner_52w",
    highvol: "feature.high_volume_scanner",
    buysetups: "feature.buy_setups",
    rotation: "feature.sector_rotation",
    calendar: "feature.earnings_calendar",
    heatmap: "feature.earnings_heatmap",
    cards: "feature.earnings_cards",
    putcall: "feature.put_call",
    walls: "feature.option_walls",
    analysts: "feature.analyst_ratings",
    thirteen: "feature.institutional_13f",
    aaii: "feature.aaii_sentiment",
    insiders: "feature.insider_trading",
    headlines: "feature.headline_sentiment",
    xly: "feature.xly_xlp",
    financials: "feature.financials_summary",
    tracker: "feature.earnings_tracker",
    company: "feature.company_financials",
    divfund: "feature.dividend_scanner",
    macro: "feature.macro_screener",
    secmacro: "feature.macro_screener",
    histpe: "feature.historical_pe",
    breakouts: "feature.breakouts",
    trends: "feature.trends",
    pullbacks: "feature.pullbacks",
    gainers: "feature.gainers_losers",
    breadth: "feature.breadth",
    secperf: "feature.sector_performance",
    heatmaps: "feature.heatmaps",
    updates: "feature.updates_log",
    help: "feature.help",
    chartviewer: "feature.chart_viewer",
  };
  let SETTINGS = [];
  function featureOn(key) {
    if (!key) return true;
    const row = SETTINGS.find((r) => r.setting === key);
    if (!row) return true;
    return String(row.value).toLowerCase() !== "false";
  }
  // The "What this page does" box. One plain-English card above the page,
  // outside #page so a filter redraw never wipes it. Off with feature.page_descriptions.
  function aboutHtml(about) {
    if (!about || !featureOn("feature.page_descriptions")) return "";
    // splitLines replace lines while the Technical | Fundamental split is on (feature.split_tech_fund).
    const split = about.splitLines && splitOn() && (!about.splitNeedsToggle || cvOpt("group_toggle"));
    const lines = [].concat((split ? about.splitLines : about.lines) || []).filter((t) => t);
    if (!lines.length) return "";
    const body = lines.map((t) => "<p>" + esc(t) + "</p>").join("") +
      (about.note ? '<p class="about-note">' + esc(about.note) + "</p>" : "");
    return '<section class="about" id="about" aria-label="' + esc(about.title || "What this page does") + '">' +
      '<div class="about-title">' + esc(about.title || "What this page does") + "</div>" + body + "</section>";
  }
  function placeAbout(about) {
    const old = document.getElementById("about");
    if (old) old.remove();
    const html = aboutHtml(about);
    const page = document.getElementById("page");
    if (html && page) page.insertAdjacentHTML("beforebegin", html);
  }
  function markReady(value) {
    requestAnimationFrame(() => requestAnimationFrame(() => { document.body.dataset.ready = value; }));
  }

  async function boot() {
    const id = document.body.dataset.page;
    const meta = findPage(id);
    const spec = (window.DESK_PAGES || {})[id];
    if (!meta || !spec) {
      document.body.dataset.ready = "error";
      return;
    }
    try {
      const names = ["updates_log.csv", "market_today.csv", "settings.csv"].concat(spec.files || []);
      const unique = Array.from(new Set(names));
      const loaded = {};
      await Promise.all(unique.map(async (n) => { loaded[n] = await loadCsv(n); }));
      await Promise.all((spec.optional || []).filter((n) => !loaded[n]).map(async (n) => {
        try { loaded[n] = await loadCsv(n); } catch (err) { loaded[n] = []; }
      }));
      SETTINGS = loaded["settings.csv"] || [];
      applyTheme();
      renderShell(meta);
      const mt = loaded["market_today.csv"];
      const stamp = (mt && mt[0] && mt[0].updated_pt) || latestChecked(loaded["updates_log.csv"]);
      document.getElementById("updated").textContent = formatUpdated(stamp);
      if (FEATURE[id] && !featureOn(FEATURE[id])) {
        document.getElementById("page").innerHTML = '<div class="panel pad m2" style="font-size:12px">Turned off in Settings</div>';
        markReady("1");
        return;
      }
      placeAbout(spec.about);
      if (featureOn("feature.chart_viewer")) placeViewerLink(id);
      spec.render({ page: document.getElementById("page"), files: loaded, settings: SETTINGS });
      markReady("1");
    } catch (err) {
      console.error(err);
      if (!document.getElementById("nav")) renderShell(meta || { id: id, title: "Nick's India Stock Desk" });
      const host = document.getElementById("page");
      if (host) host.innerHTML = '<div class="banner miss">This page could not read its data file.</div>';
      document.body.dataset.ready = "error";
    }
  }

  window.Desk = {
    UP: UP, DN: DN, AM: AM, AC: AC, MU: MU, TX: TX, SPD: SPD,
    num: num, isBlank: isBlank, esc: esc, na: na, fmt: fmt, compact: compact,
    realRows: realRows, alertDataRows: alertDataRows, quietMessage: quietMessage, showQuiet: showQuiet,
    banner: banner, noteOf: noteOf, statusOf: statusOf, drawPriceChart: drawPriceChart,
    fillCompanyLine: fillCompanyLine, companyLineHtml: companyLineHtml,
    scoreHtml: scoreHtml, scoreFill: scoreFill, tickerHtml: tickerHtml, etfHtml: etfHtml, pctHtml: pctHtml, moneyHtml: moneyHtml,
    verdictHtml: verdictHtml, trendHtml: trendHtml, pointsHtml: pointsHtml, zoneHtml: zoneHtml, signedPts: signedPts,
    drawTable: drawTable, uniq: uniq, indexTokens: indexTokens,
    selectedMulti: selectedMulti, fieldVal: fieldVal,
    multiHtml: multiHtml, selectHtml: selectHtml, searchHtml: searchHtml, rangeHtml: rangeHtml,
    pairHtml: pairHtml, dateHtml: dateHtml, feedHtml: feedHtml, placeFeed: placeFeed,
    featureOn: featureOn, aboutHtml: aboutHtml, marketWord: marketWord, marketColor: marketColor, monthLabel: monthLabel, dateTicks: dateTicks, ptsColor: ptsColor,
    wireFilters: wireFilters, matchMulti: matchMulti, matchContains: matchContains,
    matchText: matchText, matchMin: matchMin,
    destroyCharts: destroyCharts, lineChart: lineChart, barChart: barChart, comboChart: comboChart, makeChart: makeChart,
    lastNDays: lastNDays, seriesNum: seriesNum, retColor: retColor, band: band,
    renderChartViewer: renderChartViewer, chartViewerFiles: CV_FILES, setViewerStart: setViewerStart,
    splitOn: splitOn, groupOf: groupOf,
    tc: tc, theme: () => THEME, maColor: maColor,
    boot: boot,
  };
})();
