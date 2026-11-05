const assert = require("assert");
const rs = require("../site/js/rs_line.js");

function days(n, start) {
  const out = [];
  const d = new Date(start + "T00:00:00Z");
  while (out.length < n) {
    const wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6) out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

function bars(dates, closeOf, highOf) {
  return dates.map((date, i) => ({ date: date, c: closeOf(i), h: highOf ? highOf(i) : closeOf(i) }));
}

const dates = days(300, "2024-01-02");

// Rising price and a flat index: every new RS high is also a price high.
const rising = rs.build(
  bars(dates, (i) => 100 + i),
  bars(dates, () => 1000),
  { weekly: false }
);
assert.strictEqual(rising.points.length, 300);
assert.ok(Math.abs(rising.points[10].value - 110 / 1000) < 1e-12);
assert.ok(rising.markers.length > 0);
assert.ok(rising.markers.every((m) => m.kind === "with"));
assert.strictEqual(rising.markers[0].time, dates[252]);

// Flat price, falling index: the line makes highs before the price does.
const lead = rs.build(
  bars(dates, () => 100, () => 100),
  bars(dates, (i) => 1000 - i),
  { weekly: false }
);
assert.ok(lead.markers.length > 0);
assert.ok(lead.markers.every((m) => m.kind === "before"));

// Under a year: the line is drawn, and there is no 52-week dot yet.
const shortDates = dates.slice(0, 200);
const young = rs.build(
  bars(shortDates, (i) => 50 + i),
  bars(shortDates, () => 200),
  { weekly: false }
);
assert.strictEqual(young.points.length, 200);
assert.strictEqual(young.markers.length, 0);

// A zero index close is left out. It is not a point on the line.
const hole = dates.slice(0, 10);
const nifty = bars(hole, (i) => (i === 3 ? 0 : 100));
const gappy = rs.build(bars(hole, () => 50), nifty, { weekly: false });
assert.strictEqual(gappy.points.length, 9);
assert.ok(gappy.points.every((p) => p.time !== hole[3]));

// Weekly uses 52 bars, and the point is dated like the chart's weekly candle.
const weekly = rs.build(
  bars(dates, (i) => 80 + i * 0.2),
  bars(dates, () => 500),
  { weekly: true }
);
assert.strictEqual(weekly.lookback, 52);
assert.ok(weekly.points.length >= 52);
assert.ok(weekly.points.length < dates.length);
assert.strictEqual(rs.weekKey(weekly.points[0].time), rs.weekKey(dates[0]));
assert.ok(weekly.markers.length > 0);
assert.ok(weekly.markers.every((m) => m.kind === "with"));

console.log("rs line ok", rising.markers.length, "with", lead.markers.length, "before");
