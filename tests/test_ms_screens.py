"""MarketSmith style RS Rating, EPS Rating, Highest EPS and RS, and the Minervini 1-Month and 5-Month screens."""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ms_screens as ms  # noqa: E402
import relative_strength as rs  # noqa: E402
import stock_desk  # noqa: E402


def _dates(n):
    return pd.bdate_range("2024-01-01", periods=n)


# ---------------------------------------------------------------- RS Rating
def test_rs_rating_ranks_against_every_stock_not_the_nifty():
    n = 300
    idx = _dates(n)
    close = pd.DataFrame({
        "FAST": 100 * (1.004 ** np.arange(n)),
        "MID": 100 * (1.001 ** np.arange(n)),
        "SLOW": 100 * (0.999 ** np.arange(n)),
        # The Nifty is far stronger than every stock. A Nifty-relative score would call them all weak.
        "^NSEI": 100 * (1.01 ** np.arange(n)),
    }, index=idx)
    table = rs.build(close, ["FAST", "MID", "SLOW"])
    got = dict(zip(table["ticker"], table["rs"]))
    assert got == {"FAST": 99, "MID": 50, "SLOW": 1}


def test_rs_rating_uses_discrete_quarters_40_20_20_20():
    # Same 12-month gain, but RECENT made it all in the latest quarter: it must rank higher.
    q = 63
    flat = [100.0] * (3 * q + 1)
    recent = flat + list(np.linspace(100, 150, q + 1)[1:])
    early = list(np.linspace(100, 150, q + 1)) + [150.0] * (3 * q)
    close = pd.DataFrame({"RECENT": recent, "EARLY": early}, index=_dates(4 * q + 1))
    table = rs.build(close, ["RECENT", "EARLY"]).set_index("ticker")
    assert abs(float(table.loc["RECENT", "rs_raw"]) - 0.4 * 0.5) < 1e-6
    assert abs(float(table.loc["EARLY", "rs_raw"]) - 0.2 * 0.5) < 1e-6
    assert table.loc["RECENT", "rs"] == 99 and table.loc["EARLY", "rs"] == 1


def test_funds_are_not_in_the_race():
    n = 260
    close = pd.DataFrame({
        "AAA": 100 * (1.002 ** np.arange(n)),
        "BBB": 100 * (1.001 ** np.arange(n)),
        "GOLDBEES": 100 * (1.009 ** np.arange(n)),
    }, index=_dates(n))
    uni = pd.DataFrame({"ticker": ["AAA", "BBB", "GOLDBEES"], "isin": ["INE001", "INE002", "INF204KB17I5"]})
    funds = rs.fund_tickers(uni)
    assert funds == {"GOLDBEES"}
    table = rs.build(close, ["AAA", "BBB", "GOLDBEES"], skip=funds).set_index("ticker")
    assert table.loc["AAA", "rs"] == 99
    assert table.loc["GOLDBEES", "rs"] == ""
    assert table.loc["GOLDBEES", "rs_note"] == rs.FUND_NOTE
    assert rs.rs_map(table.reset_index()) == {"AAA": 99, "BBB": 1}


def test_load_rs_table_builds_in_memory_when_nothing_is_saved(tmp_path):
    n = 260
    close = pd.DataFrame({"AAA": 100 * (1.002 ** np.arange(n)), "BBB": 100 * (1.001 ** np.arange(n))}, index=_dates(n))
    uni = pd.DataFrame({"ticker": ["AAA", "BBB"], "isin": ["INE1", "INE2"]})
    stock_desk.LOG.clear()
    t = stock_desk.load_rs_table(close, uni, {}, str(tmp_path), "morning", "2024-12-31", rs_on=True)
    assert rs.rs_map(t) == {"AAA": 99, "BBB": 1}
    assert not (tmp_path / "rs_ratings.csv").exists()  # only the main run saves it
    t = stock_desk.load_rs_table(close, uni, {}, str(tmp_path), "full", "2024-12-31", rs_on=True)
    assert (tmp_path / "rs_ratings.csv").exists()
    off = stock_desk.load_rs_table(close, uni, {}, str(tmp_path / "x"), "full", "2024-12-31", rs_on=False)
    assert rs.rs_map(off) == {"AAA": 99, "BBB": 1}
    assert not (tmp_path / "x" / "rs_ratings.csv").exists()


def test_trading_floor_reads_the_rs_rating():
    import inspect
    src = inspect.getsource(stock_desk.load_trading_floor)
    assert "rs_lookup" in src and "rs_score" in src
    assert "_rs_map" not in inspect.getsource(stock_desk)


# ---------------------------------------------------------------- EPS Rating
def _q(ticker, values):
    """values: {"CY2026Q2": eps, ...}"""
    return [{"ticker": ticker, "frame": f, "eps": v} for f, v in values.items()]


def _a(ticker, values):
    return [{"ticker": ticker, "frame": f, "eps": v} for f, v in values.items()]


def test_eps_parts():
    qm = {(2026, 2): 2.0, (2025, 2): 1.0, (2026, 1): 1.5, (2025, 1): 1.0}
    a, b, latest = ms.quarter_parts(qm)
    assert latest == (2026, 2) and abs(a - 100.0) < 1e-9 and abs(b - 50.0) < 1e-9
    # Year-ago loss: the CANSLIM C rule, change over the size of then.
    assert abs(ms.yoy_change(1.0, -2.0) - 150.0) < 1e-9
    assert ms.yoy_change(1.0, 0.0) is None
    # Yearly growth: longest span from 5 down to 3 years, compound.
    g, yrs = ms.annual_growth({(2022, 0): 1.0, (2023, 0): 1.2, (2024, 0): 1.5, (2025, 0): 1.8, (2026, 0): 2.0})
    assert yrs == 4 and abs(g - ((2.0 ** 0.25) - 1) * 100) < 1e-9
    g, yrs = ms.annual_growth({(2023, 0): 1.0, (2026, 0): 1.331})
    assert yrs == 3 and abs(g - 10.0) < 1e-6
    assert ms.annual_growth({(2025, 0): 1.0, (2026, 0): 2.0}) == (None, None)  # under 3 years
    assert ms.annual_growth({(2023, 0): -1.0, (2026, 0): 2.0})[0] is None  # loss at the start


def test_eps_rating_ranks_three_parts_equally_and_leaves_gaps_blank():
    rows = []
    rows += _q("BEST", {"CY2026Q2": 3.0, "CY2025Q2": 1.0, "CY2026Q1": 3.0, "CY2025Q1": 1.0})
    rows += _q("MID", {"CY2026Q2": 1.5, "CY2025Q2": 1.0, "CY2026Q1": 1.5, "CY2025Q1": 1.0})
    rows += _q("LOW", {"CY2026Q2": 0.5, "CY2025Q2": 1.0, "CY2026Q1": 0.5, "CY2025Q1": 1.0})
    rows += _q("SHORT", {"CY2026Q2": 9.0, "CY2025Q2": 1.0})  # no prior-quarter pair
    rows += _q("NOYEARS", {"CY2026Q2": 9.0, "CY2025Q2": 1.0, "CY2026Q1": 9.0, "CY2025Q1": 1.0})
    ann = []
    for t, end in (("BEST", 4.0), ("MID", 2.0), ("LOW", 0.8), ("SHORT", 9.0)):
        ann += _a(t, {"CY2023": 1.0, "CY2026": end})
    ann += _a("NOYEARS", {"CY2025": 1.0, "CY2026": 2.0})  # under 3 years
    strict = ms.eps_ratings(pd.DataFrame(rows), pd.DataFrame(ann), cfg={"marketsmith_screens": {"require_prior_quarter": True}}).set_index("ticker")
    assert strict.loc["BEST", "eps_rating"] == 99
    assert strict.loc["MID", "eps_rating"] == 50
    assert strict.loc["LOW", "eps_rating"] == 1
    assert pd.isna(strict.loc["SHORT", "eps_rating"]) and pd.isna(strict.loc["NOYEARS", "eps_rating"])
    out = ms.eps_ratings(pd.DataFrame(rows), pd.DataFrame(ann)).set_index("ticker")
    # Default: the quarter before counts when on file. SHORT is rated on its two parts, both the best.
    assert out.loc["SHORT", "eps_rating"] == 99 and out.loc["SHORT", "eps_parts"] == 2
    assert out.loc["BEST", "eps_parts"] == 3 and out.loc["LOW", "eps_rating"] == 1
    assert pd.isna(out.loc["NOYEARS", "eps_rating"])
    assert out.loc["BEST", "latest_quarter"] == "CY2026Q2"
    assert out.loc["BEST", "eps_growth_years"] == 3


# ---------------------------------------------------------------- Minervini templates
def _bars(closes):
    c = pd.Series(closes, index=_dates(len(closes)))
    return pd.DataFrame({"close": c, "high": c * 1.01, "low": c * 0.99})


def _uptrend(n=400):
    return 50 * (1.003 ** np.arange(n))


def test_template_all_rules_pass_on_a_steady_uptrend():
    chk = ms.template_check(_bars(_uptrend()), 85, 21)
    assert chk["passes"] and all(chk["rules"])
    chk5 = ms.template_check(_bars(_uptrend()), 85, 105)
    assert chk5["passes"]


def test_template_rs_rule_is_70():
    assert ms.template_check(_bars(_uptrend()), 70, 21)["passes"]
    low = ms.template_check(_bars(_uptrend()), 69, 21)
    assert not low["passes"] and low["rules"][7] is False
    assert ms.template_check(_bars(_uptrend()), None, 21)["passes"] is False


def test_one_month_versus_five_months():
    # Up, a long slide, then a fresh rally: the 200-day has turned up over the last month,
    # but it is still lower than 105 sessions ago.
    up = 100 * (1.004 ** np.arange(100))
    down = up[-1] * (0.995 ** np.arange(1, 141))
    rally = down[-1] * (1.01 ** np.arange(1, 81))
    closes = np.concatenate([up, down, rally])
    one = ms.template_check(_bars(closes), 90, 21)
    five = ms.template_check(_bars(closes), 90, 105)
    assert one["rules"][2] is True   # 200-day higher than 21 sessions ago
    assert five["rules"][2] is False  # but not higher than 105 sessions ago
    assert one["sma200_ago"] != five["sma200_ago"]
    assert not five["passes"]
    # Same bars, same other rules: only rule 3 differs between the two screens.
    assert [a for i, a in enumerate(one["rules"]) if i != 2] == [b for i, b in enumerate(five["rules"]) if i != 2]


def test_template_low_and_high_lines():
    # 30% over the 52-week low, and within 25% of the 52-week high.
    closes = list(_uptrend())
    chk = ms.template_check(_bars(closes), 90, 21)
    assert chk["above_low_pct"] >= 30
    closes[-1] = closes[-1] * 0.70  # a 30% drop off the high on the last day
    hit = ms.template_check(_bars(closes), 90, 21)
    assert hit["rules"][6] is False and not hit["passes"]


def test_template_short_history_is_not_a_pass():
    assert ms.template_check(_bars(_uptrend(250)), 90, 21) is None
    assert ms.template_check(_bars(_uptrend(300)), 90, 105) is None


def test_build_template_lists_passing_liquid_names_strongest_rs_first():
    n = 400
    up = _uptrend(n)
    close = pd.DataFrame({"AAA": up, "BBB": up * 2, "DOWN": 100 * (0.999 ** np.arange(n))}, index=_dates(n))
    uni = pd.DataFrame({"ticker": ["AAA", "BBB", "DOWN"], "company": ["A", "B", "D"]})
    out = ms.build_template(close, close * 1.01, close * 0.99, uni, {"AAA": 75, "BBB": 95, "DOWN": 99}, 21, eps_lookup={"AAA": 88})
    assert list(out["ticker"]) == ["BBB", "AAA"]
    assert list(out["rank"]) == [1, 2]
    assert out.iloc[0]["status"] == "PASSES" and out.iloc[0]["strength"] == 95
    assert out.set_index("ticker").loc["AAA", "eps_rating"] == 88
    assert set(ms.TEMPLATE_COLS) >= set(out.columns) - {"r1"}


# ---------------------------------------------------------------- Highest EPS and RS
def test_eps_rs_ranks_by_sum_and_drops_extended():
    n = 120
    flat = np.full(n, 100.0)
    hot = np.concatenate([np.full(n - 10, 100.0), np.linspace(100, 160, 10)])  # 50-day stand-in: extended
    close = pd.DataFrame({"AAA": flat, "BBB": flat, "CCC": hot, "DDD": flat, "PIV": flat * 1.10}, index=_dates(n))
    uni = pd.DataFrame({"ticker": ["AAA", "BBB", "CCC", "DDD", "PIV"]})
    eps = pd.DataFrame({
        "ticker": ["AAA", "BBB", "CCC", "DDD", "PIV"],
        "eps_rating": [90, 99, 99, 60, 95],
        "eps_q_yoy": [50.0] * 5, "eps_prev_q_yoy": [40.0] * 5, "eps_annual_growth": [20.0] * 5,
        "eps_growth_years": [4] * 5, "latest_quarter": ["CY2026Q2"] * 5,
    })
    rsl = {"AAA": 95, "BBB": 85, "CCC": 99, "DDD": 99, "PIV": 99}
    pivots = {"PIV": (100.0, "VCP")}  # close 110 is 10% past the buy point: extended
    out, counts = ms.build_eps_rs(close, uni, eps, rsl, pivots)
    assert list(out["ticker"]) == ["AAA", "BBB"]  # 185 then 184
    assert list(out["combined"]) == [185, 184]
    assert counts == {"rated_both": 5, "over_min": 4, "extended": 2, "listed": 2}
    assert "stand-in" in out.iloc[0]["extended_check"]


def test_pivot_map_prefers_vcp_and_skips_closed():
    frames = {
        "scanner_vcp": pd.DataFrame({"ticker": ["AAA", "BBB"], "pivot": [100, 50], "status": ["READY", "CLOSED"]}),
        "scanner_box": pd.DataFrame({"ticker": ["AAA", "BBB"], "pivot": [90, 55], "status": ["READY", "READY"]}),
    }
    assert ms.pivot_map(frames) == {"AAA": (100.0, "VCP"), "BBB": (55.0, "Box")}


def test_settings_from_config_block():
    import json
    cfg = json.load(open(os.path.join(ROOT, "config.json")))
    spec = ms.settings(cfg)
    assert spec["rising_1m_sessions"] == 21 and spec["rising_5m_sessions"] == 105
    assert spec["template_rs_min"] == 70 and spec["template_above_low_pct"] == 30.0
    for k in ("scanner_eps_rs", "scanner_minervini_1m", "scanner_minervini_5m"):
        assert cfg["features"][k] is True
