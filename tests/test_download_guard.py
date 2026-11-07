"""Interrupted downloads, failed saves, restarts, and the last good cache. No network."""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import download_guard
import fundamentals_backfill as bf
import india_data
import market_sources


def _cfg():
    return {
        "features": {"sensex": False, "fundamentals_backfill": True},
        "indexes": {"bse_only": False, "sme": False},
        "rate_limit": {"bhav_pause_seconds": 0, "gap_fill_per_run": 25},
        "fundamentals_backfill": {
            "shareholding_per_run": 1,
            "statements_per_run": 0,
            "pause_seconds": 0,
            "max_minutes": 5,
        },
    }


def _bar(day, ticker, source):
    return {
        "date": day,
        "ticker": ticker,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 1000,
        "isin": "" if str(ticker).startswith("^") else "INE000000001",
        "source": source,
    }


def test_atomic_write_failure_keeps_the_old_file():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "holders.csv")
        with open(path, "w") as handle:
            handle.write("ticker,promoter_pct\nOLD,1\n")
        real = os.replace

        def broken(src, dst):
            raise OSError("disk full")

        os.replace = broken
        try:
            try:
                download_guard.atomic_write_text(path, "ticker,promoter_pct\nNEW,2\n")
                raise AssertionError("the write should have failed")
            except OSError:
                pass
            with open(path) as handle:
                assert "OLD" in handle.read()
            assert not any(name.startswith(".holders.csv.") for name in os.listdir(folder))
        finally:
            os.replace = real


def test_broken_ledger_is_kept_beside_the_cache():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "download_ledger.json")
        with open(path, "w") as handle:
            handle.write("{")
        data = download_guard.read_json(path, {"providers": {}})
        assert data == {"providers": {}}
        assert not os.path.exists(path)
        with open(path + ".bad") as handle:
            assert handle.read() == "{"


def test_lock_refuses_a_live_job_and_takes_a_dead_one():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "job.lock")
        first = download_guard.JobLock(path, stale_seconds=3600)
        first.acquire()
        second = download_guard.JobLock(path, stale_seconds=3600)
        try:
            second.acquire()
            raise AssertionError("a live lock should refuse")
        except download_guard.JobBusy:
            pass
        first.release()
        second.acquire()
        second.release()

        held = {"go": False}

        def occupy():
            lock = download_guard.JobLock(path, stale_seconds=3600)
            lock.acquire()
            held["go"] = True
            while held["go"]:
                time_sleep_short()
            lock.release()

        # A lock whose pid is gone can be taken.
        stale = download_guard.JobLock(path, stale_seconds=3600, pid_alive=lambda pid: False)
        stale.acquire()
        other = download_guard.JobLock(path, stale_seconds=3600, pid_alive=lambda pid: False)
        other.acquire()
        other.release()

        clock = {"t": 1000.0}
        old = download_guard.JobLock(path, stale_seconds=10, clock=lambda: clock["t"])
        old.acquire()
        clock["t"] = 2000.0
        newer = download_guard.JobLock(path, stale_seconds=10, clock=lambda: clock["t"])
        newer.acquire()
        newer.release()


def time_sleep_short():
    import time
    time.sleep(0.01)


def test_two_threads_cannot_hold_the_same_lock():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "job.lock")
        started = threading.Event()
        finished = threading.Event()
        errors = []

        def hold():
            lock = download_guard.JobLock(path, stale_seconds=3600)
            lock.acquire()
            started.set()
            assert finished.wait(5)
            lock.release()

        thread = threading.Thread(target=hold)
        thread.start()
        assert started.wait(5)
        try:
            download_guard.JobLock(path, stale_seconds=3600).acquire()
            errors.append("overlap")
        except download_guard.JobBusy:
            pass
        finished.set()
        thread.join(5)
        assert errors == []
        download_guard.JobLock(path, stale_seconds=3600).acquire()


def test_provider_cooldown_and_stall():
    ledger = download_guard.empty_ledger()
    now = 1_700_000_000
    for _ in range(2):
        download_guard.note_provider(ledger, "Screener", False, now, 3, 6 * 3600, "down")
    assert download_guard.provider_open(ledger, "Screener", now)
    download_guard.note_provider(ledger, "Screener", False, now, 3, 6 * 3600, "down")
    assert not download_guard.provider_open(ledger, "Screener", now)
    download_guard.note_provider(ledger, "Screener", True, now, 3, 6 * 3600)
    assert download_guard.provider_open(ledger, "Screener", now)

    for _ in range(2):
        assert download_guard.note_progress(ledger, "prices", 0, True, now, 3, 6 * 3600) == ""
    message = download_guard.note_progress(ledger, "prices", 0, True, now, 3, 6 * 3600)
    assert "person" not in message.lower() or "saved nothing" in message
    assert download_guard.blocked_reason(ledger, "prices", now)
    assert "does not fix" in message
    download_guard.note_progress(ledger, "prices", 4, True, now, 3, 6 * 3600)
    assert download_guard.blocked_reason(ledger, "prices", now) == ""


def test_unavailable_name_is_skipped_until_its_date():
    ledger = download_guard.empty_ledger()
    download_guard.note_unavailable(ledger, "zzz", "prices", "no bars", "2026-11-01", "2026-11-08")
    assert download_guard.unavailable_waiting(ledger, "ZZZ", "prices", "2026-11-07")
    assert not download_guard.unavailable_waiting(ledger, "ZZZ", "prices", "2026-11-08")
    download_guard.clear_unavailable(ledger, "zzz", "prices")
    assert not download_guard.unavailable_waiting(ledger, "ZZZ", "prices", "2026-11-07")


def test_session_status_needs_the_nse_file():
    assert download_guard.session_status(10, 0, 0) == "complete"
    assert download_guard.session_status(0, 4, 3) == "partial"
    assert download_guard.session_status(0, 0, 0) == "empty"
    assert download_guard.price_history_status(0, 100, 20) == "none"
    assert download_guard.price_history_status(5, 100, 20) == "incomplete"
    assert download_guard.price_history_status(5, 4, 20) == "ok"


def _patch_prices(nse_rows, index_rows, writes):
    def first(urls, cfg):
        return b"x", urls[0]

    def nse(content, sme=False):
        return pd.DataFrame(nse_rows)

    def index(content):
        return pd.DataFrame(index_rows)

    def bse(content, sme=False):
        return pd.DataFrame()

    real = download_guard.atomic_write_df

    def write(path, frame, compression=None):
        writes.append(os.path.basename(path))
        if writes and writes[0] == "FAIL":
            raise OSError("disk full")
        return real(path, frame, compression=compression)

    market_sources._first_bytes = first
    market_sources.parse_nse_bhav = nse
    market_sources.parse_index_close = index
    market_sources.parse_bse_bhav = bse
    market_sources.time.sleep = lambda _s: None
    download_guard.atomic_write_df = write
    india_data.KEEP_DAYS = 20


def _restore(saved):
    market_sources._first_bytes = saved["first"]
    market_sources.parse_nse_bhav = saved["nse"]
    market_sources.parse_index_close = saved["index"]
    market_sources.parse_bse_bhav = saved["bse"]
    market_sources.time.sleep = saved["sleep"]
    download_guard.atomic_write_df = saved["write"]
    india_data.KEEP_DAYS = saved["keep"]


def _saved_prices():
    return {
        "first": market_sources._first_bytes,
        "nse": market_sources.parse_nse_bhav,
        "index": market_sources.parse_index_close,
        "bse": market_sources.parse_bse_bhav,
        "sleep": market_sources.time.sleep,
        "write": download_guard.atomic_write_df,
        "keep": india_data.KEEP_DAYS,
    }


def test_failed_price_save_does_not_mark_the_day_or_replace_the_file():
    saved = _saved_prices()
    try:
        with tempfile.TemporaryDirectory() as folder:
            original = pd.DataFrame([_bar("2026-10-01", "KEEP", "NSE bhavcopy")])
            path = os.path.join(folder, "ohlcv.csv.gz")
            original.to_csv(path, index=False, compression="gzip")
            before = open(path, "rb").read()
            writes = ["FAIL"]
            _patch_prices([_bar("2026-11-06", "NEW", "NSE bhavcopy")], [], writes)
            cached = pd.read_csv(path)
            out, logs = market_sources.sync_prices([], None, _cfg(), folder, cached, "full")
            assert any("not replaced" in note for _s, _st, _l, note in logs)
            assert open(path, "rb").read() == before
            state = market_sources.load_bhav_state(folder)
            assert state["ok"] == []
            assert list(out["ticker"]) == ["KEEP"]
    finally:
        _restore(saved)


def test_a_finished_day_is_not_downloaded_again():
    saved = _saved_prices()
    calls = {"n": 0}
    try:
        with tempfile.TemporaryDirectory() as folder:
            def first(urls, cfg):
                calls["n"] += 1
                return b"x", urls[0]

            writes = []
            _patch_prices([], [], writes)
            market_sources._first_bytes = first
            day_rows = []

            def nse(content, sme=False):
                # One bar per call. The date is whatever the parser is asked to invent:
                # use a unique ticker so a second pass would show up as extra rows.
                day_rows.append(1)
                return pd.DataFrame([_bar("2026-11-0%d" % min(len(day_rows), 6), "AAA", "NSE bhavcopy")])

            market_sources.parse_nse_bhav = nse
            empty = pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])
            out, _logs = market_sources.sync_prices([], None, _cfg(), folder, empty, "full")
            first_rows = len(out)
            first_calls = calls["n"]
            assert first_rows > 0 and first_calls > 0
            state = market_sources.load_bhav_state(folder)
            assert state["ok"]
            again, _logs = market_sources.sync_prices([], None, _cfg(), folder, out, "full")
            assert calls["n"] == first_calls
            assert len(again) == first_rows
    finally:
        _restore(saved)


def test_same_bars_committed_twice_do_not_duplicate():
    with tempfile.TemporaryDirectory() as folder:
        bars = pd.DataFrame([_bar("2026-11-06", "AAA", "NSE bhavcopy")])
        state = {"ok": [], "holiday": []}
        merged, state = market_sources.commit_price_checkpoint(folder, pd.DataFrame(), bars, state, ["2026-11-06"], [])
        merged, state = market_sources.commit_price_checkpoint(folder, merged, bars, state, ["2026-11-06"], [])
        assert len(merged) == 1
        assert state["ok"] == ["2026-11-06"]


def test_partial_day_keeps_bars_and_stays_pending():
    saved = _saved_prices()
    try:
        with tempfile.TemporaryDirectory() as folder:
            _patch_prices([], [_bar("2026-11-06", "^NSEI", "NSE index")], [])
            empty = pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])
            out, _logs = market_sources.sync_prices([], None, _cfg(), folder, empty, "full")
            state = market_sources.load_bhav_state(folder)
            assert state["ok"] == []
            assert state.get("partial")
            assert "^NSEI" in set(out["ticker"].astype(str))
            on_disk = pd.read_csv(os.path.join(folder, "ohlcv.csv.gz"))
            assert "^NSEI" in set(on_disk["ticker"].astype(str))
    finally:
        _restore(saved)


def test_broken_bhav_state_does_not_touch_the_price_file():
    saved = _saved_prices()
    try:
        with tempfile.TemporaryDirectory() as folder:
            original = pd.DataFrame([_bar("2026-10-01", "KEEP", "NSE bhavcopy")])
            path = os.path.join(folder, "ohlcv.csv.gz")
            original.to_csv(path, index=False, compression="gzip")
            before = open(path, "rb").read()
            with open(os.path.join(folder, "bhav_state.json"), "w") as handle:
                handle.write("{")
            calls = {"n": 0}

            def first(urls, cfg):
                calls["n"] += 1
                return b"x", urls[0]

            _patch_prices([_bar("2026-11-06", "NEW", "NSE bhavcopy")], [], [])
            market_sources._first_bytes = first
            cached = pd.read_csv(path)
            out, logs = market_sources.sync_prices([], None, _cfg(), folder, cached, "full")
            assert calls["n"] == 0
            assert open(path, "rb").read() == before
            assert any("could not be read" in note for _s, _st, _l, note in logs)
            assert list(out["ticker"]) == ["KEEP"]
            with open(os.path.join(folder, "bhav_state.json")) as handle:
                assert handle.read() == "{"
    finally:
        _restore(saved)


def test_a_busy_price_lock_does_not_download():
    saved = _saved_prices()
    try:
        with tempfile.TemporaryDirectory() as folder:
            lock = download_guard.JobLock(os.path.join(folder, "prices.lock"), stale_seconds=3600)
            lock.acquire()
            calls = {"n": 0}

            def first(urls, cfg):
                calls["n"] += 1
                return b"x", urls[0]

            _patch_prices([], [], [])
            market_sources._first_bytes = first
            cached = pd.DataFrame([_bar("2026-10-01", "KEEP", "NSE bhavcopy")])
            out, logs = market_sources.sync_prices([], None, _cfg(), folder, cached, "full")
            assert calls["n"] == 0
            assert list(out["ticker"]) == ["KEEP"]
            assert any("already running" in note for _s, _st, _l, note in logs)
            lock.release()
    finally:
        _restore(saved)


def test_gap_fill_miss_is_not_asked_again_until_the_retry_date():
    saved = _saved_prices()
    try:
        with tempfile.TemporaryDirectory() as folder:
            market_sources.time.sleep = lambda _s: None
            calls = {"n": 0}

            def nothing(symbol, cfg=None):
                calls["n"] += 1
                return pd.DataFrame()

            market_sources._stooq_daily = nothing
            market_sources._yahoo_daily = nothing
            frame = pd.DataFrame([_bar("2026-10-%02d" % day, "^NSEI", "NSE index") for day in range(1, 31)])
            first = market_sources._gap_fill(frame, ["MISSING"], _cfg(), folder)
            assert calls["n"] == 2
            ledger = download_guard.load_ledger(folder)
            assert any(str(item.get("ticker")) == "MISSING" for item in ledger["unavailable"].values())
            market_sources._gap_fill(first["frame"], ["MISSING"], _cfg(), folder)
            assert calls["n"] == 2

            def short(symbol, cfg=None):
                calls["n"] += 1
                return pd.DataFrame([_bar("2026-10-15", "SHORT", "Stooq")])

            market_sources._stooq_daily = short
            filled = market_sources._gap_fill(frame, ["SHORT"], _cfg(), folder)
            assert "SHORT" in download_guard.load_ledger(folder)["incomplete"]["prices"]
            assert "SHORT" in set(filled["frame"]["ticker"].astype(str))
    finally:
        _restore(saved)
        # _stooq_daily and _yahoo_daily were not in _saved. Restore from the module reload is unsafe.
        # They are put back below.


def test_backfill_flush_failure_does_not_advance_and_the_next_run_resumes():
    with tempfile.TemporaryDirectory() as folder:
        data = os.path.join(folder, "data")
        cache = os.path.join(folder, "cache")
        os.makedirs(data)
        os.makedirs(cache)
        rows = [
            {"ticker": "AAA", "exchange": "NSE", "in_bse_only": "no", "nse_symbol": "AAA", "bse_symbol": "", "isin": "INE000000001"},
            {"ticker": "BBB", "exchange": "NSE", "in_bse_only": "no", "nse_symbol": "BBB", "bse_symbol": "", "isin": "INE000000002"},
        ]
        pd.DataFrame(rows).to_csv(os.path.join(data, "universe.csv"), index=False)
        pd.DataFrame([{"ticker": "AAA", "liquid": "no"}]).to_csv(os.path.join(data, "scores.csv"), index=False)
        seen = []

        def fake_fetch(rec, cfg, codes, book):
            seen.append(rec["ticker"])
            return {"ticker": rec["ticker"], "promoter_pct": 40.0, "public_pct": 60.0, "source": "Screener"}, "Screener shareholding", "ok"

        real_write = download_guard.atomic_write_df
        bf.fetch_shareholding = fake_fetch
        bf.fetch_statements = lambda *a, **k: (None, "")
        bf._refresh_company_lines = lambda *a, **k: 0
        bf.make_canary = lambda *a, **k: (lambda: True)
        bf.SHAREHOLDING_MIN_GAP = 0.0
        bf.time.sleep = lambda _s: None
        bf.today_ist = lambda: "2026-11-07"

        def fail_holders(path, frame, compression=None):
            if str(path).endswith("holders.csv"):
                raise OSError("disk full")
            return real_write(path, frame, compression=compression)

        download_guard.atomic_write_df = fail_holders
        try:
            try:
                bf.run_batch(folder, _cfg())
                raise AssertionError("a failed save should surface")
            except OSError:
                pass
            assert seen == ["AAA"]
            assert not os.path.exists(os.path.join(cache, "holders.csv"))
            cursor_path = os.path.join(cache, "backfill_cursor.json")
            assert not os.path.exists(cursor_path) or "AAA" not in open(cursor_path).read()

            download_guard.atomic_write_df = real_write
            stats = bf.run_batch(folder, _cfg())
            assert stats["shareholding_ok"] == 1
            holders = pd.read_csv(os.path.join(cache, "holders.csv"))
            assert list(holders["ticker"]) == ["AAA"]
            stats = bf.run_batch(folder, _cfg())
            assert stats["shareholding_ok"] == 1
            holders = pd.read_csv(os.path.join(cache, "holders.csv"))
            assert set(holders["ticker"]) == {"AAA", "BBB"}
            assert len(holders) == 2
        finally:
            download_guard.atomic_write_df = real_write


def test_a_second_backfill_does_not_start_while_one_is_running():
    with tempfile.TemporaryDirectory() as folder:
        data = os.path.join(folder, "data")
        cache = os.path.join(folder, "cache")
        os.makedirs(data)
        os.makedirs(cache)
        pd.DataFrame([{"ticker": "AAA", "exchange": "NSE", "isin": "INE000000001"}]).to_csv(
            os.path.join(data, "universe.csv"), index=False
        )
        calls = {"n": 0}

        def fake_fetch(*a, **k):
            calls["n"] += 1
            return None, "", "down"

        bf.fetch_shareholding = fake_fetch
        bf.time.sleep = lambda _s: None
        lock = download_guard.JobLock(os.path.join(cache, "backfill.lock"), stale_seconds=3600)
        lock.acquire()
        try:
            stats = bf.run_batch(folder, _cfg())
            assert stats.get("blocked")
            assert calls["n"] == 0
        finally:
            lock.release()


def test_unreadable_cache_stops_before_any_download():
    with tempfile.TemporaryDirectory() as folder:
        data = os.path.join(folder, "data")
        cache = os.path.join(folder, "cache")
        os.makedirs(data)
        os.makedirs(cache)
        pd.DataFrame([{"ticker": "AAA", "exchange": "NSE", "isin": "INE000000001"}]).to_csv(
            os.path.join(data, "universe.csv"), index=False
        )
        with open(os.path.join(cache, "holders.csv"), "w") as handle:
            handle.write("ticker,promoter_pct\nAAA,10\n")
        before = open(os.path.join(cache, "holders.csv")).read()
        calls = {"n": 0}

        def fake_fetch(*a, **k):
            calls["n"] += 1
            return None, "", "down"

        real = bf.pd.read_csv

        def broken(*a, **k):
            raise pd.errors.ParserError("bad cache")

        bf.pd.read_csv = broken
        bf.fetch_shareholding = fake_fetch
        try:
            stats = bf.run_batch(folder, _cfg())
            assert stats.get("cache_unreadable")
            assert calls["n"] == 0
            assert open(os.path.join(cache, "holders.csv")).read() == before
        finally:
            bf.pd.read_csv = real


def test_statement_retries_grow_and_a_quote_without_results_waits():
    cursor = {}
    ledger = download_guard.empty_ledger()
    guard = download_guard.settings({})
    today = "2026-11-07"
    for _ in range(4):
        bf._mark_statement_failed(cursor, ledger, "AAA", today, "down", guard)
    assert cursor["statements_retry_after"]["AAA"] == "2026-11-08"
    bf._mark_statement_failed(cursor, ledger, "AAA", today, "down", guard)
    assert cursor["statements_retry_after"]["AAA"] == "2026-11-10"
    bf._mark_statement_incomplete(cursor, ledger, "BBB", today, guard)
    assert cursor["statements_retry_after"]["BBB"] == "2026-11-14"
    assert "BBB" in ledger["incomplete"]["statements"]
    assert download_guard.unavailable_waiting(ledger, "BBB", "statements", "2026-11-10")


def test_progress_row_says_when_a_person_is_needed():
    with tempfile.TemporaryDirectory() as folder:
        data = os.path.join(folder, "data")
        cache = os.path.join(folder, "cache")
        os.makedirs(data)
        os.makedirs(cache)
        pd.DataFrame([{"ticker": "AAA", "exchange": "NSE", "isin": "INE000000001"}]).to_csv(
            os.path.join(data, "universe.csv"), index=False
        )
        with open(os.path.join(folder, "config.json"), "w") as handle:
            handle.write('{"features": {"fundamentals_backfill": true}}')
        ledger = download_guard.empty_ledger()
        now = download_guard.time.time()
        download_guard.note_progress(ledger, "statements", 0, True, now, 1, 6 * 3600)
        download_guard.save_ledger(cache, ledger)
        frame = bf.progress_frame(folder)
        statements = frame[frame["kind"] == "statements"].iloc[0]
        assert statements["data_status"] == "PARTIAL"
        assert "does not fix" in statements["note"]
        share = frame[frame["kind"] == "shareholding"].iloc[0]
        assert share["data_status"] == "OK"


def _restore_backfill(saved):
    bf.fetch_shareholding = saved["fetch"]
    bf.fetch_statements = saved["statements"]
    bf._refresh_company_lines = saved["lines"]
    bf.make_canary = saved["canary"]
    bf.SHAREHOLDING_MIN_GAP = saved["gap"]
    bf.time.sleep = saved["sleep"]
    bf.today_ist = saved["today"]
    bf.pd.read_csv = saved["read"]


def main():
    saved_bf = {
        "fetch": bf.fetch_shareholding,
        "statements": bf.fetch_statements,
        "lines": bf._refresh_company_lines,
        "canary": bf.make_canary,
        "gap": bf.SHAREHOLDING_MIN_GAP,
        "sleep": bf.time.sleep,
        "today": bf.today_ist,
        "read": bf.pd.read_csv,
    }
    # Remember the real price helpers before any test replaces them.
    stooq = market_sources._stooq_daily
    yahoo = market_sources._yahoo_daily
    try:
        test_atomic_write_failure_keeps_the_old_file()
        test_broken_ledger_is_kept_beside_the_cache()
        test_lock_refuses_a_live_job_and_takes_a_dead_one()
        test_two_threads_cannot_hold_the_same_lock()
        test_provider_cooldown_and_stall()
        test_unavailable_name_is_skipped_until_its_date()
        test_session_status_needs_the_nse_file()
        test_failed_price_save_does_not_mark_the_day_or_replace_the_file()
        test_a_finished_day_is_not_downloaded_again()
        test_same_bars_committed_twice_do_not_duplicate()
        test_partial_day_keeps_bars_and_stays_pending()
        test_broken_bhav_state_does_not_touch_the_price_file()
        test_a_busy_price_lock_does_not_download()
        test_gap_fill_miss_is_not_asked_again_until_the_retry_date()
        test_backfill_flush_failure_does_not_advance_and_the_next_run_resumes()
        test_a_second_backfill_does_not_start_while_one_is_running()
        test_unreadable_cache_stops_before_any_download()
        test_statement_retries_grow_and_a_quote_without_results_waits()
        test_progress_row_says_when_a_person_is_needed()
    finally:
        market_sources._stooq_daily = stooq
        market_sources._yahoo_daily = yahoo
        _restore_backfill(saved_bf)
    print("download guard ok")


if __name__ == "__main__":
    main()
