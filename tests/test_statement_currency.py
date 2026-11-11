"""Convert USD (or other non-INR) Yahoo statements into rupees before scoring."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import fundamentals as fund
import scoring


def _fx_series(rate=88.0, start="2023-10-23", end="2026-11-01"):
    idx = pd.date_range(start, end, freq="B")
    return pd.Series(rate, index=idx)


def _infy_annual():
    # Cached Infosys scale: USD statements, India share count, NSE rupee price.
    rows = [
        ("CY2024", "2024-03-31", "2024-05-15", 1.9267e10, 3.167e9, 0.76, 4.137e9),
        ("CY2025", "2025-03-31", "2025-05-15", 1.9277e10, 3.158e9, 0.76, 4.142e9),
        ("CY2026", "2026-03-31", "2026-05-15", 2.0158e10, 3.313e9, 0.80, 4.046941e9),
    ]
    recs = []
    for frame, end, filed, rev, ni, eps, shares in rows:
        recs.append({
            "ticker": "INFY", "frame": frame, "end": end, "filed": filed,
            "revenue": rev, "net_income": ni, "eps": eps, "shares": shares,
            "gross_profit": rev * 0.30, "op_income": rev * 0.21, "equity": 1.1e10,
            "debt": 7e8, "ocf": 4.1e9, "capex": 3.2e8, "dps": 0.44,
        })
    return pd.DataFrame(recs)


def test_guess_flags_infy_scale_usd_and_leaves_rupee_names():
    fx = 88.0
    assert fund.guess_statement_currency(1153.9, 4.046941e9, 2.0158e10, 0.80, fx) == "USD"
    # TCS-like rupee statements.
    assert fund.guess_statement_currency(2471.1, 3.618e9, 2.670e12, 136.01, fx) == "INR"
    # Expensive small cap: high P/S but P/E still inside the 1-500 guard.
    assert fund.guess_statement_currency(343.0, 1.345e9, 3.51e9, 0.79, fx) == "INR"
    # Tiny BSE name with skinny rupee sales, not a USD filing.
    assert fund.guess_statement_currency(48.65, 7.09e6, 7.7e5, 0.008, fx) == "INR"


def test_yahoo_financial_currency_field_wins():
    annual = _infy_annual()
    close = pd.DataFrame({"INFY": pd.Series([1153.9], index=[pd.Timestamp("2026-11-01")])})
    info = pd.DataFrame([{"ticker": "INFY", "financial_currency": "INR"}])
    decisions = fund.detect_statement_currencies(annual, None, close, info, _fx_series())
    rec = decisions[decisions.ticker == "INFY"].iloc[0]
    assert rec["currency"] == "INR"
    assert not rec["converted"]
    info_usd = pd.DataFrame([{"ticker": "INFY", "financial_currency": "USD"}])
    rec2 = fund.detect_statement_currencies(annual, None, close, info_usd, _fx_series()).iloc[0]
    assert rec2["currency"] == "USD" and rec2["converted"] and rec2["source"] == "field"


def test_period_rate_uses_history_then_edges():
    idx = pd.to_datetime(["2024-01-02", "2024-06-03", "2025-01-02"])
    fx = pd.Series([83.0, 85.0, 90.0], index=idx)
    assert fund.usd_inr_on(fx, "2024-06-03") == 85.0
    assert fund.usd_inr_on(fx, "2024-06-10") == 85.0
    assert fund.usd_inr_on(fx, "2023-01-01") == 83.0  # before first bar
    assert fund.usd_inr_on(fx, "2026-11-01") == 90.0  # after last bar
    assert fund.usd_inr_on(None, "2024-06-03") == fund.FALLBACK_USD_INR


def test_convert_scales_money_and_eps_not_shares():
    annual = _infy_annual()
    close = pd.DataFrame({"INFY": pd.Series([1153.9], index=[pd.Timestamp("2026-11-01")])})
    fx = _fx_series(83.0)
    out, _, dec = fund.align_statements_to_inr(annual, None, close, None, fx)
    assert dec.iloc[0]["converted"]
    row = out[out.frame == "CY2026"].iloc[0]
    raw = annual[annual.frame == "CY2026"].iloc[0]
    assert abs(row["revenue"] / raw["revenue"] - 83.0) < 1e-6
    assert abs(row["eps"] / raw["eps"] - 83.0) < 1e-6
    assert abs(row["net_income"] / raw["net_income"] - 83.0) < 1e-6
    assert row["shares"] == raw["shares"]


def test_infy_like_price_to_sales_lands_between_2_and_4():
    annual = _infy_annual()
    closes = pd.Series(1153.9, index=pd.date_range("2024-05-16", "2026-11-01", freq="B"))
    close = pd.DataFrame({"INFY": closes})
    fx = _fx_series(83.0)
    converted, _, _ = fund.align_statements_to_inr(annual, None, close, None, fx)
    prep = fund.prepare_annual(converted, closes)
    metrics = fund.metrics_asof(prep, "2026-11-01", 1153.9)
    assert metrics["ps"] is not None
    assert 2.0 <= metrics["ps"] <= 4.0
    assert metrics["ttm_pe"] is not None
    assert 10.0 <= metrics["ttm_pe"] <= 25.0
    raw_prep = fund.prepare_annual(annual, closes)
    raw = fund.metrics_asof(raw_prep, "2026-11-01", 1153.9)
    assert raw["ps"] is None  # 230+ is outside the sane P/S cap
    assert raw["ttm_pe"] is None  # 1442 is outside the P/E guard


def test_growth_stays_similar_when_both_years_are_converted():
    annual = _infy_annual()
    close = pd.DataFrame({"INFY": pd.Series([1153.9], index=[pd.Timestamp("2026-11-01")])})
    fx = _fx_series(83.0)
    converted, _, _ = fund.align_statements_to_inr(annual, None, close, None, fx)
    raw_g = annual.set_index("frame")["revenue"].pct_change()
    new_g = converted.set_index("frame")["revenue"].pct_change()
    # Same FX every year, so growth matches exactly.
    assert abs(float(raw_g.loc["CY2026"]) - float(new_g.loc["CY2026"])) < 1e-12
    # A moving INR=X series still uses one rate per name, so growth stays put.
    moving = pd.Series(
        [83.0, 90.0, 95.0],
        index=pd.to_datetime(["2024-03-31", "2025-03-31", "2026-06-30"]),
    )
    converted2, _, _ = fund.align_statements_to_inr(annual, None, close, None, moving)
    new_g2 = converted2.set_index("frame")["revenue"].pct_change()
    assert abs(float(raw_g.loc["CY2026"]) - float(new_g2.loc["CY2026"])) < 1e-12


def test_blank_or_out_of_range_financials_add_zero_to_the_score():
    cfg = {
        "flat_band_pct": 0.05, "buy_at": 8, "hold_at": 4, "downgrade_extended_below": 9,
        "min_fin_for_buy": 5, "stop_atr_mult": 2.0, "target_rr": 2.5,
        "analyst_strong_at": 1.8, "analyst_buy_at": 2.5, "analyst_sell_at": 3.8,
        "analyst_strong_sell_at": 4.5, "min_analysts_for_strong": 5,
    }
    base = {
        "ttm_pe": 8, "ttm_pe_avg": 12, "ps": 2.8, "ps_avg": 3.5,
        "de": 0.1, "de_avg": 0.1, "pfcf": 15, "pfcf_avg": 20,
        "rev_growth": 0.05, "rev_growth_avg": 0.04, "eps_growth": 0.05,
        "eps_growth_avg": 0.04, "roe": 0.3, "roe_avg": 0.28,
        "div_yield": 0.02, "div_yield_avg": 0.02,
    }
    mkt = {"price": 40, "sma20": 38, "sma50": 35, "sma100": 30, "sma200": 28,
           "rsi": 55, "rsi_prev": 50, "atr": 1.0, "high252": 42}
    extra = {"forward_pe": None, "analyst_mean": None, "analyst_n": None,
             "target_median": None, "target_mean": None,
             "inst_up": None, "inst_down": None, "insider_buys": None, "insider_sells": None,
             "eps_flag": None, "rev_flag": None, "sector_excess": None}
    full = scoring.score_components(base, mkt, extra, cfg)
    missing = dict(base)
    missing["ps"] = None
    missing["ps_avg"] = None
    missing["pfcf"] = None
    missing["pfcf_avg"] = None
    blanked = scoring.score_components(missing, mkt, extra, cfg)
    assert blanked["pts_ps"] is None and blanked["pts_pfcf"] is None
    # Same contribution as scoring those rows 0: the rest of Financials still adds up.
    assert blanked["pts_fin"] == scoring.nansum_strict(
        [full["pts_ttm_pe"], full["pts_de"], full["pts_rev_growth"],
         full["pts_eps_growth"], full["pts_roe"], full["pts_div_yield"], 0, 0])
    assert scoring.nansum_strict([1, None, -1]) == scoring.nansum_strict([1, 0, -1])
