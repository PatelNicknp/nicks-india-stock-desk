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
    "include_watchlist": True, "include_gap_up": True, "include_trends": True, "scanner_links": True, "fullscreen": True, "native_fullscreen_ios": False,
    "swipe": True, "swipe_right_is_next": True, "flip_toggle": True, "chart_touch_pan": True, "drag_mode_toggle": True,
    "swipe_min_px": 80, "swipe_max_ms": 300, "swipe_ratio": 1.5,
    "arrows": True, "keyboard": True, "counter": True, "preload_next": True, "ma_chips": True,
    "ma_10": False, "ma_20": False, "ma_50": True, "ma_150": True, "ma_200": True, "volume": True,
    "volume_toggle": True, "reason_box": True, "reason_box_toggle": True, "reason_max_chars": 110,
    "reason_collapsed_items": 3, "company_line": True, "day_change": True, "range_months": 6, "range_months_phone": 3,
    "range_chips": False, "group_toggle": True, "default_group": "technical",
    "reason_box_top_left": True, "last_candle_gap_px": 12, "candle_toggle": True, "default_candles": "daily",
    "style_toggle": True, "default_style": "candles",
    "dense_default": True, "target_bar_spacing": 5.8, "min_bar_spacing_px": 3, "max_bar_spacing_px": 8,
    "range_months_weekly": 24, "range_months_weekly_phone": 12,
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
    for word in ("feature.chart_viewer", "Swipe right for the next chart", "top left", "chart_viewer.reason_box_top_left", "chart_viewer.candle_toggle", "chart_viewer.style_toggle", "Weekly", "Nothing new is downloaded",
                 "every status except CLOSED", "do not add to the count",
                 "VCP", "CANSLIM", "Box", "Flag", "Qullamaggie", "Marios", "Episodic Pivot", "Buy setups",
                 "52-week breakouts", "Pullbacks", "Leaders", "High volume", "watchlist",
                 "Drag the chart slowly", "pinch", "flick it fast", "A slow drag never changes the chart",
                 "top row (ticker, price and counter) always changes the chart", "scrolls the chips", "just left of the price axis", "stays when you turn the device", "Drag: move chart", "Drag: next chart", "pinch zoom is off", "chart_viewer.drag_mode_toggle", "every saved daily bar",
                 "3M, 6M, 1Y and All", "chart_viewer.range_chips", "chart_viewer.chart_touch_pan",
                 "chart_viewer.dense_default", "chart_viewer.target_bar_spacing 5.8", "3 pixels", "8 pixels",
                 "chart_viewer.range_months_weekly"):
        assert word in text, word
    saved = pd.read_csv(os.path.join(ROOT, "data", "help.csv"))
    assert "Chart Viewer" in set(saved["topic"])


def test_pages_publish_trends_csv_where_the_viewer_fetches_it():
    yml = _read(".github", "workflows", "pages.yml")
    assert "cp -a data/. _site/data/" in yml
    assert "test -s _site/data/trends.csv" in yml
    assert "data/**" in yml
    js = _read("site", "js", "desk.js")
    start = js.index("function csvUrl")
    block = js[start:js.index("function loadCsv", start)]
    assert 'new URL("data/" + name, location.href)' in block
    assert "raw.githubusercontent.com" not in block
    assert os.path.exists(os.path.join(ROOT, "data", "trends.csv"))
    assert os.path.getsize(os.path.join(ROOT, "data", "trends.csv")) > 0


def test_trends_is_a_technical_chart_list():
    cfg = _cfg()
    assert cfg["chart_viewer"]["include_trends"] is True
    assert cfg["scanner_groups"]["trends"] == "technical"
    note = cfg["scanner_groups"]["_note"]
    assert "Trends, Dividend fundamentals" not in note
    assert "Dividend fundamentals, Stock scorecard and Top stocks are not on the Chart Viewer" in note
    desk = _read("site", "js", "desk.js")
    assert 'id: "trends"' in desk and 'file: "trends.csv"' in desk and 'opt: "include_trends"' in desk
    assert 'case "trend"' in desk and "Above the 20, 50, 100, and 200-day averages" in desk
    text = dict(tables.help_rows())["Chart Viewer"]
    assert "chart_viewer.include_trends" in text and "Trends" in text
    assert "\u2014" not in text


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
              "scanner_qullamaggie.csv", "scanner_marios.csv", "scanner_episodic_pivot.csv", "scanner_gap_up.csv", "scanner_leaders.csv",
              "scanner_52w.csv", "breakouts.csv", "high_volume.csv", "pullbacks.csv", "trends.csv", "scanner_growth.csv",
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
    assert "native_fullscreen_ios" in block and "maxTouchPoints" in block and "iPad" in block
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


def test_drag_pans_and_flick_changes_chart():
    desk = _read("site", "js", "desk.js")
    start = desk.index("function renderChartViewer(ctx)")
    block = desk[start:desk.index("    // Full screen: the real Fullscreen API", start)]
    assert 'cvRead("desk-cv-drag-pan")' in block and 'cvStore("desk-cv-drag-pan", dragPan)' in block
    assert '"Drag: " + (dragPan ? "move chart" : "next chart")' in block
    assert "horzTouchDrag: dragPan" in block and "pinch: dragPan" in block and "kineticScroll: { touch: false" in block
    assert 'inChart && dragPan && ms > cvOpt("swipe_max_ms")' in block
    assert 'cvOpt("drag_mode_toggle")' in block and "cvSwipeZone(" in block and 'zone === "scroll"' in block
    assert "let lo = from - 0.5, hi = last + pad;" in block and "setRange({ from: lo, to: hi })" in block and "cvPadBars(last - from + 1, w," in block
    assert "if (w < 120)" in block and "ResizeObserver(viewSoon)" in block
    assert "function cvPadBars(" in desk
    assert "const readUserRange = () =>" in block and "userRange = carryRange;" in block and "applyView(true)" in block and "minBarSpacing: 0.3" in block and "const CV_KEEP = 6;" in block
    assert 'stage.addEventListener("touchstart"' in block
    assert 'cvOpt("candle_toggle")' in block and 'cvRead("desk-cv-weekly")' in block and "function cvWeekly(" in desk
    assert 'cvOpt("style_toggle")' in block and 'cvRead("desk-cv-ohlc-bars")' in block and "LC.BarSeries" in block
    assert 'cvOpt("reason_box_top_left")' in block and "cvGapBars(" in block
    assert 'cvOpt("range_chips")' in block and '"3M"' in block and '"All"' in block
    assert 'cvOpt("dense_default")' in block and 'cvOpt("target_bar_spacing")' in block
    assert 'cvOpt("min_bar_spacing_px")' in block and 'cvOpt("max_bar_spacing_px")' in block
    assert "function cvDenseRange(" in desk
    assert 'cvOpt("range_months_weekly")' in block and 'cvOpt("range_months_weekly_phone")' in block
    pages = _read("site", "js", "pages.js")
    i = pages.index("chartviewer: { title:")
    desc = pages[i:pages.index("] },", i)]
    assert "\u2014" not in desc
    assert "Drag the chart slowly" in desc and "Daily and Weekly" in desc and "Candles and Bars" in desc
    assert "\u2014" not in _cfg()["chart_viewer"]["_note"]
