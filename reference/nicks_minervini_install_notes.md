# Nick's Minervini indicator — how to put this on TradingView

Use this on a **Daily** chart (the normal 1-day chart). The script name is still **Nick's Minervini with Exit Strategy**.

## Install

1. Open TradingView. Open the stock. Switch the chart to **Daily**.
2. At the bottom, open **Pine Editor**.
3. Paste the whole script. Click **Save**, then **Add to chart**.
4. If the old copy is already on the chart, remove it first so you do not get two copies.

Paste the whole script in `nicks_minervini_with_exit_strategy.pine` (the file next to this note).

## What changed

Three things. The exits and the way contractions are counted are the same as before.

1. **25% above the 52-week low.** The score line now says "25%+ above 52w low." It used to say 30%. A stock exactly 25% above the low passes. Just under 25% fails.
2. **Relative strength.** In Settings, under Trend Template, set **Benchmark for relative strength**:
   - **US: SPY** for US stocks (this is the default).
   - **India: Nifty 50** for Indian stocks. The symbol used is NSE:NIFTY.
   - **Custom symbol** only if you want something else, such as NASDAQ:QQQ or BSE:SENSEX. Then fill in **Custom benchmark symbol**.
3. **Quiet last contraction.** Before a breakout, the last contraction should dry up. The green VCP tag and the BUY label now need that, unless you turn the new switch off.

## What the box on the chart is saying

Leave **Show each rule** on. The bottom-right box is a little taller than before.

**RS vs SPY** (or Nifty 50, or your symbol) is one of these:

- **PASS** — on a 1-day chart, the stock beat the benchmark over about 6 months and about 12 months, and the relative-strength line is rising.
- **FAIL** — the history is there, and at least one of those pieces missed. The gray line under it says which one.
- **NEED DAILY** — the chart is not a 1-day chart. Open Daily.
- **NO BENCHMARK** — TradingView has no price for the symbol you picked. The rest of the script still runs.
- **NEED HISTORY** — the stock or the benchmark does not have about a year of daily prices yet.

**Last contraction quiet** is one of these:

- **PASS** — volume dried up and price tightened before the breakout.
- **FAIL** — there are enough days to judge, and the contraction is not quiet. The gray line says whether volume is still heavy, a quiet day is missing, or the daily bars did not get tighter.
- **WAIT** — the last contraction is not finished enough to judge. It does not count as a pass yet.

## How the quiet check is calculated

It looks only at the **last** contraction (the newest T, the same high as the buy line).

It uses every day from that contraction's high through the **last day before** price first closes above the buy point. The breakout day is left out. A big breakout day cannot make this check fail.

It passes only when all three are true:

- Average volume on those days is **below** the 50-day average volume (under 1.00x, not equal).
- At least one day has volume **at or under half** the usual 50-day volume. That count is "Quiet days." Set **Quiet days needed** to 2 if you want two. Extra quiet days are fine.
- After the low, and still before the breakout, the daily bars are **narrower** than the bars from the high down to the low. Each side needs at least two days. Until then the line says WAIT.

The old **Big volume** setting (1.5 times the 50-day average) is only the breakout day. It is a separate switch. A quiet contraction does not replace it.

To mark VCP the old way, turn off **VCP and BUY need a quiet final contraction**. The quiet line still shows.

## How relative strength is calculated

This is **not** IBD's 1–99 rating. TradingView does not give that number here, and this script does not invent one. IBD ranks a stock against thousands of other stocks. This chart can only see this stock and the one benchmark you pick.

On a **1-day** chart:

- The RS line is the stock's price divided by the benchmark's price.
- 6 months means 126 trading days. 12 months means 252 trading days. The stock must beat the benchmark over both.
- Rising means the RS line is higher than it was 21 trading days ago, and higher than its own 50-day average.
- A tie does not pass. The stock has to be ahead.

If the stock's market is closed when the benchmark is open, or the other way around, TradingView repeats the last known benchmark price for that day. That is the same idea as the old SPY comparison.

## What did not change

- Stop: 7% under the buy price.
- Stop moves to breakeven when the gain is 2.5 times the risk.
- "Sell part" at a 20% profit.
- "Climax" when price is up 25% in 10 days.
- "SELL" when the close falls under the trail average (20-day, unless you pick 10 or 50).
- Contraction labels, the buy line, and the rule that a breakout does not erase the base.
- The website was not changed. It still uses the older 30% low and the older 6-month and 12-month comparison.

## What this does not do

It does not promise that a PASS will make money. These checks were run as rule tests on a computer. They were not compiled inside TradingView from here, and they were not run on past trades. After you add the script, open a daily chart you know and confirm the box shows 25%, your benchmark, and the quiet-volume line.
