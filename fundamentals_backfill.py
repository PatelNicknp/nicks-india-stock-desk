"""Keep filling company statements and shareholding. One batch, then stop.

The price workflow is separate and is not changed. This script is what the
frequent GitHub Action runs. It reads cache/backfill_cursor.json, downloads the
next liquid names, then the rest of the NSE list, then BSE-only names, and
writes the cache back. After every name has a saved row, the oldest records
come around again: shareholding about every 90 days, results after an earnings
date or every 90 days.

Free sources, no API key. Shareholding runs before statements so a long
statement pass cannot use up the clock. Shareholding tries the NSE filing,
then the public Screener page, then the BSE shareholding file. Statements try
Yahoo .NS, then Yahoo .BO. A source that errors three times in one run is
skipped for the rest of that run. An empty filing is recorded and tried again
later in the pass. It does not stop the batch. A statement name whose sources
error is tried again the next day. A shareholding name whose sources all fail
is recorded as failed and tried again after 3 days, then 7, 14 and 30 days if
it keeps failing, and the batch moves on to the next name. Shareholding only
stops early for a real outage: the first names of the run all fail, or a few
big, well-known stocks fail too.

Screener addresses a BSE-only company by its BSE scrip code
(screener.in/company/530621/), not by its BSE ticker, so BSE-only names are
looked up by code. Mutual fund and ETF units (ISIN starting INF) file no
shareholding pattern and are not queued for shareholding.
"""
import json
import os
import sys
import time
from urllib.parse import quote

import pandas as pd

import fallback
import india_data
import netutil
import tables

IST = "Asia/Kolkata"
CURSOR_NAME = "backfill_cursor.json"
LIQUID, NSE, BSE = 0, 1, 2
# Days to wait before trying a failed shareholding name again: first failure,
# second, third, then every later failure.
SHAREHOLDING_RETRY_DAYS = (3, 7, 14, 30)
# Shareholding stops for the run only when this many names in a row have
# failed from the start of the run, with no name saved and no empty filing.
OUTAGE_FIRST_NAMES = 25
# After this many failures in a row, try the big stocks below. If they fail too,
# the sources are blocking or down, so shareholding stops for the run.
CANARY_EVERY = 10
CANARY_TICKERS = ("RELIANCE", "TCS", "HDFCBANK")
SHAREHOLDING_MIN_GAP = 1.0
PASS_NOTE = (
    "At 200 statements and 200 shareholding names a run, the first pass of about "
    "4,300 stocks takes well under a day when the free sources answer. "
    "Liquid names come first, then the rest of the NSE list, then BSE-only names. "
    "A name with no shareholding filing is saved for later in the pass, and a name "
    "no source answers for is tried again after a few days, so hard names do not "
    "stop the batch."
)
REFRESH_NOTE = (
    "Every name has a saved row. Shareholding refreshes about every 90 days. "
    "Results refresh after the next earnings date, or every 90 days."
)


def root_dir():
    return os.environ.get("DESK_ROOT") or os.path.dirname(os.path.abspath(__file__))


def load_cfg(root):
    with open(os.path.join(root, "config.json")) as f:
        return json.load(f)


def enabled(cfg):
    return bool((cfg.get("features") or {}).get("fundamentals_backfill", True))


def batch_cfg(cfg):
    raw = cfg.get("fundamentals_backfill") or {}
    def num(key, default):
        try:
            return type(default)(raw.get(key, default))
        except (TypeError, ValueError):
            return default
    return {
        "statements_per_run": max(1, num("statements_per_run", 40)),
        "shareholding_per_run": max(1, num("shareholding_per_run", 40)),
        "pause_seconds": max(0.0, num("pause_seconds", 0.45)),
        "max_minutes": max(1, num("max_minutes", 18)),
        "statements_refresh_days": max(1, num("statements_refresh_days", 90)),
        "shareholding_refresh_days": max(1, num("shareholding_refresh_days", 90)),
        "company_lines_per_run": max(0, num("company_lines_per_run", 40)),
    }


def today_ist():
    return pd.Timestamp.now(tz=IST).strftime("%Y-%m-%d")


def now_iso():
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%MZ")


def parse_day(value):
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        stamp = pd.to_datetime(text, errors="coerce")
    except Exception:
        return ""
    if stamp is None or pd.isna(stamp):
        return ""
    return pd.Timestamp(stamp).strftime("%Y-%m-%d")


def shift_days(day, n):
    return (pd.Timestamp(day) + pd.Timedelta(days=int(n))).strftime("%Y-%m-%d")


def blank(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return str(value).strip() == ""


def read_csv(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def load_cursor(cache):
    path = os.path.join(cache, CURSOR_NAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_cursor(cache, cursor):
    path = os.path.join(cache, CURSOR_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cursor, f, indent=1)
    os.replace(tmp, path)


def _ticker_set(df):
    if df is None or len(df) == 0 or "ticker" not in df.columns:
        return set()
    return set(df["ticker"].astype(str).str.strip().str.upper()) - {""}


def _stamp_map(df, column):
    out = {}
    if df is None or len(df) == 0 or "ticker" not in getattr(df, "columns", []):
        return out
    if column not in df.columns:
        return out
    for ticker, stamp in zip(df["ticker"].astype(str), df[column].astype(str)):
        day = parse_day(stamp)
        key = ticker.strip().upper()
        if key and day and key not in out:
            out[key] = day
    return out


def _row_map(df):
    out = {}
    if df is None or len(df) == 0 or "ticker" not in getattr(df, "columns", []):
        return out
    for rec in df.to_dict("records"):
        ticker = str(rec.get("ticker") or "").strip().upper()
        if ticker:
            out[ticker] = rec
    return out


def shareholding_covered(row):
    if not row:
        return False
    for key in ("promoter_pct", "fii_pct", "dii_pct", "public_pct"):
        if not blank(row.get(key)):
            return True
    return False


def band_for(row, liquid):
    """0 liquid NSE, 1 other NSE, 2 BSE-only."""
    ticker = str(row.get("ticker") or "").strip()
    bse_only = str(row.get("in_bse_only") or "").lower() == "yes"
    exchange = str(row.get("exchange") or "").upper()
    if bse_only or exchange == "BSE":
        return BSE
    if ticker in liquid:
        return LIQUID
    return NSE


def statements_due(covered, fetched_on, earnings_days, today, refresh_days):
    if not covered:
        return True
    if not fetched_on:
        return True
    if fetched_on <= shift_days(today, -int(refresh_days)):
        return True
    for day in earnings_days or []:
        if fetched_on < day <= today:
            return True
    return False


def shareholding_due(covered, fetched_on, as_of, today, refresh_days):
    if not covered:
        return True
    if not fetched_on:
        return True
    cutoff = shift_days(today, -int(refresh_days))
    if fetched_on <= cutoff:
        return True
    if as_of and as_of <= cutoff:
        return True
    return False


def earnings_by_ticker(earn):
    out = {}
    if earn is None or len(earn) == 0 or "ticker" not in earn.columns:
        return out
    col = "earnings_dt" if "earnings_dt" in earn.columns else None
    if col is None:
        return out
    for ticker, raw in zip(earn["ticker"].astype(str), earn[col].astype(str)):
        day = parse_day(raw)
        key = ticker.strip().upper()
        if key and day:
            out.setdefault(key, []).append(day)
    return out


def build_queue(universe, scores, info, annual, holders, earn, cursor, today, refresh_days, kind):
    """Ordered records. Missing names in each band come before any refresh."""
    if universe is None or len(universe) == 0 or "ticker" not in universe.columns:
        return []
    liquid = set()
    if scores is not None and len(scores) and "ticker" in scores.columns and "liquid" in scores.columns:
        liquid = set(scores.loc[scores["liquid"].astype(str).str.lower().eq("yes"), "ticker"].astype(str).str.upper())
    annual_set = _ticker_set(annual)
    info_set = _ticker_set(info)
    info_stamp = _stamp_map(info, "fetched_on")
    hold_map = _row_map(holders)
    earn_map = earnings_by_ticker(earn)
    retry = (cursor or {}).get(kind + "_retry_after") or {}
    days = refresh_days["statements" if kind == "statements" else "shareholding"]
    rows = []
    seen = set()
    for rec in universe.to_dict("records"):
        ticker = str(rec.get("ticker") or "").strip().upper()
        if not ticker or ticker.startswith("^") or ticker in seen:
            continue
        seen.add(ticker)
        if kind == "statements":
            covered = ticker in annual_set or ticker in info_set
            fetched = info_stamp.get(ticker, "")
            due = statements_due(covered, fetched, earn_map.get(ticker), today, days)
            as_of = ""
        else:
            hold = hold_map.get(ticker) or {}
            covered = shareholding_covered(hold)
            fetched = parse_day(hold.get("fetched_on"))
            as_of = parse_day(hold.get("as_of"))
            due = shareholding_due(covered, fetched, as_of, today, days)
            if not covered and is_fund_unit(rec):
                due = False
        retry_after = parse_day(retry.get(ticker))
        if retry_after and retry_after > today:
            due = False
        # An empty filing stays in the pass, behind names that have not been tried yet.
        defer = False
        if kind == "shareholding":
            stamped = parse_day(((cursor or {}).get("shareholding_empty_on") or {}).get(ticker))
            defer = bool(stamped) and stamped == today
        rows.append({
            "ticker": ticker,
            "band": band_for(rec, liquid),
            "covered": covered,
            "fetched_on": fetched,
            "as_of": as_of,
            "due": due,
            "retry_after": retry_after,
            "defer": defer,
            "exchange": rec.get("exchange") or "",
            "nse_symbol": rec.get("nse_symbol") or "",
            "bse_symbol": rec.get("bse_symbol") or "",
            "in_bse_only": rec.get("in_bse_only") or "",
            "isin": rec.get("isin") or "",
        })
    rows.sort(key=lambda r: (
        0 if not r["covered"] else 1,
        1 if r.get("defer") else 0,
        r["band"],
        r["fetched_on"] or "0000-00-00",
        r["ticker"],
    ))
    return rows


def take_batch(queue, cap):
    out = []
    for rec in queue:
        if not rec["due"]:
            continue
        out.append(rec)
        if len(out) >= int(cap):
            break
    return out


def is_fund_unit(rec):
    """Mutual fund and ETF units (ISIN INF...) have no shareholding pattern."""
    isin = str(rec.get("isin") or "").strip().upper()
    if isin in ("NAN", "NONE"):
        return False
    return isin.startswith("INF")


def statement_symbols(rec):
    nse = str(rec.get("nse_symbol") or "").strip().upper()
    bse = str(rec.get("bse_symbol") or "").strip().upper()
    ticker = str(rec.get("ticker") or "").strip().upper()
    bse_only = str(rec.get("in_bse_only") or "").lower() == "yes" or str(rec.get("exchange") or "").upper() == "BSE"
    if bse_only:
        first = (bse or ticker) + ".BO"
        second = (nse + ".NS") if nse else ""
    else:
        first = (nse or ticker) + ".NS"
        second = (bse + ".BO") if bse and bse != (nse or ticker) else ""
    symbols = []
    for symbol in (first, second):
        if symbol and not symbol.startswith(".") and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def first_good(field, steps, book, pause=0.0):
    """Try each source until one answers. Later sources are not called after a hit.

    The third value is ok, empty, or down. An empty reply means this name has
    no filing at that source. It does not retire the source. An exception does.
    """
    saw_empty = False
    tried = 0
    for name, fn in steps:
        if not book.allow(name):
            book.hit(field, name, "FAILED", "skipped after repeated failures")
            continue
        tried += 1
        try:
            value = fn()
        except Exception as exc:
            book.hit(field, name, "FAILED", str(exc)[:160])
            if pause:
                time.sleep(min(pause, 0.4))
            continue
        if fallback.empty(value):
            saw_empty = True
            book.hit(field, name, "MISSING", "empty reply", counts=False)
            if pause:
                time.sleep(min(pause, 0.4))
            continue
        book.ok(field, name, "answered")
        return value, name, "ok"
    if saw_empty:
        return None, "", "empty"
    if steps and not tried:
        # Every source was retired earlier in this run. Nothing was asked, so
        # this is not a failure of the name itself.
        return None, "", "retired"
    return None, "", "down"


def next_streak(streak, outcome):
    """Errors add to the outage streak. A saved row clears it. An empty filing does not."""
    if outcome == "ok":
        return 0
    if outcome == "empty":
        return streak
    return streak + 1


def _bundle_useful(info, annual, quarters):
    if annual or quarters:
        return True
    if not info:
        return False
    if str(info.get("company") or "").strip():
        return True
    for key in ("forward_pe", "analyst_mean", "analyst_count", "target_mean"):
        if not blank(info.get(key)):
            return True
    return False


def fetch_statements(rec, cfg, book):
    ticker = rec["ticker"]

    def attempt(symbol):
        def run():
            info, annual, quarters, earn = india_data.fetch_yahoo_bundle(ticker, cfg, symbol=symbol)
            if not _bundle_useful(info, annual, quarters):
                return None
            info = dict(info or {})
            info["ticker"] = ticker
            info["source"] = "Yahoo " + symbol
            return {"info": info, "annual": annual or [], "quarters": quarters or [], "earn": earn or [], "symbol": symbol}
        return run

    steps = []
    for symbol in statement_symbols(rec):
        # One label per listing so three failures skip that listing for the rest of the run.
        label = "Yahoo BO" if str(symbol).endswith(".BO") else "Yahoo NS"
        steps.append((label, attempt(symbol)))
    value, source, _outcome = first_good("statements:" + ticker, steps, book, pause=0.2)
    return value, source


def parse_screener_shareholding(html):
    """Quarterly promoter, FII, DII, and public percents from a Screener company page."""
    import html as html_lib
    import re
    if not html:
        return None
    # The tab button is data-tab-id="quarterly-shp". The table is id="quarterly-shp".
    # A bare id= search hits the button first and then reads no rows.
    start = re.search(r'\sid="quarterly-shp"', html)
    if not start:
        return None
    rest = html[start.end():]
    end = re.search(r'\sid="yearly-shp"', rest)
    chunk = rest[:end.start()] if end else rest
    if not chunk.strip():
        return None
    dates = re.findall(r"<th>([A-Z][a-z]{2} \d{4})</th>", chunk)
    found = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", chunk, re.S):
        label_m = re.search(r'<td class="text">(.*?)</td>', tr, re.S)
        if not label_m:
            continue
        label = re.sub(r"<[^>]+>", " ", label_m.group(1))
        label = html_lib.unescape(label).replace("\xa0", " ").replace("+", " ")
        label = " ".join(label.split()).lower()
        nums = []
        for raw in re.findall(r">\s*([0-9]+(?:\.[0-9]+)?)%\s*<", tr):
            try:
                nums.append(float(raw))
            except ValueError:
                continue
        if label and nums:
            found[label] = nums

    def pick(*names):
        for name in names:
            series = found.get(name)
            if not series:
                continue
            latest = series[-1]
            prev = series[-2] if len(series) >= 2 else None
            change = None if prev is None else round(latest - prev, 2)
            return latest, change
        return None, None

    promoter, promoter_chg = pick("promoters", "promoter")
    fii, fii_chg = pick("fiis", "fii")
    dii, dii_chg = pick("diis", "dii")
    public, public_chg = pick("public")
    if promoter is None and fii is None and dii is None and public is None:
        return None
    as_of = ""
    if dates:
        try:
            as_of = pd.to_datetime(dates[-1]).strftime("%Y-%m-%d")
        except Exception:
            as_of = ""
    return {
        "promoter_pct": promoter,
        "fii_pct": fii,
        "dii_pct": dii,
        "public_pct": public,
        "promoter_chg": promoter_chg,
        "fii_chg": fii_chg,
        "dii_chg": dii_chg,
        "public_chg": public_chg,
        "as_of": as_of,
        "source": "Screener",
    }


def fetch_nse_shareholding(symbol, cfg):
    history = india_data.fetch_shareholding_master(symbol, cfg)
    split = {}
    if history and history[-1].get("xbrl"):
        try:
            split = india_data.fetch_xbrl_split(history[-1]["xbrl"], cfg) or {}
        except Exception:
            split = {}
    row = india_data.shareholding_row(symbol, history, split)
    if not row or not shareholding_covered(row):
        return None
    return row


def _is_not_found(exc):
    return "404" in str(exc)


def fetch_screener_shareholding(symbols, cfg):
    """Shareholding from the public Screener page.

    symbols is one slug or a list tried in order: the NSE symbol for NSE names,
    the BSE scrip code for BSE-only names. A 404 means Screener has no page at
    that address. It moves on to the next slug and, when no slug has a page,
    returns None (no filing here), so a wrong address does not retire Screener
    for the rest of the run. Other errors (403, 429, 5xx) are raised.
    """
    if isinstance(symbols, str):
        symbols = [symbols]
    slugs = []
    for raw in symbols or []:
        token = str(raw or "").strip().upper()
        if token.endswith(".0") and token[:-2].isdigit():
            token = token[:-2]
        if token and token not in ("NAN", "NONE") and token not in slugs:
            slugs.append(token)
    headers = dict(india_data.BROWSER)
    headers["Accept"] = "text/html,application/xhtml+xml"
    headers["Referer"] = "https://www.screener.in/"
    last_err = None
    for slug in slugs:
        safe = quote(slug, safe="")
        for url in (
            "https://www.screener.in/company/%s/consolidated/" % safe,
            "https://www.screener.in/company/%s/" % safe,
        ):
            if not fallback.robots_allows(url):
                raise netutil.PermanentError("robots.txt does not allow this page")
            try:
                response = netutil.http_get(requests_mod(), url, headers, 20, max_tries=2, delays=(1.5, 3.0))
            except Exception as exc:
                if _is_not_found(exc):
                    # No company at this address. The standalone page will 404 too.
                    break
                last_err = exc
                continue
            parsed = parse_screener_shareholding(response.text)
            if parsed:
                parsed["ticker"] = slug
                return parsed
    if last_err:
        raise last_err
    return None


def fetch_bse_shareholding(code, cfg):
    code = str(code or "").strip()
    if not code or not code.isdigit():
        return None
    url = "https://api.bseindia.com/BseIndiaAPI/api/ShareHoldingNew/w?scripcode=%s" % code
    headers = dict(india_data.BROWSER)
    headers["Referer"] = "https://www.bseindia.com/"
    headers["Accept"] = "application/json"
    response = netutil.http_get(requests_mod(), url, headers, 15, max_tries=2, delays=(1.5, 3.0))
    if "html" in str(response.headers.get("content-type") or "").lower() or response.text.lstrip().startswith("<"):
        raise netutil.PermanentError("BSE shareholding page was blocked")
    try:
        payload = response.json()
    except Exception as exc:
        raise netutil.PermanentError("BSE shareholding was not JSON") from exc
    return _bse_share_row(payload)


def _bse_share_row(payload):
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        for key in ("Table", "Data", "data"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    if not rows:
        return None
    latest = rows[-1] if isinstance(rows[-1], dict) else None
    if not latest:
        return None
    folded = {str(k).lower(): v for k, v in latest.items()}

    def grab(*names):
        for name in names:
            if name in folded and not blank(folded[name]):
                return india_data._pct_num(folded[name])
        return None

    promoter = grab("promoter", "promoters", "promoter_and_promoter_group")
    fii = grab("fii", "fiis", "foreign")
    dii = grab("dii", "diis")
    public = grab("public", "public_shareholding")
    if promoter is None and fii is None and dii is None and public is None:
        return None
    return {
        "promoter_pct": promoter,
        "fii_pct": fii,
        "dii_pct": dii,
        "public_pct": public,
        "as_of": parse_day(folded.get("qtr") or folded.get("date") or ""),
        "source": "BSE shareholding",
    }


def requests_mod():
    import requests
    return requests


def bse_code_map(root):
    out = {}
    for name in ("bse_link.csv", "bse_only.csv"):
        df = read_csv(os.path.join(root, "cache", name))
        if len(df) == 0 or "bse_code" not in df.columns:
            continue
        for rec in df.to_dict("records"):
            code = str(rec.get("bse_code") or "").strip()
            if not code or code.endswith(".0"):
                code = code[:-2] if code.endswith(".0") else code
            if not code:
                continue
            for key in ("ticker", "bse_symbol", "nse_symbol", "isin"):
                token = str(rec.get(key) or "").strip().upper()
                if token:
                    out.setdefault(token, code)
    return out


def screener_slugs(rec, code):
    """Screener addresses to try. BSE-only companies live at their BSE scrip code."""
    ticker = str(rec.get("ticker") or "").strip().upper()
    nse = str(rec.get("nse_symbol") or "").strip().upper()
    bse_sym = str(rec.get("bse_symbol") or "").strip().upper()
    bse_only = str(rec.get("in_bse_only") or "").lower() == "yes" or str(rec.get("exchange") or "").upper() == "BSE"
    code = str(code or "").strip()
    out = []
    if bse_only:
        order = [code] if code else [bse_sym or ticker]
    else:
        order = [nse or ticker, code]
    for token in order:
        token = str(token or "").strip().upper()
        if token and token not in ("NAN", "NONE") and token not in out:
            out.append(token)
    return out


def fetch_shareholding(rec, cfg, codes, book):
    ticker = rec["ticker"]
    nse = str(rec.get("nse_symbol") or "").strip().upper()
    bse_sym = str(rec.get("bse_symbol") or "").strip().upper()
    bse_only = str(rec.get("in_bse_only") or "").lower() == "yes" or str(rec.get("exchange") or "").upper() == "BSE"
    steps = []
    if nse and not bse_only:
        steps.append(("NSE shareholding", lambda symbol=nse: fetch_nse_shareholding(symbol, cfg)))
    code = codes.get(ticker) or codes.get(bse_sym) or codes.get(str(rec.get("isin") or "").strip().upper())
    slugs = screener_slugs(rec, code)
    if slugs:
        steps.append(("Screener shareholding", lambda symbols=slugs: fetch_screener_shareholding(symbols, cfg)))
    if code:
        steps.append(("BSE shareholding", lambda scrip=code: fetch_bse_shareholding(scrip, cfg)))
    value, source, outcome = first_good("shareholding:" + ticker, steps, book, pause=0.25)
    if not value:
        return None, source, outcome
    row = dict(value)
    row["ticker"] = ticker
    row["source"] = row.get("source") or source
    if row.get("ownership_pct") in (None, ""):
        row["ownership_pct"] = row.get("promoter_pct")
    return row, source, "ok"


def _merge_frames(old, add_rows):
    if not add_rows:
        return old
    add = pd.DataFrame(add_rows)
    if old is None or len(old) == 0:
        return add
    if "ticker" not in old.columns:
        return add
    keep = old[~old["ticker"].astype(str).isin(set(add["ticker"].astype(str)))]
    return pd.concat([keep, add], ignore_index=True)


def _mark_retry(cursor, kind, ticker, today):
    key = kind + "_retry_after"
    book = dict(cursor.get(key) or {})
    book[ticker] = shift_days(today, 1)
    cursor[key] = book


def retry_days(fail_count):
    """3 days after the first failure, then 7, 14, and 30 days."""
    n = max(1, int(fail_count or 1))
    return SHAREHOLDING_RETRY_DAYS[min(n, len(SHAREHOLDING_RETRY_DAYS)) - 1]


def _mark_shareholding_failed(cursor, ticker, today, note=""):
    """Record a name no shareholding source answered for, and when to try it again."""
    fails = dict(cursor.get("shareholding_failures") or {})
    prev = fails.get(ticker) or {}
    try:
        count = int(prev.get("count") or 0) + 1
    except (TypeError, ValueError, AttributeError):
        count = 1
    wait = retry_days(count)
    after = shift_days(today, wait)
    fails[ticker] = {"count": count, "last_on": today, "retry_after": after, "note": str(note or "")[:140]}
    cursor["shareholding_failures"] = fails
    retry = dict(cursor.get("shareholding_retry_after") or {})
    retry[ticker] = after
    cursor["shareholding_retry_after"] = retry
    return after


def _clear_shareholding_failed(cursor, ticker):
    fails = dict(cursor.get("shareholding_failures") or {})
    if ticker in fails:
        fails.pop(ticker, None)
        cursor["shareholding_failures"] = fails


class OutageGuard:
    """Decides when shareholding should stop for the run.

    A name that fails is recorded and the batch moves on. The run stops only when
    the first OUTAGE_FIRST_NAMES names all fail, or when CANARY_EVERY names fail in
    a row and the big stocks (canary) fail too. A canary that answers clears the
    streak, so a long stretch of hard small names keeps going.
    """

    def __init__(self, canary=None, first_names=OUTAGE_FIRST_NAMES, every=CANARY_EVERY):
        self.canary = canary
        self.first_names = int(first_names)
        self.every = int(every)
        self.seen = 0
        self.any_answer = False
        self.streak = 0
        self.reason = ""

    def record(self, outcome):
        """Returns True when shareholding should stop now."""
        self.seen += 1
        if outcome in ("ok", "empty"):
            self.any_answer = True
            if outcome == "ok":
                self.streak = 0
            return False
        self.streak += 1
        if not self.any_answer and self.seen >= self.first_names:
            self.reason = "the first %d names all failed" % self.seen
            return True
        if self.streak >= self.every and self.streak % self.every == 0:
            if self.canary is None:
                return False
            if self.canary():
                self.streak = 0
                return False
            self.reason = "%d names failed in a row and the big stocks failed too" % self.streak
            return True
        return False


def make_canary(universe, cfg, codes, book, tickers=CANARY_TICKERS):
    """A check that one of the big stocks still answers. One name per check, polite."""
    recs = []
    if universe is not None and len(universe) and "ticker" in universe.columns:
        by_ticker = {str(r.get("ticker") or "").strip().upper(): r for r in universe.to_dict("records")}
        for t in tickers:
            if t in by_ticker:
                recs.append(by_ticker[t])
    if not recs:
        recs = [{"ticker": t, "nse_symbol": t, "bse_symbol": t, "exchange": "Both", "in_bse_only": "no"} for t in tickers]
    state = {"i": 0}

    def check():
        rec = dict(recs[state["i"] % len(recs)])
        state["i"] += 1
        rec["ticker"] = str(rec.get("ticker") or "").strip().upper()
        try:
            row, source, outcome = fetch_shareholding(rec, cfg, codes, book)
        except Exception as exc:
            print("shareholding canary", rec["ticker"], "error", str(exc)[:120])
            return False
        good = outcome == "ok" and bool(row)
        print("shareholding canary", rec["ticker"], "answered by " + source if good else "failed")
        return good

    return check


def _clear_retry(cursor, kind, ticker):
    key = kind + "_retry_after"
    book = dict(cursor.get(key) or {})
    book.pop(ticker, None)
    cursor[key] = book


def _mark_empty(cursor, ticker, today):
    """Remember a name with no filing so the rest of the pass can go first."""
    book = dict(cursor.get("shareholding_empty_on") or {})
    book[ticker] = today
    cursor["shareholding_empty_on"] = book


def _clear_empty(cursor, ticker):
    book = dict(cursor.get("shareholding_empty_on") or {})
    if ticker in book:
        book.pop(ticker, None)
        cursor["shareholding_empty_on"] = book


def run_batch(root, cfg, max_names=None):
    """Download the next slice. Returns a short status dict. No network when the switch is off."""
    if not enabled(cfg):
        return {"enabled": False, "statements_ok": 0, "shareholding_ok": 0}
    spec = batch_cfg(cfg)
    if max_names is not None:
        spec["statements_per_run"] = min(spec["statements_per_run"], int(max_names))
        spec["shareholding_per_run"] = min(spec["shareholding_per_run"], int(max_names))
    data = os.path.join(root, "data")
    cache = os.path.join(root, "cache")
    os.makedirs(cache, exist_ok=True)
    os.makedirs(data, exist_ok=True)
    universe = read_csv(os.path.join(data, "universe.csv"))
    scores = read_csv(os.path.join(data, "scores.csv"))
    info = read_csv(os.path.join(cache, "yahoo_info.csv"))
    annual = read_csv(os.path.join(cache, "annual.csv"))
    quarters = read_csv(os.path.join(cache, "quarters.csv"))
    earn = read_csv(os.path.join(cache, "earnings.csv"))
    holders = read_csv(os.path.join(cache, "holders.csv"))
    cursor = load_cursor(cache)
    today = today_ist()
    refresh = {
        "statements": spec["statements_refresh_days"],
        "shareholding": spec["shareholding_refresh_days"],
    }
    started = time.time()
    deadline = started + spec["max_minutes"] * 60
    book = fallback.SourceBook(give_up_after=3)
    codes = bse_code_map(root)
    pause = spec["pause_seconds"]
    stats = {
        "statements_ok": 0,
        "statements_fail": 0,
        "shareholding_ok": 0,
        "shareholding_fail": 0,
        "shareholding_empty": 0,
        "shareholding_skipped": 0,
    }

    def over_time():
        return time.time() >= deadline

    new_a, new_q, info_rows, earn_rows = [], [], [], []
    if len(info):
        info_rows.extend(info.to_dict("records"))
    hold_map = _row_map(holders)

    # Shareholding first so a full statement pass cannot use up the 18 minute budget
    # before any holder rows are saved.
    hold_queue = build_queue(universe, scores, info, annual, holders, earn, cursor, today, refresh, "shareholding")
    hold_todo = take_batch(hold_queue, spec["shareholding_per_run"])
    print("Shareholding batch %d" % len(hold_todo))
    guard = OutageGuard(canary=make_canary(universe, cfg, codes, book))
    for i, rec in enumerate(hold_todo):
        if over_time():
            print("Stopping shareholding at the time limit")
            break
        ticker = rec["ticker"]
        fail_note = "no shareholding source answered"
        try:
            row, source, outcome = fetch_shareholding(rec, cfg, codes, book)
        except Exception as exc:
            row, source, outcome = None, "", "down"
            fail_note = str(exc)[:140]
        if outcome == "ok" and row:
            row["fetched_on"] = today
            row["source"] = source or row.get("source") or ""
            chg = row.get("fii_chg")
            if chg is None:
                chg = row.get("promoter_chg")
            try:
                chg_n = float(chg) if chg is not None and chg != "" else float("nan")
            except (TypeError, ValueError):
                chg_n = float("nan")
            up, down = india_data.trend_from_change(chg_n)
            row["inst_up"] = up
            row["inst_down"] = down
            hold_map[ticker] = row
            _clear_retry(cursor, "shareholding", ticker)
            _clear_empty(cursor, ticker)
            _clear_shareholding_failed(cursor, ticker)
            stats["shareholding_ok"] += 1
            guard.record("ok")
        elif outcome == "empty":
            stats["shareholding_empty"] += 1
            _mark_empty(cursor, ticker, today)
            guard.record("empty")
            print("shareholding none", ticker, "no filing, saved for later in this pass")
        elif outcome == "retired":
            # Every source for this kind of name was retired earlier in this run.
            # Leave the name as it is; the next run asks again.
            stats["shareholding_skipped"] += 1
            if stats["shareholding_skipped"] == 1:
                print("shareholding skip", ticker, "its sources were retired earlier in this run")
        else:
            stats["shareholding_fail"] += 1
            after = _mark_shareholding_failed(cursor, ticker, today, fail_note)
            print("shareholding fail", ticker, fail_note + ", retry after " + after)
            if guard.record("down"):
                print("Shareholding stopped for this run: " + guard.reason)
                break
        if (i + 1) % 8 == 0:
            _flush_holders(hold_map, cache)
            save_cursor(cache, cursor)
        if outcome != "retired":
            # Most BSE-only names have one live source (Screener), so keep at
            # least a second between names to stay polite.
            time.sleep(max(pause, SHAREHOLDING_MIN_GAP))
    _flush_holders(hold_map, cache)
    save_cursor(cache, cursor)

    state_queue = build_queue(universe, scores, info, annual, holders, earn, cursor, today, refresh, "statements")
    todo = take_batch(state_queue, spec["statements_per_run"])
    print("Statements batch %d" % len(todo))
    streak = 0
    for i, rec in enumerate(todo):
        if over_time():
            print("Stopping statements at the time limit")
            break
        ticker = rec["ticker"]
        try:
            bundle, source = fetch_statements(rec, cfg, book)
            if not bundle:
                raise RuntimeError("no statement source answered")
            info_row = dict(bundle["info"])
            info_row["fetched_on"] = today
            info_row["source"] = source or info_row.get("source") or ""
            info_rows.append(info_row)
            if bundle["annual"]:
                new_a.append(pd.DataFrame(bundle["annual"]))
            if bundle["quarters"]:
                new_q.append(pd.DataFrame(bundle["quarters"]))
            earn_rows.extend(bundle["earn"])
            _clear_retry(cursor, "statements", ticker)
            stats["statements_ok"] += 1
            streak = 0
        except Exception as exc:
            stats["statements_fail"] += 1
            streak += 1
            _mark_retry(cursor, "statements", ticker, today)
            print("statement fail", ticker, str(exc)[:140])
            if streak >= 6:
                print("Statements paused after 6 failures in a row")
                break
        if (i + 1) % 8 == 0:
            annual, quarters = _flush_statements(annual, quarters, new_a, new_q, cache)
            _flush_info_earn(info_rows, earn_rows, earn, cache)
            earn = read_csv(os.path.join(cache, "earnings.csv"))
            save_cursor(cache, cursor)
        time.sleep(pause)
    annual, quarters = _flush_statements(annual, quarters, new_a, new_q, cache)
    _flush_info_earn(info_rows, earn_rows, earn, cache)
    stats["company_lines"] = _refresh_company_lines(root, cfg, codes, book, spec, deadline)
    cursor["last_batch_at"] = now_iso()
    cursor["last_statements_ok"] = stats["statements_ok"]
    cursor["last_statements_fail"] = stats["statements_fail"]
    cursor["last_shareholding_ok"] = stats["shareholding_ok"]
    cursor["last_shareholding_fail"] = stats["shareholding_fail"]
    cursor["last_shareholding_empty"] = stats["shareholding_empty"]
    cursor["last_shareholding_skipped"] = stats["shareholding_skipped"]
    save_cursor(cache, cursor)
    frame = progress_frame(root)
    _write_progress(data, frame)
    print(
        "Backfill statements %d ok / %d failed, shareholding %d ok / %d no filing / %d failed"
        % (
            stats["statements_ok"],
            stats["statements_fail"],
            stats["shareholding_ok"],
            stats["shareholding_empty"],
            stats["shareholding_fail"],
        )
    )
    stats["enabled"] = True
    return stats


def company_line_on(cfg):
    return bool((cfg.get("features") or {}).get("company_line", True))


def _refresh_company_lines(root, cfg, codes, book, spec, deadline):
    """Fill a few names that still have no summary, then rewrite data/company_lines.csv."""
    if not company_line_on(cfg):
        return 0
    import company_lines
    tried = 0
    try:
        if spec["company_lines_per_run"] and time.time() < deadline:
            tried = company_lines.fill_missing(
                root, cfg, codes, book, limit=spec["company_lines_per_run"], deadline=deadline,
                pause=max(1.0, spec["pause_seconds"]), today=today_ist(),
            )
        frame = company_lines.write_lines(root, today=today_ist())
        if frame is not None:
            real = int((frame["source"] != "Industry fallback").sum())
            print("Company lines %d real, %d industry fallback, %d names tried this run" % (real, len(frame) - real, tried))
    except Exception as exc:
        print("company lines skipped", str(exc)[:160])
    return tried


def _flush_statements(annual, quarters, new_a, new_q, cache):
    if new_a:
        add = pd.concat(new_a, ignore_index=True)
        keep = annual[~annual["ticker"].astype(str).isin(set(add["ticker"].astype(str)))] if len(annual) and "ticker" in annual.columns else annual
        annual = pd.concat([keep, add], ignore_index=True) if len(keep) else add
        annual.to_csv(os.path.join(cache, "annual.csv"), index=False)
        new_a.clear()
    if new_q:
        add = pd.concat(new_q, ignore_index=True)
        keep = quarters[~quarters["ticker"].astype(str).isin(set(add["ticker"].astype(str)))] if len(quarters) and "ticker" in quarters.columns else quarters
        quarters = pd.concat([keep, add], ignore_index=True) if len(keep) else add
        quarters.to_csv(os.path.join(cache, "quarters.csv"), index=False)
        new_q.clear()
    return annual, quarters


def _flush_info_earn(info_rows, earn_rows, earn, cache):
    if info_rows:
        info = pd.DataFrame(info_rows).drop_duplicates("ticker", keep="last")
        info.to_csv(os.path.join(cache, "yahoo_info.csv"), index=False)
    if earn_rows:
        earn_new = pd.DataFrame(earn_rows)
        if len(earn) and "ticker" in earn.columns:
            got = set(earn_new["ticker"].astype(str))
            earn = pd.concat([earn[~earn["ticker"].astype(str).isin(got)], earn_new], ignore_index=True)
        else:
            earn = earn_new
        earn.to_csv(os.path.join(cache, "earnings.csv"), index=False)


def _flush_holders(hold_map, cache):
    if not hold_map:
        return
    pd.DataFrame(list(hold_map.values())).to_csv(os.path.join(cache, "holders.csv"), index=False)


def _write_progress(data, frame):
    os.makedirs(data, exist_ok=True)
    out = frame.copy() if frame is not None else pd.DataFrame()
    cols = tables.COLS["backfill_progress"]
    for col in cols:
        if col not in out.columns:
            out[col] = ""
    if len(out) == 0:
        out = tables.ensure(out, cols, "MISSING", "No backfill progress yet.")
    else:
        out = out[cols]
    out.to_csv(os.path.join(data, "backfill_progress.csv"), index=False)


def progress_frame(root):
    """Two rows for the Data updates page. Counts come from the saved files."""
    try:
        return _progress_frame(root)
    except Exception as exc:
        print("backfill progress", str(exc)[:160])
        return pd.DataFrame()


def _progress_frame(root):
    try:
        cfg = load_cfg(root)
    except Exception:
        return pd.DataFrame()
    if not enabled(cfg):
        return pd.DataFrame()
    data = os.path.join(root, "data")
    cache = os.path.join(root, "cache")
    universe = read_csv(os.path.join(data, "universe.csv"))
    scores = read_csv(os.path.join(data, "scores.csv"))
    info = read_csv(os.path.join(cache, "yahoo_info.csv"))
    annual = read_csv(os.path.join(cache, "annual.csv"))
    holders = read_csv(os.path.join(cache, "holders.csv"))
    earn = read_csv(os.path.join(cache, "earnings.csv"))
    cursor = load_cursor(cache)
    if len(universe) == 0:
        return pd.DataFrame()
    names = []
    for raw in universe["ticker"].astype(str):
        ticker = raw.strip().upper()
        if ticker and not ticker.startswith("^"):
            names.append(ticker)
    total = len(dict.fromkeys(names))
    if total == 0:
        return pd.DataFrame()
    spec = batch_cfg(cfg)
    today = today_ist()
    refresh = {"statements": spec["statements_refresh_days"], "shareholding": spec["shareholding_refresh_days"]}
    annual_set = _ticker_set(annual)
    info_set = _ticker_set(info)
    hold_map = _row_map(holders)
    covered_s = len([t for t in dict.fromkeys(names) if t in annual_set or t in info_set])
    covered_h = len([t for t in dict.fromkeys(names) if shareholding_covered(hold_map.get(t))])
    missing_any = covered_s < total or covered_h < total
    cycle = PASS_NOTE if missing_any else REFRESH_NOTE
    last_at = str(cursor.get("last_batch_at") or "not yet")

    def row(kind, covered, ok_key, fail_key):
        queue = build_queue(universe, scores, info, annual, holders, earn, cursor, today, refresh, kind)
        nxt = ""
        for rec in queue:
            if rec["due"]:
                nxt = rec["ticker"]
                break
        pct = round(100.0 * covered / total, 1) if total else 0
        return {
            "kind": kind,
            "covered": int(covered),
            "total": int(total),
            "pct": pct,
            "last_batch_at": last_at,
            "last_ok": int(cursor.get(ok_key) or 0),
            "last_fail": int(cursor.get(fail_key) or 0),
            "next_name": nxt or "none",
            "cycle_note": cycle,
            "data_status": "OK",
            "note": cycle,
            "disclaimer": tables.DISCLAIMER,
        }

    frame = pd.DataFrame([
        row("statements", covered_s, "last_statements_ok", "last_statements_fail"),
        row("shareholding", covered_h, "last_shareholding_ok", "last_shareholding_fail"),
    ])
    return frame


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    max_names = None
    if "--max-names" in argv:
        i = argv.index("--max-names")
        max_names = int(argv[i + 1])
    root = root_dir()
    cfg = load_cfg(root)
    if not enabled(cfg):
        print("Fundamentals backfill is off in config.json.")
        return 0
    run_batch(root, cfg, max_names=max_names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
