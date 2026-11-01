/* Per-page layouts. Each page names the CSVs it reads. prices.csv is only on the scorecard. */
(function () {
  const D = window.Desk;
  const T = (key, label, kind, extra) => Object.assign({ key: key, label: label, kind: kind || "text" }, extra || {});
  const TK = T("ticker", "Ticker", "ticker");
  const CO = T("company", "Company", "text");
  const SE = T("sector", "Sector", "text");
  const SC = T("score", "Score", "score");
  const VE = T("verdict", "Verdict", "verdict");
  const PR = T("price", "Price", "num", { dec: 2 });

  function card(label, valueHtml, subHtml, bg) {
    return '<div class="card"' + (bg ? ' style="background:' + bg + '"' : "") + "><div class=\"l\">" +
      D.esc(label) + '</div><div class="v">' + valueHtml + "</div>" +
      (subHtml ? '<div class="s">' + subHtml + "</div>" : "") + "</div>";
  }
  function trendCard(name, word, price, day) {
    const label = D.marketWord(word) || (D.isBlank(word) ? "Not on file" : String(word));
    const color = D.marketColor(D.marketWord(word));
    const px = D.num(price);
    const move = D.num(day);
    const moveHtml = move == null ? "" : ' <span style="color:' + D.retColor(move) + '">' + (move < 0 ? "▼" : "▲") + D.fmt(Math.abs(move), 2) + "%</span>";
    const pxHtml = px == null ? D.na() : D.esc(D.fmt(px, 2));
    return '<div class="mktcard"><div class="name">' + D.esc(name) + '</div><div class="trend" style="color:' + color + '">' +
      D.esc(label) + '</div><div class="px">' + pxHtml + moveHtml + "</div></div>";
  }
  function trendStrip(mt) {
    const row = mt || {};
    const items = [
      trendCard("Nifty 50", row.nifty_trend, row.spy_price, row.spy_day_pct),
      trendCard("SENSEX", row.sensex_trend, row.sensex_price, row.sensex_day_pct),
      trendCard("Bank Nifty", row.bank_trend, row.bank_price, row.qqq_day_pct),
    ];
    if (!D.featureOn("feature.sensex")) items.splice(1, 1);
    return '<div class="mktstrip">' + items.join("") + "</div>";
  }
  function avg(rows, key) {
    const xs = [];
    rows.forEach((r) => { const n = D.num(r[key]); if (n != null) xs.push(n); });
    if (!xs.length) return null;
    return xs.reduce((a, b) => a + b, 0) / xs.length;
  }
  function median(rows, key) {
    const xs = [];
    rows.forEach((r) => { const n = D.num(r[key]); if (n != null) xs.push(n); });
    if (!xs.length) return null;
    xs.sort((a, b) => a - b);
    const m = Math.floor(xs.length / 2);
    return xs.length % 2 ? xs[m] : (xs[m - 1] + xs[m]) / 2;
  }
  function ntext(n, d) {
    if (n == null || !Number.isFinite(n)) return D.na();
    return D.esc(D.fmt(n, d));
  }
  function countWhere(rows, fn) { return rows.filter(fn).length; }
  function shift(iso, days) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }
  function maxDate(rows, key) {
    let m = "";
    rows.forEach((r) => { if (r[key] && r[key] > m) m = r[key]; });
    return m || new Date().toISOString().slice(0, 10);
  }
  function chartHost(title, sub) {
    return '<div class="panel pad"><div class="ptitle">' + D.esc(title) + "</div>" +
      (sub ? '<div class="psub">' + sub + "</div>" : "") +
      '<div class="chart-box tall"><canvas></canvas></div></div>';
  }
  function paintLine(root, labels, series, y) {
    const canvas = root.querySelector("canvas");
    D.lineChart(canvas, labels, series, { y: y || {} });
  }

  const RET = { color: true };
  function standardFilters(box, all, opts) {
    opts = opts || {};
    const bag = {};
    if (opts.passes) bag.passes = D.selectHtml("passes", "Passes screen", ["yes", "no"], opts.passes);
    if (opts.status) {
      const statuses = D.uniq(all, "status");
      const picked = (opts.statusDefault || []).filter((s) => statuses.indexOf(s) >= 0);
      bag.status = D.multiHtml("status", "Status", statuses, picked.length ? picked : null);
    }
    if (opts.single) opts.single.forEach((s) => { bag[s.key] = D.selectHtml(s.key, s.label, D.uniq(all, s.key), s.value || ""); });
    if (opts.sector) bag.sector = D.multiHtml("sector", "Sector", D.uniq(all, "sector"));
    if (opts.verdict) bag.verdict = D.multiHtml("verdict", "Verdict", D.uniq(all, "verdict"));
    if (opts.confidence) bag.confidence = D.multiHtml("confidence", "Confidence", D.uniq(all, "confidence"));
    if (opts.index) bag.index = D.multiHtml("index", "Index", D.indexTokens(all));
    const exchanges = D.uniq(all, "exchange").filter(Boolean);
    if (exchanges.length) bag.exchange = D.multiHtml("exchange", "Exchange", exchanges);
    if (opts.liquid) {
      bag.liquid = D.selectHtml("liquid", "Liquid", [{ value: "yes", label: "Yes" }, { value: "no", label: "No" }], opts.liquid === true ? "yes" : String(opts.liquid));
    }
    if (opts.trend) bag.timing = D.multiHtml("timing", "Trend", D.uniq(all, "timing"));
    if (opts.ticker) bag.ticker = D.searchHtml("ticker", "Ticker", "tick-list-" + (opts.list || "a"), D.uniq(all, "ticker"));
    const order = opts.order || ["ticker", "passes", "status", "verdict", "sector", "confidence", "index", "exchange", "liquid", "timing"];
    const parts = [];
    order.forEach((k) => { if (bag[k]) parts.push(bag[k]); });
    Object.keys(bag).forEach((k) => { if (order.indexOf(k) < 0) parts.push(bag[k]); });
    if (opts.extra) parts.push(opts.extra);
    box.innerHTML = parts.join("");
  }

  function readCommon(box, row) {
    const passes = D.fieldVal(box, "passes");
    const status = D.selectedMulti(box, "status");
    const sector = D.selectedMulti(box, "sector");
    const verdict = D.selectedMulti(box, "verdict");
    const confidence = D.selectedMulti(box, "confidence");
    const index = D.selectedMulti(box, "index");
    const exchange = D.selectedMulti(box, "exchange");
    const timing = D.selectedMulti(box, "timing");
    const ticker = (D.fieldVal(box, "ticker") || "").trim();
    if (passes && row.passes !== passes) return false;
    if (!D.matchMulti(row, "status", status)) return false;
    if (!D.matchMulti(row, "sector", sector)) return false;
    if (!D.matchMulti(row, "verdict", verdict)) return false;
    if (!D.matchMulti(row, "confidence", confidence)) return false;
    if (!D.matchContains(row, "index_membership", index)) return false;
    if (!D.matchMulti(row, "exchange", exchange)) return false;
    if (!D.matchMulti(row, "timing", timing)) return false;
    if (!D.matchText(row, "ticker", ticker)) return false;
    const nodes = box.querySelectorAll("select[data-filter]");
    for (let i = 0; i < nodes.length; i++) {
      const key = nodes[i].getAttribute("data-filter");
      const val = nodes[i].value;
      if (!val || key === "passes") continue;
      if (!Object.prototype.hasOwnProperty.call(row, key)) continue;
      if (String(row[key] == null ? "" : row[key]) !== val) return false;
    }
    return true;
  }

  function hook(box, state, draw) {
    D.wireFilters(box, () => { state.page = 0; draw(); });
  }

  function passesPage(cfg) {
    return {
      files: [cfg.file],
      render(ctx) {
        const raw = ctx.files[cfg.file];
        const all = D.realRows(raw);
        const notice = cfg.notice ? cfg.notice(all, raw) : "";
        const cap = cfg.caption ? '<p class="cap">' + D.esc(cfg.caption) + "</p>" : "";
        ctx.page.innerHTML = (cfg.noticeAbove ? "" : (notice || "")) + '<div class="ctrls" id="ctrls"></div>' +
          (cfg.noticeAbove ? '<div id="notice"></div>' : "") +
          (cfg.captionAbove ? cap : "") +
          '<div class="cards" id="cards"></div><div class="panel" id="tbl"></div>' +
          (cfg.captionAbove ? "" : cap);
        if (cfg.noticeAbove) document.getElementById("notice").innerHTML = notice || "";
        const box = document.getElementById("ctrls");
        standardFilters(box, all, cfg.filters);
        D.placeFeed(box, raw);
        document.getElementById("cards").innerHTML = cfg.cards(all);
        const state = { sort: cfg.sort || "score", dir: cfg.dir || "desc", sort2: cfg.sort2 || "", dir2: cfg.dir2 || "desc", page: 0 };
        const draw = () => {
          const rows = all.filter((r) => readCommon(box, r) && (!cfg.match || cfg.match(r, box)));
          D.drawTable(document.getElementById("tbl"), {
            rows: rows, columns: cfg.columns, state: state, pageSize: cfg.pageSize || 25, foot: cfg.foot, title: cfg.tableTitle, sub: cfg.tableSub,
          });
        };
        hook(box, state, draw);
        draw();
      },
    };
  }

  function patternPage(cfg) {
    return {
      files: [cfg.file],
      render(ctx) {
        const raw = ctx.files[cfg.file];
        const all = D.realRows(raw);
        const chartsOn = D.featureOn("feature.row_charts");
        ctx.page.innerHTML = (cfg.guide ? cfg.guide() : "") +
          (cfg.strip ? '<div id="strip"></div>' : "") +
          '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div>' +
          '<div class="panel" id="tbl"></div><div id="detail"></div><p class="cap"></p>';
        if (cfg.strip) document.getElementById("strip").innerHTML = cfg.strip(all, ctx);
        ctx.page.querySelector(".cap").textContent = cfg.caption || D.noteOf(raw);
        const box = document.getElementById("ctrls");
        standardFilters(box, all, cfg.filters);
        if (cfg.chips) box.insertAdjacentHTML("afterbegin", cfg.chips(all, ctx));
        D.placeFeed(box, raw);
        document.getElementById("cards").innerHTML = cfg.cards(all);
        const state = { sort: cfg.sort || "status", dir: cfg.dir || "asc", sort2: cfg.sort2 || "strength", dir2: "desc", page: 0 };
        let pick = null;
        const drawDetail = (row, rows) => {
          const host = document.getElementById("detail");
          D.destroyCharts();
          if (!row && !(cfg.detailRows)) { host.innerHTML = ""; return; }
          const showPrice = cfg.price && !chartsOn;
          host.innerHTML = (showPrice ? priceShell(cfg.priceSub || "Daily bars for the selected name") : "") + (cfg.detail ? cfg.detail(row, rows || []) : "");
          if (showPrice && row) D.drawPriceChart(host.querySelector("[data-px-panel]"), { ticker: row.ticker, lines: cfg.price(row) });
        };
        const strongest = (rows) => rows.slice().sort((a, b) => (D.num(b.strength) || 0) - (D.num(a.strength) || 0))[0] || null;
        const draw = () => {
          const rows = all.filter((r) => readCommon(box, r) && (!cfg.match || cfg.match(r, box)));
          if (pick && !rows.some((r) => r.ticker === pick)) pick = null;
          const selected = rows.find((r) => r.ticker === pick) || strongest(rows);
          pick = selected ? selected.ticker : null;
          D.setViewerStart(pick);
          D.drawTable(document.getElementById("tbl"), {
            rows: rows, columns: cfg.columns, state: state, pageSize: 12, pick: pick,
            lines: chartsOn ? (cfg.price || setupLines) : null,
            priceSub: cfg.priceSub || "Buy point, stop, and target when the scan has them",
            empty: "No names match. Open Status and tick WATCHING to see names still forming.",
            onPick: (row) => { pick = row.ticker; draw(); },
          });
          drawDetail(selected, rows);
        };
        hook(box, state, draw);
        draw();
      },
    };
  }

  function priceShell(sub) {
    return '<div class="panel pad" data-px-panel><div class="rowhead wrap"><div><div class="ptitle">Price</div><div class="psub">' +
      D.esc(sub || "Daily bars") + '</div></div><div class="pxtools" data-px-tools></div></div><div class="pxmas" data-px-mas></div><div class="chart-box pxchart"><div class="px-host" data-px-host><div class="px-legend" data-px-legend></div></div></div><p class="cap" data-px-cap></p></div>';
  }
  function setupLines(row) {
    const lines = [];
    if (!row) return lines;
    if (D.num(row.pivot) != null) lines.push({ value: D.num(row.pivot), color: "#F59E0B", label: "Buy point " + D.fmt(row.pivot, 2) });
    if (D.num(row.stop) != null) lines.push({ value: D.num(row.stop), color: "#EF4444", label: "Stop " + D.fmt(row.stop, 2) });
    if (D.num(row.target) != null) lines.push({ value: D.num(row.target), color: "#22C55E", label: "Target " + D.fmt(row.target, 2) });
    return lines;
  }
  function reasonBlock(row, extraCols) {
    let rules = "";
    if (extraCols) {
      rules = '<div class="panel" style="margin-top:12px"><div class="pad"><div class="ptitle">' + D.esc(row.ticker) +
        " rules</div></div><div class=\"scroll\"><table><tr>" +
        extraCols.map((c) => "<th>" + D.esc(c.label) + "</th>").join("") + "</tr><tr>" +
        extraCols.map((c) => "<td class=\"c wrap\">" + (c.kind === "pass" ? (D.isBlank(row[c.key]) ? D.na() : (String(row[c.key]).toUpperCase() === "PASS" ? '<span class="pill" style="color:#22C55E">PASS</span>' : String(row[c.key]).toUpperCase() === "FAIL" ? '<span class="pill" style="color:#EF4444">FAIL</span>' : D.esc(row[c.key]))) : (D.isBlank(row[c.key]) ? D.na() : D.esc(row[c.key]))) + "</td>").join("") +
        "</tr></table></div></div>";
    }
    return '<div class="panel pad" style="margin-top:12px"><div class="ptitle">' + D.tickerHtml(row.ticker) +
      ' · why this name</div><p class="cap" style="margin-top:8px">' + D.esc(row.reason || "") + "</p></div>" + rules;
  }

  const readyDefault = ["READY", "BROKEN OUT today"];

  function panelOff(key) {
    return !D.featureOn(key);
  }
  function offBox() {
    return '<div class="panel pad m2" style="font-size:12px">Turned off in Settings</div>';
  }
  // High volume: stocks trading far above their own 50-day average volume.
  const HV_COLS = [
    TK,
    T("company", "Company", "codesc", { width: "240px" }),
    T("volume", "Volume today", "compact", { align: "num" }),
    T("avg_volume_50d", "50-day avg volume", "compact", { align: "num", hide: "md" }),
    T("volume_ratio", "Volume ratio", "ratiox"),
    T("day_pct", "Price change", "pct", { dec: 2, color: true }),
    T("close", "Close", "num", { dec: 2 }),
    T("above_sma50", "vs 50-day", "abovema"),
    T("above_sma200", "vs 200-day", "abovema"),
    T("day_type", "Day", "updown"),
  ];
  function hvColumns(all) {
    const cols = HV_COLS.slice();
    if (all.some((r) => D.num(r.delivery_pct) != null)) cols.push(T("delivery_pct", "Delivery %", "pct", { dec: 1 }));
    return cols;
  }
  function hvMatch(r, minx, side, exch) {
    const ratio = D.num(r.volume_ratio);
    if (ratio == null || ratio < minx) return false;
    if (side && String(r.day_type || "") !== side) return false;
    if (exch) {
      const e = String(r.exchange || "");
      if (e !== exch && e !== "Both") return false;
    }
    return true;
  }
  function hvDetail(r) {
    const ratio = D.num(r.volume_ratio);
    const ratioText = ratio == null ? "More shares than usual" : (ratio >= 10 ? D.fmt(ratio, 0) : D.fmt(ratio, 1)) + " times its normal volume";
    const side = String(r.day_type || "");
    const meaning = side === "Up" ? " on an up day. That usually means buyers were in control." :
      side === "Down" ? " on a down day. That usually means sellers were in control." : ".";
    const traded = D.num(r.traded_cr);
    const tradedText = traded == null ? "" : " About Rs " + D.fmt(traded, traded >= 100 ? 0 : 1) + " crore changed hands.";
    const split = String(r.split_check || "") === "yes" ? " The price jumped more than 35% in one day recently. That is usually a split or bonus, so the ratio may be too high." : "";
    return '<p class="whytext">' + D.esc(ratioText + meaning + tradedText + split) + "</p>";
  }
  // The one-line company description, when company_lines.csv is on the desk.
  function hvAddLines(rows, files) {
    if (!D.featureOn("feature.company_line")) return rows;
    const lines = new Map();
    (files["company_lines.csv"] || []).forEach((r) => {
      if (r.ticker && r.line) lines.set(String(r.ticker).toUpperCase(), r.line);
    });
    if (!lines.size) return rows;
    return rows.map((r) => {
      const line = lines.get(String(r.ticker || "").toUpperCase());
      return line && D.isBlank(r.description) ? Object.assign({}, r, { description: line }) : r;
    });
  }
  function renderHighVolume(ctx) {
    const raw = ctx.files["high_volume.csv"] || [];
    const all = hvAddLines(D.realRows(raw).filter((r) => !D.isBlank(r.ticker)), ctx.files);
    const day = (all[0] && all[0].date) || "";
    const when = day ? " in the " + D.esc(day) + " session" : "";
    ctx.page.innerHTML =
      '<p class="cap">Stocks that traded far more shares than usual' + when + '. Volume ratio is today\'s volume divided by the average of the last 50 sessions, so 3.2x means 3.2 times a normal day. ' +
      'Heavy volume on an up day usually means buying. On a down day it usually means selling. Only stocks with a close over Rs 20 and at least Rs 1 crore traded are listed. Tap a row to see the chart. Research only.</p>' +
      '<div class="ctrls" id="ctrls"></div><div class="cards four" id="cards"></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML =
      D.selectHtml("minx", "Volume at least", [
        { value: "1.5", label: "1.5x normal" }, { value: "2", label: "2x normal" },
        { value: "3", label: "3x normal" }, { value: "5", label: "5x normal" },
      ], "2", { all: false }) +
      D.selectHtml("side", "Day", [{ value: "Up", label: "Up only (buying)" }, { value: "Down", label: "Down only (selling)" }], "") +
      D.selectHtml("exch", "Exchange", [{ value: "NSE", label: "NSE" }, { value: "BSE", label: "BSE" }], "") +
      D.searchHtml("ticker", "Ticker", "tick-list-hv", D.uniq(all, "ticker"));
    const cols = hvColumns(all);
    const state = { sort: "volume_ratio", dir: "desc", page: 0 };
    const emptyAll = all.length ? "" : (D.noteOf(raw) || "No stocks had unusually high volume in the latest session.");
    const draw = () => {
      const minx = Number(D.fieldVal(box, "minx") || "2");
      const side = D.fieldVal(box, "side") || "";
      const exch = D.fieldVal(box, "exch") || "";
      const ticker = (D.fieldVal(box, "ticker") || "").trim();
      const rows = all.filter((r) => hvMatch(r, minx, side, exch) && D.matchText(r, "ticker", ticker));
      const ups = countWhere(rows, (r) => r.day_type === "Up");
      const downs = countWhere(rows, (r) => r.day_type === "Down");
      const top = rows.slice().sort((a, b) => (D.num(b.volume_ratio) || 0) - (D.num(a.volume_ratio) || 0))[0];
      document.getElementById("cards").innerHTML =
        card("Stocks listed", D.esc(String(rows.length)), "at " + D.esc(String(minx)) + "x or more") +
        card("Up days", '<span style="color:#22C55E">' + D.esc(String(ups)) + "</span>", "heavy buying") +
        card("Down days", '<span style="color:#EF4444">' + D.esc(String(downs)) + "</span>", "heavy selling") +
        card("Biggest jump", top ? D.esc(top.ticker) : D.na(), top ? D.esc((D.num(top.volume_ratio) >= 10 ? D.fmt(top.volume_ratio, 0) : D.fmt(top.volume_ratio, 1)) + "x normal volume") : "");
      D.drawTable(document.getElementById("tbl"), {
        rows: rows, columns: cols, state: state, pageSize: 25,
        detail: hvDetail,
        priceSub: "Daily candles in rupees. The volume bars show the heavy day.",
        empty: emptyAll || "No stocks match these filters today. Try 1.5x, or set Day and Exchange to All.",
      });
    };
    hook(box, state, draw);
    draw();
  }

  function hvTodayPanel(files) {
    if (panelOff("feature.high_volume_scanner")) return "";
    return '<div class="panel today-hv" id="hvtop"></div>';
  }
  function paintHvToday(files) {
    const host = document.getElementById("hvtop");
    if (!host) return;
    const raw = files["high_volume.csv"] || [];
    const rows = D.realRows(raw).filter((r) => !D.isBlank(r.ticker) && hvMatch(r, 2, "", ""));
    const head = '<div class="pad" style="padding-bottom:0"><div class="rowhead"><div><div class="ptitle">High volume today</div>' +
      '<div class="psub">Stocks at 2x or more of their normal volume. Up day means buying, down day means selling.</div></div>' +
      '<a class="more" href="high-volume.html">All high volume ›</a></div></div>';
    if (!rows.length) {
      host.innerHTML = head + '<div class="empty">' + D.esc(raw.length ? "No stocks had unusually high volume in the latest session." : "The high volume list is not ready yet.") + "</div>";
      return;
    }
    host.innerHTML = head + '<div id="hvtbl"></div>';
    D.drawTable(document.getElementById("hvtbl"), {
      rows: rows, columns: [TK, T("volume_ratio", "Ratio", "ratiox"),
        T("day_pct", "Change", "pct", { dec: 2, color: true }), T("day_type", "Day", "updown", { short: true })],
      state: { sort: "volume_ratio", dir: "desc", page: 0 }, pageSize: 5, foot: false, detail: hvDetail,
    });
  }

  // Gap Up: stocks that opened above the day before's high on big volume and have held the
  // gap-day low since. Rows come from gap_up.py. Numbers live in the gap_up block of config.json.
  const GAP_COLS = [
    TK,
    T("company", "Company", "text", { ellipsis: true, width: "200px" }),
    T("status", "Status", "setup"),
    T("gap_date", "Gap day", "shortdate"),
    T("days_ago", "Days ago", "num", { dec: 0 }),
    T("gap_pct", "Gap %", "pct", { dec: 2, color: true }),
    T("volume_ratio", "Volume vs 50-day", "ratiox"),
    T("hold_level", "Hold level (gap-day low)", "num", { dec: 2 }),
    T("price", "Last close", "num", { dec: 2 }),
    T("above_hold_pct", "Above hold level", "pct", { dec: 1, color: true }),
    T("close_pos_pct", "Close in gap-day range", "rangepos"),
    T("above_sma50", "vs 50-day", "abovema"),
    T("above_sma200", "vs 200-day", "abovema"),
    T("also_in", "Also on", "text", { hide: "md" }),
  ];
  function gapDay(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return String(iso || "");
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return months[Number(m[2]) - 1] + " " + Number(m[3]);
  }
  function gapDetail(r) {
    const parts = [];
    const g = D.num(r.gap_pct);
    parts.push("On " + gapDay(r.gap_date) + " it opened at ₹" + D.fmt(r.gap_open, 2) + ", above the day before's high of ₹" + D.fmt(r.prev_high, 2) +
      (g == null ? "." : " (a " + D.fmt(g, 2) + "% gap)."));
    if (D.num(r.volume_ratio) != null) parts.push("Volume was " + D.fmt(r.volume_ratio, 1) + " times its 50-day average.");
    parts.push("The gap-day low of ₹" + D.fmt(r.hold_level, 2) + " is the hold level. No close since has been below it.");
    if (D.num(r.above_hold_pct) != null) parts.push("The last close is " + D.fmt(r.above_hold_pct, 1) + "% above it.");
    if (!D.isBlank(r.also_in)) parts.push("Also on: " + r.also_in + ".");
    return '<p class="whytext">' + D.esc(parts.join(" ")) + "</p>";
  }
  function gapLines(r) {
    const lines = [];
    if (!r) return lines;
    if (D.num(r.hold_level) != null) lines.push({ value: D.num(r.hold_level), color: "#EF4444", label: "Hold level " + D.fmt(r.hold_level, 2) });
    if (D.num(r.prev_high) != null) lines.push({ value: D.num(r.prev_high), color: "#F59E0B", label: "High before the gap " + D.fmt(r.prev_high, 2) });
    return lines;
  }
  function renderGapUp(ctx) {
    const raw = ctx.files["scanner_gap_up.csv"] || [];
    const all = D.realRows(raw).filter((r) => !D.isBlank(r.ticker) && ["GAP UP today", "GAP HOLDING"].indexOf(String(r.status || "")) >= 0);
    const asOf = (all[0] && all[0].price_as_of) || "";
    ctx.page.innerHTML =
      '<p class="cap">Stocks that opened at least 3% above the day before\'s high on big volume in the last 21 trading days, and have not closed below the gap-day low since. ' +
      "Newest gaps first, then the biggest." + (asOf ? " Prices to the " + D.esc(gapDay(asOf)) + " close." : "") + " Tap a row to see the chart. Research only.</p>" +
      '<div class="ctrls" id="ctrls"></div><div class="cards four" id="cards"></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML =
      D.selectHtml("age", "Gap day", [
        { value: "0", label: "Latest day" }, { value: "4", label: "Last 5 days" }, { value: "9", label: "Last 10 days" },
      ], "") +
      D.selectHtml("trend", "Trend", [
        { value: "50", label: "Above 50-day" }, { value: "200", label: "Above 200-day" }, { value: "both", label: "Above both" },
      ], "") +
      D.searchHtml("ticker", "Ticker", "tick-list-gap", D.uniq(all, "ticker"));
    const state = { sort: "gap_date", dir: "desc", sort2: "gap_pct", dir2: "desc", page: 0 };
    const emptyAll = all.length ? "" : (D.noteOf(raw) || "No stock has a gap up that is still holding.");
    const draw = () => {
      const age = D.fieldVal(box, "age");
      const trend = D.fieldVal(box, "trend") || "";
      const ticker = (D.fieldVal(box, "ticker") || "").trim();
      const rows = all.filter((r) => {
        if (age !== "" && !((D.num(r.days_ago) ?? 99) <= Number(age))) return false;
        if ((trend === "50" || trend === "both") && r.above_sma50 !== "yes") return false;
        if ((trend === "200" || trend === "both") && r.above_sma200 !== "yes") return false;
        return D.matchText(r, "ticker", ticker);
      });
      const today = countWhere(rows, (r) => D.num(r.days_ago) === 0);
      const both = countWhere(rows, (r) => r.above_sma50 === "yes" && r.above_sma200 === "yes");
      const top = rows.slice().sort((a, b) => (D.num(b.gap_pct) || 0) - (D.num(a.gap_pct) || 0))[0];
      document.getElementById("cards").innerHTML =
        card("Stocks holding", D.esc(String(rows.length)), "gap still holding") +
        card("Gapped on the latest day", '<span style="color:#22C55E">' + D.esc(String(today)) + "</span>", asOf ? D.esc(gapDay(asOf)) : "") +
        card("Above 50 and 200-day", D.esc(String(both)), "in an uptrend") +
        card("Biggest gap", top ? D.esc(top.ticker) : D.na(), top ? D.esc(D.fmt(top.gap_pct, 1) + "% on " + gapDay(top.gap_date)) : "");
      D.drawTable(document.getElementById("tbl"), {
        rows: rows, columns: GAP_COLS, state: state, pageSize: 25,
        detail: gapDetail, lines: gapLines,
        priceSub: "Daily candles in rupees. Red is the hold level (gap-day low). Orange is the high of the day before the gap.",
        empty: emptyAll || "No stocks match these filters. Set Gap day and Trend to All.",
      });
      if (D.setViewerStart) D.setViewerStart((rows[0] || {}).ticker || "");
    };
    hook(box, state, draw);
    draw();
  }

  function renderToday(ctx) {
    const mt = (ctx.files["market_today.csv"] || [])[0] || {};
    const breadth = D.lastNDays(D.realRows(ctx.files["breadth_history.csv"]), "date", 182);
    const sectors = D.realRows(ctx.files["sectors.csv"]);
    const alertRaw = ctx.files["alerts.csv"] || [];
    const alerts = D.alertDataRows(alertRaw);
    const day = D.num(mt.spy_day_pct);
    const dayHtml = day == null ? D.na() : '<span style="color:' + D.retColor(day) + '">' + (day < 0 ? "▼ " : "▲ ") + D.fmt(Math.abs(day), 2) + "% today</span>";
    const b = D.num(mt.breadth_sma50);
    const w = D.num(mt.breadth_sma50_week_ago);
    const delta = b != null && w != null ? b - w : null;
    const deltaHtml = delta == null ? D.na() : '<span style="color:' + D.retColor(delta) + '">' + (delta >= 0 ? "+" : "") + D.fmt(delta, 1) + " pts vs week ago</span>";
    const zone = mt.put_call_zone || "";
    const y10 = D.num(mt.fred_dgs10);
    const nStocks = mt.universe_n || "n/a";
    const chips = [
      ["20-day", mt.breadth_sma20, "#7C9CFF"],
      ["50-day", mt.breadth_sma50, "#E6EBF5"],
      ["100-day", mt.breadth_sma100, "#F59E0B"],
      ["200-day", mt.breadth_sma200, "#8B96AD"],
    ].map((c) => '<span class="chip"><i class="dot" style="background:' + c[2] + '"></i>' + c[0] + " <b>" +
      (D.num(c[1]) == null ? D.na() : D.fmt(c[1], 1) + "%") + "</b></span>").join("");
    const adv = D.isBlank(mt.advancers) ? D.na() : '<span style="color:#22C55E">' + D.esc(mt.advancers) + "</span>";
    const dec = D.isBlank(mt.decliners) ? D.na() : '<span style="color:#EF4444">' + D.esc(mt.decliners) + "</span>";
    const pc = D.num(mt.put_call);
    const pc5 = D.num(mt.put_call_ma5);
    const covered = D.isBlank(mt.listed_n) ? nStocks : mt.listed_n;
    const liquidNote = D.isBlank(mt.liquid_n) ? "names with a score" : D.esc(String(mt.liquid_n)) + " pass the liquidity filter";
    ctx.page.innerHTML =
      flowStrip(ctx.files) +
      trendStrip(mt) +
      '<div class="cards seven">' +
      card("Nifty 50", D.num(mt.spy_price) == null ? D.na() : D.esc(D.fmt(mt.spy_price, 2)), "day move " + (day == null ? D.na() : '<span style="color:' + D.retColor(day) + '">' + (day < 0 ? "▼" : "▲") + D.fmt(Math.abs(day), 2) + "%</span>")) +
      card("% above 50-day", b == null ? D.na() : D.esc(D.fmt(b, 1) + "%"), deltaHtml) +
      card("Advancers / decliners", adv + '<span style="color:#5B6680"> / </span>' + dec, "of " + D.esc(nStocks) + " stocks") +
      card("New 52-week highs", D.isBlank(mt.highs_52w) ? D.na() : D.esc(mt.highs_52w), (D.isBlank(mt.lows_52w) ? D.na() : D.esc(mt.lows_52w)) + " new lows") +
      card("Put/call mood", D.isBlank(zone) ? D.na() : D.zoneHtml(zone),
        (pc == null ? D.na() : D.fmt(pc, 2)) + " today · 5-day " + (pc5 == null ? D.na() : D.fmt(pc5, 2))) +
      card("India VIX", D.num(mt.vix) == null ? D.na() : D.esc(D.fmt(mt.vix, 2)), "fear gauge") +
      card("India 10Y", y10 == null ? D.na() : D.esc(D.fmt(y10, 2) + "%"), D.num(mt.inr_usd) == null ? "Rupee per dollar " + D.na() : "Rupee per dollar " + D.fmt(D.num(mt.inr_usd), 2)) +
      card("Stocks covered", D.esc(String(covered)), liquidNote) +
      "</div>" +
      '<div class="split today-top">' +
      (panelOff("feature.breadth") ? offBox() :
        '<div class="panel pad"><div class="rowhead stack"><div><div class="ptitle">Market breadth</div><div class="psub">% of the ' + D.esc(nStocks) + ' desk stocks above each average, 6 months</div></div><div class="chips nowrap">' + chips + '</div></div><div class="chart-box"><canvas id="br"></canvas></div><div class="psub note">Gaps = days with no breadth data (shown as breaks, not 0)</div></div>') +
      (panelOff("feature.top_sectors") ? offBox() :
        '<div class="panel pad"><div class="ptitle">Sectors today</div><div class="psub">Day % change, Nifty sector indexes</div><div class="chart-box"><canvas id="sec"></canvas></div></div>') +
      "</div>" +
      '<div class="split today-bot">' +
      (panelOff("feature.top_sectors") ? offBox() : '<div class="panel" id="top5"></div>') +
      (panelOff("feature.alerts") ? offBox() : '<div class="panel"><div class="pad" style="padding-bottom:0"><div class="rowhead"><div><div class="ptitle">Latest alerts</div><div class="psub">Changes since the previous run. Nothing is emailed or sent to a phone.</div></div><a class="more" href="alerts.html">All alerts ›</a></div></div><div id="alerts"></div></div>') +
      "</div>" + hvTodayPanel(ctx.files);
    paintHvToday(ctx.files);
    if (!panelOff("feature.breadth")) {
      D.lineChart(document.getElementById("br"), breadth.map((r) => r.date), [
        { label: "20-day", data: D.seriesNum(breadth, "pct_above_sma20"), color: "#7C9CFF" },
        { label: "50-day", data: D.seriesNum(breadth, "pct_above_sma50"), color: "#E6EBF5" },
        { label: "100-day", data: D.seriesNum(breadth, "pct_above_sma100"), color: "#F59E0B" },
        { label: "200-day", data: D.seriesNum(breadth, "pct_above_sma200"), color: "#8B96AD" },
      ], { y: { min: 0, max: 100 }, legend: false });
    }
    if (!panelOff("feature.top_sectors")) {
      const eleven = sectors.filter((r) => D.SPD[r.ticker]).slice().sort((a, b) => (D.num(b.day_pct) || -999) - (D.num(a.day_pct) || -999));
      D.barChart(document.getElementById("sec"), eleven.map((r) => D.SPD[r.ticker]), eleven.map((r) => D.num(r.day_pct)),
        eleven.map((r) => (D.num(r.day_pct) || 0) >= 0 ? "#1F9D55" : "#D14343"),
        { horizontal: true, labels: true, dec: 1, suffix: "%",
          x: { ticks: { color: "#5B6680", callback: (v) => { const n = Number(v); const sign = n > 0 ? "+" : n < 0 ? "−" : ""; return sign + Math.abs(n) + "%"; } }, grid: { color: "#1E293B" } },
          cat: { ticks: { color: "#C3CBDB", autoSkip: false }, grid: { display: false } } });
      const top = sectors.slice().sort((a, b) => (D.num(b.day_pct) || -999) - (D.num(a.day_pct) || -999)).slice(0, 5)
        .map((r, i) => Object.assign({}, r, { n: String(i + 1), day_bar: r.day_pct }));
      D.drawTable(document.getElementById("top5"), {
        title: "Top 5 sectors today", sub: "Best day % of the Nifty sector indexes",
        rows: top, columns: [T("n", "#", "num", { dec: 0 }), T("name", "Sector"), T("day_bar", "", "daybar"), T("day_pct", "Day %", "pct", Object.assign({ dec: 2 }, RET))],
        state: { sort: "day_pct", dir: "desc", page: 0 }, pageSize: 5, foot: false,
      });
    }
    if (!panelOff("feature.alerts")) {
      const host = document.getElementById("alerts");
      if (!alerts.length) D.showQuiet(host, D.quietMessage(alertRaw));
      else D.drawTable(host, {
        rows: alerts, columns: [TK, T("text", "What changed", "text", { wrap: true }), T("score", "Score", "scorejump"), VE],
        state: { sort: "score", dir: "desc", page: 0 }, pageSize: 8, foot: false,
      });
    }
  }

  function flowRows(files) {
    return D.realRows(files["fii_flows.csv"] || []).slice().sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
  }
  function sumFlow(rows, key) {
    let total = 0;
    let any = false;
    rows.forEach((r) => {
      const n = D.num(r[key]);
      if (n != null) { total += n; any = true; }
    });
    return any ? total : null;
  }
  function flowWindow(rows, key, n) {
    return sumFlow(rows.slice(-n), key);
  }
  function flowPrefix(rows, key, size) {
    if (!rows.length) return null;
    const stamp = String(rows[rows.length - 1].date || "");
    const prefix = stamp.slice(0, size);
    if (!prefix) return null;
    return sumFlow(rows.filter((r) => String(r.date || "").slice(0, size) === prefix), key);
  }
  function croreHtml(n) {
    if (n == null) return D.na();
    const color = n > 0 ? "#22C55E" : n < 0 ? "#EF4444" : "#E6EBF5";
    const sign = n > 0 ? "+" : "";
    return '<span style="color:' + color + '">' + D.esc(sign + D.fmt(n, 0)) + "</span>";
  }
  function streakLine(rows, key, who) {
    if (!rows.length) return who + " history is still growing";
    const last = D.num(rows[rows.length - 1][key]);
    if (last == null || last === 0) return who + " was flat on the last session";
    const bought = last > 0;
    let n = 0;
    for (let i = rows.length - 1; i >= 0; i--) {
      const v = D.num(rows[i][key]);
      if (v == null || v === 0 || (v > 0) !== bought) break;
      n += 1;
    }
    const days = n === 1 ? "day" : "days";
    return who + " " + (bought ? "bought" : "sold") + " " + n + " " + days + " in a row";
  }
  function flowStrip(files) {
    if (panelOff("feature.fii_dii_today_strip")) return "";
    const rows = flowRows(files);
    const last = rows[rows.length - 1] || {};
    const fii = D.num(last.fii_net);
    const dii = D.num(last.dii_net);
    const when = last.date ? "Session " + last.date : "Latest session";
    return '<a class="flowstrip" href="flows.html">' +
      '<div><div class="lab">FII net, crore</div><div class="val">' + croreHtml(fii) + '</div><div class="sub">' + D.esc(when) + "</div></div>" +
      '<div><div class="lab">DII net, crore</div><div class="val">' + croreHtml(dii) + '</div><div class="sub">' + D.esc(streakLine(rows, "dii_net", "DII")) + "</div></div>" +
      '<div><div class="lab">FII streak</div><div class="sub streak">' + D.esc(streakLine(rows, "fii_net", "FII")) + "</div></div>" +
      '<div class="go">FII and DII flows ›</div></a>';
  }
  function renderTop(ctx) {
    const raw = ctx.files["scores.csv"];
    const all = D.realRows(raw);
    const liquidYes = all.filter((r) => String(r.liquid || "").toLowerCase() === "yes").length;
    const cover = all.some((r) => r.liquid) ? '<p class="cap">' + D.esc(String(all.length)) + " scored. " + D.esc(String(liquidYes)) + " pass the liquidity filter. Liquid starts on Yes. Choose All to see every name.</p>" : "";
    ctx.page.innerHTML = D.banner(raw) + cover + '<div class="ctrls" id="ctrls"></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    standardFilters(box, all, { verdict: true, sector: true, confidence: true, index: true, ticker: true, liquid: "yes", order: ["verdict", "sector", "confidence", "index", "exchange", "liquid", "ticker"] });
    const state = { sort: "score", dir: "desc", page: 0 };
    const cols = [T("rank", "#", "num", { dec: 0, width: "40px" }), TK, CO, T("exchange", "Exchange", "text", { hide: "md" }), T("sector", "Sector", "text", { hide: "md" }), SC, VE, PR, T("day_pct", "Day %", "pct", Object.assign({ dec: 2 }, RET)),
      T("timing", "Trend", "trend"), T("entry_low", "Entry low", "num", { dec: 2 }), T("entry_high", "Entry high", "num", { dec: 2, hide: "md" }),
      T("stop", "Stop", "num", { dec: 2 }), T("trade_target", "Target", "num", { dec: 2 })];
    const draw = () => {
      D.drawTable(document.getElementById("tbl"), {
        rows: all.filter((r) => readCommon(box, r)), columns: cols, state: state, pageSize: 25,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function miniStat(label, valueHtml) {
    return '<div><div class="l">' + D.esc(label) + '</div><div class="v">' + valueHtml + "</div></div>";
  }
  function px2(v) {
    return D.num(v) == null ? D.na() : D.esc(D.fmt(v, 2));
  }
  function inTargetBand(value, price) {
    const v = D.num(value);
    const p = D.num(price);
    if (v == null) return false;
    if (p == null || p <= 0) return true;
    const ratio = v / p;
    return ratio >= 0.5 && ratio <= 2;
  }
  function rangeTarget(value, price) {
    if (D.num(value) == null) return D.na();
    if (!inTargetBand(value, price)) return D.na() + '<div class="l">out of range</div>';
    return D.esc(D.fmt(value, 2));
  }
  function blendParts(row) {
    const parts = [];
    if (D.num(row.target_analyst) != null) parts.push(D.num(row.target_analyst));
    if (inTargetBand(row.target_pfcf, row.price) && D.num(row.target_pfcf) != null) parts.push(D.num(row.target_pfcf));
    if (inTargetBand(row.target_peg, row.price) && D.num(row.target_peg) != null) parts.push(D.num(row.target_peg));
    return parts;
  }
  function blendHtml(row) {
    const parts = blendParts(row);
    if (!parts.length) return D.na();
    const avg = parts.reduce((sum, n) => sum + n, 0) / parts.length;
    return '<span style="color:#7C9CFF">' + D.esc(D.fmt(avg, 2)) + "</span>";
  }
  function blendCount(row) {
    const n = blendParts(row).length;
    return n ? D.esc(String(n)) : D.na();
  }
  function holdArrow(chg) {
    const n = D.num(chg);
    if (n == null) return '<span class="m2">quarter change n/a</span>';
    if (n > 0) return '<span style="color:#22C55E">▲ ' + D.esc(D.fmt(n, 2)) + " pts</span>";
    if (n < 0) return '<span style="color:#EF4444">▼ ' + D.esc(D.fmt(Math.abs(n), 2)) + " pts</span>";
    return '<span class="m2">flat vs last quarter</span>';
  }
  function holdStat(label, pct, chg) {
    const n = D.num(pct);
    const shown = n == null ? D.na() : D.esc(D.fmt(n, 2) + "%");
    return '<div class="stat"><div class="l">' + D.esc(label) + '</div><div class="v">' + shown + '</div><div class="s">' + holdArrow(chg) + "</div></div>";
  }
  function holdRow(row) {
    if (panelOff("feature.fii_shareholding_highlight")) return "";
    return '<div class="panel pad holdrow">' +
      holdStat("FII %", row.fii_pct, row.fii_chg) +
      holdStat("DII %", row.dii_pct, row.dii_chg) +
      holdStat("Promoter %", row.promoter_pct, row.promoter_chg) +
      "</div>";
  }
  function ptsCard(label, v) {
    const n = D.num(v);
    const shown = n == null ? D.na() : D.esc(D.signedPts(n));
    return card(label, '<span style="color:#E6EBF5">' + shown + "</span>", "", n == null ? "" : D.ptsColor(n));
  }
  function renderScorecard(ctx) {
    const scores = D.realRows(ctx.files["scores.csv"]);
    const params = new URLSearchParams(location.search);
    const rank1 = (scores.find((r) => String(r.rank) === "1") || scores[0] || {}).ticker || "";
    let ticker = (params.get("t") || rank1 || "").toUpperCase();
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div id="body"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.searchHtml("ticker", "Ticker", "sc-tickers", D.uniq(scores, "ticker")) +
      D.selectHtml("kind", "News type", ["headline", "desk_note"], "headline");
    D.placeFeed(box, ctx.files["scores.csv"]);
    const input = box.querySelector("[data-filter=ticker]");
    input.value = ticker;
    const newsEmpty = "News is fetched for the focus list only. Other tickers show no rows here.";
    const draw = () => {
      ticker = (D.fieldVal(box, "ticker") || rank1).trim().toUpperCase();
      input.value = ticker;
      const url = new URL(location.href);
      url.searchParams.set("t", ticker);
      history.replaceState(null, "", url);
      const row = scores.find((r) => r.ticker === ticker);
      const host = document.getElementById("body");
      D.destroyCharts();
      if (!row) {
        host.innerHTML = '<div class="empty">No scorecard for ' + D.esc(ticker) + ".</div>";
        return;
      }
      const kind = D.fieldVal(box, "kind") || "headline";
      const day = D.num(row.day_pct);
      const details = (ctx.files["score_details.csv"] || []).filter((r) => r.ticker === ticker);
      const earn = (ctx.files["earnings_history.csv"] || []).filter((r) => r.ticker === ticker && !D.isBlank(r.eps_actual))
        .sort((a, b) => a.earnings_date < b.earnings_date ? -1 : 1).slice(-8);
      const news = (ctx.files["news.csv"] || []).filter((r) => r.ticker === ticker && (kind === "" || r.kind === kind));
      const vsRows = [
        ["pts_forward_pe_ind", "Forward P/E"], ["pts_ttm_pe_ind", "Trailing P/E"], ["pts_ps_ind", "Price / sales"],
        ["pts_pfcf_ind", "Price / FCF"], ["pts_rev_growth_ind", "Revenue growth"], ["pts_eps_growth_ind", "EPS growth"],
        ["pts_div_yield_ind", "Dividend yield"],
      ];
      const vs = vsRows.map((pair) => "<tr><td>" + D.esc(pair[1]) + '</td><td class="c">' + D.pointsHtml(row[pair[0]]) + "</td></tr>").join("");
      const basis = [
        ["Fundamentals from", row.fundamentals_basis], ["Filed", row.fundamentals_filed],
        ["Years in own average", row.fin_avg_years], ["Forward P/E average", row.forward_pe_avg_basis],
        ["Missing fields", row.missing_fields],
      ].map((pair) => '<div class="rowhead"><span>' + D.esc(pair[0]) + '</span><span class="m2" style="text-align:right">' +
        (D.isBlank(pair[1]) ? D.na() : D.esc(pair[1])) + "</span></div>").join("");
      const scoreN = D.num(row.score);
      host.innerHTML =
        '<div class="panel pad identity"><div class="id-main"><div class="big">' + D.esc(row.ticker) + "</div><div>" + D.esc(row.company) +
        '</div><div class="m2" style="font-size:12px">' + D.esc(row.sector) + (row.industry ? " · " + D.esc(row.industry) : "") +
        "</div><div class=\"m2\" style=\"font-size:12px\">Relative strength uses " + D.esc(row.rs_benchmark || "Nifty 50") + ".</div></div>" +
        '<div class="stat"><div class="l">Price</div><div class="v">' + px2(row.price) + "</div></div>" +
        '<div class="stat"><div class="l">Day %</div><div class="v" style="color:' + D.retColor(day) + '">' + (day == null ? D.na() : D.esc((day > 0 ? "+" : "") + D.fmt(day, 2) + "%")) + "</div></div>" +
        '<div class="stat"><div class="l">Confidence</div><div class="v" style="font-size:16px">' + (D.isBlank(row.confidence) ? D.na() : D.esc(row.confidence)) + '</div><div class="l" style="margin-top:8px">Verdict</div><div class="vpill">' + D.verdictHtml(row.verdict) + "</div></div>" +
        '<div class="stat"><div class="l">Desk score</div><div class="v"><span class="scorepill deskscore" style="background:' + D.band(scoreN || 0) + '">' + D.esc(scoreN == null ? "–" : String(scoreN)) + "</span></div></div></div>" +
        holdRow(row) +
        '<div class="panel pad"><p style="font-size:13px;line-height:20px">' + D.esc(row.reason || "") + "</p></div>" +
        '<div class="cards">' +
        ptsCard("Technical", row.pts_tech) + ptsCard("Financials", row.pts_fin) + ptsCard("Sentiment", row.pts_sent) +
        ptsCard("Earnings", row.pts_earnings) + ptsCard("Sector", row.pts_sector) +
        card("Total score", D.scoreHtml(row.score)) + "</div>" +
        '<div class="split plan"><div class="panel pad"><div class="ptitle">Plan</div><div class="mini">' +
        miniStat("Entry low", px2(row.entry_low)) + miniStat("Entry high", px2(row.entry_high)) +
        miniStat("Stop", D.num(row.stop) == null ? D.na() : '<span style="color:#EF4444">' + D.esc(D.fmt(row.stop, 2)) + "</span>") +
        miniStat("Trade target", D.num(row.trade_target) == null ? D.na() : '<span style="color:#22C55E">' + D.esc(D.fmt(row.trade_target, 2)) + "</span>") +
        miniStat("Reward / risk", px2(row.reward_risk)) +
        '</div><p class="cap">AVOID leaves entry and the trade target blank on purpose.</p></div>' +
        '<div class="panel pad"><div class="ptitle">Valuation</div><div class="mini">' +
        miniStat("Analyst target", px2(row.target_analyst)) + miniStat("Cash-flow target", rangeTarget(row.target_pfcf, row.price)) +
        miniStat("PEG target", rangeTarget(row.target_peg, row.price)) + miniStat("Blended target", blendHtml(row)) +
        miniStat("Inputs in blend", blendCount(row)) +
        "</div></div></div>" +
        '<div class="split chartpair">' + priceShell("Plan levels stay on the chart") +
        '<div class="panel pad"><div class="ptitle">EPS surprise %, last 8 reports</div><div class="chart-box"><canvas id="eh"></canvas></div></div></div>' +
        '<div class="split r21"><div class="panel" id="break"></div><div><div class="panel"><div class="pad" style="padding-bottom:0"><div class="ptitle">Versus sector</div></div><div class="scroll"><table><tbody>' + vs +
        '</tbody></table></div></div><div class="panel pad"><div class="ptitle">Data basis</div><div style="font-size:11px;margin-top:8px">' + basis + "</div></div></div></div>" +
        '<div class="panel" id="news"></div><p class="cap">' + D.esc(newsEmpty) + "</p>";
      const entryLo = D.num(row.entry_low);
      const entryHi = D.num(row.entry_high);
      const hlines = [];
      if (entryLo != null && entryHi != null) {
        hlines.push({
          zone: [entryLo, entryHi], color: "rgba(124,156,255,.10)", labelColor: "#F59E0B",
          label: "Entry " + D.fmt(Math.min(entryLo, entryHi), 0) + "–" + D.fmt(Math.max(entryLo, entryHi), 0),
        });
      } else if (entryLo != null || entryHi != null) {
        const one = entryLo != null ? entryLo : entryHi;
        hlines.push({ value: one, color: "#F59E0B", label: "Entry " + D.fmt(one, 2) });
      }
      if (D.num(row.stop) != null) hlines.push({ value: D.num(row.stop), color: "#EF4444", label: "Stop " + D.fmt(row.stop, 2) });
      if (D.num(row.trade_target) != null) hlines.push({ value: D.num(row.trade_target), color: "#22C55E", label: "Target " + D.fmt(row.trade_target, 2) });
      D.drawPriceChart(host.querySelector("[data-px-panel]"), { ticker: ticker, lines: hlines });
      const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const earnLabels = earn.map((r) => {
        const m = /^(\d{4})-(\d{2})/.exec(r.earnings_date || "");
        return m ? mon[Number(m[2]) - 1] + " " + m[1].slice(2) : r.earnings_date;
      });
      D.makeChart(document.getElementById("eh"), {
        type: "bar",
        data: {
          labels: earnLabels,
          datasets: [
            { label: "Surprise %", data: D.seriesNum(earn, "surprise_pct"), backgroundColor: "#7C9CFF" },
            { label: "Next-day move %", data: D.seriesNum(earn, "move_1d_pct"), backgroundColor: "#8B96AD" },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: Object.assign({}, { legend: { labels: { color: "#8B96AD", boxWidth: 12 } }, barLabels: { dec: 1, suffix: "%" } }),
          scales: {
            x: { ticks: { color: "#8B96AD", maxRotation: 0, autoSkip: false }, grid: { color: "#1E293B" } },
            y: { ticks: { color: "#8B96AD" }, grid: { color: "#1E293B" } },
          },
        },
      });
      D.drawTable(document.getElementById("break"), {
        title: "Score breakdown",
        rows: details,
        columns: [T("group_name", "Group"), T("item", "Item", "text", { wrap: true }), T("points_label", "Points", "plabel"),
          T("now_value", "Now", "num", { dec: 2 }), T("avg_value", "Own 3-yr avg", "num", { dec: 2 }), T("vs_industry", "Vs sector", "points")],
        state: { sort: "group_name", dir: "asc", sort2: "item", dir2: "asc", page: 0 }, pageSize: 20,
      });
      D.drawTable(document.getElementById("news"), {
        title: "News", sub: newsEmpty,
        rows: news,
        columns: [T("headline", "Headline", "text", { wrap: true }), T("publisher", "Source"), T("published", "Published")],
        state: { sort: "published", dir: "desc", page: 0 }, pageSize: 8,
        empty: newsEmpty,
      });
    };
    box.addEventListener("change", draw);
    draw();
  }

  function shortBucket(s) {
    const map = {
      "Scores 0 or below": "≤0",
      "Scores 1 to 3": "1-3",
      "Scores 4 to 5": "4-5",
      "Scores 6 to 7": "6-7",
      "Scores 8 to 9": "8-9",
      "Scores 10 or more": "10+",
    };
    return map[s] || s;
  }
  function passCell(v) {
    const s = String(v || "");
    if (D.isBlank(s)) return D.na();
    if (s.toUpperCase() === "PASS") return '<span class="pill" style="color:#22C55E">PASS</span>';
    if (s.toUpperCase() === "FAIL") return '<span class="pill" style="color:#EF4444">FAIL</span>';
    return D.esc(s);
  }
  function prettyNums(text) {
    return String(text == null ? "" : text).replace(/-?\d[\d,]*(?:\.\d+)?/g, (m) => {
      const n = Number(m.replace(/,/g, ""));
      if (!Number.isFinite(n) || Math.abs(n) < 1000) return m;
      if (Math.abs(n - Math.round(n)) > 0.05) return m;
      return Math.round(n).toLocaleString("en-US");
    });
  }
  function letterHtml(row, key) {
    if (key === "m_status") {
      const word = D.marketWord(row.m_market);
      const note = prettyNums(row.m_status || "");
      const head = word ? '<b style="color:' + D.marketColor(word) + '">' + D.esc(word) + "</b>" : "";
      if (!head && D.isBlank(note)) return D.na();
      return head + (note ? " " + D.esc(note) : "");
    }
    if (D.isBlank(row[key])) return D.na();
    return D.esc(prettyNums(row[key]));
  }
  function letterBlock(list, row) {
    const cols = [
      ["c_status", "C"], ["a_status", "A"], ["n_status", "N"], ["s_status", "S"],
      ["l_status", "L"], ["i_status", "I"], ["m_status", "M"],
    ];
    const head = "<th>Ticker</th>" + cols.map((c) => "<th>" + c[1] + "</th>").join("");
    const body = list.map((r) => "<tr><td>" + D.tickerHtml(r.ticker) + "</td>" + cols.map((c) =>
      '<td class="wrap">' + letterHtml(r, c[0]) + "</td>").join("") + "</tr>").join("");
    const cards = list.map((r) => '<article class="lettercard"><div class="buyid">' + D.tickerHtml(r.ticker) + "</div>" +
      cols.map((c) => '<div class="lrow"><b>' + c[1] + "</b><div>" + letterHtml(r, c[0]) + "</div></div>").join("") +
      "</article>").join("");
    return '<div class="letterwrap"><div class="panel"><div class="pad" style="padding-bottom:0"><div class="ptitle">Letter details</div><div class="psub">M is the market. Nifty 50, SENSEX, and Bank Nifty versus their 21, 50, and 200 day averages.</div></div>' +
      '<div class="scroll lettertable"><table><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      '<div class="letters">' + cards + "</div></div>" +
      '<div class="panel pad"><div class="ptitle">Why this name</div><p class="cap">' + D.esc((row && row.reason) || "") + "</p></div>";
  }
  function canslimGuide() {
    if (!D.featureOn("feature.canslim_guide")) return "";
    const rows = [
      ["C", "Current quarterly earnings", "Profit this quarter versus the same quarter last year. The scan wants +25% or more."],
      ["A", "Annual earnings growth", "Yearly profit growth. The scan wants +25% for 3 years."],
      ["N", "New", "A new product, new management, or a new 52-week high."],
      ["S", "Supply and demand", "Shares available, and big volume on up days."],
      ["L", "Leader or laggard", "A top stock in its group. The scan wants an RS rank of 80 or higher."],
      ["I", "Institutional sponsorship", "Are big funds buying? That means FII, DII, and mutual funds."],
      ["M", "Market direction", "Is the overall market in an uptrend? This desk shows the Nifty 50, SENSEX, and Bank Nifty. The check passes when the Nifty 50 or SENSEX is in an uptrend."],
    ];
    const narrow = window.matchMedia("(max-width: 900px)").matches;
    const body = rows.map((r) => '<div class="ckey"><b>' + r[0] + '</b><div><div class="t">' + D.esc(r[1]) +
      '</div><div class="d">' + D.esc(r[2]) + "</div></div></div>").join("");
    return '<details class="canslim-key"' + (narrow ? "" : " open") + "><summary>What CANSLIM means</summary><div class=\"ckeys\">" + body + "</div></details>";
  }
  function moodColor(text) {
    const s = String(text || "");
    if (s.indexOf("UP") === 0) return "#22C55E";
    if (s.indexOf("DOWN") === 0) return "#EF4444";
    if (s.indexOf("MIXED") === 0) return "#F59E0B";
    return "#8B96AD";
  }
  function moodShort(text) {
    const s = String(text || "");
    const i = s.indexOf(" / ");
    if (!s) return "–";
    return i > 0 ? s.slice(0, i) : s;
  }
  function byStatus(rows) {
    return rows.slice().sort((a, b) => {
      const c = String(a.status || "").localeCompare(String(b.status || ""));
      if (c) return c;
      return (D.num(b.strength) || 0) - (D.num(a.strength) || 0);
    });
  }
  function whyLines(rows) {
    return (rows || []).filter(Boolean).map((r) => '<div class="why"><span>' + D.tickerHtml(r.ticker) +
      '</span><span class="m2">' + D.esc(r.reason || "") + "</span></div>").join("") ||
      '<div class="m2">No names in this view.</div>';
  }

  function renderWatch(ctx) {
    const port = D.realRows(ctx.files["portfolio.csv"]);
    const sum = (ctx.files["portfolio_summary.csv"] || [])[0] || {};
    const watch = D.realRows(ctx.files["watchlist.csv"]);
    const nHold = sum.n_holdings || String(port.length);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      (sum.example_warning ? '<div class="note-strip">' + D.esc(sum.example_warning) + "</div>" : "") +
      '<div class="cards" id="cards"></div><div class="panel" id="hold"></div><div class="panel" id="watch"></div>' +
      '<p class="cap">Week-ago score stays blank until a score is seven days old. A dash is missing, not zero. These files are the published output of input/holdings.csv and input/my_watchlist.csv.</p>';
    const pnl = D.num(sum.day_pnl);
    const gain = D.num(sum.total_gain);
    const attn = String(sum.needs_attention || "0");
    document.getElementById("cards").innerHTML =
      card("Portfolio value", D.num(sum.value) == null ? D.na() : D.esc("₹" + D.fmt(sum.value, 0)), D.esc(nHold) + " holdings") +
      card("Day P/L", pnl == null ? D.na() : '<span style="color:' + D.retColor(pnl) + '">' + D.esc((pnl > 0 ? "+₹" : pnl < 0 ? "-₹" : "₹") + D.fmt(Math.abs(pnl), 2)) + "</span>",
        D.num(sum.day_pnl_pct) == null ? D.na() : '<span style="color:' + D.retColor(D.num(sum.day_pnl_pct)) + '">' + (D.num(sum.day_pnl_pct) > 0 ? "+" : "") + D.fmt(sum.day_pnl_pct, 2) + "%</span>") +
      card("Total gain", gain == null ? D.na() : '<span style="color:' + D.retColor(gain) + '">' + D.esc((gain > 0 ? "+₹" : gain < 0 ? "-₹" : "₹") + D.fmt(Math.abs(gain), 0)) + "</span>",
        D.num(sum.total_gain_pct) == null ? "" : '<span style="color:' + D.retColor(D.num(sum.total_gain_pct)) + '">' + (D.num(sum.total_gain_pct) > 0 ? "+" : "") + D.fmt(sum.total_gain_pct, 2) + "%</span>") +
      card("Average desk score", D.num(sum.avg_score) == null ? D.na() : D.esc(D.fmt(sum.avg_score, 1)),
        '<span style="color:#F59E0B">' + D.esc(attn) + "</span> " + (attn === "1" ? "needs" : "need") + " attention");
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("verdict", "Verdict", D.uniq(port, "verdict")) +
      D.multiHtml("status", "Holding status", D.uniq(port, "status")) +
      D.searchHtml("ticker", "Ticker", "pf-tk", D.uniq(port.concat(watch), "ticker"));
    const hs = { sort: "weight_pct", dir: "desc", page: 0 };
    const ws = { sort: "score", dir: "desc", page: 0 };
    const draw = () => {
      const rows = port.filter((r) => D.matchMulti(r, "verdict", D.selectedMulti(box, "verdict")) &&
        D.matchMulti(r, "status", D.selectedMulti(box, "status")) && D.matchText(r, "ticker", D.fieldVal(box, "ticker")));
      const q = (D.fieldVal(box, "ticker") || "").trim();
      const example = port.some((r) => r.example === "yes") ? " · example rows" : "";
      D.drawTable(document.getElementById("hold"), {
        title: "My holdings", sub: nHold + " holdings" + example, rows: rows,
        columns: [TK, T("shares", "Shares", "num", { dec: 0 }), T("avg_cost", "Avg cost", "num", { dec: 2 }), PR,
          T("value", "Value", "money", { dec: 0 }), T("gain", "Gain", "money", { dec: 0, color: true }),
          T("gain_pct", "Gain %", "pct", { color: true }), T("weight_pct", "Weight %", "pct", { color: false }), SC,
          T("score_week_change", "Score vs week ago", "delta", { dec: 0 }),
          VE, T("stop", "Stop", "num", { dec: 2, tone: "stop" }), T("status", "Status", "hold")],
        state: hs, pageSize: 25,
      });
      D.drawTable(document.getElementById("watch"), {
        title: "Watchlist, not owned yet",
        rows: watch.filter((r) => D.matchText(r, "ticker", q) && D.matchMulti(r, "verdict", D.selectedMulti(box, "verdict"))),
        columns: [TK, CO, PR, T("day_pct", "Day %", "pct", { color: true }), SC, VE,
          T("entry_low", "Entry low", "num", { dec: 2 }), T("entry_high", "Entry high", "num", { dec: 2 }),
          T("distance_to_entry_pct", "Distance to entry %", "dist"), T("timing", "Trend", "trend"),
          T("note_input", "Nick's note", "muted", { wrap: true })],
        state: ws, pageSize: 25,
      });
    };
    hook(box, hs, draw);
    draw();
  }

  function renderAlerts(ctx) {
    const raw = ctx.files["alerts.csv"];
    const changeRaw = ctx.files["score_changes.csv"] || [];
    const all = D.alertDataRows(raw);
    const changes = D.realRows(changeRaw);
    const live = all;
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">These are changes since the previous run. Nothing is emailed or sent to a phone.</p>' +
      '<div class="cards" id="cards"></div><div class="panel" id="tbl"></div><div class="panel" id="chg" style="margin-top:24px"></div>';
    document.getElementById("cards").innerHTML =
      card("Changes this run", String(live.length)) +
      card("Verdict changes", String(countWhere(live, (r) => r.kind === "verdict_change"))) +
      card("Breakouts", String(countWhere(live, (r) => r.kind === "breakout"))) +
      card("Entry-zone arrivals", String(countWhere(live, (r) => r.kind === "entry_zone")));
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("kind", "Alert type", D.uniq(all, "kind")) +
      D.multiHtml("verdict", "Verdict now", D.uniq(all, "verdict")) +
      D.searchHtml("ticker", "Ticker", "al-tk", D.uniq(all, "ticker")) +
      D.pairHtml("lo", "hi", "Score change", "", "");
    const state = { sort: "score", dir: "desc", page: 0 };
    const st2 = { sort: "score_change", dir: "desc", page: 0 };
    const inChange = (r) => {
      const n = D.num(r.score_change);
      const lo = D.fieldVal(box, "lo");
      const hi = D.fieldVal(box, "hi");
      if ((lo !== "" || hi !== "") && n == null) return false;
      if (lo !== "" && n < Number(lo)) return false;
      if (hi !== "" && n > Number(hi)) return false;
      return true;
    };
    const draw = () => {
      const alertHost = document.getElementById("tbl");
      if (!all.length) D.showQuiet(alertHost, D.quietMessage(raw), "Alerts");
      else {
        const rows = all.filter((r) => D.matchMulti(r, "kind", D.selectedMulti(box, "kind")) &&
          D.matchMulti(r, "verdict", D.selectedMulti(box, "verdict")) &&
          D.matchText(r, "ticker", D.fieldVal(box, "ticker")));
        D.drawTable(alertHost, {
          title: "Alerts", rows: rows,
          columns: [TK, T("kind", "Type", "kind"), T("text", "What changed", "text", { wrap: true }),
            SC, T("score_prev", "Score before", "num", { dec: 0 }),
            VE, T("verdict_prev", "Verdict before", "verdict"), PR],
          state: state, pageSize: 12,
        });
      }
      const q = (D.fieldVal(box, "ticker") || "").trim();
      const changeHost = document.getElementById("chg");
      const changeRows = changes.filter((r) => D.matchText(r, "ticker", q) && D.matchMulti(r, "verdict", D.selectedMulti(box, "verdict")) && inChange(r));
      if (!changes.length) D.showQuiet(changeHost, D.quietMessage(changeRaw), "Score changes");
      else D.drawTable(changeHost, {
        title: "Score changes",
        rows: changeRows,
        columns: [TK, CO, SC, T("score_prev", "Score before", "num", { dec: 0 }), T("score_change", "Change", "delta", { dec: 0 }),
          VE, T("day_pct", "Day %", "pct", { color: true }), PR],
        state: st2, pageSize: 12,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderBacktest(ctx) {
    const summary = D.realRows(ctx.files["backtest_summary.csv"]);
    const equity = D.realRows(ctx.files["backtest_equity.csv"]);
    const buckets = D.realRows(ctx.files["backtest_buckets.csv"]).map((r) => Object.assign({}, r, { bucket_short: shortBucket(r.bucket) }));
    const yearly = D.realRows(ctx.files["backtest_yearly.csv"]);
    const notes = ctx.files["backtest_notes.csv"] || [];
    function windowLabel(r) {
      const name = r.window || "";
      if (name === "5y" && r.start && r.end) {
        const days = (Date.parse(r.end) - Date.parse(r.start)) / 86400000;
        const years = days / 365.25;
        if (Number.isFinite(years) && years < 4.6) return "Full history (" + years.toFixed(1) + "y)";
      }
      return name || ((r.start || "") + " to " + (r.end || ""));
    }
    summary.forEach((r) => { r._label = windowLabel(r); });
    const prefer = summary.find((r) => r.is_headline === "yes") || summary.slice().sort((a, b) => (D.num(b.months) || 0) - (D.num(a.months) || 0))[0];
    const head = summary.find((r) => r.is_headline === "yes") || prefer || summary[0] || {};
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="panel pad" id="head"></div><div class="cards" id="cards"></div>' +
      '<div class="split r21"><div class="panel pad"><div class="ptitle">Growth of 10,000, monthly test</div><div class="chart-box tall"><canvas id="eq"></canvas></div><p class="cap" id="eqcap"></p></div>' +
      '<div class="panel pad"><div class="ptitle">Excess return vs Nifty 50 by score bucket</div><div class="psub">12-week horizon, % per signal</div><div class="chart-box tall"><canvas id="bk"></canvas></div></div></div>' +
      '<div class="split r21"><div class="panel" id="btbl"></div><div class="panel" id="ytbl"></div></div><div class="panel" id="notes"></div>';
    const spanAvail = String(head._label || "").match(/Full history \(([\d.]+)y\)/);
    document.getElementById("head").innerHTML = '<div style="font-size:20px;line-height:26px">' + D.esc(head.headline || "") + "</div>" +
      '<div class="m2" style="font-size:11px;margin-top:6px">From ' + D.esc(head.start || "") + " to " + D.esc(head.end || "") + " · " +
      D.esc(head.months || "") + " months" + (spanAvail ? " · " + spanAvail[1] + " of 5 years available" : "") +
      " · every month, buy the 20 highest-scoring stocks, compare with the Nifty 50.</div>";
    const box = document.getElementById("ctrls");
    const windows = summary.map((r) => r._label);
    const horizons = D.uniq(buckets, "horizon");
    box.innerHTML = D.selectHtml("window", "Test window", windows, prefer ? prefer._label : "", { all: false }) +
      D.selectHtml("horizon", "Horizon", horizons, horizons.indexOf("12w") >= 0 ? "12w" : (horizons[0] || ""), { all: false });
    const bstate = { sort: "bucket_order", dir: "asc", page: 0 };
    const ystate = { sort: "year", dir: "asc", page: 0 };
    const draw = () => {
      const w = D.fieldVal(box, "window");
      const row = summary.find((r) => r._label === w) || prefer || summary[0] || {};
      const dd = D.num(row.top20_max_drawdown_pct);
      document.getElementById("cards").innerHTML =
        card("Top-20 yearly pace %", ntext(D.num(row.top20_cagr_pct), 1)) +
        card("Nifty 50 yearly pace %", ntext(D.num(row.spy_cagr_pct), 1)) +
        card("Worst drop, top 20 %", dd == null ? D.na() : '<span style="color:#EF4444">' + D.esc(D.fmt(dd, 1)) + "</span>") +
        card("12-week hit rate %", ntext(D.num(row.hit_rate_12w_pct), 1));
      const hz = D.fieldVal(box, "horizon") || "12w";
      const brows = buckets.filter((r) => r.horizon === hz).slice().sort((a, b) => (D.num(a.bucket_order) || 0) - (D.num(b.bucket_order) || 0));
      const last = equity[equity.length - 1] || {};
      document.getElementById("eqcap").textContent = "Last point: top 20 " + (D.fmt(last.top20, 0) || "–") +
        " · Nifty 50 " + (D.fmt(last.spy, 0) || "–") + " · bottom 20 " + (D.fmt(last.bottom20, 0) || "–") + ".";
      D.destroyCharts();
      D.lineChart(document.getElementById("eq"), equity.map((r) => r.date), [
        { label: "Top 20 by score", data: D.seriesNum(equity, "top20"), color: "#22C55E", spanGaps: true },
        { label: "Nifty 50", data: D.seriesNum(equity, "spy"), color: "#E6EBF5", spanGaps: true },
        { label: "Bottom 20", data: D.seriesNum(equity, "bottom20"), color: "#EF4444", spanGaps: true },
      ], { y: { ticks: { callback: (v) => D.compact(v) } } });
      D.barChart(document.getElementById("bk"), brows.map((r) => r.bucket_short), brows.map((r) => D.num(r.excess_pct)),
        brows.map((r) => (D.num(r.excess_pct) || 0) >= 0 ? "#22C55E" : "#EF4444"),
        { labels: true, dec: 1, suffix: "%", y: { grace: "10%" } });
      D.drawTable(document.getElementById("btbl"), {
        title: "Score buckets, " + hz.replace("w", " weeks"), rows: brows,
        columns: [T("bucket_order", "", "num", { dec: 0, hidden: true }), T("bucket_short", "Score bucket"), T("n", "Signals", "num", { dec: 0 }),
          T("avg_return_pct", "Avg return %", "pct", { color: true }), T("avg_spy_pct", "Nifty same period %", "pct", { color: true }),
          T("excess_pct", "Excess %", "pct", { color: true }), T("hit_rate_pct", "Hit rate %", "pct", { dec: 1, color: false })],
        state: bstate, pageSize: 10, foot: false,
      });
      D.drawTable(document.getElementById("ytbl"), {
        title: "Year by year", sub: "2026 is the year so far.", rows: yearly,
        columns: [T("year", "Year"), T("top20_pct", "Top 20 %", "pct", { color: true }), T("spy_pct", "Nifty 50 %", "pct", { color: true }),
          T("difference_pct", "Difference %", "pct", { color: true }), T("signals", "Signals", "num", { dec: 0 })],
        state: ystate, pageSize: 12, foot: false,
      });
    };
    hook(box, bstate, draw);
    draw();
    D.drawTable(document.getElementById("notes"), {
      title: "Test limits, read before trusting the score",
      rows: notes, columns: [T("item", "What was tested", "item", { width: "300px" }), T("detail", "Detail", "text", { wrap: true })],
      state: { sort: "item", dir: "asc", page: 0 }, pageSize: 20, foot: false,
    });
  }

  const growth = passesPage({
    file: "scanner_growth.csv",
    caption: "Passes when revenue growth is at least the desk's growth level (setting scoring.growth_min_pct) and the label is not AVOID. Blank growth means the filing did not have it.",
    sort: "rev_growth",
    filters: { passes: "yes", sector: true, verdict: true, ticker: true },
    columns: [TK, CO, SE, PR, SC, VE, T("rev_growth", "Revenue growth %", "pct", { dec: 1, color: true }), T("eps_growth", "EPS growth %", "pct", { dec: 1, color: true }), T("rs_spy_3m", "vs Nifty, 3 mo %", "pct", { dec: 1, color: true })],
    cards(all) {
      const pass = all.filter((r) => r.passes === "yes");
      return card("Passing the screen", String(pass.length)) +
        card("Of those, BUY", String(countWhere(pass, (r) => r.verdict === "BUY"))) +
        card("Average revenue growth %, passing", ntext(avg(pass, "rev_growth"), 1)) +
        card("Average 3-month vs Nifty %, passing", ntext(avg(pass, "rs_spy_3m"), 1));
    },
  });

  const quality = passesPage({
    file: "scanner_quality.csv",
    caption: "Passes = ROE point +1 and debt/equity under 1.5. Debt points compare to the sector and can be −1.",
    sort: "roe",
    filters: { passes: "yes", sector: true, verdict: true, ticker: true },
    columns: [TK, CO, SE, T("roe", "Return on equity %", "pct", { dec: 1, color: false }), T("de", "Debt / equity", "num", { dec: 2 }),
      T("pts_roe", "ROE points", "points"), T("pts_de", "Debt points", "points"), SC, VE],
    notice(all) {
      const roe = countWhere(all, (r) => D.num(r.roe) != null);
      const pass = countWhere(all, (r) => r.passes === "yes");
      if (pass === 0 && roe === 0) {
        return '<div class="note-strip">No stock passes today: return on equity and debt/equity are not on file (blank, not zero).</div>';
      }
      return "";
    },
    cards(all) {
      return card("Passing the screen", String(countWhere(all, (r) => r.passes === "yes"))) +
        card("ROE on file", String(countWhere(all, (r) => D.num(r.roe) != null))) +
        card("Debt/equity on file", String(countWhere(all, (r) => D.num(r.de) != null)));
    },
  });

  const dividend = passesPage({
    file: "scanner_dividend.csv",
    caption: "Passes when the yield is at least the desk's level (setting scoring.dividend_min_pct) and the label is not AVOID. A yield of 0 is real (no dividend). A dash means the yield could not be read.",
    sort: "div_yield",
    filters: { passes: "yes", sector: true, verdict: true, ticker: true },
    columns: [TK, CO, SE, PR, T("div_yield", "Yield %", "pct", { color: false }), T("div_yield_avg", "Own avg yield %", "pct", { color: false }),
      T("pts_div_yield", "Yield points", "points"), SC, VE],
    cards(all) {
      const pass = all.filter((r) => r.passes === "yes");
      const above = countWhere(pass, (r) => { const a = D.num(r.div_yield), b = D.num(r.div_yield_avg); return a != null && b != null && a > b; });
      return card("Passing the screen", String(pass.length)) +
        card("Of those, BUY", String(countWhere(pass, (r) => r.verdict === "BUY"))) +
        card("Average yield %, passing", ntext(avg(pass, "div_yield"), 2)) +
        card("Yield above own average", String(above));
    },
  });

  const wheel = passesPage({
    file: "scanner_wheel.csv",
    caption: "",
    noticeAbove: true,
    sort2: "dollar_volume",
    notice() {
      return '<p class="cap">Stock screen only. No option contracts. Indian options use fixed lot sizes, so this page does not pick a contract.</p>';
    },
    filters: { passes: "yes", sector: true, trend: true, ticker: true },
    columns: [TK, CO, SE, PR, SC, VE, T("timing", "Trend", "trend"), T("rsi14", "RSI-14", "num", { dec: 1 }),
      T("above_sma200", "Above 200-day", "flag", { no: "#EF4444" }), T("dollar_volume", "Rupee volume", "dollars")],
    cards(all) {
      const pass = all.filter((r) => r.passes === "yes");
      const med = median(pass, "dollar_volume");
      return card("Passing the screen", String(pass.length)) +
        card("Of those, BUY", String(countWhere(pass, (r) => r.verdict === "BUY"))) +
        card("Average RSI-14, passing", ntext(avg(pass, "rsi14"), 1)) +
        card("Median daily rupee volume, passing", med == null ? D.na() : D.esc("₹" + String(D.compact(med)).replace(/^-/, "")));
    },
  });

  const vcpRuleLabels = ["Above 150d & 200d", "150d over 200d", "200d rising", "50d over 150d & 200d", "Above 50d", "30%+ over 52w low", "Within 25% of 52w high", "Beats Nifty 6m & 12m"];
  const vcp = patternPage({
    file: "scanner_vcp.csv",
    caption: "",
    filters: { status: true, statusDefault: readyDefault, index: true, ticker: true, single: [{ key: "in_trade", label: "In a trade" }] },
    columns: [TK, T("index_membership", "Index"), T("status", "Status", "setup"), PR, T("pivot", "Buy point", "num", { dec: 2 }),
      T("stop", "Stop", "num", { dec: 2, tone: "stop" }), T("target", "Target", "num", { dec: 2, tone: "target" }), T("trail", "20-day trail", "num", { dec: 2 }),
      T("trend_score", "Trend template", "of8"), T("contractions", "Pullbacks"), T("depths", "Pullback depths %"),
      T("strength", "Strength", "strengthbar"), T("freshness", "Freshness", "fresh")],
    price: setupLines,
    priceSub: "Buy point, stop, and target when the scan has them",
    cards(all) {
      return card("Broken out today", String(countWhere(all, (r) => r.status === "BROKEN OUT today"))) +
        card("Ready", String(countWhere(all, (r) => r.status === "READY"))) +
        card("Watching", String(countWhere(all, (r) => r.status === "WATCHING"))) +
        card("In a trade (buy printed)", String(countWhere(all, (r) => r.in_trade === "yes")));
    },
    detail(row, rows) {
      const list = byStatus(rows).slice(0, 12);
      const head = "<th>Ticker</th>" + vcpRuleLabels.map((l) => '<th class="c">' + D.esc(l) + "</th>").join("");
      const body = list.map((r) => "<tr><td>" + D.tickerHtml(r.ticker) + "</td>" +
        vcpRuleLabels.map((_, i) => '<td class="c">' + passCell(r["r" + (i + 1)]) + "</td>").join("") + "</tr>").join("");
      return '<div class="split r12"><div class="panel pad"><div class="ptitle">Why this name</div>' + whyLines(row ? [row] : []) + "</div>" +
        '<div class="panel"><div class="pad" style="padding-bottom:0"><div class="ptitle">Trend template, 8 rules</div></div><div class="scroll"><table class="rules"><thead><tr>' +
        head + "</tr></thead><tbody>" + body + "</tbody></table></div></div></div>";
    },
  });

  const canslim = patternPage({
    file: "scanner_canslim.csv",
    caption: "Stop and target are blank on every row on purpose. A dash is missing, not zero. Product, float and industry rank are not verified.",
    filters: {
      status: true, statusDefault: readyDefault, index: true, ticker: true,
      order: ["status", "qualify", "index", "ticker"],
      single: [{ key: "qualify", label: "Qualify", value: "strict" }],
    },
    guide: canslimGuide,
    strip(all, ctx) {
      const row = all[0] || {};
      const mt = ((ctx && ctx.files["market_today.csv"]) || [])[0] || {};
      return trendStrip({
        nifty_trend: row.m_spy || mt.nifty_trend,
        sensex_trend: row.m_sensex || mt.sensex_trend,
        bank_trend: row.m_qqq || mt.bank_trend,
        spy_price: mt.spy_price,
        spy_day_pct: mt.spy_day_pct,
        sensex_price: mt.sensex_price,
        sensex_day_pct: mt.sensex_day_pct,
        bank_price: mt.bank_price,
        qqq_day_pct: mt.qqq_day_pct,
      });
    },
    columns: [TK, T("index_membership", "Index"), T("status", "Status", "setup"), T("pivot", "Buy point", "num", { dec: 2 }),
      T("strength", "CANSLIM strength (raw)", "num", { dec: 0 }), T("qualify", "Qualify", "pass"),
      T("c_quarterly_eps", "C: quarter EPS vs yr ago %", "pct", { dec: 1 }), T("a_annual_eps", "A: annual EPS %", "pct", { dec: 1 }),
      T("n_pct_from_high", "N: % from 52w high", "pct", { dec: 1 }), T("s_adv", "S: avg daily volume", "shares"),
      T("l_rs_percentile", "L: RS percentile", "num", { dec: 0 }), T("i_trend", "I: holders trend", "itrend"),
      T("m_market", "M: market", "market"), T("freshness", "Data", "fresh")],
    cards(all) {
      return card("Ready", String(countWhere(all, (r) => r.status === "READY"))) +
        card("Broken out today", String(countWhere(all, (r) => r.status === "BROKEN OUT today"))) +
        card("Strict qualify", String(countWhere(all, (r) => r.qualify === "strict"))) +
        card("Watching", String(countWhere(all, (r) => r.status === "WATCHING")));
    },
    detail(row, rows) {
      return letterBlock(byStatus(rows).slice(0, 8), row);
    },
  });

  const box = patternPage({
    file: "scanner_box.csv",
    caption: "Desk rule, not the Pine script: a 15 to 40 day range no wider than 10% whose first and last closes drift by 5% or less, then a close through the range high on volume above 1.5 times the 50-day average.",
    filters: { status: true, statusDefault: readyDefault, index: true, sector: true, ticker: true },
    columns: [TK, CO, T("index_membership", "Index"), T("status", "Status", "setup"), PR,
      T("pivot", "Buy point (range high)", "num", { dec: 2 }), T("stop", "Stop (range low)", "num", { dec: 2, tone: "stop" }),
      T("target", "Target", "num", { dec: 2, tone: "target" }), T("strength", "Strength", "strengthbar"),
      T("range_days", "Range days", "num", { dec: 0 }), T("range_width_pct", "Range width %", "pct", { dec: 1, color: false }),
      T("volume_ratio", "Volume vs 50-day", "volx", { dec: 2 }), T("freshness", "Data", "fresh")],
    price: setupLines,
    cards(all) {
      return card("Broken out today", String(countWhere(all, (r) => r.status === "BROKEN OUT today"))) +
        card("Ready", String(countWhere(all, (r) => r.status === "READY"))) +
        card("Watching", String(countWhere(all, (r) => r.status === "WATCHING")));
    },
    detail(row) {
      return '<div class="panel pad"><div class="ptitle">Why this name</div>' + whyLines(row ? [row] : []) + "</div>";
    },
  });

  const flag = patternPage({
    file: "scanner_flag.csv",
    caption: "Desk rule, not the Pine script: a pole of at least 15% in 3 to 12 sessions, then a 3 to 15 day flag that retraces less than half the pole, then a close through the flag high on volume above 1.5 times the 50-day average.",
    filters: { status: true, statusDefault: readyDefault, index: true, sector: true, ticker: true },
    columns: [TK, CO, T("index_membership", "Index"), T("status", "Status", "setup"), PR,
      T("pivot", "Buy point (flag high)", "num", { dec: 2 }), T("stop", "Stop (flag low)", "num", { dec: 2, tone: "stop" }),
      T("target", "Target", "num", { dec: 2, tone: "target" }), T("strength", "Strength", "strengthbar"),
      T("pole_pct", "Pole rise %", "pct", { dec: 1, color: false }), T("flag_bars", "Flag days", "num", { dec: 0 }),
      T("retrace_pct", "Pullback of pole %", "retrace", { dec: 1 }), T("volume_ratio", "Volume vs 50-day", "volx", { dec: 2 }),
      T("freshness", "Data", "fresh")],
    price: setupLines,
    cards(all) {
      return card("Broken out today", String(countWhere(all, (r) => r.status === "BROKEN OUT today"))) +
        card("Ready", String(countWhere(all, (r) => r.status === "READY"))) +
        card("Watching", String(countWhere(all, (r) => r.status === "WATCHING")));
    },
    detail(row) {
      return '<div class="panel pad"><div class="ptitle">Why this name</div>' + whyLines(row ? [row] : []) + "</div>";
    },
  });

  const qmStatus = ["READY", "BROKEN OUT today", "IN TRADE"];
  const qmHead = [TK, CO, T("index_membership", "Index"), T("status", "Status", "setup"), PR,
    T("pivot", "Buy point (base high)", "num", { dec: 2 }), T("entry", "Entry (fill)", "num", { dec: 2 }),
    T("stop", "Stop", "num", { dec: 2, tone: "stop" }), T("stop_basis", "Stop from"),
    T("stop_check", "Stop check"), T("stop_adr", "Stop in ADRs", "num", { dec: 2 }),
    T("risk_pct", "Risk %", "pct", { dec: 1, color: false }), T("shares", "Shares (0.5% risk)", "num", { dec: 0 }),
    T("strength", "Strength", "strengthbar"),
    T("adr_pct", "ADR %", "pct", { dec: 2, color: false }), T("adr_tag", "ADR tag"),
    T("leader_top_pct", "Return rank, top %", "num", { dec: 1 }), T("leader_window", "Rank on days", "num", { dec: 0 }),
    T("run_pct", "Run before base %", "pct", { dec: 1, color: false }), T("run_days", "Run days", "num", { dec: 0 }),
    T("base_days", "Base days", "num", { dec: 0 }), T("base_range_pct", "Base range %", "pct", { dec: 1, color: false }),
    T("higher_lows", "Higher lows", "flag"), T("dry_up", "Volume dried up", "flag"),
    T("confirmed_close", "Closed above buy point", "flag"), T("volume_ratio", "Volume vs prior 50-day", "volx", { dec: 2 }),
    T("volume_flag", "Big volume", "flag")];
  const qmTail = [T("breakout_date", "Breakout day"), T("days_in_trade", "Days in trade", "num", { dec: 0 }),
    T("exit_reason", "Closed because"), T("exit_date", "Closed on"),
    T("market_light", "Market light"), T("earnings_soon", "Results within 5 days", "flag", { yes: "#F59E0B" }),
    T("traded_value_cr", "20-day value Rs Cr", "num", { dec: 1 }), T("price_band", "Price band"),
    T("freshness", "Data", "fresh")];
  function qmCards(all) {
    return card("Broken out today", String(countWhere(all, (r) => r.status === "BROKEN OUT today"))) +
      card("Ready", String(countWhere(all, (r) => r.status === "READY"))) +
      card("In a trade", String(countWhere(all, (r) => r.status === "IN TRADE"))) +
      card("Closed", String(countWhere(all, (r) => r.status === "CLOSED"))) +
      card("Watching", String(countWhere(all, (r) => r.status === "WATCHING")));
  }
  function qmLines(row) {
    const lines = setupLines(row).filter((l) => l.label.indexOf("Target") !== 0);
    if (!row) return lines;
    if (D.num(row.trail) != null) lines.push({ value: D.num(row.trail), color: "#7C9CFF", label: "Trail " + (row.trail_with || "") + " " + D.fmt(row.trail, 2) });
    return lines;
  }
  const qullamaggie = patternPage({
    file: "scanner_qullamaggie.csv",
    caption: "",
    filters: { status: true, statusDefault: qmStatus, index: true, sector: true, ticker: true,
      single: [{ key: "stop_check", label: "Stop check" }, { key: "trail_signal", label: "Trail signal" }] },
    columns: qmHead.concat([T("partial_flag", "Sell 1/3 to 1/2"), T("trail_with", "Trail with"),
      T("trail", "Trail line", "num", { dec: 2 }), T("trail_signal", "Trail signal", "setup")], qmTail),
    price: qmLines,
    priceSub: "Buy point, stop, and trail line",
    cards: qmCards,
    detail(row) {
      return '<div class="panel pad"><div class="ptitle">Why this name</div>' + whyLines(row ? [row] : []) + "</div>";
    },
  });

  function mariosLines(row) {
    const lines = setupLines(row).filter((l) => l.label.indexOf("Target") !== 0);
    if (!row) return lines;
    if (D.num(row.target_low) != null) lines.push({ value: D.num(row.target_low), color: "#22C55E", label: "Sell part at " + D.fmt(row.target_low, 2) + " (2.5 ADR)" });
    if (D.num(row.target_high) != null) lines.push({ value: D.num(row.target_high), color: "#22C55E", label: "3 ADR " + D.fmt(row.target_high, 2) });
    if (D.num(row.trail10) != null) lines.push({ value: D.num(row.trail10), color: "#7C9CFF", label: "10-day " + D.fmt(row.trail10, 2) });
    if (D.num(row.trail20) != null) lines.push({ value: D.num(row.trail20), color: "#A78BFA", label: "20-day " + D.fmt(row.trail20, 2) });
    return lines;
  }
  const marios = patternPage({
    file: "scanner_marios.csv",
    caption: "",
    filters: { status: true, statusDefault: qmStatus, index: true, sector: true, ticker: true,
      single: [{ key: "stop_check", label: "Stop check" }, { key: "trail_signal", label: "Trail signal" }] },
    columns: qmHead.concat([T("weak_close", "Weak day-1 close", "flag", { yes: "#EF4444" }),
      T("target_low", "Sell 1/4 to 1/3 at (2.5 ADR)", "num", { dec: 2, tone: "target" }),
      T("target_high", "3 ADR level", "num", { dec: 2, tone: "target" }),
      T("partial_hit", "Partial hit", "flag"), T("partial_date", "Partial day"),
      T("trail10", "10-day line", "num", { dec: 2 }), T("trail20", "20-day line", "num", { dec: 2 }),
      T("trail_signal", "Trail signal", "setup"), T("sold_third_date", "Sold 1/3 of rest on")], qmTail),
    price: mariosLines,
    priceSub: "Buy point, stop, sell-part levels, and the 10 and 20-day lines",
    cards(all) {
      return qmCards(all) + card("Sell 1/3 today", String(countWhere(all, (r) => r.trail_signal === "SELL 1/3")));
    },
    detail(row) {
      return '<div class="panel pad"><div class="ptitle">Why this name</div>' + whyLines(row ? [row] : []) + "</div>";
    },
  });

  // Episodic Pivot: a big jump on news, end-of-day only. Rows come from setups.scan_episodic_pivot.
  const epStatus = ["EP TODAY", "BROKEN OUT today", "IN TRADE", "WATCHING"];
  function epLines(row) {
    const lines = [];
    if (!row) return lines;
    if (D.num(row.pivot) != null) lines.push({ value: D.num(row.pivot), color: "#F59E0B", label: "Buy above " + D.fmt(row.pivot, 2) });
    if (D.num(row.stop) != null) lines.push({ value: D.num(row.stop), color: "#EF4444", label: "Stop " + D.fmt(row.stop, 2) });
    if (D.num(row.trail) != null) lines.push({ value: D.num(row.trail), color: "#7C9CFF", label: "Trail " + (row.trail_with || "") + " " + D.fmt(row.trail, 2) });
    return lines;
  }
  function epFacts(row) {
    if (!row) return "";
    const facts = [
      ["EP day", row.ep_date], ["Why it counts", row.ep_trigger], ["Catalyst", row.catalyst_tag],
      ["Results timing", row.report_timing], ["Catalyst score (0 to 4)", row.catalyst_score],
      ["Base grade", row.neglect_grade], ["Market cap Rs Cr", D.isBlank(row.market_cap_cr) ? "" : D.fmt(row.market_cap_cr, 0)],
      ["Share count from", row.mcap_source], ["Upper circuit", row.circuit_flag],
      ["Nifty 50 trend", row.nifty_trend], ["3 months vs Nifty 50, points", D.isBlank(row.rs_63d_vs_nifty) ? "" : D.fmt(row.rs_63d_vs_nifty, 1)],
    ].filter((f) => !D.isBlank(f[1]));
    const items = facts.map((f) => '<div class="why"><span class="m2">' + D.esc(f[0]) + "</span><span>" + D.esc(f[1]) + "</span></div>").join("");
    const link = /^https:\/\/www\.(nseindia|bseindia)\.com\//.test(String(row.news_link || "")) ?
      '<p class="cap"><a href="' + D.esc(row.news_link) + '" target="_blank" rel="noopener">Company announcements and news</a></p>' : "";
    return '<div class="panel pad"><div class="ptitle">EP facts</div>' + items +
      '<p class="cap">' + D.esc(row.manual_check || "") + "</p>" + link + "</div>";
  }
  const episodic = patternPage({
    file: "scanner_episodic_pivot.csv",
    caption: "",
    filters: { status: true, statusDefault: epStatus, index: true, sector: true, ticker: true,
      single: [{ key: "stop_check", label: "Stop check" }, { key: "signal", label: "Signal" },
        { key: "neglect_grade", label: "Base grade" }, { key: "catalyst_tag", label: "Catalyst" }] },
    columns: [TK, CO, T("status", "Status", "setup"), PR,
      T("pivot", "Buy above", "num", { dec: 2 }), T("stop", "Stop", "num", { dec: 2, tone: "stop" }),
      T("risk_pct", "Risk %", "pct", { dec: 1, color: false }), T("stop_check", "Stop check", "setup"),
      T("signal", "Signal", "setup"), T("strength", "Strength", "strengthbar"),
      T("ep_date", "EP day"), T("days_since_ep", "Days since EP", "num", { dec: 0 }), T("ep_trigger", "Why it counts"),
      T("gap_pct", "Gap %", "pct", { dec: 1 }), T("change_pct", "Day move %", "pct", { dec: 1 }),
      T("rvol", "Volume vs 50-day", "volx", { dec: 1 }), T("dcr_pct", "Close in day range %", "num", { dec: 0 }),
      T("neglect_grade", "Base grade"), T("ret_63d_prior", "3 months before %", "pct", { dec: 1 }),
      T("first_ep_6m", "First EP in 6 months", "flag"),
      T("catalyst_tag", "Catalyst"), T("surprise_pct", "EPS beat %", "pct", { dec: 1 }),
      T("catalyst_score", "Catalyst score", "num", { dec: 0 }),
      T("market_cap_cr", "Market cap Rs Cr", "num", { dec: 0 }), T("small_young", "Under Rs 88,000 Cr", "flag"),
      T("circuit_flag", "Upper circuit"), T("adr_pct", "ADR %", "pct", { dec: 2, color: false }),
      T("risk_vs_adr", "Risk in ADRs", "num", { dec: 2 }),
      T("entry", "Entry (fill)", "num", { dec: 2 }), T("entry_date", "Bought on"),
      T("days_in_trade", "Days in trade", "num", { dec: 0 }), T("partial_window", "Sell 1/3 to 1/2"),
      T("trail_with", "Trail with"), T("trail", "Trail line", "num", { dec: 2 }),
      T("result_pct", "Result %", "pct", { dec: 1 }), T("exit_date", "Closed on"), T("exit_reason", "Closed because"),
      T("freshness", "Data", "fresh")],
    price: epLines,
    priceSub: "Buy level, stop, and trail line",
    cards(all) {
      return card("EP today", String(countWhere(all, (r) => r.status === "EP TODAY")),
        String(countWhere(all, (r) => r.status === "EP FADED")) + " faded") +
        card("Broken out today", String(countWhere(all, (r) => r.status === "BROKEN OUT today"))) +
        card("In a trade", String(countWhere(all, (r) => r.status === "IN TRADE")),
          String(countWhere(all, (r) => r.signal === "SELL PART")) + " sell part") +
        card("Watching, day 2 to 5", String(countWhere(all, (r) => r.status === "WATCHING"))) +
        card("Delayed watch", String(countWhere(all, (r) => r.status === "DELAYED WATCH"))) +
        card("Closed", String(countWhere(all, (r) => r.status === "CLOSED")));
    },
    detail(row) {
      return '<div class="panel pad"><div class="ptitle">Why this name</div>' + whyLines(row ? [row] : []) + "</div>" + epFacts(row);
    },
  });

  const leaders = patternPage({
    file: "scanner_leaders.csv",
    caption: "Leaders is the overlap of a ready or just-broken VCP and a strict CANSLIM qualify. A name on only one of those still appears.",
    filters: { status: true, statusDefault: readyDefault, ticker: true, single: [{ key: "on_vcp", label: "On VCP" }, { key: "on_canslim", label: "On CANSLIM" }] },
    columns: [TK, T("index_membership", "Index"), T("status", "Status", "setup"),
      T("on_vcp", "VCP", "flag", { width: "60px" }), T("on_canslim", "CANSLIM", "flag", { width: "60px" }),
      T("vcp_status", "VCP status", "setup"), T("canslim_status", "CANSLIM status", "setup"),
      T("pivot", "Buy point", "num", { dec: 2 }), T("stop", "Stop", "num", { dec: 2, tone: "stop" }),
      T("target", "Target", "num", { dec: 2, tone: "target" }), T("strength", "Strength", "strengthbar"), T("freshness", "Data", "fresh")],
    price: setupLines,
    cards(all) {
      return card("On both scans", String(countWhere(all, (r) => r.on_vcp === "yes" && r.on_canslim === "yes"))) +
        card("VCP only", String(countWhere(all, (r) => r.on_vcp === "yes" && r.on_canslim === "no"))) +
        card("CANSLIM only", String(countWhere(all, (r) => r.on_vcp === "no" && r.on_canslim === "yes"))) +
        card("Ready", String(countWhere(all, (r) => r.status === "READY")));
    },
    detail(row) {
      return '<div class="panel pad"><div class="ptitle">Why this name</div>' + whyLines(row ? [row] : []) + "</div>";
    },
  });

  function renderCalendar(ctx) {
    const raw = ctx.files["earnings_calendar.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div><div class="panel" id="tbl"></div>' +
      '<p class="cap">The one-day move is the next session after a report that hit at or after 4pm Eastern, otherwise the session of the report. The average is the last eight reports.</p>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.pairHtml("min", "max", "Days away 0–14", 0, 14) +
      D.selectHtml("owns", "Holdings only", ["yes", "no"], "") +
      D.searchHtml("ticker", "Ticker", "cal-tk", D.uniq(all, "ticker"));
    const windowRows = () => all.filter((r) => {
      const d = D.num(r.days_away);
      const lo = Number(D.fieldVal(box, "min"));
      const hi = Number(D.fieldVal(box, "max"));
      if (d == null || d < lo || d > hi) return false;
      const owns = D.fieldVal(box, "owns");
      if (owns && r.owns !== owns) return false;
      if (!D.matchText(r, "ticker", D.fieldVal(box, "ticker"))) return false;
      return true;
    });
    const state = { sort: "days_away", dir: "asc", sort2: "ticker", dir2: "asc", page: 0 };
    const draw = () => {
      const rows = windowRows();
      document.getElementById("cards").innerHTML =
        card("Reporting in the window", String(rows.length)) +
        card("Of those, Nick's holdings", String(countWhere(rows, (r) => r.owns === "yes"))) +
        card("After the close", String(countWhere(rows, (r) => r.when_hint === "after close")));
      D.drawTable(document.getElementById("tbl"), {
        rows: rows,
        columns: [TK, CO, T("next_earnings", "Report date", "shortdate"), T("when_hint", "When"), T("days_away", "Days away", "num", { dec: 0 }),
          T("last_eps_actual", "Last EPS", "num", { dec: 2 }), T("last_eps_estimate", "Last estimate", "num", { dec: 2 }),
          T("last_surprise_pct", "Last surprise %", "pct", { dec: 1, color: true }), T("last_1d_move_pct", "Last next-day move %", "pct", { dec: 1, color: true }),
          T("avg_1d_move_pct", "Avg next-day move %", "pct", { dec: 1, color: true }), T("n_past", "Reports on file", "num", { dec: 0 }),
          T("owns", "Held", "owns")],
        state: state, pageSize: 25,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function yq(date) {
    const m = /^(\d{4})-(\d{2})/.exec(date || "");
    if (!m) return date || "";
    return m[1] + " Q" + (Math.floor((Number(m[2]) - 1) / 3) + 1);
  }
  function renderHeat(ctx) {
    const raw = ctx.files["earnings_heatmap.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Green = EPS beat, red = miss, grey = in line. Revenue is n/a in this free feed, so a double beat cannot be shown.</p>' +
      '<div class="split r21"><div class="panel" id="pivot"></div><div class="panel" id="detail"></div></div>';
    const quartersAll = Array.from(new Set(all.map((r) => yq(r.quarter)))).sort();
    const filledQ = quartersAll.filter((qtr) => all.some((r) => yq(r.quarter) === qtr && !D.isBlank(r.eps_flag)));
    const last6 = (filledQ.length ? filledQ : quartersAll).slice(-6);
    const q0 = /^(\d{4}) Q(\d)/.exec(last6[0] || "");
    let fromDefault = q0 ? q0[1] + "-" + String((Number(q0[2]) - 1) * 3 + 1).padStart(2, "0") + "-01" : "";
    if (!fromDefault || fromDefault < "2025-10-01") fromDefault = "2025-10-01";
    const end = maxDate(all, "quarter");
    const box = document.getElementById("ctrls");
    box.innerHTML = D.dateHtml("from", "From", fromDefault) + D.dateHtml("to", "To", end) +
      D.selectHtml("eps", "EPS result", ["beat", "miss", "inline"], "") +
      D.searchHtml("ticker", "Ticker", "hm-tk", D.uniq(all, "ticker"));
    const state = { page: 0 };
    const draw = () => {
      const from = D.fieldVal(box, "from");
      const to = D.fieldVal(box, "to");
      const eps = D.fieldVal(box, "eps");
      const q = (D.fieldVal(box, "ticker") || "").trim().toLowerCase();
      const rows = all.filter((r) => (!from || r.quarter >= from) && (!to || r.quarter <= to) &&
        (!eps || r.eps_flag === eps) && (!q || r.ticker.toLowerCase().indexOf(q) >= 0));
      const quarters = Array.from(new Set(rows.map((r) => yq(r.quarter)))).sort()
        .filter((qtr) => rows.some((r) => yq(r.quarter) === qtr && !D.isBlank(r.eps_flag)));
      const by = {};
      rows.forEach((r) => { by[r.ticker + "|" + yq(r.quarter)] = r; });
      const tickers = Array.from(new Set(rows.map((r) => r.ticker))).sort();
      const pageSize = 20;
      const pages = Math.max(1, Math.ceil(tickers.length / pageSize));
      if (state.page >= pages) state.page = 0;
      const slice = tickers.slice(state.page * pageSize, state.page * pageSize + pageSize);
      const head = "<th>Ticker</th>" + quarters.map((qtr) => '<th class="c">' + D.esc(qtr) + "</th>").join("");
      const body = slice.map((t) => "<tr><td>" + D.tickerHtml(t) + "</td>" + quarters.map((qtr) => {
        const r = by[t + "|" + qtr];
        if (!r) return '<td class="hm"><span>' + D.na() + "</span></td>";
        const flag = String(r.eps_flag || "").toLowerCase();
        const fill = flag === "beat" ? "#14532D" : flag === "miss" ? "#7F1D1D" : flag === "inline" ? "#283146" : "";
        if (!fill) return '<td class="hm"><span>' + D.na() + "</span></td>";
        return '<td class="hm"><span style="background:' + fill + '">' + flag + "</span></td>";
      }).join("") + "</tr>").join("");
      document.getElementById("pivot").innerHTML = '<div class="scroll"><table><thead><tr>' + head + "</tr></thead><tbody>" + body +
        '</tbody></table></div><div class="foot"><span>' + (tickers.length ? state.page * pageSize + 1 : 0) + "–" +
        Math.min((state.page + 1) * pageSize, tickers.length) + " of " + tickers.length + " tickers</span>" +
        '<div class="pg"><button type="button" id="hp"' + (state.page <= 0 ? " disabled" : "") + '>‹</button><button type="button" id="hn"' +
        (state.page >= pages - 1 ? " disabled" : "") + ">›</button></div></div>";
      const prev = document.getElementById("hp");
      const next = document.getElementById("hn");
      if (prev) prev.onclick = () => { state.page -= 1; draw(); };
      if (next) next.onclick = () => { state.page += 1; draw(); };
      const detail = rows.slice().sort((a, b) => a.quarter < b.quarter ? 1 : -1);
      D.drawTable(document.getElementById("detail"), {
        title: "Quarter detail", rows: detail,
        columns: [TK, T("quarter", "Quarter", "date"), T("label", "Result", "earnlabel", { wrap: true })],
        state: { sort: "quarter", dir: "desc", page: 0 }, pageSize: 12,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderCards(ctx) {
    const raw = ctx.files["earnings_cards.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div><div class="panel" id="tbl"></div>' +
      '<p class="cap">Grades are a fixed rule on the last few earnings beats and revenue growth versus the company\'s own history. They are not a write-up from a person, and they are not a trade.</p>';
    document.getElementById("cards").innerHTML = "ABCDF".split("").map((g) =>
      card("Grade " + g, String(countWhere(all, (r) => r.grade === g)))).join("");
    const src = (all[0] && all[0].sources) || "Yahoo Finance earnings dates. Revenue vs estimate is not in that free feed, so revenue is left blank.";
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("grade", "Grade", ["A", "B", "C", "D", "F"]) + D.searchHtml("ticker", "Ticker", "gc", D.uniq(all, "ticker"));
    const state = { sort: "grade", dir: "asc", sort2: "ticker", dir2: "asc", page: 0 };
    const draw = () => D.drawTable(document.getElementById("tbl"), {
      rows: all.filter((r) => D.matchMulti(r, "grade", D.selectedMulti(box, "grade")) && D.matchText(r, "ticker", D.fieldVal(box, "ticker"))),
      columns: [TK, CO, T("grade", "Grade", "grade"), T("summary", "Summary", "text", { wrap: true })],
      state: state, pageSize: 25,
    });
    hook(box, state, draw);
    draw();
    const cap = document.createElement("p");
    cap.className = "cap";
    cap.textContent = src;
    ctx.page.appendChild(cap);
  }

  function latestBox(bits, zone) {
    return '<div class="split r21"><div class="panel pad"><div class="ptitle">Latest</div><div class="mini">' + bits + "</div></div>" +
      '<div class="panel pad"><div class="ptitle">Today\'s zone</div><div style="margin-top:12px">' + D.zoneHtml(zone) + "</div></div></div>";
  }
  function renderPutCall(ctx) {
    const raw = (ctx.files["put_call.csv"] || []).filter((r) => r.name === "EQUITY PUT/CALL RATIO" && r.data_status !== "MISSING");
    const end = maxDate(raw, "date");
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><p class="cap">Market mood only. Not an option position.</p>' +
      '<div id="latest"></div><div class="panel pad"><div class="ptitle">Put/call and its 5-day average</div><div class="chart-box tall"><canvas id="pc"></canvas></div></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.dateHtml("from", "From", shift(end, -90)) + D.selectHtml("zone", "Zone", D.uniq(raw, "zone"), "");
    const latest = raw.slice().sort((a, b) => a.date < b.date ? 1 : -1)[0] || {};
    document.getElementById("latest").innerHTML = latestBox(
      '<div><div class="l">Date</div><div class="v">' + D.esc(latest.date || "–") + "</div></div>" +
      '<div><div class="l">Ratio</div><div class="v">' + (D.num(latest.value) == null ? D.na() : D.esc(D.fmt(latest.value, 3))) + "</div></div>" +
      '<div><div class="l">5-day avg</div><div class="v">' + (D.num(latest.ma5) == null ? D.na() : D.esc(D.fmt(latest.ma5, 3))) + "</div></div>",
      latest.zone);
    const state = { sort: "date", dir: "desc", page: 0 };
    const draw = () => {
      const from = D.fieldVal(box, "from");
      const series = raw.filter((r) => !from || r.date >= from).sort((a, b) => a.date < b.date ? -1 : 1);
      const zone = D.fieldVal(box, "zone");
      D.destroyCharts();
      const fear = D.num((series[0] || {}).fear_line);
      const greed = D.num((series[0] || {}).greed_line);
      D.lineChart(document.getElementById("pc"), series.map((r) => r.date), [
        { label: "Put/call", data: D.seriesNum(series, "value"), color: "#7C9CFF", spanGaps: false },
        { label: "5-day avg", data: D.seriesNum(series, "ma5"), color: "#E6EBF5", spanGaps: true },
      ], {
        y: { suggestedMin: 0.3, suggestedMax: 1.1 },
        layout: { padding: { right: 24 } },
        plugins: { hlines: [{ value: fear, color: "#EF4444", label: "Fear" }, { value: greed, color: "#22C55E", label: "Greed" }] },
      });
      D.drawTable(document.getElementById("tbl"), {
        title: "Recent readings",
        rows: series.filter((r) => !zone || r.zone === zone),
        columns: [T("date", "Date", "date"), T("value", "Put/call", "num", { dec: 2 }), T("ma5", "5-day avg", "num", { dec: 3 }), T("zone", "Zone", "zone")],
        state: state, pageSize: 10,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderWalls(ctx) {
    const raw = D.realRows(ctx.files["option_walls.csv"]);
    const scores = D.realRows(ctx.files["scores.csv"] || []);
    const tickers = D.uniq(raw, "ticker");
    const start = tickers.indexOf("NVDA") >= 0 ? "NVDA" : (tickers[0] || "");
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Open interest by strike. Sentiment only. Not a contract to trade. Chains refresh once a day for the focus list, so most of the universe is not on this page.</p>' +
      '<div class="panel pad"><div class="ptitle" id="oititle">Open interest by strike</div><div class="legend"><span><i style="background:#22C55E"></i>Calls</span><span><i style="background:#EF4444;height:8px"></i>Puts</span></div><div class="chart-box tall"><canvas id="oi"></canvas></div></div><div class="split r21"><div class="panel" id="walls"></div><div class="panel pad" id="note"></div></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.searchHtml("ticker", "Ticker", "wtk", tickers) +
      '<label class="ctl"><span class="lab">Expiry</span><select data-filter="expiry"></select></label>' +
      D.selectHtml("band", "Strike range", [{ value: "near", label: "±25% of spot" }, { value: "all", label: "All strikes" }], "near", { all: false });
    box.querySelector("[data-filter=ticker]").value = start;
    const fillExpiry = () => {
      const t = (D.fieldVal(box, "ticker") || start).trim().toUpperCase();
      const rows = raw.filter((r) => r.ticker === t);
      const dates = D.uniq(rows, "expiry");
      const nearest = (rows.find((r) => r.nearest_expiry === "true") || {}).expiry || dates[0] || "";
      const sel = box.querySelector("[data-filter=expiry]");
      const prev = sel.value;
      sel.innerHTML = dates.map((d) => '<option value="' + D.esc(d) + '">' + D.esc(d) + (d === nearest ? " (nearest)" : "") + "</option>").join("");
      sel.value = dates.indexOf(prev) >= 0 ? prev : nearest;
    };
    const draw = () => {
      fillExpiry();
      const t = (D.fieldVal(box, "ticker") || start).trim().toUpperCase();
      const exp = D.fieldVal(box, "expiry");
      const spot = D.num((scores.find((r) => r.ticker === t) || {}).price);
      const near = D.fieldVal(box, "band") !== "all";
      let rows = raw.filter((r) => r.ticker === t && r.expiry === exp);
      if (near && spot != null) {
        rows = rows.filter((r) => {
          const s = D.num(r.strike);
          return s != null && s >= spot * 0.75 && s <= spot * 1.25;
        });
      }
      const strikes = D.uniq(rows, "strike");
      const call = strikes.map((s) => { const r = rows.find((x) => x.strike === s && x.side === "call"); return r ? D.num(r.open_interest) : 0; });
      const put = strikes.map((s) => { const r = rows.find((x) => x.strike === s && x.side === "put"); return r ? D.num(r.open_interest) : 0; });
      D.destroyCharts();
      const title = document.getElementById("oititle");
      if (title) title.textContent = "Open interest by strike, " + t + (exp ? " " + exp : "");
      D.barChart(document.getElementById("oi"), strikes, call, call.map(() => "#22C55E"), {
        label: "Calls",
        cat: { ticks: { color: "#8B96AD", autoSkip: false, maxRotation: 0, callback(v) {
          const label = this.getLabelForValue(v);
          const n = Number(label);
          return Number.isFinite(n) ? String(n).replace(/\.0$/, "") : label;
        } } },
      });
      const chart = (typeof Chart !== "undefined") ? Chart.getChart(document.getElementById("oi")) : null;
      if (chart) {
        chart.data.datasets.push({ label: "Puts", data: put, backgroundColor: "#EF4444", borderWidth: 0 });
        chart.update();
      }
      D.drawTable(document.getElementById("walls"), {
        title: "The walls: most open interest", rows: rows.filter((r) => r.is_wall === "yes"),
        columns: [T("side", "Side", "side"), T("strike", "Strike", "num", { dec: 2 }), T("open_interest", "Open interest", "num", { dec: 0 }), T("volume", "Volume today", "num", { dec: 0 })],
        state: { sort: "side", dir: "asc", page: 0 }, pageSize: 2, foot: false,
      });
      document.getElementById("note").innerHTML = '<div class="ptitle">Note</div><p class="cap">' + D.esc(D.noteOf(ctx.files["option_walls.csv"]) || "Open interest only, for the focus list, once a day. Not an option pick.") + "</p>";
    };
    D.wireFilters(box, draw);
    draw();
  }

  function renderAnalysts(ctx) {
    const raw = ctx.files["analyst_ratings.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div><div class="panel" id="tbl"></div>' +
      '<p class="cap">Targets are the median analyst target. Mean rating runs from 1 (strong buy) to 5 (sell). Upside is the target divided by price, minus one, in percent.</p>';
    const labels = { "2": "+2 points", "1": "+1 point", "0": "0 points" };
    document.getElementById("cards").innerHTML = ["2", "1", "0"].map((p) =>
      card(labels[p], String(countWhere(all, (r) => String(D.num(r.pts_analyst)) === p)))).join("");
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("pts", "Analyst points", D.uniq(all, "pts_analyst")) +
      D.rangeHtml("min", "Min. analysts", 0, 80, 0, 1) +
      D.searchHtml("ticker", "Ticker", "an-tk", D.uniq(all, "ticker"));
    const state = { sort: "pts_analyst", dir: "desc", sort2: "analyst_count", dir2: "desc", page: 0 };
    const draw = () => D.drawTable(document.getElementById("tbl"), {
      rows: all.filter((r) => D.matchMulti(r, "pts_analyst", D.selectedMulti(box, "pts")) &&
        D.matchMin(r, "analyst_count", D.fieldVal(box, "min")) && D.matchText(r, "ticker", D.fieldVal(box, "ticker"))),
      columns: [TK, CO, T("analyst_mean", "Mean rating (1 = strong buy)", "num", { dec: 2 }), T("analyst_count", "Analysts", "num", { dec: 0 }),
        T("pts_analyst", "Analyst points", "points"), T("target_analyst", "Median target", "num", { dec: 2 }), PR,
        T("upside_pct", "Upside %", "pct", { dec: 1, color: true })],
      state: state, pageSize: 25,
    });
    hook(box, state, draw);
    draw();
  }

  function render13f(ctx) {
    const raw = ctx.files["institutional_13f.csv"];
    const all = D.realRows(raw);
    const summary = all.filter((r) => !r.row_type || r.row_type === "summary");
    const buying = panelOff("feature.fii_shareholding_highlight") ? "" :
      '<div class="split top" style="margin-top:16px"><div class="panel" id="fiibuy"></div><div class="panel" id="diibuy"></div></div>';
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Promoter, foreign institutions (FII), Indian institutions (DII), and other public. The change is versus the prior quarter, in percentage points. A blank cell is not verified. This is not a buy or sell list.</p>' +
      '<div class="panel" id="sum"></div>' + buying;
    const box = document.getElementById("ctrls");
    box.innerHTML = D.searchHtml("ticker", "Ticker", "f-tk", D.uniq(summary, "ticker")) +
      D.multiHtml("pts", "Shareholding points", D.uniq(summary, "pts_institutional"));
    const s1 = { sort: "promoter_pct", dir: "desc", page: 0 };
    const draw = () => {
      const q = (D.fieldVal(box, "ticker") || "").trim();
      const pts = D.selectedMulti(box, "pts");
      const sums = summary.filter((r) => D.matchText(r, "ticker", q) && D.matchMulti(r, "pts_institutional", pts));
      D.drawTable(document.getElementById("sum"), {
        title: "Shareholding", rows: sums,
        columns: [TK, T("promoter_pct", "Promoter %", "num", { dec: 2 }), T("fii_pct", "FII %", "num", { dec: 2 }),
          T("dii_pct", "DII %", "num", { dec: 2 }), T("public_pct", "Other public %", "num", { dec: 2 }),
          T("promoter_chg", "Promoter chg", "num", { dec: 2 }), T("fii_chg", "FII chg", "num", { dec: 2 }),
          T("dii_chg", "DII chg", "num", { dec: 2 }),
          T("as_of", "As of", "date"), T("pts_institutional", "Points", "points")],
        state: s1, pageSize: 25,
      });
      if (!panelOff("feature.fii_shareholding_highlight")) {
        const fiiBuy = sums.filter((r) => (D.num(r.fii_chg) || 0) > 0).slice().sort((a, b) => (D.num(b.fii_chg) || 0) - (D.num(a.fii_chg) || 0)).slice(0, 15);
        const diiBuy = sums.filter((r) => (D.num(r.dii_chg) || 0) > 0).slice().sort((a, b) => (D.num(b.dii_chg) || 0) - (D.num(a.dii_chg) || 0)).slice(0, 15);
        const buyCols = [TK, T("fii_pct", "FII %", "num", { dec: 2 }), T("fii_chg", "FII chg, pts", "num", { dec: 2 })];
        const diiCols = [TK, T("dii_pct", "DII %", "num", { dec: 2 }), T("dii_chg", "DII chg, pts", "num", { dec: 2 })];
        D.drawTable(document.getElementById("fiibuy"), {
          title: "FII buying", sub: "Biggest rise in FII % versus the prior quarter",
          rows: fiiBuy, columns: buyCols, state: { sort: "fii_chg", dir: "desc", page: 0 }, pageSize: 15, foot: false,
          empty: "No quarter-over-quarter FII increase is on file yet.",
        });
        D.drawTable(document.getElementById("diibuy"), {
          title: "DII buying", sub: "Biggest rise in DII % versus the prior quarter",
          rows: diiBuy, columns: diiCols, state: { sort: "dii_chg", dir: "desc", page: 0 }, pageSize: 15, foot: false,
          empty: "No quarter-over-quarter DII increase is on file yet.",
        });
      }
    };
    hook(box, s1, draw);
    draw();
  }

  function renderAaii(ctx) {
    const raw = ctx.files["aaii_sentiment.csv"] || [];
    const row = raw[0] || {};
    const missing = !row.data_status || row.data_status === "MISSING";
    const vix = D.num(row.india_vix);
    const fii = D.num(row.fii_net_cr);
    const dii = D.num(row.dii_net_cr);
    const mt = (ctx.files["market_today.csv"] || [])[0] || {};
    ctx.page.innerHTML =
      trendStrip(mt) +
      '<div class="cards">' +
      card("India VIX", vix == null ? D.na() : D.esc(D.fmt(vix, 2)), D.esc(row.vix_zone || "zone not set")) +
      card("FII net, crore", fii == null ? D.na() : D.esc(D.fmt(fii, 0)), "cash market, one day") +
      card("DII net, crore", dii == null ? D.na() : D.esc(D.fmt(dii, 0)), "cash market, one day") +
      "</div>" +
      '<div class="panel pad w740 aaii"><div class="m2" style="font-size:11px">Status</div><div style="font-size:18px;font-weight:700;color:' + (missing ? "#F59E0B" : "#22C55E") + ';margin:8px 0">' +
      D.esc(row.data_status || "MISSING") + '</div><p style="font-size:13px">' + D.esc(row.note || "") + "</p>" +
      (row.as_of ? '<p class="cap">As of ' + D.esc(row.as_of) + "</p>" : "") +
      "</div>" +
      '<p style="margin-top:12px"><a class="linkish" href="put-call.html">Put and call open interest is the other free mood gauge ›</a></p>';
  }

  function renderInsiders(ctx) {
    const raw = ctx.files["insider_trading.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Buy and sell counts over three months, from the NSE insider (PIT) file, for the focus list. If the file is blocked, the cells stay blank.</p>' +
      '<div class="cards" id="cards"></div><div class="split r21 top"><div class="panel" id="tbl"></div>' +
      '<div class="panel pad"><div class="ptitle">Most insider buys, 3 months</div><div class="chart-box h300"><canvas id="ib"></canvas></div></div></div>';
    const labels = { "1": "Net buyers (+1)", "0": "Neutral (0)", "-1": "Net sellers (−1)" };
    document.getElementById("cards").innerHTML = ["1", "0", "-1"].map((p) =>
      card(labels[p], String(countWhere(all, (r) => String(D.num(r.pts_insider)) === p)))).join("");
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("pts", "Insider points", D.uniq(all, "pts_insider")) +
      D.rangeHtml("min", "Min. buys", 0, 50, 0, 1) +
      D.searchHtml("ticker", "Ticker", "in-tk", D.uniq(all, "ticker"));
    const state = { sort: "buys_3m", dir: "desc", page: 0 };
    const draw = () => {
      const rows = all.filter((r) => D.matchMulti(r, "pts_insider", D.selectedMulti(box, "pts")) &&
        D.matchMin(r, "buys_3m", D.fieldVal(box, "min")) && D.matchText(r, "ticker", D.fieldVal(box, "ticker")));
      D.drawTable(document.getElementById("tbl"), {
        rows: rows,
        columns: [TK, T("buys_3m", "Buys, 3 mo", "count", { up: "#22C55E" }), T("sells_3m", "Sells, 3 mo", "count", { up: "#EF4444" }), T("pts_insider", "Points", "points")],
        state: state, pageSize: 25,
      });
      const top = all.slice().sort((a, b) => (D.num(b.buys_3m) || 0) - (D.num(a.buys_3m) || 0)).slice(0, 10);
      D.destroyCharts();
      D.barChart(document.getElementById("ib"), top.map((r) => r.ticker), top.map((r) => D.num(r.buys_3m)), top.map(() => "#22C55E"), { horizontal: true, labels: true, dec: 0 });
    };
    hook(box, state, draw);
    draw();
  }

  function renderHeadlines(ctx) {
    const raw = ctx.files["headline_sentiment.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Tone is a word rule on the headline (beat, upgrade, probe, layoff, and similar). It is not added into the desk score.</p>' +
      '<div class="cards" id="cards"></div><div class="panel" id="tbl"></div>';
    document.getElementById("cards").innerHTML = [["1", "Positive"], ["0", "Neutral"], ["-1", "Negative"]].map((p) =>
      card(p[1], String(countWhere(all, (r) => String(D.num(r.tone)) === p[0])))).join("");
    const box = document.getElementById("ctrls");
    box.innerHTML = D.selectHtml("tone", "Tone", [{ value: "1", label: "Positive" }, { value: "0", label: "Neutral" }, { value: "-1", label: "Negative" }], "") +
      D.searchHtml("ticker", "Ticker", "hd-tk", D.uniq(all, "ticker")) +
      D.multiHtml("pub", "Publisher", D.uniq(all, "publisher"));
    const state = { sort: "published", dir: "desc", page: 0 };
    const draw = () => {
      const tone = D.fieldVal(box, "tone");
      D.drawTable(document.getElementById("tbl"), {
        rows: all.filter((r) => (!tone || String(D.num(r.tone)) === tone) &&
          D.matchMulti(r, "publisher", D.selectedMulti(box, "pub")) && D.matchText(r, "ticker", D.fieldVal(box, "ticker"))),
        columns: [TK, T("tone", "Tone", "tone"), T("headline", "Headline", "text", { wrap: true }), T("publisher", "Source"),
          T("published", "Published"), T("tone_note", "Why this tone", "muted", { width: "200px" })],
        state: state, pageSize: 20,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderXly(ctx) {
    const raw = D.realRows(ctx.files["xly_xlp.csv"]);
    const end = maxDate(raw, "date");
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Nifty Auto divided by Nifty FMCG. Above the 50-day average of the ratio is labeled risk on. The columns keep the old names so the file stays stable.</p>' +
      '<div id="latest"></div><div class="panel pad"><div class="ptitle">Auto / FMCG ratio and its 50-day average</div><div class="chart-box tall"><canvas id="xx"></canvas></div></div><div class="panel" id="tbl"></div>';
    const latest = raw.slice().sort((a, b) => a.date < b.date ? 1 : -1)[0] || {};
    document.getElementById("latest").innerHTML = latestBox(
      '<div><div class="l">Date</div><div class="v">' + D.esc(latest.date || "–") + "</div></div>" +
      '<div><div class="l">Ratio</div><div class="v">' + (D.num(latest.ratio) == null ? D.na() : D.esc(D.fmt(latest.ratio, 3))) + "</div></div>" +
      '<div><div class="l">50-day avg</div><div class="v">' + (D.num(latest.ratio_sma50) == null ? D.na() : D.esc(D.fmt(latest.ratio_sma50, 3))) + "</div></div>",
      latest.zone);
    const box = document.getElementById("ctrls");
    box.innerHTML = D.dateHtml("from", "From", shift(end, -182)) + D.selectHtml("zone", "Zone", D.uniq(raw, "zone"), "");
    const state = { sort: "date", dir: "desc", page: 0 };
    const draw = () => {
      const from = D.fieldVal(box, "from");
      const series = raw.filter((r) => !from || r.date >= from).sort((a, b) => a.date < b.date ? -1 : 1);
      const zone = D.fieldVal(box, "zone");
      D.destroyCharts();
      D.lineChart(document.getElementById("xx"), series.map((r) => r.date), [
        { label: "Auto / FMCG", data: D.seriesNum(series, "ratio"), color: "#7C9CFF", spanGaps: true },
        { label: "50-day avg", data: D.seriesNum(series, "ratio_sma50"), color: "#8B96AD", spanGaps: true },
      ], {});
      D.drawTable(document.getElementById("tbl"), {
        title: "Recent days",
        rows: series.filter((r) => !zone || r.zone === zone),
        columns: [T("date", "Date", "date"), T("xly", "Auto", "num", { dec: 2 }), T("xlp", "FMCG", "num", { dec: 2 }),
          T("ratio", "Ratio", "num", { dec: 3 }), T("ratio_sma50", "50-day avg", "num", { dec: 3 }), T("zone", "Zone", "zone")],
        state: state, pageSize: 10,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderFinancials(ctx) {
    const raw = ctx.files["financials_summary.csv"];
    const all = D.realRows(raw);
    const tickers = D.uniq(all, "ticker");
    const start = tickers.indexOf("ADSK") >= 0 ? "ADSK" : (tickers[0] || "");
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="panel pad" id="who"></div><div class="panel" id="tbl"></div>' +
      '<p class="cap">Direction says whether a lower or a higher number earns the point. The sector median needs four peers.</p>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.searchHtml("ticker", "Ticker", "fn-tk", tickers) + D.multiHtml("metric", "Metric", D.uniq(all, "metric"));
    box.querySelector("[data-filter=ticker]").value = start;
    const state = { sort: "metric", dir: "asc", page: 0 };
    const draw = () => {
      const t = (D.fieldVal(box, "ticker") || start).trim().toUpperCase();
      const rows = all.filter((r) => r.ticker === t && D.matchMulti(r, "metric", D.selectedMulti(box, "metric")));
      const one = rows[0] || all.find((r) => r.ticker === t) || {};
      document.getElementById("who").innerHTML = '<div style="font-size:24px;font-weight:700"><a class="tk" href="scorecard.html?t=' +
        encodeURIComponent(t) + '">' + D.esc(t) + '</a></div><div class="m2" style="font-size:13px;margin-top:4px">' + D.esc(one.sector || "") + "</div>";
      D.drawTable(document.getElementById("tbl"), {
        rows: rows,
        columns: [T("metric", "Metric"), T("direction", "Better when"), T("now_value", "Now", "num", { dec: 2 }),
          T("avg_3y", "Own 3-yr avg", "num", { dec: 2 }), T("pts_vs_self", "Points vs own history", "ownpts"),
          T("industry_median", "Sector median", "num", { dec: 2 }), T("pts_vs_industry", "Points vs sector", "points")],
        state: state, pageSize: 12, foot: false,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderTracker(ctx) {
    const raw = ctx.files["earnings_tracker.csv"];
    const all = D.realRows(raw);
    const end = maxDate(all, "earnings_date");
    const tickers = D.uniq(all, "ticker");
    const start = tickers.indexOf("ADSK") >= 0 ? "ADSK" : (tickers[0] || "");
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="split r21">' +
      '<div class="panel pad"><div class="ptitle">EPS surprise %, last 8 reports</div>' + D.companyLineHtml("su-line") + '<div class="chart-box"><canvas id="su"></canvas></div></div>' +
      '<div class="cards col" id="cards"></div></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    let upcoming = false;
    box.innerHTML = D.dateHtml("from", "From", shift(end, -365 * 3)) + D.dateHtml("to", "To", end) +
      D.searchHtml("ticker", "Ticker", "tr-tk", tickers) +
      '<button type="button" class="dd" id="upbtn">Show upcoming</button>';
    box.querySelector("[data-filter=ticker]").value = start;
    const state = { sort: "earnings_date", dir: "desc", page: 0 };
    const draw = () => {
      const from = D.fieldVal(box, "from");
      const to = D.fieldVal(box, "to");
      const q = (D.fieldVal(box, "ticker") || start).trim().toUpperCase();
      const rows = all.filter((r) => r.ticker === q && (!from || r.earnings_date >= from) && (!to || r.earnings_date <= to) &&
        (upcoming || !D.isBlank(r.eps_actual)));
      document.getElementById("cards").innerHTML =
        card("Beats", String(countWhere(rows, (r) => r.result === "beat"))) +
        card("Misses", String(countWhere(rows, (r) => r.result === "miss"))) +
        card("Upcoming (no actual yet)", String(countWhere(all, (r) => r.ticker === q && D.isBlank(r.eps_actual))));
      const chartRows = all.filter((r) => r.ticker === q && D.num(r.surprise_pct) != null)
        .sort((a, b) => a.earnings_date < b.earnings_date ? -1 : 1).slice(-8);
      D.fillCompanyLine(document.getElementById("su-line"), q);
      D.destroyCharts();
      const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      D.barChart(document.getElementById("su"), chartRows.map((r) => {
        const m = /^(\d{4})-(\d{2})/.exec(r.earnings_date || "");
        return m ? mon[Number(m[2]) - 1] + " " + m[1].slice(2) : r.earnings_date;
      }), chartRows.map((r) => D.num(r.surprise_pct)),
      chartRows.map((r) => (D.num(r.surprise_pct) || 0) >= 0 ? "#22C55E" : "#EF4444"),
      { labels: true, dec: 1, suffix: "%" });
      D.drawTable(document.getElementById("tbl"), {
        rows: rows,
        columns: [TK, T("earnings_date", "Report date", "date"), T("eps_estimate", "EPS estimate", "num", { dec: 2 }),
          T("eps_actual", "EPS actual", "num", { dec: 2 }), T("surprise_pct", "Surprise %", "pct", { dec: 1, color: true }), T("result", "Result", "result")],
        state: state, pageSize: 12,
      });
    };
    box.querySelector("#upbtn").addEventListener("click", () => {
      upcoming = !upcoming;
      box.querySelector("#upbtn").textContent = upcoming ? "Hide upcoming" : "Show upcoming";
      state.page = 0;
      draw();
    });
    hook(box, state, draw);
    draw();
  }

  function fyLabel(v) {
    const m = /^(\d{4})/.exec(String(v || ""));
    return m ? "FY" + m[1].slice(2) : "";
  }
  function renderCompany(ctx) {
    const raw = ctx.files["company_financials.csv"];
    const all = D.realRows(raw);
    const tickers = D.uniq(all, "ticker");
    const start = tickers.indexOf("ADSK") >= 0 ? "ADSK" : (tickers[0] || "");
    const end = maxDate(all, "fy_end");
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Annual figures from SEC filings. Margins are blank when the filing did not include that line.</p>' +
      D.companyLineHtml("co-line") + '<div class="split"><div class="panel pad"><div class="ptitle">Revenue and net income</div><div class="chart-box"><canvas id="rev"></canvas></div><p class="cap" id="nicap"></p></div>' +
      '<div class="panel pad"><div class="ptitle">Margins</div><div class="chart-box"><canvas id="mg"></canvas></div></div></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.searchHtml("ticker", "Ticker", "co-tk", tickers) +
      D.selectHtml("years", "Years", [{ value: "5", label: "Last 5 years" }, { value: "10", label: "Last 10 years" }], "10", { all: false });
    box.querySelector("[data-filter=ticker]").value = start;
    const state = { sort: "fy_end", dir: "desc", page: 0 };
    const moneyTick = (v) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return v;
      const body = D.compact(Math.abs(n));
      return (n < 0 ? "-₹" : "₹") + String(body || "").replace(/^-/, "");
    };
    const draw = () => {
      const t = (D.fieldVal(box, "ticker") || start).trim().toUpperCase();
      const nYears = Number(D.fieldVal(box, "years") || 10);
      const mine = all.filter((r) => r.ticker === t).sort((a, b) => a.fy_end < b.fy_end ? -1 : 1);
      const rows = mine.slice(-nYears);
      const labels = rows.map((r) => fyLabel(r.fy_end));
      const missingNi = rows.some((r) => D.num(r.revenue) != null && D.num(r.net_income) == null);
      D.fillCompanyLine(document.getElementById("co-line"), t);
      const note = document.getElementById("nicap");
      if (note) note.textContent = missingNi ? "Net income not parsed for these years." : "";
      D.destroyCharts();
      D.makeChart(document.getElementById("rev"), {
        type: "bar",
        data: { labels: labels, datasets: [
          { label: "Revenue", data: D.seriesNum(rows, "revenue"), backgroundColor: "#7C9CFF" },
          { label: "Net income", data: D.seriesNum(rows, "net_income"), backgroundColor: "#8B96AD" },
        ] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: "#8B96AD", boxWidth: 12 } }, barLabels: { level: true, money: true, dec: 1 } },
          scales: {
            x: { ticks: { color: "#8B96AD", maxRotation: 0, autoSkip: false }, grid: { display: false } },
            y: { ticks: { color: "#8B96AD", callback: moneyTick }, grid: { color: "#1E293B" } },
          },
        },
      });
      D.lineChart(document.getElementById("mg"), labels, [
        { label: "Gross margin", data: D.seriesNum(rows, "gross_margin"), color: "#E6EBF5", spanGaps: false },
        { label: "Operating margin", data: D.seriesNum(rows, "operating_margin"), color: "#7C9CFF", spanGaps: false },
        { label: "Net margin", data: D.seriesNum(rows, "net_margin"), color: "#8B96AD", spanGaps: false },
      ], { x: { ticks: { autoSkip: false, maxRotation: 0, color: "#8B96AD" } }, plugins: { barLabels: { level: true, suffix: "%", dec: 1 } } });
      D.drawTable(document.getElementById("tbl"), {
        rows: rows,
        columns: [T("fy_end", "Fiscal year", "fy"), T("revenue", "Revenue", "compact"), T("gross_profit", "Gross profit", "compact"),
          T("op_income", "Operating income", "compact"), T("net_income", "Net income", "compact"), T("eps", "EPS", "num", { dec: 2 }),
          T("gross_margin", "Gross margin %", "pct", { dec: 1, color: false }), T("operating_margin", "Operating margin %", "pct", { dec: 1, color: false }),
          T("net_margin", "Net margin %", "pct", { dec: 1, color: false }), T("pe", "P/E", "multiple", { dec: 1 }), T("ps", "P/S", "num", { dec: 2 }),
          T("pfcf", "P/FCF", "multiple", { dec: 1 })],
        state: state, pageSize: 12,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderDivFund(ctx) {
    const raw = ctx.files["dividend_scanner.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div><div class="panel" id="tbl"></div>' +
      '<p class="cap">A yield of 0 is real: the company does not pay. A dash means the yield could not be read. The Data updates page shows how many are unknown.</p>';
    const payers = all.filter((r) => (D.num(r.div_yield) || 0) > 0);
    document.getElementById("cards").innerHTML =
      card("Pay a dividend", String(payers.length)) +
      card("Pay none (yield 0)", String(countWhere(all, (r) => D.num(r.div_yield) === 0))) +
      card("Yield unknown", String(countWhere(all, (r) => D.num(r.div_yield) == null))) +
      card("Average yield of payers", ntext(avg(payers, "div_yield"), 2));
    const box = document.getElementById("ctrls");
    standardFilters(box, all, { sector: true, verdict: true, ticker: true, order: ["pays", "sector", "verdict", "ticker"] });
    box.insertAdjacentHTML("afterbegin", D.selectHtml("pays", "Pays a dividend", ["yes", "no"], ""));
    const state = { sort: "div_yield", dir: "desc", page: 0 };
    const draw = () => {
      const pays = D.fieldVal(box, "pays");
      D.drawTable(document.getElementById("tbl"), {
        rows: all.filter((r) => {
          if (!readCommon(box, r)) return false;
          const y = D.num(r.div_yield);
          if (pays === "yes" && !(y > 0)) return false;
          if (pays === "no" && y !== 0) return false;
          return true;
        }),
        columns: [TK, CO, SE, PR, T("div_yield", "Yield %", "pct", { color: false }), T("div_yield_avg", "Own avg yield %", "pct", { color: false }),
          T("dps", "Dividend per share", "num", { dec: 2 }), T("pts_div_yield", "Points", "points"), VE],
        state: state, pageSize: 25,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderMacro(ctx) {
    const raw = ctx.files["macro_screener.csv"];
    const all = D.realRows(raw);
    const mt = (ctx.files["market_today.csv"] || [])[0] || {};
    ctx.page.innerHTML = trendStrip(mt) + '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Signal is +1 when the surprise is in the direction that usually helps stocks (for unemployment and jobless claims, lower is the helpful direction). It is a label, not a forecast.</p>' +
      '<div class="cards" id="cards"></div><div class="panel" id="tbl"></div>';
    document.getElementById("cards").innerHTML =
      card("Helpful surprises (+1)", String(countWhere(all, (r) => String(D.num(r.signal)) === "1"))) +
      card("Neutral (0)", String(countWhere(all, (r) => String(D.num(r.signal)) === "0"))) +
      card("Unhelpful (−1)", String(countWhere(all, (r) => String(D.num(r.signal)) === "-1")));
    const countline = all.length + " releases in the last 14 days";
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("cat", "Category", D.uniq(all, "category")) +
      D.multiHtml("ind", "Indicator", D.uniq(all, "indicator")) +
      D.multiHtml("sig", "Signal", D.uniq(all, "signal"));
    const state = { sort: "date", dir: "desc", page: 0 };
    const draw = () => D.drawTable(document.getElementById("tbl"), {
      title: "Releases", sub: countline,
      rows: all.filter((r) => D.matchMulti(r, "category", D.selectedMulti(box, "cat")) &&
        D.matchMulti(r, "indicator", D.selectedMulti(box, "ind")) && D.matchMulti(r, "signal", D.selectedMulti(box, "sig"))),
      columns: [T("date", "Date", "date"), T("category", "Category"), T("indicator", "Indicator", "text", { wrap: true }),
        T("actual", "Actual"), T("forecast", "Forecast"), T("surprise", "Surprise", "surprise"), T("signal", "Signal", "tone")],
      state: state, pageSize: 25,
      empty: all.length ? "No rows match." : "No releases on file.",
    });
    hook(box, state, draw);
    draw();
  }

  function renderSecMacro(ctx) {
    const macro = D.realRows(ctx.files["sector_macro.csv"]);
    const sectors = D.realRows(ctx.files["sectors.csv"]);
    const plain = (macro[0] && macro[0].plain_english) || "Rule of thumb from the latest surprises. It is not a forecast.";
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><p class="cap">' + D.esc(plain) +
      " Weights are fixed in the job (for example, hotter inflation helps energy and hurts growth sectors).</p>" +
      '<div class="split sm"><div class="panel" id="mac"></div><div class="panel" id="px"></div></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("score", "Macro score", D.uniq(macro, "macro_score")) +
      D.multiHtml("etf", "Sector ETF", D.uniq(macro, "ticker"));
    const draw = () => {
      const etf = D.selectedMulti(box, "etf");
      const score = D.selectedMulti(box, "score");
      D.drawTable(document.getElementById("mac"), {
        title: "Macro scores", rows: macro.filter((r) => D.matchMulti(r, "ticker", etf) && D.matchMulti(r, "macro_score", score)),
        columns: [T("ticker", "ETF", "etf"), T("name", "Sector"), T("macro_growth", "Growth", "points"),
          T("macro_inflation", "Inflation", "points"), T("macro_jobs", "Rates", "points"), T("macro_score", "Total", "points")],
        state: { sort: "macro_score", dir: "desc", page: 0 }, pageSize: 25, foot: false,
      });
      D.drawTable(document.getElementById("px"), {
        title: "Price change (sorted by YTD)", rows: sectors.filter((r) => D.matchMulti(r, "ticker", etf)),
        columns: [T("ticker", "ETF", "etf"), T("day_pct", "Day %", "pct", { color: true }), T("week_pct", "Week %", "pct", { color: true }),
          T("month_pct", "Month %", "pct", { color: true }), T("ytd_pct", "YTD %", "pct", { color: true })],
        state: { sort: "ytd_pct", dir: "desc", page: 0 }, pageSize: 25, foot: false,
      });
    };
    hook(box, { page: 0 }, draw);
    draw();
  }

  function renderHist(ctx) {
    const raw = ctx.files["historical_pe.csv"] || [];
    const all = D.realRows(raw);
    const end = maxDate(all, "date");
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Median trailing P/E of the stocks on this desk. There is no free official Nifty 50 P/E series, so that line is not drawn.</p>' +
      '<div class="panel pad"><div class="ptitle">Desk median trailing P/E</div><div class="chart-box tall"><canvas id="pe"></canvas></div></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.dateHtml("from", "From", shift(end, -1825));
    const state = { sort: "date", dir: "desc", page: 0 };
    const draw = () => {
      const from = D.fieldVal(box, "from");
      const rows = all.filter((r) => !from || r.date >= from).sort((a, b) => a.date < b.date ? -1 : 1);
      D.destroyCharts();
      D.lineChart(document.getElementById("pe"), rows.map((r) => r.date), [
        { label: "Desk median trailing P/E", data: D.seriesNum(rows, "desk_median_trailing_pe"), color: "#7C9CFF", spanGaps: true },
      ], { legend: false });
      D.drawTable(document.getElementById("tbl"), {
        rows: rows, columns: [T("date", "Month end", "date"), T("desk_median_trailing_pe", "Median P/E", "num", { dec: 1 }),
          T("n", "Stocks in the median", "num", { dec: 0 })],
        state: state, pageSize: 12,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderBreakouts(ctx) {
    const raw = ctx.files["breakouts.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div><div class="panel" id="tbl"></div>' +
      '<p class="cap">Within 1% of the 52-week closing high. If the list is empty, nobody is near a high today: that is a result, and the note above says so.</p>';
    document.getElementById("cards").innerHTML =
      card("Near a 52-week high", String(all.length)) +
      card("With volume above average", String(countWhere(all, (r) => (D.num(r.volume_ratio) || 0) >= 1))) +
      card("Of those, BUY", String(countWhere(all, (r) => r.verdict === "BUY")));
    const box = document.getElementById("ctrls");
    standardFilters(box, all, { sector: true, verdict: true, ticker: true });
    const state = { sort: "dist_52w_high_pct", dir: "asc", page: 0 };
    const draw = () => D.drawTable(document.getElementById("tbl"), {
      rows: all.filter((r) => readCommon(box, r)),
      columns: [TK, CO, SE, PR, T("dist_52w_high_pct", "From 52-week high %", "pct", { dec: 2, color: false, abs: true }),
        T("volume_ratio", "Volume vs 50-day", "volx", { dec: 2 }), SC, VE],
      state: state, pageSize: 15,
    });
    hook(box, state, draw);
    draw();
  }

  function renderTrends(ctx) {
    const raw = ctx.files["trends.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div><div class="panel" id="tbl"></div>' +
      '<p class="cap">Uptrend means the price is above all four averages. Downtrend means it is below all four.</p>';
    const colors = { Uptrend: "#22C55E", Mixed: "#8B96AD", Downtrend: "#EF4444" };
    document.getElementById("cards").innerHTML = ["Uptrend", "Mixed", "Downtrend"].map((lab) =>
      card(lab, '<span style="color:' + colors[lab] + '">' + countWhere(all, (r) => r.trend_label === lab) + "</span>")).join("");
    const box = document.getElementById("ctrls");
    const labels = ["Uptrend", "Mixed", "Downtrend"];
    box.innerHTML = '<div class="toggles" data-filter="trend">' + labels.map((o) =>
      '<button type="button" data-v="' + o + '"' + (o === "Uptrend" ? ' class="on"' : "") + ">" + o + "</button>").join("") + "</div>" +
      D.multiHtml("sector", "Sector", D.uniq(all, "sector")) +
      D.searchHtml("ticker", "Ticker", "trd", D.uniq(all, "ticker"));
    box.querySelectorAll(".toggles button").forEach((btn) => {
      btn.addEventListener("click", () => {
        btn.classList.toggle("on");
        state.page = 0;
        draw();
      });
    });
    const state = { sort: "score", dir: "desc", page: 0 };
    const pickedTrend = () => Array.from(box.querySelectorAll(".toggles button.on")).map((b) => b.getAttribute("data-v"));
    const draw = () => {
      const on = pickedTrend();
      D.drawTable(document.getElementById("tbl"), {
        rows: all.filter((r) => (on.length === labels.length || on.indexOf(r.trend_label) >= 0) &&
          D.matchMulti(r, "sector", D.selectedMulti(box, "sector")) && D.matchText(r, "ticker", D.fieldVal(box, "ticker"))),
        columns: [TK, CO, T("trend_label", "Trend", "trend"),
          T("above_sma20", "Above 20d", "flag", { no: "#EF4444" }), T("above_sma50", "Above 50d", "flag", { no: "#EF4444" }),
          T("above_sma100", "Above 100d", "flag", { no: "#EF4444" }), T("above_sma200", "Above 200d", "flag", { no: "#EF4444" }), SC],
        state: state, pageSize: 25,
      });
    };
    hook(box, state, draw);
    draw();
  }

  const pullbacks = passesPage({
    file: "pullbacks.csv",
    caption: "An uptrend (above the 50-day and the 200-day) with price back in the pullback or entry area, and RSI under 70.",
    captionAbove: true,
    pageSize: 20,
    filters: { passes: "yes", sector: true, verdict: true, ticker: true },
    columns: [TK, CO, PR, T("rsi14", "RSI-14", "num", { dec: 1 }), T("entry_low", "Entry low", "num", { dec: 2 }),
      T("entry_high", "Entry high", "num", { dec: 2 }), SC, VE],
    cards(all) {
      const pass = all.filter((r) => r.passes === "yes");
      return card("Pullback setups", String(pass.length)) +
        card("Of those, BUY", String(countWhere(pass, (r) => r.verdict === "BUY"))) +
        card("Average RSI-14, passing", ntext(avg(pass, "rsi14"), 1));
    },
  });

  function renderGainers(ctx) {
    const raw = ctx.files["gainers_losers.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="split"><div class="panel" id="up"></div><div class="panel" id="dn"></div></div>' +
      '<p class="cap">Day % is the latest session\'s change, for stocks on the desk only.</p>';
    const box = document.getElementById("ctrls");
    standardFilters(box, all, { sector: true, verdict: true });
    const cols = [TK, CO, PR, T("day_pct", "Day %", "pct", { color: true }), SC, VE];
    const draw = () => {
      const rows = all.filter((r) => readCommon(box, r));
      D.drawTable(document.getElementById("up"), {
        title: "Biggest gainers today", rows: rows.filter((r) => r.side === "gainer"), columns: cols,
        state: { sort: "day_pct", dir: "desc", page: 0 }, pageSize: 15,
      });
      D.drawTable(document.getElementById("dn"), {
        title: "Biggest losers today", rows: rows.filter((r) => r.side === "loser"), columns: cols,
        state: { sort: "day_pct", dir: "asc", page: 0 }, pageSize: 15,
      });
    };
    hook(box, { page: 0 }, draw);
    draw();
  }

  function renderBreadth(ctx) {
    const raw = D.realRows(ctx.files["breadth_history.csv"]);
    const mt = (ctx.files["market_today.csv"] || [])[0] || {};
    const end = maxDate(raw, "date");
    const mood = (ctx.files["market_today.csv"] || [])[0] || {};
    ctx.page.innerHTML = trendStrip(mood) + '<div class="ctrls" id="ctrls"></div><div class="cards" id="cards"></div>' +
      '<div class="panel pad"><div class="ptitle">Share of the desk above each average</div><div class="chart-box htall"><canvas id="br"></canvas></div></div>' +
      '<p class="cap">A blank point is a session that did not have enough prices. The gap is left open, never drawn as zero.</p>';
    const now50 = D.num(mt.breadth_sma50);
    const prev50 = D.num(mt.breadth_sma50_week_ago);
    const delta = now50 != null && prev50 != null ? now50 - prev50 : null;
    const keys = [["breadth_sma20", "% above 20-day", ""], ["breadth_sma50", "% above 50-day", "week"], ["breadth_sma100", "% above 100-day", ""], ["breadth_sma200", "% above 200-day", ""]];
    document.getElementById("cards").innerHTML = keys.map((k) => {
      const sub = k[2] && delta != null ? '<span style="color:' + D.retColor(delta) + '">' + (delta > 0 ? "+" : "") + D.fmt(delta, 1) + " pts vs week ago</span>" : "";
      return card(k[1], D.num(mt[k[0]]) == null ? D.na() : D.esc(D.fmt(mt[k[0]], 1) + "%"), sub);
    }).join("");
    const box = document.getElementById("ctrls");
    box.innerHTML = D.dateHtml("from", "From", shift(end, -182));
    const draw = () => {
      const from = D.fieldVal(box, "from");
      const rows = raw.filter((r) => !from || r.date >= from);
      D.destroyCharts();
      D.lineChart(document.getElementById("br"), rows.map((r) => r.date), [
        { label: "Above 20-day", data: D.seriesNum(rows, "pct_above_sma20"), color: "#7C9CFF" },
        { label: "Above 50-day", data: D.seriesNum(rows, "pct_above_sma50"), color: "#E6EBF5" },
        { label: "Above 100-day", data: D.seriesNum(rows, "pct_above_sma100"), color: "#F59E0B" },
        { label: "Above 200-day", data: D.seriesNum(rows, "pct_above_sma200"), color: "#8B96AD" },
      ], { y: { min: 0, max: 100 } });
    };
    D.wireFilters(box, draw);
    draw();
  }

  function renderSecPerf(ctx) {
    const raw = ctx.files["sector_performance.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Equal weight across the desk\'s stocks in each sector, not the sector ETF. The ETF view is on Today.</p>' +
      '<div class="panel pad"><div class="ptitle">Past month, equal-weight %</div><div class="chart-box h300"><canvas id="sp"></canvas></div></div><div class="panel" id="tbl"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("sector", "Sector", D.uniq(all, "sector")) + D.rangeHtml("min", "Min. stocks", 1, 200, 5, 1);
    const state = { sort: "month_pct", dir: "desc", page: 0 };
    const draw = () => {
      const rows = all.filter((r) => D.matchMulti(r, "sector", D.selectedMulti(box, "sector")) && D.matchMin(r, "n", D.fieldVal(box, "min")));
      const ordered = rows.slice().sort((a, b) => (D.num(b.month_pct) || -999) - (D.num(a.month_pct) || -999));
      D.destroyCharts();
      D.barChart(document.getElementById("sp"), ordered.map((r) => r.sector), ordered.map((r) => D.num(r.month_pct)),
        ordered.map((r) => (D.num(r.month_pct) || 0) >= 0 ? "#1F9D55" : "#D14343"),
        { horizontal: true, labels: true, dec: 1, suffix: "%",
          x: { ticks: { color: "#5B6680", callback: (v) => { const n = Number(v); const sign = n > 0 ? "+" : n < 0 ? "−" : ""; return sign + Math.abs(n) + "%"; } }, grid: { color: "#1E293B" } } });
      D.drawTable(document.getElementById("tbl"), {
        rows: rows,
        columns: [SE, T("day_pct", "Day %", "pct", { color: true }), T("week_pct", "Week %", "pct", { color: true }), T("month_pct", "Month %", "pct", { color: true }),
          T("month3_pct", "3 months %", "pct", { color: true }), T("ytd_pct", "YTD %", "pct", { color: true }), T("pct_above_sma50", "% above 50-day", "pct", { dec: 1, color: false }),
          T("score_avg", "Average score", "num", { dec: 1 }), T("n", "Stocks", "num", { dec: 0 })],
        state: state, pageSize: 15, foot: false,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderHeatmaps(ctx) {
    const raw = ctx.files["heatmaps.csv"];
    const all = D.realRows(raw);
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap">Each cell is that stock\'s own return. The sector column on the right is the plain average of the desk\'s stocks, not the ETF.</p>' +
      '<div class="split hm"><div class="panel" id="tbl"></div><div class="panel" id="avg"></div></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("sector", "Sector", D.uniq(all, "sector")) +
      D.selectHtml("above", "Above 200-day", [{ value: "1", label: "Yes" }, { value: "0", label: "No" }], "") +
      D.searchHtml("ticker", "Ticker", "ht", D.uniq(all, "ticker"));
    const state = { sort: "ret_1d", dir: "desc", page: 0 };
    const draw = () => {
      const above = D.fieldVal(box, "above");
      const rows = all.filter((r) => D.matchMulti(r, "sector", D.selectedMulti(box, "sector")) &&
        D.matchText(r, "ticker", D.fieldVal(box, "ticker")) &&
        (!above || String(D.num(r.above_sma200)) === above || r.above_sma200 === (above === "1" ? "yes" : "no")));
      D.drawTable(document.getElementById("tbl"), {
        rows: rows,
        columns: [TK, CO, T("ret_1d", "1 day %", "heatpct", { dec: 1 }), T("ret_1w", "1 week %", "heatpct", { dec: 1 }),
          T("ret_1m", "1 month %", "heatpct", { dec: 1 }), T("ret_ytd", "YTD %", "heatpct", { dec: 1 }),
          T("above_sma20", "20d", "flag"), T("above_sma50", "50d", "flag"), T("above_sma100", "100d", "flag"), T("above_sma200", "200d", "flag")],
        state: state, pageSize: 25,
      });
      const sectors = D.uniq(rows, "sector").map((s) => {
        const sub = rows.filter((r) => r.sector === s);
        return { sector: s, ret_1d: avg(sub, "ret_1d") == null ? "" : String(avg(sub, "ret_1d")) };
      });
      D.drawTable(document.getElementById("avg"), {
        title: "Sector average, 1 day %", rows: sectors,
        columns: [SE, T("ret_1d", "1 day %", "heatpct", { dec: 2 })],
        state: { sort: "ret_1d", dir: "desc", page: 0 }, pageSize: 15, foot: false,
      });
    };
    hook(box, state, draw);
    draw();
  }

  function renderUpdates(ctx) {
    const log = ctx.files["updates_log.csv"] || [];
    const fresh = D.realRows(ctx.files["freshness.csv"]);
    const featureName = {
      "aaii sentiment": "India mood",
      "institutional 13f": "Shareholding",
      "historical pe": "Historical P/E",
      "xly xlp": "Auto vs FMCG",
      "put call": "Put/call",
      "option walls": "Put and call walls",
      "analyst ratings": "Analyst ratings",
      "insider trading": "Insider trading",
      "headline sentiment": "Headline sentiment",
      "financials summary": "Financials summary",
      "company financials": "Company financials",
      "earnings tracker": "Earnings tracker",
      "earnings calendar": "Calendar",
      "earnings heatmap": "Strength heatmap",
      "verdicts": "Verdicts",
      "backtest": "Backtest",
      "alerts": "Alerts",
      "universe": "Universe",
      "scorecard": "Stock scorecard",
      "breakouts": "52-week breakouts",
      "trends": "Trends",
      "pullbacks": "Pullbacks",
      "gainers losers": "Gainers and losers",
      "breadth": "Breadth",
      "sector performance": "Sector performance",
      "heatmaps": "Heatmaps",
      "updates log": "Data updates",
      "help": "Help",
      "earnings cards": "Report cards",
      "dividend scanner": "Dividend fundamentals",
      "macro screener": "Macro screener",
      "scanner growth": "Growth",
      "scanner quality": "Quality",
      "scanner dividend": "Dividend",
      "scanner wheel": "Liquid stocks",
      "scanner vcp": "VCP",
      "scanner canslim": "CANSLIM",
      "scanner box": "Box breakout",
      "scanner flag": "Flag breakout",
      "scanner leaders": "Leaders",
      "top stocks": "Top stocks",
      "top sectors": "Today's sectors",
      "watchlist portfolio": "Watchlist and portfolio",
      "score breakdown": "Score breakdown",
      "freshness flags": "Freshness",
      "news earnings summaries": "News",
      "momentum timing": "Timing",
      "fundamentals backfill": "Financials backfill",
    };
    const features = (ctx.settings || []).filter((r) => String(r.setting || "").indexOf("feature.") === 0).map((r) => {
      const key = String(r.setting).replace(/^feature\./, "").replace(/_/g, " ");
      const on = String(r.value || "").toLowerCase();
      const live = on === "true" || on === "yes" || on === "1";
      return { name: featureName[key] || key, on: live };
    });
    const prog = D.realRows(ctx.files["backfill_progress.csv"] || []);
    const byKind = {};
    prog.forEach((r) => { byKind[String(r.kind || "")] = r; });
    const stat = byKind.statements || {};
    const hold = byKind.shareholding || {};
    const countText = (row) => {
      if (!row || D.isBlank(row.covered)) return D.na();
      return D.esc(String(row.covered)) + " of " + D.esc(String(row.total || ""));
    };
    const when = stat.last_batch_at || hold.last_batch_at || "not yet";
    const backfillCards = '<div class="cards">' +
      card("Financials on file", countText(stat), stat.pct != null && stat.pct !== "" ? D.esc(String(stat.pct)) + "% of the list" : "") +
      card("Shareholding on file", countText(hold), hold.pct != null && hold.pct !== "" ? D.esc(String(hold.pct)) + "% of the list" : "") +
      card("Last batch", D.esc(String(when)), "Statements saved " + D.esc(String(stat.last_ok || "0")) + ", shareholding saved " + D.esc(String(hold.last_ok || "0"))) +
      "</div>" +
      (prog[0] && prog[0].cycle_note ? '<p class="cap">' + D.esc(prog[0].cycle_note) + "</p>" : "");
    ctx.page.innerHTML = backfillCards + '<div class="ctrls" id="ctrls"></div><div class="panel pad"><div class="ptitle">Feature switches</div><div class="featgrid">' +
      features.map((f) => '<div><span>' + D.esc(f.name) + '</span><span style="color:' + (f.on ? "#22C55E" : "#8B96AD") + '">' + (f.on ? "On" : "Off") + "</span></div>").join("") +
      '</div></div><div class="split r21"><div class="panel" id="log"></div><div class="panel" id="fr"></div></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.multiHtml("status", "Status", D.uniq(log, "status"));
    const draw = () => {
      D.drawTable(document.getElementById("log"), {
        title: "Updates log",
        rows: log.filter((r) => D.matchMulti(r, "status", D.selectedMulti(box, "status"))),
        columns: [T("checked_pt", "Checked", "checked"), T("source", "Source", "text", { width: "160px" }), T("status", "Status", "fresh"),
          T("latest", "Latest"), T("note", "Note", "text", { wrap: true })],
        state: { sort: "checked_pt", dir: "desc", page: 0 }, pageSize: 25,
      });
      const host = document.getElementById("fr");
      const rows = fresh.slice().sort((a, b) => (D.num(b.n_missing) || 0) - (D.num(a.n_missing) || 0));
      host.innerHTML = '<div class="pad" style="padding-bottom:0"><div class="ptitle">Fields filled in</div></div><div class="scroll"><table><thead><tr><th>Field</th><th class="num">On file</th><th class="num">Missing</th></tr></thead><tbody>' +
        rows.map((r) => {
          const miss = D.num(r.n_missing) || 0;
          return "<tr><td>" + D.esc(r.field) + '</td><td class="num">' + D.esc(r.n_present) + '</td><td class="num" style="color:' +
            (miss > 0 ? "#F59E0B" : "#8B96AD") + '">' + D.esc(String(miss)) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    };
    hook(box, { page: 0 }, draw);
    draw();
  }

  function renderFlows(ctx) {
    if (panelOff("feature.fii_dii_flows")) {
      ctx.page.innerHTML = offBox();
      return;
    }
    const rows = flowRows(ctx.files);
    const last = rows[rows.length - 1] || {};
    const fii = D.num(last.fii_net);
    const dii = D.num(last.dii_net);
    const when = last.date ? "Session " + last.date + ". Figures are in crore." : "No session is on file yet. The history grows after each close.";
    const windowRows = rows.slice(-90);
    ctx.page.innerHTML =
      '<p class="cap">' + D.esc(when) + " Green is net buying. Red is net selling. This is cash-market flow, not a trade.</p>" +
      '<div class="cards">' +
      card("FII net", croreHtml(fii), "crore · " + (D.isBlank(last.date) ? "n/a" : D.esc(last.date))) +
      card("DII net", croreHtml(dii), "crore · " + (D.isBlank(last.date) ? "n/a" : D.esc(last.date))) +
      card("FII gross buy", D.num(last.fii_buy) == null ? D.na() : D.esc(D.fmt(last.fii_buy, 0)), "crore") +
      card("FII gross sell", D.num(last.fii_sell) == null ? D.na() : D.esc(D.fmt(last.fii_sell, 0)), "crore") +
      card("DII gross buy", D.num(last.dii_buy) == null ? D.na() : D.esc(D.fmt(last.dii_buy, 0)), "crore") +
      card("DII gross sell", D.num(last.dii_sell) == null ? D.na() : D.esc(D.fmt(last.dii_sell, 0)), "crore") +
      "</div>" +
      '<div class="panel pad"><div class="ptitle">Streak</div><p style="font-size:18px;font-weight:700;margin:8px 0 4px">' + D.esc(streakLine(rows, "fii_net", "FII")) + "</p>" +
      '<p style="font-size:18px;font-weight:700;margin:0">' + D.esc(streakLine(rows, "dii_net", "DII")) + "</p></div>" +
      '<div class="cards" style="margin-top:16px">' +
      card("FII 5-day", croreHtml(flowWindow(rows, "fii_net", 5)), "DII " + (flowWindow(rows, "dii_net", 5) == null ? "n/a" : D.fmt(flowWindow(rows, "dii_net", 5), 0))) +
      card("FII 20-day", croreHtml(flowWindow(rows, "fii_net", 20)), "DII " + (flowWindow(rows, "dii_net", 20) == null ? "n/a" : D.fmt(flowWindow(rows, "dii_net", 20), 0))) +
      card("FII month to date", croreHtml(flowPrefix(rows, "fii_net", 7)), "DII " + (flowPrefix(rows, "dii_net", 7) == null ? "n/a" : D.fmt(flowPrefix(rows, "dii_net", 7), 0))) +
      card("FII year to date", croreHtml(flowPrefix(rows, "fii_net", 4)), "DII " + (flowPrefix(rows, "dii_net", 4) == null ? "n/a" : D.fmt(flowPrefix(rows, "dii_net", 4), 0))) +
      "</div>" +
      '<div class="panel pad"><div class="ptitle">FII and DII, last 90 sessions</div><div class="psub">Bars are the daily net in crore. The line is the running FII total.</div><div class="chart-box tall"><canvas id="flowbars"></canvas></div></div>' +
      '<div class="panel pad"><div class="ptitle">FII net and the index</div><div class="psub">Same sessions. The index is the line on the right scale.</div><div class="rrgtabs" id="flowbench"><button type="button" data-k="nifty" class="on">Nifty 50</button><button type="button" data-k="sensex">SENSEX</button></div><div class="chart-box tall"><canvas id="flownifty"></canvas></div></div>' +
      '<div id="oi"></div>' +
      '<p class="cap">History is kept and grows each run. A short chart means the free files only answered for those days.</p>';
    if (windowRows.length) {
      let run = 0;
      const cumAll = rows.map((r) => {
        const n = D.num(r.fii_net);
        if (n != null) run += n;
        return run;
      });
      const cum = cumAll.slice(-90);
      const labels = windowRows.map((r) => r.date);
      const fiiBars = windowRows.map((r) => D.num(r.fii_net));
      const diiBars = windowRows.map((r) => D.num(r.dii_net));
      const fiiColors = fiiBars.map((n) => (n == null || n >= 0) ? "#22C55E" : "#EF4444");
      const diiColors = diiBars.map((n) => (n == null || n >= 0) ? "rgba(124,156,255,.85)" : "rgba(245,158,11,.9)");
      D.makeChart(document.getElementById("flowbars"), {
        type: "bar",
        data: {
          labels: labels,
          datasets: [
            { label: "FII net", data: fiiBars, backgroundColor: fiiColors, yAxisID: "y" },
            { label: "DII net", data: diiBars, backgroundColor: diiColors, yAxisID: "y" },
            { type: "line", label: "FII cumulative", data: cum, borderColor: "#E6EBF5", backgroundColor: "#E6EBF5", yAxisID: "y1", pointRadius: 0, borderWidth: 2, spanGaps: true },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: "#8B96AD", boxWidth: 12 } } },
          scales: {
            x: { ticks: D.dateTicks(labels), grid: { color: "#1E293B" } },
            y: { position: "left", ticks: { color: "#8B96AD" }, grid: { color: "#1E293B" } },
            y1: { position: "right", ticks: { color: "#C3CBDB" }, grid: { display: false } },
          },
        },
      });
      let flowKey = "nifty";
      function paintFlowIndex() {
        const label = flowKey === "sensex" ? "SENSEX" : "Nifty 50";
        const series = windowRows.map((r) => D.num(flowKey === "sensex" ? r.sensex : r.nifty));
        D.makeChart(document.getElementById("flownifty"), {
          type: "bar",
          data: {
            labels: labels,
            datasets: [
              { label: "FII net", data: fiiBars, backgroundColor: fiiColors, yAxisID: "y" },
              { type: "line", label: label, data: series, borderColor: "#7C9CFF", backgroundColor: "#7C9CFF", yAxisID: "y1", pointRadius: 0, borderWidth: 2, spanGaps: true },
            ],
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { color: "#8B96AD", boxWidth: 12 } } },
            scales: {
              x: { ticks: D.dateTicks(labels), grid: { color: "#1E293B" } },
              y: { position: "left", title: { display: true, text: "FII net, crore", color: "#8B96AD" }, ticks: { color: "#8B96AD" }, grid: { color: "#1E293B" } },
              y1: { position: "right", title: { display: true, text: label, color: "#7C9CFF" }, ticks: { color: "#7C9CFF" }, grid: { display: false } },
            },
          },
        });
      }
      document.querySelectorAll("#flowbench button").forEach((btn) => {
        btn.addEventListener("click", () => {
          flowKey = btn.getAttribute("data-k");
          document.querySelectorAll("#flowbench button").forEach((b) => b.classList.toggle("on", b === btn));
          paintFlowIndex();
        });
      });
      if (!D.featureOn("feature.sensex")) {
        const host = document.getElementById("flowbench");
        if (host) host.hidden = true;
      }
      paintFlowIndex();
    }
    const oiHost = document.getElementById("oi");
    if (panelOff("feature.fii_dii_derivatives")) {
      oiHost.innerHTML = offBox();
      return;
    }
    const oi = D.realRows(ctx.files["participant_oi.csv"] || []);
    if (!oi.length) {
      oiHost.innerHTML = '<div class="panel pad"><div class="ptitle">Index futures positioning</div><p class="cap">Not available from the free NSE file today.</p></div>';
      return;
    }
    const latestDay = oi.map((r) => r.date).sort().slice(-1)[0];
    const latest = oi.filter((r) => r.date === latestDay);
    oiHost.innerHTML = '<div class="panel" id="oitbl"></div>';
    D.drawTable(document.getElementById("oitbl"), {
      title: "Index futures, long and short",
      sub: "NSE participant file for " + latestDay + ". Contracts, not a trade.",
      rows: latest,
      columns: [
        T("participant", "Who"),
        T("index_fut_long", "Index futures long", "num", { dec: 0 }),
        T("index_fut_short", "Index futures short", "num", { dec: 0 }),
        T("index_fut_net", "Net long", "num", { dec: 0 }),
      ],
      state: { sort: "participant", dir: "asc", page: 0 }, pageSize: 8, foot: false,
    });
  }

  function renderHelp(ctx) {
    const help = ctx.files["help.csv"] || [];
    const settings = ctx.files["settings.csv"] || [];
    ctx.page.innerHTML = '<div class="ctrls" id="ctrls"></div><div class="panel" id="help"></div><div class="panel w740" id="set"></div>';
    const box = document.getElementById("ctrls");
    box.innerHTML = D.searchHtml("topic", "Topic", "topics", D.uniq(help, "topic")) +
      '<label class="ctl"><span class="lab">Setting contains</span><input data-filter="setting" placeholder="Search settings"></label>';
    const draw = () => {
      const topic = (D.fieldVal(box, "topic") || "").trim().toLowerCase();
      const setting = (D.fieldVal(box, "setting") || "").trim().toLowerCase();
      D.drawTable(document.getElementById("help"), {
        title: "What the words mean",
        rows: help.filter((r) => !topic || (r.topic || "").toLowerCase().indexOf(topic) >= 0),
        columns: [T("topic", "Topic", "text"), T("plain_english", "What it means", "text", { wrap: true })],
        state: { sort: "topic", dir: "asc", page: 0 }, pageSize: 25,
      });
      D.drawTable(document.getElementById("set"), {
        title: "Settings", sub: "Edit these in the sheet's settings tab.",
        rows: settings.filter((r) => !setting || (r.setting || "").toLowerCase().indexOf(setting) >= 0),
        columns: [T("setting", "Setting"), T("value", "Value", "onoff", { wrap: true })],
        state: { sort: "setting", dir: "asc", page: 0 }, pageSize: 12,
      });
    };
    hook(box, { page: 0 }, draw);
    draw();
  }

  function zoneLines(row) {
    const lines = [];
    if (!row) return lines;
    const lo = D.num(row.entry_low);
    const hi = D.num(row.entry_high);
    if (lo != null && hi != null) lines.push({ zone: [lo, hi], labelColor: "#F59E0B" });
    if (D.num(row.stop) != null) lines.push({ value: D.num(row.stop), color: "#EF4444", label: "Stop" });
    const tgt = D.num(row.trade_target != null && row.trade_target !== "" ? row.trade_target : row.target);
    if (tgt != null) lines.push({ value: tgt, color: "#22C55E", label: "Target" });
    return lines;
  }

  function weekLines(row) {
    const lines = [];
    if (!row) return lines;
    if (D.num(row.high_52w) != null) lines.push({ value: D.num(row.high_52w), color: "#22C55E", label: "52w high" });
    if (D.num(row.low_52w) != null) lines.push({ value: D.num(row.low_52w), color: "#EF4444", label: "52w low" });
    return lines;
  }
  function renderWeek52(ctx) {
    const raw = ctx.files["scanner_52w.csv"];
    const all = D.realRows(raw);
    const hist = D.realRows(ctx.files["highs_lows_history.csv"]).slice().sort((a, b) => a.date < b.date ? -1 : 1);
    const yes = (r, key) => String(r[key] || "").toLowerCase() === "yes";
    const nHigh = countWhere(all, (r) => yes(r, "new_high_today"));
    const nLow = countWhere(all, (r) => yes(r, "new_low_today"));
    const nNear = countWhere(all, (r) => yes(r, "near_high"));
    const nVol = countWhere(all, (r) => yes(r, "high_on_volume"));
    const net = nHigh - nLow;
    const netText = net < 0 ? "−" + Math.abs(net) : String(net);
    const netColor = net > 0 ? "#22C55E" : net < 0 ? "#EF4444" : "#8B96AD";
    ctx.page.innerHTML =
      '<p class="cap">A 52-week high is the highest price of the last 252 trading days, and a 52-week low is the lowest. New highs and new lows on this page use the close, so a name can touch a new high during the day and still not count if it does not close there. Near the high means the close is within 5% of that high. A high on big volume also needs volume at least 1.5 times the 50-day average. This list is separate from 52-week breakouts. Research only. This page does not place trades.</p>' +
      '<div class="cards" id="cards"></div>' +
      '<div class="panel pad"><div class="rowhead wrap"><div style="min-width:0;flex:1"><div class="ptitle">Highs and lows</div><div class="psub">Green bars are new highs. Red bars are new lows. The line is highs minus lows.</div></div>' +
      '<div class="seg" id="hlrange"><button type="button" data-d="92">3M</button><button type="button" data-d="183" class="on">6M</button><button type="button" data-d="365">1Y</button></div></div>' +
      '<div class="chart-box tall"><canvas id="hl"></canvas></div></div>' +
      '<div class="ctrls" id="ctrls"></div><div class="panel" id="tbl"></div>';
    document.getElementById("cards").innerHTML =
      card("New 52w highs today", '<span style="color:#22C55E">' + nHigh + "</span>") +
      card("New 52w lows today", '<span style="color:#EF4444">' + nLow + "</span>") +
      card("Near high (within 5%)", '<span style="color:#F59E0B">' + nNear + "</span>") +
      card("New highs on big volume", '<span style="color:#22C55E">' + nVol + "</span>", "At least 1.5 times the 50-day average") +
      card("Net highs minus lows", '<span style="color:' + netColor + '">' + netText + "</span>");
    const tabs = [["highs", "New highs"], ["lows", "New lows"], ["near", "Near high"], ["vol", "On volume"], ["all", "All"]];
    const titles = {
      highs: "New highs today", lows: "New lows today", near: "Near the high",
      vol: "New high on big volume", all: "All stocks",
    };
    const box = document.getElementById("ctrls");
    standardFilters(box, all, { index: true, sector: true, verdict: true, ticker: true, order: ["index", "sector", "verdict", "ticker"], list: "w52" });
    box.insertAdjacentHTML("afterbegin", '<div class="w52tabs" id="w52tabs">' + tabs.map((t, i) =>
      '<button type="button" data-tab="' + t[0] + '"' + (i === 0 ? ' class="on"' : "") + ">" + t[1] + "</button>").join("") + "</div>");
    D.placeFeed(box, raw);
    let tab = "highs";
    let days = 183;
    const state = { sort: "range_position_pct", dir: "desc", sort2: "score", dir2: "desc", page: 0 };
    const columns = [TK, CO, SE, PR,
      T("high_52w", "52w high", "num", { dec: 2 }), T("low_52w", "52w low", "num", { dec: 2 }),
      T("pct_from_high", "% from high", "pct", { dec: 1, color: true }),
      T("pct_above_low", "% above low", "pct", { dec: 1, color: true }),
      T("range_position_pct", "Range", "rangepos"),
      T("volume_ratio", "Vol x", "volx", { dec: 2 }), SC, VE];
    const inTab = (r) => {
      if (tab === "highs") return yes(r, "new_high_today");
      if (tab === "lows") return yes(r, "new_low_today");
      if (tab === "near") return yes(r, "near_high");
      if (tab === "vol") return yes(r, "high_on_volume");
      return true;
    };
    const applySort = () => {
      if (tab === "lows") {
        state.sort = "pct_from_high"; state.dir = "asc"; state.sort2 = "score"; state.dir2 = "desc";
      } else {
        state.sort = "range_position_pct"; state.dir = "desc"; state.sort2 = "score"; state.dir2 = "desc";
      }
      state.page = 0;
    };
    const paint = () => {
      const rows = D.lastNDays(hist, "date", days).slice().sort((a, b) => a.date < b.date ? -1 : 1);
      D.destroyCharts();
      if (!rows.length) return;
      D.comboChart(document.getElementById("hl"), rows.map((r) => r.date), [
        { label: "New highs", data: D.seriesNum(rows, "new_highs"), color: "#22C55E" },
        { label: "New lows", data: D.seriesNum(rows, "new_lows"), color: "#EF4444" },
      ], { label: "Net", data: D.seriesNum(rows, "net"), color: "#7C9CFF" });
    };
    const draw = () => {
      D.drawTable(document.getElementById("tbl"), {
        title: titles[tab],
        rows: all.filter((r) => inTab(r) && readCommon(box, r)),
        columns: columns,
        state: state,
        pageSize: 25,
        lines: weekLines,
        priceSub: "52-week high and 52-week low",
        empty: "No names in this group.",
      });
    };
    box.querySelectorAll("#w52tabs button").forEach((btn) => {
      btn.addEventListener("click", () => {
        tab = btn.getAttribute("data-tab");
        box.querySelectorAll("#w52tabs button").forEach((b) => b.classList.toggle("on", b === btn));
        applySort();
        draw();
      });
    });
    document.getElementById("hlrange").addEventListener("click", (ev) => {
      const btn = ev.target.closest("button");
      if (!btn) return;
      days = Number(btn.getAttribute("data-d"));
      document.querySelectorAll("#hlrange button").forEach((b) => b.classList.toggle("on", b === btn));
      paint();
    });
    hook(box, state, draw);
    paint();
    draw();
  }

  function buyDetailHtml(row) {
    const px = (key) => {
      const n = D.num(row[key]);
      return n == null ? D.na() : D.esc(D.fmt(n, 2));
    };
    const gain = (key) => {
      const entry = D.num(row.entry);
      const value = D.num(row[key]);
      if (entry == null || value == null || entry === 0) return "";
      const pct = (value - entry) / entry * 100;
      const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
      return D.esc(sign + D.fmt(Math.abs(pct), 1) + "%");
    };
    const risk = D.num(row.risk_pct);
    const riskText = risk == null ? "" : D.esc(D.fmt(Math.abs(risk), 1) + "% risk");
    const rr = D.num(row.reward_risk);
    const rrText = rr == null || Math.abs(rr) > 500 ? D.na() : D.esc(D.fmt(rr, 2));
    const plan = (label, value, sub, tone) =>
      '<div class="tp' + (tone ? " " + tone : "") + '"><div class="l">' + D.esc(label) +
      '</div><div class="v">' + value + "</div>" + (sub ? '<div class="s">' + sub + "</div>" : "") + "</div>";
    const fact = (label, value) =>
      '<div class="fact"><div class="l">' + D.esc(label) + '</div><div class="v">' + value + "</div></div>";
    const rangeN = D.num(row.range_position_52w);
    let range = D.na();
    if (rangeN != null) {
      const clamped = Math.max(0, Math.min(100, rangeN));
      const w = Math.max(0, Math.round(clamped / 100 * 88));
      const color = clamped >= 95 ? "#22C55E" : clamped <= 15 ? "#EF4444" : "#7C9CFF";
      range = '<span class="track" title="' + D.esc(D.fmt(rangeN, 0)) + '"><span class="fill" style="width:' + w +
        'px;background:' + color + '"></span></span> ' + D.esc(D.fmt(rangeN, 0));
    }
    const asOfMatch = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(row.price_as_of || ""));
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const asOf = asOfMatch ? D.esc(months[Number(asOfMatch[2]) - 1] + " " + Number(asOfMatch[3]) + ", " + asOfMatch[1]) :
      (D.isBlank(row.price_as_of) ? D.na() : D.esc(row.price_as_of));
    const mkt = String(row.market_ok || "").toLowerCase();
    const mktHtml = mkt === "yes" ? '<span style="color:#22C55E">yes</span>' :
      mkt === "no" ? '<span style="color:#EF4444">no</span>' :
      (D.isBlank(row.market_ok) ? D.na() : D.esc(row.market_ok));
    const count = D.num(row.sources_count);
    const why = String(row.reason || "").trim();
    return '<p class="whytext">' + (why ? D.esc(why) : '<span class="m2">No reason was saved for this name.</span>') + "</p>" +
      '<div class="tradeplan">' +
        plan("Entry", px("entry"), "", "") +
        plan("Stop", px("stop"), riskText, "stop") +
        plan("Target 1", px("target1"), gain("target1"), "tgt") +
        plan("Target 2", px("target2"), gain("target2"), "tgt") +
        plan("Reward/risk", rrText, "", "") +
      "</div>" +
      '<div class="buyfacts">' +
        fact("Sector", D.isBlank(row.sector) ? D.na() : D.esc(row.sector)) +
        fact("Index", D.isBlank(row.index_membership) ? D.na() : D.esc(row.index_membership)) +
        fact("Price", px("price")) +
        fact("As of", asOf) +
        fact("Count", count == null ? D.na() : D.esc(D.fmt(count, 0))) +
        fact("52w range", range) +
        fact("% from 52w high", D.pctHtml(row.pct_from_high_52w, 1, true)) +
        fact("Market check", mktHtml) +
        fact("Nifty 50", D.isBlank(row.nifty_trend) ? D.na() : D.esc(row.nifty_trend)) +
        fact("SENSEX", D.isBlank(row.sensex_trend) ? D.na() : D.esc(row.sensex_trend)) +
        fact("Bank Nifty", D.isBlank(row.bank_trend) ? D.na() : D.esc(row.bank_trend)) +
        fact("Financials", String(row.financials_pending || "").toLowerCase() === "yes" ? '<span style="color:#8B96AD">Pending</span>' : "On file") +
      "</div>";
  }
  function buyLines(row) {
    const lines = [];
    if (!row) return lines;
    const add = (key, color, label) => {
      const n = D.num(row[key]);
      if (n != null) lines.push({ value: n, color: color, label: label });
    };
    add("entry", "#F59E0B", "Entry");
    add("stop", "#EF4444", "Stop");
    add("target1", "#22C55E", "Target 1");
    add("target2", "#7C9CFF", "Target 2");
    return lines;
  }
  function renderBuySetups(ctx) {
    const raw = ctx.files["buy_setups.csv"];
    const fileRows = D.realRows(raw);
    const missing = (raw || []).some((r) => r.data_status === "MISSING");
    const named = fileRows.filter((r) => String(r.ticker || "").trim()).map((r) => {
      r.status = r.best_status;
      return r;
    });
    const market = fileRows[0] || {};
    const yes = (v) => String(v || "").toLowerCase() === "yes";
    const filterOn = D.featureOn("buy_setups.market_filter");
    const marketDown = !missing && filterOn && !yes(market.market_ok);
    const progress = (ctx.files["backfill_progress.csv"] || []).find((r) => String(r.kind || "") === "statements") || {};
    const coverage = D.num(progress.pct);
    const cutoff = D.num((ctx.settings || []).find((r) => r.setting === "buy_setups.full_rules_at_coverage_pct")?.value);
    const fullAt = cutoff == null ? 80 : cutoff;
    const configChart = D.featureOn("buy_setups.chart_setups_only");
    let chartOnly = configChart && !(coverage != null && coverage >= fullAt);
    ctx.page.innerHTML =
      '<p class="cap">Research list, not a recommendation. This desk never places trades.</p>' +
      trendStrip(Object.assign({}, (ctx.files["market_today.csv"] || [])[0] || {}, {
        nifty_trend: market.nifty_trend,
        sensex_trend: market.sensex_trend,
        bank_trend: market.bank_trend,
      })) +
      '<div id="buybanner" class="buybanner" hidden></div>' +
      '<div class="cards" id="cards"></div>' +
      '<div class="ctrls" id="ctrls"></div>' +
      '<div class="panel" id="tbl"></div>' +
      '<p class="cap">A name is listed when at least one of VCP, Box, Flag, Qullamaggie, Marios, Episodic Pivot (EP), and CANSLIM is ready or broke out today, the close is above the 50-day and 200-day averages, and the risk from the entry to the stop is 8% or less. Chart setups only also keeps a BUY or a Not scored yet label, and tags the unscored rows Financials pending. A scored AVOID stays off. With the switch off, only BUY remains. The market check passes when the Nifty 50 or SENSEX is in an uptrend. When that check fails, Show anyway lists every name that passes the chart rules, greyed out, with its real verdict: BUY, HOLD, AVOID, or Not scored yet. Tap a row for the reason, the trade plan, and the daily price chart. Many breakouts fail, which is why the stop is always shown. Nothing here is an alert.</p>';
    const box = document.getElementById("ctrls");
    box.innerHTML =
      D.multiHtml("index", "Index", D.indexTokens(named)) +
      D.multiHtml("sector", "Sector", D.uniq(named, "sector")) +
      D.multiHtml("source", "Setup", ["VCP", "Box", "Flag", "Qullamaggie", "Marios", "EP", "CANSLIM"]) +
      D.multiHtml("status", "Status", D.uniq(named, "status")) +
      D.searchHtml("ticker", "Ticker", "tick-list-buy", D.uniq(named, "ticker")) +
      '<div class="rrgtabs" id="chartsw"><span class="lab">Chart setups only</span><button type="button" id="chartonly">' + (chartOnly ? "On" : "Off") + "</button></div>";
    D.placeFeed(box, raw);
    let showAnyway = false;
    const state = { sort: "_ord", dir: "asc", page: 0 };
    const columns = [
      T("_ord", "", "num", { hidden: true }),
      TK, T("company", "Company", "text", { ellipsis: true }),
      T("setup_sources", "Setup", "text", { ellipsis: true }),
      T("best_status", "Status", "setup", { ellipsis: true }),
      T("entry", "Entry", "num", { dec: 2 }),
      T("stop", "Stop", "num", { dec: 2, tone: "stop" }),
      T("target1", "Target 1", "num", { dec: 2, tone: "target" }),
      T("target2", "Target 2", "num", { dec: 2, tone: "target" }),
      T("risk_pct", "Risk %", "pct", { dec: 1 }),
      T("reward_risk", "Reward/risk", "multiple", { dec: 2 }),
      T("dist_to_entry_pct", "Dist. to entry", "pct", { dec: 1, color: true }),
      SC, VE, T("financials_pending", "Financials", "pending"),
    ];
    const sourceOk = (row) => {
      const picked = D.selectedMulti(box, "source");
      if (!picked) return true;
      const parts = String(row.setup_sources || "").split("+").map((s) => s.trim());
      return picked.some((p) => parts.indexOf(p) >= 0);
    };
    const specOrder = (rows) => {
      const ranked = rows.slice().sort((a, b) => {
        const status = (r) => r.best_status === "BROKEN OUT today" ? 0 : 1;
        if (status(a) !== status(b)) return status(a) - status(b);
        const count = (r) => D.num(r.sources_count) || 0;
        if (count(a) !== count(b)) return count(b) - count(a);
        const dist = (r) => {
          const n = D.num(r.dist_to_entry_pct);
          return n == null ? Infinity : Math.abs(n);
        };
        if (dist(a) !== dist(b)) return dist(a) - dist(b);
        const score = (r) => {
          const n = D.num(r.score);
          return n == null ? -Infinity : n;
        };
        if (score(a) !== score(b)) return score(b) - score(a);
        return String(a.ticker || "").localeCompare(String(b.ticker || ""));
      });
      ranked.forEach((r, i) => { r._ord = i; });
      return ranked;
    };
    const verdictOf = (row) => String(row.verdict || "").trim() || "Not scored yet";
    const chartPass = (row) => {
      const v = verdictOf(row);
      return v === "BUY" || (chartOnly && v === "Not scored yet");
    };
    // Show anyway lists every chart setup, whatever its verdict, so it never
    // depends on the Chart setups only switch or on the financials coverage.
    const listPass = (row) => (marketDown && showAnyway) ? true : chartPass(row);
    const correction = [market.nifty_trend, market.sensex_trend].some((t) => /correction/i.test(String(t || "")));
    const draw = () => {
      const grey = marketDown && showAnyway;
      const pool = (marketDown && !showAnyway) ? [] : named.filter((r) => listPass(r) && readCommon(box, r) && sourceOk(r));
      const rows = specOrder(pool);
      const kpis = (marketDown && !showAnyway) ? [] : named.filter(listPass);
      const broken = countWhere(kpis, (r) => r.best_status === "BROKEN OUT today");
      const multi = countWhere(kpis, (r) => (D.num(r.sources_count) || 0) >= 2);
      const rr = avg(kpis, "reward_risk");
      document.getElementById("cards").innerHTML =
        card("Setups today", String(kpis.length)) +
        card("Broken out today", String(broken)) +
        card("Multi-scanner setups", String(multi), "At least two scanners agree") +
        card("Market status", missing ? D.na() : D.esc((market.nifty_trend || "n/a") + " / " + (market.sensex_trend || "n/a")), missing ? "" : "Bank Nifty " + D.esc(market.bank_trend || "n/a")) +
        card("Average reward-to-risk", rr == null ? D.na() : D.esc(D.fmt(rr, 2)), "Target 1 versus the stop");
      const banner = document.getElementById("buybanner");
      if (marketDown) {
        banner.hidden = false;
        const rule = String(market.market_rule || "either") === "both"
          ? "A buy setup needs both the Nifty 50 and SENSEX in an uptrend, so none are listed."
          : "A buy setup needs the Nifty 50 or SENSEX in an uptrend, so none are listed.";
        banner.innerHTML = "<span>Nifty 50 is " + D.esc(market.nifty_trend || "not on file") +
          ". SENSEX is " + D.esc(market.sensex_trend || "not on file") +
          ". Bank Nifty is " + D.esc(market.bank_trend || "not on file") + ". " + rule +
          (showAnyway
            ? " " + (correction ? "The market is in a correction." : "The market is not in an uptrend.") +
              " These names pass the chart rules and are greyed out. Each one shows its real verdict."
            : "") + "</span>" +
          '<button type="button" id="showanyway">' + (showAnyway ? "Hide greyed names" : "Show anyway") + "</button>";
        banner.querySelector("#showanyway").addEventListener("click", () => { showAnyway = !showAnyway; draw(); });
      } else {
        banner.hidden = true;
        banner.innerHTML = "";
      }
      const host = document.getElementById("tbl");
      host.classList.toggle("dimmed", grey);
      D.drawTable(host, {
        rows: rows,
        columns: columns,
        state: state,
        pageSize: 25,
        fit: true,
        lines: buyLines,
        priceSub: "Entry, stop, and both targets. The stop stays on the chart because many breakouts fail.",
        detail: buyDetailHtml,
        empty: marketDown && !showAnyway ? "No buy setups are listed." : (named.filter(listPass).length ? "No names match these filters." : (grey ? "No stock passed the chart rules today." : "No stock passed the buy-setup rules today.")),
      });
    };
    const chartBtn = document.getElementById("chartonly");
    if (chartBtn) {
      chartBtn.classList.toggle("on", chartOnly);
      chartBtn.addEventListener("click", () => {
        chartOnly = !chartOnly;
        chartBtn.textContent = chartOnly ? "On" : "Off";
        chartBtn.classList.toggle("on", chartOnly);
        draw();
      });
    }
    hook(box, state, draw);
    draw();
  }

  function renderRotation(ctx) {
    const raw = ctx.files["sector_rotation.csv"] || [];
    const allRows = D.realRows(raw);
    const allTails = D.realRows(ctx.files["sector_rotation_tails.csv"] || []);
    const scores = D.realRows(ctx.files["scores.csv"] || []);
    let benchPick = "^NSEI";
    const savedBench = (ctx.settings || []).find((r) => r.setting === "sector_rotation.benchmark");
    if (savedBench && String(savedBench.value).indexOf("BSESN") >= 0) benchPick = "^BSESN";
    const takeBench = (list) => {
      if (!list.some((r) => r.benchmark)) return list;
      const got = list.filter((r) => String(r.benchmark) === benchPick);
      return got.length ? got : list.filter((r) => String(r.benchmark) !== "^BSESN");
    };
    let rows = takeBench(allRows);
    let tails = takeBench(allTails);
    const colors = {
      "^CNXIT": "#7C9CFF", "^NSEBANK": "#F59E0B", "^CNXAUTO": "#FB7185", "^CNXPHARMA": "#22C55E",
      "^CNXFMCG": "#FBBF24", "^CNXMETAL": "#94A3B8", "^CNXREALTY": "#C084FC", "^CNXENERGY": "#EF4444",
      "^CNXMEDIA": "#A78BFA", "^CNXPSUBANK": "#38BDF8", "^CNXFIN": "#2DD4BF", "^CNXINFRA": "#E6EBF5",
    };
    let ranked = rows.slice().sort((a, b) => (D.num(a.rank) || 99) - (D.num(b.rank) || 99) || String(a.name).localeCompare(String(b.name)));
    let tf = "W";
    let tailN = 8;
    let pick = ranked[0] ? ranked[0].ticker : "";
    const head = ranked[0] || {};
    const weeklyChanges = rows.filter((r) => String(r.change_weekly || "").indexOf("moved from") >= 0);
    const dailyChanges = rows.filter((r) => String(r.change_daily || "").indexOf("moved from") >= 0);
    const sample = rows[0] || {};
    ctx.page.innerHTML =
      '<div class="ctrls" id="ctrls"></div>' +
      '<p class="cap" id="rotcap">RS is the sector index divided by the Nifty 50, using daily closes already saved. RS-Ratio is 100 plus the z-score of that ratio, smoothed, versus its rolling mean. RS-Momentum is 100 plus the z-score of how fast RS-Ratio is changing. 100 is the center. Weekly and monthly points are built from those same daily bars. This is a desk calculation, not a commercial indicator. Research only. This desk never places trades.</p>' +
      '<div class="cards" id="cards"></div>' +
      '<div class="panel pad"><div class="ptitle">Relative rotation</div><div class="chart-box rrg-box"><canvas id="rrg"></canvas></div><div class="rrglegend" id="rrglegend"></div><div class="rrgread" id="rrgread">Tap a point to read RS-Ratio and RS-Momentum.</div></div>' +
      '<div class="split"><div class="panel pad" id="macro"></div><div class="panel pad" id="changed"></div></div>' +
      '<div class="panel" id="tbl"></div><div class="panel" id="names"></div>';
    document.getElementById("ctrls").innerHTML =
      '<div class="rrgtabs" id="rotbench"><span class="lab">Benchmark</span><button type="button" data-b="^NSEI">Nifty 50</button><button type="button" data-b="^BSESN">SENSEX</button></div>' +
      '<div class="rrgtabs" id="rrgtf">' +
      '<button type="button" data-tf="D">Daily</button><button type="button" data-tf="W" class="on">Weekly</button><button type="button" data-tf="M">Monthly</button></div>' +
      '<div class="rrgtabs" id="rrgtail"><span class="lab">Tail</span>' +
      '<button type="button" data-n="4">4</button><button type="button" data-n="8" class="on">8</button><button type="button" data-n="12">12</button></div>';
    D.placeFeed(document.getElementById("ctrls"), raw);
    const leadN = countWhere(rows, (r) => r.quadrant_w === "Leading");
    const lagN = countWhere(rows, (r) => r.quadrant_w === "Lagging");
    document.getElementById("cards").innerHTML =
      card("Top sector", D.esc(head.name || "n/a"), head.score != null && head.score !== "" ? "Score " + D.fmt(D.num(head.score), 1) : "") +
      card("Leading", String(leadN), "Weekly") +
      card("Lagging", String(lagN), "Weekly") +
      card("Quadrant changes", String(weeklyChanges.length), "Versus last week") +
      card("India 10-year", D.esc(sample.dgs10_trend || "not on file"), "About 3 months, when a history is saved");
    function tendency(trend, downText, upText, flatText, missingText) {
      if (trend === "down") return downText;
      if (trend === "up") return upText;
      if (trend === "flat") return flatText;
      return missingText;
    }
    const yTrend = sample.dgs10_trend || "missing";
    const yLast = D.num(sample.dgs10_last);
    document.getElementById("macro").innerHTML =
      '<div class="ptitle">Macro backdrop</div>' +
      '<p class="cap">General tendencies, not a forecast. The India 10-year is shown only when a saved history has more than one reading. Oil and gold are not in this cache.</p>' +
      '<p><strong>India 10-year yield</strong> ' + D.esc(yTrend === "missing" ? "not on file" : yTrend) + (yLast == null ? "" : " · " + D.fmt(yLast, 2)) + ". " +
      D.esc(tendency(yTrend,
        "Falling rates have often favored banks' bond books and rate-sensitive groups such as realty and autos. That is history, not a forecast.",
        "Rising rates have often favored lenders' loan yields. That is history, not a forecast.",
        "A flat yield has no strong historical lean on this page.",
        "The India 10-year history is not on file, so this line stays blank.")) + "</p>";
    const lines = [];
    dailyChanges.forEach((r) => lines.push(r.change_daily + " since the prior session."));
    weeklyChanges.forEach((r) => lines.push(r.change_weekly + " since last week."));
    document.getElementById("changed").innerHTML = '<div class="ptitle">What changed</div>' +
      (lines.length ? '<ul class="changed">' + lines.map((t) => "<li>" + D.esc(t) + "</li>").join("") + "</ul>"
        : '<p class="cap">No sector changed quadrant versus the prior session or last week.</p>');
    document.getElementById("rrglegend").innerHTML = ranked.map((r) =>
      '<span><i class="rrgdot" style="background:' + (colors[r.ticker] || "#8B96AD") + '"></i>' + D.esc(r.name || r.ticker) + "</span>").join("") +
      '<span><i class="rrgdot" style="background:#22C55E"></i>Leading</span>' +
      '<span><i class="rrgdot" style="background:#F59E0B"></i>Weakening</span>' +
      '<span><i class="rrgdot" style="background:#EF4444"></i>Lagging</span>' +
      '<span><i class="rrgdot" style="background:#7C9CFF"></i>Improving</span>';
    const state = { sort: "rank", dir: "asc", page: 0 };
    function pointsFor(ticker) {
      return tails.filter((r) => r.timeframe === tf && r.ticker === ticker)
        .sort((a, b) => (D.num(a.tail_index) || 0) - (D.num(b.tail_index) || 0))
        .slice(-tailN)
        .map((r) => ({ x: D.num(r.rs_ratio), y: D.num(r.rs_momentum), date: r.date, name: r.name, ticker: r.ticker }))
        .filter((p) => p.x != null && p.y != null);
    }
    function showReadout(p) {
      const q = p.x >= 100 && p.y >= 100 ? "Leading" : p.x >= 100 ? "Weakening" : p.y >= 100 ? "Improving" : "Lagging";
      document.getElementById("rrgread").textContent =
        (p.name || p.ticker) + " · " + p.date + " · RS-Ratio " + D.fmt(p.x, 2) + " · RS-Momentum " + D.fmt(p.y, 2) + " · " + q;
    }
    function drawChart() {
      D.destroyCharts();
      const canvas = document.getElementById("rrg");
      const sets = ranked.map((r) => {
        const data = pointsFor(r.ticker);
        const color = colors[r.ticker] || "#8B96AD";
        return { label: r.name || r.ticker, data: data, color: color, name: r.name };
      }).filter((s) => s.data.length);
      let minX = 100, maxX = 100, minY = 100, maxY = 100;
      sets.forEach((s) => s.data.forEach((p) => {
        minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
      }));
      const padX = Math.max(2, (maxX - minX) * 0.14);
      const padY = Math.max(2, (maxY - minY) * 0.14);
      const quadPlugin = {
        id: "rrgQuad",
        beforeDatasetsDraw(chart) {
          const area = chart.chartArea;
          const xs = chart.scales.x;
          const ys = chart.scales.y;
          if (!area || !xs || !ys) return;
          const x0 = xs.getPixelForValue(100);
          const y0 = ys.getPixelForValue(100);
          const ctx2 = chart.ctx;
          ctx2.save();
          function fill(x1, y1, x2, y2, color) {
            ctx2.fillStyle = color;
            ctx2.globalAlpha = 0.28;
            ctx2.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
          }
          fill(x0, area.top, area.right, y0, "#22C55E");
          fill(x0, y0, area.right, area.bottom, "#F59E0B");
          fill(area.left, y0, x0, area.bottom, "#EF4444");
          fill(area.left, area.top, x0, y0, "#7C9CFF");
          ctx2.globalAlpha = 1;
          ctx2.strokeStyle = D.tc("#94A3B8");
          ctx2.lineWidth = 1.25;
          ctx2.beginPath();
          ctx2.moveTo(x0, area.top); ctx2.lineTo(x0, area.bottom);
          ctx2.moveTo(area.left, y0); ctx2.lineTo(area.right, y0);
          ctx2.stroke();
          ctx2.font = "11px Roboto, Arial, sans-serif";
          ctx2.fillStyle = "#8B96AD";
          ctx2.textAlign = "left";
          ctx2.fillText("Improving", area.left + 6, area.top + 14);
          ctx2.textAlign = "right";
          ctx2.fillText("Leading", area.right - 6, area.top + 14);
          ctx2.fillText("Weakening", area.right - 6, area.bottom - 6);
          ctx2.textAlign = "left";
          ctx2.fillText("Lagging", area.left + 6, area.bottom - 6);
          ctx2.restore();
        },
      };
      D.makeChart(canvas, {
        type: "scatter",
        data: {
          datasets: sets.map((s) => ({
            label: s.label,
            data: s.data,
            showLine: true,
            borderColor: s.color,
            backgroundColor: s.color,
            borderWidth: 1.5,
            pointRadius: s.data.map((_, i) => i === s.data.length - 1 ? 6 : 2.5),
            pointHoverRadius: 8,
            pointHitRadius: 16,
            tension: 0,
          })),
        },
        plugins: [quadPlugin],
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: "nearest", intersect: false },
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          layout: { padding: { top: 16, right: 8, bottom: 4, left: 4 } },
          scales: {
            x: { min: minX - padX, max: maxX + padX, ticks: { color: "#8B96AD", maxTicksLimit: 6 }, grid: { color: "#1E293B" }, title: { display: true, text: "RS-Ratio", color: "#8B96AD" } },
            y: { min: minY - padY, max: maxY + padY, ticks: { color: "#8B96AD", maxTicksLimit: 6 }, grid: { color: "#1E293B" }, title: { display: true, text: "RS-Momentum", color: "#8B96AD" } },
          },
          onClick(evt, els, chart) {
            if (!els.length || !chart) return;
            const ds = chart.data.datasets[els[0].datasetIndex];
            showReadout(ds.data[els[0].index]);
          },
        },
      });
      if (!sets.length) {
        document.getElementById("rrgread").textContent = "No rotation points for this bar size yet.";
      }
    }
    function drawNames() {
      const row = ranked.find((r) => r.ticker === pick) || ranked[0];
      const host = document.getElementById("names");
      if (!row) { host.innerHTML = ""; return; }
      const names = scores.filter((r) => r.sector === row.sector)
        .sort((a, b) => (D.num(b.score) || -999) - (D.num(a.score) || -999))
        .slice(0, 12);
      D.drawTable(host, {
        title: "Top stocks in " + row.name,
        sub: row.reason || "",
        rows: names,
        columns: [T("ticker", "Ticker", "ticker"), T("company", "Company", "text"), T("score", "Score", "num", { dec: 0 }), T("verdict", "Verdict", "verdict")],
        state: { sort: "score", dir: "desc", page: 0 },
        pageSize: 12,
        foot: false,
        lines: zoneLines,
        priceSub: "Daily candles in rupees. Entry zone, stop, and target when the score has them.",
        empty: "No scored stocks in this sector.",
      });
    }
    function drawTable() {
      D.drawTable(document.getElementById("tbl"), {
        title: "Sector indexes",
        rows: ranked,
        columns: [
          T("rank", "Rank", "num", { dec: 0 }),
          T("name", "Index"),
          T("score", "Score", "num", { dec: 1 }),
          T("quadrant_d", "D", "quad"),
          T("quadrant_w", "W", "quad"),
          T("quadrant_m", "M", "quad"),
          T("rs_1m", "RS 1m", "pct", { dec: 1, color: true }),
          T("rs_3m", "RS 3m", "pct", { dec: 1, color: true }),
          T("rs_6m", "RS 6m", "pct", { dec: 1, color: true }),
          T("breadth_sma50", "Above 50d", "pct", { dec: 0 }),
          T("breadth_sma200", "Above 200d", "pct", { dec: 0 }),
          T("near_high_count", "Near high", "num", { dec: 0 }),
          T("buy_setup_count", "Buy setups", "num", { dec: 0 }),
          T("score_avg", "Desk avg", "num", { dec: 1 }),
          T("buy_share", "BUY %", "pct", { dec: 0 }),
          T("reason", "Reason", "text", { ellipsis: true, inDetail: true }),
        ],
        state: state,
        pageSize: 15,
        foot: false,
        expandable: false,
        pick: pick,
        onPick(row) { pick = row.ticker; drawTable(); drawNames(); },
        empty: "No sector rotation on file.",
      });
    }
    function paintBench() {
      rows = takeBench(allRows);
      tails = takeBench(allTails);
      ranked = rows.slice().sort((a, b) => (D.num(a.rank) || 99) - (D.num(b.rank) || 99) || String(a.name).localeCompare(String(b.name)));
      pick = ranked[0] ? ranked[0].ticker : "";
      const word = benchPick === "^BSESN" ? "the SENSEX" : "the Nifty 50";
      const cap = document.getElementById("rotcap");
      if (cap) cap.textContent = "RS is the sector index divided by " + word + ", using daily closes already saved. RS-Ratio is 100 plus the z-score of that ratio, smoothed, versus its rolling mean. RS-Momentum is 100 plus the z-score of how fast RS-Ratio is changing. 100 is the center. Weekly and monthly points are built from those same daily bars. This is a desk calculation, not a commercial indicator. Research only. This desk never places trades.";
      const headNow = ranked[0] || {};
      const leadNow = countWhere(rows, (r) => r.quadrant_w === "Leading");
      const lagNow = countWhere(rows, (r) => r.quadrant_w === "Lagging");
      document.getElementById("cards").innerHTML =
        card("Top sector", D.esc(headNow.name || "n/a"), headNow.score != null && headNow.score !== "" ? "Score " + D.fmt(D.num(headNow.score), 1) : "") +
        card("Leading", String(leadNow), "Weekly") +
        card("Lagging", String(lagNow), "Weekly") +
        card("Quadrant changes", String(rows.filter((r) => String(r.change_weekly || "").indexOf("moved from") >= 0).length), "Versus last week") +
        card("India 10-year", D.esc((rows[0] || {}).dgs10_trend || "not on file"), "About 3 months, when a history is saved");
      document.getElementById("rrglegend").innerHTML = ranked.map((r) =>
        '<span><i class="rrgdot" style="background:' + (colors[r.ticker] || "#8B96AD") + '"></i>' + D.esc(r.name || r.ticker) + "</span>").join("") +
        '<span><i class="rrgdot" style="background:#22C55E"></i>Leading</span>' +
        '<span><i class="rrgdot" style="background:#F59E0B"></i>Weakening</span>' +
        '<span><i class="rrgdot" style="background:#EF4444"></i>Lagging</span>' +
        '<span><i class="rrgdot" style="background:#7C9CFF"></i>Improving</span>';
      document.querySelectorAll("#rotbench button").forEach((b) => b.classList.toggle("on", b.getAttribute("data-b") === benchPick));
      drawChart();
      drawTable();
      drawNames();
    }
    document.querySelectorAll("#rotbench button").forEach((btn) => {
      btn.addEventListener("click", () => {
        benchPick = btn.getAttribute("data-b");
        paintBench();
      });
    });
    if (!D.featureOn("feature.sensex")) {
      const host = document.getElementById("rotbench");
      if (host) host.hidden = true;
    }
    document.getElementById("rrgtf").querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        tf = btn.getAttribute("data-tf");
        document.querySelectorAll("#rrgtf button").forEach((b) => b.classList.toggle("on", b === btn));
        drawChart();
      });
    });
    document.getElementById("rrgtail").querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        tailN = Number(btn.getAttribute("data-n"));
        document.querySelectorAll("#rrgtail button").forEach((b) => b.classList.toggle("on", b === btn));
        drawChart();
      });
    });
    paintBench();
  }


  // Plain-English "What this page does" boxes, one per page. Shown above the page by
  // Desk.boot. One switch turns them all off: feature.page_descriptions in config.json.
  // Numbers match config.json, setups.py, tables.py, and volume_scanner.py. Simple words, short sentences.
  const LIQUID_LINE = "Only stocks that trade at least ₹1 crore a day are scanned. That is the middle value of the last 20 days.";
  const ALL_SCORED_LINE = "This list checks every stock with a desk score, so it can include quiet stocks that trade under ₹1 crore a day.";
  const SCAN = "What this scanner does";
  const ABOUT = {
    vcp: { title: SCAN, note: LIQUID_LINE, lines: [
      "Same rules as Nick's TradingView indicator. A stock is listed only when it would get the green VCP tag: all 8 trend rules pass and there are at least two pullbacks that get smaller.",
      "READY means price is still under the buy line. BROKEN OUT today means it closed above the buy line on volume at least 1.5 times the 50-day average.",
      "WATCHING means the trend is 8 of 8 but it is not ready yet. Price went over the line on low volume, or there is only one pullback so far.",
      "A stock still in a trade stays on the list if its buy printed with 8 of 8. Set vcp.show_weaker_trend to true to also see stocks with a weaker trend. They show as WATCHING (trend not 8/8).",
      "A buy needs a fresh close above the line on big volume. Stops and targets: 7% stop, sell part at +20%.",
    ] },
    box: { title: SCAN, note: LIQUID_LINE, lines: [
      "A tight sideways range of 15 to 40 days, no more than 10% wide.",
      "READY means price is within 2% of the top of the box. A breakout is a close above the box on volume above 1.5 times the 50-day average.",
      "The stop is the box low.",
    ] },
    flag: { title: SCAN, note: LIQUID_LINE, lines: [
      "A sharp rise of at least 15% in 3 to 12 days (the pole), then a short 3 to 15 day pause that gives back less than half of the rise (the flag).",
      "A breakout is a close above the flag high on volume above 1.5 times the 50-day average.",
    ] },
    qullamaggie: { title: SCAN, note: LIQUID_LINE, lines: [
      "Qullamaggie's own rules: buy the top 1 to 2% gainers over 1, 3 or 6 months. ADR (normal daily range) of 3.5 to 5% or more. A 30 to 100% run in 1 to 3 months, then a 2 week to 2 month base with higher lows that rides the 10 and 20-day averages (sometimes the 50). Buy the opening range high. Stop at the low of the day, no wider than one ADR. Sell 1/3 to 1/2 after 3 to 5 days, move the stop to breakeven, then sell the rest on the first close under the 10 or 20-day.",
      "This page uses daily bars, so some rules are approximations. Leader: top 3% on the 21, 63 or 126-day return across the stocks scanned. Run: 30% or more within the 63 days before the base, rising in 40 days or less. ADR: 20-day average of high divided by low, minus 1, at least 3.5% (5% or more is tagged fast). Price at least Rs 20.",
      "Base: 10 to 40 days, the lowest low of its second half at or above the first half, at least 70% of closes above the 20-day or every close above the 50-day, and the 10-day above the 20-day with both rising. Desk rules on top: the base is no more than 25% deep, its top is within 10% of the run high, and it starts in the top half of its range. Each one has a switch.",
      "Entry: BROKEN OUT today means today's high went above the base high (the stand-in for the opening range high). Fill is the open or the base high, whichever is higher. Stop is today's low. If the stop is more than 1 ADR under the fill it says Too wide, skip, and 0.5 ADR or less is A+. READY means the close is within 1 ADR under the base high. Big volume (1.5 times the prior 50 days) only helps the ranking.",
      "IN TRADE follows each breakout day by day. On day 3 to 5 it says Sell 1/3 to 1/2 and the stop moves to breakeven. Then the first close under the 10-day ends the trade (a switch picks the 20-day). CLOSED shows the reason and the date. Trades are followed for up to 60 sessions.",
      "Extra columns, not rules: market light (Nifty 50 with Smallcap 250, or SENSEX if Smallcap 250 is not in the cache), results within 5 days, 20-day traded value, a 5% or 10% price band, and shares for 0.5% risk of a Rs 10 lakh account, at most 25% of it.",
    ] },
    marios: { title: SCAN, note: LIQUID_LINE, lines: [
      "Marios Stamatoudis's own rules: ADR above 2.5% (he prefers 3.5%). Buy the opening range breakout. Stop at the low of the day, less than 1 ATR away. Take partials at 2.5 to 3 ADRs above the entry (ADRs, not R). Move the stop to breakeven after the partial. Trail the rest with the 10, 20 or 50-day average.",
      "The slides that spread online are Financial Wisdom TV's summary of his method, not his own words.",
      "This page uses daily bars and the same base and entry checks as the Qullamaggie page, with these changes: ADR at least 2.5% (3.5% or more is marked preferred), the prior run can be up to 126 days before the base, and the last 5 base days must have lower volume than the 50-day average.",
      "The stop check uses ADR instead of ATR on both pages: more than 1 ADR from the fill to the low is Too wide, skip. A weak day-1 close (under the fill, or less than half the risk above it) is flagged.",
      "Selling: sell 1/4 to 1/3 when the high reaches the entry plus 2.5 ADRs (the 3 ADR level is shown too), then move the stop to breakeven. A close under the 10-day sells 1/3 of the rest. A close under the 20-day sells the rest and the trade shows as CLOSED with the reason and date.",
      "Extra columns, not rules: market light, results within 5 days, 20-day traded value, price band, and shares for 0.5% risk of a Rs 10 lakh account, at most 25% of it.",
    ] },
    episodic: { title: SCAN, note: LIQUID_LINE, lines: [
      "An Episodic Pivot (EP) is a big jump on surprise news, like strong results. These are Qullamaggie and Stockbee's own rules.",
      "EP day: a gap up of 10% or more at the open, or a close 8% or more above the day before, on at least 3 times normal volume (the 50-day average). Price at least ₹20. ETFs and funds are left out.",
      "EP TODAY means a strong close. Buy above the EP-day high in the next sessions. The stop is the EP-day low. EP FADED means a weak close, so no buy. WATCHING is day 2 to 5.",
      "DELAYED WATCH is day 6 to 20 (day 2 to 20 after a fade). It waits for a tight 5-day range and buys above its high. BROKEN OUT today means the price went above the buy level today.",
      "IN TRADE: on day 3 to 5 sell 1/3 to 1/2 and move the stop to breakeven. Sell the rest on the first close under the 10-day average (20-day if the stock moves less than 5% a day). CLOSED shows the result for 10 sessions.",
      "Too wide, skip means the stop is more than 1.5 normal days away. Upper circuit means no one could buy at the close. Base grade A (flat or down before the EP) is listed first.",
      "Prices are end of day only. Check guidance and other news by hand with the announcements link. Market cap is shares times the close, from saved share counts.",
    ] },
    gapup: { title: SCAN, note: "Only stocks that trade at least ₹1 crore a day on average over the last 50 days are listed, the same ₹1 crore line the Episodic Pivot scan uses.", lines: [
      "A gap up is a day when a stock opens above the day before's high. Gap % is how far the open is above that high. The gap must be at least 3%.",
      "The gap day needs at least 1.5 times the average volume of the 50 days before it, and a close of at least ₹20. ETFs and funds are left out.",
      "The gap-day low is the hold level. A stock stays on the list only while every close since the gap day is at or above it. One close below it and the stock is dropped.",
      "Only gaps in the last 21 trading days, today included, are shown. If a stock gapped more than once, you see the most recent gap that still holds. Newest gaps come first, then the biggest.",
      "GAP UP today means the gap was on the latest day. GAP HOLDING means an older gap that still holds. Gap Up does not feed Buy setups.",
      "Close in gap-day range shows where the gap day closed: 0 is the low of the day and 100 is the high. Also on shows the other scanners that list the same stock.",
    ] },
    canslim: { title: SCAN, note: LIQUID_LINE, lines: [
      "William O'Neil's method. It checks earnings growth versus a year ago, how close price is to its 52-week high, and trading volume.",
      "It also checks strength versus the Nifty 50 (SENSEX for BSE-only stocks), shareholding changes, and whether the market is in an uptrend.",
    ] },
    leaders: { title: SCAN, note: LIQUID_LINE, lines: [
      "Stocks that are a READY or just broken out VCP, or a strict CANSLIM pass. One row per stock.",
      "The best names are on both. Use the On VCP and On CANSLIM filters to see only the stocks on both lists.",
    ] },
    buysetups: { title: SCAN, note: LIQUID_LINE, lines: [
      "The main shortlist. A stock is listed when VCP, Box, Flag, Qullamaggie, Marios, Episodic Pivot (EP) or CANSLIM is ready or broke out today, price is above the 50-day and 200-day averages, and the stop is 8% or less away. Qullamaggie, Marios and EP names marked Too wide, skip are left out.",
      "An EP counts as ready on the EP day and days 2 to 5, with the buy above the EP-day high. Faded EPs, delayed EPs and stocks locked at the upper circuit are left out.",
      "It is also checked against the company score and the market trend. Show anyway lists the greyed-out ones.",
    ] },
    week52: { title: SCAN, note: LIQUID_LINE, lines: [
      "Where each stock sits in its yearly range.",
      "It flags new highs, new lows, closes within 5% of the high, and new highs made on 1.5 times normal volume.",
    ] },
    breakouts: { title: SCAN, note: ALL_SCORED_LINE, lines: [
      "Only stocks within 1% of their 52-week high.",
    ] },
    pullbacks: { title: SCAN, note: ALL_SCORED_LINE, lines: [
      "Stocks in an uptrend (above the 50-day and 200-day averages) that have dipped back into the buy zone near the 20-day average.",
      "RSI must be under 70, and the stock must not be scored AVOID.",
    ] },
    highvol: { title: SCAN, note: "Only stocks that closed above ₹20 and traded at least ₹1 crore that day are listed.", lines: [
      "Stocks trading 2 times or more their usual 50-day volume, marked as a buying day (up) or a selling day (down).",
      "Filters go from 1.5x to 5x.",
    ] },
    growth: { title: SCAN, note: LIQUID_LINE, lines: [
      "Revenue growth of 15% or more, and not scored AVOID.",
    ] },
    quality: { title: SCAN, note: LIQUID_LINE, lines: [
      "Good return on equity (it earns the plus 1 point) and debt under 1.5 times equity. Not scored AVOID.",
    ] },
    dividend: { title: SCAN, note: LIQUID_LINE, lines: [
      "Dividend yield of 1.5% or more, and not scored AVOID.",
    ] },
    wheel: { title: SCAN, note: LIQUID_LINE, lines: [
      "Big, heavily traded stocks (₹20 crore or more a day) in an uptrend (above the 200-day average).",
      "RSI under 70, not extended or in a downtrend, and not AVOID. Stock list only, no option contract picks.",
    ] },
    today: { lines: [
      "A quick look at the whole market today. The cards show the Nifty 50, advancers and decliners, new 52-week highs and lows, put/call mood, India VIX, the 10-year rate, and the rupee.",
      "Below that are today's sector moves, market breadth, and the latest alerts.",
    ] },
    flows: { lines: [
      "How much foreign investors (FII) and Indian institutions (DII) bought or sold in the cash market, in crore rupees. Green is net buying. Red is net selling.",
      "It shows 5-day, 20-day, month and year totals, a chart against the index, and index-futures positions when NSE has them.",
    ] },
    top: { lines: [
      "Every stock on the desk ranked by its desk score, highest first.",
      "Each row shows the label (BUY, HOLD or AVOID), the trend, and an entry zone, stop and target to study. The Liquid filter starts on Yes. Pick All to see quieter stocks too.",
    ] },
    scorecard: { lines: [
      "One stock at a time. Type a ticker to see its total score and how each point was earned, versus its own 3-year average and versus its sector.",
      "It also shows the plan (entry, stop, target), recent earnings surprises, and headlines.",
    ] },
    watchlist: { lines: [
      "Your holdings and your watchlist, with portfolio value, today's profit or loss, total gain, and the desk score of each stock.",
      "Change the lists in input/holdings.csv and input/my_watchlist.csv.",
    ] },
    alerts: { lines: [
      "What changed since the last run: label changes, breakouts, and stocks that moved into their entry zone.",
      "Nothing is sent to your phone or email.",
    ] },
    backtest: { lines: [
      "Tests the desk score on past data, using only what was public at the time. It compares the top 20 stocks with the Nifty 50 over 1, 4 and 12 weeks.",
      "If it says there is no clear edge, believe it. Past results are not future results.",
    ] },
    calendar: { lines: [
      "Upcoming earnings report dates for stocks on the desk, and how many days away they are.",
      "It also shows the last result versus the estimate and how much the stock moved the next day. Your holdings are marked Held.",
    ] },
    heatmap: { lines: [
      "Earnings results by quarter for each stock. Green is a beat, red is a miss, and grey is in line with the estimate.",
    ] },
    cards: { lines: [
      "A simple A to F report card for each company.",
      "The grade comes from a fixed rule on recent earnings beats and revenue growth versus the company's own history. It is not a trade.",
    ] },
    putcall: { lines: [
      "The Nifty put/call ratio. It is put open interest divided by call open interest, with a 5-day average and a mood zone.",
      "Market mood only, not a trade.",
    ] },
    walls: { lines: [
      "The strike prices with the most open interest for puts and calls. Traders often watch them as a floor and a ceiling.",
      "Market mood only, not a contract to trade.",
    ] },
    analysts: { lines: [
      "What analysts think of each stock: the average rating from 1 (strong buy) to 5 (sell), the median price target, and the upside from today's price.",
    ] },
    thirteen: { lines: [
      "Who owns each company: promoters, foreign institutions (FII), Indian institutions (DII), and the public.",
      "The change is versus the prior quarter. This is not a buy or sell list.",
    ] },
    aaii: { lines: [
      "India market mood. There is no Indian version of the AAII survey, so this page uses India VIX (the fear gauge) and the day's FII and DII cash flow in crore.",
    ] },
    insiders: { lines: [
      "Insider buy and sell counts over the last three months, from the NSE insider (PIT) file.",
      "If NSE blocks the file, the cells stay blank.",
    ] },
    headlines: { lines: [
      "Recent news headlines with a simple tone label.",
      "The tone comes from a word rule (beat, upgrade, probe, and similar words). It does not change the desk score.",
    ] },
    xly: { lines: [
      "The Nifty Auto index divided by the Nifty FMCG index.",
      "When the ratio is above its own 50-day average, the page says risk on. That means buyers prefer cars and big spending over everyday goods.",
    ] },
    financials: { lines: [
      "Each money measure for a stock, now versus its own 3-year average and versus the sector median.",
      "The Better when column says if a lower or a higher number earns the point.",
    ] },
    tracker: { lines: [
      "Past earnings reports for one stock: actual EPS versus the estimate, the surprise %, and whether it was a beat or a miss.",
      "Reports that have a date but no result yet are counted as upcoming.",
    ] },
    company: { lines: [
      "Yearly revenue, profit, EPS, and margins for one company, with charts.",
      "It also shows P/E, price to sales, and price to free cash flow.",
    ] },
    divfund: { lines: [
      "The dividend yield of every stock on the desk.",
      "A yield of 0 means the company does not pay. A dash means the yield could not be read.",
    ] },
    macro: { lines: [
      "India economy numbers such as inflation (CPI), GDP, and industry growth from the World Bank, plus the rupee.",
      "Signal is +1 when the surprise is the kind that usually helps stocks. It is a sketch, not a forecast.",
    ] },
    secmacro: { lines: [
      "Each Nifty sector index with its day, week, month and year moves, plus simple growth, inflation, and rate scores.",
      "The scores are a rule of thumb, not a forecast.",
    ] },
    histpe: { lines: [
      "The middle (median) trailing P/E of the stocks on this desk, month by month.",
      "There is no free official Nifty 50 P/E history, so that line is not drawn.",
    ] },
    trends: { lines: [
      "Shows if each stock is above its 20, 50, 100, and 200-day averages.",
      "Uptrend means above all four. Downtrend means below all four. Anything else is Mixed.",
    ] },
    gainers: { lines: [
      "The biggest gainers and losers among the desk's stocks in the latest session, by day % change.",
    ] },
    breadth: { lines: [
      "How much of the market is going up. It shows the share of the desk's stocks above each moving average over time.",
      "More stocks above their averages means a healthier market.",
    ] },
    secperf: { lines: [
      "Sector returns for the day, week, month, 3 months, and year, plus the share of stocks above their 50-day average.",
      "Each sector is an equal-weight average of the desk's stocks, not the sector index.",
    ] },
    heatmaps: { lines: [
      "A color grid of each stock's own return over 1 day, 1 week, 1 month, and the year so far. Green is up and red is down.",
      "It also shows if the stock is above its 20, 50, 100, and 200-day averages.",
    ] },
    rotation: { lines: [
      "Which Nifty sectors are leading or lagging the Nifty 50 (you can switch to SENSEX). Leading is top right, Weakening is bottom right, Lagging is bottom left, and Improving is top left.",
      "The table ranks sectors by a score that blends strength, how many stocks are above their averages or near a high, buy setups, and the average desk score.",
    ] },
    updates: { lines: [
      "Checks that the data is fresh. OK means the source answered. CACHED means an older copy was used. MISSING means there is no copy.",
      "It also shows how much of the financials and shareholding is on file, and which page switches are on.",
    ] },
    chartviewer: { title: "What this page does", lines: [
      "One big chart at a time. Pick a list at the top: every stock on any scanner, one scanner, or your watchlist.",
      "All scanner stocks puts the stocks found by the most scanners first, then the strongest.",
      "Tap Full screen. Swipe right for the next chart and left to go back. The Swipe chip flips that. The arrows and the left and right keys work too.",
      "Drag the chart slowly to see older days on the same chart, and pinch to zoom. Flick fast, or swipe on the top row, to change the chart. On a phone the chip bar scrolls sideways. The Drag chip switches between Drag: move chart and Drag: next chart.",
      "The 3M, 6M, 1Y and All chips change how much of the saved history shows.",
      "Tap the chips to show or hide the 10, 20, 50, 150 and 200-day averages and the volume. Your choice is saved on this device.",
      "The box in the lower right shows every scanner the stock is on, its status, and the reason. Tap it for more. The Reasons chip hides it.",
      "It uses the daily prices the desk already saves. Nothing new is downloaded.",
    ], splitNeedsToggle: true, splitLines: [
      "One big chart at a time. Pick Technical or Fundamental at the top, then a list: every stock in that group, one scanner, Buy setups, or your watchlist.",
      "Technical is the chart scanners (VCP, breakouts, Episodic Pivot, Gap Up, 52-week, High volume, Pullbacks, Liquid stocks). Fundamental is CANSLIM, Leaders, Growth, Quality and Dividend. Your last choice is remembered on this device.",
      "All technical stocks and All fundamental stocks put the stocks found by the most scanners in that group first, then the strongest. The box on the chart shows only that group's reasons, plus Buy setups and your watchlist.",
      "Tap Full screen. Swipe right for the next chart and left to go back. The Swipe chip flips that. The arrows and the left and right keys work too.",
      "Drag the chart slowly to see older days on the same chart, and pinch to zoom. Flick fast, or swipe on the top row, to change the chart. On a phone the chip bar scrolls sideways. The Drag chip switches between Drag: move chart and Drag: next chart.",
      "The 3M, 6M, 1Y and All chips change how much of the saved history shows.",
      "Tap the chips to show or hide the 10, 20, 50, 150 and 200-day averages and the volume. Your choice is saved on this device.",
      "The box in the lower right shows every scanner the stock is on, its status, and the reason. Tap it for more. The Reasons chip hides it.",
      "It uses the daily prices the desk already saves. Nothing new is downloaded.",
    ] },
    help: { lines: [
      "Plain-English answers about how the desk works, and a list of every setting.",
      "Start here if a word or label is unclear.",
    ] },
  };

  window.DESK_PAGES = {
    today: { files: ["market_today.csv", "breadth_history.csv", "sectors.csv", "alerts.csv", "fii_flows.csv"], optional: ["high_volume.csv"], render: renderToday },
    flows: { files: ["fii_flows.csv", "participant_oi.csv"], render: renderFlows },
    top: { files: ["scores.csv"], render: renderTop },
    scorecard: { files: ["scores.csv", "score_details.csv", "news.csv", "earnings_history.csv"], render: renderScorecard },
    watchlist: { files: ["portfolio.csv", "portfolio_summary.csv", "watchlist.csv"], render: renderWatch },
    alerts: { files: ["alerts.csv", "score_changes.csv"], render: renderAlerts },
    backtest: { files: ["backtest_summary.csv", "backtest_equity.csv", "backtest_buckets.csv", "backtest_yearly.csv", "backtest_notes.csv"], render: renderBacktest },
    growth: growth,
    quality: quality,
    dividend: dividend,
    wheel: wheel,
    vcp: vcp,
    canslim: canslim,
    box: box,
    flag: flag,
    qullamaggie: qullamaggie,
    marios: marios,
    episodic: episodic,
    leaders: leaders,
    calendar: { files: ["earnings_calendar.csv"], render: renderCalendar },
    heatmap: { files: ["earnings_heatmap.csv"], render: renderHeat },
    cards: { files: ["earnings_cards.csv"], render: renderCards },
    putcall: { files: ["put_call.csv"], render: renderPutCall },
    walls: { files: ["option_walls.csv", "scores.csv"], render: renderWalls },
    analysts: { files: ["analyst_ratings.csv"], render: renderAnalysts },
    thirteen: { files: ["institutional_13f.csv"], render: render13f },
    aaii: { files: ["aaii_sentiment.csv"], render: renderAaii },
    insiders: { files: ["insider_trading.csv"], render: renderInsiders },
    headlines: { files: ["headline_sentiment.csv"], render: renderHeadlines },
    xly: { files: ["xly_xlp.csv"], render: renderXly },
    financials: { files: ["financials_summary.csv"], render: renderFinancials },
    tracker: { files: ["earnings_tracker.csv"], render: renderTracker },
    company: { files: ["company_financials.csv"], render: renderCompany },
    divfund: { files: ["dividend_scanner.csv"], render: renderDivFund },
    macro: { files: ["macro_screener.csv"], render: renderMacro },
    secmacro: { files: ["sector_macro.csv", "sectors.csv"], render: renderSecMacro },
    histpe: { files: ["historical_pe.csv"], render: renderHist },
    breakouts: { files: ["breakouts.csv"], render: renderBreakouts },
    trends: { files: ["trends.csv"], render: renderTrends },
    pullbacks: pullbacks,
    gainers: { files: ["gainers_losers.csv"], render: renderGainers },
    breadth: { files: ["breadth_history.csv", "market_today.csv"], render: renderBreadth },
    secperf: { files: ["sector_performance.csv"], render: renderSecPerf },
    heatmaps: { files: ["heatmaps.csv"], render: renderHeatmaps },
    updates: { files: ["updates_log.csv", "freshness.csv", "backfill_progress.csv"], render: renderUpdates },
    buysetups: { files: ["buy_setups.csv", "backfill_progress.csv"], render: renderBuySetups },
    week52: { files: ["scanner_52w.csv", "highs_lows_history.csv"], render: renderWeek52 },
    highvol: { files: ["high_volume.csv"], optional: ["company_lines.csv"], render: renderHighVolume },
    gapup: { files: ["scanner_gap_up.csv"], render: renderGapUp },
    rotation: { files: ["sector_rotation.csv", "sector_rotation_tails.csv", "sector_rotation_history.csv", "scores.csv"], render: renderRotation },
    help: { files: ["help.csv", "settings.csv"], render: renderHelp },
    chartviewer: { files: [], optional: D.chartViewerFiles, render: D.renderChartViewer },
  };
  Object.keys(ABOUT).forEach((id) => {
    if (window.DESK_PAGES[id]) window.DESK_PAGES[id].about = ABOUT[id];
  });

  D.boot();
})();
