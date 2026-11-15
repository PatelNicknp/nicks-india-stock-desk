"""Free public sources for Indian stocks. No API keys.

NSE often blocks a bare data-center request. These helpers send a normal browser
header, wait between calls, and keep the last good file when a call fails.
"""
import io
import re
import time
import datetime as dt
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

import netutil

IST = "Asia/Kolkata"
PT = "America/Los_Angeles"

BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,text/html,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# About three years of sessions, plus a little so a 200-day average is warm.
KEEP_DAYS = int(365.25 * 3) + 40
CANDLE_SESSIONS = 756

INDEX_URLS = {
    "nifty50": [
        "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
        "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    ],
    "next50": [
        "https://www.niftyindices.com/IndexConstituent/ind_niftynext50list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv",
        "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv",
    ],
    "midcap150": [
        "https://www.niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
        "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    ],
    "smallcap250": [
        "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
        "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    ],
    "microcap250": [
        "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
        "https://archives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
    ],
    "totalmarket": [
        "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
        "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
    ],
}

WIKI_URLS = {
    "nifty50": "https://en.wikipedia.org/wiki/NIFTY_50",
    "next50": "https://en.wikipedia.org/wiki/NIFTY_Next_50",
}

# Latest filing assumed public 45 days after the period ends. The free feed has no filing date.
LAG_DAYS = 45

LINE_MAP = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "net_income": ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"],
    "eps": ["Diluted EPS", "Basic EPS"],
    "gross_profit": ["Gross Profit"],
    "op_income": ["Operating Income", "EBIT"],
    "equity": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
    "debt": ["Total Debt"],
    "ocf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure"],
    "dividends_paid": ["Cash Dividends Paid"],
    "shares": ["Ordinary Shares Number", "Share Issued", "Diluted Average Shares"],
}

RSS_FEEDS = [
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("LiveMint", "https://www.livemint.com/rss/markets"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Google News", "https://news.google.com/rss/search?q=India+stock+market&hl=en-IN&gl=IN&ceid=IN:en"),
    ("NDTV Profit", "https://feeds.feedburner.com/ndtvprofit-latest"),
    ("Reuters India", "https://www.reuters.com/arc/outboundfeeds/rss/category/business/india/?outputType=xml"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
]

WORLD_BANK = [
    ("Inflation", "CPI", "FP.CPI.TOTL.ZG",  -1, "India CPI inflation, yearly percent. World Bank. Not a monthly print."),
    ("Growth", "GDP", "NY.GDP.MKTP.KD.ZG", 1, "India real GDP growth, yearly percent. World Bank."),
    ("Growth", "IIP", "NV.IND.TOTL.KD.ZG", 1, "India industry growth, yearly percent. World Bank. This is not the monthly IIP."),
]


def yahoo_symbol(ticker):
    t = str(ticker or "").strip().upper()
    if not t:
        return t
    if t.startswith("^") or t.endswith("=X") or t.endswith(".NS") or t.endswith(".BO"):
        return t
    return t + ".NS"


def display_symbol(yahoo):
    t = str(yahoo or "").strip()
    if t.upper().endswith(".NS"):
        return t[:-3].upper()
    return t.upper()


def bench_column(close):
    if close is None:
        return None
    cols = set(map(str, getattr(close, "columns", [])))
    if "^NSEI" in cols:
        return "^NSEI"
    if "SPY" in cols:
        return "SPY"
    return None


def bank_column(close):
    if close is None:
        return None
    cols = set(map(str, getattr(close, "columns", [])))
    if "^NSEBANK" in cols:
        return "^NSEBANK"
    if "QQQ" in cols:
        return "QQQ"
    return None


def vix_column(close):
    if close is None:
        return None
    cols = set(map(str, getattr(close, "columns", [])))
    if "^INDIAVIX" in cols:
        return "^INDIAVIX"
    if "^VIX" in cols:
        return "^VIX"
    return None


def now_stamp():
    ist = pd.Timestamp.now(tz=IST).strftime("%Y-%m-%d %H:%M IST")
    pt = pd.Timestamp.now(tz=PT).strftime("%Y-%m-%d %H:%M PT")
    return "%s · %s" % (ist, pt)


def merge_price_history(old, new, keep_days=KEEP_DAYS):
    """Keep the saved bars and replace any day the new download also has."""
    frames = []
    for df in (old, new):
        if df is None or len(df) == 0:
            continue
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])
    both = pd.concat(frames, ignore_index=True)
    both["date"] = pd.to_datetime(both["date"], errors="coerce")
    both = both.dropna(subset=["date", "ticker", "close"])
    both["ticker"] = both["ticker"].astype(str).str.upper()
    both = both.sort_values("date").drop_duplicates(["ticker", "date"], keep="last")
    if len(both):
        cutoff = both["date"].max() - pd.Timedelta(days=int(keep_days))
        both = both[both["date"] >= cutoff]
    both["date"] = both["date"].dt.strftime("%Y-%m-%d")
    return both.reset_index(drop=True)


def _pick(frame, names):
    if frame is None or len(getattr(frame, "index", [])) == 0:
        return None
    idx = {str(i).strip().lower(): i for i in frame.index}
    for name in names:
        key = name.lower()
        if key in idx:
            return frame.loc[idx[key]]
    return None


def _cell(series, col):
    if series is None:
        return np.nan
    try:
        val = series[col] if col in series.index else series.get(col)
    except Exception:
        return np.nan
    try:
        if isinstance(val, pd.Series):
            val = val.dropna()
            if not len(val):
                return np.nan
            val = val.iloc[0]
        num = float(val)
    except (TypeError, ValueError):
        return np.nan
    if not np.isfinite(num):
        return np.nan
    return num


def _frames_to_rows(ticker, income, balance, cash, quarterly):
    if income is None or len(getattr(income, "columns", [])) == 0:
        return []
    rows = []
    for col in list(income.columns):
        end = pd.to_datetime(col, errors="coerce")
        if pd.isna(end):
            continue
        year = int(end.year)
        if quarterly:
            quarter = (int(end.month) - 1) // 3 + 1
            frame = "CY%dQ%d" % (year, quarter)
        else:
            frame = "CY%d" % year
        shares = _cell(_pick(balance, LINE_MAP["shares"]), col)
        if not np.isfinite(shares):
            shares = _cell(_pick(income, ["Diluted Average Shares", "Basic Average Shares"]), col)
        div_paid = _cell(_pick(cash, LINE_MAP["dividends_paid"]), col)
        dps = np.nan
        if np.isfinite(div_paid) and np.isfinite(shares) and shares > 0:
            dps = abs(div_paid) / shares
        capex = _cell(_pick(cash, LINE_MAP["capex"]), col)
        if np.isfinite(capex):
            capex = abs(capex)
        filed = (end + pd.Timedelta(days=LAG_DAYS)).strftime("%Y-%m-%d")
        rows.append({
            "ticker": ticker,
            "frame": frame,
            "end": end.strftime("%Y-%m-%d"),
            "filed": filed,
            "revenue": _cell(_pick(income, LINE_MAP["revenue"]), col),
            "net_income": _cell(_pick(income, LINE_MAP["net_income"]), col),
            "eps": _cell(_pick(income, LINE_MAP["eps"]), col),
            "gross_profit": _cell(_pick(income, LINE_MAP["gross_profit"]), col),
            "op_income": _cell(_pick(income, LINE_MAP["op_income"]), col),
            "equity": _cell(_pick(balance, LINE_MAP["equity"]), col),
            "debt": _cell(_pick(balance, LINE_MAP["debt"]), col),
            "ocf": _cell(_pick(cash, LINE_MAP["ocf"]), col),
            "capex": capex,
            "dps": dps,
            "shares": shares,
        })
    return rows


def fetch_yahoo_bundle(ticker, cfg, symbol=None):
    """One name: profile, earnings dates, and annual plus quarterly statements."""
    import yfinance as yf
    import company_lines
    symbol = symbol or yahoo_symbol(ticker)
    delays = tuple((cfg.get("rate_limit") or {}).get("backoff_seconds") or (1.5, 3, 6, 12))
    tries = int((cfg.get("rate_limit") or {}).get("max_retries") or 4)

    def once():
        tk = yf.Ticker(symbol)
        inf = tk.info or {}
        if not inf.get("shortName") and not inf.get("longName") and inf.get("regularMarketPrice") is None:
            raise netutil.RetryableError("empty profile " + symbol)
        annual = _frames_to_rows(ticker, tk.income_stmt, tk.balance_sheet, tk.cashflow, False)
        quarters = _frames_to_rows(ticker, tk.quarterly_income_stmt, tk.quarterly_balance_sheet, tk.quarterly_cashflow, True)
        erows = []
        try:
            ed = tk.earnings_dates
        except Exception:
            ed = None
        if ed is not None and len(ed):
            ed = ed.reset_index()
            for _, r in ed.iterrows():
                erows.append({
                    "ticker": ticker,
                    "earnings_dt": str(r.iloc[0]),
                    "eps_estimate": r.get("EPS Estimate"),
                    "eps_actual": r.get("Reported EPS"),
                    "surprise_pct": r.get("Surprise(%)"),
                })
        info = {
            "ticker": ticker,
            "company": inf.get("shortName") or inf.get("longName") or "",
            "sector": inf.get("sector") or "",
            "industry": inf.get("industry") or "",
            "forward_pe": inf.get("forwardPE"),
            "analyst_mean": inf.get("recommendationMean"),
            "analyst_count": inf.get("numberOfAnalystOpinions"),
            "target_mean": inf.get("targetMeanPrice"),
            "target_median": inf.get("targetMedianPrice"),
            "earnings_ts": inf.get("earningsTimestamp"),
            # Statement units. Quote currency is often INR for .NS even when Yahoo's
            # income statement is in USD, so this is financialCurrency, not currency.
            "financial_currency": inf.get("financialCurrency") or "",
            # Already in the same profile reply, so the company line costs no extra request.
            "summary": company_lines.keep_summary(inf.get("longBusinessSummary") or ""),
        }
        return info, annual, quarters, erows

    return netutil.call_with_retry(once, max_tries=tries, delays=delays)


def parse_constituent_frame(table, flag):
    """One Nifty CSV or Wikipedia table. Blank sector stays blank."""
    t = table.copy()
    if isinstance(t.columns, pd.MultiIndex):
        t.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in t.columns]
    t.columns = [str(c).replace("\ufeff", "").strip() for c in t.columns]
    lookup = {c.lower(): c for c in t.columns}
    sym = next((lookup[k] for k in lookup if k in ("symbol", "ticker") or k.startswith("symbol")), None)
    if sym is None or len(t) < 20:
        return None
    name = next((lookup[k] for k in lookup if k in ("company name", "company", "security") or k.startswith("company")), None)
    sec = next((lookup[k] for k in lookup if k in ("industry", "sector") or "sector" in k), None)
    tickers = (
        t[sym].astype(str)
        .str.replace(r"\[.*?\]", "", regex=True)
        .str.replace("\ufeff", "", regex=False)
        .str.upper()
        .str.strip()
    )
    df = pd.DataFrame({
        "ticker": tickers,
        "company": t[name].astype(str).str.replace(r"\[.*?\]", "", regex=True).str.strip() if name else "",
        "sector": t[sec].astype(str).str.replace(r"\[.*?\]", "", regex=True).str.strip() if sec else "",
    })
    df = df[df["ticker"].str.fullmatch(r"[A-Z0-9&-]{1,20}")]
    df = df.drop_duplicates("ticker")
    if len(df) < 20:
        return None
    df[flag] = "yes"
    return df.reset_index(drop=True)


def fetch_index_table(key, cfg):
    """Try niftyindices, then the NSE archive CSV, then Wikipedia."""
    headers = dict(BROWSER)
    headers["User-Agent"] = (cfg.get("rate_limit") or {}).get("sec_user_agent") or BROWSER["User-Agent"]
    # A browser-like agent works on the NSE archive. A research agent is fine for Wikipedia.
    errors = []
    for url in INDEX_URLS.get(key, []):
        try:
            r = netutil.http_get(requests, url, BROWSER, 30, max_tries=2, delays=(1.5, 3.0))
            if "symbol" not in r.text.lower() and "ticker" not in r.text.lower():
                raise netutil.PermanentError("not a constituent file")
            table = pd.read_csv(io.StringIO(r.text))
            df = parse_constituent_frame(table, "in_" + key)
            if df is not None:
                return df, url
        except Exception as exc:
            errors.append(str(exc)[:80])
    wiki = WIKI_URLS.get(key)
    if wiki:
        try:
            r = netutil.http_get(requests, wiki, {"User-Agent": BROWSER["User-Agent"]}, 40, max_tries=2)
            tables = pd.read_html(io.StringIO(r.text))
            for table in tables:
                df = parse_constituent_frame(table, "in_" + key)
                if df is not None:
                    return df, wiki
        except Exception as exc:
            errors.append("wiki " + str(exc)[:80])
    raise RuntimeError("; ".join(errors)[:240] or "no constituent list")


def nse_get(url, cfg):
    delays = tuple((cfg.get("rate_limit") or {}).get("backoff_seconds") or (1.5, 3, 6, 12))
    tries = int((cfg.get("rate_limit") or {}).get("max_retries") or 3)
    return netutil.http_get(requests, url, BROWSER, 30, max_tries=min(tries, 3), delays=delays)


def _pct_num(value):
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text in ("", "-", "NA", "N/A", "None"):
        return None
    try:
        num = float(text)
    except ValueError:
        return None
    if not np.isfinite(num):
        return None
    return num


def fetch_shareholding_master(symbol, cfg):
    url = "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=%s" % quote(str(symbol), safe="")
    payload = nse_get(url, cfg).json()
    if not isinstance(payload, list) or not payload:
        return []
    rows = []
    for item in payload:
        as_of = item.get("date") or ""
        try:
            as_of = pd.to_datetime(as_of, dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            as_of = str(as_of)
        rows.append({
            "as_of": as_of,
            "promoter_pct": _pct_num(item.get("pr_and_prgrp")),
            "public_broad_pct": _pct_num(item.get("public_val")),
            "xbrl": item.get("xbrl") or "",
            "name": item.get("name") or "",
        })
    rows.sort(key=lambda r: r["as_of"])
    return rows


def parse_shareholding_xbrl(text):
    """Promoter, foreign institutions, Indian institutions, and other public."""
    ctx = {}
    for match in re.finditer(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', text, re.S):
        body = match.group(2)
        member = re.search(r">([^<]*Member)<", body)
        instant = re.search(r"<xbrli:instant>([^<]+)</xbrli:instant>", body)
        ctx[match.group(1)] = (
            member.group(1) if member else "",
            instant.group(1) if instant else "",
        )
    want = {
        "in-bse-shp:ShareholdingOfPromoterAndPromoterGroupMember": "promoter_pct",
        "in-bse-shp:InstitutionsForeignMember": "fii_pct",
        "in-bse-shp:InstitutionsDomesticMember": "dii_pct",
        "in-bse-shp:NonInstitutionsMember": "public_pct",
    }
    found = {}
    pattern = re.compile(
        r'<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares[^>]*contextRef="([^"]+)"[^>]*>([^<]+)</'
    )
    for cid, raw in pattern.findall(text):
        member, instant = ctx.get(cid, ("", ""))
        key = want.get(member)
        if not key or not instant:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        # The filing stores 0.5044 for 50.44 percent.
        if 0 <= val <= 1.5:
            val = val * 100.0
        found.setdefault(key, {})[instant[:10]] = round(val, 2)
    if not found:
        return {}
    days = sorted({day for by_day in found.values() for day in by_day})
    history = []
    for day in days:
        history.append({
            "as_of": day,
            "quarter_end": quarter_end(day),
            "promoter_pct": found.get("promoter_pct", {}).get(day),
            "fii_pct": found.get("fii_pct", {}).get(day),
            "dii_pct": found.get("dii_pct", {}).get(day),
            "public_pct": found.get("public_pct", {}).get(day),
        })
    out = {}
    latest, prior = latest_and_prior(history)
    if latest:
        for key in ("promoter_pct", "fii_pct", "dii_pct", "public_pct"):
            out[key] = latest.get(key)
        out["as_of"] = latest.get("as_of") or ""
    if latest and prior:
        out.update(changes_from_levels(latest, prior))
    out["_history"] = history
    return out


def fetch_xbrl_split(url, cfg):
    if not url:
        return {}
    text = nse_get(url, cfg).text
    return parse_shareholding_xbrl(text)


def collect_nse_shareholding(symbol, cfg, xbrl_limit=4):
    """Latest NSE shareholding row plus a quarter history from recent XBRL filings.

    The master list has promoter levels for many quarters, but FII and DII live in
    the XBRL. One filing often has only the current quarter, so this downloads
    up to xbrl_limit recent files and computes the change from consecutive levels.
    """
    history = fetch_shareholding_master(symbol, cfg)
    split = {}
    all_hist = []
    wanted = [item for item in (history or []) if item.get("xbrl")]
    # Newest last; take the last xbrl_limit filings.
    for item in wanted[-max(1, int(xbrl_limit or 1)):]:
        try:
            parsed = fetch_xbrl_split(item.get("xbrl"), cfg) or {}
        except Exception:
            parsed = {}
        if parsed:
            split = parsed
        for rec in (parsed.get("_history") or []):
            all_hist.append(history_record(
                symbol, rec.get("as_of") or item.get("as_of"),
                rec.get("promoter_pct"), rec.get("fii_pct"), rec.get("dii_pct"),
                rec.get("public_pct"), "NSE shareholding",
            ))
        if parsed and not parsed.get("_history"):
            all_hist.append(history_record(
                symbol, parsed.get("as_of") or item.get("as_of"),
                parsed.get("promoter_pct"), parsed.get("fii_pct"),
                parsed.get("dii_pct"), parsed.get("public_pct"),
                "NSE shareholding",
            ))
    if split:
        split = dict(split)
        split["_history"] = (split.get("_history") or []) + all_hist
    row = shareholding_row(symbol, history, split)
    return row


def _chg(new, old):
    if new is None or old is None:
        return None
    return round(float(new) - float(old), 2)


HOLDERS_HISTORY_COLS = (
    "ticker", "as_of", "quarter_end",
    "promoter_pct", "fii_pct", "dii_pct", "public_pct", "source",
)


def quarter_end(value):
    """Map a date or 'Sep 2026' label to the calendar quarter end, for joining sources."""
    text = str(value or "").strip()
    if not text or text.lower() in ("nan", "none"):
        return ""
    try:
        stamp = pd.to_datetime(text, errors="coerce")
    except Exception:
        return ""
    if stamp is None or pd.isna(stamp):
        return ""
    stamp = pd.Timestamp(stamp)
    q = ((int(stamp.month) - 1) // 3) + 1
    month = q * 3
    day = 31 if month in (3, 12) else 30
    return pd.Timestamp(year=int(stamp.year), month=month, day=day).strftime("%Y-%m-%d")


def _blank_num(value):
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return _pct_num(value) if not isinstance(value, (int, float)) else (None if not np.isfinite(float(value)) else float(value))


def changes_from_levels(latest, prior):
    """FII, DII, promoter, and public point changes between two quarter snapshots."""
    latest = latest or {}
    prior = prior or {}
    out = {}
    for key in ("promoter", "fii", "dii", "public"):
        out[key + "_chg"] = _chg(_blank_num(latest.get(key + "_pct")), _blank_num(prior.get(key + "_pct")))
    return out


def history_record(ticker, as_of, promoter=None, fii=None, dii=None, public=None, source=""):
    end = quarter_end(as_of)
    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of": str(as_of or "")[:10] or end,
        "quarter_end": end,
        "promoter_pct": _blank_num(promoter),
        "fii_pct": _blank_num(fii),
        "dii_pct": _blank_num(dii),
        "public_pct": _blank_num(public),
        "source": source or "",
    }


def latest_and_prior(rows):
    """Newest and previous distinct quarter from a list of history records."""
    usable = []
    seen = set()
    for row in sorted((rows or []), key=lambda r: r.get("quarter_end") or r.get("as_of") or ""):
        key = row.get("quarter_end") or row.get("as_of") or ""
        if not key or key in seen:
            # Later row for the same quarter overwrites the earlier one.
            if key and usable and (usable[-1].get("quarter_end") or usable[-1].get("as_of")) == key:
                usable[-1] = row
            continue
        seen.add(key)
        usable.append(row)
    if not usable:
        return None, None
    if len(usable) == 1:
        return usable[-1], None
    return usable[-1], usable[-2]


def apply_history_changes(row, history_rows):
    """Fill missing FII/DII (and other) quarter changes from consecutive saved levels."""
    row = dict(row or {})
    latest, prior = latest_and_prior(history_rows)
    if not latest or not prior:
        return row
    chg = changes_from_levels(latest, prior)
    for key, val in chg.items():
        if val is None:
            continue
        cur = row.get(key)
        if cur is None or cur == "":
            row[key] = val
            continue
        try:
            if pd.isna(cur):
                row[key] = val
        except (TypeError, ValueError):
            pass
    return row


def merge_holders_history(old, new_rows):
    """Union on ticker + quarter_end. A newer row fills blank cells and can replace levels."""
    add = list(new_rows or [])
    if old is None or len(old) == 0:
        return pd.DataFrame(add, columns=list(HOLDERS_HISTORY_COLS)) if add else pd.DataFrame(columns=list(HOLDERS_HISTORY_COLS))
    frame = old.copy()
    if add:
        frame = pd.concat([frame, pd.DataFrame(add)], ignore_index=True)
    if len(frame) == 0:
        return pd.DataFrame(columns=list(HOLDERS_HISTORY_COLS))
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    if "quarter_end" not in frame.columns:
        frame["quarter_end"] = frame.get("as_of", pd.Series(dtype=str)).map(quarter_end)
    else:
        missing = frame["quarter_end"].isna() | (frame["quarter_end"].astype(str).str.strip() == "")
        if missing.any():
            frame.loc[missing, "quarter_end"] = frame.loc[missing, "as_of"].map(quarter_end)
    frame = frame[frame["ticker"].ne("") & frame["quarter_end"].astype(str).str.len().ge(10)]
    # Keep the last row for each ticker+quarter so a refresh wins.
    frame = frame.drop_duplicates(["ticker", "quarter_end"], keep="last")
    cols = [c for c in HOLDERS_HISTORY_COLS if c in frame.columns] + [c for c in frame.columns if c not in HOLDERS_HISTORY_COLS]
    return frame[cols].reset_index(drop=True)


def enrich_holders_from_history(holders, history):
    """Copy computed FII+DII changes onto the latest holders row when those cells are blank."""
    if holders is None or len(holders) == 0 or history is None or len(history) == 0:
        return holders
    if "ticker" not in holders.columns or "ticker" not in history.columns:
        return holders
    out = holders.copy()
    hist_map = {}
    for rec in history.to_dict("records"):
        ticker = str(rec.get("ticker") or "").strip().upper()
        if ticker:
            hist_map.setdefault(ticker, []).append(rec)
    rows = []
    for rec in out.to_dict("records"):
        ticker = str(rec.get("ticker") or "").strip().upper()
        rows.append(apply_history_changes(rec, hist_map.get(ticker) or []))
    return pd.DataFrame(rows)


def shareholding_row(symbol, history, split):
    """Latest quarter, with the change versus the prior quarter when we have it."""
    if not history and not split:
        return None
    latest = history[-1] if history else {}
    prior = history[-2] if len(history) > 1 else {}
    promoter = split.get("promoter_pct")
    if promoter is None:
        promoter = latest.get("promoter_pct")
    public = split.get("public_pct")
    # Master "public" includes institutions. Use the non-institution line from the filing when we have it.
    if public is None:
        public = None
    fii = split.get("fii_pct")
    dii = split.get("dii_pct")
    promoter_chg = _chg(latest.get("promoter_pct"), prior.get("promoter_pct"))
    if promoter_chg is None:
        promoter_chg = split.get("promoter_chg")
    row = {
        "ticker": symbol,
        "promoter_pct": promoter,
        "fii_pct": fii,
        "dii_pct": dii,
        "public_pct": public,
        "promoter_chg": promoter_chg,
        "fii_chg": split.get("fii_chg"),
        "dii_chg": split.get("dii_chg"),
        "public_chg": split.get("public_chg"),
        "as_of": split.get("as_of") or latest.get("as_of") or "",
        "company": latest.get("name") or "",
        "source": "NSE shareholding" if split else "NSE shareholding summary",
    }
    hist = list(split.get("_history") or [])
    # Master rows usually have promoter only. Still store the date so later FII/DII can join.
    for item in (history or []):
        hist.append(history_record(
            symbol, item.get("as_of"), item.get("promoter_pct"),
            item.get("fii_pct"), item.get("dii_pct"), item.get("public_pct"),
            "NSE shareholding",
        ))
    tagged = []
    for item in hist:
        rec = dict(item)
        rec.setdefault("ticker", str(symbol or "").strip().upper())
        rec.setdefault("source", row["source"])
        rec["quarter_end"] = rec.get("quarter_end") or quarter_end(rec.get("as_of"))
        tagged.append(rec)
    row = apply_history_changes(row, tagged)
    row["_history"] = tagged
    return row


def fetch_pit_counts(symbol, cfg, months=3):
    url = "https://www.nseindia.com/api/corporates-pit?index=equities&symbol=%s" % quote(str(symbol), safe="")
    payload = nse_get(url, cfg).json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not rows:
        return None, None
    cutoff = pd.Timestamp.now(tz=IST).tz_localize(None) - pd.DateOffset(months=months)
    buys = sells = 0
    seen = False
    for item in rows:
        kind = str(item.get("secType") or "")
        if "equity" not in kind.lower():
            continue
        when = item.get("acqtoDt") or item.get("date") or ""
        try:
            day = pd.to_datetime(str(when)[:11], dayfirst=True, errors="coerce")
        except Exception:
            day = pd.NaT
        if pd.isna(day) or day < cutoff:
            continue
        side = str(item.get("tdpTransactionType") or "").lower()
        if "buy" in side:
            buys += 1
            seen = True
        elif "sell" in side:
            sells += 1
            seen = True
    if not seen:
        return 0, 0
    return buys, sells


def fetch_fii_dii(cfg):
    payload = nse_get("https://www.nseindia.com/api/fiidiiTradeReact", cfg).json()
    if not isinstance(payload, list):
        return []
    out = []
    for item in payload:
        day = item.get("date") or ""
        try:
            day = pd.to_datetime(day, dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            day = str(day)
        out.append({
            "date": day,
            "category": item.get("category") or "",
            "buy_cr": _pct_num(item.get("buyValue")),
            "sell_cr": _pct_num(item.get("sellValue")),
            "net_cr": _pct_num(item.get("netValue")),
        })
    return out


def _oi(node):
    if not isinstance(node, dict):
        return None
    try:
        val = float(node.get("openInterest"))
    except (TypeError, ValueError):
        return None
    if not np.isfinite(val):
        return None
    return val


def fetch_option_walls(symbol, kind, cfg):
    """Nearest expiry only. kind is Indices or Equity."""
    info = nse_get("https://www.nseindia.com/api/option-chain-contract-info?symbol=%s" % quote(str(symbol), safe=""), cfg).json()
    expiries = info.get("expiryDates") or []
    if not expiries:
        return [], None
    expiry = expiries[0]
    url = "https://www.nseindia.com/api/option-chain-v3?type=%s&symbol=%s&expiry=%s" % (
        quote(str(kind), safe=""), quote(str(symbol), safe=""), quote(str(expiry), safe=""),
    )
    payload = nse_get(url, cfg).json()
    data = ((payload.get("records") or {}).get("data")) or []
    rows = []
    put_oi = call_oi = 0.0
    for item in data:
        for side, key in (("call", "CE"), ("put", "PE")):
            node = item.get(key) or {}
            oi = _oi(node)
            if oi is None or oi <= 0:
                continue
            if side == "call":
                call_oi += oi
            else:
                put_oi += oi
            strike = node.get("strikePrice")
            if strike is None:
                strike = item.get("strikePrice")
            rows.append({
                "ticker": symbol,
                "expiry": expiry,
                "side": side,
                "strike": strike,
                "open_interest": oi,
                "volume": node.get("totalTradedVolume"),
            })
    if not rows:
        return [], None
    df = pd.DataFrame(rows)
    df["is_wall"] = "no"
    for side, g in df.groupby("side"):
        idx = pd.to_numeric(g["open_interest"], errors="coerce").idxmax()
        df.at[idx, "is_wall"] = "yes"
    ratio = None
    if call_oi > 0:
        ratio = round(put_oi / call_oi, 4)
    return df.to_dict("records"), ratio


def clean_headline(text):
    title = re.sub(r"<!\[CDATA\[|\]\]>", "", str(text or ""))
    title = re.sub(r"<[^>]+>", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def fetch_rss(cfg):
    rows = []
    for publisher, url in RSS_FEEDS:
        try:
            r = netutil.http_get(requests, url, {"User-Agent": BROWSER["User-Agent"], "Accept": "application/rss+xml,application/xml,text/xml,*/*"}, 25, max_tries=2)
        except Exception:
            continue
        titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", r.text, re.S)
        links = re.findall(r"<link>(.*?)</link>", r.text, re.S)
        dates = re.findall(r"<pubDate>(.*?)</pubDate>", r.text, re.S)
        # The first title is the feed name.
        for i, title in enumerate(titles[1:16]):
            title = clean_headline(title)
            if len(title) < 24 or title.lower() == publisher.lower():
                continue
            link = links[i + 1] if i + 1 < len(links) else (links[i] if i < len(links) else "")
            published = dates[i] if i < len(dates) else ""
            try:
                published = pd.to_datetime(published).tz_convert(IST).strftime("%Y-%m-%d %H:%M IST")
            except Exception:
                published = str(published)[:40]
            rows.append({
                "ticker": "MARKET",
                "headline": title,
                "publisher": publisher,
                "link": link.strip(),
                "published": published,
            })
        time.sleep(0.3)
    seen = set()
    unique = []
    for row in rows:
        key = re.sub(r"[^a-z0-9]+", " ", row["headline"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def fetch_world_bank():
    rows = []
    for cat, label, code, good, note in WORLD_BANK:
        url = "https://api.worldbank.org/v2/country/IN/indicator/%s?format=json&per_page=8" % code
        try:
            r = netutil.http_get(requests, url, {"User-Agent": BROWSER["User-Agent"]}, 25, max_tries=2)
            payload = r.json()
        except Exception:
            continue
        series = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        latest = None
        for item in series or []:
            if item and item.get("value") is not None:
                latest = item
                break
        if not latest:
            continue
        rows.append({
            "country": "India",
            "category": cat,
            "indicator": label,
            "date": "%s-12-31" % latest.get("date"),
            "actual": latest.get("value"),
            "forecast": "",
            "surprise": "",
            "signal": "",
            "source": "World Bank",
            "note": note + " No forecast in this free feed, so there is no surprise score.",
        })
    return rows


def vix_zone(value):
    if value is None or not np.isfinite(value):
        return ""
    if value < 13:
        return "Calm"
    if value <= 18:
        return "Normal"
    return "Fear"


def trend_from_change(change, band=0.25):
    """Map a percentage-point change to the up/down counts the score already understands."""
    if change is None or not np.isfinite(change):
        return None, None
    if change > band:
        return 1.0, 0.0
    if change < -band:
        return 0.0, 1.0
    return 1.0, 1.0
