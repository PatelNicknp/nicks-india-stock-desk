"""VCP upgrades: 25% above the 52-week low, quiet last contraction, Nifty RS line.

These tests do not claim the rules make money. They check pass, fail, and waiting.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relative_strength as rs  # noqa: E402
import setups  # noqa: E402
from test_setups import _vcp_tape  # noqa: E402


def _spec(**kw):
    cfg = {"vcp": dict(kw)}
    return setups._vcp_cfg(cfg)


def test_config_defaults_match_the_brief():
    cfg = setups._vcp_cfg({"vcp": {}})
    assert cfg["above_low_pct"] == 25
    assert cfg["dry_up_on"] is True
    assert cfg["dry_up_below_avg_on"] is True
    assert cfg["dry_up_quiet_on"] is True
    assert cfg["dry_up_quiet_frac"] == 0.5
    assert cfg["dry_up_quiet_days"] == 1
    assert cfg["dry_up_tighten_on"] is False
    assert cfg["rs_6m_on"] and cfg["rs_12m_on"] and cfg["rs_21d_on"] and cfg["rs_50d_on"]
    saved = __import__("json").load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    block = saved["vcp"]
    assert block["above_low_pct"] == 25
    assert block["dry_up_tighten_on"] is False
    assert "not a book rule" in block["_note"]
    assert "\u2014" not in block["_note"]


def test_exactly_25_percent_above_the_low_passes():
    n = 260
    close = np.full(n, 125.0)
    high = np.full(n, 126.0)
    low = np.full(n, 124.0)
    # Inside the last 252 bars, so it is the 52-week low the rule uses.
    low[20] = 100.0
    high[20] = 101.0
    close[20] = 100.5
    close[-1] = 125.0
    spy = np.full(n, 100.0)
    trend = setups._trend_arrays(close, high, low, spy, _spec())
    assert bool(trend["rules"][5][-1]) is True
    assert setups._rule_text(True, True) == "PASS"
    close[-1] = 124.99
    trend = setups._trend_arrays(close, high, low, spy, _spec())
    assert bool(trend["rules"][5][-1]) is False
    assert bool(trend["readies"][5][-1]) is True
    low[:] = np.nan
    trend = setups._trend_arrays(close, high, low, spy, _spec())
    assert bool(trend["rules"][5][-1]) is False
    assert setups._rule_text(False, bool(trend["readies"][5][-1])) == "WAITING"


def _quiet_window():
    # Bars ago 0 is today. Build chronological then the helper uses bar indexes.
    # High at bar 0, low at bar 3, today bar 6, no close above pivot 10.
    n = 7
    close = np.array([9.0, 8.5, 8.2, 8.0, 8.6, 9.0, 9.2])
    high = np.array([10.0, 9.0, 8.6, 8.4, 8.9, 9.3, 9.5])
    low = np.array([8.7, 8.2, 8.0, 7.6, 8.4, 8.8, 9.0])
    volume = np.array([80, 70, 40, 30, 25, 20, 20], dtype=float)
    avg = np.full(n, 100.0)
    return high, low, close, volume, avg


def test_breakout_volume_does_not_spoil_a_quiet_contraction():
    high, low, close, volume, avg, = _quiet_window()
    spec = _spec()
    quiet = setups.contraction_dry_up(high, low, close, volume, avg, 0, 3, 10.0, 6, spec)
    assert quiet["status"] == "yes", quiet
    loud = volume.copy()
    loud[-1] = 5000
    avg2 = avg.copy()
    avg2[-1] = 110
    close2 = close.copy()
    close2[-1] = 11  # first close above the pivot is today, so today is excluded
    loud_result = setups.contraction_dry_up(high, low, close2, loud, avg2, 0, 3, 10.0, 6, spec)
    assert loud_result["status"] == "yes", loud_result
    pre = volume[:-1]
    assert abs(loud_result["ratio"] - (pre.mean() / 100.0)) < 1e-9
    # If today were included, the average would be above the 50-day line.
    polluted = (pre.sum() + 5000) / 7
    assert polluted / 110 > 1


def test_quiet_base_still_needs_the_breakout_volume():
    frame, spy, p2 = _vcp_tape(True)
    state = setups.vcp_last(
        frame["high"].to_numpy(), frame["low"].to_numpy(), frame["close"].to_numpy(),
        frame["volume"].to_numpy(), spy.to_numpy(),
    )
    assert state["dry_up"] == "yes", state["dry_up"]
    assert state["breakout"] is True
    # Same chart, but the breakout day is not 1.5 times the 50-day average.
    vol = frame["volume"].to_numpy().copy()
    vol[-1] = 400_000
    state = setups.vcp_last(
        frame["high"].to_numpy(), frame["low"].to_numpy(), frame["close"].to_numpy(),
        vol, spy.to_numpy(),
    )
    assert state["dry_up"] == "yes"
    assert state["big_vol"] is False
    assert state["breakout"] is False
    assert "1.5" in setups._vcp_reason(state, setups._vcp_status(state), frame.index)


def test_missing_benchmark_or_short_history_is_waiting():
    n = 80
    close = np.linspace(100, 130, n)
    high = close * 1.01
    low = close * 0.99
    spy = np.full(n, np.nan)
    trend = setups._trend_arrays(close, high, low, spy, _spec())
    assert bool(trend["rules"][7][-1]) is False
    assert setups._rule_text(False, bool(trend["readies"][7][-1])) == "WAITING"
    # A year of prices, but the benchmark is missing on the last year.
    n = 400
    close = np.linspace(100, 180, n)
    high = close * 1.01
    low = close * 0.99
    spy = np.linspace(100, 110, n)
    spy[-300:] = np.nan
    trend = setups._trend_arrays(close, high, low, spy, _spec())
    text = setups._rule_text(bool(trend["rules"][7][-1]), bool(trend["readies"][7][-1]))
    assert text == "WAITING"
    assert bool(trend["rules"][7][-1]) is False


def test_rs_line_needs_every_switched_on_piece():
    n = 400
    bench = np.full(n, 100.0)
    stock = np.linspace(100, 220, n)
    # Rising stock versus a flat benchmark passes all four pieces.
    trend = setups._trend_arrays(stock, stock * 1.01, stock * 0.99, bench, _spec())
    assert bool(trend["rules"][7][-1]) is True
    # Flat last month: still ahead over 6 and 12 months, but not over 21 days.
    stock2 = stock.copy()
    stock2[-30:] = stock2[-30]
    trend = setups._trend_arrays(stock2, stock2 * 1.01, stock2 * 0.99, bench, _spec())
    assert bool(trend["rules"][7][-1]) is False
    trend = setups._trend_arrays(stock2, stock2 * 1.01, stock2 * 0.99, bench, _spec(rs_21d_on=False, rs_50d_on=False))
    assert bool(trend["rules"][7][-1]) is True
    # Switches off: the rule is not a fake pass of missing data. The cell says OFF.
    trend = setups._trend_arrays(stock, stock, stock, np.full(n, np.nan), _spec(
        rs_6m_on=False, rs_12m_on=False, rs_21d_on=False, rs_50d_on=False,
    ))
    assert trend["r8_off"] is True
    assert setups._rule_text(True, True, off=True) == "OFF"


def test_rank_and_rs70_filter_are_unchanged():
    cfg = __import__("json").load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    assert cfg["features"]["rs_rank"] is True
    assert cfg["relative_strength"]["leader_min"] == 70
    spec = rs.settings_from(cfg)
    assert spec["leader_min"] == 70
    assert spec["min_bars"] == 253
    assert rs.feature_on(cfg) is True
    ranked = rs.rank_1_to_99({"AAA": 5.0, "BBB": 1.0})
    assert int(ranked["AAA"]) == 99
    assert int(ranked["BBB"]) == 1
    # A missing quarter stays blank. It is not stored as 0.
    assert rs.raw_score([0.1, None, 0.2, 0.1]) is None


def test_tighten_switch_is_off_and_does_not_block_a_quiet_base():
    high, low, close, volume, avg = _quiet_window()
    # Make the later bars wider so the optional check would fail if it were on.
    high[-2:] = high[-2:] + 2
    low[-2:] = low[-2:] - 2
    off = setups.contraction_dry_up(high, low, close, volume, avg, 0, 3, 10.0, 6, _spec())
    assert off["status"] == "yes", off
    on = setups.contraction_dry_up(
        high, low, close, volume, avg, 0, 3, 10.0, 6, _spec(dry_up_tighten_on=True),
    )
    assert on["status"] == "no"


def test_help_mentions_the_new_rules_without_a_profit_claim():
    import tables
    text = dict(tables.help_rows())["VCP scanner"]
    for phrase in ("25%", "1.5", "WAITING", "not a book rule", "1 to 99", "vcp.show_weaker_trend"):
        assert phrase in text, phrase
    assert "8 trend rules pass" in text
    assert "profit" not in text.lower()
    pages = open(os.path.join(ROOT, "site", "js", "pages.js"), encoding="utf-8").read()
    assert "25%+ over 52w low" in pages
    assert "30%+ over 52w low" not in pages
    assert "Dried up" in pages


if __name__ == "__main__":
    test_config_defaults_match_the_brief()
    test_exactly_25_percent_above_the_low_passes()
    test_breakout_volume_does_not_spoil_a_quiet_contraction()
    test_quiet_base_still_needs_the_breakout_volume()
    test_missing_benchmark_or_short_history_is_waiting()
    test_rs_line_needs_every_switched_on_piece()
    test_rank_and_rs70_filter_are_unchanged()
    test_tighten_switch_is_off_and_does_not_block_a_quiet_base()
    test_help_mentions_the_new_rules_without_a_profit_claim()
    print("vcp upgrades ok")
