"""Sector leaders: rotation rank when it exists, otherwise the middle RS."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sector_leaders as leaders


def _scores():
    rows = []
    for ticker, sector, rs, liquid, dist, price in (
        ("AAA", "Information Technology", 90, "yes", -5.0, 100),
        ("BBB", "Information Technology", 80, "yes", -12.5, 90),
        ("CCC", "Information Technology", 70, "yes", 0, 80),
        ("DDD", "Information Technology", 99, "no", -1, 70),
        ("EEE", "Information Technology", None, "yes", -3, 60),
        ("FFF", "Financials", 88, "yes", -20, 200),
        ("GGG", "Financials", 77, "yes", -8, 150),
        ("HHH", "Financials", 66, "yes", -4, 120),
        ("III", "Health Care", 40, "yes", -30, 50),
        ("JJJ", "Health Care", 30, "yes", -15, 40),
        ("KKK", "Health Care", 20, "yes", -10, 30),
    ):
        rows.append({
            "ticker": ticker, "company": ticker + " Co", "sector": sector,
            "price": price, "dist_52w_high_pct": dist, "liquid": liquid, "rs": rs,
        })
    return pd.DataFrame(rows)


def _ratings():
    frame = _scores()[["ticker", "rs"]]
    return frame


def _rotation():
    return pd.DataFrame([
        {"name": "IT", "sector": "Information Technology", "score": 40, "quadrant_w": "Leading", "benchmark": "^NSEI", "rank": 2},
        {"name": "Pharma", "sector": "Health Care", "score": 50, "quadrant_w": "Weakening", "benchmark": "^NSEI", "rank": 1},
        {"name": "PSU Bank", "sector": "Financials", "score": 36, "quadrant_w": "Leading", "benchmark": "^NSEI", "rank": 3},
        {"name": "Bank", "sector": "Financials", "score": 20, "quadrant_w": "Weakening", "benchmark": "^NSEI", "rank": 4},
        {"name": "IT sensex", "sector": "Information Technology", "score": 99, "quadrant_w": "Leading", "benchmark": "^BSESN", "rank": 1},
    ])


def test_leading_sectors_and_top_three_by_rs():
    out = leaders.build(_scores(), _ratings(), _rotation(), buy=pd.DataFrame({
        "ticker": ["AAA"], "setup_sources": ["VCP+CANSLIM"], "best_status": ["READY"],
    }))
    assert list(out["sector_group"].unique()) == ["Information Technology", "Financials"]
    it = out[out.sector_group == "Information Technology"]
    assert list(it["ticker"]) == ["AAA", "BBB", "CCC"]
    assert list(it["stock_rank"]) == [1, 2, 3]
    assert list(it["rs"]) == [90, 80, 70]
    assert it["sector_name"].iloc[0] == "IT"
    assert it["quadrant"].iloc[0] == "Leading"
    assert it["strength_source"].iloc[0] == "sector index"
    assert "Nifty 50" in it["blurb"].iloc[0]
    assert "\u2014" not in it["blurb"].iloc[0]
    # A blank RS is left out, and a quieter name does not jump ahead of a liquid one.
    assert "DDD" not in set(out["ticker"])
    assert "EEE" not in set(out["ticker"])
    assert float(it.loc[it.ticker == "BBB", "off_high_pct"].iloc[0]) == 12.5
    assert float(it.loc[it.ticker == "CCC", "off_high_pct"].iloc[0]) == 0.0
    assert it.loc[it.ticker == "AAA", "setup"].iloc[0] == "VCP and CANSLIM, ready"


def test_shared_group_is_listed_once_under_the_stronger_index():
    out = leaders.build(_scores(), _ratings(), _rotation())
    fin = out[out.sector_group == "Financials"]
    assert fin["sector_name"].iloc[0] == "Financials"
    assert fin["index_name"].iloc[0] == "PSU Bank"
    assert len(fin["sector_rank"].unique()) == 1
    assert "Bank" not in set(out["sector_name"])


def test_sensex_rotation_does_not_replace_the_nifty_rank():
    out = leaders.build(_scores(), _ratings(), _rotation())
    assert "IT sensex" not in set(out["sector_name"])
    assert out[out.sector_group == "Information Technology"]["strength"].iloc[0] == 40


def test_no_leading_sector_uses_the_highest_scores():
    rot = _rotation()
    rot["quadrant_w"] = "Lagging"
    out = leaders.build(_scores(), _ratings(), rot)
    assert "No sector index is Leading" in out["blurb"].iloc[0]
    assert out["sector_rank"].min() == 1
    # Pharma scores 50 and is first even though it is not Leading.
    assert out.loc[out.sector_rank == 1, "sector_name"].iloc[0] == "Pharma"


def test_median_rs_when_rotation_is_missing():
    out = leaders.build(_scores(), _ratings(), rotation=None)
    assert out["strength_source"].iloc[0] == "median RS"
    assert "middle RS" in out["blurb"].iloc[0]
    # IT median of 90, 80, 70, 99 is 85. Financials 88, 77, 66 is 77. Health care is 30.
    assert list(out["sector_group"].unique()) == ["Information Technology", "Financials"]
    assert "Health Care" not in set(out["sector_group"])
    assert "\u2014" not in " ".join(out["blurb"].astype(str))


def test_median_below_70_is_explained():
    scores = _scores()
    scores["rs"] = 40
    ratings = scores[["ticker", "rs"]]
    out = leaders.build(scores, ratings, rotation=None)
    assert "No group has a middle RS of 70" in out["blurb"].iloc[0]
    assert out["sector_rank"].max() <= 4


def test_scanner_tag_is_used_when_there_is_no_buy_setup():
    scanners = [("VCP", pd.DataFrame({"ticker": ["BBB"], "status": ["WATCHING"]}))]
    out = leaders.build(_scores(), _ratings(), _rotation(), scanners=scanners)
    it = out[out.ticker == "BBB"].iloc[0]
    assert it["setup"] == "VCP, watching"
    assert out.loc[out.ticker == "CCC", "setup"].iloc[0] == "No setup"


def test_switch_and_help_are_plain():
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = json.load(open(os.path.join(root, "config.json"), encoding="utf-8"))
    assert cfg["features"]["sector_leaders"] is True
    import tables
    text = dict(tables.help_rows())["Sector leaders"]
    assert "feature.sector_leaders" in text
    assert "top 3" in text or "three" in text
    assert "Nifty 50" in text
    assert "\u2014" not in text
    pages = open(os.path.join(root, "site", "js", "pages.js"), encoding="utf-8").read()
    assert "Sector leaders" in pages
    assert 'featureOn("feature.sector_leaders")' in pages
    assert "\u2014" not in pages[pages.index("function renderLeaders"):pages.index("function renderRotation")]
