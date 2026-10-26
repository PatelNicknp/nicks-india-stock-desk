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
    value, name, outcome = bf.first_good("shareholding", [("NSE shareholding", ok), ("Screener shareholding", later)], book)
    assert outcome == "ok"
    assert name == "NSE shareholding"
    assert value["promoter_pct"] == 10
    assert calls == ["ok"]


def test_screener_reads_the_table_not_the_tab_button():
    html = """
    <button data-tab-id="quarterly-shp" class="active">Quarterly</button>
    <button data-tab-id="yearly-shp">Yearly</button>
    <div id="quarterly-shp">
      <table>
        <tr><th class="text"></th><th>Jun 2026</th><th>Sep 2026</th></tr>
        <tr><td class="text"><button>Promoters&nbsp;<span class="blue-icon">+</span></button></td><td>74.00%</td><td>74.99%</td></tr>
        <tr><td class="text"><button>FIIs&nbsp;<span>+</span></button></td><td>0.50%</td><td>0.40%</td></tr>
        <tr><td class="text"><button>DIIs&nbsp;<span>+</span></button></td><td>8.00%</td><td>8.99%</td></tr>
        <tr><td class="text"><button>Public&nbsp;<span>+</span></button></td><td>17.50%</td><td>15.62%</td></tr>
      </table>
    </div>
    <div id="yearly-shp"><table><tr><td class="text">Promoters</td><td>1%</td></tr></table></div>
    """
    row = bf.parse_screener_shareholding(html)
    assert row["promoter_pct"] == 74.99
    assert row["fii_pct"] == 0.40
    assert row["dii_pct"] == 8.99
    assert row["public_pct"] == 15.62
    assert row["as_of"] == "2026-09-01"
    assert row["source"] == "Screener"


def test_empty_filing_does_not_retire_the_source():
    book = __import__("fallback").SourceBook(give_up_after=3)

    def empty():
        return None

    streak = 0
    for _ in range(6):
        value, name, outcome = bf.first_good(
            "shareholding",
            [("NSE shareholding", empty), ("Screener shareholding", empty)],
            book,
        )
        assert value is None and name == "" and outcome == "empty"
        streak = bf.next_streak(streak, outcome)
    assert streak == 0
    assert "NSE shareholding" not in book.dead
    assert "Screener shareholding" not in book.dead


def test_source_errors_retire_the_source_after_three():
    book = __import__("fallback").SourceBook(give_up_after=3)
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("HTTP 403")

    outcomes = []
    for _ in range(6):
        value, _name, outcome = bf.first_good("shareholding", [("BSE shareholding", boom)], book)
        assert value is None
        outcomes.append(outcome)
    # Three real errors, then the blocked site is not asked again this run.
    assert outcomes == ["down"] * 3 + ["retired"] * 3
    assert len(calls) == 3
    assert "BSE shareholding" in book.dead


def test_empty_filing_waits_behind_names_that_have_not_been_tried():
    info = pd.DataFrame(columns=["ticker", "fetched_on"])
    annual = pd.DataFrame(columns=["ticker"])
    holders = pd.DataFrame(columns=["ticker"])
    earn = pd.DataFrame(columns=["ticker", "earnings_dt"])
    cursor = {"shareholding_empty_on": {"LIQMISS": "2026-10-25"}}
    queue = bf.build_queue(
        _universe(), _scores(), info, annual, holders, earn, cursor, "2026-10-25",
        {"statements": 90, "shareholding": 90}, "shareholding",
    )
    due = [r["ticker"] for r in bf.take_batch(queue, 10)]
    assert due[0] == "LIQNEW"
    assert "LIQMISS" in due
    assert due.index("LIQMISS") > due.index("NSEMISS")


def test_switch_off_does_not_download():
    stats = bf.run_batch(os.path.dirname(__file__), {"features": {"fundamentals_backfill": False}})
    assert stats["enabled"] is False
    assert stats["statements_ok"] == 0


class _Resp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200
        self.headers = {"content-type": "text/html"}


_SHP_HTML = """
<div id="quarterly-shp"><table>
<tr><th class="text"></th><th>Jun 2026</th><th>Sep 2026</th></tr>
<tr><td class="text">Promoters&nbsp;</td><td>70.00%</td><td>73.06%</td></tr>
<tr><td class="text">Public&nbsp;</td><td>30.00%</td><td>26.94%</td></tr>
</table></div><div id="yearly-shp"></div>
"""


def _fake_screener(monkeypatch, pages):
    """pages maps a URL to html. Any other URL is a 404, like Screener."""
    import netutil
    calls = []

    def fake_get(session, url, headers, timeout, **kw):
        calls.append(url)
        if url in pages:
            return _Resp(pages[url])
        raise netutil.PermanentError("HTTP 404 for %s" % url)

    monkeypatch.setattr(bf.netutil, "http_get", fake_get)
    monkeypatch.setattr(bf.fallback, "robots_allows", lambda url, timeout=12: True)
    return calls


def test_bse_only_screener_uses_the_scrip_code():
    rec = {"ticker": "AAIL", "exchange": "BSE", "in_bse_only": "yes", "nse_symbol": "", "bse_symbol": "AAIL"}
    assert bf.screener_slugs(rec, "530621") == ["530621"]
    assert bf.screener_slugs(rec, "") == ["AAIL"]
    nse = {"ticker": "GKB", "exchange": "Both", "in_bse_only": "no", "nse_symbol": "GKB", "bse_symbol": "GKB"}
    assert bf.screener_slugs(nse, "533212") == ["GKB", "533212"]


def test_bse_only_name_saves_from_screener_by_code(monkeypatch):
    calls = _fake_screener(monkeypatch, {"https://www.screener.in/company/530621/consolidated/": _SHP_HTML})
    monkeypatch.setattr(bf, "fetch_bse_shareholding", lambda code, cfg: (_ for _ in ()).throw(RuntimeError("HTTP 403")))
    rec = {"ticker": "AAIL", "exchange": "BSE", "in_bse_only": "yes", "nse_symbol": "", "bse_symbol": "AAIL", "isin": "INE864E01021"}
    book = __import__("fallback").SourceBook(give_up_after=3)
    row, source, outcome = bf.fetch_shareholding(rec, {}, {"AAIL": "530621"}, book)
    assert outcome == "ok"
    assert source == "Screener shareholding"
    assert row["ticker"] == "AAIL"
    assert row["promoter_pct"] == 73.06
    assert all("/company/AAIL/" not in u for u in calls)


def test_screener_404_is_not_found_and_does_not_retire_screener(monkeypatch):
    calls = _fake_screener(monkeypatch, {})
    assert bf.fetch_screener_shareholding(["NOPAGE"], {}) is None
    # A 404 on the consolidated page skips the standalone page for that slug.
    assert calls == ["https://www.screener.in/company/NOPAGE/consolidated/"]
    book = __import__("fallback").SourceBook(give_up_after=3)
    for _ in range(5):
        _v, _n, outcome = bf.first_good(
            "shareholding", [("Screener shareholding", lambda: bf.fetch_screener_shareholding(["NOPAGE"], {}))], book,
        )
        assert outcome == "empty"
    assert "Screener shareholding" not in book.dead


def test_screener_block_still_raises(monkeypatch):
    import netutil

    def blocked(session, url, headers, timeout, **kw):
        raise netutil.PermanentError("HTTP 403 for %s" % url)

    monkeypatch.setattr(bf.netutil, "http_get", blocked)
    monkeypatch.setattr(bf.fallback, "robots_allows", lambda url, timeout=12: True)
    try:
        bf.fetch_screener_shareholding(["AAIL"], {})
    except netutil.PermanentError as exc:
        assert "403" in str(exc)
    else:
        raise AssertionError("a 403 should raise")


def test_retired_sources_are_not_a_failure_of_the_name():
    book = __import__("fallback").SourceBook(give_up_after=1)
    book.hit("x", "Screener shareholding", "FAILED", "HTTP 429")
    value, _name, outcome = bf.first_good("shareholding", [("Screener shareholding", lambda: {"a": 1})], book)
    assert value is None and outcome == "retired"


def test_failed_name_gets_a_growing_retry_date():
    cursor = {}
    assert bf._mark_shareholding_failed(cursor, "AAIL", "2026-10-26", "no source") == "2026-10-29"
    assert cursor["shareholding_retry_after"]["AAIL"] == "2026-10-29"
    assert cursor["shareholding_failures"]["AAIL"]["count"] == 1
    assert bf._mark_shareholding_failed(cursor, "AAIL", "2026-10-29") == "2026-11-05"
    assert bf._mark_shareholding_failed(cursor, "AAIL", "2026-11-05") == "2026-11-19"
    assert bf._mark_shareholding_failed(cursor, "AAIL", "2026-11-19") == "2026-12-19"
    assert bf._mark_shareholding_failed(cursor, "AAIL", "2026-12-19") == "2027-01-18"
    bf._clear_shareholding_failed(cursor, "AAIL")
    assert "AAIL" not in cursor["shareholding_failures"]


def test_failed_name_is_skipped_until_its_retry_date():
    info = pd.DataFrame(columns=["ticker", "fetched_on"])
    annual = pd.DataFrame(columns=["ticker"])
    cursor = {}
    bf._mark_shareholding_failed(cursor, "BSEMISS", "2026-10-25")
    args = (_universe(), _scores(), info, annual, pd.DataFrame(columns=["ticker"]),
            pd.DataFrame(columns=["ticker", "earnings_dt"]), cursor)
    for day, expect in (("2026-10-26", False), ("2026-10-27", False), ("2026-10-28", True)):
        queue = bf.build_queue(*args, day, {"statements": 90, "shareholding": 90}, "shareholding")
        due = [r["ticker"] for r in bf.take_batch(queue, 10)]
        assert ("BSEMISS" in due) is expect, day


def test_fund_units_are_not_queued_for_shareholding():
    uni = pd.concat([_universe(), pd.DataFrame([
        {"ticker": "11DPD", "exchange": "BSE", "in_bse_only": "yes", "nse_symbol": "", "bse_symbol": "11DPD", "isin": "INF204KB13U9"},
    ])], ignore_index=True)
    info = pd.DataFrame(columns=["ticker", "fetched_on"])
    annual = pd.DataFrame(columns=["ticker"])
    queue = bf.build_queue(uni, _scores(), info, annual, pd.DataFrame(columns=["ticker"]),
                           pd.DataFrame(columns=["ticker", "earnings_dt"]), {}, "2026-10-25",
                           {"statements": 90, "shareholding": 90}, "shareholding")
    due = [r["ticker"] for r in bf.take_batch(queue, 10)]
    assert "11DPD" not in due
    assert "BSEMISS" in due


def test_a_run_of_hard_names_does_not_stop_shareholding():
    canary_calls = []

    def canary():
        canary_calls.append(1)
        return True

    guard = bf.OutageGuard(canary=canary, first_names=25, every=10)
    assert guard.record("ok") is False
    for _ in range(60):
        assert guard.record("down") is False
    assert len(canary_calls) == 6


def test_first_names_all_failing_is_an_outage():
    guard = bf.OutageGuard(canary=lambda: True, first_names=25, every=10)
    stops = [guard.record("down") for _ in range(25)]
    assert stops[:24] == [False] * 24
    assert stops[24] is True
    assert "first 25" in guard.reason


def test_big_stocks_failing_too_is_an_outage():
    guard = bf.OutageGuard(canary=lambda: False, first_names=25, every=10)
    assert guard.record("empty") is False
    stops = [guard.record("down") for _ in range(10)]
    assert stops[-1] is True and not any(stops[:-1])
    assert "big stocks" in guard.reason


def test_run_batch_moves_past_failed_names(tmp_path, monkeypatch):
    root = tmp_path
    (root / "data").mkdir()
    (root / "cache").mkdir()
    rows = [{"ticker": "HARD%02d" % i, "exchange": "BSE", "in_bse_only": "yes", "nse_symbol": "",
             "bse_symbol": "HARD%02d" % i, "isin": "INE%07d" % i} for i in range(12)]
    rows.append({"ticker": "ZEASY", "exchange": "BSE", "in_bse_only": "yes", "nse_symbol": "",
                 "bse_symbol": "ZEASY", "isin": "INE9999999"})
    pd.DataFrame(rows).to_csv(root / "data" / "universe.csv", index=False)
    pd.DataFrame([{"ticker": "ZEASY", "liquid": "no"}]).to_csv(root / "data" / "scores.csv", index=False)

    def fake_fetch(rec, cfg, codes, book):
        if rec["ticker"] == "ZEASY":
            return {"ticker": "ZEASY", "promoter_pct": 50.0, "public_pct": 50.0, "source": "Screener"}, "Screener shareholding", "ok"
        return None, "", "down"

    monkeypatch.setattr(bf, "fetch_shareholding", fake_fetch)
    monkeypatch.setattr(bf, "fetch_statements", lambda rec, cfg, book: (None, ""))
    monkeypatch.setattr(bf, "_refresh_company_lines", lambda *a, **k: 0)
    monkeypatch.setattr(bf, "make_canary", lambda *a, **k: (lambda: True))
    monkeypatch.setattr(bf, "SHAREHOLDING_MIN_GAP", 0.0)
    monkeypatch.setattr(bf.time, "sleep", lambda s: None)
    monkeypatch.setattr(bf, "today_ist", lambda: "2026-10-26")
    cfg = {"features": {"fundamentals_backfill": True},
           "fundamentals_backfill": {"shareholding_per_run": 50, "statements_per_run": 1, "pause_seconds": 0}}
    stats = bf.run_batch(str(root), cfg)
    assert stats["shareholding_fail"] == 12
    assert stats["shareholding_ok"] == 1
    cursor = bf.load_cursor(str(root / "cache"))
    assert cursor["shareholding_retry_after"]["HARD00"] == "2026-10-29"
    assert cursor["shareholding_failures"]["HARD11"]["count"] == 1
    holders = pd.read_csv(root / "cache" / "holders.csv")
    assert "ZEASY" in set(holders["ticker"])


if __name__ == "__main__":
    test_missing_liquid_comes_before_other_bands_and_refreshes()
    test_earnings_date_makes_a_fresh_statement_due()
    test_shareholding_refreshes_when_the_quarter_is_old()
    test_retry_tomorrow_skips_a_failed_name_today()
    test_bse_only_uses_the_bo_symbol_first()
    test_screener_table_reads_the_latest_quarter()
    test_first_good_stops_after_the_first_answer()
    test_screener_reads_the_table_not_the_tab_button()
    test_empty_filing_does_not_retire_the_source()
    test_source_errors_retire_the_source_after_three()
    test_empty_filing_waits_behind_names_that_have_not_been_tried()
    test_switch_off_does_not_download()
    print("backfill ok")
