"""Unit tests for official NSE/BSE rupee statement parsing. No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import exchange_financials as xf


SAMPLE_XBRL = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin"
            xmlns:xbrli="http://www.xbrl.org/2003/instance">
  <xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/NSESymbol">INFY</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-10-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="FourD"><xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/NSESymbol">INFY</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
  <xbrli:unit id="INRPerShare"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
  <in-bse-fin:DescriptionOfPresentationCurrency contextRef="OneD">INR</in-bse-fin:DescriptionOfPresentationCurrency>
  <in-bse-fin:RevenueFromOperations contextRef="OneD" unitRef="INR" decimals="-7">417640000000.00</in-bse-fin:RevenueFromOperations>
  <in-bse-fin:RevenueFromOperations contextRef="FourD" unitRef="INR" decimals="-7">1220640000000.00</in-bse-fin:RevenueFromOperations>
  <in-bse-fin:ProfitOrLossAttributableToOwnersOfParent contextRef="OneD" unitRef="INR" decimals="-7">68060000000.00</in-bse-fin:ProfitOrLossAttributableToOwnersOfParent>
  <in-bse-fin:DilutedEarningsLossPerShareFromContinuingOperations contextRef="OneD" unitRef="INRPerShare" decimals="INF">16.39</in-bse-fin:DilutedEarningsLossPerShareFromContinuingOperations>
  <in-bse-fin:PaidUpValueOfEquityShareCapital contextRef="OneD" unitRef="INR" decimals="-7">20720000000.00</in-bse-fin:PaidUpValueOfEquityShareCapital>
  <in-bse-fin:FaceValueOfEquityShareCapital contextRef="OneD" unitRef="INRPerShare">5</in-bse-fin:FaceValueOfEquityShareCapital>
  <in-bse-fin:ProfitBeforeExceptionalItemsAndTax contextRef="OneD" unitRef="INR" decimals="-7">96700000000.00</in-bse-fin:ProfitBeforeExceptionalItemsAndTax>
</xbrli:xbrl>
"""

BANK_XBRL = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin"
            xmlns:xbrli="http://www.xbrl.org/2003/instance">
  <xbrli:context id="OneD">
    <xbrli:period><xbrli:startDate>2024-10-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <in-bse-fin:DescriptionOfPresentationCurrency contextRef="OneD">INR</in-bse-fin:DescriptionOfPresentationCurrency>
  <in-bse-fin:InterestEarned contextRef="OneD" unitRef="INR">850401700000.00</in-bse-fin:InterestEarned>
  <in-bse-fin:ProfitLossForThePeriod contextRef="OneD" unitRef="INR">167000000000.00</in-bse-fin:ProfitLossForThePeriod>
  <in-bse-fin:BasicEarningsPerShareAfterExtraordinaryItems contextRef="OneD">21.5</in-bse-fin:BasicEarningsPerShareAfterExtraordinaryItems>
</xbrli:xbrl>
"""

ANNUAL_CASH_XBRL = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin"
            xmlns:xbrli="http://www.xbrl.org/2003/instance">
  <xbrli:context id="OneD">
    <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="FourD">
    <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <in-bse-fin:DateOfStartOfReportingPeriod contextRef="OneD">2024-01-01</in-bse-fin:DateOfStartOfReportingPeriod>
  <in-bse-fin:DateOfEndOfReportingPeriod contextRef="OneD">2024-03-31</in-bse-fin:DateOfEndOfReportingPeriod>
  <in-bse-fin:DateOfStartOfReportingPeriod contextRef="FourD">2023-04-01</in-bse-fin:DateOfStartOfReportingPeriod>
  <in-bse-fin:DateOfEndOfReportingPeriod contextRef="FourD">2024-03-31</in-bse-fin:DateOfEndOfReportingPeriod>
  <in-bse-fin:DescriptionOfPresentationCurrency contextRef="OneD">INR</in-bse-fin:DescriptionOfPresentationCurrency>
  <in-bse-fin:RevenueFromOperations contextRef="OneD" unitRef="INR">379230000000.00</in-bse-fin:RevenueFromOperations>
  <in-bse-fin:RevenueFromOperations contextRef="FourD" unitRef="INR">1536700000000.00</in-bse-fin:RevenueFromOperations>
  <in-bse-fin:ProfitLossForPeriod contextRef="OneD" unitRef="INR">79690000000.00</in-bse-fin:ProfitLossForPeriod>
  <in-bse-fin:ProfitLossForPeriod contextRef="FourD" unitRef="INR">262300000000.00</in-bse-fin:ProfitLossForPeriod>
  <in-bse-fin:DilutedEarningsLossPerShareFromContinuingOperations contextRef="FourD">63.4</in-bse-fin:DilutedEarningsLossPerShareFromContinuingOperations>
  <in-bse-fin:CashFlowsFromUsedInOperatingActivities contextRef="FourD" unitRef="INR">252100000000.00</in-bse-fin:CashFlowsFromUsedInOperatingActivities>
  <in-bse-fin:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities contextRef="FourD" unitRef="INR">22010000000.00</in-bse-fin:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities>
</xbrli:xbrl>
"""


def test_quarterly_xbrl_uses_the_period_not_the_year_to_date():
    parsed = xf.parse_financial_xbrl(SAMPLE_XBRL, "2024-10-01", "2024-12-31")
    assert parsed["currency"] == "INR"
    assert parsed["revenue"] == 417640000000.0
    assert parsed["net_income"] == 68060000000.0
    assert parsed["eps"] == 16.39
    assert parsed["shares"] == 4144000000.0
    assert parsed["end"] == pd.Timestamp("2024-12-31")
    row = xf.filing_row("INFY", parsed, True, "NSE", filed="16-Jan-2025 19:40")
    assert row["frame"] == "CY2024Q4"
    assert row["source"] == "NSE"
    assert row["currency"] == "INR"
    assert row["filed"] == "2025-01-16"


def test_bank_xbrl_reads_interest_earned_as_revenue():
    parsed = xf.parse_financial_xbrl(BANK_XBRL, "2024-10-01", "2024-12-31")
    assert parsed["revenue"] == 850401700000.0
    assert parsed["net_income"] == 167000000000.0
    assert parsed["eps"] == 21.5


def test_annual_xbrl_reads_operating_cash_flow_from_matching_dates():
    parsed = xf.parse_financial_xbrl(ANNUAL_CASH_XBRL, "2023-04-01", "2024-03-31")
    assert parsed["ocf"] == 252100000000.0
    assert parsed["capex"] == 22010000000.0
    assert parsed["revenue"] == 1536700000000.0
    assert parsed["net_income"] == 262300000000.0
    assert parsed["end"] == pd.Timestamp("2024-03-31")
    assert parsed["from"] == pd.Timestamp("2023-04-01")


def test_select_filings_prefers_consolidated_and_the_newest_periods():
    items = [
        {"toDate": "31-Dec-2024", "fromDate": "01-Oct-2024", "consolidated": "Non-Consolidated",
         "xbrl": "http://example/a.xml", "period": "Quarterly"},
        {"toDate": "31-Dec-2024", "fromDate": "01-Oct-2024", "consolidated": "Consolidated",
         "xbrl": "http://example/b.xml", "period": "Quarterly"},
        {"toDate": "30-Sep-2024", "fromDate": "01-Jul-2024", "consolidated": "Consolidated",
         "xbrl": "http://example/c.xml", "period": "Quarterly"},
        {"toDate": "31-Mar-2024", "fromDate": "01-Apr-2023", "consolidated": "Consolidated",
         "xbrl": "http://example/year.xml", "period": "Annual"},
    ]
    picked = xf.select_filings(items, True, 8)
    assert [row[2] for row in picked] == ["http://example/b.xml", "http://example/c.xml"]
    annual = xf.select_filings(items, False, 4)
    assert [row[2] for row in annual] == ["http://example/year.xml"]


def test_bse_table_parser_reads_inr_numbers():
    payload = {
        "Table": [
            {"toDate": "31-Dec-2024", "Revenue": "1000", "NetProfit": "200", "EPS": "5.5", "period": "Quarterly"},
            {"toDate": "31-Mar-2024", "Revenue": "4000", "NetProfit": "800", "EPS": "22", "Type": "Annual"},
        ]
    }
    q, a = xf.parse_bse_result_tables(payload, "INFY")
    assert q[0]["revenue"] == 1000
    assert q[0]["source"] == "BSE"
    assert q[0]["currency"] == "INR"
    assert a[0]["frame"] == "CY2024"
    assert a[0]["net_income"] == 800


def test_walk_xbrl_links_finds_nested_urls():
    payload = {"Table": [{"xbrl": "https://nsearchives.nseindia.com/a.xml", "other": 1}]}
    assert xf.walk_xbrl_links(payload) == ["https://nsearchives.nseindia.com/a.xml"]


def test_stale_bundle_is_treated_as_empty(monkeypatch):
    monkeypatch.setattr(xf, "nse_list_results", lambda symbol, period, cfg: [
        {"toDate": "31-Dec-2022", "fromDate": "01-Oct-2022", "consolidated": "Consolidated",
         "xbrl": "http://example/old.xml", "period": period, "filingDate": "15-Jan-2023"},
    ])
    monkeypatch.setattr(xf, "_download_xbrl", lambda url, cfg, referer: SAMPLE_XBRL)
    monkeypatch.setattr(xf.time, "sleep", lambda s: None)
    # SAMPLE_XBRL ends 2024-12-31; force an old parsed end via empty download? The parser
    # uses the XBRL dates, so override max age to 30 days to make late-2024 stale in 2026.
    cfg = {"fundamentals_backfill": {"nse_results_max_age_days": 30, "nse_xbrl_pause_seconds": 0}}
    assert xf.fetch_nse_statements("INFY", cfg) is None


def test_fresh_enough_nse_bundle_records_source_and_currency(monkeypatch):
    monkeypatch.setattr(xf, "nse_list_results", lambda symbol, period, cfg: [
        {"toDate": "31-Dec-2024", "fromDate": "01-Oct-2024", "consolidated": "Consolidated",
         "xbrl": "http://example/q.xml", "period": "Quarterly" if period == "Quarterly" else "Annual",
         "filingDate": "16-Jan-2025"},
    ] if period == "Quarterly" else [])
    monkeypatch.setattr(xf, "_download_xbrl", lambda url, cfg, referer: SAMPLE_XBRL)
    monkeypatch.setattr(xf.time, "sleep", lambda s: None)
    cfg = {"fundamentals_backfill": {"nse_results_max_age_days": 5000, "nse_xbrl_pause_seconds": 0}}
    bundle = xf.fetch_nse_statements("INFY", cfg)
    assert bundle["source"] == "NSE"
    assert bundle["currency"] == "INR"
    assert bundle["quarters"][0]["revenue"] == 417640000000.0
    assert bundle["info"]["financial_currency"] == "INR"
