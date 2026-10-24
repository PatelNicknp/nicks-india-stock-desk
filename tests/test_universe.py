"""Nifty 50, Next 50, and Midcap 150 join without duplicate rows."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import stock_desk as desk


def _frame(rows, flag):
    return desk._blank_flags(pd.DataFrame(rows), flag)


def test_membership_order_and_dedupe():
    n50 = _frame([
        {"ticker": "RELIANCE", "company": "Reliance", "sector": "Energy"},
        {"ticker": "HDFCBANK", "company": "HDFC Bank", "sector": "Financials"},
    ], "in_nifty50")
    nxt = _frame([
        {"ticker": "RELIANCE", "company": "Reliance Industries", "sector": "Oil"},
        {"ticker": "ADANIGREEN", "company": "Adani Green", "sector": "Utilities"},
    ], "in_next50")
    mid = _frame([
        {"ticker": "ADANIGREEN", "company": "Adani Green Energy", "sector": "Utilities"},
        {"ticker": "POLYCAB", "company": "Polycab", "sector": "Industrials"},
    ], "in_midcap150")
    out = desk.combine_indexes([n50, nxt, mid], ["TCS"], [], {"nifty50": True, "next50": True, "midcap150": True})
    assert list(out["ticker"]).count("RELIANCE") == 1
    assert list(out["ticker"]).count("ADANIGREEN") == 1
    rel = out[out.ticker == "RELIANCE"].iloc[0]
    assert rel["index_membership"] == "Nifty 50 / Next 50"
    assert rel["sector"] == "Energy"
    green = out[out.ticker == "ADANIGREEN"].iloc[0]
    assert green["index_membership"] == "Next 50 / Midcap 150"
    assert green["in_nifty50"] == "no"
    poly = out[out.ticker == "POLYCAB"].iloc[0]
    assert poly["index_membership"] == "Midcap 150"
    tcs = out[out.ticker == "TCS"].iloc[0]
    assert tcs["index_membership"] == "Focus"
    assert len(out) == 5


def test_switch_drops_only_that_list():
    n50 = _frame([{"ticker": "HDFCBANK", "company": "HDFC Bank", "sector": "Financials"}], "in_nifty50")
    nxt = _frame([
        {"ticker": "HDFCBANK", "company": "HDFC Bank", "sector": "Financials"},
        {"ticker": "ADANIGREEN", "company": "Adani Green", "sector": "Utilities"},
    ], "in_next50")
    mid = _frame([{"ticker": "POLYCAB", "company": "Polycab", "sector": "Industrials"}], "in_midcap150")
    off = desk.combine_indexes([n50, nxt, mid], [], [], {"nifty50": True, "next50": False, "midcap150": False})
    assert set(off["ticker"]) == {"HDFCBANK"}
    assert off.iloc[0]["index_membership"] == "Nifty 50 / Next 50"
    only_mid = desk.combine_indexes([n50, nxt, mid], [], [], {"nifty50": False, "next50": False, "midcap150": True})
    assert set(only_mid["ticker"]) == {"POLYCAB"}
    held = desk.combine_indexes([n50, nxt, mid], ["ADANIGREEN"], [], {"nifty50": False, "next50": False, "midcap150": False})
    assert set(held["ticker"]) == {"ADANIGREEN"}
    assert held.iloc[0]["index_membership"] == "Next 50"


def test_wiki_tables_for_nifty_lists():
    extra = ["T%02d" % i for i in range(20)]
    nifty = pd.DataFrame({
        "Symbol": ["M&M", "RELIANCE", "BAD TICKER", "BAJAJ-AUTO"] + extra,
        "Company Name": ["Mahindra", "Reliance [1]", "Nope", "Bajaj Auto"] + extra,
        "Industry": ["Technology"] * (4 + len(extra)),
    })
    tiny = pd.DataFrame({"Ticker": ["A"], "Company": ["x"], "Industry": ["Technology"]})
    out = desk.wiki_constituents([tiny, nifty], "in_nifty50")
    assert {"M&M", "RELIANCE", "BAJAJ-AUTO"} <= set(out["ticker"])
    assert "BAD TICKER" not in set(out["ticker"])
    assert (out["in_nifty50"] == "yes").all()
    assert (out["in_next50"] == "no").all()
    assert (out["in_midcap150"] == "no").all()
    assert out.loc[out.ticker == "RELIANCE", "company"].iloc[0] == "Reliance"
    assert (out["sector"] == "Information Technology").all()


def test_switches_default_on():
    assert desk.index_switches({}) == {"nifty50": True, "next50": True, "midcap150": True}
    assert desk.index_switches({"indexes": {"next50": False}})["next50"] is False
    assert desk.membership_label("yes", "yes", "yes") == "Nifty 50 / Next 50 / Midcap 150"
    assert desk.membership_label("no", "no", "no") == "Focus"


if __name__ == "__main__":
    test_membership_order_and_dedupe()
    test_switch_drops_only_that_list()
    test_wiki_tables_for_nifty_lists()
    test_switches_default_on()
    print("universe ok")
