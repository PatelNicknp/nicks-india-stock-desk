"""Every page has a plain-English description box with its own switch."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "site"))

import build_pages  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _about_block():
    js = _read("site", "js", "pages.js")
    start = js.index("const LIQUID_LINE")
    end = js.index("window.DESK_PAGES = {", start)
    return js[start:end]


class PageDescriptionTests(unittest.TestCase):
    def test_switch_in_config_defaults_on(self):
        cfg = json.loads(_read("config.json"))
        self.assertIs(cfg["features"].get("page_descriptions"), True)

    def test_desk_js_uses_the_switch(self):
        js = _read("site", "js", "desk.js")
        self.assertIn('featureOn("feature.page_descriptions")', js)

    def test_every_page_has_a_description(self):
        block = _about_block()
        keys = set(re.findall(r"^    ([a-z0-9]+): \{", block, re.M))
        pids = {pid for _f, pid, _t in build_pages.PAGES}
        self.assertEqual(sorted(pids - keys), [])
        self.assertEqual(sorted(keys - pids), [])

    def test_plain_words(self):
        block = _about_block()
        self.assertNotIn("\u2014", block)
        self.assertNotIn("TradingView\" ", block)
        self.assertNotIn("Open in TradingView", block)

    def test_numbers_match_the_code(self):
        cfg = json.loads(_read("config.json"))
        block = _about_block()
        liq = cfg["liquidity"]
        self.assertEqual(liq["min_median_traded_value"], 10_000_000)
        self.assertEqual(liq["median_days"], 20)
        self.assertIn("at least ₹1 crore a day", block)
        self.assertIn("last 20 days", block)
        sc = cfg["scoring"]
        self.assertIn("Revenue growth of %d%% or more" % sc["growth_min_pct"], block)
        self.assertIn("debt under %s times equity" % sc["quality_max_de"], block)
        self.assertIn("Dividend yield of %s%% or more" % sc["dividend_min_pct"], block)
        self.assertIn("₹%d crore or more a day" % (sc["wheel_min_dollar_volume"] // 10_000_000), block)


if __name__ == "__main__":
    unittest.main()
