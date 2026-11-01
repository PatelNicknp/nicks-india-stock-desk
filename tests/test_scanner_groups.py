"""Technical and Fundamental: the scanner_groups config, the menu split, and the Chart Viewer switch keys."""
import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "site"))

import build_pages  # noqa: E402
import tables  # noqa: E402

TECHNICAL = ["vcp", "box", "flag", "qullamaggie", "marios", "episodic", "gapup", "week52", "breakouts",
             "highvol", "pullbacks", "trends", "wheel"]
FUNDAMENTAL = ["canslim", "leaders", "growth", "quality", "dividend", "divfund", "scorecard", "top"]


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _cfg():
    return json.loads(_read("config.json"))


def _js_groups():
    js = _read("site", "js", "desk.js")
    m = re.search(r"const GROUP_DEFAULTS = \{(.*?)\};", js, re.S)
    assert m
    return dict(re.findall(r"(\w+): \"(technical|fundamental)\"", m.group(1)))


def test_switch_defaults_on():
    cfg = _cfg()
    assert cfg["features"]["split_tech_fund"] is True
    assert cfg["chart_viewer"]["group_toggle"] is True
    assert cfg["chart_viewer"]["default_group"] == "technical"


def test_groups_match_nicks_lists():
    groups = {k: v for k, v in _cfg()["scanner_groups"].items() if not k.startswith("_")}
    assert list(groups) == TECHNICAL + FUNDAMENTAL
    assert all(groups[k] == "technical" for k in TECHNICAL)
    assert all(groups[k] == "fundamental" for k in FUNDAMENTAL)
    # CANSLIM and Leaders are fundamental by Nick's choice.
    assert groups["canslim"] == "fundamental" and groups["leaders"] == "fundamental"


def test_js_defaults_match_config():
    groups = {k: v for k, v in _cfg()["scanner_groups"].items() if not k.startswith("_")}
    js = _js_groups()
    assert js == groups
    assert list(js) == list(groups), "menu order"


def test_gainers_stays_outside_both_and_group_keys_sit_at_the_end():
    cfg = _cfg()
    assert "gainers" not in cfg["scanner_groups"]
    assert list(cfg["chart_viewer"])[-2:] == ["group_toggle", "default_group"]
    js = _read("site", "js", "desk.js")
    assert 'GROUP_IDS.indexOf(v) >= 0 ? v : ""' in js  # any other word: out of both


def test_every_group_key_is_a_page():
    pids = {pid for _f, pid, _t in build_pages.PAGES}
    for key in _cfg()["scanner_groups"]:
        if not key.startswith("_"):
            assert key in pids, key


def test_every_chart_viewer_scanner_has_a_group():
    js = _read("site", "js", "desk.js")
    start = js.index("const CV_SOURCES = [")
    block = js[start:js.index("];", start)]
    ids = re.findall(r'\{ id: "(\w+)"', block)
    groups = _js_groups()
    for i in ids:
        assert i in groups, i
    tech = [i for i in ids if groups[i] == "technical"]
    fund = [i for i in ids if groups[i] == "fundamental"]
    assert fund == ["canslim", "growth", "quality", "dividend", "leaders"] or set(fund) == {"canslim", "leaders", "growth", "quality", "dividend"}
    assert {"vcp", "box", "flag", "qullamaggie", "marios", "episodic", "gapup", "week52", "breakouts", "highvol", "pullbacks", "wheel"} == set(tech)


def test_menu_split_code():
    js = _read("site", "js", "desk.js")
    assert 'featureOn("feature.split_tech_fund")' in js
    assert 'setting === "scanner_groups." + id' in js
    assert '"desk-cv-group"' in js
    assert '"All " + group + " stocks"' in js and '"All scanner stocks"' in js
    assert "menuGroups = navGroups()" in js


def test_settings_and_help():
    cfg = _cfg()
    rows = tables.settings_rows(cfg)
    settings = dict(zip(rows["setting"], rows["value"]))
    assert settings["feature.split_tech_fund"] is True
    assert settings["chart_viewer.group_toggle"] is True
    assert settings["chart_viewer.default_group"] == "technical"
    for k in TECHNICAL + FUNDAMENTAL:
        assert settings["scanner_groups." + k] in ("technical", "fundamental"), k
    assert "scanner_groups._note" not in settings
    saved = pd.read_csv(os.path.join(ROOT, "data", "settings.csv"))
    keys = set(saved["setting"])
    for k in ["feature.split_tech_fund", "chart_viewer.group_toggle", "chart_viewer.default_group"] + ["scanner_groups." + x for x in TECHNICAL + FUNDAMENTAL]:
        assert k in keys, k
    topics = dict(tables.help_rows())
    text = topics["Technical and Fundamental"]
    assert "\u2014" not in text and "feature.split_tech_fund" in text and "scanner_groups" in text
    assert "CANSLIM, Leaders" in text
    cv = topics["Chart Viewer"]
    assert "Technical | Fundamental" in cv and "chart_viewer.group_toggle" in cv and "chart_viewer.default_group" in cv
    saved_help = pd.read_csv(os.path.join(ROOT, "data", "help.csv"))
    assert "Technical and Fundamental" in set(saved_help["topic"])


def test_chart_viewer_description_has_both_versions():
    js = _read("site", "js", "pages.js")
    start = js.index("    chartviewer: { title:")
    block = js[start:js.index("    ] },", start)]
    assert "splitLines" in block and "All scanner stocks puts" in block and "All technical stocks and All fundamental stocks" in block
    assert "\u2014" not in block
