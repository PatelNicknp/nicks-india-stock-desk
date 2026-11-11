/* Shareholding box: percents, quarter change colors, public when present, pledge only when the row has it. */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const noop = () => {};
const sandbox = {
  console: console,
  document: {
    documentElement: { setAttribute: noop, removeAttribute: noop },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener: noop,
  },
  localStorage: { getItem() { return null; }, setItem() {} },
  addEventListener: noop,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "site", "js", "desk.js"), "utf8"), sandbox);
const D = sandbox.window.Desk;
assert.ok(D && D.shareholdingHtml && D.shareholdingOf);

const html = D.shareholdingHtml({
  promoter_pct: "74.99", promoter_chg: "0",
  fii_pct: "0.40", fii_chg: "0.02",
  dii_pct: "8.99", dii_chg: "-0.22",
  public_pct: "15.62", public_chg: "",
  as_of: "2026-09-30",
});
assert.ok(html.includes("Promoter") && html.includes("74.99%"), html);
assert.ok(html.includes("FII") && html.includes("0.40%"), html);
assert.ok(html.includes("DII") && html.includes("8.99%"), html);
assert.ok(html.includes("Public") && html.includes("15.62%"), html);
assert.ok(html.includes("sh-up") && html.includes("0.02 pts"), html);
assert.ok(html.includes("sh-dn") && html.includes("0.22 pts"), html);
assert.ok(html.includes("sh-na") && html.includes("–"), html);
assert.ok(!html.includes("quarter change n/a"), html);
assert.ok(!html.includes("flat vs last quarter"), html);
assert.ok(html.includes("as of 2026-09-30"), html);
assert.ok(!html.includes("Pledge"), html);
assert.ok(!html.includes("\u2014"), html);

const noPublic = D.shareholdingHtml({ promoter_pct: "50", fii_pct: "10", dii_pct: "20" });
assert.ok(!noPublic.includes("Public"), noPublic);

const pledged = D.shareholdingHtml({
  promoter_pct: "60", promoter_chg: "1",
  fii_pct: "10", dii_pct: "10",
  pledge_pct: "4.5", pledge_chg: "-0.5",
});
assert.ok(pledged.includes("Pledge") && pledged.includes("4.50%"), pledged);
assert.ok(pledged.includes("sh-dn") && pledged.includes("0.50 pts"), pledged);
assert.ok(!pledged.includes("\u2014"), pledged);

const named = D.shareholdingHtml({ promoter_pct: "10", pledged_pct: "2" });
assert.ok(named.includes("Pledge") && named.includes("2.00%"), named);

const missing = D.shareholdingHtml(null);
assert.ok(missing.includes("not on file"), missing);
assert.ok(!missing.includes("Pledge"), missing);
const blank = D.shareholdingHtml({ promoter_pct: "", fii_pct: "", note: "not verified" });
assert.ok(blank.includes("not on file"), blank);

const row = D.shareholdingOf([
  { ticker: "aaa", row_type: "owner", promoter_pct: "1" },
  { ticker: "AAA", row_type: "summary", promoter_pct: "40", public_pct: "60" },
  { ticker: "BBB", row_type: "summary", promoter_pct: "9" },
], "aaa");
assert.strictEqual(row.promoter_pct, "40");
assert.strictEqual(D.shareholdingOf([], "AAA"), null);

console.log("shareholding_check ok");
