"""Per-stock shareholding box: scorecard, Chart Viewer chip, and the on/off switch."""
import json
import os
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tables  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _cfg():
    return json.loads(_read("config.json"))


def test_switch_defaults_on_and_is_saved():
    cfg = _cfg()
    assert cfg["features"]["stock_shareholding"] is True
    rows = tables.settings_rows(cfg)
    settings = dict(zip(rows["setting"], rows["value"]))
    assert settings["feature.stock_shareholding"] is True
    saved = pd.read_csv(os.path.join(ROOT, "data", "settings.csv"))
    assert "feature.stock_shareholding" in set(saved["setting"])
    got = saved[saved["setting"] == "feature.stock_shareholding"]["value"].iloc[0]
    assert str(got).lower() == "true"


def test_help_uses_simple_words():
    text = dict(tables.help_rows())["Stock shareholding"]
    assert "\u2014" not in text
    for word in ("feature.stock_shareholding", "promoter", "FII", "DII", "public", "Pledge",
                 "Nothing new is downloaded", "Shareholding chip", "Chart Viewer", "scorecard"):
        assert word in text, word
    saved = pd.read_csv(os.path.join(ROOT, "data", "help.csv"))
    assert "Stock shareholding" in set(saved["topic"])
    plain = saved[saved["topic"] == "Stock shareholding"]["plain_english"].iloc[0]
    assert "\u2014" not in plain and "feature.stock_shareholding" in plain


def test_scorecard_and_chart_viewer_share_the_file():
    pages = _read("site", "js", "pages.js")
    assert 'optional: ["institutional_13f.csv", "stock_canslim.csv"]' in pages
    assert "stockShareHtml(ctx, ticker, row)" in pages
    assert 'panelOff("feature.stock_shareholding")' in pages
    assert "feature.stock_shareholding" in pages[pages.index("scorecard: { lines:"):pages.index("watchlist: { lines:")]
    desk = _read("site", "js", "desk.js")
    assert '"institutional_13f.csv"' in desk
    assert 'chip("hold", "Shareholding"' in desk
    assert 'featureOn("feature.stock_shareholding")' in desk
    assert 'id === "hold"' in desk
    assert "function shareholdingHtml(" in desk and "function shareholdingOf(" in desk
    start = desk.index("const SHARE_FIELDS")
    block = desk[start:desk.index("function renderChartViewer", start)]
    assert "\u2014" not in block
    assert "Pledge" in block and "public_pct" in block and "pledge_pct" in block
    css = _read("site", "css", "desk.css")
    assert ".sh-up{color:var(--green)" in css and ".sh-dn{color:var(--red)" in css
    assert ".cv-hold[hidden]{display:none}" in css
    assert "\u2014" not in css[css.index(".sh-box"):css.index(".tf-grid{grid-template-columns:minmax(0,1fr)")]


def test_box_html_rules():
    script = os.path.join(ROOT, "tests", "shareholding_check.js")
    proc = subprocess.run(["node", script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
