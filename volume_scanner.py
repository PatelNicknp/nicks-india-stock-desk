"""High volume scanner. Uses only the daily bars the desk already saves. No new downloads.

A stock is listed when the latest session's volume is well above its own
50-day average volume. The file keeps every stock at 1.5x or more so the page
can offer 1.5x, 2x, 3x, and 5x. The default view on the page is 2x.
"""
import numpy as np
import pandas as pd

MIN_RATIO_KEPT = 1.5      # lowest choice on the page
DEFAULT_RATIO = 2.0       # default choice on the page
MIN_PRICE = 20.0          # rupees
MIN_TRADED = 1e7          # Rs 1 crore = 10,000,000 rupees
AVG_DAYS = 50
LONG_DAYS = 200
DESC_KEYS = ("description", "company_description", "one_liner", "about", "summary_line", "business")
DELIVERY_KEYS = ("delivery_pct", "deliv_pct", "deliv_per", "delivery_per", "pct_deliverable")


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def session_date(long):
    """Latest date with a full market's worth of stock rows. A stray currency bar on a weekend does not count."""
    if long is None or not len(long) or "date" not in long.columns:
        return ""
    stocks = long[~long["ticker"].astype(str).str.startswith("^") & ~long["ticker"].astype(str).str.contains("=")]
    if not len(stocks):
        return ""
    counts = stocks.groupby("date").size().sort_index()
    if not len(counts):
        return ""
    floor = max(1, int(counts.tail(30).median() * 0.5))
    good = counts[counts >= floor]
    return str(good.index.max()) if len(good) else str(counts.index.max())


def _pick(frame, keys):
    if frame is None or not len(frame):
        return None
    for k in keys:
        if k in frame.columns and frame[k].astype(str).str.strip().replace({"nan": "", "None": ""}).ne("").any():
            return k
    return None


def _exchange_word(v):
    s = str(v or "").strip().upper()
    if s in ("BOTH", "NSE/BSE", "NSE+BSE"):
        return "Both"
    if s.startswith("NSE"):
        return "NSE"
    if s.startswith("BSE"):
        return "BSE"
    return ""


def build(long, scores=None, universe=None, cfg=None):
    """Return one row per stock at 1.5x volume or more that also passes the price and traded value floors."""
    if long is None or not len(long):
        return pd.DataFrame(), "No daily bars in the price cache."
    need = {"date", "ticker", "close", "volume"}
    if not need.issubset(set(long.columns)):
        return pd.DataFrame(), "The price cache has no volume column."
    day = session_date(long)
    if not day:
        return pd.DataFrame(), "No market session in the price cache."
    deliv_key = _pick(long, DELIVERY_KEYS)
    cols = ["date", "ticker", "close", "volume"] + ([deliv_key] if deliv_key else [])
    df = long[cols].copy()
    df["ticker"] = df["ticker"].astype(str)
    df = df[~df["ticker"].str.startswith("^") & ~df["ticker"].str.contains("=")]
    df["date"] = df["date"].astype(str)
    df = df[df["date"] <= day]
    df["close"] = _num(df["close"])
    df["volume"] = _num(df["volume"])
    df = df.dropna(subset=["close"]).drop_duplicates(["ticker", "date"], keep="last")
    # Only stocks that traded in the latest session.
    today_names = set(df.loc[df["date"] == day, "ticker"])
    df = df[df["ticker"].isin(today_names)]
    # Stocks only. ETFs and fund units (ISIN starting INF) are left out, and so is
    # anything that is not on the desk's stock list.
    funds = set()
    if "isin" in long.columns:
        isin = long.loc[long["date"].astype(str) == day, ["ticker", "isin"]]
        funds |= set(isin.loc[isin["isin"].astype(str).str.upper().str.startswith("INF"), "ticker"].astype(str))
    known = set()
    for src in (scores, universe):
        if src is None or not len(src) or "ticker" not in src.columns:
            continue
        known |= set(src["ticker"].astype(str))
        if "isin" in src.columns:
            funds |= set(src.loc[src["isin"].astype(str).str.upper().str.startswith("INF"), "ticker"].astype(str))
    if known:
        df = df[df["ticker"].isin(known)]
    df = df[~df["ticker"].isin(funds)].sort_values(["ticker", "date"])
    df = df.groupby("ticker", sort=False).tail(LONG_DAYS)
    g = df.groupby("ticker", sort=False)
    n_bars = g["close"].transform("size")
    pos = g.cumcount()
    last = df[pos == n_bars - 1].set_index("ticker")
    prev = df[pos == n_bars - 2].set_index("ticker")
    prior = df[(pos >= n_bars - 1 - AVG_DAYS) & (pos < n_bars - 1)]
    avg_vol = prior.groupby("ticker")["volume"].mean()
    n_prior = prior.groupby("ticker")["volume"].count()
    sma50 = df[pos >= n_bars - AVG_DAYS].groupby("ticker")["close"].mean()
    n50 = df[pos >= n_bars - AVG_DAYS].groupby("ticker")["close"].count()
    # Indian stocks are capped at a 20% move a day. A bigger one-day jump in the
    # last 50 sessions is most likely a split or bonus, which also bends volume.
    jump = (g["close"].pct_change().abs() > 0.35) & (pos >= n_bars - 1 - AVG_DAYS)
    split_seen = jump.groupby(df["ticker"]).any()
    sma200 = g["close"].mean()
    n200 = g["close"].count()

    out = pd.DataFrame({
        "ticker": last.index,
        "date": day,
        "close": last["close"].values,
        "volume": last["volume"].values,
    }).set_index("ticker")
    out["prev_close"] = prev["close"].reindex(out.index)
    out["avg_volume_50d"] = avg_vol.reindex(out.index)
    out["n_prior"] = n_prior.reindex(out.index).fillna(0)
    out["sma50"] = sma50.reindex(out.index).where(n50.reindex(out.index) >= AVG_DAYS)
    out["sma200"] = sma200.reindex(out.index).where(n200.reindex(out.index) >= LONG_DAYS)
    out["split_check"] = np.where(split_seen.reindex(out.index).fillna(False).astype(bool), "yes", "")
    if deliv_key:
        out["delivery_pct"] = _num(last[deliv_key]).reindex(out.index)
    # Need a full 50 sessions of history so the average means something.
    out = out[(out["n_prior"] >= AVG_DAYS) & (out["avg_volume_50d"] > 0) & (out["volume"] > 0)]
    out["volume_ratio"] = out["volume"] / out["avg_volume_50d"]
    out["traded_value"] = out["close"] * out["volume"]
    out["traded_cr"] = out["traded_value"] / 1e7
    out["day_pct"] = (out["close"] / out["prev_close"] - 1.0) * 100.0
    out = out[(out["volume_ratio"] >= MIN_RATIO_KEPT) & (out["close"] > MIN_PRICE) & (out["traded_value"] >= MIN_TRADED)]
    if not len(out):
        return pd.DataFrame(), "No stock traded at 1.5 times its 50-day average volume in the %s session." % day

    def above(a, b):
        return np.where(b.isna(), "", np.where(a > b, "yes", "no"))

    out["above_sma50"] = above(out["close"], out["sma50"])
    out["above_sma200"] = above(out["close"], out["sma200"])
    out["day_type"] = np.where(out["day_pct"].isna(), "", np.where(out["day_pct"] > 0, "Up", np.where(out["day_pct"] < 0, "Down", "Flat")))
    out["meaning"] = np.where(out["day_type"] == "Up", "Buying", np.where(out["day_type"] == "Down", "Selling", ""))
    out = out.reset_index()

    # Names, exchange, and the one-line description when the desk already has them.
    info = pd.DataFrame({"ticker": out["ticker"]})
    for src in (scores, universe):
        if src is None or not len(src) or "ticker" not in src.columns:
            continue
        s = src.drop_duplicates("ticker").set_index(src.drop_duplicates("ticker")["ticker"].astype(str))
        for col in ("company", "sector", "exchange"):
            if col in s.columns:
                vals = info["ticker"].map(s[col])
                info[col] = info[col].where(info[col].astype(str).str.strip().ne("") & info[col].notna(), vals) if col in info.columns else vals
        dk = _pick(s, DESC_KEYS)
        if dk:
            vals = info["ticker"].map(s[dk])
            info["description"] = info["description"].where(info["description"].notna(), vals) if "description" in info.columns else vals
    for col in ("company", "sector", "exchange", "description"):
        out[col] = info[col].values if col in info.columns else ""
    out["exchange"] = out["exchange"].map(_exchange_word)
    out["passes_default"] = np.where(out["volume_ratio"] >= DEFAULT_RATIO, "yes", "no")
    out = out.sort_values("volume_ratio", ascending=False).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    n_default = int((out["passes_default"] == "yes").sum())
    note = ("Session %s. %d stocks at 2x or more of their 50-day average volume, %d at 1.5x or more. "
            "Close over Rs 20 and at least Rs 1 crore traded. Built from the saved daily bars. No new download."
            % (day, n_default, len(out)))
    if not deliv_key:
        note += " Delivery % is not in the saved bars, so that column stays blank."
    out["note"] = note
    return out, note
