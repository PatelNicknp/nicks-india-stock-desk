"""Offline checks for the Episodic Pivot scan and the saved market cap. Synthetic tapes only."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import market_cap  # noqa: E402
import setups  # noqa: E402
import tables  # noqa: E402

FLAT = 150


def _uni(names):
    return pd.DataFrame([
        {"ticker": t, "company": t + " Co", "sector": "Industrials", "index_membership": "Smallcap 250", "nse_symbol": t}
        for t in names
    ])


def _tape(ep=(112.0, 113.0, 111.5, 112.8, 5_000_000.0), after=None, base=100.0, flat=FLAT, drift=0.0):
    """flat bars near `base` (high +1, low -1, 1M volume), one EP bar (open, high, low, close, volume), then `after` bars.

    after: list of (open, high, low, close) with 1M volume.
    """
    o, h, l, c, v = [], [], [], [], []
    for i in range(flat):
        px = base + drift * i
        o.append(px); h.append(px + 1.0); l.append(px - 1.0); c.append(px); v.append(1_000_000.0)
    eo, eh, el, ec, ev = ep
    o.append(eo); h.append(eh); l.append(el); c.append(ec); v.append(ev)
    for bo, bh, bl, bc in (after or []):
        o.append(bo); h.append(bh); l.append(bl); c.append(bc); v.append(1_000_000.0)
    idx = pd.bdate_range("2026-01-01", periods=len(c))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)


def _scan(frame, cfg=None, ticker="AAA", **kw):
    def one(col):
        return frame[[col]].rename(columns={col: ticker})
    return setups.scan_episodic_pivot(one("close"), one("high"), one("low"), one("volume"), _uni([ticker]), cfg,
                                      opn=one("open"), **kw)


def _cfg(**kw):
    return {"episodic_pivot": kw}


def _row(frame, cfg=None, **kw):
    out = _scan(frame, cfg, **kw)
    assert len(out) == 1, out
    return out.iloc[0]


# ---------------------------------------------------------------- EP day rules
def test_gap_on_big_volume_is_ep_today():
    row = _row(_tape())
    assert row["status"] == "EP TODAY"
    assert row["ep_trigger"] == "Gap up and big up day"
    assert _row(_tape(), _cfg(close_change_trigger=False))["ep_trigger"] == "Gap up"
    assert float(row["gap_pct"]) == 12.0
    assert float(row["entry"]) == 113.0 and float(row["pivot"]) == 113.0
    assert float(row["stop"]) == 111.5
    assert row["stop_basis"] == "EP-day low"
    assert float(row["rvol"]) == 5.0
    assert row["stop_check"] == "OK"
    assert "buy above today's high 113.0" in row["reason"]


def test_small_gap_and_small_move_is_not_an_ep():
    assert len(_scan(_tape(ep=(109.0, 109.5, 108.5, 107.5, 5e6)))) == 0


def test_stockbee_close_change_trigger_and_its_switch():
    frame = _tape(ep=(101.0, 109.5, 100.5, 109.0, 5e6))
    row = _row(frame, _cfg(stop_width_check=False))
    assert row["ep_trigger"] == "Big up day"
    assert row["status"] == "EP TODAY"
    assert len(_scan(frame, _cfg(close_change_trigger=False))) == 0


def test_gap_switch_and_number():
    assert len(_scan(_tape(), _cfg(gap_trigger=False, close_change_trigger=False))) == 0
    assert len(_scan(_tape(), _cfg(gap_min_pct=15, close_change_trigger=False))) == 0


def test_volume_rule_and_its_switch():
    frame = _tape(ep=(112.0, 113.0, 111.5, 112.8, 2_500_000.0))
    assert len(_scan(frame)) == 0
    assert len(_scan(frame, _cfg(rvol_filter=False))) == 1
    assert len(_scan(frame, _cfg(rvol_min=2))) == 1


def test_price_floor_rs_20():
    frame = _tape(ep=(16.8, 16.95, 16.7, 16.9, 5e6), base=15.0)
    assert len(_scan(frame, _cfg(stop_width_check=False))) == 0
    assert len(_scan(frame, _cfg(price_floor=False, stop_width_check=False))) == 1


def test_weak_close_is_faded_and_has_no_entry():
    row = _row(_tape(ep=(112.0, 116.0, 109.0, 110.0, 5e6)))
    assert row["status"] == "EP FADED"
    assert pd.isna(row["entry"]) or row["entry"] == ""
    assert "weak" in row["reason"]
    # Turn both close checks off and the same day is a confirmed EP.
    row = _row(_tape(ep=(112.0, 116.0, 109.0, 110.0, 5e6)), _cfg(confirm_close_upper_half=False, confirm_close_above_open=False))
    assert row["status"] == "EP TODAY"


def test_upper_circuit_lock_is_flagged_and_kept_out_of_buy_setups():
    frame = _tape(ep=(105.0, 120.0, 104.0, 120.0, 5e6))
    row = _row(frame, _cfg(stop_width_check=False))
    assert row["status"] == "EP TODAY"
    assert row["circuit_flag"] == setups.EP_UC_TEXT
    assert setups.ep_upper_circuit(100.0, 120.0, 120.0) == 20
    assert setups.ep_upper_circuit(100.0, 112.0, 111.0) == 0
    assert len(setups.ep_buy_frame(_scan(frame, _cfg(stop_width_check=False)))) == 0
    assert _row(frame, _cfg(stop_width_check=False, upper_circuit_flag=False))["circuit_flag"] in ("", None) or \
        pd.isna(_row(frame, _cfg(stop_width_check=False, upper_circuit_flag=False))["circuit_flag"])


def test_stop_too_wide_against_adr():
    row = _row(_tape(ep=(112.0, 120.0, 111.0, 119.0, 5e6)))
    assert row["stop_check"] == "Too wide, skip"
    assert float(row["risk_vs_adr"]) > 1.5
    assert _row(_tape(ep=(112.0, 120.0, 111.0, 119.0, 5e6)), _cfg(max_stop_adr_mult=5))["stop_check"] == "OK"
    assert _row(_tape(ep=(112.0, 120.0, 111.0, 119.0, 5e6)), _cfg(stop_width_check=False))["stop_check"] == "OK"


# ---------------------------------------------------------------- after the EP day
def test_day_two_to_five_is_watching():
    after = [(112.5, 112.9, 112.0, 112.5), (112.4, 112.8, 112.0, 112.6)]
    row = _row(_tape(after=after))
    assert row["status"] == "WATCHING"
    assert int(row["days_since_ep"]) == 2
    assert float(row["entry"]) == 113.0


def test_going_above_the_ep_high_is_broken_out_today():
    after = [(112.5, 112.9, 112.0, 112.5), (113.5, 114.5, 113.2, 114.0)]
    row = _row(_tape(after=after))
    assert row["status"] == "BROKEN OUT today"
    # Opened above the EP-day high, so the fill is the open.
    assert float(row["entry"]) == 113.5
    assert float(row["stop"]) == 111.5
    assert row["signal"] == "HOLD"


def test_closing_under_the_ep_low_before_a_buy_is_closed():
    after = [(112.0, 112.5, 110.0, 110.5)]
    row = _row(_tape(after=after))
    assert row["status"] == "CLOSED"
    assert "under the EP-day low" in row["exit_reason"]


def test_closed_rows_drop_off_after_the_keep_days():
    after = [(112.0, 112.5, 110.0, 110.5)] + [(110.5, 111.0, 110.0, 110.5)] * 12
    assert len(_scan(_tape(after=after))) == 0
    assert len(_scan(_tape(after=after), _cfg(closed_keep_days=30))) == 1


def test_in_trade_partial_window_breakeven_and_trail_exit():
    up = [(113.5, 114.5, 113.2, 114.0), (114.0, 115.0, 113.8, 114.8), (114.8, 115.6, 114.5, 115.4), (115.4, 116.0, 115.0, 115.8)]
    row = _row(_tape(after=up))
    assert row["status"] == "IN TRADE"
    assert int(row["days_in_trade"]) == 3
    assert row["signal"] == "SELL PART"
    # After the partial the stop is at breakeven (the fill).
    assert float(row["stop"]) == 113.5 and row["stop_basis"] == "breakeven"
    assert row["trail_with"] == "20-day"
    # A close under the 20-day after the partial closes the trade.
    down = up + [(115.8, 116.2, 113.8, 114.0), (114.0, 114.2, 113.6, 113.7), (113.0, 113.2, 109.0, 109.5)]
    row = _row(_tape(after=down))
    assert row["status"] == "CLOSED"
    assert row["exit_reason"] in ("breakeven stop", "first close under the 20-day average")
    assert row["signal"] in ("SELL", "STOPPED", "EXIT")
    assert row["result_pct"] != ""


def test_trail_length_follows_adr():
    assert setups.ep_trail_len(5.0) == 10
    assert setups.ep_trail_len(4.9) == 20
    assert setups.ep_trail_len(None) == 20


def test_no_follow_through_flag():
    flat_after = [(113.5, 114.0, 113.2, 113.6)] + [(113.6, 114.0, 113.3, 113.6)] * 6
    row = _row(_tape(after=flat_after), _cfg(trail_after_partial_only=True, breakeven_after_partial=False))
    assert row["status"] == "IN TRADE"
    assert row["signal"] == "NO FOLLOW-THROUGH"
    row = _row(_tape(after=flat_after), _cfg(breakeven_after_partial=False, time_stop_flag=False))
    assert row["signal"] == "HOLD"


def test_delayed_watch_after_a_fade_uses_a_tight_range():
    tight = [(110.5, 110.8, 110.2, 110.5)] * 6
    row = _row(_tape(ep=(112.0, 116.0, 109.0, 110.0, 5e6), after=tight))
    assert row["status"] == "DELAYED WATCH"
    assert float(row["entry"]) == 110.8 and float(row["stop"]) == 110.2
    assert len(_scan(_tape(ep=(112.0, 116.0, 109.0, 110.0, 5e6), after=tight), _cfg(delayed_watch=False))) == 1
    assert _row(_tape(ep=(112.0, 116.0, 109.0, 110.0, 5e6), after=tight), _cfg(delayed_watch=False))["status"] == "CLOSED"


# ---------------------------------------------------------------- ranking and catalyst
def test_neglect_grade():
    assert setups.ep_neglect_grade(5, 10) == "A"
    assert setups.ep_neglect_grade(5, 40) == "B"
    assert setups.ep_neglect_grade(25, 40) == "B"
    assert setups.ep_neglect_grade(45, 80) == "C"
    assert setups.ep_neglect_grade(None, None) == ""


def test_grade_a_sorts_first_inside_a_status():
    a = _tape()
    c = _tape(drift=1.0)  # ran up more than 30% in the 3 months before the EP
    last_c = c["close"].iloc[FLAT - 1]
    c.iloc[FLAT] = [last_c * 1.12, last_c * 1.13, last_c * 1.115, last_c * 1.128, 5e6]
    close = pd.DataFrame({"CCC": c["close"], "AAA": a["close"]})
    out = setups.scan_episodic_pivot(close, pd.DataFrame({"CCC": c["high"], "AAA": a["high"]}),
                                     pd.DataFrame({"CCC": c["low"], "AAA": a["low"]}),
                                     pd.DataFrame({"CCC": c["volume"], "AAA": a["volume"]}), _uni(["CCC", "AAA"]),
                                     _cfg(stop_width_check=False), opn=pd.DataFrame({"CCC": c["open"], "AAA": a["open"]}))
    assert list(out["ticker"]) == ["AAA", "CCC"]
    assert list(out["neglect_grade"]) == ["A", "C"]


def _earn(day, minute=11 * 60, surprise=25.0):
    ts = pd.Timestamp(day).tz_localize("Asia/Kolkata") + pd.Timedelta(minutes=minute)
    return pd.DataFrame([{"ticker": "AAA", "earnings_dt": ts.isoformat(), "eps_estimate": 2.0, "eps_actual": 2.5, "surprise_pct": surprise}])


def test_earnings_link_on_the_ep_day_and_catalyst_score():
    frame = _tape()
    ep_day = frame.index[FLAT]
    q = pd.DataFrame([
        {"ticker": "AAA", "end": "2025-03-31", "filed": "2025-05-01", "revenue": 100.0, "eps": 1.0},
        {"ticker": "AAA", "end": "2025-06-30", "filed": "2025-08-01", "revenue": 100.0, "eps": 1.0},
        {"ticker": "AAA", "end": "2026-03-31", "filed": "2026-05-01", "revenue": 120.0, "eps": 1.3},
        {"ticker": "AAA", "end": "2026-06-30", "filed": "2026-07-15", "revenue": 150.0, "eps": 1.6},
    ])
    row = _row(frame, earnings=_earn(ep_day), quarters=q)
    assert row["catalyst_tag"] == "Earnings EP"
    assert "during market hours" in row["report_timing"]
    assert float(row["surprise_pct"]) == 25.0
    assert float(row["rev_yoy_last_filed"]) == 50.0
    assert row["rev_accel"] == "yes"
    assert int(row["catalyst_score"]) == 4
    # Results two sessions before do not link.
    row = _row(frame, earnings=_earn(frame.index[FLAT - 2]))
    assert row["catalyst_tag"] != "Earnings EP"
    assert setups.ep_catalyst_score(None, {"eps_yoy": None, "rev_yoy": None, "rev_accel": None}) == 0


# ---------------------------------------------------------------- Nick's switches (all off by default)
def test_nick_switches_default_off():
    p = setups.EP_DEFAULTS
    for key in ("nick_gap_filter", "nick_rvol_filter", "nick_price_floor", "nick_min_mcap", "nick_min_avg_volume",
                "nick_max_perf_3m", "nick_require_earnings", "nick_require_catalyst", "nick_require_flat_base"):
        assert p[key] is False, key


def test_nick_gap_filter_drops_close_only_moves():
    frame = _tape(ep=(101.0, 109.5, 100.5, 109.0, 5e6))
    assert len(_scan(frame, _cfg(stop_width_check=False))) == 1
    assert len(_scan(frame, _cfg(stop_width_check=False, nick_gap_filter=True))) == 0


def test_nick_rvol_and_price_switches():
    frame = _tape(ep=(112.0, 113.0, 111.5, 112.8, 3_500_000.0))
    assert len(_scan(frame, _cfg(nick_rvol_filter=True, nick_rvol_min=4))) == 0
    assert len(_scan(frame, _cfg(nick_price_floor=True, nick_min_price=200))) == 0
    assert len(_scan(frame, _cfg(nick_price_floor=True, nick_min_price=20))) == 1


def test_nick_market_cap_switch_uses_saved_shares():
    frame = _tape()
    small = {"AAA": {"shares": 1e8, "source": "test", "as_of": "2026-06-30"}}   # about Rs 1,128 crore
    big = {"AAA": {"shares": 1e9, "source": "test", "as_of": "2026-06-30"}}     # about Rs 11,280 crore
    row = _row(frame, shares=small)
    assert float(row["market_cap_cr"]) == round(1e8 * 112.8 / 1e7, 0)
    assert row["small_young"] == "yes"
    assert len(_scan(frame, _cfg(nick_min_mcap=True), shares=small)) == 0
    assert len(_scan(frame, _cfg(nick_min_mcap=True), shares=big)) == 1
    # No share count means the switch cannot pass it.
    assert len(_scan(frame, _cfg(nick_min_mcap=True))) == 0


def test_nick_avg_volume_switch():
    frame = _tape()
    assert len(_scan(frame, _cfg(nick_min_avg_volume=True, nick_min_avg_volume_shares=500000))) == 1
    assert len(_scan(frame, _cfg(nick_min_avg_volume=True, nick_min_avg_volume_shares=2_000_000))) == 0


def test_nick_three_month_switch():
    c = _tape(drift=1.0)
    last_c = c["close"].iloc[FLAT - 1]
    c.iloc[FLAT] = [last_c * 1.12, last_c * 1.13, last_c * 1.115, last_c * 1.128, 5e6]
    assert len(_scan(c, _cfg(stop_width_check=False))) == 1
    assert len(_scan(c, _cfg(stop_width_check=False, nick_max_perf_3m=True))) == 0


def test_nick_earnings_catalyst_and_flat_base_switches():
    frame = _tape()
    ep_day = frame.index[FLAT]
    assert len(_scan(frame, _cfg(nick_require_earnings=True))) == 0
    assert len(_scan(frame, _cfg(nick_require_earnings=True), earnings=_earn(ep_day - pd.offsets.BDay(1), 16 * 60))) == 1
    assert len(_scan(frame, _cfg(nick_require_catalyst=True))) == 0
    assert len(_scan(frame, _cfg(nick_require_catalyst=True), earnings=_earn(ep_day))) == 1
    assert len(_scan(frame, _cfg(nick_require_flat_base=True))) == 1
    c = _tape(drift=1.0)
    last_c = c["close"].iloc[FLAT - 1]
    c.iloc[FLAT] = [last_c * 1.12, last_c * 1.13, last_c * 1.115, last_c * 1.128, 5e6]
    assert len(_scan(c, _cfg(stop_width_check=False, nick_require_flat_base=True))) == 0


# ---------------------------------------------------------------- Buy setups
def test_buy_setups_take_ep_entries_only():
    ep = pd.DataFrame([
        {"ticker": "EPT", "status": "EP TODAY", "pivot": 100.0, "stop": 96.0, "strength": 70, "stop_check": "OK", "circuit_flag": "",
         "company": "E", "sector": "Tech", "index_membership": "Nifty 50", "price": 99.0, "price_as_of": "2026-10-29"},
        {"ticker": "WID", "status": "EP TODAY", "pivot": 100.0, "stop": 80.0, "strength": 70, "stop_check": "Too wide, skip", "circuit_flag": "",
         "company": "W", "sector": "Tech", "index_membership": "Nifty 50", "price": 99.0, "price_as_of": "2026-10-29"},
        {"ticker": "UCL", "status": "EP TODAY", "pivot": 100.0, "stop": 96.0, "strength": 70, "stop_check": "OK", "circuit_flag": setups.EP_UC_TEXT,
         "company": "U", "sector": "Tech", "index_membership": "Nifty 50", "price": 99.0, "price_as_of": "2026-10-29"},
        {"ticker": "FAD", "status": "EP FADED", "pivot": 100.0, "stop": 96.0, "strength": 70, "stop_check": "OK", "circuit_flag": "",
         "company": "F", "sector": "Tech", "index_membership": "Nifty 50", "price": 99.0, "price_as_of": "2026-10-29"},
        {"ticker": "INT", "status": "IN TRADE", "pivot": 100.0, "stop": 96.0, "strength": 70, "stop_check": "OK", "circuit_flag": "",
         "company": "I", "sector": "Tech", "index_membership": "Nifty 50", "price": 99.0, "price_as_of": "2026-10-29"},
    ])
    scores = pd.DataFrame([{"ticker": t, "verdict": "BUY", "score": 9} for t in ("EPT", "WID", "UCL", "FAD", "INT")])
    empty = pd.DataFrame()
    out = setups.build_buy_setups(empty, empty, empty, empty, scores, sma_ok={t: True for t in scores["ticker"]},
                                  market={"spy": True, "qqq": True}, episodic_pivot=ep)
    assert list(out["ticker"]) == ["EPT"]
    assert out.iloc[0]["setup_sources"] == "EP"
    assert out.iloc[0]["best_status"] == "READY"
    assert float(out.iloc[0]["stop"]) == 96.0
    off = setups.build_buy_setups(empty, empty, empty, empty, scores, sma_ok={t: True for t in scores["ticker"]},
                                  market={"spy": True, "qqq": True}, episodic_pivot=ep, cfg=_cfg(feed_buy_setups=False))
    assert "EPT" not in set(off["ticker"])
    assert list(setups.BUY_SETUP_ORDER).index("EP") == list(setups.BUY_SETUP_ORDER).index("Marios") + 1


def test_switch_turns_the_scan_off():
    frame = _tape()
    out = setups.build_setups(
        frame[["close"]].rename(columns={"close": "AAA"}), frame[["high"]].rename(columns={"high": "AAA"}),
        frame[["low"]].rename(columns={"low": "AAA"}), frame[["volume"]].rename(columns={"volume": "AAA"}),
        _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        {"scanner_vcp": False, "scanner_canslim": False, "scanner_box": False, "scanner_flag": False, "scanner_52w": False,
         "scanner_leaders": False, "scanner_qullamaggie": False, "scanner_marios": False, "scanner_episodic_pivot": False},
    )
    assert len(out["scanner_episodic_pivot"]) == 0


# ---------------------------------------------------------------- saved market cap
def test_statement_shares_take_the_newest_period():
    q = pd.DataFrame([{"ticker": "AAA", "end": "2026-03-31", "shares": 1e7}, {"ticker": "AAA", "end": "2026-06-30", "shares": 2e7}])
    a = pd.DataFrame([{"ticker": "AAA", "end": "2026-03-31", "shares": 1.5e7}, {"ticker": "BBB", "end": "2026-03-31", "shares": 5e6}])
    got = market_cap.statement_shares(a, q)
    assert got["AAA"][0] == 2e7 and got["BBB"][0] == 5e6


def test_build_saves_market_cap_in_crore_and_keeps_old_names(tmp_path):
    close = pd.DataFrame({"AAA": [100.0, 110.0]}, index=pd.bdate_range("2026-10-28", periods=2))
    q = pd.DataFrame([{"ticker": "AAA", "end": "2026-06-30", "shares": 2e7}])
    old = pd.DataFrame([{"ticker": "OLD", "shares": 1e6, "shares_source": "Yahoo quote", "shares_as_of": "2026-01-01",
                         "close": 50, "close_date": "2026-01-01", "market_cap_cr": 5, "saved_on": "2026-01-01"}])
    table = market_cap.build(old, pd.DataFrame(), q, close, "2026-10-31")
    by = table.set_index("ticker")
    assert float(by.loc["AAA", "market_cap_cr"]) == 220.0
    assert "OLD" in by.index
    market_cap.save(table, str(tmp_path))
    back = market_cap.read_cache(str(tmp_path))
    assert set(back["ticker"]) == {"AAA", "OLD"}
    assert list(back.columns) == market_cap.COLUMNS


def test_fetch_missing_is_capped_and_does_not_ask_twice():
    calls = []

    def fake(symbol):
        calls.append(symbol)
        return 1e7 if symbol.startswith("A") else None

    table, asked, found = market_cap.fetch_missing(pd.DataFrame(columns=market_cap.COLUMNS), ["A1", "B1", "A2", "A3"],
                                                   None, "2026-10-31", max_names=2, pause=0, fetch=fake)
    assert asked == 2 and found == 1 and calls == ["A1.NS", "B1.NS"]
    calls.clear()
    table, asked, found = market_cap.fetch_missing(table, ["A1", "B1"], None, "2026-11-02", max_names=5, pause=0, fetch=fake)
    assert asked == 0 and calls == []
    # After the wait the name with no answer is asked again.
    table, asked, found = market_cap.fetch_missing(table, ["B1"], None, "2026-12-15", max_names=5, refetch_days=30, pause=0, fetch=fake)
    assert asked == 1


def test_fill_market_cap_on_rows():
    ep = pd.DataFrame([{"ticker": "AAA", "price": 100.0, "market_cap_cr": "", "shares": "", "mcap_source": "", "small_young": ""}])
    out = setups.ep_fill_market_cap(ep, {"AAA": {"shares": 1e8, "source": "Yahoo quote", "as_of": "2026-10-31"}})
    assert float(out.iloc[0]["market_cap_cr"]) == 1000.0
    assert out.iloc[0]["small_young"] == "yes"


# ---------------------------------------------------------------- config, help, columns
def test_config_has_every_switch_and_number():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["features"]["scanner_episodic_pivot"] is True
    block = cfg["episodic_pivot"]
    assert set(block) - {"_note"} == set(setups.EP_DEFAULTS)
    for k, v in setups.EP_DEFAULTS.items():
        assert block[k] == v, k
    assert block["min_price"] == 20 and block["close_change_min_pct"] == 8 and block["benchmark"] == "^NSEI"
    assert block["nick_min_mcap_cr"] == 4400


def test_help_settings_and_columns():
    topics = dict(tables.help_rows())
    assert "Episodic Pivot" in topics and "Market cap" in topics
    for text in (topics["Episodic Pivot"], topics["Market cap"]):
        assert "\u2014" not in text
    assert "feature.scanner_episodic_pivot" in topics["Episodic Pivot"]
    cols = tables.COLS["scanner_episodic_pivot"]
    for c in ("status", "ep_date", "pivot", "stop", "market_cap_cr", "circuit_flag", "signal", "result_pct", "disclaimer"):
        assert c in cols
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    rows = tables.settings_rows(cfg)
    assert "episodic_pivot.nick_min_mcap" in set(rows["setting"])


def test_page_has_no_tradingview_button_and_is_in_the_menu():
    with open(os.path.join(ROOT, "site", "js", "desk.js"), encoding="utf-8") as f:
        desk = f.read()
    with open(os.path.join(ROOT, "site", "js", "pages.js"), encoding="utf-8") as f:
        pages = f.read()
    assert '["Episodic Pivot", "episodic_pivot.html", "episodic"]' in desk
    assert 'episodic: "feature.scanner_episodic_pivot"' in desk
    start = pages.index("const epStatus")
    end = pages.index("const leaders = patternPage")
    block = pages[start:end]
    assert "TradingView" not in block and "\u2014" not in block
    assert os.path.exists(os.path.join(ROOT, "site", "episodic_pivot.html"))
