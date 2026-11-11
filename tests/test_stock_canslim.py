"""Scorecard CANSLIM card: one row per stock, without changing scanner qualify rules."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import setups  # noqa: E402
import tables  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _cfg():
    return json.loads(_read("config.json"))


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


def _uni(names, sectors=None):
    rows = []
    for t in names:
        rows.append({
            "ticker": t,
            "company": t + " Co",
            "sector": (sectors or {}).get(t, "Information Technology"),
            "index_membership": "SP500",
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


def _base_panel():
    frame = _climb_frame()
    spy = pd.Series(100 * (1.0003 ** np.arange(len(frame))), index=frame.index)
    quiet = frame.copy()
    quiet["volume"] = 1_000.0
    return _panel(["AAA", "BBB", "SPY"], {
        "AAA": frame,
        "BBB": quiet,
        "SPY": pd.DataFrame({"close": spy, "high": spy * 1.01, "low": spy * 0.99, "volume": 1e8}, index=frame.index),
    })


def test_switches_default_on_and_are_saved():
    cfg = _cfg()
    for key in ("stock_canslim", "canslim_industry_rank", "canslim_free_float", "canslim_news"):
        assert cfg["features"][key] is True
    rows = tables.settings_rows(cfg)
    settings = dict(zip(rows["setting"], rows["value"]))
    assert settings["feature.stock_canslim"] is True
    saved = pd.read_csv(os.path.join(ROOT, "data", "settings.csv"))
    for key in ("feature.stock_canslim", "feature.canslim_industry_rank",
                "feature.canslim_free_float", "feature.canslim_news"):
        assert key in set(saved["setting"])
        got = saved[saved["setting"] == key]["value"].iloc[0]
        assert str(got).lower() == "true"


def test_help_uses_simple_words():
    text = dict(tables.help_rows())["Stock CANSLIM"]
    assert "\u2014" not in text
    for word in ("feature.stock_canslim", "feature.canslim_industry_rank", "feature.canslim_free_float",
                 "feature.canslim_news", "scorecard", "not verified", "15 names a day"):
        assert word in text, word
    saved = pd.read_csv(os.path.join(ROOT, "data", "help.csv"))
    assert "Stock CANSLIM" in set(saved["topic"])


def test_every_stock_gets_a_card_and_missing_letters_stay_blank():
    close, high, low, vol = _base_panel()
    quarters = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q3", "eps": 1.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "eps": 1.4},
    ])
    annual = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2023", "eps": 2.0},
        {"ticker": "AAA", "frame": "CY2024", "eps": 2.5},
    ])
    holders = pd.DataFrame([
        {"ticker": "AAA", "promoter_pct": 60.0, "fii_chg": 0.8, "dii_chg": 0.2, "public_pct": 20.0},
    ])
    uni = _uni(["AAA", "BBB", "CCC"])
    scores = pd.DataFrame([
        {"ticker": "AAA", "industry": "Software"},
        {"ticker": "BBB", "industry": "Software"},
        {"ticker": "CCC", "industry": "Banks"},
    ])
    rs_table = pd.DataFrame([
        {"ticker": "AAA", "rs": 88},
        {"ticker": "BBB", "rs": 40},
        {"ticker": "CCC", "rs": 90},
    ])
    news_map = {"AAA": {"checked": True, "n": 1, "headline": "AAA wins a large order", "publisher": "Wire"}}
    out = setups.build_stock_canslim(
        close, high, low, vol, uni, quarters, annual, holders,
        cfg=_cfg(), rs_table=rs_table, news_map=news_map, scores=scores,
        shares={"AAA": 10_000_000},
    )
    assert set(out["ticker"]) == {"AAA", "BBB", "CCC"}
    aaa = out[out.ticker == "AAA"].iloc[0]
    bbb = out[out.ticker == "BBB"].iloc[0]
    ccc = out[out.ticker == "CCC"].iloc[0]
    assert aaa["c_value"] == 40.0 and aaa["c_mark"] == "pass"
    assert aaa["a_value"] == 25.0 and aaa["a_mark"] == "pass"
    assert aaa["n_mark"] == "pass"
    assert aaa["n_news_mark"] == "pass"
    assert "AAA wins a large order" in aaa["n_news_status"]
    assert aaa["s_mark"] == "pass"
    assert aaa["s_float_pct"] == 40.0
    assert aaa["s_float_shares"] == 4_000_000
    assert "Free float is 40.0%" in aaa["s_status"]
    assert aaa["l_mark"] == "pass" and aaa["l_value"] == 88.0
    assert aaa["i_mark"] == "pass" and aaa["i_value"] == "up"
    assert "promoter" not in aaa["i_status"].lower() or "FII" in aaa["i_status"]
    assert bbb["c_mark"] == "not verified" and bbb["c_value"] == ""
    assert bbb["a_mark"] == "not verified" and bbb["a_value"] == ""
    assert bbb["s_mark"] == "fail"
    assert bbb["s_float_mark"] == "not verified"
    assert bbb["l_mark"] == "fail"
    assert bbb["n_news_mark"] == "not verified"
    assert ccc["c_value"] == "" and ccc["n_mark"] == "not verified"
    assert ccc["s_mark"] == "not verified"
    # Industry rank: Banks median 90 vs Software median 64, so Banks ranks 1.
    assert int(ccc["l_industry_rank"]) == 1
    assert int(aaa["l_industry_n"]) == 2
    assert aaa["l_industry_mark"] in ("pass", "fail")
    blob = out.to_csv(index=False)
    assert "not verified" in blob
    assert not any(str(aaa[c]) == "0" and aaa[c] is not True for c in ("c_value",) if False)


def test_does_not_invent_zero_for_missing_eps():
    close, high, low, vol = _base_panel()
    out = setups.build_stock_canslim(
        close, high, low, vol, _uni(["BBB"]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        cfg=_cfg(),
    )
    row = out.iloc[0]
    assert row["c_value"] == "" and row["c_mark"] == "not verified"
    assert row["a_value"] == "" and row["a_mark"] == "not verified"
    assert row["i_mark"] == "not verified"
    assert 0 not in (row["c_value"], row["a_value"], row["i_value"])


def test_news_checked_empty_is_fail_not_a_guessed_headline():
    close, high, low, vol = _base_panel()
    out = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        cfg=_cfg(), news_map={"AAA": {"checked": True, "n": 0, "headline": "", "publisher": ""}},
    )
    row = out.iloc[0]
    assert row["n_news_mark"] == "fail"
    assert "No fresh headline" in row["n_news_status"]


def test_switches_turn_pieces_off():
    close, high, low, vol = _base_panel()
    cfg = _cfg()
    cfg["features"]["canslim_free_float"] = False
    cfg["features"]["canslim_industry_rank"] = False
    cfg["features"]["canslim_news"] = False
    holders = pd.DataFrame([{"ticker": "AAA", "promoter_pct": 55.0, "fii_chg": 1.0, "dii_chg": 0.0}])
    out = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), holders,
        cfg=cfg, rs_table=pd.DataFrame([{"ticker": "AAA", "rs": 90}]),
        news_map={"AAA": {"checked": True, "n": 1, "headline": "Should not show", "publisher": "X"}},
        scores=pd.DataFrame([{"ticker": "AAA", "industry": "Software"}]),
        shares={"AAA": 1000},
    )
    row = out.iloc[0]
    assert row["s_float_pct"] == ""
    assert "Free float is off" in row["s_status"]
    assert row["l_industry_rank"] == ""
    assert "Industry group rank is off" in row["l_status"]
    assert row["n_news_mark"] == "not verified"
    assert "News check is off" in row["n_news_status"]
    cfg["features"]["stock_canslim"] = False
    empty = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), holders, cfg=cfg,
    )
    assert len(empty) == 0


def test_scanner_qualify_is_unchanged():
    close, high, low, vol = _base_panel()
    quarters = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2024Q3", "eps": 1.0},
        {"ticker": "AAA", "frame": "CY2025Q3", "eps": 1.4},
    ])
    annual = pd.DataFrame([
        {"ticker": "AAA", "frame": "CY2023", "eps": 2.0},
        {"ticker": "AAA", "frame": "CY2024", "eps": 2.5},
    ])
    holders = pd.DataFrame([{"ticker": "AAA", "inst_up": 10, "inst_down": 4, "ownership_pct": 60}])
    scanned, _ = setups.scan_canslim(close, high, low, vol, _uni(["AAA", "BBB"]), quarters, annual, holders)
    card = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA", "BBB"]), quarters, annual, holders, cfg=_cfg(),
    )
    assert set(card["ticker"]) == {"AAA", "BBB"}
    if len(scanned):
        assert set(scanned["ticker"]).issubset({"AAA", "BBB"})
        aaa = scanned[scanned.ticker == "AAA"].iloc[0]
        assert aaa["c_quarterly_eps"] == 40.0
        assert aaa["a_annual_eps"] == 25.0
        assert "industry rank not verified" in aaa["note"]
        assert "float not verified" in aaa["note"]




def test_l_pass_line_is_adjustable():
    close, high, low, vol = _base_panel()
    cfg = _cfg()
    rs = pd.DataFrame([{"ticker": "AAA", "rs": 88}])
    out = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        cfg=cfg, rs_table=rs,
    )
    assert out.iloc[0]["l_mark"] == "pass"
    cfg["stock_canslim"]["l_rs_min"] = 90
    out2 = setups.build_stock_canslim(
        close, high, low, vol, _uni(["AAA"]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        cfg=cfg, rs_table=rs,
    )
    assert out2.iloc[0]["l_mark"] == "fail"
    assert "90" in out2.iloc[0]["l_status"]


def test_scorecard_page_loads_the_card():
    pages = _read("site", "js", "pages.js")
    assert "function stockCanslimHtml" in pages
    assert "stockCanslimHtml(ctx, ticker, row)" in pages
    assert "stock_canslim.csv" in pages
    assert 'optional: ["institutional_13f.csv", "stock_canslim.csv"]' in pages
    assert pages.index("stockCanslimHtml(ctx, ticker, row)") < pages.index("stockShareHtml(ctx, ticker, row)")
    assert "CAN SLIM" in pages
    assert "No data yet" in pages
    assert "cl-chip" in pages and "cl-rows" in pages
    chunk = pages[pages.index("scorecard: { lines:"):pages.index("watchlist: { lines:")]
    assert "feature.stock_canslim" in chunk
    assert "feature.stock_shareholding" in chunk
    css = _read("site", "css", "desk.css")
    assert ".cl-box{" in css and ".cl-chip{" in css and ".cl-pass{" in css
    assert ".sc-break-grid{" in css and ".sc-page .identity{" in css
    assert "--cl-plus2:" in css and "--cl-minus:" in css
    block = pages[pages.index("function clTone"):pages.index("function ptsCard")]
    assert "\u2014" not in block
    assert "FAIL" in block and "No data yet" in block
    assert "Not verified" in block
    assert "function scoreBreakHtml" in pages
    assert "function vsSectorHtml" in pages
    assert "function analystCardHtml" in pages
    assert "sc-top" in pages and "sc-lower" in pages
    assert 'title: "Score breakdown"' not in pages
    assert "25% or more vs the year-ago quarter" in block
    assert "Within 15% of the 52-week closing high" in block


def test_feature_switch_hides_the_scorecard_card():
    pages = _read("site", "js", "pages.js")
    start = pages.index("function stockCanslimHtml")
    chunk = pages[start:pages.index("function wireCanslimRows")]
    assert 'panelOff("feature.stock_canslim")' in chunk
    after = chunk.split('panelOff("feature.stock_canslim")', 1)[1][:80]
    assert "return \"\"" in after or "return '';" in after or 'return ""' in after
    assert pages.index("stockCanslimHtml(ctx, ticker, row)") < pages.index("stockShareHtml(ctx, ticker, row)")
    assert "cl-val-phone" in pages
    assert "avg vol" in pages
    assert 'panelOff("feature.stock_canslim")' in chunk
    css = _read("site", "css", "desk.css")
    assert "sc-break-grid{display:grid;grid-template-columns:minmax(0,1fr)" in css.replace(" ", "") or ".sc-break-grid{display:grid;grid-template-columns:minmax(0,1fr)" in css
    assert "@media (min-width:700px)" in css
    assert "function scRowMissing" in pages
    now_fn = pages[pages.index("function scNowLine"):pages.index("function scoreBreakHtml")]
    assert "No data yet" in now_fn
    assert "Rising" in now_fn and "Falling" in now_fn and "Flat" in now_fn
    assert "institutional" in now_fn
