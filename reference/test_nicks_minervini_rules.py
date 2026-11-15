#!/usr/bin/env python3
"""Rule checks for Nick's TradingView Minervini indicator.

These tests do not compile Pine and they do not measure profitability.
They lock the unchanged script blocks, and they run the same pass/fail
rules as the updated script: 25% above the 52-week low, benchmark
relative strength, and the quiet final contraction.

Run from the repo root:
    python reference/test_nicks_minervini_rules.py
"""
import hashlib
import random
import re
import unittest
from pathlib import Path

PINE = Path(__file__).resolve().parent / "nicks_minervini_with_exit_strategy.pine"

# Hashes of regions that this change must not touch. Computed from the
# canonical script before the three approved edits.
UNCHANGED = {
    "ma": (
        "sma50  = ta.sma(close, 50)",
        'plot(show200 ? sma200 : na, "SMA 200", color = color.new(color.red, 0),    linewidth = 1)\n',
        "70eb57fbd79954a98b7b3e7f3ba9b6584eae046142aa17cf8f297ebdd35e0cf2",
    ),
    "vcp": (
        "ph = ta.pivothigh(high, pivL, pivR)",
        "shrinking = cnt >= 2   // the run is shrinking by construction; need 2+ for a VCP\n",
        "6c22e63d4b2ca3a1052a2afb3761dd3d242fd61573372eed333bb3b11e11172c",
    ),
    "labels": (
        "var label vcpLbl = na",
        'array.push(cLbl, label.new(array.get(cLowBar, i), array.get(cLow, i) * 0.985, txt, style = label.style_label_up, color = color.new(color.purple, 0), textcolor = color.white, size = size.tiny))\n',
        "432c0407c700f4bd28ac28894ab75b8102785785e47164734007980b187c0574",
    ),
    "buy": (
        "pivotPrice = cnt > 0 ? array.get(cHigh, cnt - 1) : na",
        "    buyLine := na\n",
        "0588afcb5da709f5106c70cce04af11fd47150476c2756d200400fe547a0c930",
    ),
    "vol_draw": (
        "var array<label> vLbl = array.new<label>()",
        'array.push(vLbl, label.new(markBar, low[k], "", yloc = yloc.belowbar, style = label.style_triangleup, color = up ? color.new(color.green, 0) : color.new(color.red, 0), size = size.tiny))\n',
        "7f6d9c219b0d3c3d34b157b4674b4cc7823521673c7a4c7f074a28d37850718e",
    ),
    "alert": (
        'crossUp = ta.crossover(close, pivotPrice)',
        'alertcondition(breakout, "VCP Breakout", "{{ticker}} closed above the VCP buy point at {{close}}")\n',
        "8972c02dc52def91d251257cc5f455ed14803569c2111d59ba3ea190b44ed70b",
    ),
    "dist": (
        'showDist = input.bool(true, "Show distance from 52-week high", group = "Display")',
        "    table.cell(distT, 0, 0, txt, text_color = col, text_size = size.normal)\n",
        "ae5e6b08af6c7a7cea2eb25960b426a0a56d4ce5b09a8367a25e1473addb36f6",
    ),
    "exit": (
        "// --------- EXIT TOOLS (Minervini-style) ---------",
        None,
        "532f133401288d9843a18e3d7bac4553aef9f5708410cc0c97c2ed58400c97c6",
    ),
}


def pine_text():
    return PINE.read_text()


def between(src, start, end):
    i = src.index(start)
    if end is None:
        return src[i:]
    return src[i:src.index(end, i) + len(end)]


def strip_pine(src):
    """Drop comments and string contents so brackets and assignments can be checked."""
    out = []
    i = 0
    n = len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            if j < 0:
                break
            out.append("\n")
            i = j + 1
            continue
        if src[i] == '"':
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == '"':
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def above_low(close, low52, fraction):
    return close >= low52 * fraction


def within_high(close, high52):
    return close >= high52 * 0.75


def template_rules(close, sma50, sma150, sma200, sma200_prev, low52, high52, r8):
    """Rules 1-7 match the script. Rule 8 is passed in (the RS result)."""
    r1 = close > sma150 and close > sma200
    r2 = sma150 > sma200
    r3 = sma200 > sma200_prev
    r4 = sma50 > sma150 and sma50 > sma200
    r5 = close > sma50
    r6 = above_low(close, low52, 1.25)
    r7 = within_high(close, high52)
    rules = [r1, r2, r3, r4, r5, r6, r7, bool(r8)]
    return rules, sum(rules)


def old_beats_benchmark(stock, bench):
    """The previous rule 8: beat the benchmark over 126 and 252 bars. No RS-line trend."""
    if stock is None or bench is None or len(stock) <= 252 or len(bench) <= 252:
        return False
    b12 = bench[-1 - 252]
    b6 = bench[-1 - 126]
    s12 = stock[-1 - 252]
    s6 = stock[-1 - 126]
    if b12 is None or b6 is None or s12 is None or s6 is None:
        return False
    if min(b12, b6, s12, s6) <= 0:
        return False
    stock6 = stock[-1] / s6 - 1
    stock12 = stock[-1] / s12 - 1
    bench6 = bench[-1] / b6 - 1
    bench12 = bench[-1] / b12 - 1
    return stock6 > bench6 and stock12 > bench12


def rs_status(stock, bench, on_daily):
    """Mirror of rule 8.

    RS line = stock close / benchmark close.
    Pass requires a 1-day chart, about a year of history, the RS line above
    its value 126 and 252 bars ago, above its value 21 bars ago, and above
    its 50-bar average. A missing bar inside that 50-bar average is "not ready",
    same as Pine's ta.sma when a value is na.
    """
    if not on_daily:
        return {"status": "NEED DAILY", "r8": False}
    if not bench or bench[-1] is None or bench[-1] <= 0:
        return {"status": "NO BENCHMARK", "r8": False}

    n = min(len(stock), len(bench))
    stock = list(stock)[-n:]
    bench = list(bench)[-n:]
    rs = []
    for s, b in zip(stock, bench):
        if s is None or b is None or b <= 0:
            rs.append(None)
        else:
            rs.append(s / b)

    def ago(series, k):
        if len(series) <= k:
            return None
        return series[-1 - k]

    rs_now = ago(rs, 0)
    rs21 = ago(rs, 21)
    rs126 = ago(rs, 126)
    rs252 = ago(rs, 252)
    window = rs[-50:] if len(rs) >= 50 else None
    sma = None
    if window is not None and all(v is not None for v in window):
        sma = sum(window) / 50.0
    s6, s12 = ago(stock, 126), ago(stock, 252)
    b6, b12 = ago(bench, 126), ago(bench, 252)
    ready = (
        all(v is not None for v in (rs_now, rs21, rs126, rs252, sma, s6, s12, b6, b12))
        and s6 > 0 and s12 > 0 and b6 > 0 and b12 > 0
    )
    if not ready:
        return {"status": "NEED HISTORY", "r8": False}
    beat6 = rs_now > rs126
    beat12 = rs_now > rs252
    month_up = rs_now > rs21
    above = rs_now > sma
    # Same comparison the script uses for the on-chart percents.
    ret6 = (stock[-1] / s6 - 1) > (bench[-1] / b6 - 1)
    ret12 = (stock[-1] / s12 - 1) > (bench[-1] / b12 - 1)
    if ret6 != beat6 or ret12 != beat12:
        raise AssertionError("return test and RS-line test disagreed")
    r8 = beat6 and beat12 and month_up and above
    return {
        "status": "PASS" if r8 else "FAIL",
        "r8": r8,
        "beat6": beat6,
        "beat12": beat12,
        "month_up": month_up,
        "above": above,
    }


def dry_up(high, low, close, volume, avg50, hi_ago, lo_ago, pivot, quiet_frac=0.5, min_quiet=1):
    """Mirror of the quiet-final-contraction check.

    Lists are indexed by bars ago: index 0 is today, index hi_ago is the swing high.
    The first close above the pivot, walking from the high toward today, is the
    breakout. That bar and every newer bar are excluded.
    """
    if hi_ago is None or lo_ago is None or pivot is None or not pivot or pivot <= 0:
        return {"status": "WAIT", "ok": False, "reason": "not ready"}
    if lo_ago < 0 or hi_ago < lo_ago or hi_ago > 450:
        return {"status": "WAIT", "ok": False, "reason": "out of reach"}

    break_ago = -1
    for bk in range(hi_ago, -1, -1):
        px = close[bk]
        if break_ago < 0 and px is not None and px > pivot:
            break_ago = bk
    end_ago = break_ago + 1 if break_ago >= 0 else 0
    if end_ago > hi_ago:
        return {"status": "WAIT", "ok": False, "reason": "empty", "end_ago": end_ago, "break_ago": break_ago}

    vol_sum = 0.0
    vol_n = 0
    quiet_n = 0
    pull_sum = 0.0
    pull_n = 0
    right_sum = 0.0
    right_n = 0
    for wk in range(end_ago, hi_ago + 1):
        v = volume[wk]
        a = avg50[wk]
        if v is not None and a is not None and a > 0:
            vol_sum += v
            vol_n += 1
            if v <= a * quiet_frac:
                quiet_n += 1
        c = close[wk]
        h = high[wk]
        lo = low[wk]
        if c is not None and c > 0 and h is not None and lo is not None:
            rng = (h - lo) / c
            if wk >= lo_ago:
                pull_sum += rng
                pull_n += 1
            else:
                right_sum += rng
                right_n += 1

    ref = avg50[end_ago]
    mean = vol_sum / vol_n if vol_n else None
    ratio = mean / ref if mean is not None and ref is not None and ref > 0 else None
    vol_below = ratio is not None and ratio < 1.0
    quiet_ok = quiet_n >= min_quiet
    pull_avg = pull_sum / pull_n if pull_n else None
    right_avg = right_sum / right_n if right_n else None
    price_tight = (
        pull_n >= 2 and right_n >= 2 and pull_avg is not None and right_avg is not None and right_avg < pull_avg
    )
    vol_ready = vol_n >= 4 and ref is not None and ref > 0 and ratio is not None
    if not vol_ready:
        status, ok = "WAIT", False
    elif vol_below and quiet_ok:
        status, ok = "PASS", True
    else:
        status, ok = "FAIL", False
    if pull_n >= 2 and right_n >= 2 and pull_avg is not None and right_avg is not None and pull_avg > 0:
        if price_tight:
            tight_status, tight_ok = "PASS", True
        else:
            tight_status, tight_ok = "FAIL", False
    else:
        tight_status, tight_ok = "WAIT", False
    return {
        "status": status,
        "ok": ok,
        "ratio": ratio,
        "quiet_n": quiet_n,
        "pull_n": pull_n,
        "right_n": right_n,
        "vol_n": vol_n,
        "end_ago": end_ago,
        "break_ago": break_ago,
        "vol_below": vol_below,
        "quiet_ok": quiet_ok,
        "price_tight": price_tight,
        "tight_status": tight_status,
        "tight_ok": tight_ok,
        "included": list(range(end_ago, hi_ago + 1)),
    }


def is_vcp(shrinking, trend_ok, require_dry, dry_ok, require_tight=False, tight_ok=False,
          require_depth=False, depth_ok=False, require_base=False, base_ok=False):
    return (
        shrinking and trend_ok
        and ((not require_dry) or dry_ok)
        and ((not require_tight) or tight_ok)
        and ((not require_depth) or depth_ok)
        and ((not require_base) or base_ok)
    )


def depth_check(depths, limit=35.0, enabled=True):
    """Largest pullback in the base. Exactly the limit passes. Later ones already shrink."""
    if not enabled:
        return {"status": "OFF", "ok": True, "largest": None}
    if not depths:
        return {"status": "WAIT", "ok": False, "largest": None}
    largest = max(depths)
    ok = largest <= limit
    return {"status": "PASS" if ok else "FAIL", "ok": ok, "largest": largest}


def base_check(bars, min_weeks=3, max_weeks=45, enabled=True, daily=True):
    """Bars from the base's starting high to today. One week is 5 daily bars."""
    if not enabled:
        return {"status": "OFF", "ok": True, "weeks": None}
    if not daily or bars is None:
        return {"status": "WAIT", "ok": False, "weeks": None}
    weeks = bars / 5.0
    if weeks < min_weeks:
        status, ok = "WAIT", False
    elif weeks > max_weeks:
        status, ok = "FAIL", False
    else:
        status, ok = "PASS", True
    return {"status": status, "ok": ok, "weeks": weeks}


class Contractions:
    """Line-by-line mirror of the contraction lists. Pivots are fed already confirmed."""

    def __init__(self, min_depth=3.0, min_bars=2, base_tol=5.0, lookback=100, max_t=4):
        self.min_depth = min_depth
        self.min_bars = min_bars
        self.base_tol = base_tol
        self.lookback = lookback
        self.max_t = max_t
        self.last_high = None
        self.last_high_bar = None
        self.last_type = 0
        self.h_depth, self.h_high, self.h_bar = [], [], []
        self.h_low, self.h_low_bar = [], []

    def pivot_high(self, price, bar):
        if self.last_type != 1 or self.last_high is None or price > self.last_high:
            self.last_high = price
            self.last_high_bar = bar
        self.last_type = 1

    def pivot_low(self, price, bar):
        if not (self.last_type == 1 and self.last_high is not None):
            return
        depth = (self.last_high - price) / self.last_high * 100
        if self.h_high and self.last_high <= self.h_high[-1] and price < self.h_low[-1]:
            prev = self.h_high[-1]
            self.h_depth[-1] = (prev - price) / prev * 100
            self.h_low[-1] = price
            self.h_low_bar[-1] = bar
            self.last_type = -1
        elif depth >= self.min_depth and bar - self.last_high_bar >= self.min_bars:
            self.h_depth.append(depth)
            self.h_high.append(self.last_high)
            self.h_bar.append(self.last_high_bar)
            self.h_low.append(price)
            self.h_low_bar.append(bar)
            self.last_type = -1

    def trim(self, bar_index):
        while self.h_bar and bar_index - self.h_bar[0] > self.lookback:
            for bucket in (self.h_depth, self.h_high, self.h_bar, self.h_low, self.h_low_bar):
                bucket.pop(0)

    def shrinking_run(self):
        base_idx = -1
        for i, high in enumerate(self.h_high):
            if base_idx < 0 or high > self.h_high[base_idx] * (1 + self.base_tol / 100):
                base_idx = i
        if base_idx < 0:
            return []
        depth = self.h_depth[base_idx:]
        if not depth:
            return []
        run_start = len(depth) - 1
        if run_start > 0:
            while run_start > 0 and depth[run_start - 1] > depth[run_start]:
                run_start -= 1
        run_start = max(run_start, len(depth) - self.max_t)
        return depth[run_start:]


def replay_exit(bars, stop_pct=7.0, use_be=True, be_r=2.5, show_part=True, part_pct=20.0,
                show_climax=True, climax_pct=25.0, climax_bars=10, show_trail=True,
                show_stop=True, exit_on=True, vol_mult=1.5):
    """Mirror of the exit block. Each bar dict supplies the fields the script reads."""
    state = {
        "in_trade": False, "entry": None, "stop": None, "be_done": False,
        "part_done": False, "climax_done": False, "entry_bar": None,
    }
    log = []
    for bar in bars:
        stop_hit = trail_hit = part_hit = climax_hit = False
        if exit_on:
            if state["in_trade"]:
                risk = state["entry"] * stop_pct / 100
                if use_be and not state["be_done"] and bar["high"] >= state["entry"] + be_r * risk:
                    state["stop"] = max(state["stop"], state["entry"])
                    state["be_done"] = True
                if show_part and not state["part_done"] and bar["high"] >= state["entry"] * (1 + part_pct / 100):
                    part_hit = True
                    state["part_done"] = True
                if (
                    show_climax and not state["climax_done"] and bar["index"] - state["entry_bar"] >= 3
                    and bar["close"] >= bar["close_ago"] * (1 + climax_pct / 100) and bar["close"] > state["entry"]
                ):
                    climax_hit = True
                    state["climax_done"] = True
                if show_stop and bar["close"] < state["stop"]:
                    stop_hit = True
                elif (
                    show_trail and bar["index"] - state["entry_bar"] >= 3
                    and bar["close"] < bar["trail"] and bar["prev_close"] >= bar["prev_trail"]
                ):
                    trail_hit = True
                if stop_hit or trail_hit:
                    state["in_trade"] = False
            if bar["breakout"] and not state["in_trade"]:
                state["in_trade"] = True
                state["entry"] = bar["close"]
                state["stop"] = bar["close"] * (1 - stop_pct / 100)
                state["be_done"] = False
                state["part_done"] = False
                state["climax_done"] = False
                state["entry_bar"] = bar["index"]
        else:
            state["in_trade"] = False
        avg = bar["avg"]
        heavy = avg is not None and bar["vol"] > avg * vol_mult
        log.append({
            "stop_hit": stop_hit, "trail_hit": trail_hit, "part_hit": part_hit,
            "climax_hit": climax_hit, "heavy": heavy, "in_trade": state["in_trade"],
            "entry": state["entry"], "stop": state["stop"], "be_done": state["be_done"],
        })
    return log


def flat_bar(index, close, high=None, low=None, vol=100, avg=100, trail=90, prev_close=None,
             prev_trail=90, breakout=False, close_ago=None):
    return {
        "index": index,
        "close": close,
        "high": close if high is None else high,
        "low": close if low is None else low,
        "vol": vol,
        "avg": avg,
        "trail": trail,
        "prev_close": close if prev_close is None else prev_close,
        "prev_trail": prev_trail,
        "breakout": breakout,
        "close_ago": close if close_ago is None else close_ago,
    }


def bars_ago_frame(n, close, high, low, volume, avg):
    """Build bars-ago lists (index 0 = today) from chronological lists."""
    def rev(xs):
        return list(reversed(xs))
    return rev(high), rev(low), rev(close), rev(volume), rev(avg)


class SourceLockTests(unittest.TestCase):
    def test_unchanged_regions_match_the_canonical_script(self):
        src = pine_text()
        for name, (start, end, digest) in UNCHANGED.items():
            chunk = between(src, start, end)
            got = hashlib.sha256(chunk.encode()).hexdigest()
            self.assertEqual(got, digest, name)

    def test_approved_lines_and_no_fake_rating(self):
        src = pine_text()
        self.assertIn('indicator("Nick\'s Minervini with Exit Strategy"', src)
        self.assertIn("//@version=6", src)
        self.assertIn("r6 = close >= low52 * 1.25", src)
        self.assertNotIn("1.30", src)
        self.assertNotIn("30%+", src)
        self.assertNotIn("spySymbol", src)
        self.assertNotIn("lookahead_on", src)
        self.assertIn('options = ["US: SPY", "India: Nifty 50", "Custom symbol"]', src)
        self.assertIn('"NSE:NIFTY"', src)
        self.assertIn("lookahead = barmerge.lookahead_off", src)
        self.assertIn("ignore_invalid_symbol = true", src)
        self.assertIn("bool onDaily = timeframe.isdaily and timeframe.multiplier == 1", src)
        self.assertIn("rsLine > rsLine[126]", src)
        self.assertIn("rsLine > rsLine[252]", src)
        self.assertIn("rsLine > rsLine[21]", src)
        self.assertIn("rsLine > rsSma50", src)
        self.assertIn("ta.sma(rsLine, 50)", src)
        self.assertIn(
            "isVCP = shrinking and trendOK and (not requireDry or dryUpOk) and (not requireTight or tightOk) and (not requireDepth or depthOk) and (not requireBase or baseOk)",
            src,
        )
        self.assertIn("breakout = not na(pivotPrice) and crossUp and (not needVolume or bigVol) and isVCP", src)
        self.assertIn("if dBreakAgo < 0 and not na(close[bk]) and close[bk] > dPiv", src)
        self.assertIn("int dEndAgo = dBreakAgo >= 0 ? dBreakAgo + 1 : 0", src)
        self.assertIn("array.get(cBar, cnt - 1)", src)
        self.assertIn("array.get(cLowBar, cnt - 1)", src)
        self.assertIn("dryMeanRatio < 1.0", src)
        self.assertIn("vBar <= aBar * quietFrac", src)
        self.assertIn("rightAvg < pullAvg", src)
        self.assertIn('input.float(0.5, "Quiet day:', src)
        self.assertIn('input.int(1, "Quiet days needed"', src)
        self.assertIn('input.float(1.5, "Big volume = this many x 50-day average"', src)
        self.assertEqual(src.count("avgVol = ta.sma(volume, 50)"), 1)
        self.assertLess(src.index("avgVol = ta.sma(volume, 50)"), src.index("isVCP = shrinking"))
        self.assertIn("if nH > 0 and lastHigh <= array.get(hHigh, nH - 1) and pl < array.get(hLow, nH - 1)", src)
        self.assertIn("a breakout to a new high does NOT reset the base", src)
        self.assertIn('stopPct    = input.float(7.0,', src)
        self.assertIn('beR        = input.float(2.5,', src)
        self.assertIn('partPct    = input.float(20.0,', src)
        self.assertIn('climaxPct  = input.float(25.0,', src)
        self.assertIn('climaxBars = input.int(10,', src)
        self.assertIn('trailLen   = input.string("20",', src)
        for line in src.splitlines():
            if "1-99" in line or "RS Rating" in line:
                self.assertRegex(line, r"(?i)\b(not|no)\b")
        self.assertNotIn("rsRating", src)
        self.assertIn("fake number", src)

    def test_score_box_stays_small_and_rules_stay(self):
        src = pine_text()
        self.assertIn("table.new(position.bottom_right, 2, 13,", src)
        self.assertIn('input.int(225, "Base lookback (bars)"', src)
        self.assertIn('input.float(35.0, "Deepest pullback allowed (%)"', src)
        self.assertIn('input.int(3, "Base minimum (weeks)"', src)
        self.assertIn('input.int(45, "Base maximum (weeks)"', src)
        self.assertIn('"Depth"', src)
        self.assertIn('"Base"', src)
        self.assertIn('requireTight = input.bool(true, "VCP and BUY need tighter bars after the low"', src)
        self.assertIn('"Bars tightened"', src)
        self.assertNotIn("table.merge_cells", src)
        self.assertNotIn("table.cell(tt, 0, 9, rsDetail", src)
        self.assertNotIn("table.cell(tt, 0, 11, dryDetail", src)
        self.assertIn("tooltip = rsTip", src)
        self.assertIn("tooltip = dryDetail", src)
        self.assertIn("tooltip = tightDetail", src)
        self.assertIn("Both 6 months and 12 months have to beat the benchmark.", src)
        self.assertIn("Average volume is ", src)
        self.assertIn('showNumbers = input.bool(true, "Show short numbers in the score box"', src)
        self.assertIn('volMarks = input.int(8, "Big-volume marks to draw"', src)
        self.assertIn("marked < volMarks and bigVol[k]", src)
        self.assertIn("breakout = not na(pivotPrice) and crossUp and (not needVolume or bigVol) and isVCP", src)
        self.assertNotIn("volMarks", src.split("breakout = not na(pivotPrice)")[1].split("\n")[0])
        self.assertIn("r6 = close >= low52 * 1.25", src)
        self.assertIn("r8 = beat6 and beat12 and rsMonthUp and rsAboveAvg", src)
        self.assertIn("dryMeanRatio < 1.0", src)
        self.assertIn("quietN >= minQuiet", src)
        self.assertIn("rightAvg < pullAvg", src)
        self.assertIn("array.get(cLow, i) * 0.985", src)
        self.assertIn('stopPct    = input.float(7.0,', src)

    def test_script_is_plain_ascii(self):
        src = pine_text()
        bad = sorted({ch for ch in src if ord(ch) > 127})
        self.assertEqual(bad, [], "non-ASCII: " + " ".join(hex(ord(ch)) for ch in bad))

    def test_pine_structure(self):
        src = pine_text()
        self.assertNotIn("\t", src)
        code = strip_pine(src)
        stack = []
        pairs = {")": "(", "]": "[", "}": "{"}
        for i, ch in enumerate(code):
            if ch in "([{":
                stack.append(ch)
            elif ch in ")]}":
                self.assertTrue(stack, f"extra {ch} at {i}")
                self.assertEqual(stack.pop(), pairs[ch], f"mismatch at {i}")
        self.assertEqual(stack, [])
        declared = set()
        assign = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?::=|=(?!=))")
        for lineno, line in enumerate(code.splitlines(), 1):
            for match in assign.finditer(line):
                name = match.group(1)
                op = match.group(0)[match.end(1) - match.start():]
                if op.startswith(":="):
                    self.assertIn(name, declared, f"{name} assigned with := before = on line {lineno}")
                else:
                    declared.add(name)


class TemplateTests(unittest.TestCase):
    def test_rule6_boundary_moved_from_30_to_25(self):
        low = 100
        self.assertFalse(above_low(124.99, low, 1.25))
        self.assertTrue(above_low(125, low, 1.25))
        self.assertTrue(above_low(130, low, 1.25))
        # The band between 25% and 30% is the change.
        self.assertTrue(above_low(125, low, 1.25))
        self.assertFalse(above_low(125, low, 1.30))
        self.assertFalse(above_low(129.99, low, 1.30))
        self.assertTrue(above_low(130, low, 1.30))

    def test_other_template_rules_unchanged(self):
        rules, score = template_rules(
            close=130, sma50=120, sma150=110, sma200=100, sma200_prev=99,
            low52=100, high52=140, r8=True,
        )
        self.assertEqual(rules, [True] * 8)
        self.assertEqual(score, 8)
        # Rule 1 needs both longer averages. Rule 3 needs a rising 200. Rule 7 is 25% of the high.
        r, _ = template_rules(130, 120, 110, 140, 100, 100, 140, True)
        self.assertFalse(r[0])  # price is not above the 200-day
        self.assertFalse(r[1])  # and the 150-day is not above that 200-day either
        r, _ = template_rules(130, 120, 110, 100, 100, 100, 140, True)
        self.assertFalse(r[2])  # 200 flat, not rising
        self.assertFalse(within_high(74.99, 100))
        self.assertTrue(within_high(75, 100))
        r, s = template_rules(130, 120, 110, 100, 99, 100, 140, False)
        self.assertEqual(r[:7], [True] * 7)
        self.assertFalse(r[7])
        self.assertEqual(s, 7)

    def test_vcp_gate_keeps_dry_up_optional(self):
        self.assertTrue(is_vcp(True, True, False, False))
        self.assertFalse(is_vcp(True, True, True, False))
        self.assertTrue(is_vcp(True, True, True, True))
        self.assertFalse(is_vcp(False, True, False, True))
        self.assertFalse(is_vcp(True, False, False, True))


class RelativeStrengthTests(unittest.TestCase):
    def _series(self, n=400, stock_at=None, bench=100):
        stock = [100 + i for i in range(n)]
        benchmark = [bench] * n if not isinstance(bench, list) else list(bench)
        if stock_at:
            for i, value in stock_at.items():
                stock[i] = value
        return stock, benchmark

    def test_rising_stock_beats_a_flat_benchmark(self):
        stock, bench = self._series()
        got = rs_status(stock, bench, True)
        self.assertEqual(got["status"], "PASS")
        self.assertTrue(got["r8"] and got["beat6"] and got["beat12"] and got["month_up"] and got["above"])

    def test_lagging_the_benchmark_fails(self):
        # Same shape as the AMZN daily screenshot: stock behind SPY over 6 and 12 months.
        # A red FAIL there is the rule. The layout change must not turn it into a pass.
        n = 400
        stock = [100.0] * n
        bench = [100.0] * n
        stock[-1] = 103.6
        stock[-127] = 103.6 / (1 - 0.049)
        stock[-253] = 103.6 / 1.036
        bench[-1] = 100.0
        bench[-127] = 100.0 / (1 - 0.003)
        bench[-253] = 100.0 / 1.086
        got = rs_status(stock, bench, True)
        self.assertEqual(got["status"], "FAIL")
        self.assertFalse(got["beat6"])
        self.assertFalse(got["beat12"])
        self.assertFalse(got["r8"])

    def test_tie_does_not_pass(self):
        stock = [100] * 400
        got = rs_status(stock, stock, True)
        self.assertEqual(got["status"], "FAIL")
        self.assertFalse(got["r8"])

    def test_old_6_and_12_pass_is_not_enough_when_the_line_is_not_rising(self):
        n = 400
        stock, bench = self._series(n)
        today = n - 1
        stock[today - 252] = 150
        stock[today - 126] = 200
        stock[today - 21] = 500
        stock[today] = 490
        for i in range(today - 49, today):
            if i != today - 21:
                stock[i] = 400
        got = rs_status(stock, bench, True)
        self.assertTrue(old_beats_benchmark(stock, bench))
        self.assertFalse(got["month_up"])
        self.assertTrue(got["beat6"] and got["beat12"] and got["above"])
        self.assertEqual(got["status"], "FAIL")

    def test_below_its_50_day_average_fails_even_if_the_month_is_up(self):
        n = 400
        stock, bench = self._series(n)
        today = n - 1
        stock[today - 252] = 100
        stock[today - 126] = 200
        stock[today - 21] = 300
        stock[today] = 400
        for i in range(today - 49, today + 1):
            if i not in (today - 21, today):
                stock[i] = 2000
        got = rs_status(stock, bench, True)
        self.assertTrue(got["beat6"] and got["beat12"] and got["month_up"])
        self.assertFalse(got["above"])
        self.assertEqual(got["status"], "FAIL")
        self.assertTrue(old_beats_benchmark(stock, bench))

    def test_loses_the_6_month_window(self):
        n = 400
        stock, bench = self._series(n)
        today = n - 1
        stock[today - 252] = 100
        stock[today - 126] = 800
        stock[today] = 300
        got = rs_status(stock, bench, True)
        self.assertFalse(got["beat6"])
        self.assertTrue(got["beat12"])
        self.assertEqual(got["status"], "FAIL")

    def test_missing_benchmark_history_and_timeframe(self):
        stock, bench = self._series()
        self.assertEqual(rs_status(stock, bench, False)["status"], "NEED DAILY")
        self.assertEqual(rs_status(stock, None, False)["status"], "NEED DAILY")
        self.assertEqual(rs_status(stock, None, True)["status"], "NO BENCHMARK")
        self.assertEqual(rs_status(stock, [0] * len(stock), True)["status"], "NO BENCHMARK")
        self.assertEqual(rs_status(stock, [-1] * len(stock), True)["status"], "NO BENCHMARK")
        short_s, short_b = self._series(200)
        self.assertEqual(rs_status(short_s, short_b, True)["status"], "NEED HISTORY")
        stock[-10] = None
        self.assertEqual(rs_status(stock, bench, True)["status"], "NEED HISTORY")
        stock, bench = self._series()
        stock[-252 - 1] = 0
        self.assertEqual(rs_status(stock, bench, True)["status"], "NEED HISTORY")

    def test_return_and_rs_line_agree_on_random_prices(self):
        rng = random.Random(25)
        for _ in range(200):
            stock = [rng.randint(1, 5000) for _ in range(300)]
            bench = [rng.randint(1, 5000) for _ in range(300)]
            for ago in (21, 126, 252):
                s_now, s_then = stock[-1], stock[-1 - ago]
                b_now, b_then = bench[-1], bench[-1 - ago]
                gap = (s_now / s_then) - (b_now / b_then)
                line_gap = (s_now / b_now) - (s_then / b_then)
                if abs(gap) > 1e-6 and abs(line_gap) > 1e-6:
                    self.assertEqual(gap > 0, line_gap > 0)


class DryUpTests(unittest.TestCase):
    def _quiet_pass(self, breakout_volume=None):
        # Bars ago 5..0. Pivot is 10. Closes stay under it unless a breakout is requested.
        # Pullback (high through low) is wider than the days after the low.
        n = 6
        close = [9, 9, 9, 8, 9, 9]  # ago 0..5, but we'll build chrono then flip
        # Build chronological: oldest is the high (ago 5), then down to the low (ago 3), then two tight days, then today.
        chrono_close = [9.0, 8.5, 8.0, 9.0, 9.2, 9.4]
        chrono_high = [10.0, 9.0, 8.4, 9.2, 9.4, 9.6]
        chrono_low = [8.8, 8.2, 7.6, 8.8, 9.1, 9.3]
        chrono_vol = [80, 70, 40, 30, 25, 20]
        chrono_avg = [100] * 6
        if breakout_volume is not None:
            chrono_close[-1] = 10.5
            chrono_high[-1] = 11
            chrono_vol[-1] = breakout_volume
            chrono_avg[-1] = 110
        high, low, close, volume, avg = bars_ago_frame(n, chrono_close, chrono_high, chrono_low, chrono_vol, chrono_avg)
        # ago: 0 today, 5 = oldest = swing high. low is the third chrono bar = ago 3.
        return dry_up(high, low, close, volume, avg, hi_ago=5, lo_ago=3, pivot=10)

    def test_quiet_contraction_passes(self):
        got = self._quiet_pass()
        self.assertEqual(got["status"], "PASS", got)
        self.assertTrue(got["ok"])
        self.assertLess(got["ratio"], 1)
        self.assertGreaterEqual(got["quiet_n"], 1)
        self.assertTrue(got["price_tight"])
        self.assertEqual(got["tight_status"], "PASS")
        self.assertTrue(is_vcp(True, True, True, got["ok"], True, got["tight_ok"]))
        self.assertEqual(got["break_ago"], -1)
        self.assertEqual(got["included"], [0, 1, 2, 3, 4, 5])

    def test_breakout_volume_is_excluded_and_cannot_fail_the_dry_up(self):
        quiet = self._quiet_pass()
        loud = self._quiet_pass(breakout_volume=5000)
        self.assertEqual(loud["status"], "PASS", loud)
        self.assertEqual(loud["end_ago"], 1)
        self.assertNotIn(0, loud["included"])
        self.assertEqual(loud["included"], [1, 2, 3, 4, 5])
        included_vols = [80, 70, 40, 30, 25]
        self.assertAlmostEqual(loud["ratio"], (sum(included_vols) / len(included_vols)) / 100)
        self.assertNotAlmostEqual(loud["ratio"], quiet["ratio"], places=3)
        # If that breakout bar were included, the average would be above the 50-day.
        polluted = (sum(included_vols) + 5000) / 6
        self.assertGreater(polluted / 110, 1)

    def test_volume_equal_to_the_average_fails(self):
        n = 6
        chrono_close = [9.0, 8.5, 8.0, 9.0, 9.2, 9.4]
        chrono_high = [10.0, 9.0, 8.4, 9.2, 9.4, 9.6]
        chrono_low = [8.8, 8.2, 7.6, 8.8, 9.1, 9.3]
        chrono_vol = [100] * 6
        chrono_avg = [100] * 6
        high, low, close, volume, avg = bars_ago_frame(n, chrono_close, chrono_high, chrono_low, chrono_vol, chrono_avg)
        got = dry_up(high, low, close, volume, avg, 5, 3, 10, quiet_frac=1.0, min_quiet=1)
        self.assertEqual(got["ratio"], 1)
        self.assertFalse(got["vol_below"])
        self.assertTrue(got["quiet_ok"] and got["price_tight"])
        self.assertEqual(got["status"], "FAIL")

    def test_quiet_day_threshold_is_at_or_under(self):
        n = 6
        chrono_close = [9.0, 8.5, 8.0, 9.0, 9.2, 9.4]
        chrono_high = [10.0, 9.0, 8.4, 9.2, 9.4, 9.6]
        chrono_low = [8.8, 8.2, 7.6, 8.8, 9.1, 9.3]
        # One day exactly half, the rest just above half but still under the 50-day average.
        chrono_vol = [60, 60, 50, 60, 60, 60]
        chrono_avg = [100] * 6
        high, low, close, volume, avg = bars_ago_frame(n, chrono_close, chrono_high, chrono_low, chrono_vol, chrono_avg)
        one = dry_up(high, low, close, volume, avg, 5, 3, 10, quiet_frac=0.5, min_quiet=1)
        self.assertEqual(one["quiet_n"], 1)
        self.assertEqual(one["status"], "PASS")
        need_two = dry_up(high, low, close, volume, avg, 5, 3, 10, quiet_frac=0.5, min_quiet=2)
        self.assertEqual(need_two["status"], "FAIL")
        chrono_vol[2] = 50.01
        high, low, close, volume, avg = bars_ago_frame(n, chrono_close, chrono_high, chrono_low, chrono_vol, chrono_avg)
        just_over = dry_up(high, low, close, volume, avg, 5, 3, 10, quiet_frac=0.5, min_quiet=1)
        self.assertEqual(just_over["quiet_n"], 0)
        self.assertEqual(just_over["status"], "FAIL")

    def test_wider_bars_after_the_low_fail(self):
        n = 6
        chrono_close = [9.0, 8.8, 8.6, 9.0, 9.0, 9.0]
        chrono_high = [9.2, 9.0, 8.8, 10.0, 10.0, 10.0]
        chrono_low = [8.9, 8.7, 8.5, 7.0, 7.0, 7.0]
        chrono_vol = [40, 40, 40, 30, 30, 30]
        chrono_avg = [100] * 6
        high, low, close, volume, avg = bars_ago_frame(n, chrono_close, chrono_high, chrono_low, chrono_vol, chrono_avg)
        got = dry_up(high, low, close, volume, avg, 5, 3, 10)
        self.assertFalse(got["price_tight"])
        self.assertEqual(got["tight_status"], "FAIL")
        self.assertTrue(got["vol_below"] and got["quiet_ok"])
        self.assertEqual(got["status"], "PASS")
        self.assertFalse(is_vcp(True, True, True, got["ok"], True, got["tight_ok"]))
        self.assertTrue(is_vcp(True, True, True, got["ok"], False, got["tight_ok"]))

    def test_too_few_days_after_the_low_waits(self):
        # Low is yesterday. Only today is after the low, so the tighten test is not ready.
        n = 4
        chrono_close = [9.0, 8.5, 8.0, 9.2]
        chrono_high = [10.0, 9.0, 8.5, 9.4]
        chrono_low = [8.6, 8.2, 7.5, 9.0]
        chrono_vol = [40, 35, 30, 20]
        chrono_avg = [100] * 4
        high, low, close, volume, avg = bars_ago_frame(n, chrono_close, chrono_high, chrono_low, chrono_vol, chrono_avg)
        got = dry_up(high, low, close, volume, avg, hi_ago=3, lo_ago=1, pivot=10)
        self.assertEqual(got["right_n"], 1)
        self.assertGreaterEqual(got["pull_n"], 2)
        self.assertEqual(got["tight_status"], "WAIT")
        self.assertFalse(got["tight_ok"])
        self.assertFalse(is_vcp(True, True, True, True, True, got["tight_ok"]))

    def test_no_average_and_out_of_reach_wait(self):
        n = 6
        chrono_close = [9.0, 8.5, 8.0, 9.0, 9.2, 9.4]
        chrono_high = [10.0, 9.0, 8.4, 9.2, 9.4, 9.6]
        chrono_low = [8.8, 8.2, 7.6, 8.8, 9.1, 9.3]
        chrono_vol = [40] * 6
        chrono_avg = [None] * 6
        high, low, close, volume, avg = bars_ago_frame(n, chrono_close, chrono_high, chrono_low, chrono_vol, chrono_avg)
        got = dry_up(high, low, close, volume, avg, 5, 3, 10)
        self.assertEqual(got["status"], "WAIT")
        self.assertEqual(dry_up(high, low, close, volume, avg, 500, 3, 10)["reason"], "out of reach")
        self.assertEqual(dry_up(high, low, close, volume, avg, None, 3, 10)["reason"], "not ready")

    def test_only_the_final_contraction_window_is_measured(self):
        # A heavy bar older than the swing high is not in the lists the check receives.
        got = self._quiet_pass()
        self.assertEqual(max(got["included"]), 5)


class DepthAndBaseTests(unittest.TestCase):
    def test_depth_limit_passes_at_35_and_fails_above_it(self):
        exact = depth_check([35.0, 12.0, 6.0])
        self.assertEqual(exact["status"], "PASS")
        self.assertTrue(exact["ok"])
        self.assertEqual(exact["largest"], 35.0)
        deep = depth_check([35.01, 10.0])
        self.assertEqual(deep["status"], "FAIL")
        self.assertFalse(is_vcp(True, True, False, True, False, True, True, deep["ok"]))
        shallow = depth_check([10.0, 4.0], limit=35)
        self.assertEqual(shallow["status"], "PASS")
        self.assertTrue(is_vcp(True, True, False, True, False, True, True, shallow["ok"]))

    def test_depth_switch_off_does_not_block(self):
        off = depth_check([50.0], enabled=False)
        self.assertEqual(off["status"], "OFF")
        self.assertTrue(is_vcp(True, True, False, True, False, True, False, False))

    def test_no_pullback_waits(self):
        got = depth_check([])
        self.assertEqual(got["status"], "WAIT")
        self.assertFalse(got["ok"])

    def test_base_length_bounds(self):
        self.assertEqual(base_check(15)["status"], "PASS")  # 3.0 weeks
        self.assertAlmostEqual(base_check(15)["weeks"], 3.0)
        short = base_check(14)  # 2.8 weeks
        self.assertEqual(short["status"], "WAIT")
        self.assertFalse(is_vcp(True, True, False, True, False, True, False, True, True, short["ok"]))
        self.assertEqual(base_check(225)["status"], "PASS")  # 45.0 weeks
        long = base_check(226)
        self.assertEqual(long["status"], "FAIL")
        self.assertFalse(long["ok"])
        self.assertEqual(base_check(None)["status"], "WAIT")
        self.assertEqual(base_check(100, daily=False)["status"], "WAIT")

    def test_base_switch_off_does_not_block(self):
        self.assertEqual(base_check(10, enabled=False)["status"], "OFF")
        self.assertTrue(is_vcp(True, True, False, True, False, True, False, True, False, False))


class ContractionTests(unittest.TestCase):
    def test_lower_high_and_lower_low_extend_one_contraction(self):
        c = Contractions()
        c.pivot_high(100, 10)
        c.pivot_low(90, 20)
        self.assertEqual(len(c.h_depth), 1)
        c.pivot_high(99, 30)  # lower high, so this is still the same pullback if the low undercuts
        c.pivot_low(85, 40)
        self.assertEqual(len(c.h_depth), 1)
        self.assertAlmostEqual(c.h_depth[0], (100 - 85) / 100 * 100)
        self.assertEqual(c.h_low[0], 85)
        self.assertEqual(c.h_low_bar[0], 40)

    def test_a_shallower_next_dip_is_a_new_contraction(self):
        c = Contractions()
        c.pivot_high(100, 10)
        c.pivot_low(90, 20)
        c.pivot_high(98, 30)
        c.pivot_low(94, 40)  # not a lower low, depth about 4%
        self.assertEqual(len(c.h_depth), 2)
        self.assertGreater(c.h_depth[0], c.h_depth[1])

    def test_tiny_or_too_short_dip_is_ignored(self):
        c = Contractions()
        c.pivot_high(100, 10)
        c.pivot_low(98, 20)  # 2% < 3% minimum
        self.assertEqual(c.h_depth, [])
        c.pivot_low(90, 11)  # deep, but only 1 bar from the high
        self.assertEqual(c.h_depth, [])

    def test_base_survives_a_breakout_and_a_small_retest(self):
        c = Contractions()
        c.pivot_high(232, 10)
        c.pivot_low(200, 30)
        c.pivot_high(232.5, 50)  # retest, not 5% higher
        c.pivot_low(220, 70)
        highs_before = list(c.h_high)
        # A breakout is not a pivot, so the lists do not change.
        self.assertEqual(c.h_high, highs_before)
        run = c.shrinking_run()
        self.assertEqual(len(run), 2)
        # A clearly higher high starts a new base and drops the old contraction.
        c.pivot_high(260, 90)
        c.pivot_low(240, 110)
        self.assertEqual(len(c.shrinking_run()), 1)

    def test_equal_depths_do_not_chain_and_max_t_caps_the_run(self):
        c = Contractions(max_t=4)
        # Higher highs, so a lower low does not extend the previous contraction.
        specs = [(100, 80), (120, 96), (150, 120), (180, 144), (200, 160)]
        bar = 0
        for high, low in specs:
            bar += 5
            c.pivot_high(high, bar)
            bar += 5
            c.pivot_low(low, bar)
        # Each depth is 20%, so none is strictly tighter. Only the newest stands.
        self.assertEqual(len(c.shrinking_run()), 1)
        c = Contractions(max_t=2)
        depths = [20, 15, 10, 8]
        price = 100
        bar = 0
        for depth in depths:
            bar += 5
            c.pivot_high(price, bar)
            bar += 5
            c.pivot_low(price * (1 - depth / 100), bar)
            price = price * 0.99  # next high is lower, but the low is not under the previous low
        got = c.shrinking_run()
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[0], 10)
        self.assertAlmostEqual(got[1], 8)


class ExitTests(unittest.TestCase):
    def test_defaults_and_breakeven_partial_stop(self):
        # Buy at 100. Stop starts at 93. Breakeven arms at 117.5. Partial at 120.
        bars = [
            flat_bar(0, 100, breakout=True),
            flat_bar(1, 110, high=117.49),
            flat_bar(2, 112, high=117.5),
            flat_bar(3, 115, high=120),
            flat_bar(4, 121, high=122),
            flat_bar(5, 100, high=101),  # close equals the moved stop: not a hit
            flat_bar(6, 99.99, high=101),
        ]
        log = replay_exit(bars)
        self.assertEqual(log[0]["entry"], 100)
        self.assertAlmostEqual(log[0]["stop"], 93)
        self.assertFalse(log[1]["be_done"])
        self.assertTrue(log[2]["be_done"])
        self.assertAlmostEqual(log[2]["stop"], 100)
        self.assertTrue(log[3]["part_hit"])
        self.assertFalse(log[4]["part_hit"])  # once
        self.assertFalse(log[5]["stop_hit"])
        self.assertTrue(log[6]["stop_hit"])
        self.assertFalse(log[6]["in_trade"])

    def test_climax_needs_three_bars_and_fires_once(self):
        bars = [flat_bar(0, 100, breakout=True, close_ago=100)]
        for i, close in enumerate((110, 120, 130), start=1):
            bars.append(flat_bar(i, close, close_ago=100))
        log = replay_exit(bars)
        self.assertFalse(log[1]["climax_hit"])
        self.assertFalse(log[2]["climax_hit"])
        self.assertTrue(log[3]["climax_hit"])  # 130 >= 100 * 1.25, three bars in
        bars.append(flat_bar(4, 140, close_ago=100))
        log = replay_exit(bars)
        self.assertFalse(log[4]["climax_hit"])

    def test_trail_does_not_fire_before_three_bars_or_when_the_stop_also_hits(self):
        bars = [
            flat_bar(0, 100, breakout=True),
            flat_bar(2, 101, trail=102, prev_close=103, prev_trail=102),
            flat_bar(3, 101, trail=102, prev_close=103, prev_trail=102),
        ]
        log = replay_exit(bars)
        self.assertFalse(log[1]["trail_hit"])
        self.assertTrue(log[2]["trail_hit"])
        self.assertFalse(log[2]["heavy"])
        # Stop wins over the trail on the same bar. A wick under the stop is not a stop.
        bars = [
            flat_bar(0, 100, breakout=True),
            flat_bar(5, 96, low=80, trail=95, prev_close=97, prev_trail=95),
            flat_bar(6, 90, trail=95, prev_close=96, prev_trail=95, vol=200, avg=100),
        ]
        log = replay_exit(bars)
        self.assertFalse(log[1]["stop_hit"])
        self.assertFalse(log[1]["trail_hit"])
        self.assertTrue(log[2]["stop_hit"])
        self.assertFalse(log[2]["trail_hit"])
        self.assertTrue(log[2]["heavy"])

    def test_heavy_trail_and_master_switch_and_no_reset_while_in_a_trade(self):
        bars = [
            flat_bar(0, 100, breakout=True),
            flat_bar(4, 101, trail=110, prev_close=112, prev_trail=110, vol=160, avg=100),
        ]
        log = replay_exit(bars)
        self.assertTrue(log[1]["trail_hit"] and log[1]["heavy"])
        bars = [flat_bar(0, 100, breakout=True), flat_bar(1, 50, breakout=True)]
        log = replay_exit(bars, exit_on=False)
        self.assertFalse(log[0]["in_trade"])
        self.assertFalse(log[1]["stop_hit"])
        # Still in the trade: a new breakout does not replace the entry.
        bars = [flat_bar(0, 100, breakout=True), flat_bar(1, 110, breakout=True)]
        log = replay_exit(bars)
        self.assertEqual(log[1]["entry"], 100)
        # Stop and a fresh breakout on the same bar: exit, then the script enters again.
        bars = [flat_bar(0, 100, breakout=True), flat_bar(1, 90, breakout=True)]
        log = replay_exit(bars)
        self.assertTrue(log[1]["stop_hit"])
        self.assertTrue(log[1]["in_trade"])
        self.assertEqual(log[1]["entry"], 90)
        self.assertAlmostEqual(log[1]["stop"], 90 * 0.93)


if __name__ == "__main__":
    unittest.main()
