"""Moving average colours: the chart_colors block in config.json is what the charts use (same as US PR #40)."""
import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tables  # noqa: E402

DARK = {"10": "#22c55e", "20": "#f97316", "50": "#3b82f6", "150": "#eab308", "200": "#ef4444"}
LIGHT = {"10": "#16a34a", "20": "#ea580c", "50": "#2563eb", "150": "#ca8a04", "200": "#dc2626"}


def _cfg():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)


def _read(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


def _js_map(js, name):
    m = re.search(r"const %s = (\{[^}]*\});" % name, js)
    assert m, name
    return json.loads(m.group(1))


def _lum(h):
    def ch(x):
        x = int(x, 16) / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(h[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_chart_colors_block():
    cfg = _cfg()
    block = cfg["chart_colors"]
    assert list(block) == ["_note", "ma_colors", "ma_colors_light"]
    assert block["ma_colors"] == DARK
    assert block["ma_colors_light"] == LIGHT
    assert "\u2014" not in block["_note"]
    keys = list(cfg)
    assert keys.index("chart_colors") == keys.index("chart_viewer") + 1  # next to the chart settings
    for v in list(DARK.values()) + list(LIGHT.values()):
        assert re.fullmatch(r"#[0-9a-f]{6}", v)
    for k, v in LIGHT.items():  # every light line shows on white
        assert 1.05 / (_lum(v) + 0.05) >= 2.9, (k, v)


def test_viewer_uses_the_config_colours():
    block = _cfg()["chart_colors"]
    js = _read("site", "js", "desk.js")
    assert _js_map(js, "MA_COLORS") == block["ma_colors"]
    assert _js_map(js, "MA_COLORS_LIGHT") == block["ma_colors_light"]
    assert '"chart_colors." + block + "." + key' in js
    # Chart Viewer lines and chips.
    assert "color: maColor(d.n, d.color), lineWidth: 1" in js
    assert 'chip(d.id, "MA " + d.n, maColor(d.n, d.color), ma[d.id])' in js
    # Row charts: lines, legend, chips. SMA lines only; EMAs keep their colour.
    assert js.count("maDefColor(def)") >= 4
    assert 'def.kind === "sma" ? maColor(def.n, def.color) : def.color' in js
    assert "color: def.color" not in js and "color: d.color" not in js
    # Light colours are not in the light-mode swap table, so what the config says is what is drawn.
    light_tbl = json.loads(re.search(r"const LIGHT = (\{.*?\});", js).group(1))
    for v in block["ma_colors_light"].values():
        assert v.upper() not in light_tbl


def test_level_lines_keep_their_colours():
    pages = _read("site", "js", "pages.js")
    assert "maColor" not in pages
    for line in ['color: "#F59E0B", label: "Buy point "', 'color: "#EF4444", label: "Stop "',
                 'color: "#EF4444", label: "Hold level "', 'color: "#7C9CFF", label: "10-day "',
                 'color: "#A78BFA", label: "20-day "', 'color: "#7C9CFF", label: "Trail "']:
        assert line in pages, line
    js = _read("site", "js", "desk.js")
    assert 'color: "#EF4444", label: "52w low"' in js and 'color: "#F59E0B", label: "Buy point"' in js


def test_settings_and_help_rows():
    got = tables.settings_rows(_cfg())
    got = got.to_dict("records") if hasattr(got, "to_dict") else got
    rows = {r["setting"]: r["value"] for r in got}
    for block, colors in (("ma_colors", DARK), ("ma_colors_light", LIGHT)):
        for n, v in colors.items():
            assert rows["chart_colors.%s.%s" % (block, n)] == v
    assert not any(k.startswith("chart_colors._") for k in rows)
    saved = pd.read_csv(os.path.join(ROOT, "data", "settings.csv"), dtype=str)
    saved = dict(zip(saved["setting"], saved["value"]))
    for n, v in DARK.items():
        assert saved["chart_colors.ma_colors." + n] == v
    for n, v in LIGHT.items():
        assert saved["chart_colors.ma_colors_light." + n] == v
    text = dict(tables.help_rows())["Moving average colors"]
    assert "chart_colors" in text and "#ca8a04" in text and "\u2014" not in text
    assert "Moving average colors" in set(pd.read_csv(os.path.join(ROOT, "data", "help.csv"))["topic"])
