"""SENSEX file parser. No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import market_sources


SAMPLE = """IndexCode,IndexID,IndexName,PreviousClose,OpenPrice,HighPrice,LowPrice,ClosePrice
1,SENSEX,BSE SENSEX,73000,73100,73500,72900,73250.5
2,BSE500,BSE 500,100,101,102,99,101
"""


def test_parse_keeps_only_sensex():
    bars = market_sources.parse_bse_index_summary(SAMPLE.encode("utf-8"), "2026-10-23")
    assert len(bars) == 1
    row = bars.iloc[0]
    assert row["ticker"] == "^BSESN"
    assert row["date"] == "2026-10-23"
    assert abs(float(row["close"]) - 73250.5) < 1e-6
    assert abs(float(row["open"]) - 73100) < 1e-6
    assert abs(float(row["high"]) - 73500) < 1e-6
    assert abs(float(row["low"]) - 72900) < 1e-6
    assert row["source"] == "BSE index file"


def test_parse_rejects_a_file_without_sensex():
    text = "IndexID,IndexName,ClosePrice\nBSE500,BSE 500,101\n"
    bars = market_sources.parse_bse_index_summary(text.encode("utf-8"), "2026-10-23")
    assert len(bars) == 0


def test_switch_off_does_not_download():
    frame = pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])
    out, logs = market_sources.update_sensex(frame, {"features": {"sensex": False}}, ["2026-10-23"])
    assert len(out) == 0
    assert logs[0][0] == "Prices (SENSEX)"
    assert "off" in logs[0][3]


if __name__ == "__main__":
    test_parse_keeps_only_sensex()
    test_parse_rejects_a_file_without_sensex()
    test_switch_off_does_not_download()
    print("sensex ok")
