"""VCP list rule: a stock is listed only with the 8 of 8 trend template (the green VCP tag)."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setups  # noqa: E402
from test_setups import _vcp_tape  # noqa: E402

WEAK = setups.WEAK_TREND_STATUS


def _state(**kw):
    base = {
        "score": 8, "rules": [True] * 8, "cnt": 2, "depths": [8.0, 4.0], "highs": [100.0, 99.0],
        "pivot": 99.0, "is_vcp": True, "breakout": False, "big_vol": False, "in_trade": False,
        "entry": None, "entry_bar": -1, "entry_score": -1, "stop": None, "be_done": False,
        "part_done": False, "climax_done": False, "trail": 95.0, "close": 98.0, "bars": 300,
        "high52": 100.0,
    }
    base.update(kw)
    if "score" in kw and "rules" not in kw:
        base["rules"] = [i < kw["score"] for i in range(8)]
    if "is_vcp" not in kw:
        base["is_vcp"] = base["cnt"] >= 2 and base["score"] == 8
    return base


def test_config_switch_defaults_off():
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    assert cfg["vcp"]["show_weaker_trend"] is False
    assert setups._vcp_cfg(cfg)["show_weaker_trend"] is False
    assert setups._vcp_cfg(None)["show_weaker_trend"] is False
    assert setups._vcp_cfg({"vcp": {"show_weaker_trend": True}})["show_weaker_trend"] is True


def test_ready_and_watching_need_eight_of_eight():
    assert setups._vcp_status(_state()) == "READY"
    assert setups._vcp_status(_state(close=101.0)) == "WATCHING"  # over the line on low volume
    assert setups._vcp_status(_state(cnt=1, depths=[6.0], is_vcp=False)) == "WATCHING"  # one pullback
    for score in range(8):
        assert setups._vcp_status(_state(score=score)) is None, score
        assert setups._vcp_status(_state(score=score, close=101.0)) is None, score
        assert setups._vcp_status(_state(score=score, cnt=1, depths=[6.0])) is None, score


def test_switch_brings_back_weaker_rows_with_a_clear_label():
    assert setups._vcp_status(_state(score=0), True) == WEAK
    assert setups._vcp_status(_state(score=7, close=101.0), True) == WEAK
    assert setups._vcp_status(_state(score=6, cnt=1, depths=[6.0]), True) == WEAK
    assert setups._vcp_status(_state(score=5, cnt=1, depths=[6.0]), True) is None
    # 8 of 8 rows keep their normal labels with the switch on.
    assert setups._vcp_status(_state(), True) == "READY"


def test_open_trade_stays_only_if_the_buy_was_eight_of_eight():
    trade = dict(in_trade=True, entry=99.5, entry_bar=290, stop=92.5)
    assert setups._vcp_status(_state(score=3, entry_score=8, **trade)) == "WATCHING"
    assert setups._vcp_status(_state(score=7, entry_score=7, **trade)) is None
    assert setups._vcp_status(_state(score=7, entry_score=7, **trade), True) == WEAK
    reason = setups._vcp_reason(_state(score=3, entry_score=8, **trade), "WATCHING", None)
    assert "was 8 of 8 on the buy day" in reason and "\u2014" not in reason


def test_breakout_records_the_trend_score_on_the_buy_day():
    frame, spy, _p2 = _vcp_tape(True)
    state = setups.vcp_last(frame["high"], frame["low"], frame["close"], frame["volume"], spy.to_numpy())
    assert state["breakout"] and state["entry_score"] == 8


def _panel(frame, spy):
    close = pd.DataFrame({"AAA": frame["close"], "SPY": spy})
    high = pd.DataFrame({"AAA": frame["high"], "SPY": spy * 1.002})
    low = pd.DataFrame({"AAA": frame["low"], "SPY": spy * 0.998})
    vol = pd.DataFrame({"AAA": frame["volume"], "SPY": 1e8})
    uni = pd.DataFrame([{"ticker": "AAA", "company": "AAA Co", "sector": "IT", "index_membership": "Other"}])
    return close, high, low, vol, uni


def test_scan_drops_a_weak_trend_unless_the_switch_is_on():
    frame, _spy, _p2 = _vcp_tape(False)
    n = len(frame)
    # A benchmark that rises much faster fails rule 8, so the trend is 7 of 8.
    fast = pd.Series(100 * (1.01 ** np.arange(n)), index=frame.index)
    close, high, low, vol, uni = _panel(frame, fast)
    assert len(setups.scan_vcp(close, high, low, vol, uni, {})) == 0
    out = setups.scan_vcp(close, high, low, vol, uni, {"vcp": {"show_weaker_trend": True}})
    assert list(out["status"]) == [WEAK]
    assert list(out["trend_score"]) == ["7 of 8"]
    # With a normal benchmark the same chart is 8 of 8 and READY.
    slow = pd.Series(100 * (1.0004 ** np.arange(n)), index=frame.index)
    close, high, low, vol, uni = _panel(frame, slow)
    out = setups.scan_vcp(close, high, low, vol, uni, {})
    assert list(out["status"]) == ["READY"] and list(out["trend_score"]) == ["8 of 8"]


def test_help_text_is_plain():
    js = open(os.path.join(ROOT, "site", "js", "pages.js"), encoding="utf-8").read()
    assert "vcp.show_weaker_trend" in js and "WATCHING (trend not 8/8)" in js
    src = open(os.path.join(ROOT, "tables.py"), encoding="utf-8").read()
    line = [ln for ln in src.splitlines() if '("VCP scanner",' in ln][0]
    assert "8 trend rules pass" in line and "vcp.show_weaker_trend" in line and "\u2014" not in line
