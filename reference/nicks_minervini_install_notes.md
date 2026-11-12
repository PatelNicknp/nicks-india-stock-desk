# Nick's Minervini indicator: how to put this on TradingView

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

The box stays in the **bottom-right**. Each row is a short name and PASS or FAIL. It does not print a paragraph on the chart. A long sentence in that box is what made it stretch across an iPad chart.

Press and hold a row on iPad, or hover on a computer, for the full note. **Show short numbers in the score box** (on by default) adds only a short number, such as `FAIL -4.9%/-0.3%` on the RS row or `FAIL 1.27x 0d` on the quiet row. Turn that switch off for the smallest box. Neither switch changes pass or fail.

A red **FAIL** means that rule missed. On the AMZN daily chart that was sent, RS vs SPY and the quiet contraction were FAIL because the stock lagged SPY and the last contraction was not quiet. That result is the rule, not a broken box.

**RS vs SPY** (or Nifty 50, or your symbol) is one of these:

- **PASS**. On a 1-day chart, the stock beat the benchmark over about 6 months and about 12 months, and the relative-strength line is rising.
- **FAIL**. The history is there, and at least one of those pieces missed. The row tip says which one. The short number, when shown, is the 6-month stock change and the 6-month benchmark change.
- **NEED DAILY**. The chart is not a 1-day chart. Open Daily.
- **NO BENCHMARK**. TradingView has no price for the symbol you picked. The rest of the script still runs.
- **NEED HISTORY**. The stock or the benchmark does not have about a year of daily prices yet.

**Last contraction quiet** is the volume check only:

- **PASS**. Volume dried up before the breakout.
- **FAIL**. There are enough days to judge, and the contraction is not quiet. The tip says whether volume is still heavy or a quiet day is missing. The short number is the volume multiple and how many quiet days were found.
- **WAIT**. Volume is not ready to judge yet. It does not count as a pass.

**Bars tightened** is its own row. It is on by default. The switch is **VCP and BUY need tighter bars after the low**.

- **PASS**. In the last pullback, the daily bars after the low are narrower than the bars on the way down. The short number is how the two ranges compare. Under 1.00x passes.
- **FAIL**. Both sides have at least two days, and the bars after the low are not narrower.
- **WAIT**. There are not yet two days on the way down and two days after the low. A wait is not a pass, so the green VCP tag and BUY stay off while this switch is on.
- **OFF**. You turned the switch off. The row does not block the tag or BUY.

Press and hold the row for the full note. The note stays off the chart so the box does not stretch.

**Big-volume marks to draw** defaults to 8, the latest marks in the current base, and it skips the bar that carries a T label so the triangles do not sit on that tag. The 1.5x breakout test is unchanged. Set the number to 0 to hide the marks. The T label sits a little under the contraction low so the box is not on the candle. The contraction count is unchanged.

## How the quiet check is calculated

It looks only at the **last** contraction (the newest T, the same high as the buy line).

It uses every day from that contraction's high through the **last day before** price first closes above the buy point. The breakout day is left out. A big breakout day cannot make this check fail.

The quiet row passes only when both are true:

- Average volume on those days is **below** the 50-day average volume (under 1.00x, not equal).
- At least one day has volume **at or under half** the usual 50-day volume. That count is "Quiet days." Set **Quiet days needed** to 2 if you want two. Extra quiet days are fine.

The bars-tightened row uses the same days, but it compares ranges, not volume. From the contraction high down to the low, it takes the average daily high-to-low range. Then it does the same for the days after the low, up to the day before the close over the buy line. The second average has to be smaller. Each side needs at least two days. The breakout day is left out of both checks.

The **Big volume** setting (1.5 times the 50-day average) is only the breakout day. It is separate. A quiet contraction does not replace it.

The green VCP tag and the BUY label need the quiet row and the bars-tightened row while those switches are on. Turn off **VCP and BUY need a quiet final contraction** to skip the volume check. Turn off **VCP and BUY need tighter bars after the low** to skip the range check. The rows still show.

## How relative strength is calculated

This is **not** IBD's 1-99 rating. TradingView does not give that number here, and this script does not invent one. IBD ranks a stock against thousands of other stocks. This chart can only see this stock and the one benchmark you pick.

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
- Contraction counting, the buy line, and the rule that a breakout does not erase the base.
- BUY, STOP, Sell part, Climax, and SELL still use the same prices and the same volume test.
- This layout fix does not change the website.

## What this does not do

It does not promise that a PASS will make money. These checks were run as rule tests on a computer. They were not compiled inside TradingView from here, and they were not run on past trades. After you add the script, open a daily chart you know and confirm the box shows 25%, your benchmark, and the quiet-volume line.
