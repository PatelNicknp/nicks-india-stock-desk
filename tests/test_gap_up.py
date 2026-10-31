"""Gap Up scanner: Nick's rules on made-up daily bars."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gap_up  # noqa: E402
import tables  # noqa: E402

N = 260  # bars per stock


def _bars(scale=1.0):
    """Flat stock: open 100, high 101, low 99, close 100, volume 1000 (times scale for prices)."""
    return {
        "open": np.full(N, 100.0) * scale, "high": np.full(N, 101.0) * scale,
        "low": np.full(N, 99.0) * scale, "close": np.full(N, 100.0) * scale,
        "volume": np.full(N, 1000.0),
    }


def _gap(b, i, open_=102.0, high=105.0, low=101.5, close=104.0, volume=2000.0, after=None):
    """Put a gap day at bar i. Later bars sit at `after` (default: the gap-day close) so they hold."""
    b["open"][i], b["high"][i], b["low"][i], b["close"][i], b["volume"][i] = open_, high, low, close, volume
    level = close if after is None else after
    for j in range(i + 1, N):
        b["open"][j] = b["close"][j] = level
        b["high"][j] = level + 1.0
        b["low"][j] = level - 1.0
    return b


def _run(stocks, cfg=None):
    dates = pd.bdate_range("2025-11-03", periods=N)
    wide = {k: pd.DataFrame({t: b[k] for t, b in stocks.items()}, index=dates) for k in ("open", "high", "low", "close", "volume")}
    uni = pd.DataFrame({"ticker": list(stocks), "company": ["Co " + t for t in stocks]})
    # The made-up stocks trade only Rs 1 lakh a day and most gaps are about 1%, so the rupee floor
    # and the 3% minimum are off unless a test turns them on.
    cfg = {"gap_up": dict({"liquidity_floor": False, "min_gap_filter": False}, **((cfg or {}).get("gap_up") or {}))}
    out, note = gap_up.build(wide["close"], wide["high"], wide["low"], wide["volume"], wide["open"], uni, cfg)
    return out, note


def _one(b, cfg=None):
    out, _ = _run({"AAA": b}, cfg)
    return out.iloc[0].to_dict() if len(out) else None


def test_basic_row_and_numbers():
    row = _one(_gap(_bars(), N - 3))
    assert row is not None
    assert row["status"] == "GAP HOLDING"
    assert row["days_ago"] == 2
    assert abs(row["gap_pct"] - (102.0 / 101.0 - 1) * 100) < 1e-9
    assert abs(row["volume_ratio"] - 2.0) < 1e-9
    assert row["hold_level"] == 101.5 and row["gap_low"] == 101.5
    assert row["price"] == 104.0
    assert abs(row["above_hold_pct"] - (104.0 / 101.5 - 1) * 100) < 1e-9
    assert abs(row["close_pos_pct"] - (104.0 - 101.5) / (105.0 - 101.5) * 100) < 1e-9
    assert row["company"] == "Co AAA"
    assert row["reason"].startswith("Gap Up 1.0% on ")
    assert ", holding." in row["reason"]


def test_true_gap_open_inside_yesterdays_range_is_rejected():
    # Above yesterday's close (100) but not above its high (101): not a true gap.
    assert _one(_gap(_bars(), N - 3, open_=100.5, low=100.2)) is None
    # Equal to yesterday's high is not above it either.
    assert _one(_gap(_bars(), N - 3, open_=101.0, low=100.8)) is None
    # Just above the high counts. Any size, no minimum.
    assert _one(_gap(_bars(), N - 3, open_=101.01, low=100.9)) is not None


def test_true_gap_switch_off_uses_yesterdays_close():
    cfg = {"gap_up": {"true_gap_only": False}}
    assert _one(_gap(_bars(), N - 3, open_=100.5, low=100.2), cfg) is not None


def test_volume_needs_one_and_a_half_times_the_50_day_average():
    assert _one(_gap(_bars(), N - 3, volume=1490.0)) is None
    assert _one(_gap(_bars(), N - 3, volume=1500.0)) is not None


def test_volume_average_is_the_50_days_before_the_gap_day():
    b = _gap(_bars(), N - 3, volume=1500.0)
    # A busy day 51 sessions before the gap is outside the average, so the gap still passes.
    b["volume"][N - 3 - 51] = 100000.0
    assert _one(b) is not None
    # The same busy day 50 sessions before is inside it, so the ratio drops under 1.5.
    b = _gap(_bars(), N - 3, volume=1500.0)
    b["volume"][N - 3 - 50] = 100000.0
    assert _one(b) is None


def test_price_floor_on_the_gap_day_close():
    s = 0.19  # prices around Rs 19
    low = _bars(s)
    assert _one(_gap(low, N - 3, open_=102 * s, high=105 * s, low=101.5 * s, close=104 * s)) is None
    s = 20.0 / 104.0  # gap-day close exactly Rs 20
    ok = _bars(s)
    assert _one(_gap(ok, N - 3, open_=102 * s, high=105 * s, low=101.5 * s, close=20.0)) is not None


def test_hold_rule_close_below_gap_day_low_drops_the_stock():
    b = _gap(_bars(), N - 6)
    b["close"][N - 2] = 101.49
    b["low"][N - 2] = 101.0
    assert _one(b) is None


def test_hold_rule_close_equal_to_gap_day_low_stays():
    b = _gap(_bars(), N - 6)
    b["close"][N - 2] = 101.5
    b["low"][N - 2] = 100.0  # an intraday dip under the low is fine, only closes count
    row = _one(b)
    assert row is not None and row["status"] == "GAP HOLDING"


def test_hold_switch_off_keeps_a_broken_gap():
    b = _gap(_bars(), N - 6)
    b["close"][N - 1] = 100.0
    row = _one(b, {"gap_up": {"hold_rule": False}})
    assert row is not None and row["status"] == "BROKE HOLD"


def test_lookback_window_is_21_trading_days_including_today():
    today = _one(_gap(_bars(), N - 1))
    assert today["days_ago"] == 0 and today["status"] == "GAP UP today"  # today counts
    row = _one(_gap(_bars(), N - 21))
    assert row is not None and row["days_ago"] == 20
    assert _one(_gap(_bars(), N - 22)) is None
    assert _one(_gap(_bars(), N - 22), {"gap_up": {"lookback_days": 22}}) is not None


def test_most_recent_holding_gap_is_picked():
    b = _gap(_bars(), N - 15)  # first gap: low 101.5, then sits at 104
    # second gap later: open 106 over the 105 high, low 105.5, close 108
    _gap(b, N - 5, open_=106.0, high=109.0, low=105.5, close=108.0, volume=5000.0)
    row = _one(b)
    assert row["days_ago"] == 4 and row["gap_low"] == 105.5
    # The newer gap breaks (close 104 under 105.5) but the older one still holds, so the older one shows.
    b["close"][N - 1] = 104.0
    row = _one(b)
    assert row is not None and row["days_ago"] == 14 and row["gap_low"] == 101.5


def test_sorted_newest_gap_first_then_by_gap_size():
    stocks = {
        "OLD": _gap(_bars(), N - 10, open_=110.0, high=112.0, low=109.0, close=111.0),
        "SMALL": _gap(_bars(), N - 2, open_=101.5, high=104.0, low=101.2, close=103.0),
        "BIG": _gap(_bars(), N - 2, open_=108.0, high=110.0, low=107.0, close=109.0),
    }
    out, _ = _run(stocks)
    assert list(out["ticker"]) == ["BIG", "SMALL", "OLD"]
    assert list(out["rank"]) == [1, 2, 3]


def test_stock_not_traded_today_is_skipped():
    b = _gap(_bars(), N - 5)
    other = _bars()
    for k in ("open", "high", "low", "close", "volume"):
        b[k][N - 1] = np.nan
    out, _ = _run({"AAA": b, "BBB": other})
    assert "AAA" not in set(out.get("ticker", []))


def test_funds_left_out():
    uni = pd.DataFrame({"ticker": ["AAA", "GOLDBEES", "QUIET"], "isin": ["INE000A01010", "INF204KB17I5", "INE000B01010"]})
    names = gap_up.pick_universe(uni, None, {})
    assert list(names["ticker"]) == ["AAA", "QUIET"]
    names = gap_up.pick_universe(uni, None, {"gap_up": {"skip_etfs_and_funds": False}})
    assert list(names["ticker"]) == ["AAA", "GOLDBEES", "QUIET"]


def test_also_in_lists_other_scanners():
    rows = pd.DataFrame({"ticker": ["AAA", "BBB"]})
    frames = {
        "scanner_vcp": pd.DataFrame({"ticker": ["AAA"], "status": ["READY"]}),
        "scanner_episodic_pivot": pd.DataFrame({"ticker": ["AAA", "BBB"], "status": ["IN TRADE", "CLOSED"]}),
        "high_volume": pd.DataFrame({"ticker": ["BBB"], "passes_default": ["yes"]}),
    }
    out = gap_up.add_also_in(rows, frames)
    assert list(out["also_in"]) == ["VCP, EP", "High volume"]


def test_config_switches_settings_and_help():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["features"]["scanner_gap_up"] is True
    block = {k: v for k, v in cfg["gap_up"].items() if not k.startswith("_")}
    assert block["lookback_days"] == 21 and block["vol_mult"] == 1.5 and block["min_price"] == 20
    assert block["true_gap_only"] is True and block["hold_rule"] is True and block["hold_level"] == "gap_day_low"
    assert block["liquidity_floor"] is True and block["min_traded_value_cr"] == 1.0
    # Same key names and order as the US desk, then the India keys.
    assert block["min_gap_filter"] is True and block["min_gap_pct"] == 3.0
    us = ["lookback_days", "true_gap_only", "min_gap_filter", "min_gap_pct", "volume_filter", "vol_mult", "vol_avg_days", "price_floor",
          "min_price", "liquidity_floor", "liquidity_days", "min_traded_value_cr", "hold_rule", "skip_stale",
          "sma_fast", "sma_slow", "show_other_scanners", "skip_etfs_and_funds", "hold_level"]
    assert list(block) == us == list(gap_up.GAP_DEFAULTS)
    for k, v in gap_up.GAP_DEFAULTS.items():
        assert block[k] == v, k
    assert cfg["chart_viewer"]["include_gap_up"] is True
    rows = tables.settings_rows(cfg)
    settings = dict(zip(rows["setting"], rows["value"]))
    assert settings["feature.scanner_gap_up"] is True
    for k in block:
        assert "gap_up." + k in settings, k
    text = dict(tables.help_rows())["Gap Up"]
    assert "\u2014" not in text and "feature.scanner_gap_up" in text
    assert "scanner_gap_up" in tables.COLS


def test_rupee_traded_value_floor():
    # Flat bars: close about 100 x 1000 shares = Rs 1 lakh a day, far under Rs 1 crore.
    assert _one(_gap(_bars(), N - 3), {"gap_up": {"liquidity_floor": True}}) is None
    assert _one(_gap(_bars(), N - 3), {"gap_up": {"liquidity_floor": True, "min_traded_value_cr": 0.01}}) is not None


def test_volume_and_price_switches():
    assert _one(_gap(_bars(), N - 3, volume=1000.0)) is None
    assert _one(_gap(_bars(), N - 3, volume=1000.0), {"gap_up": {"volume_filter": False}}) is not None


def test_gap_up_does_not_feed_buy_setups():
    import inspect
    import setups
    assert "gap" not in inspect.signature(setups.build_buy_setups).parameters


def test_min_gap_three_percent():
    on = {"gap_up": {"min_gap_filter": True, "min_gap_pct": 3.0}}
    # Prior high is 101. 2.9% over it is out, exactly 3% is in.
    assert _one(_gap(_bars(), N - 3, open_=101.0 * 1.029, low=101.5), on) is None
    row = _one(_gap(_bars(), N - 3, open_=101.0 * 1.03, low=101.5), on)
    assert row is not None and abs(row["gap_pct"] - 3.0) < 1e-9
    # A 1% gap is out with the switch on, and in with it off.
    assert _one(_gap(_bars(), N - 3, open_=101.0 * 1.01, low=101.5), on) is None
    off = {"gap_up": {"min_gap_filter": False, "min_gap_pct": 3.0}}
    assert _one(_gap(_bars(), N - 3, open_=101.0 * 1.01, low=101.5), off) is not None


def test_config_default_is_three_percent():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    p = gap_up.gap_cfg(cfg)
    assert p["min_gap_filter"] is True and p["min_gap_pct"] == 3.0
    text = dict(tables.help_rows())["Gap Up"]
    assert "at least 3%" in text
