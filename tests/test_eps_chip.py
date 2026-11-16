"""Chart Viewer EPS chip: 'EPS nn' next to RS, green at 80+, none without a rating."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_chart_viewer_eps_chip():
    if not os.path.exists(os.path.join(ROOT, "data", "eps_ratings.csv")):
        pytest.skip("no eps_ratings.csv yet")
    try:
        proc = subprocess.run(["node", os.path.join(ROOT, "tests", "eps_chip.js")], cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
    except FileNotFoundError as exc:
        pytest.skip("node is not installed: " + str(exc))
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 2:
        pytest.skip(out.strip() or "playwright is not installed")
    assert proc.returncode == 0, out


def test_description_box_explains_the_eps_chip():
    text = open(os.path.join(ROOT, "site", "js", "pages.js"), encoding="utf-8").read()
    assert text.count("The EPS chip next to it is the 1 to 99 EPS Rating.") == 2
