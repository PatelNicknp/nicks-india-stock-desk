"""EPS Rating (1-99). No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import eps_rating


def _q(ticker, values):
    # values: {frame: eps}
    return [{"ticker": ticker, "frame": f, "eps": v} for f, v in values.items()]


def test_two_quarters_are_averaged_against_a_year_ago():
    q = pd.DataFrame(_q("A", {"CY2025Q2": 1.0, "CY2025Q3": 1.0, "CY2026Q2": 1.5, "CY2026Q3": 2.0}))
    g, n = eps_rating.quarterly_growth(q)
    assert n == 2 and round(g, 1) == 75.0


def test_one_quarter_when_only_one_has_a_year_ago():
    q = pd.DataFrame(_q("A", {"CY2025Q3": 1.0, "CY2026Q2": 1.5, "CY2026Q3": 2.0}))
    g, n = eps_rating.quarterly_growth(q)
    assert n == 1 and round(g, 1) == 100.0


def test_annual_uses_three_years_then_falls_back():
    a = pd.DataFrame(_q("A", {"CY2023": 1.0, "CY2024": 1.2, "CY2025": 1.5, "CY2026": 1.728}))
    g, n = eps_rating.annual_growth(a)
    assert n == 3 and round(g, 1) == 20.0
    a2 = pd.DataFrame(_q("A", {"CY2025": 1.0, "CY2026": 1.3}))
    g2, n2 = eps_rating.annual_growth(a2)
    assert n2 == 1 and round(g2, 1) == 30.0


def test_growth_is_capped():
    q = pd.DataFrame(_q("A", {"CY2025Q3": 0.01, "CY2026Q3": 5.0}))
    g, _ = eps_rating.quarterly_growth(q)
    assert g == eps_rating.CAP_HIGH


def test_ratings_are_percentiles_from_1_to_99_and_blank_without_data():
    rows = []
    for i, t in enumerate(["A", "B", "C", "D", "E"]):
        rows += _q(t, {"CY2025Q3": 1.0, "CY2026Q3": 1.0 + 0.1 * i})
    q = pd.DataFrame(rows)
    out = eps_rating.build(q, pd.DataFrame(columns=["ticker", "frame", "eps"]), ["A", "B", "C", "D", "E", "NODATA", "FUND"], skip=["FUND"])
    r = dict(zip(out["ticker"], out["eps_rating"]))
    assert r["A"] == 1 and r["E"] == 99
    assert r["A"] < r["B"] < r["C"] < r["D"] < r["E"]
    assert pd.isna(r["NODATA"])
    assert "FUND" not in r
    note = out.set_index("ticker").loc["E", "eps_note"]
    assert note.startswith("EPS Rating 99")
    assert out.set_index("ticker").loc["NODATA", "eps_note"] == ""


def test_both_parts_blend_equally():
    assert eps_rating.raw_score(40.0, 20.0) == 30.0
    assert eps_rating.raw_score(None, 20.0) == 20.0
    assert eps_rating.raw_score(None, None) is None
