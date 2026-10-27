"""Offline checks for the Qullamaggie and Marios breakout scans. Synthetic tapes only."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import setups  # noqa: E402

PIVOT = 152.0


def _uni(names):
    return pd.DataFrame([
        {"ticker": t, "company": t + " Co", "sector": "Industrials", "index_membership": "Midcap 150"}
        for t in names
    ])


def _panel(frame, ticker="AAA"):
    return (frame[["close"]].rename(columns={"close": ticker}), frame[["high"]].rename(columns={"high": ticker}),
            frame[["low"]].rename(columns={"low": ticker}), frame[["volume"]].rename(columns={"volume": ticker}))


def _tape(last_close=155.0, last_vol=3_000_000.0, after=None):
    """100 flat bars, a 50% run over 40 bars, a 30-bar base that tightens, then today.

    after: optional list of (close, high, low) bars appended after today's bar.
    """
    close, high, low = [], [], []
    for _ in range(100):
        close.append(100.0); high.append(101.0); low.append(99.0)
    for px in np.linspace(101, 147, 40):
        close.append(px); high.append(px + 1.0); low.append(px - 1.0)
    # Base: first half swings wider, second half is tight and drifts up.
    for i in range(15):
        px = 146.0 + i * 0.1
        close.append(px); high.append(px + 3.0); low.append(px - 5.0)
    high[141] = PIVOT
    for i in range(15):
        px = 147.6 + i * 0.1
        close.append(px); high.append(px + 0.8); low.append(px - 0.8)
    close.append(last_close); high.append(last_close + 1.0); low.append(min(last_close, PIVOT) - 2.0)
    for c, h, l in (after or []):
        close.append(c); high.append(h); low.append(l)
    n = len(close)
    vol = np.full(n, 1_000_000.0)
    vol[170] = last_vol
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"close": close, "high": high, "low": low, "volume": vol}, index=idx)


def _scan(frame, fn=setups.scan_qullamaggie, cfg=None):
    c, h, l, v = _panel(frame)
    return fn(c, h, l, v, _uni(["AAA"]), cfg)


def test_breakout_detected_on_big_volume():
    out = _scan(_tape())
    assert len(out) == 1
    row = out.iloc[0]
    assert row["status"] == "BROKEN OUT today"
    assert float(row["pivot"]) == PIVOT
    # Stop is the breakout-day low, entry is the breakout close, risk shown.
    assert float(row["stop"]) == PIVOT - 2.0
    assert float(row["entry"]) == 155.0
    assert row["stop_basis"] == "breakout-day low"
    assert abs(float(row["risk_pct"]) - round((155.0 - 150.0) / 155.0 * 100, 1)) < 1e-9
    assert float(row["run_pct"]) >= 30
    assert 10 <= int(row["base_days"]) <= 40
    assert "breakout-day low" in row["reason"]


def test_no_breakout_on_low_volume():
    out = _scan(_tape(last_vol=1_100_000.0))
    row = out.iloc[0]
    assert row["status"] == "WATCHING"
    assert "volume was not 1.5 times" in row["reason"]


def test_ready_under_the_pivot_uses_todays_low():
    out = _scan(_tape(last_close=150.0, last_vol=900_000.0))
    row = out.iloc[0]
    assert row["status"] == "READY"
    assert float(row["entry"]) == PIVOT
    assert float(row["stop"]) == 148.0
    assert row["stop_basis"] == "today's low"
    assert "Stop is today's low" in row["reason"]


def test_no_run_means_no_setup():
    frame = _tape()
    frame.iloc[100:140, frame.columns.get_loc("close")] = 140.0
    frame.iloc[100:140, frame.columns.get_loc("high")] = 141.0
    frame.iloc[100:140, frame.columns.get_loc("low")] = 139.0
    frame.iloc[:100, frame.columns.get_loc("low")] = 135.0
    frame.iloc[:100, frame.columns.get_loc("close")] = 136.0
    frame.iloc[:100, frame.columns.get_loc("high")] = 137.0
    assert len(_scan(frame)) == 0


def test_config_numbers_are_used():
    cfg = {"qullamaggie": {"run_min_pct": 80}}
    assert len(_scan(_tape(), cfg=cfg)) == 0


def test_adr_target_math():
    high = np.full(20, 105.0)
    low = np.full(20, 100.0)
    assert abs(setups.marios_adr_pct(high, low, 20) - 5.0) < 1e-9
    lo, hi = setups.marios_targets(200.0, 4.0, 2.5, 3.0)
    assert abs(lo - 220.0) < 1e-9 and abs(hi - 224.0) < 1e-9
    assert setups.marios_adr_pct(high[:5], low[:5], 20) is None


def test_trail_selection():
    assert setups.marios_trail_len(5.0, 5.0) == 10
    assert setups.marios_trail_len(7.2, 5.0) == 10
    assert setups.marios_trail_len(4.99, 5.0) == 20
    assert setups.marios_trail_len(None, 5.0) == 20


def test_marios_breakout_row_has_both_targets_and_trail():
    frame = _tape()
    out = _scan(frame, setups.scan_marios)
    row = out.iloc[0]
    assert row["status"] == "BROKEN OUT today"
    adr = setups.marios_adr_pct(frame["high"].to_numpy(), frame["low"].to_numpy(), 20)
    assert abs(float(row["adr_pct"]) - round(adr, 2)) < 1e-9
    lo, hi = setups.marios_targets(155.0, adr, 2.5, 3.0)
    assert float(row["target_low"]) == round(lo, 2)
    assert float(row["target_high"]) == round(hi, 2)
    assert row["trail_with"] == ("10-day" if adr >= 5 else "20-day")


def test_marios_in_trade_partial_and_sell():
    # Three days up after the breakout, far enough to reach the partial zone.
    up = [(162.0, 175.0, 160.0), (166.0, 168.0, 163.0), (168.0, 170.0, 166.0)]
    out = _scan(_tape(after=up), setups.scan_marios)
    row = out.iloc[0]
    assert row["status"] == "IN TRADE"
    assert float(row["entry"]) == 155.0
    assert row["partial_hit"] == "yes"
    assert row["trail_signal"] == "HOLD"
    assert row["breakout_date"] != ""
    # Then a close far under the trail line.
    down = up + [(140.0, 151.0, 139.0)]
    row = _scan(_tape(after=down), setups.scan_marios).iloc[0]
    assert row["status"] == "IN TRADE"
    assert row["trail_signal"] == "SELL"
    assert row["stop_hit"] == "yes"


def test_qullamaggie_does_not_show_in_trade():
    up = [(162.0, 175.0, 160.0)]
    out = _scan(_tape(after=up))
    assert "IN TRADE" not in set(out["status"]) if len(out) else True


def _ready(t, pivot=100.0, stop=96.0):
    return {"ticker": t, "status": "READY", "pivot": pivot, "stop": stop, "strength": 60,
            "company": t, "sector": "Tech", "index_membership": "Nifty 50", "price": 99, "price_as_of": "2026-10-23"}


def test_buy_setups_take_the_new_scans_and_keep_the_risk_rule():
    empty = pd.DataFrame()
    qm = pd.DataFrame([_ready("QQQM"), _ready("WIDE", stop=80.0)])
    mar = pd.DataFrame([_ready("QQQM")])
    scores = pd.DataFrame([{"ticker": "QQQM", "verdict": "BUY", "score": 9}, {"ticker": "WIDE", "verdict": "BUY", "score": 9}])
    out = setups.build_buy_setups(empty, empty, empty, empty, scores,
                                  sma_ok={"QQQM": True, "WIDE": True}, market={"spy": True, "qqq": True},
                                  qullamaggie=qm, marios=mar)
    by = out.set_index("ticker")
    assert by.loc["QQQM", "setup_sources"] == "Qullamaggie + Marios"
    # A 20% setup stop is capped by the 7% desk stop, so risk stays at or under 8%.
    assert float(by.loc["WIDE", "risk_pct"]) <= 8.0
    order = list(setups.BUY_SETUP_ORDER)
    assert order.index("Qullamaggie") == order.index("Flag") + 1
    assert order.index("Marios") == order.index("Qullamaggie") + 1


def test_switches_turn_the_scans_off():
    out = setups.build_setups(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        {"scanner_vcp": False, "scanner_canslim": False, "scanner_box": False, "scanner_flag": False,
         "scanner_leaders": False, "scanner_qullamaggie": False, "scanner_marios": False},
    )
    assert len(out["scanner_qullamaggie"]) == 0 and len(out["scanner_marios"]) == 0


def test_config_has_switches_and_numbers():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["features"]["scanner_qullamaggie"] is True
    assert cfg["features"]["scanner_marios"] is True
    assert cfg["qullamaggie"]["run_min_pct"] == 30
    assert cfg["marios"]["fast_adr_pct"] == 5
