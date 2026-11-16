"""IBD-style EPS Rating, 1 to 99, for every India stock on the desk.

Each stock gets a raw growth score from its saved financials:
- Quarterly part: the average of the last two quarters' EPS change versus the
  same quarter a year earlier (one quarter when only one can be computed).
- Annual part: the yearly EPS growth rate over the last three years (compound),
  or over two years or one year when less history is on file.
When both parts exist they count equally. When one is missing the other is used
alone. Each growth number is capped at -100% and +500% so one tiny base does not
swamp the race. The raw scores are then ranked against every stock with a score:
EPS 85 means its earnings growth beat about 85% of India stocks. No score is
given (blank, no chip) when neither part can be computed. Fund units are left out.
Downloads nothing; it reads the quarterly and annual files already saved.
"""
import numpy as np
import pandas as pd

CAP_LOW, CAP_HIGH = -100.0, 500.0
COLS = ["ticker", "eps_rating", "eps_raw", "eps_q_growth", "eps_a_growth", "eps_a_years", "eps_note"]


def _frame_key(frame):
    text = str(frame)
    if len(text) == 6 and text.startswith("CY") and text[2:].isdigit():
        return int(text[2:]) * 10
    if len(text) == 8 and text.startswith("CY") and text[6] == "Q" and text[2:6].isdigit() and text[7] in "1234":
        return int(text[2:6]) * 10 + int(text[7])
    return None


def _growth(now, old):
    if now is None or old is None or not np.isfinite(now) or not np.isfinite(old) or old == 0:
        return None
    return (now - old) / abs(old) * 100.0


def _clip(x):
    return None if x is None else float(min(CAP_HIGH, max(CAP_LOW, x)))


def _series(sub, quarterly):
    if sub is None or len(sub) == 0 or "eps" not in sub.columns or "frame" not in sub.columns:
        return {}
    out = {}
    for frame, eps in zip(sub["frame"].astype(str), pd.to_numeric(sub["eps"], errors="coerce")):
        if ("Q" in frame) != quarterly:
            continue
        k = _frame_key(frame)
        if k is None or eps is None or not np.isfinite(eps):
            continue
        out[k] = float(eps)
    return out


def quarterly_growth(sub):
    """Average EPS change versus a year ago for the last two quarters on file."""
    q = _series(sub, True)
    if not q:
        return None, 0
    keys = sorted(q)
    vals = []
    for k in keys[-2:][::-1]:
        g = _growth(q[k], q.get(k - 10))
        if g is not None:
            vals.append(_clip(g))
    if not vals:
        return None, 0
    return float(np.mean(vals)), len(vals)


def annual_growth(sub, years=3):
    """Yearly EPS growth rate over up to `years` years (compound when both ends are positive)."""
    a = _series(sub, False)
    if not a:
        return None, 0
    latest = max(a)
    for n in range(int(years), 0, -1):
        old_k = latest - 10 * n
        if old_k not in a:
            continue
        now, old = a[latest], a[old_k]
        if old == 0:
            continue
        if now > 0 and old > 0:
            g = ((now / old) ** (1.0 / n) - 1.0) * 100.0
        else:
            g = _growth(now, old) / n
        return _clip(g), n
    return None, 0


def raw_score(q_growth, a_growth):
    parts = [x for x in (q_growth, a_growth) if x is not None]
    if not parts:
        return None
    return float(np.mean(parts))


def percentile_ratings(raw):
    """Map raw scores to 1..99 by rank among the stocks that have one."""
    s = pd.Series(raw, dtype=float).dropna()
    if len(s) == 0:
        return {}
    if len(s) == 1:
        return {s.index[0]: 99}
    pct = s.rank(method="average", pct=True)
    # Lowest lands near 1, highest at 99.
    scaled = ((pct - pct.min()) / (pct.max() - pct.min()) * 98.0 + 1.0).round().astype(int)
    return scaled.clip(1, 99).to_dict()


def build(quarters, annual, tickers, skip=None):
    skip = {str(t).upper() for t in (skip or [])}
    tickers = [str(t).strip().upper() for t in tickers if str(t).strip() and not str(t).startswith("^")]
    tickers = [t for t in dict.fromkeys(tickers) if t not in skip]

    def groups(df):
        if df is None or len(df) == 0 or "ticker" not in df.columns:
            return {}
        d = df.copy()
        d["ticker"] = d["ticker"].astype(str).str.strip().str.upper()
        return dict(tuple(d.groupby("ticker")))

    qg, ag = groups(quarters), groups(annual)
    rows, raw = [], {}
    for t in tickers:
        qv, qn = quarterly_growth(qg.get(t))
        av, an = annual_growth(ag.get(t))
        r = raw_score(qv, av)
        if r is not None:
            raw[t] = r
        rows.append({"ticker": t, "eps_raw": r, "eps_q_growth": qv, "eps_a_growth": av, "eps_a_years": an or None, "_qn": qn})
    ranks = percentile_ratings(raw)
    out = []
    for row in rows:
        t = row["ticker"]
        rating = ranks.get(t)
        note = ""
        if rating is not None:
            bits = []
            if row["eps_q_growth"] is not None:
                bits.append("last %s EPS %+.0f%% vs a year ago" % ("2 quarters'" if row["_qn"] == 2 else "quarter's", row["eps_q_growth"]))
            if row["eps_a_growth"] is not None:
                yrs = row["eps_a_years"]
                bits.append("yearly EPS %+.0f%% a year over %d year%s" % (row["eps_a_growth"], yrs, "" if yrs == 1 else "s"))
            note = "EPS Rating %d: earnings growth beat about %d%% of India stocks (%s)." % (rating, rating, "; ".join(bits))
        out.append({
            "ticker": t,
            "eps_rating": rating,
            "eps_raw": None if row["eps_raw"] is None else round(row["eps_raw"], 2),
            "eps_q_growth": None if row["eps_q_growth"] is None else round(row["eps_q_growth"], 1),
            "eps_a_growth": None if row["eps_a_growth"] is None else round(row["eps_a_growth"], 1),
            "eps_a_years": row["eps_a_years"],
            "eps_note": note,
        })
    df = pd.DataFrame(out, columns=COLS)
    if len(df):
        df["eps_rating"] = pd.to_numeric(df["eps_rating"], errors="coerce").astype("Int64")
        df["eps_a_years"] = pd.to_numeric(df["eps_a_years"], errors="coerce").astype("Int64")
    return df
