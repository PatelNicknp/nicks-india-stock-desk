"""Nick's India Stock Desk.

Research screen for NSE stocks. It never places a trade and it never calls a broker.

    python stock_desk.py --close    # after the NSE close: bhavcopy plus a slice of slow sources
    python stock_desk.py --retry    # same, but only the last few sessions (late bhavcopy)
    python stock_desk.py --morning  # news and FII/DII only
    python stock_desk.py --offline  # cache only, for tests
    python stock_desk.py --rescore  # light rebuild: rescore from files on disk, no downloads

Daily prices come from the NSE bhavcopy. BSE, Stooq, and Yahoo are fallbacks.
Yahoo is not used to price every stock. Statements and shareholding rotate
through a slice each after-close run. A separate job, fundamentals_backfill.py,
keeps filling those files all day. If a source fails, the previous file is
kept and the updates log says CACHED.
"""
import os, sys, io, json, time, html, re, datetime as dt
import numpy as np
import pandas as pd
import requests

import netutil
import fundamentals as fund
import scoring
import tables
import setups
import sector_rotation
import india_data
import fundamentals_backfill

ROOT = None  # set in main so tests can point DESK_ROOT at a temp folder
PT = "America/Los_Angeles"
ET = "America/New_York"
IST = "Asia/Kolkata"
DISCLAIMER = tables.DISCLAIMER
LOG = []
STAMPS = {}

SECTOR_ETF_BY_NAME = {
    "Information Technology": "^CNXIT", "Technology": "^CNXIT",
    "Health Care": "^CNXPHARMA", "Healthcare": "^CNXPHARMA",
    "Financials": "^CNXFIN", "Financial Services": "^CNXFIN",
    "Industrials": "^CNXINFRA",
    "Communication Services": "^CNXMEDIA", "Telecommunications": "^CNXMEDIA",
    "Consumer Discretionary": "^CNXAUTO", "Consumer Cyclical": "^CNXAUTO",
    "Consumer Staples": "^CNXFMCG", "Consumer Defensive": "^CNXFMCG",
    "Energy": "^CNXENERGY",
    "Real Estate": "^CNXREALTY",
    "Materials": "^CNXMETAL", "Basic Materials": "^CNXMETAL",
}

ECON_SPECS = [
    ("Growth", "GDP", ["GDP"], 1),
    ("Growth", "ISM manufacturing", ["ISM Manufacturing PMI"], 1),
    ("Growth", "Retail sales", ["Retail Sales"], 1),
    ("Inflation", "CPI", ["CPI"], 1),
    ("Inflation", "Fed funds rate", ["Fed Interest Rate Decision"], 1),
    ("Jobs", "Nonfarm payrolls", ["Nonfarm Payrolls"], 1),
    ("Jobs", "Unemployment rate", ["Unemployment Rate"], -1),
    ("Jobs", "Jobless claims", ["Initial Jobless Claims"], -1),
]


def root():
    return ROOT


def log(source, status, latest="", note=""):
    now = india_data.now_stamp()
    LOG.append({"source": source, "status": status, "latest": str(latest), "note": note, "checked_pt": now})
    print("[%s] %s %s %s" % (status, source, latest, note))


def paths():
    r = root()
    data, cache, inp = (os.path.join(r, d) for d in ("data", "cache", "input"))
    for d in (data, cache, os.path.join(cache, "pcr"), os.path.join(cache, "econ")):
        os.makedirs(d, exist_ok=True)
    return data, cache, inp


def rebuild_after_backfill_on(cfg):
    """Switch for the light rebuild at the end of each backfill run. Default on."""
    spec = (cfg or {}).get("fundamentals_backfill") or {}
    return bool(spec.get("rebuild_pages_after_run", True))


def load_cfg():
    with open(os.path.join(root(), "config.json")) as f:
        return json.load(f)


def load_stamps(cache):
    f = os.path.join(cache, "stamps.json")
    if os.path.exists(f):
        with open(f) as fh:
            STAMPS.update(json.load(fh))


def save_stamps(cache):
    with open(os.path.join(cache, "stamps.json"), "w") as f:
        json.dump(STAMPS, f, indent=1)


def rl(cfg):
    return cfg["rate_limit"]


def session_headers(cfg, sec=False):
    if sec:
        return {"User-Agent": rl(cfg)["sec_user_agent"], "Accept": "application/json", "Accept-Encoding": "gzip, deflate"}
    return {"User-Agent": "Mozilla/5.0 (compatible; NickStockDesk/1.0; research)", "Accept": "application/json,text/html,*/*"}


def today_et():
    """Session date for the once-a-day stamp. India uses the IST date."""
    return pd.Timestamp.now(tz=IST).strftime("%Y-%m-%d")


def progress_load(cache, name):
    """Tickers already fetched today. A crashed run can continue instead of starting over."""
    f = os.path.join(cache, "progress_%s.json" % name)
    if not os.path.exists(f):
        return set()
    try:
        data = json.load(open(f))
    except Exception:
        return set()
    if data.get("date") != today_et():
        return set()
    return set(data.get("tickers") or [])


def progress_save(cache, name, done):
    f = os.path.join(cache, "progress_%s.json" % name)
    json.dump({"date": today_et(), "tickers": sorted(done)}, open(f, "w"))


def read_csv(path, **kw):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kw)


def write_out(df, name, data_dir):
    cols = tables.COLS[name]
    if df is None:
        df = pd.DataFrame(columns=cols)
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan if c not in ("data_status", "note", "disclaimer") else ""
    out = out[cols]
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].round(4)
    out.to_csv(os.path.join(data_dir, name + ".csv"), index=False, na_rep="")


def gated(df, name, feature_on, missing_note):
    if not feature_on:
        return pd.DataFrame(columns=tables.COLS[name])
    return tables.ensure(df, tables.COLS[name], "MISSING", missing_note)


# ---------------------------------------------------------------- prices
def frames_from_download(df):
    if df is None or len(getattr(df, "index", [])) == 0 or not isinstance(df.columns, pd.MultiIndex):
        return None
    levels = [set(map(str, df.columns.get_level_values(i))) for i in range(df.columns.nlevels)]

    def grab(field):
        if field in levels[0]:
            sub = df.xs(field, axis=1, level=0)
        elif field in levels[1]:
            sub = df.xs(field, axis=1, level=1)
        else:
            return None
        if isinstance(sub, pd.Series):
            sub = sub.to_frame()
        return sub

    # Open is already in this Yahoo batch. Keeping it does not add a request.
    return grab("Close"), grab("High"), grab("Low"), grab("Volume"), grab("Open")


def _normalize_index(df):
    if df is None:
        return None
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    df.index = idx
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def download_prices(tickers, cfg, period="3y", start=None):
    """One batched Yahoo download. period is used for a cold start. start is a recent date."""
    import yfinance as yf
    batch = int(rl(cfg)["yahoo_batch_size"])
    pause = float(rl(cfg)["yahoo_batch_pause_seconds"])
    symbols = [india_data.yahoo_symbol(t) for t in tickers]
    parts = []

    def pull(chunk):
        def once():
            kwargs = dict(interval="1d", auto_adjust=True, progress=False, group_by="ticker", threads=False)
            if start:
                df = yf.download(chunk, start=start, **kwargs)
            else:
                df = yf.download(chunk, period=period, **kwargs)
            got = frames_from_download(df)
            if got is None or got[0] is None or got[0].dropna(how="all").empty:
                raise netutil.RetryableError("empty price batch (%d names)" % len(chunk))
            return got
        try:
            return netutil.call_with_retry(once, max_tries=rl(cfg)["max_retries"], delays=tuple(rl(cfg)["backoff_seconds"]))
        except Exception:
            if len(chunk) == 1:
                return None
            mid = len(chunk) // 2
            return ("split", chunk[:mid], chunk[mid:])

    queue = [symbols[i:i + batch] for i in range(0, len(symbols), batch)]
    while queue:
        chunk = queue.pop(0)
        got = pull(chunk)
        if isinstance(got, tuple) and got and isinstance(got[0], str) and got[0] == "split":
            queue = [got[1], got[2]] + queue
            continue
        if isinstance(got, tuple) and got and not isinstance(got[0], str):
            renamed = []
            for frame in got:
                frame = _normalize_index(frame)
                if frame is not None:
                    frame = frame.copy()
                    frame.columns = [india_data.display_symbol(c) for c in frame.columns]
                    frame = frame.loc[:, ~frame.columns.duplicated()]
                renamed.append(frame)
            parts.append(tuple(renamed))
        if queue:
            time.sleep(pause)
    if not parts:
        raise RuntimeError("no prices downloaded")

    def cat(i):
        frames = [p[i] for p in parts if len(p) > i and p[i] is not None]
        if not frames:
            return None
        out = pd.concat(frames, axis=1)
        out = out.loc[:, ~out.columns.duplicated()]
        return out.sort_index()
    return cat(0), cat(1), cat(2), cat(3), cat(4)


def ohlcv_long(close, high, low, vol, opn=None):
    def melt(df, name):
        x = df.copy()
        x.index.name = "date"
        m = x.reset_index().melt(id_vars="date", var_name="ticker", value_name=name)
        return m
    m = melt(close, "close")
    if high is not None:
        m = m.merge(melt(high, "high"), on=["date", "ticker"], how="left")
    if low is not None:
        m = m.merge(melt(low, "low"), on=["date", "ticker"], how="left")
    if vol is not None:
        m = m.merge(melt(vol, "volume"), on=["date", "ticker"], how="left")
    if opn is not None:
        m = m.merge(melt(opn, "open"), on=["date", "ticker"], how="left")
    m = m.dropna(subset=["close"])
    m["date"] = pd.to_datetime(m["date"]).dt.strftime("%Y-%m-%d")
    return m


def wide_from_long(df, col):
    if df is None or len(df) == 0 or col not in df.columns:
        return pd.DataFrame()
    x = df.copy()
    x["date"] = pd.to_datetime(x["date"])
    w = x.pivot_table(index="date", columns="ticker", values=col, aggfunc="last").sort_index()
    return w


def load_prices(tickers, cfg, cache, mode, universe=None):
    """After the close, append NSE bhavcopy sessions. Morning and offline stay on the cache."""
    path = os.path.join(cache, "ohlcv.csv.gz")
    cached = read_csv(path) if os.path.exists(path) else pd.DataFrame()
    if mode in ("offline", "morning", "hourly"):
        if len(cached):
            note = "offline mode, used cache" if mode == "offline" else "morning run does not download prices"
            log("Prices (NSE bhavcopy)", "OK", cached["date"].max() if "date" in cached else "", note)
            return cached
        log("Prices (NSE bhavcopy)", "MISSING", "", "no price cache and this run does not download")
        return pd.DataFrame()
    if mode in ("full", "retry"):
        try:
            import market_sources
            long, notes = market_sources.sync_prices(tickers, universe, cfg, cache, cached, mode)
            if len(long):
                long.to_csv(path, index=False, compression="gzip")
            for source, status, latest, note in notes:
                log(source, status, latest, note)
            return long
        except Exception as exc:
            if len(cached):
                log("Prices (NSE bhavcopy)", "CACHED", cached["date"].max() if "date" in cached else "", str(exc)[:160])
                return cached
            log("Prices (NSE bhavcopy)", "MISSING", "", str(exc)[:160])
            return pd.DataFrame()
    log("Prices (NSE bhavcopy)", "CACHED" if len(cached) else "MISSING", "", "this run does not download prices")
    return cached


# ---------------------------------------------------------------- universe
# One row per stock. A name in more than one list keeps every flag.
FLAGS = (
    "in_nifty50", "in_next50", "in_midcap150", "in_smallcap250", "in_microcap250",
    "in_totalmarket", "in_other_nse", "in_sme", "in_bse_only", "in_my_picks",
)
INDEX_LABELS = {
    "in_nifty50": "Nifty 50",
    "in_next50": "Next 50",
    "in_midcap150": "Midcap 150",
    "in_smallcap250": "Smallcap 250",
    "in_microcap250": "Microcap 250",
    "in_totalmarket": "Total Market",
    "in_other_nse": "Other NSE",
    "in_sme": "SME",
    "in_bse_only": "BSE only",
    "in_my_picks": "My picks",
}
SWITCH_DEFAULTS = {
    "nifty50": True, "next50": True, "midcap150": True, "smallcap250": True,
    "microcap250": True, "totalmarket": True, "other_nse": True, "sme": False, "bse_only": True,
}
INDEX_SOURCES = {
    "nifty50": {"flag": "in_nifty50", "cache": "nifty50.csv", "legacy": "universe.csv", "log": "Universe (Nifty 50)", "stamp": "universe_nifty50"},
    "next50": {"flag": "in_next50", "cache": "next50.csv", "legacy": None, "log": "Universe (Nifty Next 50)", "stamp": "universe_next50"},
    "midcap150": {"flag": "in_midcap150", "cache": "midcap150.csv", "legacy": None, "log": "Universe (Nifty Midcap 150)", "stamp": "universe_midcap150"},
    "smallcap250": {"flag": "in_smallcap250", "cache": "smallcap250.csv", "legacy": None, "log": "Universe (Smallcap 250)", "stamp": "universe_smallcap250"},
    "microcap250": {"flag": "in_microcap250", "cache": "microcap250.csv", "legacy": None, "log": "Universe (Microcap 250)", "stamp": "universe_microcap250"},
    "totalmarket": {"flag": "in_totalmarket", "cache": "totalmarket.csv", "legacy": None, "log": "Universe (Total Market)", "stamp": "universe_totalmarket"},
}
# Eleven GICS sectors. Wikipedia ICB names and Yahoo profile names both land here.
# Industry is a separate column and is not renamed.
ICB_TO_GICS = {
    "Technology": "Information Technology",
    "Information Technology": "Information Technology",
    "Telecommunications": "Communication Services",
    "Communication Services": "Communication Services",
    "Health Care": "Health Care",
    "Healthcare": "Health Care",
    "Consumer Discretionary": "Consumer Discretionary",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Staples": "Consumer Staples",
    "Consumer Defensive": "Consumer Staples",
    "Industrials": "Industrials",
    "Utilities": "Utilities",
    "Financials": "Financials",
    "Financial Services": "Financials",
    "Real Estate": "Real Estate",
    "Energy": "Energy",
    "Basic Materials": "Materials",
    "Materials": "Materials",
}
GICS_SECTORS = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
)


def gics_sector(name):
    """Map an ICB or Yahoo sector onto one GICS name. Blank stays blank."""
    if name is None:
        return ""
    try:
        if pd.isna(name):
            return ""
    except (ValueError, TypeError):
        pass
    text = str(name).strip()
    if not text or text.lower() in ("nan", "none"):
        return ""
    if text in ICB_TO_GICS:
        return ICB_TO_GICS[text]
    if text in GICS_SECTORS:
        return text
    # An NSE industry name is not a sector. Leave it blank so the Yahoo sector can fill in.
    return ""


def index_switches(cfg):
    raw = cfg.get("indexes") or {}
    return {key: bool(raw.get(key, default)) for key, default in SWITCH_DEFAULTS.items()}


def membership_label(in_nifty50, in_next50, in_midcap150, in_smallcap250="no", in_microcap250="no",
                     in_totalmarket="no", in_other_nse="no", in_sme="no", in_bse_only="no", in_my_picks="no"):
    """Stable tags. A holding outside the lists is Focus."""
    flags = {
        "in_nifty50": in_nifty50, "in_next50": in_next50, "in_midcap150": in_midcap150,
        "in_smallcap250": in_smallcap250, "in_microcap250": in_microcap250,
        "in_totalmarket": in_totalmarket, "in_other_nse": in_other_nse, "in_sme": in_sme,
        "in_bse_only": in_bse_only, "in_my_picks": in_my_picks,
    }
    parts = [INDEX_LABELS[flag] for flag in FLAGS if flags.get(flag) == "yes"]
    return " / ".join(parts) if parts else "Focus"


def wiki_constituents(tables, flag):
    """Pick the constituents table. Accepts Symbol or Ticker, including Nifty CSVs."""
    for table in tables:
        df = india_data.parse_constituent_frame(table, flag)
        if df is None:
            continue
        df["sector"] = df["sector"].map(lambda s: ICB_TO_GICS.get(s, s) if s and str(s).lower() != "nan" else "")
        for f in FLAGS:
            if f not in df.columns:
                df[f] = "no"
            else:
                df[f] = df[f].map(lambda v: "yes" if str(v).lower() == "yes" else "no")
            if f != flag:
                df[f] = "no"
        df[flag] = "yes"
        return df.reset_index(drop=True)
    raise RuntimeError("no symbol table on the constituent page")


def _read_index_cache(cache, spec):
    path = os.path.join(cache, spec["cache"])
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return read_csv(path), path
    legacy = spec.get("legacy")
    if legacy:
        old = os.path.join(cache, legacy)
        if os.path.exists(old) and os.path.getsize(old) > 0:
            return read_csv(old), path
    return pd.DataFrame(), path


def load_index(key, cfg, cache, mode):
    """One index list. Hourly and offline never call the network. A failed fetch keeps the cache."""
    spec = INDEX_SOURCES[key]
    cached, path = _read_index_cache(cache, spec)
    label = spec["log"]

    def finish(df, status, note, latest=""):
        log(label, status, latest, note)
        return _blank_flags(df, spec["flag"]) if len(df) else df

    switches = index_switches(cfg)
    switch_on = switches.get(key, True)
    if not switch_on and len(cached):
        return finish(cached, "OK", "switch is off, used the saved list for tags only", len(cached))
    if not switch_on:
        return finish(pd.DataFrame(), "OK", "switch is off and there is no saved list")
    if mode in ("offline", "hourly", "morning", "retry"):
        if len(cached):
            note = "offline mode, used cache" if mode == "offline" else "reused cache (refreshes once a day)"
            return finish(cached, "OK", note, len(cached))
        return finish(pd.DataFrame(), "MISSING", "no cache and this run does not refresh the list")
    stamp = STAMPS.get(spec["stamp"])
    if stamp == today_et() and len(cached) and "--force-slow" not in sys.argv:
        return finish(cached, "OK", "already fetched today", len(cached))
    try:
        df, src = india_data.fetch_index_table(key, cfg)
        df = _blank_flags(df, spec["flag"])
        df.to_csv(path, index=False)
        STAMPS[spec["stamp"]] = today_et()
        return finish(df, "OK", "%d names from %s" % (len(df), src.split("/")[2]), len(df))
    except Exception as exc:
        if len(cached):
            return finish(cached, "CACHED", str(exc)[:160], len(cached))
        return finish(pd.DataFrame(), "MISSING", str(exc)[:160])


def _blank_flags(df, yes_flag=None):
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["ticker", "company", "sector", *FLAGS])
    out = df.copy()
    for col in ("ticker", "company", "sector"):
        if col not in out.columns:
            out[col] = ""
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    for f in FLAGS:
        if f not in out.columns:
            out[f] = "no"
        out[f] = out[f].fillna("no").astype(str).str.lower().map(lambda v: "yes" if v == "yes" else "no")
    if yes_flag:
        out[yes_flag] = "yes"
    return out


def growth_frame(cfg):
    """Kept so older tests can build a third list. This desk does not use a growth list."""
    rows = []
    for t in cfg.get("growth_names", []):
        rows.append({
            "ticker": str(t).upper().strip(), "company": "", "sector": "",
            "in_nifty50": "no", "in_next50": "no", "in_midcap150": "no",
        })
    return pd.DataFrame(rows)


def _tag_listing(df):
    """Mark each row as an NSE symbol or a BSE symbol before the ISIN merge."""
    piece = _blank_flags(df)
    for col in ("nse_symbol", "bse_symbol", "bse_code", "isin"):
        if col not in piece.columns:
            piece[col] = ""
        piece[col] = piece[col].fillna("").astype(str).replace({"nan": ""})
    nse_like = piece[[f for f in FLAGS if f not in ("in_bse_only", "in_my_picks")]].eq("yes").any(axis=1)
    bse_like = piece["in_bse_only"].eq("yes") & ~nse_like
    piece.loc[bse_like & piece["bse_symbol"].eq(""), "bse_symbol"] = piece.loc[bse_like, "ticker"]
    piece.loc[~bse_like & piece["nse_symbol"].eq(""), "nse_symbol"] = piece.loc[~bse_like, "ticker"]
    return piece


def _first_text(series):
    for value in series:
        if isinstance(value, str) and value.strip() and value.lower() != "nan":
            return value.strip()
    return ""


def combine_indexes(parts, holdings, watch, switches, my_picks=None):
    """One row per company. The same ISIN on NSE and BSE keeps the NSE symbol."""
    frames = []
    for df in parts:
        if df is not None and len(df):
            frames.append(_tag_listing(df))
    picks = [str(t).upper().strip() for t in (my_picks or []) if str(t).strip()]
    always = {str(t).upper() for t in list(holdings) + list(watch) + picks}
    extra = []
    for ticker in always:
        extra.append({"ticker": ticker, "company": "", "sector": "", "in_my_picks": "yes" if ticker in picks else "no"})
    if extra:
        frames.append(_tag_listing(pd.DataFrame(extra)))
    id_cols = ["nse_symbol", "bse_symbol", "bse_code", "isin", "exchange"]
    cols = ["ticker", "company", "sector", *id_cols, *FLAGS, "index_membership"]
    if not frames:
        return pd.DataFrame(columns=cols)
    df = pd.concat(frames, ignore_index=True)
    for col in id_cols:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).replace({"nan": ""})
    df["isin"] = df["isin"].str.upper().str.strip()
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    isin_owner = {}
    for isin, symbol in zip(df["isin"], df["nse_symbol"]):
        if len(str(isin)) == 12 and str(symbol).strip():
            isin_owner[str(isin)] = str(symbol).strip().upper()
    df["_key"] = [
        "T" + isin_owner.get(isin, ticker)
        for isin, ticker in zip(df["isin"], df["ticker"])
    ]
    agg = {"company": _first_text, "sector": _first_text, "isin": _first_text,
           "nse_symbol": _first_text, "bse_symbol": _first_text, "bse_code": _first_text}
    for flag in FLAGS:
        agg[flag] = lambda s, _f=flag: "yes" if (s.astype(str) == "yes").any() else "no"
    # Ticker is the NSE symbol when we have one, else the BSE symbol.
    agg["ticker"] = _first_text
    df = df.groupby("_key", as_index=False).agg(agg)
    nse_flags = [f for f in FLAGS if f not in ("in_bse_only", "in_my_picks")]
    has_nse = df[nse_flags].eq("yes").any(axis=1)
    df.loc[df["nse_symbol"].eq("") & has_nse, "nse_symbol"] = df["ticker"]
    df.loc[df["nse_symbol"].ne(""), "ticker"] = df.loc[df["nse_symbol"].ne(""), "nse_symbol"]
    only_bse = df["nse_symbol"].eq("") & df["bse_symbol"].ne("")
    df.loc[only_bse, "ticker"] = df.loc[only_bse, "bse_symbol"]
    both = df["nse_symbol"].ne("") & df["bse_symbol"].ne("")
    bse_only = df["nse_symbol"].eq("") & (df["bse_symbol"].ne("") | df["in_bse_only"].eq("yes"))
    df["exchange"] = "NSE"
    df.loc[both, "exchange"] = "Both"
    df.loc[bse_only, "exchange"] = "BSE"
    df["index_membership"] = [
        membership_label(*row) for row in df[list(FLAGS)].itertuples(index=False, name=None)
    ]

    def keep(row):
        if row["ticker"] in always or row["in_my_picks"] == "yes":
            return True
        for key, flag in (
            ("nifty50", "in_nifty50"), ("next50", "in_next50"), ("midcap150", "in_midcap150"),
            ("smallcap250", "in_smallcap250"), ("microcap250", "in_microcap250"),
            ("totalmarket", "in_totalmarket"), ("other_nse", "in_other_nse"),
            ("sme", "in_sme"), ("bse_only", "in_bse_only"),
        ):
            default = SWITCH_DEFAULTS.get(key, True)
            if switches.get(key, default) and row[flag] == "yes":
                return True
        return False

    out = df[df.apply(keep, axis=1)].drop(columns=["_key"], errors="ignore").reset_index(drop=True)
    return out


# ---------------------------------------------------------------- slow SEC / yahoo / nasdaq
def cik_map(cfg, cache, mode):
    path = os.path.join(cache, "company_tickers.json")
    raw = None
    if os.path.exists(path):
        with open(path) as f:
            raw = json.load(f)
    allow = mode == "full" and (STAMPS.get("cik_map") != today_et() or raw is None or "--force-slow" in sys.argv)
    if allow:
        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            lim = netutil.RateLimiter(rl(cfg)["sec_requests_per_second"])
            r = netutil.http_get(requests, url, session_headers(cfg, sec=True), 40, limiter=lim, max_tries=rl(cfg)["max_retries"])
            raw = r.json()
            with open(path, "w") as f:
                json.dump(raw, f)
            STAMPS["cik_map"] = today_et()
            log("SEC company tickers", "OK", today_et(), "%d companies" % len(raw))
        except Exception as exc:
            if raw is not None:
                log("SEC company tickers", "CACHED", "", str(exc)[:160])
            else:
                log("SEC company tickers", "MISSING", "", str(exc)[:160])
                return {}
    elif raw is not None:
        log("SEC company tickers", "OK", STAMPS.get("cik_map", ""), "reused cache")
    else:
        log("SEC company tickers", "MISSING", "", "no cache")
        return {}
    out = {}
    for row in raw.values():
        t = str(row.get("ticker", "")).upper().replace(".", "-")
        if t:
            out[t] = str(row.get("cik_str")).zfill(10)
    return out


def _need_fetch(name, cache_file, mode, allow_morning=False):
    exists = os.path.exists(cache_file) and os.path.getsize(cache_file) > 0
    use = mode
    if mode == "morning" and not allow_morning:
        use = "offline"
    if mode == "retry":
        use = "full"
    return netutil.decide_slow(STAMPS.get(name), today_et(), exists, use, force="--force-slow" in sys.argv)


def _missing_tickers(df, tickers):
    """Names in today's universe that are not in the saved file yet."""
    if df is None or len(df) == 0 or "ticker" not in getattr(df, "columns", []):
        return list(tickers)
    have = set(df["ticker"].astype(str))
    return [t for t in tickers if t not in have]


def _balance_sheet_blank(annual):
    """True when the cache has filings but equity and debt are both empty.

    The old parser kept only facts tagged CY####. Balance-sheet facts usually
    have no such tag, so those two columns were saved as all blank.
    """
    if annual is None or len(annual) == 0:
        return False
    for col in ("equity", "debt"):
        if col not in annual.columns:
            continue
        if pd.to_numeric(annual[col], errors="coerce").notna().any():
            return False
    return True


def _flow_gap(annual):
    """True when recent years have revenue but the income-statement frame was dropped.

    Facts with no CY#### tag used to be skipped. That left net income blank on
    filings that do report it. One full run refetches so the new parser can keep them.
    """
    if annual is None or len(annual) == 0 or "net_income" not in getattr(annual, "columns", []):
        return False
    end = pd.to_datetime(annual["end"], errors="coerce") if "end" in annual.columns else pd.Series(pd.NaT, index=annual.index)
    recent = annual[end >= pd.Timestamp("2022-01-01")]
    if len(recent) < 100 or "revenue" not in recent.columns:
        return False
    rev = pd.to_numeric(recent["revenue"], errors="coerce")
    ni = pd.to_numeric(recent["net_income"], errors="coerce")
    return int((rev.notna() & ni.isna()).sum()) >= 80


def load_sec(tickers, cik, cfg, cache, mode):
    annual_p = os.path.join(cache, "annual.csv")
    quarter_p = os.path.join(cache, "quarters.csv")
    annual, quarters = read_csv(annual_p), read_csv(quarter_p)
    decision = _need_fetch("sec_facts", annual_p, mode)
    gaps = None
    sheet_blank = _balance_sheet_blank(annual)
    flow_gap = _flow_gap(annual)
    if decision == "reuse":
        gaps = _missing_tickers(annual, tickers) if mode == "full" else []
        gaps = [t for t in gaps if t in cik]
        # One full run may refetch when the saved statements are unusable.
        # Hourly and offline never call the SEC. This is the same daily pass, not an extra source.
        if mode == "full" and sheet_blank:
            print("SEC equity and debt are blank in the cache; refetching company facts")
            gaps = None
        elif mode == "full" and flow_gap:
            print("SEC annual net income is missing where revenue is present; refetching company facts")
            gaps = None
        elif not gaps:
            status = "PARTIAL" if sheet_blank else "OK"
            note = "reused cache (slow sources refresh at most once a day)"
            if sheet_blank:
                note = "reused cache; equity and debt are blank on every row. This run does not call the SEC."
            log("Fundamentals (SEC EDGAR company facts)", status, STAMPS.get("sec_facts", ""), note)
            return annual, quarters
        else:
            print("SEC filling %d names added since the daily fetch" % len(gaps))
    if decision == "missing":
        log("Fundamentals (SEC EDGAR company facts)", "MISSING", "", "no cache and this run does not call the SEC")
        return annual, quarters
    lim = netutil.RateLimiter(rl(cfg)["sec_requests_per_second"])
    headers = session_headers(cfg, sec=True)
    # A new day refreshes everyone. A crash the same day continues where it stopped.
    # A balance-sheet refetch ignores today's progress: those rows were parsed without equity.
    done = progress_load(cache, "sec")
    if mode == "full" and (sheet_blank or flow_gap) and not gaps:
        done = set()
    new_a, new_q, fails = [], [], 0
    pool = gaps if gaps else [t for t in tickers if t in cik]
    todo = [t for t in pool if t not in done]
    if done:
        print("SEC skipping %d names already fetched today" % len(done))
    for i, t in enumerate(todo):
        url = "https://data.sec.gov/api/xbrl/companyfacts/CIK%s.json" % cik[t]
        try:
            r = netutil.http_get(requests, url, headers, 60, limiter=lim, max_tries=rl(cfg)["max_retries"])
            a, q = fund.parse_companyfacts(r.json())
            if len(a):
                a = a.copy()
                a["ticker"] = t
                new_a.append(a)
            if len(q):
                q = q.copy()
                q["ticker"] = t
                new_q.append(q)
            done.add(t)
        except Exception as exc:
            fails += 1
            if i < 3:
                print("sec fail", t, str(exc)[:100])
        if (i + 1) % 40 == 0:
            print("SEC %d / %d" % (i + 1, len(todo)))
            annual, quarters = _flush_sec(annual, quarters, new_a, new_q, annual_p, quarter_p)
            progress_save(cache, "sec", done)
    annual, quarters = _flush_sec(annual, quarters, new_a, new_q, annual_p, quarter_p)
    progress_save(cache, "sec", done)
    fail_rate = fails / max(len(todo), 1)
    if fails == len(todo) and len(todo):
        status = "CACHED" if len(annual) else "MISSING"
        if status != "CACHED":
            STAMPS.pop("sec_facts", None)
        log("Fundamentals (SEC EDGAR company facts)", status, "", "all %d requests failed" % fails)
    elif fail_rate > 0.5:
        log("Fundamentals (SEC EDGAR company facts)", "CACHED", "", "%d of %d failed; will try again next full run" % (fails, len(todo)))
    else:
        STAMPS["sec_facts"] = today_et()
        note = "%d names" % annual["ticker"].nunique() if len(annual) else "0"
        if fails:
            note += ", %d failed and kept prior rows" % fails
        status = "OK"
        if _balance_sheet_blank(annual):
            status = "PARTIAL"
            note += "; equity and debt are still blank"
        log("Fundamentals (SEC EDGAR company facts)", status, today_et(), note)
    return annual, quarters


def _flush_sec(annual, quarters, new_a, new_q, annual_p, quarter_p):
    if new_a:
        add = pd.concat(new_a, ignore_index=True)
        keep = annual[~annual["ticker"].isin(add["ticker"])] if len(annual) else annual
        annual = pd.concat([keep, add], ignore_index=True)
        annual.to_csv(annual_p, index=False)
        new_a.clear()
    if new_q:
        add = pd.concat(new_q, ignore_index=True)
        keep = quarters[~quarters["ticker"].isin(add["ticker"])] if len(quarters) else quarters
        quarters = pd.concat([keep, add], ignore_index=True)
        quarters.to_csv(quarter_p, index=False)
        new_q.clear()
    return annual, quarters


def load_yahoo(tickers, cfg, cache, mode):
    info_p = os.path.join(cache, "yahoo_info.csv")
    earn_p = os.path.join(cache, "earnings.csv")
    info, earn = read_csv(info_p), read_csv(earn_p)
    decision = _need_fetch("yahoo_slow", info_p, mode)
    gaps = None
    if decision == "reuse":
        gaps = _missing_tickers(info, tickers) if mode == "full" else []
        if not gaps:
            log("Analyst and profile (Yahoo Finance)", "OK", STAMPS.get("yahoo_slow", ""), "reused cache (slow sources refresh at most once a day)")
            log("Earnings dates (Yahoo Finance)", "OK", STAMPS.get("yahoo_slow", ""), "reused cache")
            return info, earn
        print("Yahoo profiles filling %d names added since the daily fetch" % len(gaps))
    if decision == "missing":
        log("Analyst and profile (Yahoo Finance)", "MISSING", "", "no cache and this run does not call Yahoo profiles")
        log("Earnings dates (Yahoo Finance)", "MISSING", "", "no cache")
        return info, earn
    import yfinance as yf
    lim = netutil.RateLimiter(rl(cfg)["yahoo_profile_per_second"])
    done = progress_load(cache, "yahoo")
    rows, erows, fails = [], [], 0
    old_info = info.set_index("ticker") if len(info) and "ticker" in info.columns else None
    if len(info) and done:
        rows.extend(info[info["ticker"].isin(done)].to_dict("records"))
        if len(earn):
            erows.extend(earn[earn["ticker"].isin(done)].to_dict("records"))
    pool = gaps if gaps else list(tickers)
    todo = [t for t in pool if t not in done]
    if done:
        print("Yahoo profiles skipping %d names already fetched today" % len(done))
    for i, t in enumerate(todo):
        lim.wait()
        try:
            tk = yf.Ticker(t)
            def once():
                inf = tk.info or {}
                if not inf or (inf.get("regularMarketPrice") is None and inf.get("forwardPE") is None and inf.get("shortName") is None):
                    raise netutil.RetryableError("empty profile " + t)
                return inf
            inf = netutil.call_with_retry(once, max_tries=rl(cfg)["max_retries"])
            rows.append({
                "ticker": t,
                "company": inf.get("shortName") or inf.get("longName") or "",
                "sector": inf.get("sector") or "",
                "industry": inf.get("industry") or "",
                "forward_pe": inf.get("forwardPE"),
                "analyst_mean": inf.get("recommendationMean"),
                "analyst_count": inf.get("numberOfAnalystOpinions"),
                "target_mean": inf.get("targetMeanPrice"),
                "target_median": inf.get("targetMedianPrice"),
                    "earnings_ts": inf.get("earningsTimestamp"),
            })
            done.add(t)
            try:
                ed = tk.earnings_dates
            except Exception:
                ed = None
            if ed is not None and len(ed):
                ed = ed.reset_index()
                for _, r in ed.iterrows():
                    erows.append({
                        "ticker": t,
                        "earnings_dt": str(r.iloc[0]),
                        "eps_estimate": r.get("EPS Estimate"),
                        "eps_actual": r.get("Reported EPS"),
                        "surprise_pct": r.get("Surprise(%)"),
                    })
        except Exception:
            fails += 1
            if old_info is not None and t in old_info.index:
                rows.append(old_info.loc[t].to_dict())
        if (i + 1) % 25 == 0:
            print("Yahoo profiles %d / %d" % (i + 1, len(todo)))
            if rows:
                pd.DataFrame(rows).drop_duplicates("ticker", keep="last").to_csv(info_p, index=False)
            if erows:
                pd.DataFrame(erows).to_csv(earn_p, index=False)
            progress_save(cache, "yahoo", done)
    if rows:
        info = pd.DataFrame(rows).drop_duplicates("ticker", keep="last")
        info.to_csv(info_p, index=False)
    if erows:
        earn = pd.DataFrame(erows)
        # keep prior earnings for tickers we failed, if we got nothing for them
        if fails and os.path.exists(earn_p):
            prev = read_csv(earn_p)
            if len(prev):
                got = set(earn["ticker"])
                earn = pd.concat([earn, prev[~prev["ticker"].isin(got)]], ignore_index=True)
        earn.to_csv(earn_p, index=False)
    progress_save(cache, "yahoo", done)
    fail_rate = fails / max(len(todo), 1)
    if fail_rate > 0.5:
        log("Analyst and profile (Yahoo Finance)", "CACHED" if len(info) else "MISSING", "", "%d of %d failed" % (fails, len(tickers)))
        log("Earnings dates (Yahoo Finance)", "CACHED" if len(earn) else "MISSING", "", "same pass as profiles")
    else:
        STAMPS["yahoo_slow"] = today_et()
        log("Analyst and profile (Yahoo Finance)", "OK", today_et(), "%d names, %d failed" % (len(info), fails))
        log("Earnings dates (Yahoo Finance)", "OK" if len(earn) else "MISSING", today_et(), "%d rows" % len(earn))
    return info, earn


def _parse_asof(value):
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    return pd.Timestamp(ts)


def _latest_holder_rows(rows):
    """One row per filer, and only the newest quarter for that ticker.

    The holdings table mixes quarter-end dates. Summing them, or listing both,
    counts the same shares twice.
    """
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    if "ticker" not in frame.columns:
        return rows
    frame["_asof"] = frame["as_of"].map(_parse_asof) if "as_of" in frame.columns else pd.NaT
    kept = []
    for _ticker, sub in frame.groupby(frame["ticker"].astype(str), sort=False):
        latest = sub["_asof"].max()
        if pd.isna(latest):
            chunk = sub
        else:
            chunk = sub[sub["_asof"] == latest]
        chunk = chunk.copy()
        chunk["_owner"] = chunk["owner"].astype(str).str.strip().str.lower() if "owner" in chunk.columns else ""
        chunk = chunk.sort_values("_asof").drop_duplicates("_owner", keep="last")
        kept.append(chunk.drop(columns=["_asof", "_owner"], errors="ignore"))
    if not kept:
        return []
    return pd.concat(kept, ignore_index=True).to_dict("records")


def latest_shares_by_ticker(annual, quarters):
    """Newest SEC share count for each ticker. Blank stays blank."""
    parts = []
    for frame in (quarters, annual):
        if frame is None or len(frame) == 0 or "ticker" not in getattr(frame, "columns", []) or "shares" not in frame.columns:
            continue
        sub = frame[["ticker", "end", "shares"]].copy()
        sub["end"] = pd.to_datetime(sub["end"], errors="coerce")
        sub["shares"] = pd.to_numeric(sub["shares"], errors="coerce")
        sub = sub.dropna(subset=["end", "shares"])
        sub = sub[sub["shares"] > 0]
        parts.append(sub)
    if not parts:
        return {}
    all_rows = pd.concat(parts, ignore_index=True).sort_values("end")
    last = all_rows.drop_duplicates("ticker", keep="last")
    return dict(zip(last["ticker"].astype(str), last["shares"].astype(float)))


def ownership_percent(inst_shares, sec_shares, nasdaq_so_m, fallback_pct):
    """Holdings divided by the share count that matches the filing.

    Nasdaq divides total reported holdings by its own shares-outstanding figure.
    That denominator is often one class or a stale count, so the percent prints
    above 100. SEC shares can be one class too. The denominator is the larger of
    the two counts. Above 100 after that still means the holdings were counted
    twice; the caller flags it instead of pretending the raw percent was right.
    Returns (percent or None, exceeds_shares).
    """
    inst = _parse_int(inst_shares)
    sec = _parse_int(sec_shares)
    nq = _parse_int(nasdaq_so_m)
    if nq is not None and 0 < nq < 1_000_000:
        nq = nq * 1_000_000.0
    # A share count under 1,000,000 that matches Nasdaq after * 1,000,000 was
    # reported in millions (MCD). NVR's real 2.8 million shares is already above that.
    if sec is not None and 0 < sec < 1_000_000:
        scaled = sec * 1_000_000.0
        if nq and abs(scaled - nq) / nq <= 0.35:
            sec = scaled
        elif not nq:
            sec = scaled
    # Either source can be one share class. The smaller count pushes the percent
    # through 100. Use the larger count; still above 100 means the holdings overlap.
    denoms = [v for v in (sec, nq) if v and v > 0]
    denom = max(denoms) if denoms else None
    if inst is not None and denom and denom > 0:
        pct = inst / denom * 100.0
        return round(pct, 2), pct > 100.0
    own, capped = cap_ownership(fallback_pct)
    if own is None:
        return None, False
    return own, bool(capped)


def apply_ownership(holders, annual, quarters):
    """Replace Nasdaq's ownership percent with holdings / SEC shares."""
    if holders is None or len(holders) == 0:
        return holders
    out = holders.copy()
    shares = latest_shares_by_ticker(annual, quarters)
    pcts = []
    overs = []
    for _, r in out.iterrows():
        pct, over = ownership_percent(
            r.get("inst_shares"), shares.get(str(r.get("ticker"))), r.get("nasdaq_so_m"), r.get("ownership_pct"))
        pcts.append(pct)
        overs.append(over)
    out["ownership_pct"] = pcts
    out["_ownership_over"] = overs
    return out


def filer_name(name):
    """Keep a filer's own casing. Nasdaq title-cases short names (Fmr Llc, Blackrock)."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    text = str(name).strip()
    if not text:
        return ""
    known = {
        "fmr llc": "FMR LLC",
        "blackrock, inc.": "BlackRock, Inc.",
        "blackrock inc.": "BlackRock, Inc.",
        "blackrock, inc": "BlackRock, Inc.",
    }
    if text.lower() in known:
        return known[text.lower()]
    out = []
    for word in text.split():
        bare = word.strip(",")
        if bare.lower() in ("llc", "lp", "llp"):
            suffix = "," if word.endswith(",") else ""
            out.append(bare.upper() + suffix)
        else:
            out.append(word)
    return " ".join(out)


def cap_ownership(value):
    """Nasdaq's share of shares outstanding can exceed 100 when share classes overlap.

    Cap the published figure at 100 and say so. The raw feed is not a sum we control.
    """
    n = _parse_int(value)
    if n is None:
        return None, False
    if n > 100:
        return 100.0, True
    return n, False


def _parse_int(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if s in ("", "N/A", "--", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_holders(tickers, cfg, cache, mode):
    path = os.path.join(cache, "holders.csv")
    detail_p = os.path.join(cache, "holder_rows.csv")
    summary, detail = read_csv(path), read_csv(detail_p)
    decision = _need_fetch("holders", path, mode)
    gaps = None
    # The saved percent is Nasdaq's raw ratio. Recomputing it needs the holdings
    # total and Nasdaq's share count, which older caches did not keep.
    missing_parts = len(summary) > 0 and "inst_shares" not in summary.columns
    if decision == "reuse":
        gaps = _missing_tickers(summary, tickers) if mode == "full" else []
        if mode == "full" and missing_parts:
            print("13F cache has no holdings total; refetching so ownership is not just capped")
            gaps = None
            decision = "fetch"
        elif not gaps:
            log("Institutional 13F and insider (Nasdaq)", "OK", STAMPS.get("holders", ""), "reused cache (slow sources refresh at most once a day)")
            return summary, detail
        else:
            print("Nasdaq filling %d names added since the daily fetch" % len(gaps))
    if decision == "missing":
        log("Institutional 13F and insider (Nasdaq)", "MISSING", "", "no cache and this run does not call Nasdaq")
        return summary, detail
    lim = netutil.RateLimiter(rl(cfg)["nasdaq_requests_per_second"])
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    done = progress_load(cache, "holders")
    if mode == "full" and missing_parts:
        done = set()
    sums, rows, fails = [], [], 0
    old = summary.set_index("ticker") if len(summary) and "ticker" in summary.columns else None
    if len(summary) and done:
        sums.extend(summary[summary["ticker"].isin(done)].to_dict("records"))
    if len(detail) and done and "ticker" in detail.columns:
        rows.extend(detail[detail["ticker"].isin(done)].to_dict("records"))
    pool = gaps if gaps else list(tickers)
    todo = [t for t in pool if t not in done]
    if done:
        print("Nasdaq skipping %d names already fetched today" % len(done))
    for i, t in enumerate(todo):
        try:
            hurl = "https://api.nasdaq.com/api/company/%s/institutional-holdings?limit=5" % t
            iurl = "https://api.nasdaq.com/api/company/%s/insider-trades?limit=5" % t
            hr = netutil.http_get(requests, hurl, headers, 30, limiter=lim, max_tries=rl(cfg)["max_retries"])
            ir = netutil.http_get(requests, iurl, headers, 30, limiter=lim, max_tries=rl(cfg)["max_retries"])
            hd, idata = hr.json().get("data") or {}, ir.json().get("data") or {}
            increased = decreased = holders = own = None
            as_of = ""
            for r in ((hd.get("activePositions") or {}).get("rows") or []):
                name = r.get("positions") or ""
                if "Increased" in name:
                    increased = _parse_int(r.get("shares"))
                elif "Decreased" in name:
                    decreased = _parse_int(r.get("shares"))
                elif "Total" in name:
                    holders = _parse_int(r.get("holders"))
            own_s = ((hd.get("ownershipSummary") or {}).get("SharesOutstandingPCT") or {}).get("value")
            so_s = ((hd.get("ownershipSummary") or {}).get("ShareoutstandingTotal") or {}).get("value")
            own, _capped = cap_ownership(own_s)
            inst_shares = None
            for r in ((hd.get("activePositions") or {}).get("rows") or []):
                if "Total Institutional" in (r.get("positions") or ""):
                    inst_shares = _parse_int(r.get("shares"))
            table = ((hd.get("holdingsTransactions") or {}).get("table") or {})
            parsed_rows = []
            for r in (table.get("rows") or []):
                if not as_of:
                    as_of = r.get("date") or ""
                parsed_rows.append({
                    "ticker": t, "owner": filer_name(r.get("ownerName")), "shares": _parse_int(r.get("sharesHeld")),
                    "share_change": _parse_int(r.get("sharesChange")), "as_of": r.get("date") or "",
                })
            parsed_rows = _latest_holder_rows(parsed_rows)
            rows.extend(parsed_rows)
            buys = sells = None
            for r in ((idata.get("numberOfTrades") or {}).get("rows") or []):
                name = r.get("insiderTrade") or ""
                if "Buy" in name:
                    buys = _parse_int(r.get("months3"))
                elif "Sell" in name:
                    sells = _parse_int(r.get("months3"))
            sums.append({
                "ticker": t, "inst_up": increased, "inst_down": decreased, "holders": holders,
                "ownership_pct": own, "inst_shares": inst_shares, "nasdaq_so_m": _parse_int(so_s),
                "as_of": as_of, "insider_buys": buys, "insider_sells": sells,
            })
            done.add(t)
        except Exception:
            fails += 1
            if old is not None and t in old.index:
                sums.append(old.loc[t].to_dict())
        if (i + 1) % 40 == 0:
            print("Nasdaq %d / %d" % (i + 1, len(todo)))
            if sums:
                pd.DataFrame(sums).drop_duplicates("ticker", keep="last").to_csv(path, index=False)
            if rows:
                pd.DataFrame(rows).to_csv(detail_p, index=False)
            progress_save(cache, "holders", done)
    if sums:
        summary = pd.DataFrame(sums).drop_duplicates("ticker", keep="last")
        summary.to_csv(path, index=False)
    if rows:
        detail = pd.DataFrame(rows)
        detail.to_csv(detail_p, index=False)
    progress_save(cache, "holders", done)
    fail_rate = fails / max(len(todo), 1)
    if fail_rate > 0.5:
        log("Institutional 13F and insider (Nasdaq)", "CACHED" if len(summary) else "MISSING", "", "%d of %d failed" % (fails, len(tickers)))
    else:
        STAMPS["holders"] = today_et()
        log("Institutional 13F and insider (Nasdaq)", "OK", today_et(), "%d names, %d failed" % (len(summary), fails))
    return summary, detail


def load_news(tickers, cfg, cache, mode):
    path = os.path.join(cache, "news.csv")
    cached = read_csv(path) if os.path.exists(path) else pd.DataFrame()
    decision = _need_fetch("news", path, mode)
    if decision != "fetch":
        status = "OK" if len(cached) else "MISSING"
        note = "reused cache" if len(cached) else "no cache and this run does not fetch headlines"
        if decision == "missing":
            status = "MISSING"
        log("News headlines (Yahoo Finance)", status, STAMPS.get("news", ""), note)
        return cached
    lim = netutil.RateLimiter(rl(cfg)["news_per_second"])
    headers = {"User-Agent": "Mozilla/5.0"}
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    rows, fails = [], 0
    for t in tickers:
        try:
            def once(ticker=t):
                lim.wait()
                resp = requests.get(url, params={"q": ticker, "newsCount": 4, "quotesCount": 0}, headers=headers, timeout=20)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise netutil.RetryableError("news HTTP %s" % resp.status_code)
                if resp.status_code in (403, 404):
                    raise netutil.PermanentError("news HTTP %s" % resp.status_code)
                resp.raise_for_status()
                return resp.json()
            payload = netutil.call_with_retry(once, max_tries=3)
            for item in (payload.get("news") or [])[:4]:
                when = item.get("providerPublishTime")
                try:
                    published = pd.to_datetime(int(when), unit="s", utc=True).tz_convert(PT).strftime("%Y-%m-%d %H:%M PT")
                except Exception:
                    published = ""
                rows.append({
                    "ticker": t, "headline": item.get("title") or "", "publisher": item.get("publisher") or "",
                    "link": item.get("link") or "", "published": published,
                })
        except Exception:
            fails += 1
    if rows:
        df = pd.DataFrame(rows)
        if fails and len(cached):
            got = set(df["ticker"])
            df = pd.concat([df, cached[~cached["ticker"].isin(got)]], ignore_index=True)
        df.to_csv(path, index=False)
        STAMPS["news"] = today_et()
        log("News headlines (Yahoo Finance)", "OK", today_et(), "%d headlines, %d names failed" % (len(rows), fails))
        return df
    if len(cached):
        log("News headlines (Yahoo Finance)", "CACHED", "", "%d names failed" % fails)
        return cached
    log("News headlines (Yahoo Finance)", "MISSING", "", "no headlines")
    return pd.DataFrame()


def load_walls(tickers, cfg, cache, mode):
    path = os.path.join(cache, "option_walls.csv")
    cached = read_csv(path) if os.path.exists(path) else pd.DataFrame()
    decision = _need_fetch("option_walls", path, mode)
    if decision != "fetch":
        log("Option walls (Yahoo option chain)", "OK" if len(cached) else "MISSING", STAMPS.get("option_walls", ""),
            "reused cache (option chains refresh at most once a day)" if len(cached) else "no cache and this run does not download chains")
        return cached
    import yfinance as yf
    lim = netutil.RateLimiter(rl(cfg)["option_chain_per_second"])
    rows, fails = [], 0
    for t in tickers:
        try:
            lim.wait()
            tk = yf.Ticker(t)
            exps = list(tk.options or [])[:3]
            for exp in exps:
                lim.wait()
                chain = tk.option_chain(exp)
                for side, frame in (("call", chain.calls), ("put", chain.puts)):
                    if frame is None or len(frame) == 0:
                        continue
                    use = frame[pd.to_numeric(frame.get("openInterest"), errors="coerce").fillna(0) > 0]
                    for _, r in use.iterrows():
                        rows.append({
                            "ticker": t, "expiry": exp, "side": side, "strike": r.get("strike"),
                            "open_interest": r.get("openInterest"), "volume": r.get("volume"),
                        })
        except Exception:
            fails += 1
    if rows:
        df = pd.DataFrame(rows)
        # mark the strike with the most open interest on each side
        df["is_wall"] = "no"
        for (t, exp, side), g in df.groupby(["ticker", "expiry", "side"]):
            idx = pd.to_numeric(g["open_interest"], errors="coerce").idxmax()
            df.at[idx, "is_wall"] = "yes"
        df.to_csv(path, index=False)
        STAMPS["option_walls"] = today_et()
        log("Option walls (Yahoo option chain)", "OK", today_et(), "%d rows, %d names failed" % (len(df), fails))
        return df
    if len(cached):
        log("Option walls (Yahoo option chain)", "CACHED", "", "%d names failed" % fails)
        return cached
    log("Option walls (Yahoo option chain)", "MISSING", "", "no chains")
    return pd.DataFrame()


def load_pcr(cfg, cache, mode):
    path = os.path.join(cache, "pcr.csv")
    cached = read_csv(path) if os.path.exists(path) else pd.DataFrame()
    decision = _need_fetch("pcr", path, mode)
    if decision != "fetch":
        log("Put/call (CBOE)", "OK" if len(cached) else "MISSING", STAMPS.get("pcr", ""),
            "reused cache" if len(cached) else "no cache")
        return cached
    lim = netutil.RateLimiter(5)
    headers = session_headers(cfg)
    days = 160 if len(cached) < 40 else 6
    rows = []
    if len(cached):
        rows.extend(cached.to_dict("records"))
    have = set(str(r.get("date")) + "|" + str(r.get("name")) for r in rows)
    start = dt.date.today()
    got_new = 0
    for i in range(days):
        day = start - dt.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        f = os.path.join(cache, "pcr", "%s.json" % day)
        payload = None
        if os.path.exists(f) and i > 4:
            try:
                payload = json.load(open(f))
            except Exception:
                payload = None
        if payload is None:
            url = "https://cdn.cboe.com/data/us/options/market_statistics/daily/%s_daily_options" % day
            try:
                r = netutil.http_get(requests, url, headers, 20, limiter=lim, max_tries=2)
                payload = r.json()
                with open(f, "w") as fh:
                    json.dump(payload, fh)
                got_new += 1
            except Exception:
                continue
        for item in payload.get("ratios") or []:
            key = "%s|%s" % (day, item.get("name"))
            if key in have:
                continue
            try:
                val = float(item.get("value"))
            except (TypeError, ValueError):
                continue
            rows.append({"date": str(day), "name": item.get("name"), "value": val})
            have.add(key)
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates(["date", "name"]).sort_values(["name", "date"])
        df.to_csv(path, index=False)
        STAMPS["pcr"] = today_et()
        log("Put/call (CBOE)", "OK", df["date"].max(), "%d days refreshed" % got_new)
        return df
    log("Put/call (CBOE)", "MISSING", "", "no files")
    return df


def load_fred(cfg, cache, mode):
    """FRED is often blocked from GitHub runners. Failure must not stop the job."""
    out = {}
    if mode == "offline":
        for sid in ("DGS10", "T10Y2Y"):
            f = os.path.join(cache, "fred_%s.csv" % sid)
            if os.path.exists(f):
                s = pd.read_csv(f)
                s.columns = ["date", "v"][:len(s.columns)]
                v = pd.to_numeric(s.iloc[:, 1], errors="coerce").dropna()
                if len(v):
                    out[sid] = float(v.iloc[-1])
        log("FRED", "OK" if out else "MISSING", "", "offline mode")
        return out
    headers = session_headers(cfg)
    ok = False
    err = ""
    for sid in ("DGS10", "T10Y2Y"):
        f = os.path.join(cache, "fred_%s.csv" % sid)
        try:
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + sid
            r = netutil.http_get(requests, url, headers, 12, max_tries=2, delays=(1.5, 3.0))
            open(f, "w").write(r.text)
            ok = True
        except Exception as exc:
            err = str(exc)[:120]
        if os.path.exists(f):
            try:
                s = pd.read_csv(f)
                v = pd.to_numeric(s.iloc[:, 1], errors="coerce").dropna()
                if len(v):
                    out[sid] = float(v.iloc[-1])
            except Exception:
                pass
    if ok:
        log("FRED", "OK", today_et(), "10-year yield and 10y-2y")
    elif out:
        log("FRED", "CACHED", "", err or "request failed, used the saved file")
    else:
        log("FRED", "MISSING", "", err or "no data and no cache. GitHub runners often block FRED.")
    return out


def _num_text(v):
    if v is None:
        return None
    v = html.unescape(str(v)).replace("\xa0", " ").replace(",", "").strip()
    if v in ("", "-", "—", "N/A"):
        return None
    m = re.match(r"^([-+]?\d*\.?\d+)\s*([%KMBT]?)", v)
    if not m:
        return None
    x = float(m.group(1))
    return x * {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(m.group(2), 1)


def load_econ(cfg, cache, mode):
    path = os.path.join(cache, "econ.csv")
    cached = read_csv(path) if os.path.exists(path) else pd.DataFrame()
    decision = _need_fetch("econ", path, mode)
    if decision != "fetch":
        log("Economic calendar (Nasdaq)", "OK" if len(cached) else "MISSING", STAMPS.get("econ", ""),
            "reused cache" if len(cached) else "no cache")
        return cached
    lim = netutil.RateLimiter(rl(cfg)["nasdaq_requests_per_second"])
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    days = 120 if len(cached) < 20 else 12
    rows = []
    start = dt.date.today()
    for i in range(days):
        day = start - dt.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        f = os.path.join(cache, "econ", "%s.json" % day)
        payload = None
        if os.path.exists(f) and i > 3:
            try:
                payload = json.load(open(f))
            except Exception:
                payload = None
        if payload is None:
            url = "https://api.nasdaq.com/api/calendar/economicevents?date=%s" % day
            try:
                r = netutil.http_get(requests, url, headers, 25, limiter=lim, max_tries=2)
                payload = r.json()
                with open(f, "w") as fh:
                    json.dump(payload, fh)
            except Exception:
                continue
        for item in ((payload.get("data") or {}).get("rows") or []):
            if item.get("country") not in ("United States", "US"):
                continue
            event = (item.get("eventName") or "").strip()
            actual = _num_text(item.get("actual"))
            forecast = _num_text(item.get("consensus"))
            for cat, label, names, good in ECON_SPECS:
                if event not in names:
                    continue
                surprise = None if actual is None or forecast is None else actual - forecast
                signal = None if surprise is None else (1 if surprise > 0 else -1 if surprise < 0 else 0) * good
                rows.append({
                    "country": "US", "category": cat, "indicator": label, "date": str(day),
                    "actual": item.get("actual"), "forecast": item.get("consensus"),
                    "surprise": surprise, "signal": signal,
                })
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates(["indicator", "date"], keep="last")
        df.to_csv(path, index=False)
        STAMPS["econ"] = today_et()
        log("Economic calendar (Nasdaq)", "OK", df["date"].max(), "%d matched releases" % len(df))
        return df
    if len(cached):
        log("Economic calendar (Nasdaq)", "CACHED", "", "no fresh rows")
        return cached
    log("Economic calendar (Nasdaq)", "MISSING", "", "no matched releases")
    return df


# ---------------------------------------------------------------- score
def _rsi_series(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def _last(series, n=None):
    s = series.dropna()
    if n is not None and len(s) < n:
        return None
    if not len(s):
        return None
    return float(s.iloc[-1])


def _score_benchmark(row, close, cfg, nifty):
    """NSE names stay on the Nifty 50. BSE-only names use SENSEX when the switch is on and the bars are saved."""
    use = bool(((cfg or {}).get("benchmark") or {}).get("bse_only_uses_sensex", True))
    if not bool(((cfg or {}).get("features") or {}).get("sensex", True)):
        use = False
    exchange = str(row.get("exchange") or "").strip().upper()
    if use and exchange == "BSE" and close is not None and "^BSESN" in close.columns:
        series = close["^BSESN"].dropna()
        if len(series) > 63:
            return close["^BSESN"], "SENSEX"
    if nifty is not None:
        name = india_data.bench_column(close)
        return nifty, ("Nifty 50" if name == "^NSEI" else (name or "Nifty 50"))
    return None, "Nifty 50"


def market_features(close, high, low, vol, ticker, spy):
    if ticker not in close.columns:
        return None
    c = close[ticker].dropna()
    if len(c) < 30:
        return None
    h = high[ticker] if high is not None and ticker in high.columns else c
    l = low[ticker] if low is not None and ticker in low.columns else c
    v = vol[ticker] if vol is not None and ticker in vol.columns else None
    sma = lambda n: float(c.rolling(n).mean().iloc[-1]) if len(c) >= n else None
    rsi = _rsi_series(c)
    rsi_now = float(rsi.dropna().iloc[-1]) if rsi.dropna().shape[0] else None
    rsi_prev = float(rsi.dropna().iloc[-6]) if rsi.dropna().shape[0] > 6 else None
    prev_c = c.shift(1)
    tr = pd.concat([(h.reindex(c.index) - l.reindex(c.index)), (h.reindex(c.index) - prev_c).abs(), (l.reindex(c.index) - prev_c).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if tr.dropna().shape[0] >= 14 else float(c.diff().abs().rolling(14).mean().iloc[-1])
    price = float(c.iloc[-1])
    high252 = float(h.reindex(c.index).tail(252).max())
    low252 = float(l.reindex(c.index).tail(252).min())
    def ret(n):
        if len(c) > n and c.iloc[-1 - n] > 0:
            return float(c.iloc[-1] / c.iloc[-1 - n] - 1)
        return None
    rs = None
    if spy is not None:
        sp = spy.reindex(c.index).dropna()
        both = c.reindex(sp.index).dropna()
        if len(both) > 63 and len(sp) > 63:
            rs = float(both.iloc[-1] / both.iloc[-64] - 1) - float(sp.iloc[-1] / sp.iloc[-64] - 1)
    vol_ratio = dollar = None
    if v is not None:
        vv = v.reindex(c.index).dropna()
        if len(vv) > 20 and vv.tail(20).mean():
            vol_ratio = float(vv.iloc[-1] / vv.tail(20).mean())
            dollar = float(price * vv.tail(20).mean())
    ytd = None
    year = c.index[-1].year
    sub = c[c.index.year == year]
    if len(sub) > 1 and sub.iloc[0] > 0:
        ytd = float(sub.iloc[-1] / sub.iloc[0] - 1)
    return {
        "price": price,
        "sma20": sma(20), "sma50": sma(50), "sma100": sma(100), "sma200": sma(200),
        "rsi": rsi_now, "rsi_prev": rsi_prev, "atr": atr,
        "high252": high252, "low252": low252,
        "day_pct": ret(1), "ret_1w": ret(5), "ret_1m": ret(21), "ret_3m": ret(63), "ret_ytd": ytd,
        "rs_spy": rs, "vol_ratio": vol_ratio, "dollar_volume": dollar,
        "dist_52w": (price / high252 - 1) if high252 else None,
        "near_low": bool(low252 and price <= low252 * 1.01),
        "asof": str(c.index[-1].date()),
    }


def build_scores(universe, close, high, low, vol, annual, quarters, info, holders, earnings, cfg):
    scfg = cfg["scoring"]
    info_i = info.set_index("ticker") if len(info) else pd.DataFrame()
    hold_i = holders.set_index("ticker") if len(holders) else pd.DataFrame()
    prepared = {}
    q_by = {}
    if len(quarters):
        q = quarters.copy()
        for t, g in q.groupby("ticker"):
            q_by[t] = g
    bench_name = india_data.bench_column(close)
    spy = close[bench_name] if bench_name else None
    etf_ret = {}
    if spy is not None:
        for etf in SECTOR_ETF_BY_NAME.values():
            if etf in close.columns and len(close[etf].dropna()) > 63:
                e = close[etf].dropna()
                s = spy.reindex(e.index).dropna()
                if len(s) > 63:
                    etf_ret[etf] = float(e.iloc[-1] / e.iloc[-64] - 1) - float(s.iloc[-1] / s.iloc[-64] - 1)
    rows = []
    group_etf = {}
    for etf in cfg.get("sector_etfs", []):
        group_etf.setdefault(etf.get("group"), etf["ticker"])
    for _, u in universe.iterrows():
        t = u["ticker"]
        bench_series, bench_label = _score_benchmark(u, close, cfg, spy)
        mkt = market_features(close, high, low, vol, t, bench_series)
        if not mkt:
            continue
        if t not in prepared:
            sub = annual[annual["ticker"] == t] if len(annual) and "ticker" in annual.columns else pd.DataFrame()
            prepared[t] = fund.prepare_annual(sub, close[t].dropna()) if t in close.columns and len(sub) else pd.DataFrame()
        fin = fund.metrics_asof(prepared[t], mkt["asof"], mkt["price"], q_by.get(t))
        inf = info_i.loc[t].to_dict() if len(info_i) and t in info_i.index else {}
        if isinstance(info_i.loc[t], pd.DataFrame) if len(info_i) and t in info_i.index else False:
            inf = info_i.loc[t].iloc[-1].to_dict()
        hol = hold_i.loc[t].to_dict() if len(hold_i) and t in hold_i.index else {}
        if len(hold_i) and t in hold_i.index and isinstance(hold_i.loc[t], pd.DataFrame):
            hol = hold_i.loc[t].iloc[-1].to_dict()
        eps_flag = rev_flag = None
        if len(earnings) and "ticker" in earnings.columns:
            sube = earnings[earnings["ticker"] == t].copy()
            if len(sube):
                sube["earnings_dt"] = pd.to_datetime(sube["earnings_dt"], utc=True, errors="coerce")
                past = sube[pd.to_numeric(sube["eps_actual"], errors="coerce").notna()].sort_values("earnings_dt")
                if len(past):
                    last = past.iloc[-1]
                    eps_flag = scoring.beat_flag(scoring._f(last["eps_actual"]), scoring._f(last["eps_estimate"]))
        sector = gics_sector(u.get("sector") or inf.get("sector") or "")
        etf = SECTOR_ETF_BY_NAME.get(sector) or group_etf.get(sector)
        extra = {
            "forward_pe": scoring._f(inf.get("forward_pe")),
            "analyst_mean": scoring._f(inf.get("analyst_mean")),
            "analyst_n": scoring._f(inf.get("analyst_count")),
            "target_mean": scoring._f(inf.get("target_mean")),
            "target_median": scoring._f(inf.get("target_median")),
            "inst_up": scoring._f(hol.get("inst_up")) if scoring._f(hol.get("inst_up")) is not None else scoring._f(hol.get("_inst_up")),
            "inst_down": scoring._f(hol.get("inst_down")) if scoring._f(hol.get("inst_down")) is not None else scoring._f(hol.get("_inst_down")),
            "insider_buys": scoring._f(hol.get("insider_buys")),
            "insider_sells": scoring._f(hol.get("insider_sells")),
            "eps_flag": eps_flag, "rev_flag": rev_flag,
            "sector_excess": etf_ret.get(etf),
        }
        rec = scoring.score_components(fin, mkt, extra, scfg)
        # display percents
        for key in ("rev_growth", "rev_growth_avg", "eps_growth", "eps_growth_avg", "roe", "roe_avg",
                    "div_yield", "div_yield_avg", "day_pct", "ret_1w", "ret_1m", "ret_3m", "ret_ytd", "rs_spy", "dist_52w"):
            val = rec.get(key, mkt.get(key) if key in ("day_pct", "ret_1w", "ret_1m", "ret_3m", "ret_ytd") else None)
        rec["day_pct"] = _pct(mkt["day_pct"])
        rec["ret_1w"] = _pct(mkt["ret_1w"])
        rec["ret_1m"] = _pct(mkt["ret_1m"])
        rec["ret_3m"] = _pct(mkt["ret_3m"])
        rec["ret_ytd"] = _pct(mkt["ret_ytd"])
        rec["rs_spy_3m"] = _pct(mkt["rs_spy"])
        rec["rs_benchmark"] = bench_label
        rec["dist_52w_high_pct"] = _pct(mkt["dist_52w"])
        for key in ("rev_growth", "eps_growth", "roe", "div_yield"):
            rec[key] = _pct(rec.get(key))
            rec[key + "_avg"] = _pct(rec.get(key + "_avg"))
        rec.update({
            "ticker": t,
            "company": u.get("company") or inf.get("company") or "",
            "sector": sector,
            "industry": inf.get("industry") or "",
            "index_membership": u.get("index_membership") or membership_label(u.get("in_nifty50"), u.get("in_next50"), u.get("in_midcap150")),
            "universe": u.get("index_membership") or membership_label(u.get("in_nifty50"), u.get("in_next50"), u.get("in_midcap150")),
            "price": round(mkt["price"], 2),
            "upside_pct": _upside_pct(extra.get("target_mean"), mkt["price"]),
            "price_as_of": mkt["asof"],
            "rsi14": None if mkt["rsi"] is None else round(mkt["rsi"], 1),
            "volume_ratio": None if mkt["vol_ratio"] is None else round(mkt["vol_ratio"], 2),
            "dollar_volume": mkt["dollar_volume"],
            "above_sma20": _above(mkt["price"], mkt["sma20"]),
            "above_sma50": _above(mkt["price"], mkt["sma50"]),
            "above_sma100": _above(mkt["price"], mkt["sma100"]),
            "above_sma200": _above(mkt["price"], mkt["sma200"]),
            "near_low": mkt["near_low"],
            "analyst_mean": extra["analyst_mean"],
            "analyst_count": extra["analyst_n"],
            "fundamentals_basis": fin.get("basis") or "",
            "fundamentals_filed": fin.get("filed") or "",
            "fin_avg_years": fin.get("avg_years") or 0,
            "inst_up": extra["inst_up"], "inst_down": extra["inst_down"],
            "insider_buys_3m": extra["insider_buys"], "insider_sells_3m": extra["insider_sells"],
            "holders_asof": hol.get("as_of") or "",
            "ownership_pct": hol.get("ownership_pct"),
            "holders_n": hol.get("holders"),
            "dps": fin.get("dps"),
            "prepared": prepared[t],
        })
        # next earnings
        nxt = ""
        if len(earnings) and "ticker" in earnings.columns:
            sube = earnings[earnings["ticker"] == t]
            if len(sube):
                dts = pd.to_datetime(sube["earnings_dt"], utc=True, errors="coerce")
                future = dts[dts > pd.Timestamp.now(tz="UTC")]
                if len(future):
                    nxt = str(future.min().date())
        if not nxt and inf.get("earnings_ts"):
            try:
                nxt = str(pd.to_datetime(float(inf["earnings_ts"]), unit="s").date())
            except Exception:
                nxt = ""
        rec["next_earnings"] = nxt
        miss = tables.missing_fields(rec)
        rec["missing_fields"] = ";".join(miss)
        rec["missing_count"] = len(miss)
        for k in ("entry_low", "entry_high", "stop", "trade_target", "target_analyst", "target_pfcf", "target_peg", "target_blended"):
            if rec.get(k) is not None and np.isfinite(rec[k]):
                rec[k] = round(float(rec[k]), 2)
            elif rec.get(k) is not None and not np.isfinite(rec.get(k) or np.nan):
                rec[k] = None
        if rec.get("reward_risk") is not None and np.isfinite(rec["reward_risk"]):
            rec["reward_risk"] = round(float(rec["reward_risk"]), 2)
        rows.append(rec)
    df = pd.DataFrame(rows)
    if len(df):
        df = scoring.add_industry(df, scfg["flat_band_pct"])
        df = scoring.apply_sector_point_fallback(df, scfg)
        misses, counts = [], []
        for _, rec in df.iterrows():
            fields = tables.missing_fields(rec)
            misses.append(";".join(fields))
            counts.append(len(fields))
        df["missing_fields"] = misses
        df["missing_count"] = counts
        df = assign_ranks(df)
    return df, prepared


def assign_ranks(df):
    """Rank 1..N by score, then fewer missing inputs, then ticker.

    A row with no score stays blank. Missing is not ranked as zero, and it does not take a number.
    """
    if df is None or len(df) == 0 or "score" not in getattr(df, "columns", []):
        return df
    out = df.copy()
    score = pd.to_numeric(out["score"], errors="coerce")
    if "missing_count" in out.columns:
        miss = pd.to_numeric(out["missing_count"], errors="coerce").fillna(10 ** 9)
    else:
        miss = pd.Series(0, index=out.index)
    ticker = out["ticker"].astype(str) if "ticker" in out.columns else pd.Series("", index=out.index)
    order = pd.DataFrame({"score": score, "miss": miss, "ticker": ticker}, index=out.index)
    order = order.sort_values(["score", "miss", "ticker"], ascending=[False, True, True], na_position="last", kind="mergesort")
    out = out.loc[order.index].copy()
    n = int(order["score"].notna().sum())
    ranks = list(range(1, n + 1)) + [pd.NA] * (len(out) - n)
    out["rank"] = pd.array(ranks, dtype="Int64")
    front = ["rank"] + [c for c in out.columns if c != "rank"]
    return out[front]


def _pct(x):
    if x is None or not np.isfinite(x):
        return None
    return round(float(x) * 100, 2)


def _above(price, sma):
    if sma is None or not np.isfinite(sma):
        return ""
    return 1 if price > sma else 0


def apply_feature_blanks(df, features):
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    if not features.get("score_breakdown", True):
        for c in out.columns:
            if c.startswith("pts_") or c in ("score", "confidence"):
                out[c] = np.nan
    if not features.get("verdicts", True):
        for c in ("verdict", "reason", "entry_low", "entry_high", "stop", "trade_target", "reward_risk"):
            if c in out.columns:
                out[c] = np.nan if c != "verdict" and c != "reason" else ""
    if not features.get("momentum_timing", True):
        for c in ("timing", "sma_alignment", "rs_spy_3m", "dist_52w_high_pct", "volume_ratio", "rsi14"):
            if c in out.columns:
                out[c] = np.nan if c != "timing" and c != "sma_alignment" else ""
    if not features.get("freshness_flags", True):
        for c in ("missing_fields", "missing_count", "price_status", "fundamentals_status", "analyst_status", "holders_status"):
            if c in out.columns:
                out[c] = ""
    return out


def holdings_table(cfg, inp):
    path = os.path.join(inp, "holdings.csv")
    if os.path.exists(path):
        df = read_csv(path)
        if len(df):
            return df
    rows = cfg.get("holdings") or []
    df = pd.DataFrame(rows)
    if len(df):
        os.makedirs(inp, exist_ok=True)
        df.to_csv(path, index=False)
    return df


def watch_table(cfg, inp):
    path = os.path.join(inp, "my_watchlist.csv")
    if os.path.exists(path):
        df = read_csv(path)
        if len(df):
            return df
    rows = [{"ticker": t, "note": ""} for t in cfg.get("watchlist", [])]
    df = pd.DataFrame(rows)
    if len(df):
        os.makedirs(inp, exist_ok=True)
        df.to_csv(path, index=False)
    return df


def build_portfolio(holds, scores, history):
    if holds is None or len(holds) == 0 or scores is None or len(scores) == 0:
        return pd.DataFrame(), pd.DataFrame()
    sc = scores.set_index("ticker")
    rows = []
    for _, h in holds.iterrows():
        t = str(h["ticker"]).upper()
        if t not in sc.index:
            continue
        r = sc.loc[t]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        shares = float(h["shares"])
        cost = float(h["avg_cost"])
        price = float(r["price"])
        value = shares * price
        basis = shares * cost
        week = _week_score(history, t)
        change = None if week is None or scoring._f(r.get("score")) is None else int(r["score"]) - int(week)
        status = "On track"
        if scoring._f(r.get("stop")) and price < float(r["stop"]):
            status = "Below stop"
        elif r.get("next_earnings"):
            try:
                days = (pd.Timestamp(r["next_earnings"]) - pd.Timestamp.now().normalize()).days
                if 0 <= days <= 7:
                    status = "Earnings soon"
            except Exception:
                pass
        if status == "On track" and change is not None and change <= -2:
            status = "Weakening"
        rows.append({
            "ticker": t, "company": r.get("company"), "shares": shares, "avg_cost": cost, "price": price,
            "day_pct": r.get("day_pct"), "value": round(value, 2), "cost": round(basis, 2),
            "gain": round(value - basis, 2), "gain_pct": round((price / cost - 1) * 100, 2) if cost else None,
            "score": r.get("score"), "score_week_ago": week, "score_week_change": change,
            "verdict": r.get("verdict"), "stop": r.get("stop"), "status": status,
            "example": h.get("example", ""),
        })
    port = pd.DataFrame(rows)
    if not len(port):
        return port, pd.DataFrame()
    total = port["value"].sum()
    port["weight_pct"] = (port["value"] / total * 100).round(1) if total else np.nan
    day = 0.0
    for _, r in port.iterrows():
        pct = scoring._f(r.get("day_pct"))
        if pct is not None:
            day += r["value"] - r["value"] / (1 + pct / 100.0)
    needs = int(port["status"].isin(["Below stop", "Weakening", "Earnings soon"]).sum())
    example = "yes" if (port["example"].astype(str).str.lower() == "yes").any() else "no"
    summary = pd.DataFrame([{
        "value": round(float(total), 2),
        "day_pnl": round(day, 2),
        "day_pnl_pct": round(day / (total - day) * 100, 2) if total != day else None,
        "total_gain": round(float(port["gain"].sum()), 2),
        "total_gain_pct": round(float(port["gain"].sum()) / float(port["cost"].sum()) * 100, 2) if port["cost"].sum() else None,
        "avg_score": round(float(pd.to_numeric(port["score"], errors="coerce").mean()), 2),
        "needs_attention": needs,
        "n_holdings": int(len(port)),
        "example_warning": "These holdings include example rows. Edit input/holdings.csv. This desk never places a trade." if example == "yes" else "",
    }])
    return port, summary


def _week_score(history, ticker):
    if history is None or len(history) == 0:
        return None
    sub = history[history["ticker"] == ticker].copy()
    if not len(sub):
        return None
    sub["date"] = pd.to_datetime(sub["date"])
    cut = pd.Timestamp.now().normalize() - pd.Timedelta(days=7)
    old = sub[sub["date"] <= cut]
    if not len(old):
        return None
    return scoring._f(old.sort_values("date").iloc[-1]["score"])


def build_watch(watch, scores):
    if watch is None or len(watch) == 0 or scores is None or len(scores) == 0:
        return pd.DataFrame()
    sc = scores.set_index("ticker")
    rows = []
    for _, w in watch.iterrows():
        t = str(w["ticker"]).upper()
        if t not in sc.index:
            continue
        r = sc.loc[t]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        price = scoring._f(r.get("price"))
        hi = scoring._f(r.get("entry_high"))
        dist = None
        if price and hi:
            dist = round((price / hi - 1) * 100, 2)
        rows.append({
            "ticker": t, "company": r.get("company"), "price": r.get("price"), "day_pct": r.get("day_pct"),
            "score": r.get("score"), "verdict": r.get("verdict"),
            "entry_low": r.get("entry_low"), "entry_high": r.get("entry_high"),
            "distance_to_entry_pct": dist, "timing": r.get("timing"), "note_input": w.get("note", ""),
        })
    return pd.DataFrame(rows)


# Scorecard chart window. About half a year of sessions. The job's full history
# stays in cache/ohlcv.csv.gz and is not copied into the sheet.
CHART_BARS = 126
# About three years of sessions. The browser computes the averages from these bars.
CANDLE_BARS = india_data.CANDLE_SESSIONS
_TICKER_FILE = re.compile(r"^[A-Z0-9&][A-Z0-9.&\-]{0,18}$")


def _upside_pct(target_mean, price):
    """Percent upside from the mean analyst target. Blank when either input is missing."""
    target = scoring._f(target_mean)
    px = scoring._f(price)
    if target is None or px is None or px <= 0:
        return None
    return round((target / px - 1) * 100, 2)


def _column_blank(df, col):
    if df is None or len(df) == 0 or col not in getattr(df, "columns", []):
        return True
    return not pd.to_numeric(df[col], errors="coerce").notna().any()


def price_file(close, scores):
    if close is None or close.empty or scores is None or len(scores) == 0:
        return pd.DataFrame()
    names = [t for t in scores["ticker"] if t in close.columns]
    names = list(dict.fromkeys(names))
    if not names:
        return pd.DataFrame()
    # Average each ticker on the sessions it actually traded, using the full
    # cache, and only then keep the chart window. A holiday hole in the wide
    # frame used to blank the next 20 or 50 bars.
    px = close[names].tail(CHART_BARS)
    window = px.index
    sma20 = {}
    sma50 = {}
    for t in names:
        traded = pd.to_numeric(close[t], errors="coerce").dropna()
        sma20[t] = traded.rolling(20, min_periods=20).mean().reindex(window)
        sma50[t] = traded.rolling(50, min_periods=50).mean().reindex(window)
    levels = scores.drop_duplicates("ticker", keep="first").set_index("ticker")
    level_cols = ("entry_low", "entry_high", "stop", "trade_target")
    pieces = []
    for t in names:
        vals = pd.to_numeric(px[t], errors="coerce").dropna()
        if not len(vals):
            continue
        part = pd.DataFrame({
            "date": [str(pd.Timestamp(d).date()) for d in vals.index],
            "ticker": t,
            "close": [round(float(v), 2) for v in vals.values],
            "sma20": [None if pd.isna(v) else round(float(v), 2) for v in sma20[t].reindex(vals.index).values],
            "sma50": [None if pd.isna(v) else round(float(v), 2) for v in sma50[t].reindex(vals.index).values],
        })
        for col in level_cols:
            part[col] = levels.at[t, col] if col in levels.columns else None
        pieces.append(part)
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True)


def candle_file(long_df, tickers, bars=CANDLE_BARS):
    """OHLC sessions per ticker for the site price chart.

    High, low, close, volume, and open come from the price cache. Open stays
    blank when that cache has no open column. `bars` is None to keep the whole
    cache, or a session count to keep only the tail. Moving averages are not
    stored here; the chart computes them in the browser.
    """
    cols = ["date", "ticker", "open", "high", "low", "close", "volume"]
    if long_df is None or len(long_df) == 0 or not tickers or "close" not in getattr(long_df, "columns", []):
        return pd.DataFrame(columns=cols)
    want = []
    for t in tickers:
        s = str(t or "").strip().upper()
        if _TICKER_FILE.match(s):
            want.append(s)
    want = list(dict.fromkeys(want))
    if not want:
        return pd.DataFrame(columns=cols)
    x = long_df[long_df["ticker"].astype(str).str.upper().isin(want)].copy()
    if not len(x):
        return pd.DataFrame(columns=cols)
    x["ticker"] = x["ticker"].astype(str).str.upper()
    x["date"] = pd.to_datetime(x["date"])
    for col in ("open", "high", "low", "close", "volume"):
        if col not in x.columns:
            x[col] = np.nan
        else:
            x[col] = pd.to_numeric(x[col], errors="coerce")
    x = x.dropna(subset=["close"]).sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    parts = []
    for _, g in x.groupby("ticker", sort=False):
        g = g.copy()
        if bars:
            g = g.tail(int(bars))
        parts.append(g)
    if not parts:
        return pd.DataFrame(columns=cols)
    out = pd.concat(parts, ignore_index=True)
    for col in ("open", "high", "low", "close"):
        out[col] = out[col].round(2)
    out["volume"] = out["volume"].round(0).astype("Int64")
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out[cols]


def write_candle_files(frame, out_dir):
    """One compact CSV per ticker. Rewrites a file only when its text changed.

    Returns how many files were rewritten.
    """
    os.makedirs(out_dir, exist_ok=True)
    if frame is None or len(frame) == 0 or "ticker" not in frame.columns:
        return 0
    keep = set()
    rewritten = 0
    cols = [c for c in frame.columns if c != "ticker"]
    for ticker, g in frame.groupby("ticker", sort=False):
        name = str(ticker) + ".csv"
        keep.add(name)
        text = g[cols].to_csv(index=False, na_rep="")
        path = os.path.join(out_dir, name)
        old = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                old = fh.read()
        if old == text:
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        rewritten += 1
    for name in os.listdir(out_dir):
        if name.endswith(".csv") and name not in keep:
            os.remove(os.path.join(out_dir, name))
    return rewritten


def candle_group(ticker):
    text = str(ticker or "").upper()
    if text.startswith("^"):
        return "_indexes"
    if text[:1] >= "A" and text[:1] <= "Z":
        return text[:1]
    return "0"


def write_candle_groups(frame, out_dir):
    """One gzipped CSV per letter. Rewrites a group only when its bytes changed."""
    import gzip
    os.makedirs(out_dir, exist_ok=True)
    if frame is None or len(frame) == 0 or "ticker" not in frame.columns:
        return 0
    frame = frame.copy()
    frame["_group"] = frame["ticker"].map(candle_group)
    rewritten = 0
    keep = set()
    for group, part in frame.groupby("_group", sort=False):
        name = "%s.csv.gz" % group
        keep.add(name)
        body = part.drop(columns="_group").to_csv(index=False, na_rep="").encode("utf-8")
        path = os.path.join(out_dir, name)
        old = b""
        if os.path.exists(path):
            with open(path, "rb") as fh:
                old = fh.read()
        packed = gzip.compress(body, mtime=0)
        if old == packed:
            continue
        with open(path, "wb") as fh:
            fh.write(packed)
        rewritten += 1
    for name in os.listdir(out_dir):
        if name.endswith(".csv"):
            os.remove(os.path.join(out_dir, name))
        elif name.endswith(".csv.gz") and name not in keep:
            os.remove(os.path.join(out_dir, name))
    return rewritten


def news_rows(news, scores):
    rows = []
    if news is None or len(news) == 0:
        return pd.DataFrame()
    reasons = scores.set_index("ticker")["reason"].to_dict() if len(scores) else {}
    seen = set()
    for _, r in news.iterrows():
        tone, tone_note = scoring.headline_tone(r.get("headline"))
        rows.append({
            "ticker": r["ticker"], "kind": "headline", "headline": r.get("headline"),
            "summary": "%s Source: %s. %s" % (r.get("headline"), r.get("publisher") or "unknown", tone_note),
            "publisher": r.get("publisher"), "link": r.get("link"), "published": r.get("published"),
            "tone": tone, "tone_note": tone_note,
        })
        seen.add(r["ticker"])
    for t in seen:
        if t in reasons and reasons[t]:
            rows.append({
                "ticker": t, "kind": "desk_note", "headline": "Desk note",
                "summary": reasons[t], "publisher": "Desk research note", "link": "", "published": "",
                "tone": "", "tone_note": "This line is the desk's own score sentence, not a news article.",
            })
    return pd.DataFrame(rows)


def attach_status(scores, price_status, fin_status, an_status, hold_status):
    if scores is None or len(scores) == 0:
        return scores
    scores = scores.copy()
    scores["price_status"] = price_status
    scores["fundamentals_status"] = fin_status
    scores["analyst_status"] = an_status
    scores["holders_status"] = hold_status
    scores["data_status"] = "OK"
    scores["note"] = ""
    scores["disclaimer"] = DISCLAIMER
    return scores


def source_status(name):
    for row in LOG:
        if row["source"] == name:
            return row["status"]
    return ""


def _slow_note(mode, have):
    if have and mode == "offline":
        return "offline mode, used cache"
    if have:
        return "reused cache (slow sources refresh at most once a day)"
    return "no cache and this run does not call the network"


def _stock_names(tickers):
    out = []
    for t in tickers or []:
        s = str(t).upper().strip()
        if not s or s.startswith("^") or s.endswith("=X"):
            continue
        out.append(s)
    return list(dict.fromkeys(out))


def load_statements(tickers, cfg, cache, mode):
    """Yahoo statements, profile, and earnings dates. At most once per IST day."""
    annual_p = os.path.join(cache, "annual.csv")
    quarter_p = os.path.join(cache, "quarters.csv")
    info_p = os.path.join(cache, "yahoo_info.csv")
    earn_p = os.path.join(cache, "earnings.csv")
    annual, quarters = read_csv(annual_p), read_csv(quarter_p)
    info, earn = read_csv(info_p), read_csv(earn_p)
    names = _stock_names(tickers)
    decision = _need_fetch("yahoo_statements", annual_p, mode)
    if decision == "fetch" and STAMPS.get("yahoo_slow") == today_et() and "--force-slow" not in sys.argv and len(info):
        decision = "reuse"
    gaps = []
    if decision == "reuse":
        base = annual if len(annual) else info
        gaps = _missing_tickers(base, names) if mode == "full" else []
        if not gaps:
            note = _slow_note(mode, len(annual) > 0)
            stamp = STAMPS.get("yahoo_statements") or STAMPS.get("yahoo_slow") or ""
            log("Fundamentals (Yahoo statements)", "OK" if len(annual) else "MISSING", stamp,
                note if len(annual) else "no statements in the cache. This run does not call Yahoo.")
            log("Analyst and profile (Yahoo Finance)", "OK" if len(info) else "MISSING", STAMPS.get("yahoo_slow", ""),
                _slow_note(mode, len(info) > 0) if len(info) else "no cache and this run does not call Yahoo profiles")
            log("Earnings dates (Yahoo Finance)", "OK" if len(earn) else "MISSING", STAMPS.get("yahoo_slow", ""),
                "reused cache" if len(earn) else "no cache")
            return annual, quarters, info, earn
        print("Yahoo statements filling %d new names" % len(gaps))
    if decision == "missing":
        log("Fundamentals (Yahoo statements)", "MISSING", "", "no cache and this run does not call Yahoo")
        log("Analyst and profile (Yahoo Finance)", "MISSING", "", "no cache and this run does not call Yahoo profiles")
        log("Earnings dates (Yahoo Finance)", "MISSING", "", "no cache")
        return annual, quarters, info, earn

    lim = netutil.RateLimiter(rl(cfg).get("yahoo_profile_per_second") or 1)
    done = progress_load(cache, "yahoo_statements")
    cap = int((cfg.get("rate_limit") or {}).get("yahoo_statements_per_run") or 160)
    days = int((cfg.get("rate_limit") or {}).get("fundamentals_refresh_days") or 5)
    have = set()
    fetched_on = {}
    if len(info) and "ticker" in info.columns:
        have = set(info["ticker"].astype(str))
        if "fetched_on" in info.columns:
            for ticker, stamp in zip(info["ticker"].astype(str), info["fetched_on"].astype(str)):
                fetched_on[ticker] = stamp
    if len(annual) and "ticker" in annual.columns:
        have |= set(annual["ticker"].astype(str))
    cutoff = (pd.Timestamp(today_et()) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    missing = [t for t in names if t not in have]
    stale = [t for t in names if t in have and fetched_on.get(t, "0000") <= cutoff and t not in missing]
    # A name with no fetched_on date is treated as due on its bucket day, not all at once.
    day_num = pd.Timestamp(today_et()).toordinal()
    rotating = []
    for ticker in names:
        if ticker in missing or ticker in stale:
            continue
        if fetched_on.get(ticker):
            continue
        if (day_num + (sum(ord(ch) for ch in ticker) % days)) % days == 0:
            rotating.append(ticker)
    pool = [t for t in missing + stale + rotating if t not in done]
    if gaps:
        pool = [t for t in gaps if t not in done] + [t for t in pool if t not in gaps]
    todo = pool[:cap]
    if not todo:
        note = _slow_note(mode, len(annual) > 0)
        stamp = STAMPS.get("yahoo_statements") or STAMPS.get("yahoo_slow") or ""
        log("Fundamentals (Yahoo statements)", "OK" if len(annual) else "MISSING", stamp,
            "every name is inside the refresh window" if len(annual) else note)
        log("Analyst and profile (Yahoo Finance)", "OK" if len(info) else "MISSING", STAMPS.get("yahoo_slow", ""),
            "same slice" if len(info) else "no cache")
        log("Earnings dates (Yahoo Finance)", "OK" if len(earn) else "MISSING", STAMPS.get("yahoo_slow", ""),
            "reused cache" if len(earn) else "no cache")
        return annual, quarters, info, earn
    print("Yahoo statements slice %d of %d due" % (len(todo), len(pool)))
    new_a, new_q, info_rows, earn_rows = [], [], [], []
    if len(info):
        info_rows.extend(info.to_dict("records"))
    fails = 0
    streak = 0
    if done and not gaps:
        print("Yahoo statements skipping %d names already fetched today" % len(done))
    for i, t in enumerate(todo):
        lim.wait()
        try:
            inf, a_rows, q_rows, e_rows = india_data.fetch_yahoo_bundle(t, cfg)
            inf["fetched_on"] = today_et()
            inf["source"] = "Yahoo"
            info_rows.append(inf)
            if a_rows:
                new_a.append(pd.DataFrame(a_rows))
            if q_rows:
                new_q.append(pd.DataFrame(q_rows))
            earn_rows.extend(e_rows)
            done.add(t)
            streak = 0
        except Exception as exc:
            fails += 1
            streak += 1
            if i < 3:
                print("yahoo fail", t, str(exc)[:120])
            if streak >= 6:
                print("Yahoo stopped after %d failures in a row" % streak)
                break
        if (i + 1) % 10 == 0:
            print("Yahoo statements %d / %d" % (i + 1, len(todo)))
            annual, quarters = _flush_sec(annual, quarters, new_a, new_q, annual_p, quarter_p)
            if info_rows:
                pd.DataFrame(info_rows).drop_duplicates("ticker", keep="last").to_csv(info_p, index=False)
            progress_save(cache, "yahoo_statements", done)
        time.sleep(0.15)
    annual, quarters = _flush_sec(annual, quarters, new_a, new_q, annual_p, quarter_p)
    if info_rows:
        info = pd.DataFrame(info_rows).drop_duplicates("ticker", keep="last")
        info.to_csv(info_p, index=False)
    if earn_rows:
        earn_new = pd.DataFrame(earn_rows)
        if len(earn):
            got = set(earn_new["ticker"].astype(str))
            earn = pd.concat([earn[~earn["ticker"].astype(str).isin(got)], earn_new], ignore_index=True)
        else:
            earn = earn_new
        earn.to_csv(earn_p, index=False)
    progress_save(cache, "yahoo_statements", done)
    tried = max(len(todo), 1)
    if fails and (fails == len(todo) or fails / tried > 0.5 or streak >= 6):
        status = "CACHED" if len(annual) else "MISSING"
        log("Fundamentals (Yahoo statements)", status, "", "%d of %d failed; kept the saved copy" % (fails, len(todo)))
        log("Analyst and profile (Yahoo Finance)", "CACHED" if len(info) else "MISSING", "", "same pass as statements")
        log("Earnings dates (Yahoo Finance)", "CACHED" if len(earn) else "MISSING", "", "same pass as statements")
    else:
        STAMPS["yahoo_statements"] = today_et()
        STAMPS["yahoo_slow"] = today_et()
        n_names = int(annual["ticker"].nunique()) if len(annual) and "ticker" in annual.columns else 0
        note = "%d names" % n_names
        if fails:
            note += ", %d failed and kept prior rows" % fails
        log("Fundamentals (Yahoo statements)", "OK", today_et(), note)
        log("Analyst and profile (Yahoo Finance)", "OK" if len(info) else "MISSING", today_et(), "%d names" % len(info))
        log("Earnings dates (Yahoo Finance)", "OK" if len(earn) else "MISSING", today_et(), "%d rows" % len(earn))
    return annual, quarters, info, earn


def load_shareholding(tickers, focus, cfg, cache, mode):
    """NSE promoter summary for the universe. FII, DII, and PIT only for the focus list."""
    path = os.path.join(cache, "holders.csv")
    cached = read_csv(path)
    names = _stock_names(tickers)
    focus_set = set(_stock_names(focus))
    decision = _need_fetch("shareholding", path, mode)
    if decision != "fetch":
        have = len(cached) > 0
        note = _slow_note(mode, have) if have else "data not available for free"
        status = "OK" if have else "MISSING"
        log("Shareholding (NSE)", status, STAMPS.get("shareholding", "") if have else "", note)
        insider_ok = have and "insider_buys" in cached.columns and pd.to_numeric(cached["insider_buys"], errors="coerce").notna().any()
        log("Insiders (NSE PIT)", "OK" if insider_ok else ("CACHED" if have else "MISSING"), "",
            "reused cache" if insider_ok else ("data not available for free" if not have else "saved file has no PIT counts"))
        return cached

    done = progress_load(cache, "shareholding")
    by_t = {}
    if len(cached):
        for rec in cached.to_dict("records"):
            by_t[str(rec.get("ticker"))] = rec
    fails = 0
    streak = 0
    cap = int((cfg.get("rate_limit") or {}).get("shareholding_per_run") or 50)
    priority = ["ABBOTINDIA", "EMBASSY", "MCX"] + _stock_names(focus)

    def _needs_split(ticker):
        row = by_t.get(ticker) or {}
        fii = row.get("fii_pct")
        try:
            blank = fii is None or fii == "" or (isinstance(fii, float) and pd.isna(fii))
        except TypeError:
            blank = True
        return blank

    ordered = []
    for ticker in priority + names:
        if ticker in done or ticker not in names and ticker not in priority:
            continue
        if ticker not in ordered:
            ordered.append(ticker)
    missing_split = [t for t in ordered if _needs_split(t)]
    rest = [t for t in ordered if t not in missing_split]
    todo = (missing_split + rest)[:cap]
    if not todo:
        log("Shareholding (NSE)", "OK" if len(cached) else "MISSING", STAMPS.get("shareholding", ""),
            "slice already done today" if len(cached) else "no names to fetch")
        return cached
    for i, t in enumerate(todo):
        try:
            history = india_data.fetch_shareholding_master(t, cfg)
            split = {}
            if t in focus_set and history and history[-1].get("xbrl"):
                try:
                    split = india_data.fetch_xbrl_split(history[-1]["xbrl"], cfg)
                except Exception:
                    split = {}
            row = india_data.shareholding_row(t, history, split) or {"ticker": t}
            buys, sells = None, None
            if t in focus_set:
                try:
                    buys, sells = india_data.fetch_pit_counts(t, cfg)
                except Exception:
                    buys, sells = None, None
            if not history and buys is None and sells is None and not split:
                raise RuntimeError("empty shareholding")
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
            row["insider_buys"] = buys
            row["insider_sells"] = sells
            if row.get("ownership_pct") in (None, ""):
                row["ownership_pct"] = row.get("promoter_pct")
            by_t[t] = row
            done.add(t)
            streak = 0
        except Exception as exc:
            fails += 1
            streak += 1
            if i < 2:
                print("shareholding fail", t, str(exc)[:100])
            if streak >= 6:
                print("NSE shareholding stopped after %d failures in a row" % streak)
                break
        if (i + 1) % 15 == 0:
            pd.DataFrame(list(by_t.values())).to_csv(path, index=False)
            progress_save(cache, "shareholding", done)
            print("Shareholding %d / %d" % (i + 1, len(todo)))
        time.sleep(0.35)
    out = pd.DataFrame(list(by_t.values())) if by_t else pd.DataFrame()
    if len(out):
        out.to_csv(path, index=False)
    progress_save(cache, "shareholding", done)
    if todo and (streak >= 6 or fails == len(todo)):
        status = "CACHED" if len(out) else "MISSING"
        note = "%d failed; kept the saved copy. Blank cells are not verified." % fails
        log("Shareholding (NSE)", status, "", note)
        log("Insiders (NSE PIT)", status, "", note if len(out) else "data not available for free")
    else:
        STAMPS["shareholding"] = today_et()
        log("Shareholding (NSE)", "OK" if len(out) else "MISSING", today_et(), "%d names, %d failed" % (len(out), fails))
        have_ins = len(out) and "insider_buys" in out.columns and pd.to_numeric(out["insider_buys"], errors="coerce").notna().any()
        log("Insiders (NSE PIT)", "OK" if have_ins else "PARTIAL", today_et(),
            "counts for the focus list" if have_ins else "no PIT rows in this pass")
    return out


def _clean_news(frame):
    if frame is None or len(frame) == 0 or "headline" not in frame.columns:
        return frame
    out = frame.copy()
    out["headline"] = out["headline"].map(india_data.clean_headline)
    out = out[out["headline"].str.len() >= 24]
    if "publisher" in out.columns:
        out = out[out["headline"].str.lower() != out["publisher"].fillna("").str.lower()]
    return out.reset_index(drop=True)


def load_india_news(cfg, cache, mode):
    path = os.path.join(cache, "news.csv")
    cached = read_csv(path)
    decision = _need_fetch("news", path, mode, allow_morning=True)
    if decision != "fetch":
        have = len(cached) > 0
        if have:
            cached = _clean_news(cached)
        log("News headlines (RSS)", "OK" if have else "MISSING", STAMPS.get("news", "") if have else "",
            _slow_note(mode, have) if have else "no cache and this run does not fetch headlines")
        return cached
    try:
        rows = india_data.fetch_rss(cfg)
    except Exception as exc:
        rows = []
        print("rss", str(exc)[:80])
    if rows:
        cached = _clean_news(pd.DataFrame(rows))
        cached.to_csv(path, index=False)
        STAMPS["news"] = today_et()
        log("News headlines (RSS)", "OK", today_et(), "%d headlines" % len(cached))
        return cached
    if len(cached):
        log("News headlines (RSS)", "CACHED", "", "feeds failed; kept the saved headlines")
        return cached
    log("News headlines (RSS)", "MISSING", "", "no headlines")
    return cached


def load_option_mood(focus, cfg, cache, mode):
    wall_p = os.path.join(cache, "option_walls.csv")
    pcr_p = os.path.join(cache, "pcr.csv")
    walls, pcr = read_csv(wall_p), read_csv(pcr_p)
    decision = _need_fetch("option_walls", wall_p, mode)
    if decision != "fetch":
        log("Option walls (NSE)", "OK" if len(walls) else "MISSING", "",
            _slow_note(mode, len(walls) > 0) if len(walls) else "not available")
        log("Put/call (NSE open interest)", "OK" if len(pcr) else "MISSING", "",
            "reused cache" if len(pcr) else "not available")
        return walls, pcr
    symbols = [("NIFTY", "Indices"), ("BANKNIFTY", "Indices")]
    for t in _stock_names(focus):
        if t not in ("NIFTY", "BANKNIFTY"):
            symbols.append((t, "Equity"))
    symbols = symbols[:12]
    frames = []
    ratio = None
    fails = 0
    for sym, kind in symbols:
        try:
            rows, got = india_data.fetch_option_walls(sym, kind, cfg)
            if rows:
                frames.append(pd.DataFrame(rows))
            if sym == "NIFTY" and got is not None:
                ratio = got
        except Exception as exc:
            fails += 1
            print("option fail", sym, str(exc)[:80])
        time.sleep(0.4)
    if frames:
        walls = pd.concat(frames, ignore_index=True)
        walls.to_csv(wall_p, index=False)
    if ratio is not None:
        row = pd.DataFrame([{"date": today_et(), "name": "NIFTY PUT/CALL OPEN INTEREST", "value": ratio}])
        pcr = pd.concat([pcr, row], ignore_index=True) if len(pcr) else row
        pcr = pcr.drop_duplicates(["date", "name"], keep="last")
        pcr.to_csv(pcr_p, index=False)
    if frames:
        STAMPS["option_walls"] = today_et()
        log("Option walls (NSE)", "OK", today_et(), "%d rows. Open interest only. Not an option pick." % len(walls))
    elif len(walls):
        log("Option walls (NSE)", "CACHED", "", "not available this run; kept the saved copy")
    else:
        log("Option walls (NSE)", "MISSING", "", "not available")
    if len(pcr):
        if ratio is not None:
            STAMPS["pcr"] = today_et()
        log("Put/call (NSE open interest)", "OK", "", "Nifty put open interest divided by call open interest")
    else:
        log("Put/call (NSE open interest)", "MISSING", "", "not available")
    return walls, pcr


def load_fii(cfg, cache, mode):
    path = os.path.join(cache, "fii_dii.csv")
    cached = read_csv(path)
    decision = _need_fetch("fii_dii", path, mode, allow_morning=True)
    if decision != "fetch":
        log("FII and DII cash (NSE)", "OK" if len(cached) else "MISSING", "",
            _slow_note(mode, len(cached) > 0) if len(cached) else "not available")
        return cached
    import market_sources
    try:
        rows, extra = market_sources.fetch_fii_archives(cfg)
        fresh = pd.DataFrame(rows) if rows else pd.DataFrame()
        merged = market_sources.merge_flow_rows(cached, fresh)
        if len(merged):
            merged.to_csv(path, index=False)
            STAMPS["fii_dii"] = today_et()
            note = "%d days kept" % merged["date"].nunique()
            if extra:
                note += ". " + extra
            log("FII and DII cash (NSE)", "OK", today_et(), note)
            return merged
    except Exception as exc:
        if len(cached):
            log("FII and DII cash (NSE)", "CACHED", "", str(exc)[:140])
            return cached
        log("FII and DII cash (NSE)", "MISSING", "", str(exc)[:140])
        return cached
    if len(cached):
        log("FII and DII cash (NSE)", "CACHED", "", "empty reply; kept the saved copy")
        return cached
    log("FII and DII cash (NSE)", "MISSING", "", "not available")
    return cached


def _fred_last(series_id):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s" % series_id
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": india_data.BROWSER["User-Agent"]})
        if r.status_code != 200 or "date" not in r.text.lower():
            return None
        frame = pd.read_csv(io.StringIO(r.text))
        if frame.shape[1] < 2:
            return None
        vals = pd.to_numeric(frame.iloc[:, 1], errors="coerce").dropna()
        if not len(vals):
            return None
        return float(vals.iloc[-1])
    except Exception:
        return None


def load_india_macro(cfg, cache, mode):
    path = os.path.join(cache, "econ.csv")
    fred_p = os.path.join(cache, "fred.json")
    cached = read_csv(path)
    fred = {}
    if os.path.exists(fred_p):
        try:
            fred = json.load(open(fred_p))
        except Exception:
            fred = {}
    decision = _need_fetch("econ", path, mode)
    if decision != "fetch":
        log("Macro (World Bank and FRED)", "OK" if len(cached) else "MISSING", "",
            _slow_note(mode, len(cached) > 0) if len(cached) else "not available. No forecast in the free feed.")
        return cached, fred
    import market_sources
    rows, notes, book = market_sources.macro_chain(cfg)
    y10 = None
    for row in rows:
        if row.get("indicator") == "India 10-year yield" and row.get("actual") not in ("", None):
            try:
                y10 = float(row["actual"])
            except (TypeError, ValueError):
                y10 = None
    if y10 is not None:
        fred["DGS10"] = round(y10, 2)
    else:
        fred.pop("DGS10", None)
    for item in book.rows:
        if item["status"] != "OK":
            log("Macro (%s)" % item["source"], "MISSING", "", item["detail"])
    if rows:
        cached = pd.DataFrame(rows)
        cached.to_csv(path, index=False)
        json.dump(fred, open(fred_p, "w"))
        STAMPS["econ"] = today_et()
        note = "%d rows. Surprise stays blank when there is no forecast." % len(cached)
        if notes:
            note += " " + " ".join(notes)
        log("Macro (RBI, FRED, World Bank)", "OK", today_et(), note[:300])
        return cached, fred
    if len(cached):
        log("Macro (World Bank and FRED)", "CACHED", "", "feeds failed; kept the saved copy")
        return cached, fred
    log("Macro (World Bank and FRED)", "MISSING", "", "not available")
    return cached, fred


def build_mood(close, fii):
    """India VIX and cash flows only. A US VIX print does not fill this page."""
    vix = None
    as_of = ""
    if close is not None and "^INDIAVIX" in getattr(close, "columns", []):
        series = close["^INDIAVIX"].dropna()
        if len(series):
            vix = round(float(series.iloc[-1]), 2)
            stamp = series.index[-1]
            as_of = str(stamp.date()) if hasattr(stamp, "date") else str(stamp)[:10]
    fii_net = dii_net = None
    if fii is not None and len(fii) and "category" in fii.columns and "net_cr" in fii.columns:
        day = str(fii["date"].astype(str).iloc[-1]) if "date" in fii.columns else ""
        last = fii[fii["date"].astype(str) == day] if day else fii

        def _net(label):
            sub = last[last["category"].astype(str).str.contains(label, case=False, regex=False)]
            if not len(sub):
                return None
            return scoring._f(sub.iloc[-1].get("net_cr"))

        fii_net = _net("FII")
        if fii_net is None:
            fii_net = _net("FPI")
        dii_net = _net("DII")
        if day:
            as_of = day
    if vix is None and fii_net is None and dii_net is None:
        return None
    return {
        "as_of": as_of,
        "india_vix": "" if vix is None else vix,
        "vix_zone": india_data.vix_zone(vix) if vix is not None else "",
        "fii_net_cr": "" if fii_net is None else fii_net,
        "dii_net_cr": "" if dii_net is None else dii_net,
        "note": "India VIX is a fear gauge. FII and DII nets are cash-market flow in crore rupees. This is not a survey.",
    }


def _listing_frames(cfg, cache, mode, parts, switches):
    """NSE equity master, the leftover 'Other NSE' names, SME, and BSE-only names."""
    import market_sources
    frames = []
    master_path = os.path.join(cache, "equity_master.csv")
    master = read_csv(master_path) if os.path.exists(master_path) else pd.DataFrame()
    fetch_lists = mode == "full" or (mode == "retry" and not len(master))
    if fetch_lists:
        try:
            master, url = market_sources.fetch_nse_master(cfg)
            master.to_csv(master_path, index=False)
            log("Universe (NSE equity list)", "OK", len(master), "%d names from %s" % (len(master), url.split("/")[2]))
        except Exception as exc:
            if len(master):
                log("Universe (NSE equity list)", "CACHED", len(master), str(exc)[:140])
            else:
                log("Universe (NSE equity list)", "MISSING", "", str(exc)[:140])
    elif len(master):
        log("Universe (NSE equity list)", "OK", len(master), "reused cache")
    else:
        log("Universe (NSE equity list)", "MISSING", "", "no cache and this run does not refresh the list")
    tagged = set()
    for part in parts:
        if part is not None and len(part) and "ticker" in part.columns:
            tagged |= set(part["ticker"].astype(str).str.upper())
    if len(master):
        keep_series = set(market_sources.NSE_EQUITY)
        listed = master[master["series"].astype(str).str.upper().isin(keep_series)].copy()
        other = listed[~listed["ticker"].astype(str).str.upper().isin(tagged)].copy()
        if len(other):
            other = other.rename(columns={}) 
            other["sector"] = ""
            other["in_other_nse"] = "yes"
            other["nse_symbol"] = other["ticker"]
            frames.append(other)
            log("Universe (Other NSE)", "OK", len(other), "NSE shares that are not in the index lists above")
        # Carry ISIN onto index rows by merging later inside combine. Attach isin via a thin frame.
        isin_frame = listed[["ticker", "company", "isin"]].copy()
        isin_frame["sector"] = ""
        isin_frame["nse_symbol"] = isin_frame["ticker"]
        frames.append(isin_frame)
    if switches.get("sme", False):
        sme_path = os.path.join(cache, "sme.csv")
        sme = read_csv(sme_path) if os.path.exists(sme_path) else pd.DataFrame()
        if fetch_lists:
            try:
                sme, url = market_sources.fetch_sme_master(cfg)
                sme.to_csv(sme_path, index=False)
                log("Universe (SME)", "OK", len(sme), "%d names" % len(sme))
            except Exception as exc:
                log("Universe (SME)", "CACHED" if len(sme) else "MISSING", len(sme) if len(sme) else "", str(exc)[:120])
        if len(sme):
            sme = sme.copy()
            sme["sector"] = ""
            sme["in_sme"] = "yes"
            frames.append(sme)
    elif True:
        log("Universe (SME)", "OK", "", "switch is off")
    if switches.get("bse_only", True):
        bse_path = os.path.join(cache, "bse_only.csv")
        bse = read_csv(bse_path) if os.path.exists(bse_path) else pd.DataFrame()
        if fetch_lists:
            try:
                content = url = None
                bars = pd.DataFrame()
                today = pd.Timestamp.now(tz=IST).date()
                last_error = "no BSE file"
                for back in range(0, 8):
                    day = today - dt.timedelta(days=back)
                    try:
                        content, url = market_sources._first_bytes(market_sources.bse_bhav_urls(day), cfg)
                        bars = market_sources.parse_bse_bhav(content, sme=switches.get("sme", False))
                        if len(bars):
                            break
                        last_error = "BSE file had no equity rows"
                    except Exception as exc:
                        last_error = str(exc)[:80]
                        content = None
                if content is None or not len(bars):
                    raise RuntimeError(last_error)
                nse_isins = set(master["isin"].astype(str).str.upper()) if len(master) and "isin" in master.columns else set()
                nse_tickers = set(master["ticker"].astype(str).str.upper()) if len(master) else tagged
                bse = market_sources.bse_only_names(bars, nse_isins, nse_tickers)
                if len(bse):
                    bse.to_csv(bse_path, index=False)
                log("Universe (BSE only)", "OK" if len(bse) else "MISSING", len(bse),
                    "%d names whose ISIN is not on the NSE list" % len(bse))
                # Remember BSE symbols for dual-listed names.
                if len(master) and len(bars):
                    linked = market_sources.tag_bse_symbols(master, bars)
                    link_path = os.path.join(cache, "bse_link.csv")
                    linked.to_csv(link_path, index=False)
                    frames.append(linked.assign(sector=""))
            except Exception as exc:
                if len(bse):
                    log("Universe (BSE only)", "CACHED", len(bse), str(exc)[:140])
                else:
                    log("Universe (BSE only)", "MISSING", "", str(exc)[:140])
        else:
            log("Universe (BSE only)", "OK", len(bse), "reused cache")
            link_path = os.path.join(cache, "bse_link.csv")
            if os.path.exists(link_path):
                linked = read_csv(link_path)
                if len(linked):
                    frames.append(linked.assign(sector=""))
        if len(bse):
            frames.append(bse)
    else:
        log("Universe (BSE only)", "OK", "", "switch is off")
    return frames


def main(argv=None):
    global ROOT
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "full"
    # Light rebuild. Same as offline (no network), and it also skips the
    # backtest, the price candles, and the saved score history, so it is quick
    # and keeps the daily comparison for alerts. The backfill job runs it.
    light = "--rescore" in argv
    if "--offline" in argv or light:
        mode = "offline"
    elif "--morning" in argv or "--hourly" in argv:
        mode = "morning"
    elif "--retry" in argv:
        mode = "retry"
    elif "--full" in argv or "--close" in argv:
        mode = "full"
    ROOT = os.environ.get("DESK_ROOT") or os.path.dirname(os.path.abspath(__file__))
    LOG.clear()
    STAMPS.clear()
    cfg = load_cfg()
    if light and "--after-backfill" in argv and not rebuild_after_backfill_on(cfg):
        print("Rebuild after the backfill is off in config.json (fundamentals_backfill.rebuild_pages_after_run).")
        return {}
    data, cache, inp = paths()
    load_stamps(cache)
    features = cfg["features"]
    holds = holdings_table(cfg, inp)
    watch = watch_table(cfg, inp)
    hold_tickers = [str(t).upper() for t in holds["ticker"]] if len(holds) else []
    watch_tickers = [str(t).upper() for t in watch["ticker"]] if len(watch) else []

    switches = index_switches(cfg)
    picks = [str(t).upper().strip() for t in (cfg.get("my_picks") or []) if str(t).strip()]
    if features.get("universe", True):
        parts = [load_index(key, cfg, cache, mode) for key in (
            "nifty50", "next50", "midcap150", "smallcap250", "microcap250", "totalmarket")]
        parts.extend(_listing_frames(cfg, cache, mode, parts, switches))
        universe = combine_indexes(parts, hold_tickers, watch_tickers, switches, my_picks=picks)
    else:
        universe = combine_indexes([], hold_tickers, watch_tickers, switches)
        log("Universe feature", "OK", "", "feature off: scoring the holdings and watchlist only")
    etfs = [e["ticker"] for e in cfg.get("sector_etfs", [])]
    extras = etfs + ["^NSEI", "^NSEBANK", "^INDIAVIX", "INR=X"]
    if features.get("sensex", True):
        extras.append("^BSESN")
    tickers = list(dict.fromkeys(list(universe["ticker"]) + extras))
    long = load_prices(tickers, cfg, cache, mode, universe)
    close, high, low, vol = wide_from_long(long, "close"), wide_from_long(long, "high"), wide_from_long(long, "low"), wide_from_long(long, "volume")
    price_status = source_status("Prices (Yahoo Finance)")

    score_on = features.get("score_breakdown", True) or features.get("scorecard", True) or features.get("top_stocks", True)
    focus_seed = list(dict.fromkeys(hold_tickers + watch_tickers))
    if not score_on:
        annual, quarters = pd.DataFrame(), pd.DataFrame()
        info, earnings = pd.DataFrame(), pd.DataFrame()
        holders = pd.DataFrame()
    else:
        annual, quarters, info, earnings = load_statements(list(universe["ticker"]), cfg, cache, mode)
        holders = load_shareholding(list(universe["ticker"]), focus_seed, cfg, cache, mode)
    if len(annual) or len(quarters):
        annual, quarters = fund.adjust_pershare_for_splits(annual, quarters)
    # fill sector gaps from Yahoo
    if len(info) and len(universe):
        imap = info.set_index("ticker")
        for i, u in universe.iterrows():
            t = u["ticker"]
            if t in imap.index:
                row = imap.loc[t]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[-1]
                sector = gics_sector(u.get("sector")) or gics_sector(row.get("sector"))
                if sector:
                    universe.at[i, "sector"] = sector
                if not u.get("company") and row.get("company"):
                    universe.at[i, "company"] = row.get("company")
    if len(universe) and "sector" in universe.columns:
        universe["sector"] = universe["sector"].map(gics_sector)
        embassy = universe["ticker"].astype(str).str.upper().eq("EMBASSY")
        if embassy.any():
            universe.loc[embassy, "sector"] = "Real Estate"
            if "industry" not in universe.columns:
                universe["industry"] = ""
            universe.loc[embassy, "industry"] = "REIT"

    scores, prepared = build_scores(universe, close, high, low, vol, annual, quarters, info, holders, earnings, cfg) if len(close) else (pd.DataFrame(), {})
    scores = apply_feature_blanks(scores, features)
    fin_status = source_status("Fundamentals (Yahoo statements)")
    an_status = source_status("Analyst and profile (Yahoo Finance)")
    hold_status = source_status("Shareholding (NSE)")
    scores = attach_status(scores, price_status, fin_status, an_status, hold_status)
    if len(scores) and _column_blank(scores, "roe") and _column_blank(scores, "de"):
        for row in LOG:
            if "Yahoo statements" in row["source"] and row["status"] == "OK":
                row["status"] = "PARTIAL"
                row["note"] = (row["note"] + " " if row["note"] else "") + "roe and de are blank on every scored row."
    liquid_view = scores
    if len(scores):
        scores["in_holdings"] = np.where(scores["ticker"].isin(hold_tickers), "yes", "no")
        if len(universe):
            meta = universe.drop_duplicates("ticker").set_index("ticker")
            for col in ("exchange", "nse_symbol", "bse_symbol", "index_membership", "industry"):
                if col in meta.columns and (col not in scores.columns or col == "index_membership"):
                    scores[col] = scores["ticker"].map(meta[col])
        if len(holders):
            hold_map = holders.drop_duplicates("ticker").set_index("ticker")
            for col in ("fii_pct", "dii_pct", "fii_chg", "dii_chg", "promoter_pct"):
                if col in hold_map.columns:
                    scores[col] = scores["ticker"].map(hold_map[col])
        liq_cfg = cfg.get("liquidity") or {}
        minimum = float(liq_cfg.get("min_median_traded_value") or 10000000)
        window = int(liq_cfg.get("median_days") or 20)
        import market_sources
        liq = market_sources.liquidity_table(long, list(scores["ticker"]), window, minimum)
        if len(liq):
            scores = scores.merge(liq, on="ticker", how="left")
        if "liquid" not in scores.columns:
            scores["liquid"] = "yes"
        scores["liquid"] = scores["liquid"].fillna("no")
        if not liq_cfg.get("enabled", True):
            scores["liquid"] = "yes"
    scores = assign_ranks(scores)
    liquid_view = scores[scores["liquid"].astype(str).eq("yes")] if len(scores) and "liquid" in scores.columns else scores

    # focus list for heavy sentiment feeds
    focus = list(focus_seed)
    if len(scores):
        focus += list(scores["ticker"].head(25))
    focus = list(dict.fromkeys(focus))[:40]
    news = load_india_news(cfg, cache, mode) if features.get("headline_sentiment", True) or features.get("news_earnings_summaries", True) else pd.DataFrame()
    if features.get("option_walls", True) or features.get("put_call", True):
        walls, pcr = load_option_mood(focus, cfg, cache, mode)
    else:
        walls, pcr = pd.DataFrame(), pd.DataFrame()
    if not features.get("option_walls", True):
        walls = pd.DataFrame()
    if not features.get("put_call", True):
        pcr = pd.DataFrame()
    pcr_df = tables.put_call_table(pcr, cfg["scoring"]["fear_line"], cfg["scoring"]["greed_line"]) if len(pcr) else pd.DataFrame()
    want_flows = features.get("aaii_sentiment", True) or features.get("fii_dii_flows", True) or features.get("fii_dii_today_strip", True)
    fii = load_fii(cfg, cache, mode) if want_flows else pd.DataFrame()
    import market_sources
    flows = market_sources.flows_from_history(fii, close) if want_flows else pd.DataFrame()
    participants = pd.DataFrame()
    if features.get("fii_dii_derivatives", True) and mode in ("full", "retry"):
        try:
            participants, url = market_sources.fetch_participant_oi(cfg)
            log("FII derivatives (NSE participant OI)", "OK", participants["date"].iloc[0] if len(participants) else "",
                "%d rows from the participant file" % len(participants))
        except Exception as exc:
            cached_oi = read_csv(os.path.join(cache, "participant_oi.csv"))
            if len(cached_oi):
                participants = cached_oi
                log("FII derivatives (NSE participant OI)", "CACHED", "", str(exc)[:140])
            else:
                log("FII derivatives (NSE participant OI)", "MISSING", "", str(exc)[:140])
    elif features.get("fii_dii_derivatives", True):
        participants = read_csv(os.path.join(cache, "participant_oi.csv"))
        log("FII derivatives (NSE participant OI)", "OK" if len(participants) else "MISSING", "",
            "reused cache" if len(participants) else "not loaded on this run")
    if len(participants) and not light:
        participants.to_csv(os.path.join(cache, "participant_oi.csv"), index=False)
    econ, fred = load_india_macro(cfg, cache, mode) if features.get("macro_screener", True) else (pd.DataFrame(), {})

    # history and alerts
    hist_path = os.path.join(data, "score_history.csv")
    history = read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()
    prev_path = os.path.join(cache, "prev_scores.csv")
    prev = read_csv(prev_path) if os.path.exists(prev_path) else pd.DataFrame()
    alerts = pd.DataFrame(scoring.build_alerts(scores, prev, cfg["scoring"]["score_jump"], cfg["scoring"]["buy_at"], cfg["scoring"]["hold_at"])) if features.get("alerts", True) else pd.DataFrame()
    changes = pd.DataFrame()
    if features.get("alerts", True) and len(scores) and len(prev):
        p = prev.set_index("ticker")
        rows = []
        for _, r in scores.iterrows():
            if r["ticker"] not in p.index:
                continue
            old = p.loc[r["ticker"]]
            if isinstance(old, pd.DataFrame):
                old = old.iloc[-1]
            a, b = scoring._f(r.get("score")), scoring._f(old.get("score"))
            if a is None or b is None or a == b:
                continue
            rows.append({"ticker": r["ticker"], "company": r.get("company"), "price": r.get("price"), "day_pct": r.get("day_pct"),
                         "score": a, "score_prev": b, "score_change": a - b, "verdict": r.get("verdict")})
        changes = pd.DataFrame(rows)
        if len(changes):
            changes = changes.reindex(changes["score_change"].abs().sort_values(ascending=False).index)

    # backtest
    bt = {"summary": pd.DataFrame(), "buckets": pd.DataFrame(), "equity": pd.DataFrame(), "yearly": pd.DataFrame(), "notes": pd.DataFrame()}
    bt_path = os.path.join(data, "backtest_summary.csv")
    run_bt = features.get("backtest", True) and (mode in ("full", "offline") or "--backtest" in argv or not os.path.exists(bt_path))
    if light and os.path.exists(bt_path):
        run_bt = False
    if features.get("backtest", True) and run_bt and len(close):
        sector_etf = {}
        for _, u in universe.iterrows():
            sector_etf[u["ticker"]] = SECTOR_ETF_BY_NAME.get(u.get("sector") or "")
        q_by = {t: g for t, g in quarters.groupby("ticker")} if len(quarters) else {}
        bench = india_data.bench_column(close) or "SPY"
        bt = scoring.run_backtest(close, prepared, q_by, sector_etf, close, bench, cfg["scoring"]["flat_band_pct"])
        if len(bt["summary"]):
            log("Backtest", "OK", bt["summary"]["end"].iloc[-1] if "end" in bt["summary"] else "", "monthly point-in-time test")
        else:
            log("Backtest", "MISSING", "", "not enough history or too few stocks with filings")
    elif features.get("backtest", True) and os.path.exists(bt_path):
        bt = {k: read_csv(os.path.join(data, "backtest_%s.csv" % k)) for k in ("summary", "buckets", "equity", "yearly", "notes")}
        log("Backtest", "OK", "", "reused the last test (it rebuilds on the after-close run)")
    elif not features.get("backtest", True):
        log("Backtest", "OK", "", "feature off")

    # assemble pages
    breadth = tables.breadth_history(close) if features.get("breadth", True) else pd.DataFrame()
    screener, sector_macro = tables.macro_tables(econ, cfg.get("sector_etfs", []))
    sectors = tables.etf_sectors(close, scores, cfg.get("sector_etfs", []), sector_macro) if features.get("top_sectors", True) else pd.DataFrame()
    # if macro feed empty, blank the macro columns and say so
    if features.get("top_sectors", True) and (econ is None or len(econ) == 0) and len(sectors):
        sectors["note"] = sectors.get("note", "")
        sectors["macro_note"] = "Macro surprises are missing, so those columns are blank."
    xratio = tables.xly_xlp_table(close) if features.get("xly_xlp", True) else pd.DataFrame()
    updated = india_data.now_stamp()
    asof = ""
    bench_asof = india_data.bench_column(close) if len(close) else None
    if bench_asof and close[bench_asof].notna().any():
        asof = str(pd.Timestamp(close[bench_asof].dropna().index.max()).date())
    elif len(close):
        asof = str(close.dropna(how="all").index.max().date())
    market = tables.market_row(close, breadth, pcr_df, fred, xratio, updated, asof, len(scores), scores)
    if len(market):
        market["listed_n"] = int(len(universe))
        market["liquid_n"] = int((scores["liquid"].astype(str) == "yes").sum()) if len(scores) and "liquid" in scores.columns else 0
        snap = setups.market_snapshot(close, cfg)
        for key in (
            "nifty_trend", "sensex_trend", "bank_trend", "market_ok", "market_rule",
            "spy_uptrend", "sensex_uptrend", "qqq_uptrend",
        ):
            if key in ("spy_uptrend", "sensex_uptrend", "qqq_uptrend"):
                continue
            market[key] = snap.get(key, "")
    earn_pages, _hist = tables.earnings_pages(scores, earnings, close, hold_tickers) if len(scores) else ({}, pd.DataFrame())
    scan_scores = liquid_view if len(liquid_view) else scores
    g, q, d, w = tables.scanners(scan_scores, cfg["scoring"]) if len(scan_scores) else (pd.DataFrame(),) * 4
    br, tr, pb, gl, heat = tables.technical_pages(scores) if len(scores) else (pd.DataFrame(),) * 5
    port, port_sum = build_portfolio(holds, scores, history) if features.get("watchlist_portfolio", True) else (pd.DataFrame(), pd.DataFrame())
    watch_out = build_watch(watch, scores) if features.get("watchlist_portfolio", True) else pd.DataFrame()
    prices = price_file(close, scores) if features.get("scorecard", True) else pd.DataFrame()
    if light:
        log("Price candles", "OK", asof, "Light rebuild. Prices did not change, so the saved candle files were kept.")
    elif len(scores) and long is not None and len(long):
        candle_names = list(scores["ticker"])
        if "^NSEI" in set(long["ticker"].astype(str)):
            candle_names.append("^NSEI")
        if "^BSESN" in set(long["ticker"].astype(str)):
            candle_names.append("^BSESN")
        candle_frame = candle_file(long, candle_names)
        n_candles = write_candle_groups(candle_frame, os.path.join(data, "ohlc"))
        span = int(candle_frame.groupby("ticker").size().max()) if len(candle_frame) else 0
        n_names = int(candle_frame["ticker"].nunique()) if len(candle_frame) else 0
        note = "%d tickers in letter files, %d groups rewritten, up to %d sessions." % (n_names, n_candles, span)
        if "open" not in long.columns or not pd.to_numeric(long["open"], errors="coerce").notna().any():
            note += " Open is blank until the next full price download."
        log("Price candles", "OK", asof, note)
    news_out = news_rows(news, scores) if len(scores) else pd.DataFrame()
    headlines = news_out[news_out["kind"] == "headline"] if len(news_out) and "kind" in news_out.columns else pd.DataFrame()
    details = tables.score_details(scores) if len(scores) else pd.DataFrame()
    fins = tables.financials_long(scores) if len(scores) else pd.DataFrame()
    company = tables.company_rows(annual, close) if features.get("company_financials", True) else pd.DataFrame()
    hpe = tables.historical_pe(close, prepared) if features.get("historical_pe", True) else pd.DataFrame()
    if len(hpe):
        hpe["note"] = "Median trailing P/E of the stocks on this desk. There is no free official Nifty 50 P/E series, so that line is not drawn."
    fresh = tables.freshness_table(scores) if features.get("freshness_flags", True) else pd.DataFrame()
    inst_rows = []
    if len(holders):
        pts = scores.set_index("ticker")["pts_institutional"] if len(scores) and "pts_institutional" in scores.columns else pd.Series(dtype=float)
        for _, r in holders.iterrows():
            fii_pct = r.get("fii_pct")
            promoter = r.get("promoter_pct")
            fii_blank = fii_pct is None or fii_pct == "" or (isinstance(fii_pct, float) and pd.isna(fii_pct))
            prom_blank = promoter is None or promoter == "" or (isinstance(promoter, float) and pd.isna(promoter))
            note = ""
            if fii_blank and not prom_blank:
                note = "Foreign and domestic institutions are not verified for this name. Promoter percent is from the NSE summary."
            elif fii_blank and prom_blank:
                note = "Shareholding split is not verified."
            inst_rows.append({
                "ticker": r.get("ticker"), "row_type": "summary", "owner": "",
                "promoter_pct": r.get("promoter_pct"), "fii_pct": r.get("fii_pct"),
                "dii_pct": r.get("dii_pct"), "public_pct": r.get("public_pct"),
                "promoter_chg": r.get("promoter_chg"), "fii_chg": r.get("fii_chg"),
                "dii_chg": r.get("dii_chg"), "public_chg": r.get("public_chg"),
                "as_of": r.get("as_of"),
                "pts_institutional": pts.get(r.get("ticker"), "") if len(pts) else "",
                "note": note,
            })
    inst = pd.DataFrame(inst_rows)
    setup_universe = universe
    if len(universe) and len(scores) and "liquid" in scores.columns and (cfg.get("liquidity") or {}).get("enabled", True):
        allowed = set(scores.loc[scores["liquid"].astype(str).eq("yes"), "ticker"].astype(str))
        setup_universe = universe[universe["ticker"].astype(str).isin(allowed)]
    if len(close) and len(setup_universe):
        opn = wide_from_long(long, "open") if long is not None and len(long) and "open" in long.columns else None
        setup_frames = setups.build_setups(close, high, low, vol, setup_universe, quarters, annual, holders, features, scores=scores, cfg=cfg, opn=opn)
    else:
        setup_frames = {k: pd.DataFrame() for k in (
            "scanner_vcp", "scanner_canslim", "scanner_box", "scanner_flag", "scanner_leaders",
            "scanner_qullamaggie", "scanner_marios", "scanner_52w", "highs_lows_history",
        )}
    def _n(frame):
        if frame is None or len(frame) == 0 or "ticker" not in getattr(frame, "columns", []):
            return 0
        return int((frame["ticker"].astype(str) != "").sum())
    log("Pattern scanners", "OK", asof, "VCP %d, CANSLIM %d, box %d, flag %d, Qullamaggie %d, Marios %d, leaders %d, 52-week %d. No new downloads." % (
        _n(setup_frames.get("scanner_vcp")), _n(setup_frames.get("scanner_canslim")),
        _n(setup_frames.get("scanner_box")), _n(setup_frames.get("scanner_flag")),
        _n(setup_frames.get("scanner_qullamaggie")), _n(setup_frames.get("scanner_marios")),
        _n(setup_frames.get("scanner_leaders")), _n(setup_frames.get("scanner_52w")),
    ))
    buy_on = features.get("buy_setups", True)
    if buy_on and len(close):
        buy = setups.build_buy_setups(
            setup_frames.get("scanner_vcp"), setup_frames.get("scanner_box"),
            setup_frames.get("scanner_flag"), setup_frames.get("scanner_canslim"),
            scores, close, setup_frames.get("scanner_52w"), cfg=cfg,
            qullamaggie=setup_frames.get("scanner_qullamaggie"), marios=setup_frames.get("scanner_marios"),
        )
    else:
        buy = pd.DataFrame()
    buy_listed = setups.buy_rows_listed(buy) if _n(buy) else buy
    log("Buy setups", "OK" if _n(buy) else "MISSING", asof,
        "%d chart setups, %d with a BUY or Not scored yet label. The market check passes when the Nifty 50 or SENSEX is in an uptrend. This desk never places trades." % (_n(buy), _n(buy_listed)))
    rot_scores = scores
    if len(scores) and (cfg.get("liquidity") or {}).get("enabled", True) and "liquid" in scores.columns:
        rot_scores = scores[scores["liquid"].astype(str).str.lower().eq("yes")]
    if features.get("sector_rotation", True) and len(close):
        rot_cfg = dict(cfg.get("sector_rotation") or {})
        choices = [str(rot_cfg.get("benchmark") or "^NSEI")]
        if features.get("sensex", True) and "^BSESN" in close.columns and "^BSESN" not in choices:
            choices.append("^BSESN")
        if "^NSEI" not in choices and "^NSEI" in close.columns:
            choices.insert(0, "^NSEI")
        pieces = []
        logs_rot = []
        for bench_code in choices:
            one_cfg = dict(rot_cfg)
            one_cfg["benchmark"] = bench_code
            one = sector_rotation.build(
                close, high, rot_scores, cfg.get("sector_etfs"),
                scanners=setup_frames,
                buy_setups=buy_listed if _n(buy_listed) else None,
                fred=sector_rotation.read_fred_cache(cache),
                cfg=one_cfg,
            )
            pieces.append(one)
            if one.get("log"):
                logs_rot.append(one["log"])
        rot = {
            "sector_rotation": pd.concat([p["sector_rotation"] for p in pieces if len(p.get("sector_rotation", []))], ignore_index=True) if any(len(p.get("sector_rotation", [])) for p in pieces) else pd.DataFrame(),
            "sector_rotation_tails": pd.concat([p["sector_rotation_tails"] for p in pieces if len(p.get("sector_rotation_tails", []))], ignore_index=True) if any(len(p.get("sector_rotation_tails", [])) for p in pieces) else pd.DataFrame(),
            "sector_rotation_history": pd.concat([p["sector_rotation_history"] for p in pieces if len(p.get("sector_rotation_history", []))], ignore_index=True) if any(len(p.get("sector_rotation_history", [])) for p in pieces) else pd.DataFrame(),
            "log": " ".join(logs_rot),
        }
    else:
        rot = {
            "sector_rotation": pd.DataFrame(),
            "sector_rotation_tails": pd.DataFrame(),
            "sector_rotation_history": pd.DataFrame(),
            "log": "Sector rotation is off." if not features.get("sector_rotation", True) else "No prices for sector indexes.",
        }
    log("Sector rotation", "OK" if len(rot.get("sector_rotation", [])) else "MISSING", asof, rot.get("log") or "")
    backfill_on = features.get("fundamentals_backfill", True)
    progress = fundamentals_backfill.progress_frame(ROOT) if backfill_on else pd.DataFrame()
    if backfill_on and len(progress):
        log("Financials backfill", "OK", progress.iloc[0].get("last_batch_at") or "", str(progress.iloc[0].get("note") or ""))
    elif backfill_on:
        log("Financials backfill", "MISSING", "", "No progress file yet. This run does not call the backfill sources.")

    insider = pd.DataFrame()
    if len(holders) and "ticker" in holders.columns:
        insider = pd.DataFrame({
            "ticker": holders["ticker"],
            "buys_3m": holders["insider_buys"] if "insider_buys" in holders.columns else "",
            "sells_3m": holders["insider_sells"] if "insider_sells" in holders.columns else "",
        })
    if len(insider) and len(scores):
        insider["pts_insider"] = insider["ticker"].map(scores.set_index("ticker")["pts_insider"])

    # walls note. nearest expiry is computed from the expiry column already on file.
    if len(walls):
        walls = tables.mark_nearest_expiry(walls)
        walls["note"] = "Open interest only, for the focus list, once a day. Not an option pick."

    # High volume scanner. Uses the bars already in memory. Its own try so a
    # problem here can never stop the rest of the update.
    hv_on = features.get("high_volume_scanner", True)
    hv = pd.DataFrame()
    hv_note = "High volume scanner is off."
    if hv_on:
        try:
            import volume_scanner
            hv, hv_note = volume_scanner.build(long, scores, universe, cfg)
            log("High volume scanner", "OK" if len(hv) else "MISSING", asof, hv_note)
        except Exception as exc:
            hv = pd.DataFrame()
            hv_note = "The high volume scan did not run this time. The rest of the desk updated as normal."
            log("High volume scanner", "MISSING", asof, (hv_note + " " + str(exc))[:200])

    aaii_note = "There is no free AAII survey for India. India VIX and FII or DII cash were not available, so this page has no number."
    mood = build_mood(close, fii) if features.get("aaii_sentiment", True) else None

    files = {
        "scores": gated(scores, "scores", features.get("top_stocks", True) or features.get("scorecard", True), "No scores."),
        "score_details": gated(details, "score_details", features.get("scorecard", True), "No score breakdown."),
        "market_today": gated(market, "market_today", True, "No market snapshot."),
        "sectors": gated(sectors, "sectors", features.get("top_sectors", True), "No Nifty sector indexes."),
        "breadth_history": gated(breadth, "breadth_history", features.get("breadth", True), "No breadth history."),
        "alerts": gated(alerts, "alerts", features.get("alerts", True), "No changes versus the last run."),
        "score_changes": gated(changes, "score_changes", features.get("alerts", True), "No score changes versus the last run."),
        "portfolio": gated(port, "portfolio", features.get("watchlist_portfolio", True), "No holdings."),
        "portfolio_summary": gated(port_sum, "portfolio_summary", features.get("watchlist_portfolio", True), "No holdings."),
        "watchlist": gated(watch_out, "watchlist", features.get("watchlist_portfolio", True), "Watchlist is empty."),
        "prices": gated(prices, "prices", features.get("scorecard", True), "No prices."),
        "news": gated(news_out, "news", features.get("news_earnings_summaries", True), "No headlines."),
        "scanner_growth": gated(g, "scanner_growth", features.get("scanner_growth", True), "Growth screen off or empty."),
        "scanner_quality": gated(q, "scanner_quality", features.get("scanner_quality", True), "Quality screen off or empty."),
        "scanner_dividend": gated(d, "scanner_dividend", features.get("scanner_dividend", True), "Dividend screen off or empty."),
        "scanner_wheel": gated(w, "scanner_wheel", features.get("scanner_wheel", True), "Liquid stock screen off or empty."),
        "scanner_vcp": gated(setup_frames["scanner_vcp"], "scanner_vcp", features.get("scanner_vcp", True), "No VCP setups. The scan used cached prices only."),
        "scanner_canslim": gated(setup_frames["scanner_canslim"], "scanner_canslim", features.get("scanner_canslim", True), "No CANSLIM setups. Missing letters stay not verified. No new downloads."),
        "scanner_box": gated(setup_frames["scanner_box"], "scanner_box", features.get("scanner_box", True), "No box setups in the cached prices."),
        "scanner_flag": gated(setup_frames["scanner_flag"], "scanner_flag", features.get("scanner_flag", True), "No flag setups in the cached prices."),
        "scanner_qullamaggie": gated(setup_frames.get("scanner_qullamaggie"), "scanner_qullamaggie", features.get("scanner_qullamaggie", True), "No Qullamaggie setups in the cached prices."),
        "scanner_marios": gated(setup_frames.get("scanner_marios"), "scanner_marios", features.get("scanner_marios", True), "No Marios setups in the cached prices."),
        "scanner_leaders": gated(setup_frames.get("scanner_leaders"), "scanner_leaders", features.get("scanner_leaders", True), "No leaders. A leader is a ready or just-broken VCP, a strict CANSLIM qualify, or both."),
        "scanner_52w": gated(setup_frames.get("scanner_52w"), "scanner_52w", features.get("scanner_52w", True), "No 52-week rows. The scan used cached prices only."),
        "highs_lows_history": gated(setup_frames.get("highs_lows_history"), "highs_lows_history", features.get("scanner_52w", True), "No 52-week history in the cached prices."),
        "buy_setups": gated(buy, "buy_setups", buy_on, "No buy setups. The list is built from the scanners already on the desk. This desk never places trades."),
        "sector_rotation": gated(rot.get("sector_rotation"), "sector_rotation", features.get("sector_rotation", True), "No sector rotation. The Nifty 50 or the sector indexes were missing from the price cache."),
        "sector_rotation_tails": gated(rot.get("sector_rotation_tails"), "sector_rotation_tails", features.get("sector_rotation", True), "No relative-rotation tails."),
        "sector_rotation_history": gated(rot.get("sector_rotation_history"), "sector_rotation_history", features.get("sector_rotation", True), "No relative-rotation history."),
        "earnings_calendar": gated(earn_pages.get("calendar"), "earnings_calendar", features.get("earnings_calendar", True), "No earnings dates."),
        "earnings_heatmap": gated(earn_pages.get("heatmap"), "earnings_heatmap", features.get("earnings_heatmap", True), "No earnings history. Revenue vs estimate is not in the free feed."),
        "earnings_cards": gated(earn_pages.get("cards"), "earnings_cards", features.get("earnings_cards", True), "No earnings history to grade."),
        "earnings_history": gated(earn_pages.get("history"), "earnings_history", features.get("earnings_tracker", True), "No earnings history."),
        "put_call": gated(pcr_df, "put_call", features.get("put_call", True), "Nifty put/call open interest was not available."),
        "option_walls": gated(walls, "option_walls", features.get("option_walls", True), "Option chains were not available. They refresh once a day for Nifty, Bank Nifty, and the focus list."),
        "analyst_ratings": gated(scores, "analyst_ratings", features.get("analyst_ratings", True), "No analyst data."),
        "institutional_13f": gated(inst, "institutional_13f", features.get("institutional_13f", True), "No shareholding summary. FII and DII stay blank until the filing split is on file."),
        "aaii_sentiment": gated(pd.DataFrame([mood]) if mood else pd.DataFrame(), "aaii_sentiment", features.get("aaii_sentiment", True), aaii_note) if features.get("aaii_sentiment", True) else pd.DataFrame(columns=tables.COLS["aaii_sentiment"]),
        "fii_flows": gated(flows, "fii_flows", features.get("fii_dii_flows", True) or features.get("fii_dii_today_strip", True), "FII and DII cash history was not available."),
        "participant_oi": gated(participants, "participant_oi", features.get("fii_dii_derivatives", True), "NSE participant open interest was not available."),
        "insider_trading": gated(insider, "insider_trading", features.get("insider_trading", True), "Insider counts are not available for free."),
        "headline_sentiment": gated(headlines, "headline_sentiment", features.get("headline_sentiment", True), "No headlines for the focus list."),
        "xly_xlp": gated(xratio, "xly_xlp", features.get("xly_xlp", True), "Nifty Auto or Nifty FMCG price was missing."),
        "financials_summary": gated(fins, "financials_summary", features.get("financials_summary", True), "No financials."),
        "earnings_tracker": gated(earn_pages.get("history"), "earnings_tracker", features.get("earnings_tracker", True), "No earnings tracker."),
        "company_financials": gated(company, "company_financials", features.get("company_financials", True), "No company filings."),
        "dividend_scanner": gated(scores, "dividend_scanner", features.get("dividend_scanner", True), "No dividend rows."),
        "macro_screener": gated(screener, "macro_screener", features.get("macro_screener", True), "No India macro rows. The free feed has no forecast, so surprise stays blank."),
        "sector_macro": gated(sector_macro, "sector_macro", features.get("macro_screener", True), "No sector macro scores because the surprise feed is missing."),
        "historical_pe": gated(hpe, "historical_pe", features.get("historical_pe", True), "Not enough statements to build a median trailing P/E. Official Nifty 50 P/E is MISSING."),
        "breakouts": gated(br, "breakouts", features.get("breakouts", True), "No names near a 52-week high."),
        "trends": gated(tr, "trends", features.get("trends", True), "No trend rows."),
        "pullbacks": gated(pb, "pullbacks", features.get("pullbacks", True), "No pullback rows."),
        "gainers_losers": gated(gl, "gainers_losers", features.get("gainers_losers", True), "No gainers."),
        "high_volume": gated(hv, "high_volume", hv_on, hv_note),
        "sector_performance": gated(tables.sector_perf(scores), "sector_performance", features.get("sector_performance", True), "No sector performance."),
        "heatmaps": gated(heat, "heatmaps", features.get("heatmaps", True), "No heatmap."),
        "freshness": gated(fresh, "freshness", features.get("freshness_flags", True), "Freshness flags are off."),
        "updates_log": pd.DataFrame(LOG),
        "backfill_progress": gated(progress, "backfill_progress", backfill_on, "The financials backfill has not written a progress row yet."),
        "help": pd.DataFrame(tables.help_rows(), columns=["topic", "plain_english"]),
        "settings": tables.settings_rows(cfg),
        "universe": gated(universe, "universe", True, "Universe is empty."),
        "backtest_summary": gated(bt.get("summary"), "backtest_summary", features.get("backtest", True), "Not enough point-in-time history to run the test."),
        "backtest_buckets": gated(bt.get("buckets"), "backtest_buckets", features.get("backtest", True), "No buckets."),
        "backtest_equity": gated(bt.get("equity"), "backtest_equity", features.get("backtest", True), "No equity curve."),
        "backtest_yearly": gated(bt.get("yearly"), "backtest_yearly", features.get("backtest", True), "No yearly rows."),
        "backtest_notes": gated(bt.get("notes"), "backtest_notes", features.get("backtest", True), "No notes."),
    }
    # Mood stays MISSING only when neither India VIX nor FII/DII cash is on file.
    if features.get("aaii_sentiment", True) and mood is None:
        files["aaii_sentiment"] = tables.ensure(pd.DataFrame(), tables.COLS["aaii_sentiment"], "MISSING", aaii_note)

    # alerts: if the builder returned nothing, say so plainly instead of looking broken
    if features.get("alerts", True) and (files["alerts"] is None or len(files["alerts"]) == 0 or (len(files["alerts"]) == 1 and files["alerts"].iloc[0].get("data_status") == "MISSING")):
        note = "No prior run to compare yet. Verdict changes show up on the next run." if not len(prev) else "No verdict changes or score crossings this run."
        files["alerts"] = tables.ensure(pd.DataFrame([{"ticker": "", "kind": "info", "text": note}]), tables.COLS["alerts"], "OK", note)

    partial_pages = []
    for name, df in files.items():
        if df is None or "data_status" not in getattr(df, "columns", []):
            continue
        if (df["data_status"].astype(str) == "PARTIAL").any():
            partial_pages.append(name)
    if partial_pages:
        log("Column check", "PARTIAL", "", "A column is blank on every row: " + ", ".join(partial_pages) + ". Blank is missing, not zero.")
    else:
        log("Column check", "OK", "", "No measured column is blank on every row.")
    files["updates_log"] = pd.DataFrame(LOG)

    for name, df in files.items():
        write_out(df if df is not None else pd.DataFrame(), name, data)

    # persist score history and previous snapshot for the next run.
    # The light rebuild keeps them, so alerts still compare with the last daily run.
    if light:
        log("Light rebuild", "OK", "", "Rescored from the financials and shareholding already on disk. No downloads.")
    if len(scores) and not light:
        today = pd.Timestamp.now(tz=IST).strftime("%Y-%m-%d")
        snap = scores[["ticker", "score", "verdict", "price", "timing", "stop", "insider_buys_3m"]].copy()
        snap["date"] = today
        hist = pd.concat([history, snap[["date", "ticker", "score"]]], ignore_index=True) if len(history) else snap[["date", "ticker", "score"]]
        hist = hist.drop_duplicates(["date", "ticker"], keep="last")
        hist.to_csv(hist_path, index=False)
        snap.to_csv(prev_path, index=False)
    if not light:
        save_stamps(cache)
    meta = {
        "updated_pt": updated,
        "price_as_of": asof,
        "mode": "rescore" if light else mode,
        "label": DISCLAIMER,
        "n_stocks": int(len(scores)),
        "tabs": sorted(files),
    }
    with open(os.path.join(data, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    # rewrite updates log now that backtest and the rest have logged
    write_out(pd.DataFrame(LOG), "updates_log", data)
    print("wrote %d files to %s" % (len(files), data))
    return files


if __name__ == "__main__":
    main()
