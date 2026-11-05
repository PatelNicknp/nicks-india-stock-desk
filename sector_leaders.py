"""Strong sectors and the three stocks in each with the highest RS rank.

The sector order comes from the sector rotation score versus the Nifty 50 when
that table is on file. A sector counts as strong when its weekly box is Leading.
If none is Leading, the highest scores are shown and the note says so.

Indexes that share one stock group (Bank, PSU Bank, and Financial Services are
all Financials) are listed once, under the strongest index.

When the rotation table is missing, sectors are ranked by the middle RS of
their stocks. A middle RS of 70 or more is strong. If none reaches 70, the
highest ones are shown and the note says so.

Stocks with a blank RS are left out. Liquid names come first. A quieter name
is used only when the group has fewer than three liquid stocks with an RS.
"""

import numpy as np
import pandas as pd

TOP_STOCKS = 3
LEADER_RS = 70
FILL_WHEN_NONE = 4
MIN_FOR_MEDIAN = 3

COLUMNS = [
    "ticker", "company", "sector_name", "sector_group", "sector_rank",
    "strength", "strength_source", "quadrant", "index_name", "stock_rank",
    "rs", "price", "off_high_pct", "setup", "blurb",
    "data_status", "note",
]

BLURB_LEADING = "Ranked by the sector index versus the Nifty 50. Only Leading sectors are shown."
BLURB_TOP = "No sector index is Leading. These are the highest scores versus the Nifty 50."
BLURB_MEDIAN = "Sector indexes are not on file. Sectors are ranked by the middle RS of their stocks. Only groups at 70 or higher are shown."
BLURB_MEDIAN_TOP = "Sector indexes are not on file. No group has a middle RS of 70 or higher. These are the strongest by that middle RS."


def build(scores, ratings, rotation=None, buy=None, scanners=None, sector_etfs=None):
    """One row per leader stock. Empty when there is no RS rank to sort by."""
    stocks = _stock_frame(scores, ratings)
    if stocks is None or len(stocks) == 0 or not pd.to_numeric(stocks["rs"], errors="coerce").notna().any():
        return pd.DataFrame(columns=COLUMNS)
    tags = _setup_tags(buy, scanners)
    rot = _nifty_rotation(rotation)
    if rot is not None and len(rot):
        groups, kind = _from_rotation(rot)
        source = "sector index"
    else:
        groups, kind = _from_median(stocks)
        source = "median RS"
    blurb = {
        "leading": BLURB_LEADING,
        "top": BLURB_TOP,
        "median": BLURB_MEDIAN,
        "median_top": BLURB_MEDIAN_TOP,
    }.get(kind, BLURB_LEADING)
    rows = []
    for rank, group in enumerate(groups, start=1):
        members = stocks[stocks["sector"].astype(str) == str(group["group"])]
        picked = _pick(members, TOP_STOCKS)
        for i, (_, stock) in enumerate(picked.iterrows(), start=1):
            ticker = str(stock["ticker"])
            rows.append({
                "ticker": ticker,
                "company": stock.get("company") or "",
                "sector_name": group["title"],
                "sector_group": group["group"],
                "sector_rank": rank,
                "strength": _round(group["strength"], 2),
                "strength_source": source,
                "quadrant": group.get("quadrant") or "",
                "index_name": group.get("index_name") or "",
                "stock_rank": i,
                "rs": int(stock["rs_num"]),
                "price": _round(stock.get("price"), 2),
                "off_high_pct": _off_high(stock.get("dist_52w_high_pct")),
                "setup": tags.get(ticker.upper()) or "No setup",
                "blurb": blurb,
                "data_status": "OK",
                "note": blurb,
            })
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(rows, columns=COLUMNS)


def _stock_frame(scores, ratings):
    if scores is None or len(scores) == 0 or "ticker" not in getattr(scores, "columns", []):
        return pd.DataFrame()
    if ratings is None or len(ratings) == 0 or "ticker" not in getattr(ratings, "columns", []):
        return pd.DataFrame()
    base = scores.copy()
    base["ticker"] = base["ticker"].astype(str)
    rate = ratings.drop_duplicates("ticker", keep="last").copy()
    rate["ticker"] = rate["ticker"].astype(str)
    keep = [c for c in ("ticker", "rs") if c in rate.columns]
    out = base.merge(rate[keep], on="ticker", how="left", suffixes=("", "_rank"))
    if "rs_rank" in out.columns and "rs" not in out.columns:
        out["rs"] = out["rs_rank"]
    if "rs" not in out.columns:
        return pd.DataFrame()
    if "sector" not in out.columns:
        out["sector"] = ""
    if "company" not in out.columns:
        out["company"] = ""
    return out


def _nifty_rotation(rotation):
    if rotation is None or len(getattr(rotation, "index", [])) == 0:
        return None
    if "benchmark" not in rotation.columns:
        return rotation
    bench = rotation["benchmark"].astype(str)
    nifty = rotation[bench.str.contains("NSEI")]
    if len(nifty):
        return nifty
    return rotation[~bench.str.contains("BSESN")]


def _from_rotation(rot):
    groups = {}
    for _, row in rot.iterrows():
        group = str(row.get("sector") or "").strip()
        if not group:
            continue
        item = {
            "name": str(row.get("name") or group),
            "score": _num(row.get("score")),
            "quadrant": str(row.get("quadrant_w") or ""),
        }
        bucket = groups.setdefault(group, [])
        bucket.append(item)
    leading = []
    ranked = []
    for group, items in groups.items():
        best = max(items, key=lambda item: item["score"] if item["score"] is not None else -1e18)
        lead = [item for item in items if item["quadrant"] == "Leading"]
        lead_best = max(lead, key=lambda item: item["score"] if item["score"] is not None else -1e18) if lead else None
        chosen = lead_best or best
        title = chosen["name"] if len(items) == 1 else group
        rec = {
            "group": group,
            "title": title,
            "strength": chosen["score"],
            "quadrant": "Leading" if lead else (chosen["quadrant"] or ""),
            "index_name": chosen["name"] if title != chosen["name"] else "",
        }
        ranked.append(rec)
        if lead:
            leading.append(rec)
    ranked.sort(key=lambda rec: (-(rec["strength"] if rec["strength"] is not None else -1e18), rec["title"]))
    leading.sort(key=lambda rec: (-(rec["strength"] if rec["strength"] is not None else -1e18), rec["title"]))
    if leading:
        return leading, "leading"
    return ranked[:FILL_WHEN_NONE], "top"


def _from_median(stocks):
    rows = []
    for group, frame in stocks.groupby(stocks["sector"].astype(str)):
        name = str(group).strip()
        if not name or name.lower() == "nan":
            continue
        values = pd.to_numeric(frame["rs"], errors="coerce").dropna()
        if len(values) < MIN_FOR_MEDIAN:
            continue
        rows.append({
            "group": name,
            "title": name,
            "strength": float(values.median()),
            "quadrant": "",
            "index_name": "",
        })
    rows.sort(key=lambda rec: (-rec["strength"], rec["title"]))
    strong = [rec for rec in rows if rec["strength"] >= LEADER_RS]
    if strong:
        return strong, "median"
    return rows[:FILL_WHEN_NONE], "median_top"


def _pick(frame, n):
    if frame is None or len(frame) == 0:
        return frame.iloc[0:0] if frame is not None else pd.DataFrame()
    out = frame.copy()
    out["rs_num"] = pd.to_numeric(out["rs"], errors="coerce")
    out = out[out["rs_num"].notna()]
    if len(out) == 0:
        return out
    if "liquid" in out.columns:
        out["_liq"] = out["liquid"].astype(str).str.lower().eq("yes").astype(int)
    else:
        out["_liq"] = 1
    out["_ticker"] = out["ticker"].astype(str)
    out = out.sort_values(["_liq", "rs_num", "_ticker"], ascending=[False, False, True])
    return out.head(n)


def _setup_tags(buy, scanners):
    tags = {}
    for label, frame in list(scanners or []):
        if frame is None or len(frame) == 0 or "ticker" not in getattr(frame, "columns", []):
            continue
        for _, row in frame.iterrows():
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker or ticker in tags:
                continue
            status = _status_words(row.get("status"))
            tags[ticker] = (label + ", " + status) if status else label
    if buy is not None and len(buy) and "ticker" in buy.columns:
        for _, row in buy.iterrows():
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            sources = " ".join(str(row.get("setup_sources") or "").replace("+", " and ").split())
            status = _status_words(row.get("best_status"))
            if sources and status:
                text = sources + ", " + status
            else:
                text = sources or status
            if text:
                tags[ticker] = text
    return tags


def _status_words(status):
    text = str(status or "").strip()
    low = text.lower()
    if not low or low == "nan":
        return ""
    if low == "ready":
        return "ready"
    if "broken out" in low:
        return "broke out today"
    if low == "watching":
        return "watching"
    if "in trade" in low:
        return "in a trade"
    if low == "ep today":
        return "EP today"
    return text


def _off_high(value):
    number = _num(value)
    if number is None:
        return ""
    if number >= 0:
        return 0.0
    return round(abs(number), 1)


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _round(value, places):
    number = _num(value)
    if number is None:
        return ""
    return round(number, places)
