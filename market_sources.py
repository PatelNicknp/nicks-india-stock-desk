"""Daily prices and lists from free public files.

NSE bhavcopy is the main price file. BSE bhavcopy fills names that are not on
the NSE. Stooq and Yahoo are only a small gap fill. Index levels prefer the
NSE close file.
"""
import io
import json
import os
import time
import zipfile
import datetime as dt
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

import fallback
import india_data
import netutil


MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
NSE_EQUITY = {"EQ", "BE", "BZ"}
NSE_SME = {"SM"}
# A, B, T, X, XT are the main BSE equity groups. Z and P are still shares.
# F, E, G are funds, ETFs, and government bonds. M and MT are the SME board.
BSE_EQUITY = {"A", "B", "T", "X", "XT", "Z", "P"}
BSE_SME = {"M", "MT", "MS"}
UDIFF_CUTOFF = dt.date(2024, 7, 8)

INDEX_NAMES = {
    "nifty 50": "^NSEI",
    "nifty bank": "^NSEBANK",
    "nifty it": "^CNXIT",
    "nifty pharma": "^CNXPHARMA",
    "nifty financial services": "^CNXFIN",
    "nifty auto": "^CNXAUTO",
    "nifty fmcg": "^CNXFMCG",
    "nifty metal": "^CNXMETAL",
    "nifty realty": "^CNXREALTY",
    "nifty energy": "^CNXENERGY",
    "nifty media": "^CNXMEDIA",
    "nifty psu bank": "^CNXPSUBANK",
    "nifty infrastructure": "^CNXINFRA",
    "india vix": "^INDIAVIX",
}


def _pause(cfg):
    try:
        return float((cfg.get("rate_limit") or {}).get("bhav_pause_seconds") or 0.2)
    except (TypeError, ValueError):
        return 0.2


def _get(url, cfg, timeout=40):
    headers = dict(india_data.BROWSER)
    if "bseindia" in url:
        headers["Referer"] = "https://www.bseindia.com/"
    return netutil.http_get(requests, url, headers, timeout, max_tries=2, delays=(1.0, 3.0))


def _read_table(content):
    raw = content
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = zf.namelist()[0]
            raw = zf.read(name)
    text = raw.decode("utf-8", errors="replace")
    frame = pd.read_csv(io.StringIO(text))
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def _num(series):
    return pd.to_numeric(series, errors="coerce")


def parse_nse_bhav(content, sme=False):
    """One NSE cash bhavcopy, new or old layout, equities only."""
    frame = _read_table(content)
    keep = set(NSE_EQUITY)
    if sme:
        keep |= NSE_SME
    if "TckrSymb" in frame.columns:
        series = frame["SctySrs"].astype(str).str.strip().str.upper()
        kind = frame["FinInstrmTp"].astype(str).str.strip().str.upper() if "FinInstrmTp" in frame.columns else "STK"
        use = frame[(series.isin(keep)) & (kind.eq("STK") | kind.eq(""))].copy()
        if not len(use):
            return pd.DataFrame()
        out = pd.DataFrame({
            "date": pd.to_datetime(use["TradDt"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "ticker": use["TckrSymb"].astype(str).str.strip().str.upper(),
            "isin": use["ISIN"].astype(str).str.strip().str.upper() if "ISIN" in use.columns else "",
            "series": series.loc[use.index].values,
            "open": _num(use["OpnPric"]),
            "high": _num(use["HghPric"]),
            "low": _num(use["LwPric"]),
            "close": _num(use["ClsPric"]),
            "volume": _num(use["TtlTradgVol"]),
            "turnover": _num(use["TtlTrfVal"]),
            "source": "NSE bhavcopy",
        })
    elif "SYMBOL" in frame.columns:
        series = frame["SERIES"].astype(str).str.strip().str.upper()
        use = frame[series.isin(keep)].copy()
        if not len(use):
            return pd.DataFrame()
        stamp = use["TIMESTAMP"] if "TIMESTAMP" in use.columns else ""
        out = pd.DataFrame({
            "date": pd.to_datetime(stamp, errors="coerce").dt.strftime("%Y-%m-%d"),
            "ticker": use["SYMBOL"].astype(str).str.strip().str.upper(),
            "isin": use["ISIN"].astype(str).str.strip().str.upper() if "ISIN" in use.columns else "",
            "series": series.loc[use.index].values,
            "open": _num(use["OPEN"]),
            "high": _num(use["HIGH"]),
            "low": _num(use["LOW"]),
            "close": _num(use["CLOSE"]),
            "volume": _num(use["TOTTRDQTY"]),
            "turnover": _num(use["TOTTRDVAL"]),
            "source": "NSE bhavcopy",
        })
    else:
        return pd.DataFrame()
    out = out.dropna(subset=["date", "ticker", "close"])
    out = out[out["ticker"].str.fullmatch(r"[A-Z0-9&-]{1,20}")]
    return out.reset_index(drop=True)


def parse_bse_bhav(content, sme=False):
    """BSE cash bhavcopy. Funds, bonds, and ETFs are left out."""
    frame = _read_table(content)
    if "TckrSymb" not in frame.columns:
        return pd.DataFrame()
    series = frame["SctySrs"].astype(str).str.strip().str.upper()
    keep = set(BSE_EQUITY)
    if sme:
        keep |= BSE_SME
    kind = frame["FinInstrmTp"].astype(str).str.strip().str.upper() if "FinInstrmTp" in frame.columns else "STK"
    use = frame[series.isin(keep) & (kind.eq("STK") | kind.eq(""))].copy()
    if not len(use):
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(use["TradDt"], errors="coerce").dt.strftime("%Y-%m-%d"),
        "ticker": use["TckrSymb"].astype(str).str.strip().str.upper(),
        "isin": use["ISIN"].astype(str).str.strip().str.upper() if "ISIN" in use.columns else "",
        "series": series.loc[use.index].values,
        "bse_code": use["FinInstrmId"].astype(str).str.replace(r"\.0$", "", regex=True) if "FinInstrmId" in use.columns else "",
        "open": _num(use["OpnPric"]),
        "high": _num(use["HghPric"]),
        "low": _num(use["LwPric"]),
        "close": _num(use["ClsPric"]),
        "volume": _num(use["TtlTradgVol"]),
        "turnover": _num(use["TtlTrfVal"]),
        "source": "BSE bhavcopy",
    })
    out = out.dropna(subset=["date", "ticker", "close"])
    out = out[out["ticker"].str.fullmatch(r"[A-Z0-9&-]{1,20}")]
    return out.reset_index(drop=True)


def parse_index_close(content):
    frame = _read_table(content)
    if "Index Name" not in frame.columns:
        return pd.DataFrame()
    rows = []
    for _, item in frame.iterrows():
        code = INDEX_NAMES.get(str(item.get("Index Name") or "").strip().lower())
        if not code:
            continue
        day = pd.to_datetime(item.get("Index Date"), dayfirst=True, errors="coerce")
        if pd.isna(day):
            continue
        rows.append({
            "date": day.strftime("%Y-%m-%d"),
            "ticker": code,
            "isin": "",
            "series": "INDEX",
            "open": _as_float(item.get("Open Index Value")),
            "high": _as_float(item.get("High Index Value")),
            "low": _as_float(item.get("Low Index Value")),
            "close": _as_float(item.get("Closing Index Value")),
            "volume": _as_float(item.get("Volume")),
            "turnover": _as_float(item.get("Turnover (Rs. Cr.)")),
            "source": "NSE ind_close_all",
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).dropna(subset=["close"])


def _as_float(value):
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return np.nan
    if not np.isfinite(number):
        return np.nan
    return number


def nse_bhav_urls(day):
    mon = MONTHS[day.month - 1]
    stamp = "cm%02d%s%d" % (day.day, mon, day.year)
    old = [
        "https://archives.nseindia.com/content/historical/EQUITIES/%d/%s/%sbhav.csv.zip" % (day.year, mon, stamp),
        "https://nsearchives.nseindia.com/content/historical/EQUITIES/%d/%s/%sbhav.csv.zip" % (day.year, mon, stamp),
    ]
    new = [
        "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_%s_F_0000.csv.zip" % day.strftime("%Y%m%d"),
    ]
    if day >= UDIFF_CUTOFF:
        return new + old
    return old + new


def bse_bhav_urls(day):
    return [
        "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_%s_F_0000.CSV" % day.strftime("%Y%m%d"),
    ]


def index_urls(day):
    stamp = day.strftime("%d%m%Y")
    return [
        "https://nsearchives.nseindia.com/content/indices/ind_close_all_%s.csv" % stamp,
        "https://www.niftyindices.com/Daily_Snapshot/ind_close_all_%s.csv" % stamp,
    ]


SENSEX_TICKER = "^BSESN"


def bse_index_summary_urls(day):
    """One day of BSE index levels. The date is in the file name."""
    stamp = day.strftime("%d%m%Y")
    return [
        "https://www.bseindia.com/bsedata/Index_Bhavcopy/INDEXSummary_%s.csv" % stamp,
    ]


def parse_bse_index_summary(content, day):
    """The SENSEX row from a BSE index summary. Other indexes in that file are left out."""
    frame = _read_table(content)
    if frame is None or len(frame) == 0:
        return pd.DataFrame()
    cols = {str(c).strip().lower(): c for c in frame.columns}
    id_col = cols.get("indexid") or cols.get("index code") or cols.get("indexcode")
    name_col = cols.get("indexname") or cols.get("index name")
    if id_col is None and name_col is None:
        return pd.DataFrame()
    use = frame.iloc[0:0]
    if id_col is not None:
        use = frame[frame[id_col].astype(str).str.strip().str.upper().eq("SENSEX")]
    if not len(use) and name_col is not None:
        names = frame[name_col].astype(str).str.strip().str.upper()
        use = frame[names.eq("BSE SENSEX") | names.eq("SENSEX")]
    if not len(use):
        return pd.DataFrame()
    row = use.iloc[0]
    open_col = cols.get("openprice") or cols.get("open") or cols.get("open index value")
    high_col = cols.get("highprice") or cols.get("high") or cols.get("high index value")
    low_col = cols.get("lowprice") or cols.get("low") or cols.get("low index value")
    close_col = cols.get("closeprice") or cols.get("close") or cols.get("closing index value")
    if close_col is None:
        return pd.DataFrame()
    close = _as_float(row.get(close_col))
    if not np.isfinite(close):
        return pd.DataFrame()
    stamp = pd.Timestamp(day).strftime("%Y-%m-%d")
    return pd.DataFrame([{
        "date": stamp,
        "ticker": SENSEX_TICKER,
        "isin": "",
        "series": "INDEX",
        "open": _as_float(row.get(open_col)) if open_col else np.nan,
        "high": _as_float(row.get(high_col)) if high_col else np.nan,
        "low": _as_float(row.get(low_col)) if low_col else np.nan,
        "close": close,
        "volume": np.nan,
        "turnover": np.nan,
        "source": "BSE index file",
    }])


def _yahoo_index(symbol, cfg, start=None):
    bars = _yahoo_daily(symbol, cfg, start=start)
    if not len(bars):
        return bars
    out = bars.copy()
    out["ticker"] = str(symbol).upper()
    out["source"] = "Yahoo"
    return out


def _stooq_index(symbol):
    """Stooq daily bars for an index. The stock helper appends .in, which is wrong here."""
    url = "https://stooq.com/q/d/l/?s=%s&i=d" % quote(str(symbol).lower())
    try:
        if not fallback.robots_allows(url):
            return pd.DataFrame()
        response = requests.get(
            url,
            headers={"User-Agent": india_data.BROWSER["User-Agent"], "Accept": "text/csv"},
            timeout=15,
        )
        text = response.text or ""
        if response.status_code != 200 or "Date" not in text[:80] or "<html" in text[:200].lower():
            return pd.DataFrame()
        frame = pd.read_csv(io.StringIO(text))
    except Exception:
        return pd.DataFrame()
    if "Close" not in frame.columns:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(frame["Date"], errors="coerce").dt.strftime("%Y-%m-%d"),
        "ticker": str(symbol).upper(),
        "open": pd.to_numeric(frame.get("Open"), errors="coerce"),
        "high": pd.to_numeric(frame.get("High"), errors="coerce"),
        "low": pd.to_numeric(frame.get("Low"), errors="coerce"),
        "close": pd.to_numeric(frame["Close"], errors="coerce"),
        "volume": pd.to_numeric(frame.get("Volume"), errors="coerce"),
        "source": "Stooq",
    })
    return out.dropna(subset=["date", "close"])


def _sensex_dates(frame):
    if frame is None or len(frame) == 0 or "ticker" not in frame.columns:
        return set()
    sub = frame[frame["ticker"].astype(str).str.upper().eq(SENSEX_TICKER)]
    if not len(sub) or "date" not in sub.columns:
        return set()
    return set(pd.to_datetime(sub["date"], errors="coerce").dt.strftime("%Y-%m-%d").dropna())


def update_sensex(frame, cfg, session_dates):
    """SENSEX daily bars. BSE index file, then Yahoo ^BSESN, then Stooq.

    session_dates are the sessions already in the price cache, newest last.
    A run walks backward through missing sessions and stops after a run of
    misses, so an old gap does not hammer the BSE site. Yahoo fills the older
    years when the BSE file does not go back that far.
    """
    logs = []
    if not ((cfg or {}).get("features") or {}).get("sensex", True):
        logs.append(("Prices (SENSEX)", "OK", "", "SENSEX switch is off"))
        return frame, logs
    pause = _pause(cfg)
    have = _sensex_dates(frame)
    wanted = []
    for day in session_dates or []:
        stamp = pd.Timestamp(day).strftime("%Y-%m-%d")
        if stamp not in have:
            wanted.append(pd.Timestamp(day).date())
    wanted = sorted(set(wanted), reverse=True)
    parts = []
    misses = 0
    bse_n = 0
    for day in wanted:
        if bse_n and misses >= 12:
            break
        try:
            content, _url = _first_bytes(bse_index_summary_urls(day), cfg)
            bars = parse_bse_index_summary(content, day)
            if len(bars):
                parts.append(bars)
                bse_n += 1
                misses = 0
            else:
                misses += 1
        except Exception:
            misses += 1
        time.sleep(pause)
    bse = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    yahoo_n = 0
    stooq_n = 0
    covered = set(have)
    if len(bse):
        covered |= set(bse["date"].astype(str))
    wanted_stamps = [pd.Timestamp(day).strftime("%Y-%m-%d") for day in (session_dates or [])]
    need_yahoo = any(stamp not in covered for stamp in wanted_stamps) or not covered
    yahoo = pd.DataFrame()
    if need_yahoo:
        start = None
        if session_dates:
            start = pd.Timestamp(min(pd.Timestamp(day) for day in session_dates)).strftime("%Y-%m-%d")
        yahoo = _yahoo_index(SENSEX_TICKER, cfg, start=start)
        if len(yahoo):
            yahoo = yahoo[~yahoo["date"].astype(str).isin(covered)]
            yahoo_n = int(yahoo["date"].nunique()) if len(yahoo) else 0
            if len(yahoo):
                covered |= set(yahoo["date"].astype(str))
        time.sleep(pause)
    stooq = pd.DataFrame()
    still_open = any(stamp not in covered for stamp in wanted_stamps) or not covered
    if still_open:
        stooq = _stooq_index("^bsesn")
        if len(stooq):
            stooq["ticker"] = SENSEX_TICKER
            stooq = stooq[~stooq["date"].astype(str).isin(covered)]
            stooq_n = int(stooq["date"].nunique()) if len(stooq) else 0
    fresh = pd.concat([df for df in (bse, yahoo, stooq) if len(df)], ignore_index=True) if (len(bse) or len(yahoo) or len(stooq)) else pd.DataFrame()
    if len(fresh):
        fresh = fresh.drop(columns=[c for c in ("source",) if c in fresh.columns], errors="ignore")
        # Keep the columns the price cache already uses. A new column would land on every row.
        keep = [c for c in frame.columns if c in fresh.columns] if frame is not None and len(frame) else list(fresh.columns)
        if frame is not None and len(frame):
            for col in frame.columns:
                if col not in fresh.columns:
                    fresh[col] = np.nan if col not in ("isin", "series") else ""
            fresh = fresh[list(frame.columns)]
        elif keep:
            fresh = fresh[keep]
        frame = india_data.merge_price_history(frame, fresh)
    last = ""
    if frame is not None and len(frame) and "ticker" in frame.columns:
        sub = frame[frame["ticker"].astype(str).str.upper().eq(SENSEX_TICKER)]
        if len(sub):
            last = str(pd.to_datetime(sub["date"]).max().date())
    if bse_n or yahoo_n or stooq_n or last:
        status = "OK" if (bse_n or yahoo_n or stooq_n or last) else "MISSING"
        if stooq_n:
            stooq_txt = "Stooq filled %d." % stooq_n
        elif still_open:
            stooq_txt = "Stooq returned nothing for the remaining sessions."
        else:
            stooq_txt = "Stooq was not needed."
        note = "BSE index file %d sessions. Yahoo ^BSESN filled %d older sessions. %s" % (bse_n, yahoo_n, stooq_txt)
        if not (bse_n or yahoo_n or stooq_n) and last:
            note = "SENSEX already in the price cache through %s." % last
            status = "CACHED"
        logs.append(("Prices (SENSEX)", status, last, note))
    else:
        logs.append(("Prices (SENSEX)", "MISSING", "", "BSE index file, Yahoo, and Stooq did not return SENSEX bars. The saved cache has none."))
    return frame if frame is not None else pd.DataFrame(), logs


def _first_bytes(urls, cfg):
    errors = []
    for url in urls:
        try:
            response = _get(url, cfg)
            body = response.content or b""
            head = body.lstrip()[:80].lower()
            if head.startswith(b"<") or b"<html" in head:
                raise RuntimeError("html page, not a data file")
            return body, url
        except Exception as exc:
            errors.append(str(exc)[:80])
    raise RuntimeError("; ".join(errors)[:180] or "no file")


def fetch_nse_master(cfg):
    urls = [
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
        "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    ]
    content, url = _first_bytes(urls, cfg)
    frame = _read_table(content)
    symbol = _col(frame, ("SYMBOL",))
    name = _col(frame, ("NAME OF COMPANY", "NAME"))
    series = _col(frame, ("SERIES",))
    isin = _col(frame, ("ISIN NUMBER", "ISIN"))
    out = pd.DataFrame({
        "ticker": frame[symbol].astype(str).str.strip().str.upper(),
        "company": frame[name].astype(str).str.strip() if name else "",
        "series": frame[series].astype(str).str.strip().str.upper() if series else "EQ",
        "isin": frame[isin].astype(str).str.strip().str.upper() if isin else "",
    })
    out = out[out["ticker"].str.fullmatch(r"[A-Z0-9&-]{1,20}")]
    return out.drop_duplicates("ticker").reset_index(drop=True), url


def fetch_sme_master(cfg):
    urls = [
        "https://nsearchives.nseindia.com/content/equities/SME_EQUITY_L.csv",
        "https://archives.nseindia.com/content/equities/SME_EQUITY_L.csv",
    ]
    content, url = _first_bytes(urls, cfg)
    frame = _read_table(content)
    symbol = _col(frame, ("SYMBOL",))
    if not symbol:
        return pd.DataFrame(), url
    name = _col(frame, ("NAME OF COMPANY", "NAME"))
    isin = _col(frame, ("ISIN NUMBER", "ISIN"))
    out = pd.DataFrame({
        "ticker": frame[symbol].astype(str).str.strip().str.upper(),
        "company": frame[name].astype(str).str.strip() if name else "",
        "series": "SM",
        "isin": frame[isin].astype(str).str.strip().str.upper() if isin else "",
    })
    out = out[out["ticker"].str.fullmatch(r"[A-Z0-9&-]{1,20}")]
    return out.drop_duplicates("ticker").reset_index(drop=True), url


def _col(frame, names):
    lookup = {str(c).strip().upper(): c for c in frame.columns}
    for name in names:
        if name.upper() in lookup:
            return lookup[name.upper()]
    return None


def bse_only_names(bse_bars, nse_isins, nse_tickers):
    """Companies on the BSE file whose ISIN is not on the NSE list."""
    if bse_bars is None or len(bse_bars) == 0:
        return pd.DataFrame()
    rows = bse_bars.drop_duplicates("isin" if "isin" in bse_bars.columns else "ticker").copy()
    nse_isins = {str(x).strip().upper() for x in nse_isins if str(x).strip()}
    nse_tickers = {str(x).strip().upper() for x in nse_tickers}
    keep = []
    for _, row in rows.iterrows():
        isin = str(row.get("isin") or "").strip().upper()
        ticker = str(row.get("ticker") or "").strip().upper()
        if isin and isin in nse_isins:
            continue
        if not isin and ticker in nse_tickers:
            continue
        symbol = ticker
        if symbol in nse_tickers:
            code = str(row.get("bse_code") or "").strip()
            symbol = code if code and code not in nse_tickers else ""
        if not symbol:
            continue
        keep.append({
            "ticker": symbol,
            "company": "",
            "sector": "",
            "isin": isin,
            "nse_symbol": "",
            "bse_symbol": ticker,
            "bse_code": str(row.get("bse_code") or ""),
            "in_bse_only": "yes",
        })
    if not keep:
        return pd.DataFrame()
    return pd.DataFrame(keep).drop_duplicates("ticker")


def tag_bse_symbols(nse_frame, bse_bars):
    """Attach the BSE symbol when the same ISIN trades on both exchanges."""
    if nse_frame is None or len(nse_frame) == 0 or bse_bars is None or len(bse_bars) == 0:
        return nse_frame
    if "isin" not in nse_frame.columns or "isin" not in bse_bars.columns:
        return nse_frame
    bse = bse_bars.dropna(subset=["isin"]).drop_duplicates("isin")
    lookup = dict(zip(bse["isin"].astype(str).str.upper(), bse["ticker"].astype(str).str.upper()))
    codes = {}
    if "bse_code" in bse.columns:
        codes = dict(zip(bse["isin"].astype(str).str.upper(), bse["bse_code"].astype(str)))
    out = nse_frame.copy()
    if "bse_symbol" not in out.columns:
        out["bse_symbol"] = ""
    if "nse_symbol" not in out.columns:
        out["nse_symbol"] = out["ticker"].astype(str).str.upper()
    if "bse_code" not in out.columns:
        out["bse_code"] = ""
    isins = out["isin"].astype(str).str.upper()
    for i, isin in isins.items():
        if isin in lookup:
            out.at[i, "bse_symbol"] = lookup[isin]
            out.at[i, "bse_code"] = codes.get(isin, "")
    return out


def load_bhav_state(cache):
    path = os.path.join(cache, "bhav_state.json")
    if not os.path.exists(path):
        return {"ok": [], "holiday": []}
    try:
        data = json.load(open(path))
    except Exception:
        return {"ok": [], "holiday": []}
    data.setdefault("ok", [])
    data.setdefault("holiday", [])
    return data


def save_bhav_state(cache, state):
    json.dump(state, open(os.path.join(cache, "bhav_state.json"), "w"))


def sync_prices(tickers, universe, cfg, cache, cached, mode):
    """Fill about three years of daily bars, then only the missing sessions.

    Returns the long price table and log rows (source, status, latest, note).
    """
    logs = []
    state = load_bhav_state(cache)
    ok_dates = set(state.get("ok") or [])
    holidays = set(state.get("holiday") or [])
    end = pd.Timestamp.now(tz=india_data.IST).tz_localize(None).normalize()
    start = end - pd.Timedelta(days=india_data.KEEP_DAYS)
    if mode == "retry":
        # The backup run only looks at the last few sessions. A late file can land here.
        start = max(start, end - pd.Timedelta(days=10))
    days = pd.bdate_range(start.date(), end.date())
    pending = [d.date() for d in days if d.strftime("%Y-%m-%d") not in ok_dates and d.strftime("%Y-%m-%d") not in holidays]
    sme = bool((cfg.get("indexes") or {}).get("sme"))
    bse_on = bool((cfg.get("indexes") or {}).get("bse_only", True))
    nse_isins = set()
    if universe is not None and len(universe) and "isin" in universe.columns:
        mask = pd.Series(True, index=universe.index)
        if "exchange" in universe.columns:
            mask = universe["exchange"].astype(str).isin(["NSE", "Both", ""])
        nse_isins = set(universe.loc[mask, "isin"].astype(str).str.upper()) - {""}
    nse_rows = bse_rows = index_rows = 0
    nse_days = bse_days = index_days = 0
    nse_fail = bse_fail = index_fail = 0
    fresh_parts = []
    pause = _pause(cfg)
    for i, day in enumerate(pending):
        stamp = day.strftime("%Y-%m-%d")
        got_any = False
        try:
            content, url = _first_bytes(nse_bhav_urls(day), cfg)
            bars = parse_nse_bhav(content, sme=sme)
            if len(bars):
                fresh_parts.append(bars)
                nse_rows += len(bars)
                nse_days += 1
                got_any = True
            else:
                nse_fail += 1
        except Exception:
            nse_fail += 1
        time.sleep(pause)
        if bse_on:
            try:
                content, url = _first_bytes(bse_bhav_urls(day), cfg)
                bars = parse_bse_bhav(content, sme=sme)
                if len(bars):
                    if nse_isins:
                        isin = bars["isin"].astype(str).str.upper()
                        # Keep a BSE print when the NSE file has no bar for that ISIN today.
                        nse_today = set()
                        if fresh_parts:
                            last = fresh_parts[-1]
                            if len(last) and str(last["date"].iloc[-1]) == stamp and last["source"].iloc[0] == "NSE bhavcopy":
                                nse_today = set(last["isin"].astype(str).str.upper())
                        bars = bars[~isin.isin(nse_today)].copy()
                    if len(bars):
                        # Prefer the NSE symbol for a dual-listed name. BSE-only keeps its own symbol.
                        fresh_parts.append(bars)
                        bse_rows += len(bars)
                        bse_days += 1
                        got_any = True
            except Exception:
                bse_fail += 1
            time.sleep(pause)
        try:
            content, url = _first_bytes(index_urls(day), cfg)
            bars = parse_index_close(content)
            if len(bars):
                if "niftyindices" in url:
                    bars["source"] = "niftyindices"
                fresh_parts.append(bars)
                index_rows += len(bars)
                index_days += 1
                got_any = True
            else:
                index_fail += 1
        except Exception:
            index_fail += 1
        if got_any:
            ok_dates.add(stamp)
        elif day < (end.date() - dt.timedelta(days=3)):
            # An old weekday with no file is a holiday. A recent miss stays pending for the retry run.
            holidays.add(stamp)
        if (i + 1) % 20 == 0 and fresh_parts:
            cached = india_data.merge_price_history(cached, pd.concat(fresh_parts, ignore_index=True))
            fresh_parts = []
            state["ok"] = sorted(ok_dates)
            state["holiday"] = sorted(holidays)
            save_bhav_state(cache, state)
            cached.to_csv(os.path.join(cache, "ohlcv.csv.gz"), index=False, compression="gzip")
            print("Bhavcopy %d / %d sessions" % (i + 1, len(pending)), flush=True)
        time.sleep(pause)
    if fresh_parts:
        cached = india_data.merge_price_history(cached, pd.concat(fresh_parts, ignore_index=True))
    # Drop BSE bars whose ISIN already has an NSE bar that day, so one company is one row.
    if len(cached) and "isin" in cached.columns and "source" in cached.columns:
        cached = _prefer_nse_rows(cached)
    state["ok"] = sorted(ok_dates)
    state["holiday"] = sorted(holidays)
    save_bhav_state(cache, state)
    gap_notes = _gap_fill(cached, tickers, cfg)
    cached = gap_notes.pop("frame")
    logs.append(("Prices (NSE bhavcopy)", "OK" if nse_days else ("CACHED" if len(cached) else "MISSING"),
                 str(end.date()), "%d sessions added, %d bars. %d dates had no NSE file." % (nse_days, nse_rows, nse_fail)))
    if bse_on:
        status = "OK" if bse_days else "MISSING"
        logs.append(("Prices (BSE bhavcopy)", status, str(end.date()),
                     "%d sessions, %d bars kept for names missing that day's NSE print. %d dates failed." % (bse_days, bse_rows, bse_fail)))
    else:
        logs.append(("Prices (BSE bhavcopy)", "OK", "", "BSE switch is off"))
    idx_status = "OK" if index_days else "MISSING"
    logs.append(("Index levels (NSE ind_close_all)", idx_status, str(end.date()),
                 "%d sessions. niftyindices is the second try. %d dates failed." % (index_days, index_fail)))
    logs.extend(gap_notes["logs"])
    session_dates = []
    if len(cached) and "ticker" in cached.columns:
        nifty = cached[cached["ticker"].astype(str).str.upper().eq("^NSEI")]
        if len(nifty):
            session_dates = list(pd.to_datetime(nifty["date"], errors="coerce").dropna().dt.date.unique())
    cached, sensex_logs = update_sensex(cached, cfg, session_dates)
    logs.extend(sensex_logs)
    if len(cached):
        last = str(pd.to_datetime(cached["date"]).max().date())
        logs.append(("Prices", "OK", last, "%d rows after the fallback chain" % len(cached)))
    return cached, logs


def _prefer_nse_rows(frame):
    """When NSE and BSE both printed the same ISIN on the same day, keep NSE."""
    out = frame.copy()
    out["isin"] = out["isin"].fillna("").astype(str).str.upper()
    has = out["isin"].str.len() == 12
    dual = out[has].copy()
    if not len(dual):
        return out
    # A blank source is an older saved row. Those were already kept as the NSE print.
    src = dual["source"].fillna("").astype(str)
    dual["_rank"] = np.where(src.str.startswith("B"), 1, 0)
    dual = dual.sort_values("_rank").drop_duplicates(["date", "isin"], keep="first")
    rest = out[~has]
    return pd.concat([rest, dual.drop(columns="_rank")], ignore_index=True)


def _gap_fill(frame, tickers, cfg):
    """Stooq, then Yahoo, for symbols that still have no bars. Capped so a run stays short."""
    logs = []
    have = set(frame["ticker"].astype(str).str.upper()) if len(frame) and "ticker" in frame.columns else set()
    missing = []
    for ticker in tickers or []:
        symbol = str(ticker).upper().strip()
        if not symbol or symbol in have or symbol.startswith("^") or symbol.endswith("=X"):
            continue
        missing.append(symbol)
    cap = int((cfg.get("rate_limit") or {}).get("gap_fill_per_run") or 25)
    missing = missing[:cap]
    stooq_n = yahoo_n = 0
    parts = []
    if missing:
        for symbol in missing:
            bars = _stooq_daily(symbol)
            if len(bars):
                parts.append(bars)
                stooq_n += 1
                continue
            bars = _yahoo_daily(symbol, cfg)
            if len(bars):
                parts.append(bars)
                yahoo_n += 1
            time.sleep(0.3)
    # Index symbols and the rupee still use Yahoo when the NSE close file missed them.
    index_need = [t for t in (tickers or []) if str(t).startswith("^") and str(t).upper() not in have]
    fx_need = [t for t in (tickers or []) if str(t).upper() in ("INR=X", "INRINR=X") and str(t).upper() not in have]
    for symbol in index_need + fx_need:
        bars = _yahoo_daily(symbol, cfg)
        if len(bars):
            parts.append(bars)
            yahoo_n += 1
    if parts:
        frame = india_data.merge_price_history(frame, pd.concat(parts, ignore_index=True))
    logs.append(("Prices (Stooq)", "OK" if stooq_n else "MISSING", "",
                 "%d names filled. Stooq often blocks a plain download." % stooq_n if missing else "no gaps to fill"))
    logs.append(("Prices (Yahoo)", "OK" if yahoo_n else "MISSING", "",
                 "%d names, indexes, or the rupee. Yahoo is not used for the full list." % yahoo_n))
    return {"frame": frame, "logs": logs}


def _stooq_daily(symbol):
    url = "https://stooq.com/q/d/l/?s=%s.in&i=d" % quote(symbol.lower())
    try:
        if not fallback.robots_allows(url):
            return pd.DataFrame()
        response = requests.get(url, headers={"User-Agent": india_data.BROWSER["User-Agent"], "Accept": "text/csv"}, timeout=15)
        if response.status_code != 200 or "Date" not in response.text[:80]:
            return pd.DataFrame()
        frame = pd.read_csv(io.StringIO(response.text))
    except Exception:
        return pd.DataFrame()
    if "Close" not in frame.columns:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(frame["Date"], errors="coerce").dt.strftime("%Y-%m-%d"),
        "ticker": symbol,
        "open": pd.to_numeric(frame.get("Open"), errors="coerce"),
        "high": pd.to_numeric(frame.get("High"), errors="coerce"),
        "low": pd.to_numeric(frame.get("Low"), errors="coerce"),
        "close": pd.to_numeric(frame["Close"], errors="coerce"),
        "volume": pd.to_numeric(frame.get("Volume"), errors="coerce"),
        "source": "Stooq",
    })
    return out.dropna(subset=["date", "close"])


def _yahoo_daily(symbol, cfg, start=None):
    try:
        import yfinance as yf
        yahoo = india_data.yahoo_symbol(symbol)
        if str(symbol).upper() == "INR=X":
            yahoo = "INR=X"
        if start:
            raw = yf.download(yahoo, start=start, interval="1d", auto_adjust=True, progress=False, threads=False)
        else:
            raw = yf.download(yahoo, period="3y", interval="1d", auto_adjust=True, progress=False, threads=False)
    except Exception:
        return pd.DataFrame()
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    out = pd.DataFrame({
        "date": pd.to_datetime(raw.index).tz_localize(None).strftime("%Y-%m-%d") if getattr(raw.index, "tz", None) is not None else pd.to_datetime(raw.index).strftime("%Y-%m-%d"),
        "ticker": india_data.display_symbol(symbol) if not str(symbol).startswith("^") and not str(symbol).endswith("=X") else str(symbol).upper(),
        "open": pd.to_numeric(raw.get("Open"), errors="coerce").values,
        "high": pd.to_numeric(raw.get("High"), errors="coerce").values,
        "low": pd.to_numeric(raw.get("Low"), errors="coerce").values,
        "close": pd.to_numeric(raw.get("Close"), errors="coerce").values,
        "volume": pd.to_numeric(raw.get("Volume"), errors="coerce").values,
        "source": "Yahoo",
    })
    return out.dropna(subset=["close"])


def liquidity_table(long_df, tickers, days, minimum):
    """20-day median rupee turnover. Turnover from the bhavcopy, else close times volume."""
    cols = ["ticker", "median_traded_value", "liquid"]
    if long_df is None or len(long_df) == 0:
        return pd.DataFrame(columns=cols)
    frame = long_df.copy()
    if tickers:
        want = {str(t).upper() for t in tickers}
        frame = frame[frame["ticker"].astype(str).str.upper().isin(want)]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame = frame[~frame["ticker"].str.startswith("^")]
    frame = frame[~frame["ticker"].str.endswith("=X")]
    if "turnover" in frame.columns:
        value = pd.to_numeric(frame["turnover"], errors="coerce")
    else:
        value = pd.Series(np.nan, index=frame.index)
    backup = pd.to_numeric(frame["close"], errors="coerce") * pd.to_numeric(frame.get("volume"), errors="coerce")
    frame["value"] = value.where(value.notna() & (value > 0), backup)
    frame = frame.dropna(subset=["date", "value"]).sort_values("date")
    rows = []
    for ticker, group in frame.groupby("ticker"):
        tail = group.tail(int(days))
        med = float(tail["value"].median()) if len(tail) else float("nan")
        liquid = "yes" if np.isfinite(med) and med >= float(minimum) else "no"
        rows.append({"ticker": ticker, "median_traded_value": round(med, 0) if np.isfinite(med) else np.nan, "liquid": liquid})
    return pd.DataFrame(rows)


def flows_from_history(history, close):
    """One row per day: FII and DII buy, sell, net, plus the Nifty close."""
    cols = ["date", "fii_buy", "fii_sell", "fii_net", "dii_buy", "dii_sell", "dii_net", "nifty", "sensex", "source"]
    if history is None or len(history) == 0 or "category" not in history.columns:
        return pd.DataFrame(columns=cols)
    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame.dropna(subset=["date"])

    def side(label):
        mask = frame["category"].astype(str).str.contains(label, case=False, regex=False)
        sub = frame[mask]
        if not len(sub):
            return pd.DataFrame(columns=["date", "buy", "sell", "net", "source"])
        sub = sub.sort_values("date").drop_duplicates("date", keep="last")
        return pd.DataFrame({
            "date": sub["date"].values,
            "buy": pd.to_numeric(sub.get("buy_cr"), errors="coerce").values,
            "sell": pd.to_numeric(sub.get("sell_cr"), errors="coerce").values,
            "net": pd.to_numeric(sub.get("net_cr"), errors="coerce").values,
            "source": sub["source"].astype(str).values if "source" in sub.columns else "NSE",
        })

    fii = side("FII")
    if not len(fii):
        fii = side("FPI")
    dii = side("DII")
    if not len(fii) and not len(dii):
        return pd.DataFrame(columns=cols)
    dates = sorted(set(fii["date"]).union(set(dii["date"]))) if len(dii) else sorted(set(fii["date"]))
    fii_map = fii.set_index("date") if len(fii) else None
    dii_map = dii.set_index("date") if len(dii) else None
    nifty = {}
    if close is not None and "^NSEI" in getattr(close, "columns", []):
        series = close["^NSEI"].dropna()
        for stamp, value in series.items():
            key = str(pd.Timestamp(stamp).date())
            nifty[key] = round(float(value), 2)
    sensex = {}
    if close is not None and "^BSESN" in getattr(close, "columns", []):
        series = close["^BSESN"].dropna()
        for stamp, value in series.items():
            key = str(pd.Timestamp(stamp).date())
            sensex[key] = round(float(value), 2)
    rows = []
    for day in dates:
        def cell(table, col):
            if table is None or day not in table.index:
                return np.nan
            return table.at[day, col]

        source = ""
        if fii_map is not None and day in fii_map.index:
            source = str(fii_map.at[day, "source"])
        elif dii_map is not None and day in dii_map.index:
            source = str(dii_map.at[day, "source"])
        rows.append({
            "date": day,
            "fii_buy": cell(fii_map, "buy"),
            "fii_sell": cell(fii_map, "sell"),
            "fii_net": cell(fii_map, "net"),
            "dii_buy": cell(dii_map, "buy"),
            "dii_sell": cell(dii_map, "sell"),
            "dii_net": cell(dii_map, "net"),
            "nifty": nifty.get(day, np.nan),
            "sensex": sensex.get(day, np.nan),
            "source": source or "NSE",
        })
    return pd.DataFrame(rows)


def merge_flow_rows(old, new):
    frames = [df for df in (old, new) if df is not None and len(df)]
    if not frames:
        return pd.DataFrame(columns=["date", "category", "buy_cr", "sell_cr", "net_cr", "source"])
    both = pd.concat(frames, ignore_index=True)
    both["date"] = pd.to_datetime(both["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    both = both.dropna(subset=["date", "category"])
    both["category"] = both["category"].astype(str)
    return both.sort_values("date").drop_duplicates(["date", "category"], keep="last").reset_index(drop=True)


def fetch_fii_archives(cfg):
    """Older free history first, then today's NSE print so the official day wins."""
    rows = []
    errors = []
    try:
        older = _public_fii_archive(cfg)
        rows.extend(older)
        if not older:
            errors.append("public archive no rows")
    except Exception as exc:
        errors.append("public archive " + str(exc)[:60])
    try:
        latest = india_data.fetch_fii_dii(cfg)
        for row in latest:
            row["source"] = "NSE fiidiiTradeReact"
        rows.extend(latest)
    except Exception as exc:
        errors.append("NSE " + str(exc)[:80])
    extra_urls = [
        ("NSDL FPI", "https://www.fpi.nsdl.co.in/Reports/LatestFPIInvestment.aspx"),
        ("Moneycontrol", "https://www.moneycontrol.com/techmvc/responsive/fiidii/getFiiDii?classic=true"),
    ]
    for name, url in extra_urls:
        try:
            if not fallback.robots_allows(url):
                errors.append(name + " robots")
                continue
            response = _get(url, cfg, timeout=18)
            parsed = _parse_fii_html(response.text, name)
            rows.extend(parsed)
            if not parsed:
                errors.append(name + " no rows")
        except Exception as exc:
            errors.append(name + " " + str(exc)[:60])
    return rows, "; ".join(errors)[:180]


def _public_fii_archive(cfg):
    """Daily cash history from a free NSE-sourced archive. Seeded rows are dropped."""
    url = "https://raw.githubusercontent.com/MrChartist/fii-dii-data/main/data/history.json"
    response = _get(url, cfg, timeout=25)
    data = response.json()
    if not isinstance(data, list):
        return []
    keep = {"fetch-pipeline", "live-fetch"}
    rows = []
    for item in data:
        if str(item.get("_source") or "") not in keep:
            continue
        day = pd.to_datetime(item.get("date"), dayfirst=True, errors="coerce")
        if pd.isna(day):
            continue
        stamp = day.strftime("%Y-%m-%d")
        for category, buy_key, sell_key, net_key in (
            ("FII", "fii_buy", "fii_sell", "fii_net"),
            ("DII", "dii_buy", "dii_sell", "dii_net"),
        ):
            rows.append({
                "date": stamp,
                "category": category,
                "buy_cr": _as_float(item.get(buy_key)),
                "sell_cr": _as_float(item.get(sell_key)),
                "net_cr": _as_float(item.get(net_key)),
                "source": "public FII archive",
            })
    return rows


def _parse_fii_html(text, source):
    """Pull a simple table of dates and nets when the page is plain HTML."""
    if "fii" not in text.lower() and "fpi" not in text.lower():
        return []
    try:
        tables = pd.read_html(io.StringIO(text))
    except Exception:
        return []
    rows = []
    for table in tables:
        cols = [str(c).strip().lower() for c in table.columns]
        if not any("fii" in c or "fpi" in c or "dii" in c for c in cols):
            continue
        date_col = None
        for i, name in enumerate(cols):
            if "date" in name:
                date_col = table.columns[i]
                break
        if date_col is None:
            continue
        for _, item in table.iterrows():
            day = pd.to_datetime(item.get(date_col), dayfirst=True, errors="coerce")
            if pd.isna(day):
                continue
            for label, needle in (("FII", "fii"), ("FPI", "fpi"), ("DII", "dii")):
                for i, name in enumerate(cols):
                    if needle in name and "net" in name:
                        rows.append({
                            "date": day.strftime("%Y-%m-%d"),
                            "category": "FII" if label == "FPI" else label,
                            "buy_cr": None,
                            "sell_cr": None,
                            "net_cr": _as_float(item.iloc[i]),
                            "source": source,
                        })
    return rows


def fetch_participant_oi(cfg, day=None):
    """NSE participant-wise open interest. FII, DII, Pro, and Client index futures."""
    day = day or (pd.Timestamp.now(tz=india_data.IST).tz_localize(None).date())
    stamps = [day - dt.timedelta(days=n) for n in range(0, 6)]
    last_error = "no file"
    for stamp in stamps:
        token = stamp.strftime("%d%m%Y")
        urls = [
            "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_%s.csv" % token,
            "https://archives.nseindia.com/content/nsccl/fao_participant_oi_%s.csv" % token,
        ]
        for url in urls:
            try:
                response = _get(url, cfg, timeout=20)
                frame = _read_participant_file(response.content)
            except Exception as exc:
                last_error = str(exc)[:80]
                continue
            parsed = _parse_participant(frame, stamp)
            if len(parsed):
                return parsed, url
    raise RuntimeError(last_error)


def _read_participant_file(content):
    """The NSE file starts with a title line. The header is the Client Type row."""
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines[:6]):
        low = line.lower()
        if "client type" in low or "future index long" in low:
            start = i
            break
    frame = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def _parse_participant(frame, day):
    if frame is None or len(frame) == 0:
        return pd.DataFrame()
    cols = {str(c).strip().lower(): c for c in frame.columns}
    client = None
    for key, column in cols.items():
        if "client" in key or key in ("type", "participant"):
            client = column
            break
    if client is None:
        client = frame.columns[0]
    # The file is usually wide: Future Index Long, Future Index Short, and so on.
    long_col = short_col = None
    for key, column in cols.items():
        if "future" in key and "index" in key and "long" in key:
            long_col = column
        if "future" in key and "index" in key and "short" in key:
            short_col = column
    rows = []
    for _, item in frame.iterrows():
        name = str(item.get(client) or "").strip()
        if not name or name.lower() in ("total", "nan"):
            continue
        if not any(word in name.lower() for word in ("fii", "fpi", "dii", "pro", "client")):
            continue
        long_v = _as_float(item.get(long_col)) if long_col else np.nan
        short_v = _as_float(item.get(short_col)) if short_col else np.nan
        net = long_v - short_v if np.isfinite(long_v) and np.isfinite(short_v) else np.nan
        rows.append({
            "date": stamp_date(day),
            "participant": name,
            "index_fut_long": long_v,
            "index_fut_short": short_v,
            "index_fut_net": net,
            "source": "NSE fao_participant_oi",
        })
    return pd.DataFrame(rows)


def stamp_date(day):
    if hasattr(day, "strftime"):
        return day.strftime("%Y-%m-%d")
    return str(day)[:10]


def fetch_repo_rate(cfg):
    """RBI homepage, then Trading Economics, then the config last-known value."""
    def rbi():
        response = _get("https://www.rbi.org.in/", cfg, timeout=25)
        text = response.text
        import re
        match = re.search(r"Policy Repo Rate[^0-9]{0,40}(\d{1,2}\.\d{2})", text, re.I)
        if not match:
            match = re.search(r"repo rate[^0-9]{0,40}(\d{1,2}\.\d{2})\s*%", text, re.I)
        if not match:
            return None
        return float(match.group(1))

    def trading():
        url = "https://tradingeconomics.com/india/interest-rate"
        if not fallback.robots_allows(url):
            return None
        response = _get(url, cfg, timeout=18)
        import re
        match = re.search(r"India Interest Rate[^0-9]{0,80}(\d{1,2}\.\d{2})", response.text, re.I | re.S)
        if not match:
            return None
        return float(match.group(1))

    book = fallback.SourceBook()
    last = ((cfg.get("last_known") or {}).get("repo_rate") or {})
    cache_value = last.get("value")
    try:
        cache_value = float(cache_value)
    except (TypeError, ValueError):
        cache_value = None
    value, source, note = fallback.run_chain("repo", [("RBI", rbi), ("Trading Economics", trading)], cache_value, book)
    return value, source, note, book


def fetch_fred_series(series_id, timeout=25):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s" % series_id
    response = netutil.http_get(
        requests, url, {"User-Agent": india_data.BROWSER["User-Agent"]}, timeout, max_tries=3, delays=(2.0, 5.0, 10.0)
    )
    frame = pd.read_csv(io.StringIO(response.text))
    if frame.shape[1] < 2:
        return None, None
    values = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
    mask = values.notna()
    if not mask.any():
        return None, None
    last = frame.loc[mask].iloc[-1]
    return float(values[mask].iloc[-1]), str(last.iloc[0])[:10]


def macro_chain(cfg):
    """Repo, 10-year, CPI, IIP, GDP, and the rupee. Each field keeps the first source that answered."""
    rows = []
    notes = []
    repo, repo_source, repo_note, book = fetch_repo_rate(cfg)
    if repo is not None:
        rows.append(_macro_row("Rates", "RBI repo rate", "", repo, repo_source, repo_note or "Policy repo rate, percent."))
    else:
        notes.append("Repo rate was not available.")
    y10, y10_date, y10_source, y10_note = _yield_chain(cfg)
    if y10 is not None:
        rows.append(_macro_row("Rates", "India 10-year yield", y10_date, y10, y10_source, y10_note or "Level only. No forecast, so there is no surprise score."))
    else:
        notes.append("India 10-year yield was not available.")
    for label, category, series_id, note in (
        ("CPI", "Inflation", "INDCPIALLMINMEI", "Monthly CPI index from FRED. Not a year-on-year percent."),
        ("IIP", "Growth", "INDPROINDMISMEI", "Monthly industrial production index from FRED."),
    ):
        try:
            value, day = fetch_fred_series(series_id)
        except Exception as exc:
            value, day = None, None
            notes.append("%s FRED failed (%s)." % (label, str(exc)[:60]))
        if value is not None:
            rows.append(_macro_row(category, label, day, value, "FRED", note + " No forecast in this feed, so surprise stays blank."))
        else:
            notes.append("%s was not available from FRED." % label)
    try:
        for row in india_data.fetch_world_bank():
            row["source"] = "World Bank"
            # Keep yearly GDP. Do not replace a monthly CPI or IIP we already stored.
            if row["indicator"] in ("CPI", "IIP") and any(r["indicator"] == row["indicator"] for r in rows):
                row["indicator"] = row["indicator"] + " yearly"
            rows.append(row)
    except Exception as exc:
        notes.append("World Bank " + str(exc)[:60])
    return rows, notes, book


def _yield_chain(cfg):
    found = {}

    def fred():
        value, day = fetch_fred_series("INDIRLTLT01STM", timeout=28)
        if value is None:
            value, day = fetch_fred_series("IRLTLT01INM156N", timeout=20)
        if value is None:
            return None
        found["date"] = day
        return value

    def investing():
        url = "https://www.investing.com/rates-bonds/india-10-year-bond-yield"
        if not fallback.robots_allows(url):
            return None
        response = _get(url, cfg, timeout=18)
        import re
        match = re.search(r'data-test="instrument-price-last"[^>]*>([0-9.]+)', response.text)
        if not match:
            match = re.search(r"India 10-Year[^0-9]{0,40}([0-9]+\.[0-9]+)", response.text)
        if not match:
            return None
        return float(match.group(1))

    last = ((cfg.get("last_known") or {}).get("india_10y") or {})
    try:
        cache_value = float(last.get("value"))
    except (TypeError, ValueError):
        cache_value = None
    value, source, note = fallback.run_chain("india_10y", [("FRED", fred), ("Investing.com", investing)], cache_value)
    return value, found.get("date") or last.get("date") or "", source, note


def _macro_row(category, indicator, day, actual, source, note):
    return {
        "country": "India",
        "category": category,
        "indicator": indicator,
        "date": day or "",
        "actual": actual,
        "forecast": "",
        "surprise": "",
        "signal": "",
        "source": source,
        "note": note,
    }
