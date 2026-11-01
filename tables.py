"""Turn scored rows into one CSV per Looker page.

Pages are pre-aggregated here so Looker only filters and draws.
Missing numbers stay blank. A feed that cannot be built is one MISSING row with a note.
"""
import numpy as np
import pandas as pd
import fundamentals as fund
from scoring import FIN_SPECS, grade_earnings, headline_tone, beat_flag

DISCLAIMER = "Research only. Not a recommendation to buy or sell. This desk never places trades. Stocks only, no option contracts."

# How a macro surprise maps onto each sector ETF. +1 means a "good" surprise helps that ETF.
# The third bucket is still called Jobs in the file so the columns stay stable.
# On this desk that bucket is the rate backdrop, not a jobs report.
MACRO_WEIGHT = {
    "^CNXIT": {"Growth": 1, "Inflation": -1, "Jobs": -1},
    "^CNXPHARMA": {"Growth": 0, "Inflation": -1, "Jobs": 0},
    "^CNXFIN": {"Growth": 1, "Inflation": 1, "Jobs": 1},
    "^NSEBANK": {"Growth": 1, "Inflation": 1, "Jobs": 1},
    "^CNXPSUBANK": {"Growth": 1, "Inflation": 1, "Jobs": 1},
    "^CNXINFRA": {"Growth": 1, "Inflation": 0, "Jobs": -1},
    "^CNXMEDIA": {"Growth": 1, "Inflation": -1, "Jobs": 0},
    "^CNXAUTO": {"Growth": 1, "Inflation": -1, "Jobs": -1},
    "^CNXCONSUM": {"Growth": 1, "Inflation": -1, "Jobs": -1},
    "^CNXFMCG": {"Growth": -1, "Inflation": 0, "Jobs": 0},
    "^CNXENERGY": {"Growth": 0, "Inflation": 1, "Jobs": 0},
    "^CNXREALTY": {"Growth": 1, "Inflation": -1, "Jobs": -1},
    "^CNXMETAL": {"Growth": 1, "Inflation": 1, "Jobs": 0},
    "XLK": {"Growth": 1, "Inflation": -1, "Jobs": 0},
    "XLY": {"Growth": 1, "Inflation": -1, "Jobs": 1},
    "XLP": {"Growth": -1, "Inflation": 0, "Jobs": 0},
}

INDUSTRY_ETF = (
    ("bank", "^NSEBANK"),
    ("psu", "^CNXPSUBANK"),
    ("media", "^CNXMEDIA"),
    ("oil", "^CNXENERGY"),
    ("realty", "^CNXREALTY"),
    ("real estate", "^CNXREALTY"),
    ("metal", "^CNXMETAL"),
    ("auto", "^CNXAUTO"),
    ("pharma", "^CNXPHARMA"),
    ("software", "^CNXIT"),
    ("it ", "^CNXIT"),
)


def blank_row(columns, status, note):
    row = {c: "" for c in columns}
    row["data_status"] = status
    row["note"] = note
    if "disclaimer" in columns:
        row["disclaimer"] = DISCLAIMER
    return row


def _cell_blank(v):
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (ValueError, TypeError):
        pass
    if isinstance(v, str) and v.strip().lower() in ("", "nan", "none", "<na>"):
        return True
    return False


def flag_blank_columns(df):
    """OK is wrong when a measured column is blank on every row.

    A one-row MISSING placeholder stays MISSING. An alerts info row is a
    message, not a broken feed. note and disclaimer may be empty.
    """
    if df is None or len(df) == 0 or "data_status" not in df.columns:
        return df
    status = df["data_status"].astype(str)
    if len(df) == 1 and status.iloc[0] == "MISSING":
        return df
    if "kind" in df.columns and len(df) == 1 and str(df.iloc[0].get("kind") or "") == "info":
        return df
    measured = [c for c in df.columns if c not in ("note", "disclaimer", "data_status")]
    blanks = [c for c in measured if df[c].map(_cell_blank).all()]
    if not blanks:
        return df
    out = df.copy()
    all_blank = len(blanks) == len(measured)
    new_status = "MISSING" if all_blank else "PARTIAL"
    def _next(s):
        if s in ("MISSING", "CACHED"):
            return s
        return new_status
    out["data_status"] = status.map(_next)
    extra = "Blank on every row: " + ", ".join(blanks) + ". A blank is missing data, not zero."
    notes = out["note"].map(lambda v: "" if _cell_blank(v) else str(v).strip())
    out["note"] = np.where(notes.eq(""), extra, notes + " " + extra)
    return out


def ensure(df, columns, status_if_empty, note):
    if df is None or len(df) == 0:
        return pd.DataFrame([blank_row(columns, status_if_empty, note)])
    out = df.copy()
    for c in columns:
        if c not in out.columns:
            out[c] = ""
    if "disclaimer" in columns:
        out["disclaimer"] = DISCLAIMER
    if "data_status" in columns and (out["data_status"].eq("").all() or out["data_status"].isna().all()):
        out["data_status"] = "OK"
    out = out[columns]
    out = flag_blank_columns(out)
    return out


def _off(columns):
    return pd.DataFrame(columns=columns)


# Column orders are the Looker headers. Do not rename them after the Sheet is connected.
COLS = {}

COLS["scores"] = [
    "rank", "ticker", "company", "sector", "industry", "index_membership", "universe", "price", "day_pct", "price_as_of",
    "score", "confidence", "verdict", "reason",
    "pts_tech", "pts_fin", "pts_sent", "pts_earnings", "pts_sector",
    "pts_trend", "pts_oscillator",
    "pts_forward_pe", "pts_ttm_pe", "pts_ps", "pts_de", "pts_pfcf",
    "pts_rev_growth", "pts_eps_growth", "pts_roe", "pts_div_yield",
    "pts_analyst", "pts_institutional", "pts_insider",
    "forward_pe", "forward_pe_avg", "ttm_pe", "ttm_pe_avg", "ps", "ps_avg", "de", "de_avg",
    "pfcf", "pfcf_avg", "rev_growth", "rev_growth_avg", "eps_growth", "eps_growth_avg",
    "roe", "roe_avg", "div_yield", "div_yield_avg", "forward_pe_avg_basis", "fin_avg_years", "fundamentals_basis", "fundamentals_filed",
    "ind_forward_pe", "pts_forward_pe_ind", "ind_ttm_pe", "pts_ttm_pe_ind", "ind_ps", "pts_ps_ind",
    "ind_de", "pts_de_ind", "ind_pfcf", "pts_pfcf_ind", "ind_rev_growth", "pts_rev_growth_ind",
    "ind_eps_growth", "pts_eps_growth_ind", "ind_roe", "pts_roe_ind", "ind_div_yield", "pts_div_yield_ind",
    "analyst_mean", "analyst_count", "target_analyst", "target_analyst_kind", "target_pfcf", "target_peg", "target_blended", "target_blend_n",
    "entry_low", "entry_high", "stop", "trade_target", "reward_risk",
    "timing", "sma_alignment", "rsi14", "rs_spy_3m", "rs_benchmark", "dist_52w_high_pct", "volume_ratio",
    "above_sma20", "above_sma50", "above_sma100", "above_sma200",
    "next_earnings", "missing_fields", "missing_count",
    "price_status", "fundamentals_status", "analyst_status", "holders_status",
    "exchange", "nse_symbol", "bse_symbol", "liquid", "median_traded_value",
    "fii_pct", "dii_pct", "fii_chg", "dii_chg",
    "data_status", "note", "disclaimer",
]

# Breakdown columns the scorecard table uses. Status and the disclaimer are not repeated on every row.
COLS["score_details"] = ["ticker", "group_name", "item", "points", "points_label", "now_value", "avg_value", "vs_industry"]
COLS["market_today"] = [
    "spy_price", "spy_day_pct", "qqq_day_pct", "sensex_price", "sensex_day_pct", "bank_price",
    "nifty_trend", "sensex_trend", "bank_trend", "market_ok", "market_rule", "buy_count",
    "breadth_sma20", "breadth_sma50", "breadth_sma100", "breadth_sma200",
    "breadth_sma50_week_ago", "advancers", "decliners", "universe_n", "highs_52w", "lows_52w",
    "put_call", "put_call_ma5", "put_call_zone", "put_call_name", "vix",
    "fred_dgs10", "fred_t10y2y", "inr_usd", "xly_xlp", "updated_pt", "price_as_of",
    "listed_n", "liquid_n",
    "data_status", "note", "disclaimer",
]
COLS["sectors"] = ["ticker", "name", "group_name", "day_pct", "week_pct", "month_pct", "month3_pct", "ytd_pct", "rs_3m_pct", "score_avg", "n_stocks", "pct_above_sma50", "macro_growth", "macro_inflation", "macro_jobs", "macro_score", "data_status", "note", "disclaimer"]
COLS["breadth_history"] = ["date", "pct_above_sma20", "pct_above_sma50", "pct_above_sma100", "pct_above_sma200", "data_status", "note", "disclaimer"]
COLS["alerts"] = ["ticker", "kind", "text", "score", "score_prev", "verdict", "verdict_prev", "price", "data_status", "note", "disclaimer"]
COLS["score_changes"] = ["ticker", "company", "price", "day_pct", "score", "score_prev", "score_change", "verdict", "data_status", "note", "disclaimer"]
COLS["portfolio"] = ["ticker", "company", "shares", "avg_cost", "price", "day_pct", "value", "cost", "gain", "gain_pct", "weight_pct", "score", "score_week_ago", "score_week_change", "verdict", "stop", "status", "example", "data_status", "note", "disclaimer"]
COLS["portfolio_summary"] = ["value", "day_pnl", "day_pnl_pct", "total_gain", "total_gain_pct", "avg_score", "needs_attention", "n_holdings", "example_warning", "data_status", "note", "disclaimer"]
COLS["watchlist"] = ["ticker", "company", "price", "day_pct", "score", "verdict", "entry_low", "entry_high", "distance_to_entry_pct", "timing", "note_input", "data_status", "note", "disclaimer"]
# Chart columns only. Full daily history stays in cache/ohlcv.csv.gz, not in this file.
COLS["prices"] = ["date", "ticker", "close", "sma20", "sma50", "entry_low", "entry_high", "stop", "trade_target"]
COLS["news"] = ["ticker", "kind", "headline", "summary", "publisher", "link", "published", "data_status", "note", "disclaimer"]
COLS["scanner_growth"] = ["ticker", "company", "sector", "price", "score", "verdict", "rev_growth", "eps_growth", "rs_spy_3m", "passes", "why", "data_status", "note", "disclaimer"]
COLS["scanner_quality"] = ["ticker", "company", "sector", "price", "score", "verdict", "roe", "de", "pts_roe", "pts_de", "passes", "why", "data_status", "note", "disclaimer"]
COLS["scanner_dividend"] = ["ticker", "company", "sector", "price", "score", "verdict", "div_yield", "div_yield_avg", "pts_div_yield", "passes", "why", "data_status", "note", "disclaimer"]
COLS["scanner_wheel"] = ["ticker", "company", "sector", "price", "score", "verdict", "timing", "rsi14", "above_sma200", "dollar_volume", "passes", "why", "data_status", "note", "disclaimer"]
_SETUP = ["ticker", "company", "sector", "index_membership", "status", "pivot", "stop", "target", "strength", "reason", "freshness", "price", "price_as_of"]
COLS["scanner_vcp"] = _SETUP + [
    "trail", "trend_score", "contractions", "depths", "volume_ok", "in_trade", "stop_basis",
    "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8",
    "data_status", "note", "disclaimer",
]
COLS["scanner_canslim"] = _SETUP + [
    "c_quarterly_eps", "c_status", "a_annual_eps", "a_status",
    "n_pct_from_high", "n_status", "s_adv", "s_status",
    "l_rs_percentile", "l_status", "i_trend", "i_status",
    "m_market", "m_spy", "m_sensex", "m_qqq", "m_status", "qualify", "vcp_heuristic",
    "data_status", "note", "disclaimer",
]
COLS["scanner_box"] = _SETUP + ["range_days", "range_width_pct", "volume_ratio", "data_status", "note", "disclaimer"]
COLS["scanner_flag"] = _SETUP + ["pole_pct", "flag_bars", "retrace_pct", "volume_ratio", "data_status", "note", "disclaimer"]
# Qullamaggie and Marios share the entry, base, and context columns. Qullamaggie has no fixed target.
_QM_COMMON = [
    "entry", "stop_basis", "stop_check", "stop_adr", "risk_pct", "shares", "position_value", "position_pct",
    "adr_pct", "adr_now", "adr_tag", "leader_top_pct", "leader_pct", "leader_window",
    "run_pct", "run_days", "base_days", "base_range_pct", "higher_lows", "sma20_share", "dry_up",
    "confirmed_close", "volume_ratio", "volume_flag",
    "breakout_date", "days_in_trade", "trade_stop", "entry_stop", "exit_reason", "exit_date", "exit_price",
    "market_light", "next_earnings", "earnings_soon", "traded_value_cr", "price_band",
]
COLS["scanner_qullamaggie"] = [c for c in _SETUP if c != "target"] + _QM_COMMON + [
    "partial_flag", "trail_with", "trail", "trail_signal",
    "data_status", "note", "disclaimer",
]
COLS["scanner_marios"] = _SETUP + _QM_COMMON + [
    "weak_close", "target_low", "target_high", "partial_hit", "partial_date",
    "trail10", "trail20", "trail_signal", "sold_third_date",
    "data_status", "note", "disclaimer",
]
# Episodic Pivot: one row per stock. pivot is the buy level (EP-day high, or a tight range high for a delayed EP).
COLS["scanner_episodic_pivot"] = [c for c in _SETUP if c != "target"] + [
    "ep_date", "days_since_ep", "ep_trigger", "catalyst_tag", "report_timing",
    "gap_pct", "change_pct", "volume", "avg_volume_50", "rvol", "dcr_pct", "closed_above_open", "first_ep_6m",
    "ret_63d_prior", "ret_126d_prior", "rs_63d_vs_nifty", "nifty_trend", "base_range_pct", "neglect_grade",
    "eps_actual", "eps_estimate", "surprise_pct", "eps_yoy_last_filed", "rev_yoy_last_filed", "rev_accel", "last_quarter_end",
    "analyst_count", "few_analysts", "catalyst_score", "manual_check",
    "shares", "market_cap_cr", "mcap_source", "small_young", "avg_volume_30",
    "adr_pct", "adr_now", "ep_high", "ep_low", "entry", "entry_basis", "stop_basis", "risk_pct", "risk_vs_adr", "stop_check",
    "circuit_flag", "partial_window", "trail_with", "trail", "signal",
    "entry_date", "days_in_trade", "exit_date", "exit_price", "exit_reason", "result_pct", "news_link",
    "data_status", "note", "disclaimer",
]
# Gap Up: one row per stock, the most recent true gap that still holds. hold_level is the gap-day low.
COLS["scanner_gap_up"] = [
    "rank", "ticker", "company", "sector", "index_membership", "status", "gap_date", "days_ago", "gap_pct", "avg_traded_cr",
    "prev_high", "prev_close", "gap_open", "gap_high", "gap_low", "gap_close", "volume", "avg_volume_50", "volume_ratio",
    "hold_level", "price", "price_as_of", "above_hold_pct", "close_pos_pct", "sma50", "sma200", "above_sma50", "above_sma200",
    "also_in", "reason", "data_status", "note", "disclaimer",
]
COLS["scanner_leaders"] = _SETUP + [
    "vcp_status", "canslim_status", "vcp_strength", "canslim_strength", "on_vcp", "on_canslim",
    "data_status", "note", "disclaimer",
]
# high_52w and low_52w are the high and low. new_high_today and new_low_today use the close.
COLS["scanner_52w"] = [
    "ticker", "company", "sector", "index_membership", "price", "price_as_of",
    "high_52w", "low_52w", "pct_from_high", "pct_above_low", "range_position_pct",
    "new_high_today", "new_low_today", "near_high", "high_on_volume", "volume_ratio",
    "days_since_high", "score", "verdict", "data_status", "note", "disclaimer",
]
COLS["highs_lows_history"] = [
    "date", "new_highs", "new_lows", "near_high_count", "net", "data_status", "note", "disclaimer",
]
COLS["buy_setups"] = [
    "ticker", "company", "sector", "index_membership", "price", "price_as_of",
    "setup_sources", "sources_count", "best_status", "entry", "stop", "target1", "target2",
    "risk_pct", "reward_risk", "dist_to_entry_pct", "score", "verdict",
    "range_position_52w", "pct_from_high_52w", "reason", "market_ok", "spy_uptrend", "qqq_uptrend",
    "sensex_uptrend", "nifty_trend", "sensex_trend", "bank_trend", "market_rule", "financials_pending", "listed", "rs_benchmark",
    "data_status", "note", "disclaimer",
]
COLS["sector_rotation"] = [
    "ticker", "name", "benchmark", "sector", "score", "rank",
    "quadrant_d", "quadrant_w", "quadrant_m",
    "rs_ratio_w", "rs_momentum_w",
    "rs_1m", "rs_3m", "rs_6m",
    "breadth_sma50", "breadth_sma200", "n_stocks",
    "near_high_count", "near_high_share",
    "buy_setup_count", "buy_setup_share",
    "score_avg", "buy_share", "rrg_points",
    "change_daily", "change_weekly",
    "dgs10_last", "dgs10_prev", "dgs10_trend",
    "t10y2y_last", "t10y2y_prev", "t10y2y_trend",
    "reason", "data_status", "note", "disclaimer",
]
COLS["sector_rotation_tails"] = [
    "timeframe", "ticker", "name", "benchmark", "date", "rs_ratio", "rs_momentum", "quadrant", "tail_index",
    "data_status", "note", "disclaimer",
]
COLS["sector_rotation_history"] = [
    "date", "timeframe", "ticker", "name", "benchmark", "rs_ratio", "rs_momentum", "quadrant",
    "data_status", "note", "disclaimer",
]
COLS["backfill_progress"] = [
    "kind", "covered", "total", "pct", "last_batch_at", "last_ok", "last_fail",
    "next_name", "cycle_note", "data_status", "note", "disclaimer",
]
COLS["earnings_calendar"] = ["ticker", "company", "next_earnings", "when_hint", "days_away", "last_eps_actual", "last_eps_estimate", "last_surprise_pct", "last_1d_move_pct", "avg_1d_move_pct", "n_past", "owns", "data_status", "note", "disclaimer"]
COLS["earnings_heatmap"] = ["ticker", "quarter", "eps_flag", "rev_flag", "label", "heat", "data_status", "note", "disclaimer"]
COLS["earnings_cards"] = ["ticker", "company", "grade", "summary", "sources", "data_status", "note", "disclaimer"]
COLS["earnings_history"] = ["ticker", "earnings_date", "eps_estimate", "eps_actual", "surprise_pct", "move_1d_pct", "data_status", "note", "disclaimer"]
COLS["put_call"] = ["date", "name", "value", "ma5", "fear_line", "greed_line", "zone", "data_status", "note", "disclaimer"]
COLS["option_walls"] = ["ticker", "expiry", "side", "strike", "open_interest", "volume", "is_wall", "nearest_expiry", "data_status", "note", "disclaimer"]
COLS["analyst_ratings"] = ["ticker", "company", "analyst_mean", "analyst_count", "pts_analyst", "target_analyst", "target_analyst_kind", "price", "upside_pct", "data_status", "note", "disclaimer"]
COLS["institutional_13f"] = [
    "ticker", "row_type", "owner", "promoter_pct", "fii_pct", "dii_pct", "public_pct",
    "promoter_chg", "fii_chg", "dii_chg", "public_chg", "as_of", "pts_institutional",
    "data_status", "note", "disclaimer",
]
COLS["aaii_sentiment"] = ["as_of", "india_vix", "vix_zone", "fii_net_cr", "dii_net_cr", "data_status", "note", "disclaimer"]
COLS["insider_trading"] = ["ticker", "buys_3m", "sells_3m", "pts_insider", "data_status", "note", "disclaimer"]
COLS["headline_sentiment"] = ["ticker", "headline", "publisher", "link", "published", "tone", "tone_note", "data_status", "note", "disclaimer"]
COLS["xly_xlp"] = ["date", "xly", "xlp", "ratio", "ratio_sma50", "zone", "data_status", "note", "disclaimer"]
COLS["financials_summary"] = ["ticker", "sector", "metric", "direction", "now_value", "avg_3y", "pts_vs_self", "industry_median", "pts_vs_industry", "data_status", "note", "disclaimer"]
COLS["earnings_tracker"] = ["ticker", "earnings_date", "eps_estimate", "eps_actual", "surprise_pct", "result", "data_status", "note", "disclaimer"]
COLS["company_financials"] = ["ticker", "fy_end", "filed", "revenue", "gross_profit", "op_income", "net_income", "eps", "gross_margin", "operating_margin", "net_margin", "fcf", "pe", "ps", "pfcf", "data_status", "note", "disclaimer"]
COLS["dividend_scanner"] = ["ticker", "company", "sector", "price", "div_yield", "div_yield_avg", "dps", "pts_div_yield", "verdict", "data_status", "note", "disclaimer"]
COLS["macro_screener"] = ["country", "category", "indicator", "date", "actual", "forecast", "surprise", "signal", "source", "data_status", "note", "disclaimer"]
COLS["sector_macro"] = ["ticker", "name", "macro_growth", "macro_inflation", "macro_jobs", "macro_score", "plain_english", "data_status", "note", "disclaimer"]
COLS["historical_pe"] = ["date", "desk_median_trailing_pe", "n", "official_sp500_pe", "official_status", "data_status", "note", "disclaimer"]
COLS["breakouts"] = ["ticker", "company", "sector", "price", "dist_52w_high_pct", "volume_ratio", "score", "verdict", "data_status", "note", "disclaimer"]
COLS["trends"] = ["ticker", "company", "sector", "price", "trend_label", "sma_alignment", "above_sma20", "above_sma50", "above_sma100", "above_sma200", "score", "data_status", "note", "disclaimer"]
COLS["pullbacks"] = ["ticker", "company", "sector", "price", "rsi14", "entry_low", "entry_high", "score", "verdict", "passes", "why", "data_status", "note", "disclaimer"]
COLS["high_volume"] = ["rank", "ticker", "company", "description", "sector", "exchange", "date", "volume", "avg_volume_50d", "volume_ratio", "day_pct", "close", "prev_close", "traded_cr", "sma50", "sma200", "above_sma50", "above_sma200", "day_type", "meaning", "delivery_pct", "split_check", "passes_default", "data_status", "note", "disclaimer"]
COLS["gainers_losers"] = ["side", "ticker", "company", "sector", "price", "day_pct", "score", "verdict", "data_status", "note", "disclaimer"]
COLS["sector_performance"] = ["sector", "day_pct", "week_pct", "month_pct", "month3_pct", "ytd_pct", "pct_above_sma50", "score_avg", "n", "data_status", "note", "disclaimer"]
COLS["heatmaps"] = ["ticker", "company", "sector", "ret_1d", "ret_1w", "ret_1m", "ret_ytd", "above_sma20", "above_sma50", "above_sma100", "above_sma200", "data_status", "note", "disclaimer"]
COLS["freshness"] = ["field", "n_missing", "n_present", "data_status", "note", "disclaimer"]
COLS["updates_log"] = ["source", "status", "latest", "note", "checked_pt"]
COLS["help"] = ["topic", "plain_english"]
COLS["settings"] = ["setting", "value"]
COLS["universe"] = ["ticker", "company", "sector", "index_membership", "exchange", "nse_symbol", "bse_symbol", "isin", "in_nifty50", "in_next50", "in_midcap150", "in_smallcap250", "in_microcap250", "in_totalmarket", "in_other_nse", "in_sme", "in_bse_only", "in_my_picks", "data_status", "note", "disclaimer"]
COLS["fii_flows"] = ["date", "fii_buy", "fii_sell", "fii_net", "dii_buy", "dii_sell", "dii_net", "nifty", "sensex", "source", "data_status", "note", "disclaimer"]
COLS["participant_oi"] = ["date", "participant", "index_fut_long", "index_fut_short", "index_fut_net", "source", "data_status", "note", "disclaimer"]
COLS["backtest_summary"] = ["window", "start", "end", "months", "top20_cagr_pct", "spy_cagr_pct", "bottom20_cagr_pct", "top20_total_pct", "spy_total_pct", "bottom20_total_pct", "top20_max_drawdown_pct", "spy_max_drawdown_pct", "hit_rate_12w_pct", "top_bucket_excess_12w_pct", "headline", "is_headline", "data_status", "note", "disclaimer"]
COLS["backtest_buckets"] = ["horizon", "bucket", "bucket_order", "n", "avg_return_pct", "avg_spy_pct", "excess_pct", "hit_rate_pct", "data_status", "note", "disclaimer"]
COLS["backtest_equity"] = ["date", "top20", "spy", "bottom20", "data_status", "note", "disclaimer"]
COLS["backtest_yearly"] = ["year", "top20_pct", "spy_pct", "difference_pct", "hit_rate_12w_pct", "signals", "data_status", "note", "disclaimer"]
COLS["backtest_notes"] = ["item", "detail", "data_status", "note", "disclaimer"]


def _date_cell(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ""
    try:
        if pd.isna(v):
            return ""
    except (ValueError, TypeError):
        return ""
    try:
        return str(pd.Timestamp(v).date())
    except Exception:
        return str(v)


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(x):
        return None
    return x


def _yn(flag):
    return 1 if flag else 0


def missing_fields(row):
    fields = []
    for key, _ in FIN_SPECS:
        if _num(row.get(key)) is None or _num(row.get("pts_" + key)) is None:
            # a present value with no points means the baseline was missing
            if _num(row.get(key)) is None or _num(row.get(key + "_avg")) is None:
                fields.append(key)
    for key in ("pts_analyst", "pts_institutional", "pts_insider", "pts_earnings", "pts_trend", "pts_sector"):
        if row.get(key) is None or (isinstance(row.get(key), float) and not np.isfinite(row.get(key))):
            fields.append(key)
    return fields


def score_details(scores):
    rows = []
    items = [
        ("Technical", "Trend vs 20-day and 50-day", "pts_trend", None, None),
        ("Technical", "Oscillator (RSI-14)", "pts_oscillator", "rsi14", None),
        ("Financials", "Forward P/E (lower is better)", "pts_forward_pe", "forward_pe", "forward_pe_avg"),
        ("Financials", "Trailing P/E (lower is better)", "pts_ttm_pe", "ttm_pe", "ttm_pe_avg"),
        ("Financials", "Price / sales (lower is better)", "pts_ps", "ps", "ps_avg"),
        ("Financials", "Debt / equity (lower is better)", "pts_de", "de", "de_avg"),
        ("Financials", "Price / free cash flow (lower is better)", "pts_pfcf", "pfcf", "pfcf_avg"),
        ("Financials", "Revenue growth (higher is better)", "pts_rev_growth", "rev_growth", "rev_growth_avg"),
        ("Financials", "EPS growth (higher is better)", "pts_eps_growth", "eps_growth", "eps_growth_avg"),
        ("Financials", "Return on equity (higher is better)", "pts_roe", "roe", "roe_avg"),
        ("Financials", "Dividend yield (higher is better)", "pts_div_yield", "div_yield", "div_yield_avg"),
        ("Sentiment", "Analyst rating", "pts_analyst", "analyst_mean", None),
        ("Sentiment", "Institutional 13F trend", "pts_institutional", None, None),
        ("Sentiment", "Insider buys vs sells", "pts_insider", None, None),
        ("Earnings", "Latest earnings vs estimate", "pts_earnings", None, None),
        ("Sector", "Sector vs S&P 500, 3 months", "pts_sector", "rs_spy_3m", None),
    ]
    for _, r in scores.iterrows():
        for group, item, pts, now, avg in items:
            p = r.get(pts)
            missing_pt = p is None or p == "" or (isinstance(p, (float, np.floating)) and not np.isfinite(p))
            try:
                missing_pt = missing_pt or bool(pd.isna(p))
            except (ValueError, TypeError):
                pass
            label = "n/a" if missing_pt else points_label(p)
            ind = ""
            if pts.startswith("pts_") and "ind_" + pts[4:] in scores.columns:
                ind = r.get("pts_" + pts[4:] + "_ind") if False else r.get("pts_" + pts.replace("pts_", "") + "_ind", "")
            rows.append({
                "ticker": r["ticker"], "group_name": group, "item": item,
                "points": "" if label == "n/a" else int(p), "points_label": label,
                "now_value": r.get(now) if now else "", "avg_value": r.get(avg) if avg else "",
                "vs_industry": "" if ind is None else ind,
            })
    return pd.DataFrame(rows)


def points_label(p):
    """Words, so a sheet does not turn '+1' into a number. The points column stays numeric."""
    n = int(p)
    if n > 0:
        return "plus %d" % n
    if n < 0:
        return "minus %d" % abs(n)
    return "zero"


def _passes_frame(df, cols):
    return df


def scanners(scores, cfg):
    g = scores.copy()
    growth_cut = cfg["growth_min_pct"]
    g["passes"] = np.where(
        g["rev_growth"].map(_num).ge(growth_cut) & g["verdict"].ne("AVOID") & g["rev_growth"].notna(),
        "yes", "no")
    g["why"] = np.where(g["passes"].eq("yes"), "Revenue growth is at least the screen level and the label is not AVOID.", "Does not pass the growth screen.")
    q = scores.copy()
    q["passes"] = np.where((q["pts_roe"] == 1) & (q["de"].map(_num).fillna(99) < cfg["quality_max_de"]) & q["verdict"].ne("AVOID"), "yes", "no")
    q["why"] = np.where(
        q["passes"].eq("yes"),
        "Return on equity point is +1 and debt/equity is under the desk limit. Debt points compare to the sector and can be -1. The label is not AVOID.",
        "Does not pass the quality screen.")
    d = scores.copy()
    d["passes"] = np.where(d["div_yield"].map(_num).ge(cfg["dividend_min_pct"]) & d["verdict"].ne("AVOID"), "yes", "no")
    d["why"] = np.where(d["passes"].eq("yes"), "Dividend yield clears the screen and the label is not AVOID.", "Does not pass the dividend screen.")
    w = scores.copy()
    dv = w["dollar_volume"].map(_num) if "dollar_volume" in w.columns else pd.Series(np.nan, index=w.index)
    w["dollar_volume"] = dv
    w["passes"] = np.where(
        w["verdict"].ne("AVOID") & (w["above_sma200"] == 1) & w["rsi14"].map(_num).lt(70) & dv.ge(cfg["wheel_min_dollar_volume"]) & ~w["timing"].isin(["Extended", "Downtrend"]),
        "yes", "no")
    w["why"] = np.where(
        w["passes"].eq("yes"),
        "Liquid stock in an uptrend that is not extended.",
        "Does not pass the liquid-stock screen.")
    w["why"] = w["why"] + " Stock screen only. No option contracts. Indian options use fixed lot sizes, so this page does not pick a contract."
    return g, q, d, w


def _reaction_table(earnings, close):
    """1-day move after each report. After 4pm Eastern, the move is the next session."""
    rows = []
    if earnings is None or len(earnings) == 0 or close is None or close.empty:
        return pd.DataFrame(rows)
    idx = close.index
    for _, r in earnings.iterrows():
        ts = pd.Timestamp(r["earnings_dt"])
        if ts.tzinfo is not None:
            ts = ts.tz_convert("America/New_York").tz_localize(None)
        day = ts.normalize()
        if ts.hour >= 16:
            day = day + pd.Timedelta(days=1)
        i = idx.searchsorted(day)
        move = np.nan
        if 0 < i < len(idx):
            t = r["ticker"]
            if t in close.columns:
                a, b = close.iloc[i - 1][t], close.iloc[i][t]
                if pd.notna(a) and pd.notna(b) and a > 0:
                    move = (b / a - 1) * 100
        result = beat_flag(_num(r.get("eps_actual")), _num(r.get("eps_estimate")))
        rows.append({
            "ticker": r["ticker"],
            "earnings_date": str(pd.Timestamp(r["earnings_dt"]).date()) if pd.notna(r["earnings_dt"]) else "",
            "eps_estimate": r.get("eps_estimate"),
            "eps_actual": r.get("eps_actual"),
            "surprise_pct": r.get("surprise_pct"),
            "result": result,
            "move_1d_pct": None if not np.isfinite(move) else round(float(move), 2),
            "has_actual": pd.notna(r.get("eps_actual")),
            "earnings_dt": r["earnings_dt"],
        })
    return pd.DataFrame(rows)


def earnings_pages(scores, earnings, close, holdings):
    hist = _reaction_table(earnings, close)
    if hist.empty:
        return {}, hist
    cal_rows, heat_rows, card_rows = [], [], []
    owns = set(holdings or [])
    names = scores.set_index("ticker")["company"].to_dict() if len(scores) else {}
    growth_pts = scores.set_index("ticker")["pts_rev_growth"].to_dict() if len(scores) else {}
    for t, g in hist.groupby("ticker"):
        g = g.sort_values("earnings_dt")
        past = g[g["has_actual"] == True]
        future = g[g["has_actual"] == False]
        moves = past["move_1d_pct"].dropna()
        avg = float(moves.tail(8).mean()) if len(moves) else np.nan
        last = past.iloc[-1] if len(past) else None
        nxt = future.iloc[0] if len(future) else None
        days = ""
        when = ""
        nxt_s = ""
        if nxt is not None and pd.notna(nxt["earnings_dt"]):
            ts = pd.Timestamp(nxt["earnings_dt"])
            if ts.tzinfo is not None:
                ts_et = ts.tz_convert("America/New_York")
                when = "after close" if ts_et.hour >= 16 else "before or during the session"
                days = int((ts_et.tz_localize(None).normalize() - pd.Timestamp.now().normalize()).days)
            nxt_s = str(ts.date())
        cal_rows.append({
            "ticker": t, "company": names.get(t, ""), "next_earnings": nxt_s, "when_hint": when, "days_away": days,
            "last_eps_actual": None if last is None else last["eps_actual"],
            "last_eps_estimate": None if last is None else last["eps_estimate"],
            "last_surprise_pct": None if last is None else last["surprise_pct"],
            "last_1d_move_pct": None if last is None else last["move_1d_pct"],
            "avg_1d_move_pct": None if not np.isfinite(avg) else round(avg, 2),
            "n_past": int(len(past)), "owns": "yes" if t in owns else "no",
        })
        flags = []
        for _, row in past.tail(4).iloc[::-1].iterrows():
            flag = beat_flag(_num(row["eps_actual"]), _num(row["eps_estimate"]))
            flags.append(flag)
            label = {"beat": "eps beat, revenue n/a", "miss": "eps miss, revenue n/a", "inline": "eps inline, revenue n/a"}.get(flag, "incomplete")
            heat = {"beat": 1, "miss": -1, "inline": 0}.get(flag, "")
            heat_rows.append({"ticker": t, "quarter": row["earnings_date"], "eps_flag": flag or "", "rev_flag": "", "label": label, "heat": heat})
        grade, summary = grade_earnings(flags, growth_pts.get(t))
        card_rows.append({
            "ticker": t, "company": names.get(t, ""), "grade": grade or "",
            "summary": summary,
            "sources": "Yahoo Finance earnings dates. Revenue vs estimate is not in that free feed, so revenue is left blank.",
        })
    return {
        "calendar": pd.DataFrame(cal_rows),
        "heatmap": pd.DataFrame(heat_rows),
        "cards": pd.DataFrame(card_rows),
        "history": hist,
    }, hist


def financials_long(scores):
    rows = []
    labels = {
        "forward_pe": ("Forward P/E", "lower"),
        "ttm_pe": ("Trailing P/E", "lower"),
        "ps": ("Price / sales", "lower"),
        "de": ("Debt / equity", "lower"),
        "pfcf": ("Price / free cash flow", "lower"),
        "rev_growth": ("Revenue growth %", "higher"),
        "eps_growth": ("EPS growth %", "higher"),
        "roe": ("Return on equity %", "higher"),
        "div_yield": ("Dividend yield %", "higher"),
    }
    for _, r in scores.iterrows():
        for key, (label, direction) in labels.items():
            avg = r.get(key + "_avg")
            pts = r.get("pts_" + key)
            note = ""
            # A sector fallback used to be written into the own-history column.
            if key in ("roe", "de") and _cell_blank(avg) and not _cell_blank(pts):
                note = "sector fallback"
                pts = ""
            rows.append({
                "ticker": r["ticker"], "sector": r.get("sector"), "metric": label, "direction": direction,
                "now_value": r.get(key), "avg_3y": avg, "pts_vs_self": pts,
                "industry_median": r.get("ind_" + key), "pts_vs_industry": r.get("pts_" + key + "_ind"),
                "note": note,
            })
    return pd.DataFrame(rows)


def _multiple(price, denominator):
    """Price (or market cap) over a fundamental. Blank when either side is missing or not positive."""
    if price is None or denominator is None or not np.isfinite(price) or price <= 0 or denominator <= 0:
        return None
    value = round(float(price) / float(denominator), 4)
    # A ratio that rounds to zero is a unit mismatch (shares in millions, revenue in dollars). Leave it blank.
    if value <= 0:
        return None
    return value


def company_rows(annual, close):
    rows = []
    if annual is None or len(annual) == 0:
        return pd.DataFrame(rows)
    closes = {}
    if close is not None and hasattr(close, "columns"):
        for t in pd.unique(annual["ticker"]):
            if t in close.columns:
                closes[t] = pd.to_numeric(close[t], errors="coerce").dropna()
    for _, r in annual.iterrows():
        rev, gp, oi, ni = _num(r.get("revenue")), _num(r.get("gross_profit")), _num(r.get("op_income")), _num(r.get("net_income"))
        fcf = None
        if _num(r.get("ocf")) is not None and _num(r.get("capex")) is not None:
            fcf = _num(r.get("ocf")) - _num(r.get("capex"))
        gm = gp / rev if rev and gp is not None and rev > 0 else None
        om = oi / rev if rev and oi is not None and rev > 0 else None
        nm = ni / rev if rev and ni is not None and rev > 0 else None
        eps = _num(r.get("eps"))
        shares = _num(r.get("shares"))
        filed = r.get("filed")
        known = None
        if not _cell_blank(filed):
            try:
                known = pd.Timestamp(filed) + pd.Timedelta(days=1)
            except Exception:
                known = None
        px = fund._price_on_or_after(closes.get(r["ticker"]), known)
        if px is not None and not np.isfinite(px):
            px = None
        mcap = px * shares if px is not None and shares is not None else None
        rows.append({
            "ticker": r["ticker"],
            "fy_end": _date_cell(r.get("fy_end") if not _cell_blank(r.get("fy_end")) else r.get("end")),
            "filed": _date_cell(filed),
            "revenue": rev, "gross_profit": gp, "op_income": oi, "net_income": ni,
            "eps": eps,
            "gross_margin": None if gm is None else round(gm * 100, 2),
            "operating_margin": None if om is None else round(om * 100, 2),
            "net_margin": None if nm is None else round(nm * 100, 2),
            "fcf": fcf,
            "pe": fund.guard_multiple(_multiple(px, eps)),
            "ps": _multiple(mcap, rev),
            "pfcf": _multiple(mcap, fcf),
        })
    return pd.DataFrame(rows)


def mark_nearest_expiry(df, today=None):
    """Flag the expiry on or after today for each ticker. No chain download.

    If every expiry is already past, the latest one is the nearest. The flag
    is the text true or false so it is not stored as 1 or 0.
    """
    if df is None or len(df) == 0 or "expiry" not in df.columns:
        return df
    out = df.copy()
    day = pd.Timestamp(today).normalize() if today is not None else pd.Timestamp.now().normalize()
    exp = pd.to_datetime(out["expiry"], errors="coerce")
    out["nearest_expiry"] = "false"
    for _, idx in out.groupby(out["ticker"].astype(str)).groups.items():
        dates = exp.loc[idx]
        future = dates[dates >= day]
        if len(future):
            pick = future.min()
        else:
            past = dates.dropna()
            if not len(past):
                continue
            pick = past.max()
        out.loc[dates[dates == pick].index, "nearest_expiry"] = "true"
    return out


def macro_tables(econ, sector_etfs):
    if econ is None or len(econ) == 0:
        return pd.DataFrame(), pd.DataFrame()
    screener = econ.copy()
    if "signal" in econ.columns:
        released = econ[pd.to_numeric(econ["signal"], errors="coerce").notna()]
    else:
        released = econ
    # latest signal per category
    sig = {}
    if len(released):
        for cat, g in released.groupby("category"):
            sig[cat] = int(np.sign(g["signal"].sum())) if g["signal"].sum() != 0 else 0
    rows = []
    for etf in sector_etfs:
        w = MACRO_WEIGHT.get(etf["ticker"], {})
        if not sig or not w:
            rows.append({"ticker": etf["ticker"], "name": etf["name"], "macro_growth": "", "macro_inflation": "", "macro_jobs": "", "macro_score": "", "plain_english": "No mapped macro surprise."})
            continue
        parts = {}
        for cat in ("Growth", "Inflation", "Jobs"):
            parts[cat] = sig.get(cat, 0) * w.get(cat, 0)
        score = parts["Growth"] + parts["Inflation"] + parts["Jobs"]
        rows.append({
            "ticker": etf["ticker"], "name": etf["name"],
            "macro_growth": parts["Growth"], "macro_inflation": parts["Inflation"], "macro_jobs": parts["Jobs"],
            "macro_score": score,
            "plain_english": "Rule of thumb from the latest surprises. It is not a forecast.",
        })
    return screener, pd.DataFrame(rows)


def put_call_table(pcr, fear, greed):
    if pcr is None or len(pcr) == 0:
        return pd.DataFrame()
    df = pcr.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["name", "date"])
    df["ma5"] = df.groupby("name")["value"].transform(lambda s: s.rolling(5, min_periods=1).mean())
    df["fear_line"] = fear
    df["greed_line"] = greed
    def zone(v):
        if v is None or not np.isfinite(v):
            return ""
        if v >= fear:
            return "Fear"
        if v <= greed:
            return "Greed"
        return "Neutral"
    df["zone"] = df["ma5"].map(zone)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def xly_xlp_table(close):
    if close is None:
        return pd.DataFrame()
    left = "^CNXAUTO" if "^CNXAUTO" in close.columns else ("XLY" if "XLY" in close.columns else None)
    right = "^CNXFMCG" if "^CNXFMCG" in close.columns else ("XLP" if "XLP" in close.columns else None)
    if left is None or right is None:
        return pd.DataFrame()
    df = pd.DataFrame({"xly": close[left], "xlp": close[right]}).dropna()
    if df.empty:
        return pd.DataFrame()
    df["ratio"] = df["xly"] / df["xlp"]
    df["ratio_sma50"] = df["ratio"].rolling(50).mean()
    df["zone"] = np.where(df["ratio"] > df["ratio_sma50"], "Risk on", "Risk off")
    df = df.dropna(subset=["ratio"]).tail(260).reset_index()
    date_col = "date" if "date" in df.columns else df.columns[0]
    df["date"] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
    return df[["date", "xly", "xlp", "ratio", "ratio_sma50", "zone"]]


def historical_pe(close, prepared):
    if close is None or close.empty or not prepared:
        return pd.DataFrame()
    idx = close.index
    month_ends = idx.to_series().groupby(idx.to_period("M")).max().tolist()[-120:]
    if not month_ends:
        return pd.DataFrame()
    ends = pd.DatetimeIndex(month_ends)
    pes_by_month = [[] for _ in month_ends]
    for t, prep in prepared.items():
        if t not in close.columns or prep is None or len(prep) == 0:
            continue
        if "known_on" not in prep.columns or "eps" not in prep.columns:
            continue
        known_on = pd.to_datetime(prep["known_on"], errors="coerce")
        if getattr(known_on.dt, "tz", None) is not None:
            known_on = known_on.dt.tz_localize(None)
        known_vals = known_on.values
        eps_vals = pd.to_numeric(prep["eps"], errors="coerce").values
        prices = pd.to_numeric(close[t].reindex(ends), errors="coerce").values
        # For each month end, the last row in file order already known on that day.
        ok = known_vals[None, :] <= ends.values[:, None]
        any_ok = ok.any(axis=1)
        last = ok.shape[1] - 1 - np.argmax(ok[:, ::-1], axis=1)
        for i in np.flatnonzero(any_ok):
            eps = eps_vals[last[i]]
            price = prices[i]
            if np.isfinite(eps) and eps > 0 and np.isfinite(price) and price > 0:
                pe = price / eps
                if 0 < pe < 2000:
                    pes_by_month[i].append(pe)
    rows = []
    for d, pes in zip(month_ends, pes_by_month):
        if len(pes) < 20:
            continue
        rows.append({
            "date": str(pd.Timestamp(d).date()),
            "desk_median_trailing_pe": round(float(np.median(pes)), 2),
            "n": len(pes),
            "official_sp500_pe": "",
            "official_status": "MISSING",
        })
    return pd.DataFrame(rows)


def technical_pages(scores):
    br = scores[scores["dist_52w_high_pct"].map(_num).ge(-1)].copy() if "dist_52w_high_pct" in scores.columns else scores.iloc[0:0]
    tr = scores.copy()
    def trend_label(r):
        flags = [r.get("above_sma20"), r.get("above_sma50"), r.get("above_sma100"), r.get("above_sma200")]
        if all(f == 1 for f in flags):
            return "Uptrend"
        if all(f == 0 for f in flags if f in (0, 1)) and all(f in (0, 1) for f in flags):
            return "Downtrend"
        return "Mixed"
    tr["trend_label"] = tr.apply(trend_label, axis=1)
    pb = scores.copy()
    has_entry = pb["entry_low"].map(_num).notna() & pb["entry_high"].map(_num).notna() if "entry_low" in pb.columns else False
    pb["passes"] = np.where(
        (pb["above_sma200"] == 1) & (pb["above_sma50"] == 1) & pb["timing"].isin(["Pullback", "In entry zone"])
        & pb["rsi14"].map(_num).lt(70) & pb["verdict"].ne("AVOID") & has_entry,
        "yes", "no")
    pb["why"] = np.where(pb["passes"].eq("yes"), "Uptrend structure with price back near the entry area.", "Not a pullback setup.")
    gl = []
    s2 = scores.dropna(subset=["day_pct"]).sort_values("day_pct", ascending=False)
    for _, r in s2.head(15).iterrows():
        gl.append({**r.to_dict(), "side": "gainer"})
    for _, r in s2.tail(15).iterrows():
        gl.append({**r.to_dict(), "side": "loser"})
    heat = scores.copy()
    heat["ret_1d"] = heat["day_pct"]
    heat["ret_1w"] = heat.get("ret_1w")
    heat["ret_1m"] = heat.get("ret_1m")
    heat["ret_ytd"] = heat.get("ret_ytd")
    return br, tr, pb, pd.DataFrame(gl), heat


def sector_perf(scores):
    rows = []
    if scores is None or len(scores) == 0:
        return pd.DataFrame()
    for sector, g in scores.groupby(scores["sector"].fillna("Unknown")):
        rows.append({
            "sector": sector,
            "day_pct": round(float(pd.to_numeric(g["day_pct"], errors="coerce").mean()), 2),
            "week_pct": _mean(g, "ret_1w"),
            "month_pct": _mean(g, "ret_1m"),
            "month3_pct": _mean(g, "ret_3m"),
            "ytd_pct": _mean(g, "ret_ytd"),
            "pct_above_sma50": round(float((g["above_sma50"] == 1).mean()) * 100, 1) if "above_sma50" in g else "",
            "score_avg": _mean(g, "score"),
            "n": int(len(g)),
        })
    return pd.DataFrame(rows)


def _mean(g, col):
    if col not in g.columns:
        return ""
    s = pd.to_numeric(g[col], errors="coerce").dropna()
    if not len(s):
        return ""
    return round(float(s.mean()), 2)


def etf_sectors(close, scores, sector_etfs, macro_df):
    rows = []
    macro = macro_df.set_index("ticker") if macro_df is not None and len(macro_df) else None
    for etf in sector_etfs:
        t = etf["ticker"]
        rec = {"ticker": t, "name": etf["name"], "group_name": etf.get("group", etf["name"])}
        if close is not None and t in close.columns:
            s = close[t].dropna()
            if len(s) > 5:
                rec["day_pct"] = _ret(s, 1)
                rec["week_pct"] = _ret(s, 5)
                rec["month_pct"] = _ret(s, 21)
                rec["month3_pct"] = _ret(s, 63)
                rec["ytd_pct"] = _ytd(s)
                bench_name = "^NSEI" if "^NSEI" in close.columns else ("SPY" if "SPY" in close.columns else None)
                if bench_name:
                    spy = close[bench_name].reindex(s.index).dropna()
                    both = s.reindex(spy.index).dropna()
                    if len(both) > 63 and len(spy) > 63:
                        rec["rs_3m_pct"] = round((both.iloc[-1] / both.iloc[-64] - spy.iloc[-1] / spy.iloc[-64]) * 100, 2)
        members = _members(scores, etf)
        if len(members):
            rec["score_avg"] = _mean(members, "score")
            rec["n_stocks"] = int(len(members))
            rec["pct_above_sma50"] = round(float((members["above_sma50"] == 1).mean()) * 100, 1)
        series = close[t].dropna() if close is not None and t in getattr(close, "columns", []) else pd.Series(dtype=float)
        if len(series) <= 5 and len(members):
            # The index file had no history, so use the average of the stocks in the group.
            for src, dest in (("day_pct", "day_pct"), ("ret_1w", "week_pct"), ("ret_1m", "month_pct"), ("ret_3m", "month3_pct"), ("ret_ytd", "ytd_pct")):
                if src in members.columns and rec.get(dest) in (None, ""):
                    rec[dest] = _mean(members, src)
        if macro is not None and t in macro.index:
            m = macro.loc[t]
            for k in ("macro_growth", "macro_inflation", "macro_jobs", "macro_score"):
                rec[k] = m.get(k)
        rows.append(rec)
    return pd.DataFrame(rows)


def _members(scores, etf):
    if scores is None or len(scores) == 0:
        return scores.iloc[0:0]
    group = etf.get("group")
    base = scores[scores["sector"] == group] if group else scores.iloc[0:0]
    ticker = etf["ticker"]
    if ticker in ("XLK", "XLV", "XLF", "XLI", "XLC", "XLY", "XLP", "XLE", "XLU", "XLRE", "XLB",
                  "^CNXIT", "^CNXFIN", "^CNXAUTO", "^CNXPHARMA", "^CNXFMCG", "^CNXENERGY", "^CNXINFRA", "^CNXCONSUM"):
        return base
    key = etf["name"].lower()
    ind = scores["industry"].fillna("").str.lower() if "industry" in scores.columns else pd.Series("", index=scores.index)
    for needle, code in INDUSTRY_ETF:
        if code == ticker:
            # A narrower index (banks, media, metal) keeps only that industry.
            return scores[ind.str.contains(needle, regex=False)]
    return base


def _ret(s, n):
    if len(s) <= n or s.iloc[-1 - n] == 0:
        return ""
    return round(float(s.iloc[-1] / s.iloc[-1 - n] - 1) * 100, 2)


def _ytd(s):
    year = s.index[-1].year
    sub = s[s.index.year == year]
    if len(sub) < 2 or sub.iloc[0] == 0:
        return ""
    return round(float(sub.iloc[-1] / sub.iloc[0] - 1) * 100, 2)


def breadth_history(close):
    """Share of stocks above each moving average, on sessions where stocks traded.

    A holiday that only has a VIX print used to leave one blank row in the price
    panel. The next 20, 50, 100, and 200 sessions then had no average, and those
    missing readings were stored as 0. Missing stays blank. A stock with no price
    or no average that day is left out of the count. It is not treated as below.
    """
    if close is None or close.empty:
        return pd.DataFrame()
    drop = [c for c in list(MACRO_WEIGHT) + ["SPY", "QQQ", "^VIX", "^NSEI", "^NSEBANK", "^BSESN", "^INDIAVIX", "INR=X"] if c in close.columns]
    px = close.drop(columns=drop, errors="ignore")
    if px.shape[1] == 0:
        return pd.DataFrame()
    traded = px.notna().sum(axis=1)
    if int(traded.max()) == 0:
        return pd.DataFrame()
    # Half the usual names, and at least 20. That drops a holiday row and keeps a normal session.
    floor = max(20, int(traded.max() * 0.5))
    px = px.loc[traded >= floor]
    if px.empty:
        return pd.DataFrame()
    shares = {}
    for n, name in ((20, "pct_above_sma20"), (50, "pct_above_sma50"), (100, "pct_above_sma100"), (200, "pct_above_sma200")):
        sma = px.rolling(n, min_periods=n).mean()
        valid = px.notna() & sma.notna()
        count = valid.sum(axis=1)
        above = (px > sma) & valid
        share = above.sum(axis=1) / count.where(count >= 20)
        shares[name] = share * 100
    ready = shares["pct_above_sma20"].dropna()
    if ready.empty:
        return pd.DataFrame()
    idx = px.index[px.index >= ready.index[0]][-140:]
    rows = []
    for d in idx:
        row = {"date": str(pd.Timestamp(d).date())}
        for name, series in shares.items():
            v = series.loc[d]
            if pd.notna(v):
                row[name] = round(float(v), 1)
        rows.append(row)
    return pd.DataFrame(rows)


def market_row(close, breadth, pcr_df, fred, xratio, updated, asof, n, scores):
    row = {"updated_pt": updated, "price_as_of": asof, "universe_n": n}
    bench = "^NSEI" if close is not None and "^NSEI" in close.columns else ("SPY" if close is not None and "SPY" in close.columns else None)
    if bench:
        s = close[bench].dropna()
        if len(s):
            row["spy_price"] = round(float(s.iloc[-1]), 2)
            if len(s) > 1 and s.iloc[-2]:
                row["spy_day_pct"] = round(float(s.iloc[-1] / s.iloc[-2] - 1) * 100, 2)
    bank = "^NSEBANK" if close is not None and "^NSEBANK" in close.columns else ("QQQ" if close is not None and "QQQ" in close.columns else None)
    if bank:
        q = close[bank].dropna()
        if len(q):
            row["bank_price"] = round(float(q.iloc[-1]), 2)
        if len(q) > 1 and q.iloc[-2]:
            row["qqq_day_pct"] = round(float(q.iloc[-1] / q.iloc[-2] - 1) * 100, 2)
    if close is not None and "^BSESN" in close.columns:
        sx = close["^BSESN"].dropna()
        if len(sx):
            row["sensex_price"] = round(float(sx.iloc[-1]), 2)
        if len(sx) > 1 and sx.iloc[-2]:
            row["sensex_day_pct"] = round(float(sx.iloc[-1] / sx.iloc[-2] - 1) * 100, 2)
    vix_name = "^INDIAVIX" if close is not None and "^INDIAVIX" in close.columns else ("^VIX" if close is not None and "^VIX" in close.columns else None)
    if vix_name:
        v = close[vix_name].dropna()
        if len(v):
            row["vix"] = round(float(v.iloc[-1]), 2)
    if close is not None and "INR=X" in close.columns:
        fx = close["INR=X"].dropna()
        if len(fx):
            row["inr_usd"] = round(float(fx.iloc[-1]), 2)
    if breadth is not None and len(breadth):
        last = breadth.iloc[-1]
        for k in ("pct_above_sma20", "pct_above_sma50", "pct_above_sma100", "pct_above_sma200"):
            row[k.replace("pct_above_", "breadth_")] = last.get(k)
        if len(breadth) > 5:
            row["breadth_sma50_week_ago"] = breadth.iloc[-6].get("pct_above_sma50")
    if scores is not None and len(scores):
        if "verdict" in scores.columns:
            row["buy_count"] = int((scores["verdict"].astype(str) == "BUY").sum())
        day = pd.to_numeric(scores["day_pct"], errors="coerce")
        row["advancers"] = int((day > 0).sum())
        row["decliners"] = int((day < 0).sum())
        dist = pd.to_numeric(scores["dist_52w_high_pct"], errors="coerce")
        row["highs_52w"] = int((dist >= -1).sum())
        # lows: price near 252-day low is not in dist. leave blank if we didn't compute it
        if "near_low" in scores.columns:
            row["lows_52w"] = int(scores["near_low"].sum())
    if pcr_df is not None and len(pcr_df):
        eq = pcr_df[pcr_df["name"] == "EQUITY PUT/CALL RATIO"]
        use = eq if len(eq) else pcr_df
        last = use.iloc[-1]
        row["put_call"] = last.get("value")
        row["put_call_ma5"] = last.get("ma5")
        row["put_call_zone"] = last.get("zone")
        row["put_call_name"] = last.get("name")
    if fred:
        row["fred_dgs10"] = fred.get("DGS10")
        row["fred_t10y2y"] = fred.get("T10Y2Y")
    if xratio is not None and len(xratio):
        row["xly_xlp"] = round(float(xratio.iloc[-1]["ratio"]), 3)
    return pd.DataFrame([row])


def freshness_table(scores):
    fields = [k for k, _ in FIN_SPECS] + ["pts_analyst", "pts_institutional", "pts_insider", "pts_earnings", "pts_trend", "pts_sector"]
    rows = []
    n = len(scores)
    for f in fields:
        if f not in scores.columns or n == 0:
            rows.append({"field": f, "n_missing": n, "n_present": 0})
            continue
        present = pd.to_numeric(scores[f], errors="coerce").notna().sum()
        rows.append({"field": f, "n_missing": int(n - present), "n_present": int(present)})
    return pd.DataFrame(rows)


def help_rows():
    return [
        ("What this is", "Nick's India Stock Desk is a research screen for NSE stocks. It does not place trades and it does not connect to a broker. Nothing here is a recommendation to buy or sell."),
        ("Stocks only", "There are no option contract picks. The liquid stocks page is a stock screen. The put and call walls page is market mood only. Indian options use fixed lot sizes, so this desk does not pick a contract."),
        ("Prices", "Prices are in rupees. The daily bars come from the NSE bhavcopy. If that file is missing, the desk tries the BSE bhavcopy, then Stooq, then Yahoo. The Nifty 50, SENSEX, and Bank Nifty are shown side by side. SENSEX daily bars come from the BSE index file, then Yahoo, then Stooq, then the saved cache. NSE stocks are compared with the Nifty 50. BSE-only stocks are compared with SENSEX. Turn SENSEX off with feature.sensex."),
        ("The score", "Each money measure is plus 1, 0, or minus 1 versus that company's own recent history. Lower is better for forward P/E, trailing P/E, price/sales, debt/equity, and price/free cash flow. Higher is better for revenue growth, EPS growth, return on equity, and dividend yield. Analyst rating can be plus 2 to minus 2. Shareholding, insiders, the price trend, the oscillator, the latest result, and the sector each add a small point. The score is the sum of the points we actually have."),
        ("Missing data", "A missing number is left blank and marked n/a. It is not stored as zero and it does not add or subtract a point. If a free source is blocked, the page says not available."),
        ("Forward P/E history", "Free data does not include a history of forward estimates. The baseline for forward P/E is the 3-year average of year-end trailing P/E."),
        ("Versus the industry", "The industry figure is the middle value of the other stocks in the same sector on this desk. It is not a paid database. If fewer than four peers have a number, the comparison is blank."),
        ("Verdicts", "BUY, HOLD, and AVOID are research labels. A high score that is extended, in a downtrend, or missing most of its financials is labeled HOLD instead of BUY. When a stock has no financials yet, the label is Not scored yet, in gray, and the reason says financials are still downloading. That is not an AVOID. Entry, stop, and target are a plan for study, not an order."),
        ("Targets", "You will see an analyst target when Yahoo has one, a price/free-cash-flow target, a PEG-style target, and a blend of whichever of those exist. The trade target is separate. It is an entry-zone plan using the recent daily range."),
        ("Backtest", "Once a month the job asks what the score would have been using only data that was already public, then looks at the next 1, 4, and 12 weeks versus the Nifty 50. Read the headline. If it says there is no clear edge, believe that. Past results are not future results."),
        ("Shareholding", "Promoter, FII, DII, and other public percents come from the NSE shareholding filing when that file is reachable. The change is versus the prior quarter. If the split is missing, the cell says not verified. It is not a US 13F report."),
        ("Insiders", "Insider points use NSE PIT buy and sell counts over three months. If NSE blocks the file, the page says data not available for free and the score for that piece stays blank."),
        ("Put/call and walls", "The put/call line is Nifty put open interest divided by call open interest, when the NSE option chain answers. Walls are the strikes with the most open interest. They are mood, not a trade. If NSE blocks the chain, the page says not available."),
        ("India mood", "There is no Indian version of the AAII survey, so that survey is not shown. This page uses India VIX and, when the NSE file answers, the day's FII and DII cash flow in crores."),
        ("Nifty P/E", "There is no free official daily Nifty 50 P/E this desk can rely on. The chart is the median trailing P/E of the stocks on this desk. The official column stays blank."),
        ("Macro", "The macro page shows India CPI, GDP, and industry growth from the World Bank when that feed answers, plus the rupee from Yahoo. A forecast is often missing, so the surprise stays blank. It is a sketch, not a forecast. The rate column on the sector map is a simple rule of thumb."),
        ("Auto versus FMCG", "This is the Nifty Auto index divided by the Nifty FMCG index. It stands in for the old discretionary versus staples chart. Above the 50-day average of the ratio is labeled risk on."),
        ("Rate limits", "The after-close run reads that day's bhavcopy and a slice of statements and shareholding. It does not download every company from Yahoo. A light morning run only refreshes headlines and FII or DII cash. If a source fails, the previous file is kept and the updates log says CACHED."),
        ("The lists", "The desk covers NSE shares and BSE-only shares. Tags are Nifty 50, Next 50, Midcap 150, Smallcap 250, Microcap 250, Total Market, Other NSE, and BSE only. Each tag has a switch. SME is off unless you turn it on. Your holdings, watchlist, and my picks are always included. A company on both exchanges is shown once, under the NSE symbol."),
        ("Liquidity", "Scanners hide names whose 20-day median traded value is under the rupee line in config.json. The line is 1 crore rupees unless you change it. Top stocks can still show the quieter names if you turn the liquid filter off."),
        ("FII and DII", "The FII and DII page shows cash-market buy and sell in crore rupees. Green is net buying. Red is net selling. The history grows each day. A second block shows index-futures positioning when the NSE participant file answers."),
        ("Times", "Times are shown in India time (IST) and Pacific time (PT)."),
        ("VCP scanner", "This page follows the same 8-point trend template and pullback count as Nick's indicator. NSE stocks use the Nifty 50 as the benchmark. BSE-only stocks use SENSEX. A stock is listed only when it would get the green VCP tag: all 8 trend rules pass and there are at least two pullbacks that get smaller. READY means price is still under the buy line. BROKEN OUT today means today's close went above the buy line on volume at least 1.5 times the 50-day average. WATCHING means price is above the buy line on low volume, or there is only one pullback so far, and the trend is still 8 of 8. A stock still in a trade stays listed if its buy printed with 8 of 8, even if the trend has slipped since. Set vcp.show_weaker_trend to true to also see stocks with smaller pullbacks but a weaker trend. They show as WATCHING (trend not 8/8)."),
        ("CANSLIM scanner", "C and A are the year-ago EPS change from the saved statements. N is how close the price is to its 52-week closing high. S is the 20-day average volume. L is the relative-strength percentile versus the Nifty for NSE stocks, and versus SENSEX for BSE-only stocks. I is the shareholding change when we have it. M shows the Nifty 50, SENSEX, and Bank Nifty side by side as Uptrend, Under pressure, or Correction. The market is in an uptrend when the Nifty 50 or SENSEX is in an uptrend. Set market.require_both_uptrends to true to require both. Bank Nifty is shown and does not decide. The What CANSLIM means box explains each letter. A blank that says not verified was not in the cache. It is not a guess."),
        ("Row charts", "On a stock list, the button at the left of a row opens that stock's daily price chart under the row. Only one chart stays open. The caption names the benchmark: Nifty 50 for NSE stocks, SENSEX for BSE-only stocks. The scorecard says the same thing. Turn the charts off with feature.row_charts in config.json."),
        ("52-week highs and lows", "The 52-week high is the highest price of the last 252 trading sessions, and the 52-week low is the lowest. A new high today means the close is at or above the prior 252-session high. A new low today means the close is at or below the prior 252-session low. Near the high means the close is within 5% of that high. A high on volume also needs volume at least 1.5 times the 50-day average. This page is separate from the 52-week breakouts list, which only keeps names within 1% of the high. Research only. Turn it off with feature.scanner_52w."),
        ("Buy setups", "Research list, not a recommendation. This desk never places trades. A stock is listed when VCP, Box, Flag, Qullamaggie, Marios, Episodic Pivot (EP), or CANSLIM is ready or broke out today, the close is above the 50-day and the 200-day averages, and the risk from the entry to the stop is 8% or less. Qullamaggie, Marios, and EP rows marked Too wide, skip are left out. An EP counts as ready on its EP day and days 2 to 5 (buy above the EP-day high), and as broke out today when the price goes above it. EP stocks locked at the upper circuit, faded EPs, and delayed EPs are left out. Chart setups only, on while financials coverage is under 80%, also keeps a BUY or a Not scored yet label and marks the unscored names Financials pending. A scored AVOID stays off the list until you press Show anyway. Turn that switch off and the page keeps only BUY. The market check passes when the Nifty 50 or SENSEX is in an uptrend. Set market.require_both_uptrends to require both. Bank Nifty is shown and does not decide. When the check fails, the list stays empty until you press Show anyway. Show anyway then lists every name that passes the chart rules, greyed out, with its real verdict: BUY, HOLD, AVOID, or Not scored yet. The banner names which index is up or down. The stop is the tighter of 7% under the entry or the setup's own stop. Target 1 is 20% above the entry, or 20% above the breakout close. Target 2 is the entry plus three times the risk. Scores are rebuilt from the saved financials and shareholding at the end of every backfill run, with no new downloads. Turn that off with fundamentals_backfill.rebuild_pages_after_run. Turn the page off with feature.buy_setups."),
        ("Sector rotation", "The graph compares Nifty sector indexes with a benchmark using daily closes already in the cache. The default benchmark is the Nifty 50. You can switch the page to SENSEX. No new download. RS is the sector index close divided by that benchmark. RS-Ratio is 100 plus the z-score of that ratio, after a moving average, versus its own rolling mean. RS-Momentum is 100 plus the z-score of the change in RS-Ratio. 100 is the center. Leading is top right, Weakening is bottom right, Lagging is bottom left, Improving is top left. Weekly and monthly points are built from those same daily bars. The score blends relative strength, how many of the sector's stocks are above their averages, how many are near a 52-week high, how many are on a buy setup, and the average desk score. A missing factor is left out. It is not stored as zero. Oil and gold are not on file. Turn it off with feature.sector_rotation."),
        ("Financials backfill", "A separate job downloads company statements, ratios, analyst numbers, and promoter, FII, DII, and public shareholding. It is scheduled every 15 minutes, including weekends, and continues from a saved cursor. GitHub may start a run late. Liquid stocks come first, then the rest of the NSE list, then BSE-only names. After every name has a saved row, it refreshes the oldest shareholding about every 90 days and refreshes results after the next earnings date, or every 90 days. At 200 statements and 200 shareholding names a run, the first pass of the full list is well under a day when the free sources answer. A name with no shareholding filing is saved for later in the pass. Turn it off with feature.fundamentals_backfill. The price schedule does not change."),
        ("High volume", "This page lists stocks that traded far more shares than usual in the latest session. Volume ratio is today's volume divided by the average of the last 50 sessions, so 3.2x means 3.2 times a normal day. Heavy volume on an up day usually means buying. Heavy volume on a down day usually means selling. The page starts at 2x or more, a close over Rs 20, and at least Rs 1 crore traded. You can switch to 1.5x, 3x, or 5x, pick up days or down days, and pick NSE or BSE. Tap a row to see its chart. It uses the same daily prices the desk already saves. No new download. ETFs and funds are left out. Research only. Turn it off with feature.high_volume_scanner."),
        ("Box and flag", "A box is a tight sideways range that closes out the top on above-average volume. A flag is a sharp rise, a short pause, then a close above the pause on volume. These two are desk rules."),
        ("Qullamaggie breakout", "Qullamaggie's own rules: top 1 to 2% gainers, ADR of 3.5 to 5% or more, a 30 to 100% run in 1 to 3 months, then a 2 week to 2 month base with higher lows riding the 10 and 20-day averages (sometimes the 50). He buys the opening range high, puts the stop at the low of the day no wider than ADR, sells 1/3 to 1/2 after 3 to 5 days, moves the stop to breakeven, and trails the rest with the 10 or 20-day close. Daily-data approximations on this page: top 3% on the 21, 63 or 126-day return across the scanned stocks, a 30% run within the 63 days before the base that rose in 40 days or less, ADR as the 20-day average of high divided by low minus 1 (3.5% or more, 5% or more is tagged fast), price at least Rs 20, a 10 to 40 day base whose second-half lowest low is at or above the first half, at least 70% of closes above the 20-day or all above the 50-day, and the 10-day above the 20-day with both rising. Desk rules with their own switches: base no deeper than 25%, base top within 10% of the run high, and the base starts in the top half of its range. The trigger is the day's high going above the base high when the prior day's high was not. Fill is the open or the base high, whichever is higher. Stop is that day's low. More than 1 ADR from fill to stop is Too wide, skip, and it stays on the page but not on Buy setups. 0.5 ADR or less is A+. ADR is used for this check on both pages. READY means the close is within 1 ADR under the base high. Volume of 1.5 times the prior 50 days is a ranking flag, not a rule. Volume drying up is shown as a flag. IN TRADE follows each breakout bar by bar: Sell 1/3 to 1/2 on day 3 to 5 with the stop at breakeven, then the first close under the 10-day ends it (qullamaggie.trail_use_sma20 switches to the 20-day). CLOSED shows the reason and the date, for up to 60 sessions. Market light, results within 5 sessions, 20-day traded value, price band, and shares for 0.5% risk are columns, not rules. Every rule has a switch in the qullamaggie block of config.json."),
        ("Marios breakout", "Marios Stamatoudis's own rules: ADR above 2.5% (he prefers 3.5%), opening range breakout entries, a stop at the low of the day under 1 ATR, partials at 2.5 to 3 ADRs above the entry (ADRs, not R), breakeven after the partial, and a trail on the 10, 20 or 50-day average. The slides that went around were Financial Wisdom TV's summary, not his own. This page uses the same daily-data base and entry checks as the Qullamaggie page, with ADR at least 2.5% (3.5% or more marked preferred), a prior run within 126 days, and the volume dry-up as a rule (last 5 base days under the 50-day average). The stop check uses ADR instead of ATR. A weak day-1 close (under the fill, or less than half the risk above it) is flagged. Selling: 1/4 to 1/3 when the high reaches the entry plus 2.5 ADRs (the 3 ADR level is shown too), then the stop moves to breakeven. A close under the 10-day sells 1/3 of the rest. A close under the 20-day sells the rest and the trade shows as CLOSED with the reason and date. Every rule has a switch in the marios block of config.json."),
        ("Episodic Pivot", "An Episodic Pivot (EP) is a big jump on surprise news, like strong results. This page follows Qullamaggie and Stockbee's own rules. An EP day is a gap up of 10% or more at the open, or a close 8% or more above the day before, on at least 3 times the average volume of the last 50 days. Price must be at least Rs 20. Only liquid stocks are scanned (at least Rs 1 crore a day, the middle value of the last 20 days). ETFs and funds are left out. Prices are end of day only, so there is no early-morning check and no opening range high. EP TODAY means a strong close: in the top half of the day's range and at or above the open. Buy above the EP-day high in the next sessions, with the stop at the EP-day low. EP FADED means a weak close, so it is not a buy. WATCHING is day 2 to 5 after a strong EP. DELAYED WATCH is day 6 to 20 (day 2 to 20 after a fade): it waits for a tight 5-day range and buys above its high. BROKEN OUT today means the price went above the buy level today. IN TRADE shows the stop. On day 3 to 5 of the trade it says SELL PART: sell 1/3 to 1/2 and move the stop to breakeven. Then sell the rest on the first close under the 10-day average, or the 20-day when the normal daily move (ADR) is under 5%. NO FOLLOW-THROUGH means it did not rise one normal day's move in 5 sessions (Stockbee's time stop). CLOSED shows the result and stays for 10 sessions. A stock locked at the upper circuit is flagged no entry possible. A stop more than 1.5 times the normal daily range is marked Too wide, skip. Rows are ranked by base grade: A is flat or down before the EP, B is up a little, C already ran more than 30% in 3 months. Earnings EP means results came out on the EP day or the day before. Guidance, revenue beats, and other news are not in the free data, so check them with the announcements link. Nick's own filters are switches that start off. Numbers are under episodic_pivot in config.json. Turn the page off with feature.scanner_episodic_pivot."),
        ("Gap Up", "The Gap Up page lists stocks that opened above the day before's high (a true gap) and have held it since. The gap must be at least 3%. Gap % is the open divided by the day before's high, minus 1. Turn the 3% minimum off with gap_up.min_gap_filter, and then any gap counts. The gap day also needs at least 1.5 times the average volume of the 50 days before it and a close of at least Rs 20. The stock must also trade at least Rs 1 crore a day on average over the last 50 days, the same rupee line the Episodic Pivot scan uses. ETFs and funds are left out. The gap-day low is the hold level. A stock is dropped as soon as any daily close from the gap day through today is below it. A close exactly on it still counts as holding. Only gaps in the last 21 trading days, today included, are checked. If a stock gapped more than once, the most recent gap that still holds is shown. GAP UP today means the gap was on the latest day. GAP HOLDING means an older gap that still holds. Newest gaps come first, then the biggest. Close in gap-day range shows where the gap day closed between its low (0) and high (100). Also on lists the other scanners that show the same stock. Gap Up does not feed Buy setups. Prices are end of day only. It uses the saved daily bars. Nothing new is downloaded, and nothing is sent to you. Numbers are under gap_up in config.json. Turn the page off with feature.scanner_gap_up."),
        ("Market cap", "Market cap is the number of shares times the latest close, in Rs crore. Share counts come from the company results the desk already saved, and they are kept in cache/market_cap.csv so every run reuses them. A newer result replaces an older count. If an Episodic Pivot stock still has no share count, the after-close run asks Yahoo for it, at most 5 stocks a run, and saves the answer. A stock with no answer is asked again after 30 days. No paid data and no key. A share split after the last result can make the number too low until the next result."),
        ("Chart Viewer", "The Chart Viewer page shows one big daily chart at a time. Pick a list at the top. All scanner stocks is every stock on VCP, CANSLIM, Box, Flag, Qullamaggie, Marios, Episodic Pivot, Gap Up, Leaders, 52-week, 52-week breakouts, High volume, Pullbacks, Growth, Quality, Dividend, or Liquid stocks, with no repeats. Chart scanners count every status except CLOSED (chart_viewer.include_watching and chart_viewer.include_closed). Growth, Quality, Dividend, Liquid stocks, and Pullbacks count the stocks that pass. High volume counts the stocks its page lists. 52-week counts a new high, a new low, or near the high. Gap Up counts every stock its page lists (chart_viewer.include_gap_up). Buy setups and the watchlist show in the reason box but do not add to the count. Stocks found by the most scanners come first, then the strongest. A Technical | Fundamental switch sits above the list (chart_viewer.group_toggle). Technical shows only the chart scanners and All technical stocks. Fundamental shows only CANSLIM, Leaders, Growth, Quality and Dividend, and All fundamental stocks. The reason box then lists only that group's scanners, plus Buy setups and the watchlist. The switch starts on Technical (chart_viewer.default_group) and remembers your last choice on this device. Swiping stays inside the list you picked. You can also pick one scanner, Buy setups, or your watchlist. Each scanner page has an Open in Chart Viewer link. Tap Full screen. On iPhone, where Safari has no full screen for pages, the chart covers the whole screen instead. Swipe right for the next chart and left to go back (chart_viewer.swipe_right_is_next, and the Swipe chip flips it). Drag the chart slowly with one finger to move the same chart back and forward in time, and pinch with two fingers to zoom (chart_viewer.chart_touch_pan). To change the chart, flick it fast: at least 80 pixels in under 0.3 seconds, and 1.5 times more sideways than up or down (chart_viewer.swipe_min_px, chart_viewer.swipe_max_ms, chart_viewer.swipe_ratio). A slow drag never changes the chart. A swipe on the top row (ticker, price and counter) always changes the chart. On the chip bar, a swipe scrolls the chips when they do not all fit, as on a phone, and changes the chart when they do. The Drag chip switches between Drag: move chart and Drag: next chart, where pinch zoom is off too, and the choice is saved on this device (chart_viewer.drag_mode_toggle). The arrows and the left and right keys work too. The chips show or hide the 10, 20, 50, 150, and 200-day averages and the volume, and the choice is saved on this device. The box in the lower right lists every scanner the stock is on, its status, and its reason. Tap it for more, or hide it with the Reasons chip (chart_viewer.reason_box). The chart loads every saved daily bar, so you can drag back to older days. It opens on the last 6 months, or 3 months on a phone (chart_viewer.range_months). The newest candle sits just left of the Why box, in the same spot on every chart, so the box never covers it. A range you dragged to stays when you turn the device or switch full screen. A new chart or a range chip goes back to the first view. The 3M, 6M, 1Y and All chips change how much shows (chart_viewer.range_chips). The next chart is loaded early so it opens fast. It uses the saved daily bars only. Nothing new is downloaded. Turn the page off with feature.chart_viewer."),
        ("Technical and Fundamental", "The menu splits the screeners into two headings. Technical is price and volume: VCP, Box breakout, Flag breakout, Qullamaggie breakout, Marios breakout, Episodic Pivot, Gap Up, 52-week, 52-week breakouts, High volume, Pullbacks, Trends, and Liquid stocks. Fundamental is the company's numbers and score: CANSLIM, Leaders, Growth, Quality, Dividend, Dividend fundamentals, Stock scorecard, and Top stocks. Market-wide pages (Gainers and losers, Breadth, Sector performance, Heatmaps) are under Market. Today, Buy setups, the watchlist, the Chart Viewer, earnings, sentiment, macro, and help stay where they were. The Chart Viewer has the same split as a Technical | Fundamental switch. Move a screener to the other heading with scanner_groups in config.json. Turn off only the Chart Viewer switch with chart_viewer.group_toggle: the menu stays split and the Chart Viewer has one All list. Turn the split off with feature.split_tech_fund to get the one combined menu and one All list back."),
        ("Light mode", "The desk starts dark. Pick Dark, Light, or Match device under Theme at the top of the menu (open the menu on a phone). Match device follows the phone or computer setting. The choice is saved on this device only, and the page reloads to switch. Every page, the Chart Viewer, and the charts switch colours. On white, the green, orange, and red labels are darker, and text keeps a contrast of at least 4.5 to 1. Change the starting theme with light_mode.default_theme in config.json (dark, light, or auto). Hide Match device with light_mode.match_device_option. Hide the toggle with feature.light_mode, which keeps every page dark."),
        ("Leaders", "Leaders puts a VCP that is ready or broken out today together with a strict CANSLIM qualify. One row per stock."),
        ("Your list", "Edit input/holdings.csv and input/my_watchlist.csv to change the portfolio and the watchlist. Example rows are marked example=yes. Replace them with your own shares and cost. The desk still will not place a trade."),
        ("Alerts", "The alerts page lists score and label changes since the last run. It does not send a phone alert, an email, or a message."),
        ("Updates log", "OK means the source answered. PARTIAL means a column is blank on every row. CACHED means this run failed and an older copy was used. MISSING means there is no copy at all. A blank cell is missing data. It is not a zero."),
        ("Page descriptions", "Each page starts with a short box that says what the page does. Turn all of them off with feature.page_descriptions in config.json."),
        ("Switches", "Every page has an on/off switch in config.json under features. The index lists have switches under indexes. Turning a page off keeps the file headers so the site does not break."),
    ]


def settings_rows(cfg):
    rows = [{"setting": "feature." + k, "value": v} for k, v in cfg["features"].items()]
    buy_cfg = cfg.get("buy_setups") or {}
    rows.append({"setting": "buy_setups.market_filter", "value": buy_cfg.get("market_filter", True)})
    rows.append({"setting": "buy_setups.chart_setups_only", "value": buy_cfg.get("chart_setups_only", True)})
    rows.append({"setting": "buy_setups.full_rules_at_coverage_pct", "value": buy_cfg.get("full_rules_at_coverage_pct", 80)})
    back_cfg = cfg.get("fundamentals_backfill") or {}
    rows.append({"setting": "fundamentals_backfill.rebuild_pages_after_run", "value": back_cfg.get("rebuild_pages_after_run", True)})
    market_cfg = cfg.get("market") or {}
    rows.append({"setting": "market.require_both_uptrends", "value": market_cfg.get("require_both_uptrends", False)})
    bench_cfg = cfg.get("benchmark") or {}
    rows.append({"setting": "benchmark.bse_only_uses_sensex", "value": bench_cfg.get("bse_only_uses_sensex", True)})
    rot_bench = (cfg.get("sector_rotation") or {}).get("benchmark", "^NSEI")
    rows.append({"setting": "sector_rotation.benchmark", "value": rot_bench})
    ep_cfg = cfg.get("episodic_pivot") or {}
    for key, value in ep_cfg.items():
        if str(key).startswith("nick_"):
            rows.append({"setting": "episodic_pivot." + key, "value": value})
    for key, value in (cfg.get("gap_up") or {}).items():
        if not str(key).startswith("_"):
            rows.append({"setting": "gap_up." + key, "value": value})
    for key, value in (cfg.get("scanner_groups") or {}).items():
        if not str(key).startswith("_"):
            rows.append({"setting": "scanner_groups." + key, "value": value})
    lm_cfg = cfg.get("light_mode") or {}
    rows.append({"setting": "light_mode.default_theme", "value": lm_cfg.get("default_theme", "dark")})
    rows.append({"setting": "light_mode.match_device_option", "value": lm_cfg.get("match_device_option", True)})
    for key, value in (cfg.get("chart_viewer") or {}).items():
        if not str(key).startswith("_"):
            rows.append({"setting": "chart_viewer." + key, "value": value})
    for k, v in (cfg.get("indexes") or {}).items():
        rows.append({"setting": "index." + k, "value": v})
    for k, v in cfg.get("scoring", {}).items():
        rows.append({"setting": "scoring." + k, "value": v})
    rot = cfg.get("sector_rotation") or {}
    for tf, spec in (rot.get("windows") or {}).items():
        if isinstance(spec, dict):
            for key, value in spec.items():
                rows.append({"setting": "sector_rotation.windows.%s.%s" % (tf, key), "value": value})
    for key, value in (rot.get("weights") or {}).items():
        rows.append({"setting": "sector_rotation.weight." + str(key), "value": value})
    for key in ("near_high_pct", "w52_bars", "tail_keep", "macro_lookback", "yield_flat_band"):
        if key in rot:
            rows.append({"setting": "sector_rotation." + key, "value": rot[key]})
    backfill = cfg.get("fundamentals_backfill") or {}
    for key in (
        "statements_per_run", "shareholding_per_run", "pause_seconds", "max_minutes",
        "statements_refresh_days", "shareholding_refresh_days",
    ):
        if key in backfill:
            rows.append({"setting": "fundamentals_backfill." + key, "value": backfill[key]})
    rows.append({"setting": "label", "value": DISCLAIMER})
    return pd.DataFrame(rows)
