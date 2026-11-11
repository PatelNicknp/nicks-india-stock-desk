"""Today's Run everything link opens the main update workflow. It does not start a run."""
import json
import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tables  # noqa: E402

URL = "https://github.com/PatelNicknp/nicks-india-stock-desk/actions/workflows/update.yml"


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_switch_defaults_on_and_is_saved():
    cfg = json.loads(_read("config.json"))
    assert cfg["features"]["run_everything"] is True
    rows = tables.settings_rows(cfg)
    settings = dict(zip(rows["setting"], rows["value"]))
    assert settings["feature.run_everything"] is True
    saved = pd.read_csv(os.path.join(ROOT, "data", "settings.csv"))
    assert "feature.run_everything" in set(saved["setting"])
    got = saved[saved["setting"] == "feature.run_everything"]["value"].iloc[0]
    assert str(got).lower() == "true"


def test_help_and_readme_use_simple_words():
    text = dict(tables.help_rows())["Run everything"]
    assert "\u2014" not in text
    for word in ("Run everything", "does not start the run", "no token", "Run workflow",
                 "Last update", "IST", "PT", "data/meta.json", "Last update: not available",
                 "feature.run_everything"):
        assert word in text, word
    saved = pd.read_csv(os.path.join(ROOT, "data", "help.csv"))
    assert "Run everything" in set(saved["topic"])
    plain = saved[saved["topic"] == "Run everything"]["plain_english"].iloc[0]
    assert plain == text
    readme = _read("README.md")
    assert "Run everything" in readme and "feature.run_everything" in readme
    assert "does not start the run" in readme and "Last update: not available" in readme
    about = _read("site", "js", "pages.js")
    start = about.index("today: { lines:")
    block = about[start:about.index("] },", start)]
    assert "Run everything" in block and "does not start the run" in block
    assert "\u2014" not in block


def test_button_only_opens_the_close_workflow():
    update = _read(".github", "workflows", "update.yml")
    # The manual button was already there. The three weekday schedules stay as they are.
    assert "workflow_dispatch:" in update
    for cron in ('"30 2 * * 1-5"', '"0 11 * * 1-5"', '"0 13 * * 1-5"'):
        assert "cron: " + cron in update
    assert "python stock_desk.py --close" in update
    js = _read("site", "js", "desk.js")
    assert URL in js
    start = js.index("function headerActionsHtml")
    block = js[start:js.index("function latestChecked", start)]
    assert ">Run everything</a>" in block
    assert 'target="_blank"' in block
    assert 'featureOn("feature.run_everything")' in block
    assert 'id="last-update"' in block
    assert "Last update:" in block
    low = block.lower()
    for banned in ("token", "secret", "authorization", "api.github.com", "workflow_dispatch", "onclick"):
        assert banned not in low, banned
    # No Tito Option control on this desk, so the link sits in the header actions.
    assert "Tito Option" not in js
    assert "headerActionsHtml(page)" in js


def test_run_everything_in_the_browser():
    script = os.path.join(ROOT, "tests", "run_everything_check.js")
    try:
        proc = subprocess.run(["node", script], cwd=ROOT, capture_output=True, text=True, timeout=180)
    except FileNotFoundError as exc:
        pytest.skip("node is not installed: " + str(exc))
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 2:
        pytest.skip(out.strip() or "playwright is not installed")
    assert proc.returncode == 0, out
