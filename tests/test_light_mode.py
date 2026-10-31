"""Light mode: the switch, the config key, matching colours in CSS and JS, and a browser check."""
import json
import os
import re
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tables  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _vars(block):
    return dict(re.findall(r"--([a-z0-9]+):([^;]+);", block))


def _css_blocks():
    css = _read("site", "css", "desk.css")
    dark = re.search(r":root\{color-scheme:dark;(.*?)\}", css).group(1)
    light = re.search(r':root\[data-theme="light"\]\{color-scheme:light;(.*?)\}', css).group(1)
    return css, _vars(dark), _vars(light)


def test_switch_and_config_defaults():
    cfg = json.loads(_read("config.json"))
    assert cfg["features"]["light_mode"] is True
    block = {k: v for k, v in cfg["light_mode"].items() if not k.startswith("_")}
    assert block == {"default_theme": "dark", "match_device_option": True}, "same keys as the US desk"
    assert "theme" not in cfg


def test_settings_and_help():
    cfg = json.loads(_read("config.json"))
    rows = tables.settings_rows(cfg)
    settings = dict(zip(rows["setting"], rows["value"]))
    assert settings["feature.light_mode"] is True
    assert settings["light_mode.default_theme"] == "dark"
    assert settings["light_mode.match_device_option"] is True
    saved = set(pd.read_csv(os.path.join(ROOT, "data", "settings.csv"))["setting"])
    assert {"feature.light_mode", "light_mode.default_theme", "light_mode.match_device_option"} <= saved
    text = dict(tables.help_rows())["Light mode"]
    assert "\u2014" not in text
    for word in ("Dark, Light, or Match device", "feature.light_mode", "light_mode.default_theme",
                 "light_mode.match_device_option", "starts dark", "top of the menu", "4.5 to 1"):
        assert word in text, word
    assert "Light mode" in set(pd.read_csv(os.path.join(ROOT, "data", "help.csv"))["topic"])


def test_css_uses_variables_for_every_colour():
    css, dark, light = _css_blocks()
    assert set(dark) == set(light) and len(dark) >= 20
    rest = re.sub(r":root(\[data-theme=\"light\"\])?\{color-scheme:[a-z]+;.*?\}", "", css)
    assert re.findall(r"#[0-9A-Fa-f]{6}\b|rgba\(", rest) == []
    assert dark["bg"] == "#0B0F17" and light["bg"] == "#F3F5F9"
    assert dark["panel"] == "#121826" and light["panel"] == "#FFFFFF"


def test_js_light_map_matches_css():
    _css, dark, light = _css_blocks()
    js = _read("site", "js", "desk.js")
    m = re.search(r"const LIGHT = (\{.*?\});", js)
    assert m
    mapping = json.loads(m.group(1))
    for name, value in dark.items():
        assert mapping[value.upper().replace(" ", "")] == light[name], name
    # Status colours get darker on white.
    assert mapping["#22C55E"] == "#12703A" and mapping["#F59E0B"] == "#9A4A06" and mapping["#EF4444"] == "#B42318"
    # A light colour is never also a dark one, so swapping twice changes nothing.
    assert not set(mapping.values()) & set(mapping)


def test_toggle_code():
    js = _read("site", "js", "desk.js")
    assert 'const THEME_KEY = "desk-theme";' in js
    assert 'featureOn("feature.light_mode")' in js
    assert '"Match device"' in js and 'b("dark", "Dark")' in js and 'b("light", "Light")' in js
    assert 'let themeChoice = storedTheme() || "dark";' in js
    assert js.count("tvCreate(host") >= 2 and "LC.createChart(" not in js
    assert "tcDeep(config);" in js
    assert '"light_mode.default_theme"' in js and '"light_mode.match_device_option"' in js
    # The Theme row sits at the top of the menu, right under the search box.
    assert "hidden></div></div></div>' + themeToggleHtml() +" in js


def test_light_mode_in_phone_and_tablet():
    script = os.path.join(ROOT, "tests", "light_mode_check.js")
    try:
        proc = subprocess.run(["node", script], cwd=ROOT, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as exc:
        pytest.skip("node is not installed: " + str(exc))
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 2:
        pytest.skip(out.strip() or "playwright is not installed")
    assert proc.returncode == 0, out
