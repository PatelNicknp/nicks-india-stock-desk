"""Chart Viewer: config switches, help, settings, the page list, and a phone and tablet browser check."""
import json
import os
import re
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "site"))

import build_pages  # noqa: E402
import tables  # noqa: E402

EXPECTED = {
    "list_picker": True, "include_watching": True, "include_closed": False, "include_buy_setups": True,
    "include_watchlist": True, "scanner_links": True, "fullscreen": True, "swipe": True, "swipe_right_is_next": True,
    "flip_toggle": True, "chart_touch_pan": False, "swipe_min_px": 50, "swipe_max_ms": 700, "swipe_ratio": 1.5,
    "arrows": True, "keyboard": True, "counter": True, "preload_next": True, "ma_chips": True,
    "ma_10": False, "ma_20": False, "ma_50": True, "ma_150": True, "ma_200": True, "volume": True,
    "volume_toggle": True, "reason_box": True, "reason_box_toggle": True, "reason_max_chars": 110,
    "reason_collapsed_items": 3, "company_line": True, "day_change": True, "range_months": 6, "range_months_phone": 3,
}


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _cfg():
    return json.loads(_read("config.json"))


def test_feature_switch_and_config_block():
    cfg = _cfg()
    assert cfg["features"]["chart_viewer"] is True
    block = cfg["chart_viewer"]
    mine = {k: v for k, v in block.items() if not k.startswith("_")}
    assert mine == EXPECTED
    assert list(mine) == list(EXPECTED), "same key order as the US desk"


def test_js_defaults_match_config():
    js = _read("site", "js", "desk.js")
    m = re.search(r"const CV_DEFAULTS = \{(.*?)\};", js, re.S)
    assert m
    body = m.group(1)
    for key, value in EXPECTED.items():
        want = json.dumps(value)
        assert re.search(r"\b%s: %s(,|\s)" % (re.escape(key), re.escape(want)), body), key


def test_settings_rows_show_every_switch():
    rows = tables.settings_rows(_cfg())
    settings = dict(zip(rows["setting"], rows["value"]))
    assert settings["feature.chart_viewer"] is True
    for key, value in EXPECTED.items():
        assert settings["chart_viewer." + key] == value, key
    assert "chart_viewer._note" not in settings
    saved = pd.read_csv(os.path.join(ROOT, "data", "settings.csv"))
    saved_keys = set(saved["setting"])
    assert "feature.chart_viewer" in saved_keys
    for key in EXPECTED:
        assert "chart_viewer." + key in saved_keys, key


def test_help_row():
    topics = dict(tables.help_rows())
    text = topics["Chart Viewer"]
    assert "\u2014" not in text
    for word in ("feature.chart_viewer", "Swipe right for the next chart", "lower right", "Nothing new is downloaded",
                 "every status except CLOSED", "do not add to the count",
                 "VCP", "CANSLIM", "Box", "Flag", "Qullamaggie", "Marios", "Episodic Pivot", "Buy setups",
                 "52-week breakouts", "Pullbacks", "Leaders", "High volume", "watchlist"):
        assert word in text, word
    saved = pd.read_csv(os.path.join(ROOT, "data", "help.csv"))
    assert "Chart Viewer" in set(saved["topic"])


def test_page_list_menu_and_description():
    assert ("chart-viewer.html", "chartviewer", "Chart Viewer") in build_pages.PAGES
    assert os.path.exists(os.path.join(ROOT, "site", "chart-viewer.html"))
    assert 'data-page="chartviewer"' in _read("site", "chart-viewer.html")
    desk = _read("site", "js", "desk.js")
    assert '["Charts", [\n      ["Chart Viewer", "chart-viewer.html", "chartviewer"],' in desk
    assert 'chartviewer: "feature.chart_viewer"' in desk
    pages = _read("site", "js", "pages.js")
    assert "chartviewer: { title:" in pages
    assert "chartviewer: { files: [], optional: D.chartViewerFiles, render: D.renderChartViewer }" in pages
    assert '"chart-viewer.html"' in _read("tests", "check_site.mjs")


def test_every_scanner_is_a_source():
    desk = _read("site", "js", "desk.js")
    start = desk.index("const CV_SOURCES = [")
    block = desk[start:desk.index("const CV_MAS", start)]
    for f in ("buy_setups.csv", "scanner_vcp.csv", "scanner_canslim.csv", "scanner_box.csv", "scanner_flag.csv",
              "scanner_qullamaggie.csv", "scanner_marios.csv", "scanner_episodic_pivot.csv", "scanner_leaders.csv",
              "scanner_52w.csv", "breakouts.csv", "high_volume.csv", "pullbacks.csv", "scanner_growth.csv",
              "scanner_quality.csv", "scanner_dividend.csv", "scanner_wheel.csv", "watchlist.csv"):
        assert '"' + f + '"' in block, f
        assert os.path.exists(os.path.join(ROOT, "data", f)), f


def test_viewer_code_rules():
    desk = _read("site", "js", "desk.js")
    start = desk.index("// ---------------------------------------------------------------- Chart Viewer")
    block = desk[start:desk.index("  function navOn(items)", start)]
    assert "\u2014" not in block
    assert "Open in TradingView" not in block
    assert "alert(" not in block and "Notification" not in block
    assert "yahoo" not in block.lower()
    assert "loadTickerBars" in block and "requestFullscreen" in block and "100dvh" not in block
    css = _read("site", "css", "desk.css")
    assert "100dvh" in css and "safe-area-inset-top" in css and ".cv-stage:fullscreen" in css


def test_viewer_in_phone_and_tablet():
    script = os.path.join(ROOT, "tests", "chart_viewer_check.js")
    try:
        proc = subprocess.run(["node", script], cwd=ROOT, capture_output=True, text=True, timeout=240)
    except FileNotFoundError as exc:
        pytest.skip("node is not installed: " + str(exc))
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 2:
        pytest.skip(out.strip() or "playwright is not installed")
    assert proc.returncode == 0, out
