"""Cursor order for the financials and shareholding backfill. No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import fundamentals_backfill as bf


def _universe():
    return pd.DataFrame([
        {"ticker": "LIQMISS", "exchange": "NSE", "in_bse_only": "no", "nse_symbol": "LIQMISS", "bse_symbol": "LIQMISS"},
        {"ticker": "LIQOLD", "exchange": "NSE", "in_bse_only": "no", "nse_symbol": "LIQOLD", "bse_symbol": "LIQOLD"},
        {"ticker": "NSEMISS", "exchange": "NSE", "in_bse_only": "no", "nse_symbol": "NSEMISS", "bse_symbol": ""},
        {"ticker": "BSEMISS", "exchange": "BSE", "in_bse_only": "yes", "nse_symbol": "", "bse_symbol": "BSEMISS"},
        {"ticker": "LIQNEW", "exchange": "Both", "in_bse_only": "no", "nse_symbol": "LIQNEW", "bse_symbol": "LIQNEW"},
    ])


def _scores():
    return pd.DataFrame([
        {"ticker": "LIQMISS", "liquid": "yes"},
        {"ticker": "LIQOLD", "liquid": "yes"},
        {"ticker": "LIQNEW", "liquid": "yes"},
        {"ticker": "NSEMISS", "liquid": "no"},
        {"ticker": "BSEMISS", "liquid": "no"},
    ])


def test_missing_liquid_comes_before_other_bands_and_refreshes():
    info = pd.DataFrame([
        {"ticker": "LIQOLD", "fetched_on": "2020-01-01", "company": "Old"},
        {"ticker": "LIQNEW", "fetched_on": "2026-10-20", "company": "New"},
    ])
    annual = pd.DataFrame({"ticker": ["LIQOLD", "LIQNEW"]})
    holders = pd.DataFrame(columns=["ticker"])
    earn = pd.DataFrame(columns=["ticker", "earnings_dt"])
    queue = bf.build_queue(_universe(), _scores(), info, annual, holders, earn, {}, "2026-10-25", {"statements": 90, "shareholding": 90}, "statements")
    due = [r["ticker"] for r in bf.take_batch(queue, 10)]
    assert due[:3] == ["LIQMISS", "NSEMISS", "BSEMISS"]
    assert due[3] == "LIQOLD"
    assert "LIQNEW" not in due


def test_earnings_date_makes_a_fresh_statement_due():
    assert bf.statements_due(True, "2026-10-01", ["2026-10-20"], "2026-10-25", 90) is True
    assert bf.statements_due(True, "2026-10-20", ["2026-10-01"], "2026-10-25", 90) is False
    assert bf.statements_due(False, "", [], "2026-10-25", 90) is True


def test_shareholding_refreshes_when_the_quarter_is_old():
    assert bf.shareholding_due(True, "2026-10-20", "2026-06-01", "2026-10-25", 90) is True
    assert bf.shareholding_due(True, "2026-10-20", "2026-09-30", "2026-10-25", 90) is False


def test_retry_tomorrow_skips_a_failed_name_today():
    info = pd.DataFrame(columns=["ticker", "fetched_on"])
    annual = pd.DataFrame(columns=["ticker"])
    cursor = {"statements_retry_after": {"LIQMISS": "2026-10-26"}}
    queue = bf.build_queue(
        _universe(), _scores(), info, annual, pd.DataFrame(columns=["ticker"]),
        pd.DataFrame(columns=["ticker", "earnings_dt"]), cursor, "2026-10-25",
        {"statements": 90, "shareholding": 90}, "statements",
    )
    due = [r["ticker"] for r in bf.take_batch(queue, 10)]
    assert "LIQMISS" not in due
    assert due[0] == "LIQNEW"


def test_bse_only_uses_the_bo_symbol_first():
    symbols = bf.statement_symbols({
        "ticker": "BSEMISS", "exchange": "BSE", "in_bse_only": "yes",
        "nse_symbol": "", "bse_symbol": "BSEMISS",
    })
    assert symbols == ["BSEMISS.BO"]
    both = bf.statement_symbols({
        "ticker": "LIQNEW", "exchange": "Both", "in_bse_only": "no",
        "nse_symbol": "LIQNEW", "bse_symbol": "LIQNEW",
    })
    assert both == ["LIQNEW.NS"]


def test_screener_table_reads_the_latest_quarter():
    html = """
    <div id="quarterly-shp">
      <table><thead><tr><th class="text"></th><th>Jun 2026</th><th>Sep 2026</th></tr></thead>
      <tbody>
        <tr><td class="text">Promoters&nbsp;</td><td>50.00%</td><td>50.48%</td></tr>
        <tr><td class="text">FIIs&nbsp;</td><td>19.21%</td><td>19.07%</td></tr>
        <tr><td class="text">DIIs&nbsp;</td><td>19.72%</td><td>19.90%</td></tr>
        <tr><td class="text">Public&nbsp;</td><td>10.84%</td><td>10.40%</td></tr>
      </tbody></table>
    </div>
    <div id="yearly-shp"><table><tr><td class="text">Promoters</td><td>1%</td></tr></table></div>
    """
    row = bf.parse_screener_shareholding(html)
    assert row["promoter_pct"] == 50.48
    assert row["fii_pct"] == 19.07
    assert row["fii_chg"] == round(19.07 - 19.21, 2)
    assert row["dii_pct"] == 19.90
    assert row["public_pct"] == 10.40
    assert row["as_of"] == "2026-09-01"
    assert row["source"] == "Screener"


def test_first_good_stops_after_the_first_answer():
    calls = []

    def ok():
        calls.append("ok")
        return {"promoter_pct": 10}

    def later():
        calls.append("later")
        return {"promoter_pct": 99}

    book = __import__("fallback").SourceBook()
    value, name = bf.first_good("shareholding", [("NSE shareholding", ok), ("Screener shareholding", later)], book)
    assert name == "NSE shareholding"
    assert value["promoter_pct"] == 10
    assert calls == ["ok"]


def test_switch_off_does_not_download():
    stats = bf.run_batch(os.path.dirname(__file__), {"features": {"fundamentals_backfill": False}})
    assert stats["enabled"] is False
    assert stats["statements_ok"] == 0


if __name__ == "__main__":
    test_missing_liquid_comes_before_other_bands_and_refreshes()
    test_earnings_date_makes_a_fresh_statement_due()
    test_shareholding_refreshes_when_the_quarter_is_old()
    test_retry_tomorrow_skips_a_failed_name_today()
    test_bse_only_uses_the_bo_symbol_first()
    test_screener_table_reads_the_latest_quarter()
    test_first_good_stops_after_the_first_answer()
    test_switch_off_does_not_download()
    print("backfill ok")
