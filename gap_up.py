"""Gap Up scanner. Uses only the daily bars the desk already saves. No new downloads.

Nick's rules (numbers live in the gap_up block of config.json):
1. True gap: the gap day's open is above the day before's high, by at least 3%
   (min_gap_filter and min_gap_pct). Gap % = open / previous high - 1.
2. Volume: gap-day volume is at least 1.5 times the average of the 50 days before it.
3. Quality: gap-day close at least Rs 20, and an average traded value (close times
   volume) of at least Rs 1 crore a day over the last 50 sessions. Rs 1 crore is the
   same rupee line the Episodic Pivot scan uses (the desk's liquidity block).
4. Holding: no daily close below the gap-day low from the gap day through today.
   A close equal to the low still holds.
5. Window: the gap day is one of the last 21 trading days, today included. When a
   stock has several gaps, the most recent one that still holds is shown.
Rows are sorted newest gap first, then by gap %.
"""
import numpy as np
import pandas as pd

# Same key names and order as the US desk's gap_up block. India adds the rupee floor
# (min_traded_value_cr), Nick's 3% minimum switch (min_gap_filter), skip_etfs_and_funds, and hold_level.
GAP_DEFAULTS = {
    "lookback_days": 21,
    "true_gap_only": True,
    "min_gap_filter": True,
    "min_gap_pct": 3.0,
    "volume_filter": True,
    "vol_mult": 1.5,
    "vol_avg_days": 50,
    "price_floor": True,
    "min_price": 20.0,
    "liquidity_floor": True,
    "liquidity_days": 50,
    "min_traded_value_cr": 1.0,
    "hold_rule": True,
    "skip_stale": True,
    "sma_fast": 50,
    "sma_slow": 200,
    "show_other_scanners": True,
    "skip_etfs_and_funds": True,
    "hold_level": "gap_day_low",
}
GAP_TODAY = "GAP UP today"
GAP_HOLDING = "GAP HOLDING"
GAP_BROKE = "BROKE HOLD"
LISTED = (GAP_TODAY, GAP_HOLDING)
HOLD_LEVELS = ("gap_day_low", "gap_day_close", "prev_high")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Other scanners named in the "Also on" column. Same rule as the Chart Viewer:
# any status except CLOSED counts. High volume counts the rows its page lists by default.
ALSO_IN = [
    ("scanner_vcp", "VCP"), ("scanner_canslim", "CANSLIM"), ("scanner_box", "Box"),
    ("scanner_flag", "Flag"), ("scanner_qullamaggie", "Qullamaggie"), ("scanner_marios", "Marios"),
    ("scanner_episodic_pivot", "EP"), ("scanner_leaders", "Leaders"),
    ("high_volume", "High volume"), ("buy_setups", "Buy setups"),
]


def gap_cfg(cfg):
    out = dict(GAP_DEFAULTS)
    for k, v in ((cfg or {}).get("gap_up") or {}).items():
        if not str(k).startswith("_"):
            out[k] = v
    if str(out.get("hold_level")) not in HOLD_LEVELS:
        out["hold_level"] = "gap_day_low"
    return out


def short_date(iso):
    try:
        d = pd.Timestamp(iso)
    except Exception:
        return str(iso or "")
    return "%s %d" % (MONTHS[d.month - 1], d.day)


def fund_tickers(*frames):
    """ETFs and fund units: ISIN starting INF."""
    funds = set()
    for src in frames:
        if src is None or not len(src) or "isin" not in getattr(src, "columns", []) or "ticker" not in src.columns:
            continue
        pairs = src[["ticker", "isin"]].dropna().drop_duplicates()
        funds |= set(pairs.loc[pairs["isin"].astype(str).str.upper().str.startswith("INF"), "ticker"].astype(str))
    return funds


def pick_universe(universe, long=None, cfg=None):
    """The names to scan: the desk's stock list, without ETFs and funds unless the switch says otherwise.
    The rupee traded-value floor is checked per stock in build()."""
    p = gap_cfg(cfg)
    names = universe
    if names is None or not len(names):
        return names
    if p["skip_etfs_and_funds"]:
        funds = fund_tickers(long, names, universe)
        names = names[~names["ticker"].astype(str).isin(funds)]
    return names


def _calendar(close):
    """Trading days of the market: dates where at least half the stocks have a close."""
    if close is None or not len(close):
        return pd.DatetimeIndex([])
    cols = [c for c in close.columns if not str(c).startswith("^") and "=" not in str(c)]
    sub = close[cols] if cols else close
    counts = sub.notna().sum(axis=1)
    if not len(counts) or counts.max() == 0:
        return pd.DatetimeIndex([])
    floor = max(1, int(counts.tail(30).median() * 0.5))
    return pd.DatetimeIndex(counts[counts >= floor].index).sort_values()


def _col(frame, ticker):
    if frame is None or ticker not in getattr(frame, "columns", []):
        return None
    return frame[ticker]


def scan_one(o, h, l, c, v, window_start, p):
    """Find the most recent gap that passes every rule. Arrays are the stock's own bars, oldest first.
    window_start: first bar index allowed as a gap day. Returns a dict or None."""
    n = len(c)
    avg_days = int(p["vol_avg_days"])
    min_ratio = float(p["vol_mult"])
    min_price = float(p["min_price"])
    # min_gap_pct is a whole percent (3.0 means 3%). With min_gap_filter off, any true gap counts.
    min_gap = float(p.get("min_gap_pct") or 0.0) / 100.0 if p["min_gap_filter"] else 0.0
    t = n - 1
    first = max(int(window_start), avg_days, 1)
    for i in range(t, first - 1, -1):
        oi, hi, li, ci, vi = o[i], h[i], l[i], c[i], v[i]
        if not (np.isfinite(oi) and np.isfinite(ci) and np.isfinite(li) and np.isfinite(hi)):
            continue
        ref = h[i - 1] if p["true_gap_only"] else c[i - 1]
        if not np.isfinite(ref) or ref <= 0:
            continue
        # Rule 1: the open is above yesterday's high (above yesterday's close when the switch is off).
        if not oi > ref:
            continue
        gap = oi / ref - 1.0
        if gap < min_gap - 1e-9:
            continue
        # Rule 2: volume at least 1.5 times the average of the 50 days before the gap day.
        prior = v[i - avg_days:i]
        prior = prior[np.isfinite(prior)]
        avg = float(prior.mean()) if len(prior) >= avg_days else np.nan
        ratio = vi / avg if np.isfinite(vi) and np.isfinite(avg) and avg > 0 else np.nan
        if p["volume_filter"] and not (np.isfinite(ratio) and ratio >= min_ratio):
            continue
        # Rule 3: gap-day close at least Rs 20.
        if p["price_floor"] and not ci >= min_price:
            continue
        level = {"gap_day_low": li, "gap_day_close": ci, "prev_high": h[i - 1]}[p["hold_level"]]
        after = c[i:t + 1]
        after = after[np.isfinite(after)]
        broke = bool(len(after) and (after < level).any())
        # Rule 4: no close below the hold level from the gap day through today.
        if broke and p["hold_rule"]:
            continue
        rng = hi - li
        pos = 100.0 if rng <= 0 else (ci - li) / rng * 100.0
        return {
            "i": i, "gap_pct": gap * 100.0, "prev_high": float(h[i - 1]), "prev_close": float(c[i - 1]),
            "gap_open": float(oi), "gap_high": float(hi), "gap_low": float(li), "gap_close": float(ci),
            "volume": float(vi), "avg_volume_50": avg, "volume_ratio": float(ratio),
            "hold_level": float(level), "holding": not broke, "close_pos_pct": float(pos),
        }
    return None


def build(close, high, low, vol, opn, universe, cfg=None, scores=None):
    """Return (rows, note). One row per stock with a gap that passes every rule."""
    p = gap_cfg(cfg)
    if opn is None or not len(getattr(opn, "columns", [])):
        return pd.DataFrame(), "The saved bars have no open price yet, so gaps cannot be checked."
    if close is None or not len(close):
        return pd.DataFrame(), "No daily bars in the price cache."
    cal = _calendar(close)
    if not len(cal):
        return pd.DataFrame(), "No market session in the price cache."
    today = cal[-1]
    look = max(1, int(p["lookback_days"]))
    window = cal[-look:]
    window_first = window[0]
    names = list(universe["ticker"].astype(str)) if universe is not None and len(universe) else []
    meta = {}
    for src in (universe, scores):
        if src is None or not len(src) or "ticker" not in src.columns:
            continue
        for rec in src.drop_duplicates("ticker").to_dict("records"):
            m = meta.setdefault(str(rec["ticker"]), {})
            for col in ("company", "sector", "index_membership"):
                val = rec.get(col)
                if col not in m or m[col] in ("", None) or (isinstance(m[col], float) and np.isnan(m[col])):
                    m[col] = val
    fast, slow = int(p["sma_fast"]), int(p["sma_slow"])
    rows = []
    for ticker in names:
        cs = _col(close, ticker)
        if cs is None:
            continue
        frame = pd.DataFrame({
            "open": _col(opn, ticker), "high": _col(high, ticker), "low": _col(low, ticker),
            "close": cs, "volume": _col(vol, ticker),
        }).loc[:today].dropna(subset=["close", "high", "low"])
        if len(frame) < int(p["vol_avg_days"]) + 1:
            continue
        # skip_stale: the stock must have traded on the latest market day, so the hold rule runs through today.
        if p["skip_stale"] and pd.Timestamp(frame.index[-1]) != pd.Timestamp(today):
            continue
        idx = pd.DatetimeIndex(frame.index)
        start = int(idx.searchsorted(window_first))
        a = {k: pd.to_numeric(frame[k], errors="coerce").to_numpy(dtype=float) for k in frame.columns}
        # Rupee floor: average close times volume over the last liquidity_days sessions.
        tv_n = int(p["liquidity_days"])
        tv = (a["close"] * a["volume"])[-tv_n:]
        tv = tv[np.isfinite(tv)]
        traded_cr = float(tv.mean()) / 1e7 if len(tv) else np.nan
        if p["liquidity_floor"] and not (len(tv) >= tv_n and traded_cr >= float(p["min_traded_value_cr"])):
            continue
        hit = scan_one(a["open"], a["high"], a["low"], a["close"], a["volume"], start, p)
        if hit is None:
            continue
        i = hit["i"]
        gap_day = pd.Timestamp(idx[i])
        last = float(a["close"][-1])
        closes = a["close"]
        sma_f = float(np.nanmean(closes[-fast:])) if np.isfinite(closes[-fast:]).sum() >= fast else np.nan
        sma_s = float(np.nanmean(closes[-slow:])) if np.isfinite(closes[-slow:]).sum() >= slow else np.nan
        m = meta.get(ticker, {})
        days_ago = int(len(window) - 1 - window.get_loc(gap_day)) if gap_day in window else int(len(idx) - 1 - i)
        if not hit["holding"]:
            status = GAP_BROKE
        else:
            status = GAP_TODAY if days_ago == 0 else GAP_HOLDING
        rows.append({
            "ticker": ticker, "company": m.get("company", ""), "sector": m.get("sector", ""),
            "index_membership": m.get("index_membership", ""),
            "status": status, "avg_traded_cr": traded_cr,
            "gap_date": gap_day.strftime("%Y-%m-%d"), "days_ago": days_ago,
            "gap_pct": hit["gap_pct"], "prev_high": hit["prev_high"], "prev_close": hit["prev_close"],
            "gap_open": hit["gap_open"], "gap_high": hit["gap_high"], "gap_low": hit["gap_low"],
            "gap_close": hit["gap_close"], "volume": hit["volume"], "avg_volume_50": hit["avg_volume_50"],
            "volume_ratio": hit["volume_ratio"], "hold_level": hit["hold_level"],
            "price": last, "price_as_of": pd.Timestamp(today).strftime("%Y-%m-%d"),
            "above_hold_pct": (last / hit["hold_level"] - 1.0) * 100.0 if hit["hold_level"] > 0 else np.nan,
            "close_pos_pct": hit["close_pos_pct"],
            "sma50": sma_f, "sma200": sma_s,
            "above_sma50": "" if not np.isfinite(sma_f) else ("yes" if last > sma_f else "no"),
            "above_sma200": "" if not np.isfinite(sma_s) else ("yes" if last > sma_s else "no"),
        })
    out = pd.DataFrame(rows)
    day_s = pd.Timestamp(today).strftime("%Y-%m-%d")
    if not len(out):
        return out, ("No stock gapped above the day before's high on %sx volume and held it in the last %d sessions (to %s)."
                     % (_x(p["vol_mult"]), look, day_s))
    out["reason"] = out.apply(lambda r: reason_text(r, p), axis=1)
    out = out.sort_values(["gap_date", "gap_pct"], ascending=[False, False]).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    note = ("Session %s. %d stocks gapped above the day before's high on %sx or more of their 50-day volume in the last %d sessions "
            "and have held the gap-day low. Gap Up does not feed Buy setups. Built from the saved daily bars. No new download." % (day_s, len(out), _x(p["vol_mult"]), look))
    out["note"] = note
    return out, note


def _x(v):
    f = float(v)
    return ("%d" % f) if f == int(f) else ("%g" % f)


def reason_text(r, p=None):
    word = "holding" if r.get("status") in LISTED else "broke the hold level"
    return "Gap Up %.1f%% on %s, %s. Volume %.1fx the 50-day average. Last close %.1f%% above the gap-day low." % (
        float(r["gap_pct"]), short_date(r["gap_date"]), word, float(r["volume_ratio"]), float(r["above_hold_pct"]))


def _listed(frame, name):
    """Tickers a scanner lists, by the Chart Viewer's rule."""
    if frame is None or not len(frame) or "ticker" not in getattr(frame, "columns", []):
        return set()
    f = frame[frame["ticker"].astype(str).str.strip().ne("") & frame["ticker"].notna()]
    if name == "high_volume":
        if "passes_default" in f.columns:
            f = f[f["passes_default"].astype(str).str.lower().eq("yes")]
    elif name == "buy_setups":
        if "listed" in f.columns:
            f = f[f["listed"].astype(str).str.lower().eq("yes")]
    elif "status" in f.columns:
        s = f["status"].astype(str).str.strip()
        f = f[s.ne("") & s.ne("nan") & s.ne("CLOSED")]
    return set(f["ticker"].astype(str).str.upper())


def add_also_in(rows, frames, cfg=None):
    """Fill the also_in column with the other scanners that list the same stock."""
    if rows is None or not len(rows):
        return rows
    p = gap_cfg(cfg)
    out = rows.copy()
    if not p["show_other_scanners"]:
        out["also_in"] = ""
        return out
    sets = [(label, _listed((frames or {}).get(name), name)) for name, label in ALSO_IN]
    out["also_in"] = [", ".join(label for label, s in sets if str(t).upper() in s) for t in out["ticker"]]
    return out
