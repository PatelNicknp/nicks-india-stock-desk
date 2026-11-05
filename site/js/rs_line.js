/* RS line for the Chart Viewer: stock close divided by the Nifty 50 close.
   No download. Weekly bars use the same Monday week as the chart's weekly candles.
   A new 52-week high is strictly above the prior 252 daily bars, or 52 weekly bars.
   "before" means that high in the line happened on a bar whose price did not make
   a new 52-week high. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.rsLine = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const DAILY = 252;
  const WEEKLY = 52;

  function weekKey(iso) {
    const d = new Date(String(iso).slice(0, 10) + "T00:00:00Z");
    if (isNaN(d.getTime())) return "";
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return d.toISOString().slice(0, 10);
  }

  function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function foldWeeks(bars) {
    const out = [];
    let cur = null;
    let key = "";
    (bars || []).forEach((b) => {
      const day = String(b.date || "").slice(0, 10);
      const k = weekKey(day);
      if (!k) return;
      const c = num(b.c != null ? b.c : b.close);
      if (c == null) return;
      const h = num(b.h != null ? b.h : b.high);
      const high = h == null ? c : h;
      if (!cur || k !== key) {
        key = k;
        cur = { date: day, c: c, h: high, key: k };
        out.push(cur);
        return;
      }
      cur.h = Math.max(cur.h, high);
      cur.c = c;
    });
    return out;
  }

  function dailyBars(bars) {
    const out = [];
    (bars || []).forEach((b) => {
      const day = String(b.date || "").slice(0, 10);
      if (!day) return;
      const c = num(b.c != null ? b.c : b.close);
      if (c == null) return;
      const h = num(b.h != null ? b.h : b.high);
      out.push({ date: day, c: c, h: h == null ? c : h, key: day });
    });
    return out;
  }

  function maxOf(values, end, len) {
    let m = -Infinity;
    for (let i = end - len; i < end; i++) {
      if (values[i] > m) m = values[i];
    }
    return m;
  }

  function build(stockBars, niftyBars, opts) {
    const weekly = !!(opts && opts.weekly);
    const lookback = weekly ? WEEKLY : DAILY;
    const stock = weekly ? foldWeeks(stockBars) : dailyBars(stockBars);
    const nifty = weekly ? foldWeeks(niftyBars) : dailyBars(niftyBars);
    const niftyClose = new Map();
    nifty.forEach((b) => { niftyClose.set(b.key, b.c); });
    const points = [];
    stock.forEach((b) => {
      const base = niftyClose.get(b.key);
      if (!(base > 0)) return;
      points.push({ time: b.date, value: b.c / base, high: b.h });
    });
    const markers = [];
    const rs = points.map((p) => p.value);
    const px = points.map((p) => p.high);
    for (let i = lookback; i < points.length; i++) {
      if (!(points[i].value > maxOf(rs, i, lookback))) continue;
      const priceAlso = points[i].high > maxOf(px, i, lookback);
      markers.push({ time: points[i].time, kind: priceAlso ? "with" : "before" });
    }
    return { points: points, markers: markers, lookback: lookback };
  }

  return { build: build, weekKey: weekKey, DAILY: DAILY, WEEKLY: WEEKLY };
});
