"""O'Neil CANSLIM scanner: every rule is a hard gate, and there is no soft tier."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import setups  # noqa: E402
import tables  # noqa: E402


def _cfg():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _dates(n, start="2024-01-02"):
    return pd.bdate_range(start, periods=n)


def _panel(tickers, frames):
    close, high, low, vol = {}, {}, {}, {}
    for t, f in frames.items():
        close[t] = f["close"]
        high[t] = f["high"]
        low[t] = f["low"]
        vol[t] = f["volume"]
    return pd.DataFrame(close), pd.DataFrame(high), pd.DataFrame(low), pd.DataFrame(vol)


def _uni(names, isin=None):
    rows = []
    for t in names:
        rows.append({
            "ticker": t,
            "company": t + " Co",
            "sector": "Information Technology",
            "index_membership": "Nifty 50 / Total Market",
            "isin": (isin or {}).get(t, "INE" + t[:6].ljust(6, "0") + "01019"),
        })
    return pd.DataFrame(rows)


def _climb_frame(n=260, start=50.0, vol=2_000_000.0):
    idx = _dates(n)
    close = start * (1.002 ** np.arange(n))
    return pd.DataFrame({
        "close": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "volume": np.full(n, vol),
    }, index=idx)


def _climb_panel(names):
    frame = _climb_frame()
    frames = {t: frame.copy() for t in names}
    return _panel(names, frames)


def _passing_quarters(*tickers):
    rows = []
    for t in tickers:
        rows.append({"ticker": t, "frame": "CY2024Q3", "eps": 1.0, "revenue": 100.0})
        rows.append({"ticker": t, "frame": "CY2025Q3", "eps": 1.4, "revenue": 130.0})
    return pd.DataFrame(rows)


def _passing_annual(*tickers, roe=25.0):
    rows = []
    for t in tickers:
        rows.append({"ticker": t, "frame": "CY2023", "eps": 2.0, "net_income": 20.0, "equity": 100.0})
        # latest year: ROE = net_income / equity
        rows.append({"ticker": t, "frame": "CY2024", "eps": 2.5, "net_income": roe, "equity": 100.0})
    return pd.DataFrame(rows)


def _streak_annual(*tickers, roe=25.0, pcts=(30, 30, 30)):
    """Four years of EPS so three YoY figures can be computed. pcts is latest-first."""
    rows = []
    for t in tickers:
        # Work backwards from a latest EPS of 10.
        latest = 10.0
        years = [latest]
        for p in pcts:
            prev = years[-1] / (1.0 + p / 100.0)
            years.append(prev)
        years = list(reversed(years))  # oldest first, 4 values
        for i, eps in enumerate(years):
            rec = {"ticker": t, "frame": "CY%d" % (2021 + i), "eps": eps, "net_income": roe, "equity": 100.0}
            rows.append(rec)
    return pd.DataFrame(rows)


def _passing_holders(*tickers, fii=0.5, dii=0.0):
    return pd.DataFrame([{"ticker": t, "fii_chg": fii, "dii_chg": dii} for t in tickers])


def _scan(names, **kwargs):
    close, high, low, vol = _climb_panel(names)
    quarters = kwargs.pop("quarters", _passing_quarters(*names))
    annual = kwargs.pop("annual", _passing_annual(*names))
    holders = kwargs.pop("holders", _passing_holders(*names))
    uni = kwargs.pop("universe", _uni(names))
    rs_map = kwargs.pop("rs_map", {t: 88 for t in names})
    cfg = kwargs.pop("cfg", _cfg())
    return setups.scan_canslim(close, high, low, vol, uni, quarters, annual, holders, cfg, rs_map=rs_map)


def test_passing_name_is_listed_as_strict():
    out, market = _scan(["AAA"])
    assert list(out["ticker"]) == ["AAA"]
    row = out.iloc[0]
    assert row["qualify"] == "strict"
    assert row["status"] in ("READY", "BROKEN OUT today", "WATCHING")
    assert row["c_quarterly_eps"] == 40.0
    assert row["c_sales"] == 30.0
    assert row["a_annual_eps"] == 25.0
    assert row["a_roe"] == 25.0
    assert row["rs"] == 88
    assert float(row["s_ud"]) >= 1.0
    assert row["i_trend"] == "up"
    assert "does not block" in row["reason"] or "display only" in row["reason"]
    # Market is shown, but a missing second index must not empty the list.
    assert "not verified" in market["text"] or market["label"]


def test_no_soft_tier_and_rs_under_80_is_out():
    out, _ = _scan(["AAA", "BBB"], rs_map={"AAA": 80, "BBB": 79})
    assert list(out["ticker"]) == ["AAA"]
    assert "soft" not in set(out["qualify"])


def test_funds_and_etfs_are_excluded():
    uni = _uni(["AAA", "BBB"], isin={"AAA": "INE123A01019", "BBB": "INF204KB18R4"})
    out, _ = _scan(["AAA", "BBB"], universe=uni)
    assert list(out["ticker"]) == ["AAA"]


def test_missing_eps_is_not_listed():
    quarters = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q3", "revenue": 100.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "revenue": 130.0},
    ])
    out, _ = _scan(["AAA"], quarters=quarters)
    assert len(out) == 0


def test_sales_must_pass_or_accelerate():
    # Sales +10% and prior quarter also +10% (not accelerating) fails.
    slow = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q2", "eps": 1.0, "revenue": 100.0},
        {"ticker": "AAA", "frame": "CY2024Q3", "eps": 1.0, "revenue": 100.0},
        {"ticker": "AAA", "frame": "CY2025Q2", "eps": 1.4, "revenue": 110.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "eps": 1.4, "revenue": 110.0},
    ])
    out, _ = _scan(["AAA"], quarters=slow)
    assert len(out) == 0
    # Same +10% latest sales, but the quarter before fell, so sales are accelerating.
    accel = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q2", "eps": 1.0, "revenue": 100.0},
        {"ticker": "AAA", "frame": "CY2024Q3", "eps": 1.0, "revenue": 100.0},
        {"ticker": "AAA", "frame": "CY2025Q2", "eps": 1.4, "revenue": 80.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "eps": 1.4, "revenue": 110.0},
    ])
    out2, _ = _scan(["AAA"], quarters=accel)
    assert list(out2["ticker"]) == ["AAA"]
    assert "accelerating" in out2.iloc[0]["c_status"].lower()


def test_missing_sales_without_acceleration_is_not_listed():
    quarters = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q3", "eps": 1.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "eps": 1.4},
    ])
    out, _ = _scan(["AAA"], quarters=quarters)
    assert len(out) == 0


def test_low_roe_fails_and_missing_roe_does_not():
    out_low, _ = _scan(["AAA"], annual=_passing_annual("AAA", roe=16.0))
    assert len(out_low) == 0
    annual = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2023", "eps": 2.0},
        {"ticker": "AAA", "frame": "CY2024", "eps": 2.5},
    ])
    out_miss, _ = _scan(["AAA"], annual=annual)
    assert list(out_miss["ticker"]) == ["AAA"]
    assert out_miss.iloc[0]["a_roe"] == ""
    assert "ROE is not verified" in out_miss.iloc[0]["a_status"]


def test_n_must_be_within_15_percent():
    close, high, low, vol = _climb_panel(["AAA"])
    # Drop the last close far below the 52-week high.
    peak = float(close["AAA"].iloc[-2])
    close.loc[close.index[-1], "AAA"] = peak * 0.80
    high.loc[high.index[-1], "AAA"] = peak * 0.81
    low.loc[low.index[-1], "AAA"] = peak * 0.79
    out, _ = setups.scan_canslim(
        close, high, low, vol, _uni(["AAA"]), _passing_quarters("AAA"), _passing_annual("AAA"),
        _passing_holders("AAA"), _cfg(), rs_map={"AAA": 88},
    )
    assert len(out) == 0


def test_i_uses_fii_dii_only_and_flat_passes():
    # Promoter jump and inst_up must not count as I.
    promoter_only = pd.DataFrame([{"ticker": "AAA", "promoter_chg": 5.0, "inst_up": 10, "inst_down": 0}])
    out, _ = _scan(["AAA"], holders=promoter_only)
    assert list(out["ticker"]) == ["AAA"]
    assert out.iloc[0]["i_trend"] == "not verified"
    # Flat FII+DII (inside the 0.25 band) passes and is listed.
    flat = _passing_holders("AAA", fii=0.10, dii=0.05)
    out_flat, _ = _scan(["AAA"], holders=flat)
    assert list(out_flat["ticker"]) == ["AAA"]
    assert out_flat.iloc[0]["i_trend"] == "flat"
    # A real fall is a fail, so the name is not listed.
    down = _passing_holders("AAA", fii=-0.40, dii=0.0)
    out_down, _ = _scan(["AAA"], holders=down)
    assert len(out_down) == 0


def test_scorecard_i_matches_the_scanner():
    close, high, low, vol = _climb_panel(["AAA", "BBB", "CCC"])
    uni = _uni(["AAA", "BBB", "CCC"])
    holders = pd.DataFrame([
        {"ticker": "AAA", "fii_chg": 0.10, "dii_chg": 0.05, "promoter_chg": -2.0, "inst_up": 0, "inst_down": 10},
        {"ticker": "BBB", "fii_chg": -0.80, "dii_chg": 0.0},
        {"ticker": "CCC", "promoter_chg": 4.0, "inst_up": 8, "inst_down": 0},
    ])
    card = setups.build_stock_canslim(
        close, high, low, vol, uni, _passing_quarters("AAA", "BBB", "CCC"),
        _passing_annual("AAA", "BBB", "CCC"), holders, cfg=_cfg(),
        rs_table=pd.DataFrame([{"ticker": t, "rs": 88} for t in ("AAA", "BBB", "CCC")]),
    )
    marks = {r.ticker: (r.i_mark, r.i_value) for r in card.itertuples()}
    assert marks["AAA"] == ("pass", "flat")
    assert marks["BBB"] == ("fail", "down")
    assert marks["CCC"] == ("not verified", "")


def test_scorecard_c_fails_when_sales_miss():
    close, high, low, vol = _climb_panel(["AAA"])
    quarters = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q3", "eps": 1.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "eps": 1.4},
    ])
    card = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA"]), quarters, _passing_annual("AAA"),
        _passing_holders("AAA"), cfg=_cfg(),
        rs_table=pd.DataFrame([{"ticker": "AAA", "rs": 88}]),
    )
    row = card.iloc[0]
    assert row["c_value"] == 40.0
    assert row["c_mark"] == "fail"
    assert row["c_sales"] == ""


def test_scorecard_missing_eps_stays_blank():
    close, high, low, vol = _climb_panel(["AAA"])
    card = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        cfg=_cfg(),
    )
    row = card.iloc[0]
    assert row["c_value"] == "" and row["c_mark"] == "not verified"
    assert row["a_value"] == "" and row["a_mark"] == "not verified"
    assert row["i_mark"] == "not verified"
    assert 0 not in (row["c_value"], row["a_value"], row["i_value"])


def test_upper_circuit_is_watching_not_ready_or_broken_out():
    close, high, low, vol = _climb_panel(["AAA"])
    prev = float(close["AAA"].iloc[-2])
    locked = round(prev * 1.10, 6)
    close.loc[close.index[-1], "AAA"] = locked
    high.loc[high.index[-1], "AAA"] = locked
    low.loc[low.index[-1], "AAA"] = prev * 1.02
    vol.loc[vol.index[-1], "AAA"] = 20_000_000.0
    # The lock is a new high on huge volume, which would otherwise be BROKEN OUT today.
    out, _ = setups.scan_canslim(
        close, high, low, vol, _uni(["AAA"]), _passing_quarters("AAA"), _passing_annual("AAA"),
        _passing_holders("AAA"), _cfg(), rs_map={"AAA": 88},
    )
    assert list(out["ticker"]) == ["AAA"]
    assert out.iloc[0]["status"] == "WATCHING"
    assert "upper circuit" in out.iloc[0]["reason"]


def test_sma_stack_is_required():
    close, high, low, vol = _climb_panel(["AAA"])
    # Flatten the last 200 sessions so SMA50 cannot sit above SMA200 after a long decline.
    n = len(close)
    decline = np.linspace(float(close["AAA"].iloc[-201]), float(close["AAA"].iloc[-201]) * 0.60, 201)
    close.iloc[-201:, close.columns.get_loc("AAA")] = decline
    high.iloc[-201:, high.columns.get_loc("AAA")] = decline * 1.01
    low.iloc[-201:, low.columns.get_loc("AAA")] = decline * 0.99
    out, _ = setups.scan_canslim(
        close, high, low, vol, _uni(["AAA"]), _passing_quarters("AAA"), _passing_annual("AAA"),
        _passing_holders("AAA"), _cfg(), rs_map={"AAA": 88},
    )
    assert len(out) == 0


def test_up_down_volume_under_one_is_not_listed():
    close, high, low, vol = _climb_panel(["AAA"])
    # Keep the climb (so SMAs still stack) but make up days quiet and down days heavy
    # in the last 50 sessions, with only tiny down ticks so the 52-week high still holds.
    closes = close["AAA"].to_numpy(dtype=float).copy()
    volumes = vol["AAA"].to_numpy(dtype=float).copy()
    for i in range(len(closes) - 50, len(closes)):
        if (i % 2) == 0:
            closes[i] = closes[i - 1] * 1.0001
            volumes[i] = 50_000.0
        else:
            closes[i] = closes[i - 1] * 0.9999
            volumes[i] = 5_000_000.0
    # Keep the last close near the high enough to stay within 15%.
    peak = max(float(closes.max()), float(close["AAA"].max()))
    assert closes[-1] / peak - 1.0 >= -0.15
    close["AAA"] = closes
    high["AAA"] = closes * 1.01
    low["AAA"] = closes * 0.99
    vol["AAA"] = volumes
    out, _ = setups.scan_canslim(
        close, high, low, vol, _uni(["AAA"]), _passing_quarters("AAA"), _passing_annual("AAA"),
        _passing_holders("AAA"), _cfg(), rs_map={"AAA": 88},
    )
    assert len(out) == 0


def test_vcp_heuristic_is_not_a_gate():
    # A passing name with no contraction still lists, and the column is still written.
    out, _ = _scan(["AAA"])
    assert list(out["ticker"]) == ["AAA"]
    assert "vcp_heuristic" in out.columns
    assert "not a qualify rule" in out.iloc[0]["reason"]


def test_help_describes_the_new_rules():
    help_map = dict(tables.help_rows())
    scan = help_map["CANSLIM scanner"]
    card = help_map["Stock CANSLIM"]
    assert "\u2014" not in scan and "\u2014" not in card
    for blob in (scan, card):
        assert "80 or higher" in blob or "80 or more" in blob
        assert "FII and DII" in blob
        assert "accelerating" in blob or "faster than the quarter before" in blob
        assert "does not fail" in blob or "does not block" in blob
    assert "soft watch" in scan
    assert "There is no soft watch list" in scan
    assert "upper circuit" in scan
    assert "display only" in scan
    assert "feature.stock_canslim" in card
    assert "near miss" in scan.lower() or "near misses" in scan.lower()
    assert "three years" in scan.lower() or "3-year" in scan.lower() or "3 year" in scan.lower()


def test_market_does_not_empty_the_list():
    # The India-style snapshot is attached for display. Even when those averages
    # are missing, a name that passes the stock rules stays on the list.
    out, market = _scan(["AAA"])
    assert len(out) == 1
    assert "m_status" in out.columns
    assert out.iloc[0]["m_status"]
    assert "block" in out.iloc[0]["reason"]


def test_short_annual_history_does_not_fail_the_streak():
    # Two years can compute latest YoY, but not a 3-year streak. That stays not verified.
    out, _ = _scan(["AAA"], annual=_passing_annual("AAA"))
    assert list(out["ticker"]) == ["AAA"]
    assert out.iloc[0]["a_streak"] == "" or out.iloc[0]["a_streak"] != "3/3"
    assert "not verified" in str(out.iloc[0]["a_status"]).lower() or "3-year" in str(out.iloc[0]["a_status"])


def test_three_year_streak_is_a_gate_when_history_exists():
    good = _streak_annual("GOOD", pcts=(30, 40, 50))
    bad = _streak_annual("BAD", pcts=(40, 10, 40))  # middle year only 10%
    annual = pd.concat([good, bad], ignore_index=True)
    out, market, near = setups.scan_canslim(
        *_climb_panel(["GOOD", "BAD"]), _uni(["GOOD", "BAD"]),
        _passing_quarters("GOOD", "BAD"), annual, _passing_holders("GOOD", "BAD"),
        _cfg(), rs_map={"GOOD": 88, "BAD": 88}, include_near=True,
    )
    assert list(out["ticker"]) == ["GOOD"]
    assert out.iloc[0]["a_streak"] == "3/3"
    assert list(near["ticker"]) == ["BAD"]
    assert near.iloc[0]["missed_rule"] == "A"
    # Scorecard A also fails when the streak is short.
    close, high, low, vol = _climb_panel(["BAD"])
    card = setups.build_stock_canslim(close, high, low, vol, _uni(["BAD"]), _passing_quarters("BAD"), bad, _passing_holders("BAD"), _cfg())
    assert card.iloc[0]["a_mark"] == "fail"
    assert card.iloc[0]["a_streak"] == "2/3"


def test_near_miss_is_exactly_one_rule_and_does_not_change_the_main_list():
    close, high, low, vol = _climb_panel(["AAA", "LOWL", "LOWC", "BOTH"])
    uni = _uni(["AAA", "LOWL", "LOWC", "BOTH"])
    quarters = pd.concat([
        _passing_quarters("AAA", "LOWL"),
        pd.DataFrame([
            {"ticker": "LOWC", "frame": "CY2024Q3", "eps": 1.0, "revenue": 100.0},
            {"ticker": "LOWC", "frame": "CY2025Q3", "eps": 1.05, "revenue": 101.0},  # C fails
            {"ticker": "BOTH", "frame": "CY2024Q3", "eps": 1.0, "revenue": 100.0},
            {"ticker": "BOTH", "frame": "CY2025Q3", "eps": 1.05, "revenue": 101.0},  # C fails
        ]),
    ], ignore_index=True)
    annual = _passing_annual("AAA", "LOWL", "LOWC", "BOTH")
    holders = _passing_holders("AAA", "LOWL", "LOWC", "BOTH")
    rs_map = {"AAA": 88, "LOWL": 79, "LOWC": 88, "BOTH": 79}  # LOWL misses L; BOTH misses C and L
    main, _, near = setups.scan_canslim(close, high, low, vol, uni, quarters, annual, holders, _cfg(), rs_map=rs_map, include_near=True)
    assert list(main["ticker"]) == ["AAA"]
    assert "near miss" not in set(main["qualify"])
    names = dict(zip(near["ticker"], near["missed_rule"]))
    assert names["LOWL"] == "L"
    assert names["LOWC"] == "C"
    assert "BOTH" not in names
    assert "AAA" not in names
    # Leaders and the usual unpack still use the main list only.
    main2, _ = setups.scan_canslim(close, high, low, vol, uni, quarters, annual, holders, _cfg(), rs_map=rs_map)
    assert list(main2["ticker"]) == ["AAA"]


def test_eps_acceleration_is_shown_and_is_not_a_gate():
    # Latest EPS YoY 40%, prior quarter YoY 50% so acceleration is no, but C still passes on +25% / sales +25%.
    quarters = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q2", "eps": 1.0, "revenue": 100.0},
        {"ticker": "AAA", "frame": "CY2024Q3", "eps": 1.0, "revenue": 100.0},
        {"ticker": "AAA", "frame": "CY2025Q2", "eps": 1.5, "revenue": 130.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "eps": 1.4, "revenue": 130.0},
    ])
    out, _ = _scan(["AAA"], quarters=quarters)
    assert list(out["ticker"]) == ["AAA"]
    assert out.iloc[0]["c_eps_accel"] == "no"


def test_i_down_is_a_near_miss_and_missing_i_is_not():
    close, high, low, vol = _climb_panel(["DOWN", "MISS"])
    uni = _uni(["DOWN", "MISS"])
    quarters = _passing_quarters("DOWN", "MISS")
    annual = _passing_annual("DOWN", "MISS")
    holders = pd.DataFrame([
        {"ticker": "DOWN", "fii_chg": -0.8, "dii_chg": 0.0},
        {"ticker": "MISS"},
    ])
    main, _, near = setups.scan_canslim(
        close, high, low, vol, uni, quarters, annual, holders, _cfg(),
        rs_map={"DOWN": 88, "MISS": 88}, include_near=True,
    )
    assert list(main["ticker"]) == ["MISS"]
    assert list(near["ticker"]) == ["DOWN"]
    assert near.iloc[0]["missed_rule"] == "I"


if __name__ == "__main__":
    test_passing_name_is_listed_as_strict()
    test_no_soft_tier_and_rs_under_80_is_out()
    test_funds_and_etfs_are_excluded()
    test_missing_eps_is_not_listed()
    test_sales_must_pass_or_accelerate()
    test_missing_sales_without_acceleration_is_not_listed()
    test_low_roe_fails_and_missing_roe_does_not()
    test_n_must_be_within_15_percent()
    test_i_uses_fii_dii_only_and_flat_passes()
    test_scorecard_i_matches_the_scanner()
    test_scorecard_c_fails_when_sales_miss()
    test_scorecard_missing_eps_stays_blank()
    test_upper_circuit_is_watching_not_ready_or_broken_out()
    test_sma_stack_is_required()
    test_up_down_volume_under_one_is_not_listed()
    test_vcp_heuristic_is_not_a_gate()
    test_help_describes_the_new_rules()
    test_market_does_not_empty_the_list()
    test_short_annual_history_does_not_fail_the_streak()
    test_three_year_streak_is_a_gate_when_history_exists()
    test_near_miss_is_exactly_one_rule_and_does_not_change_the_main_list()
    test_eps_acceleration_is_shown_and_is_not_a_gate()
    test_i_down_is_a_near_miss_and_missing_i_is_not()
    print("oneil canslim ok")
