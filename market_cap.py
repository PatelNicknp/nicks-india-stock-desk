"""Saved share counts and market cap for the Episodic Pivot page.

Market cap = shares x close, in rupee crore (1 crore = 10,000,000).

Where the share count comes from, in order:
1. cache/market_cap.csv, the saved copy from earlier runs.
2. The latest share count in the Yahoo statements the backfill job already saved
   (cache/quarters.csv, then cache/annual.csv). No new download.
3. Only when a name on the Episodic Pivot page still has no count: a small Yahoo
   lookup (free, no API key), at most a few names a run, only on the price runs,
   never on a rescore. Every count found is saved, so it is not asked for again
   until it is old.

The saved file is reused on every run, and a newer filing replaces an older count.
"""
import os
import time

import numpy as np
import pandas as pd

FILE_NAME = "market_cap.csv"
COLUMNS = [
    "ticker", "shares", "shares_source", "shares_as_of", "close", "close_date",
    "market_cap_cr", "saved_on",
]
CRORE = 1e7


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def cache_path(cache_dir):
    return os.path.join(cache_dir, FILE_NAME)


def read_cache(cache_dir):
    path = cache_path(cache_dir)
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_csv(path, dtype={"ticker": str})
    except Exception:
        return pd.DataFrame(columns=COLUMNS)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNS]


def statement_shares(annual, quarters):
    """Latest positive share count per ticker from the saved statements: {ticker: (shares, period_end, source)}."""
    best = {}
    for frame, source in ((annual, "Yahoo annual statement"), (quarters, "Yahoo quarterly statement")):
        if frame is None or len(frame) == 0 or "shares" not in frame.columns or "ticker" not in frame.columns:
            continue
        sub = frame[["ticker", "end", "shares"]].copy()
        sub["shares"] = pd.to_numeric(sub["shares"], errors="coerce")
        sub["end"] = pd.to_datetime(sub["end"], errors="coerce")
        sub = sub.dropna(subset=["shares", "end"])
        sub = sub[sub["shares"] > 0]
        if len(sub) == 0:
            continue
        last = sub.sort_values("end").drop_duplicates("ticker", keep="last")
        for t, end, sh in zip(last["ticker"].astype(str), last["end"], last["shares"]):
            old = best.get(t)
            # The newer period wins. On a tie the quarterly count wins (it is listed second).
            if old is None or end >= old[1]:
                best[t] = (float(sh), end, source)
    return best


def _last_close(close, ticker):
    if close is None or ticker not in getattr(close, "columns", []):
        return None, ""
    s = pd.to_numeric(close[ticker], errors="coerce").dropna()
    if len(s) == 0:
        return None, ""
    return float(s.iloc[-1]), str(pd.Timestamp(s.index[-1]).date())


def build(cache_df, annual, quarters, close, today):
    """Merge the saved copy with the statements and today's close. Returns the full table to save.

    Every saved name is kept, not only today's universe, so a name that drops out and comes back is reused.
    """
    rows = {}
    if cache_df is not None and len(cache_df):
        for rec in cache_df.to_dict("records"):
            t = str(rec.get("ticker") or "").strip()
            if t:
                rows[t] = dict(rec)
    fresh = statement_shares(annual, quarters)
    for t, (sh, end, source) in fresh.items():
        old = rows.get(t)
        old_end = pd.to_datetime(old.get("shares_as_of"), errors="coerce") if old else pd.NaT
        old_src = str(old.get("shares_source") or "") if old else ""
        # A saved Yahoo quote count is newer than any statement period it was taken after.
        if old is None or _num(old.get("shares")) is None or pd.isna(old_end) or end > old_end or (
                end == old_end and old_src != "Yahoo quote"):
            rows[t] = {"ticker": t, "shares": sh, "shares_source": source, "shares_as_of": str(pd.Timestamp(end).date()),
                       "saved_on": today}
    for t in list(rows):
        rec = rows[t]
        px, d = _last_close(close, t)
        sh = _num(rec.get("shares"))
        if px is not None and sh is not None:
            rec["close"] = round(px, 2)
            rec["close_date"] = d
            rec["market_cap_cr"] = round(sh * px / CRORE, 1)
        if not rec.get("saved_on"):
            rec["saved_on"] = today
    out = pd.DataFrame(list(rows.values()), columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
    return out.sort_values("ticker").reset_index(drop=True) if len(out) else out


def shares_map(table):
    """{ticker: {"shares", "source", "as_of"}} for the scanner."""
    out = {}
    if table is None or len(table) == 0:
        return out
    for rec in table.to_dict("records"):
        sh = _num(rec.get("shares"))
        if sh is None or sh <= 0:
            continue
        out[str(rec["ticker"])] = {"shares": sh, "source": str(rec.get("shares_source") or ""),
                                   "as_of": str(rec.get("shares_as_of") or "")}
    return out


def yahoo_symbol(ticker, universe=None):
    t = str(ticker).strip().upper()
    if universe is not None and len(universe) and "ticker" in universe.columns:
        row = universe[universe["ticker"].astype(str) == t]
        if len(row):
            r = row.iloc[-1]
            exch = str(r.get("exchange") or "").upper()
            bse = str(r.get("bse_symbol") or "").strip().upper()
            nse = str(r.get("nse_symbol") or "").strip().upper()
            if exch == "BSE" or str(r.get("in_bse_only") or "").lower() == "yes":
                code = str(r.get("bse_code") or "").strip()
                return (code.split(".")[0] if code and code != "nan" else (bse or t)) + ".BO"
            return (nse if nse and nse != "NAN" else t) + ".NS"
    return t + ".NS"


def fetch_missing(table, need, universe, today, max_names=5, refetch_days=30, pause=1.0, fetch=None):
    """Ask Yahoo for the share count of at most max_names names that still have none.

    need: tickers that want a count (the Episodic Pivot rows). A name asked in the last
    refetch_days with no answer is not asked again, so a bad symbol costs one request a month.
    Returns (table, asked, found).
    """
    table = table.copy() if table is not None and len(table) else pd.DataFrame(columns=COLUMNS)
    have = shares_map(table)
    asked_recent = set()
    if len(table):
        for rec in table.to_dict("records"):
            if _num(rec.get("shares")) is None and str(rec.get("shares_source") or "") == "Yahoo quote (no answer)":
                d = pd.to_datetime(rec.get("saved_on"), errors="coerce")
                if pd.notna(d) and (pd.Timestamp(today) - d).days < int(refetch_days):
                    asked_recent.add(str(rec["ticker"]))
    todo = [t for t in dict.fromkeys(str(x) for x in (need or [])) if t not in have and t not in asked_recent][: int(max_names)]
    if not todo:
        return table, 0, 0
    if fetch is None:
        fetch = _yahoo_shares
    found = 0
    new_rows = []
    for i, t in enumerate(todo):
        if i and pause:
            time.sleep(pause)
        try:
            sh = _num(fetch(yahoo_symbol(t, universe)))
        except Exception:
            sh = None
        if sh is not None and sh > 0:
            found += 1
            new_rows.append({"ticker": t, "shares": sh, "shares_source": "Yahoo quote", "shares_as_of": today, "saved_on": today})
        else:
            new_rows.append({"ticker": t, "shares": "", "shares_source": "Yahoo quote (no answer)", "shares_as_of": "", "saved_on": today})
    keep = table[~table["ticker"].astype(str).isin([r["ticker"] for r in new_rows])] if len(table) else table
    out = pd.concat([keep, pd.DataFrame(new_rows, columns=COLUMNS)], ignore_index=True)
    return out.sort_values("ticker").reset_index(drop=True), len(todo), found


def _yahoo_shares(symbol):
    import yfinance as yf
    info = yf.Ticker(symbol).fast_info
    try:
        return info["shares"]
    except Exception:
        return getattr(info, "shares", None)


def refresh_close(table, close):
    """Recompute close and market cap after a lookup."""
    if table is None or len(table) == 0:
        return table
    out = table.copy()
    for col in ("close", "close_date", "market_cap_cr"):
        out[col] = out[col].astype(object)
    for i, rec in out.iterrows():
        px, d = _last_close(close, str(rec["ticker"]))
        sh = _num(rec.get("shares"))
        if px is not None and sh is not None:
            out.at[i, "close"] = round(px, 2)
            out.at[i, "close_date"] = d
            out.at[i, "market_cap_cr"] = round(sh * px / CRORE, 1)
    return out


def save(table, cache_dir):
    out = table.copy() if table is not None else pd.DataFrame(columns=COLUMNS)
    for c in COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out[COLUMNS].to_csv(cache_path(cache_dir), index=False)
