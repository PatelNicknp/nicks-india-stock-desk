# Trading Floor rules

The Trading Floor is a page (`site/trading-floor.html`, page id `tradingfloor`) where six desk roles
talk through today's top picks in plain words. It is advice only: it never places an order, never
calls a broker, and sends no alerts.

Code: `trading_floor.py`. Wiring: `load_trading_floor()` in `stock_desk.py`. Tests:
`tests/test_trading_floor.py`. Output: `data/trading_floor.csv`. Headline cache:
`cache/trading_floor_news.csv`.

It runs on the main update after the NSE bhavcopy is in (3:00 AM PT, the close run) and on the
late-bhavcopy retry. The morning run leaves the saved file alone.

## Switches

- `features.trading_floor` (true): the whole page. Off writes an empty `trading_floor.csv` with the
  headers, makes no headline requests, hides the menu item, and the page says "Turned off in Settings".
- Every number below is in the `trading_floor` block of `config.json` and shows in Settings as
  `trading_floor.<group>.<key>`. Each role has `on` (off means that role votes 0 and says
  "Off in Settings"), and each check has its own `*_check` switch.

## Which stocks

1. The Buy setups rows the page lists (BUY and Not scored yet), in that page's own order.
2. If that is shorter than `max_stocks` and `fill_from_scanners` is on: stocks that are READY or
   BROKEN OUT today on at least `fill_min_scanners` of the pattern scanners (VCP, Box, Flag,
   Qullamaggie, Marios, EP, CANSLIM). Rows marked Too wide are left out. Levels come from
   `setups.buy_levels`.
3. At most `max_stocks` (15).
4. `stocks_only` (true) skips ETFs, index funds, and other fund units. A bhavcopy ISIN starting with INF is a fund. A fund series (F, E, G, and the other fund groups) is a fund. When the ISIN and series are missing, a fund name (ETF, BEES, mutual fund, index fund) is enough. The next individual stock in the same order takes the open slot. Set `stocks_only` to false to keep those names.

## Facts every role reads

All from the daily bars the desk already saved and the files it already built. No new Yahoo volume.

- price, day change, MA10, MA20, MA50, run, up streak, and gap, from those bars.
- volume ratio = today's volume / the average of the 50 sessions before today.
- entry, stop, target, risk %, reward/risk from Buy setups (target = target 1).
- market = Buy setups' `market_ok` (the check passes when the Nifty 50 or SENSEX is in an uptrend).
- next earnings from `scores.csv` when that column is on file.
- FII and DII net cash for the day, shown in one sentence. It does not add or subtract a point.
- RS score, only when a score column named `rs_score`, `rs`, or `rs_rank` is already on the desk.
  It is added to the Charts line and does not change the vote.

## Headlines (News)

Fresh means published within `news.fresh_days` (3) days of the price date. A headline counts when
it names the ticker or a distinctive word of the company. The desk's saved headlines come first,
including market headlines filed under MARKET. Only picks with none of those use the Google News
cache. That cache is filled on the main run only, once a day, one free RSS request per such pick
(no key, India edition), at most 15 a day. A failed request is soft.

## The roles

Each of News, Scout, Charts, Skeptic, and Sentiment gives +1, 0, or -1. The Chief adds them up.

- News: sum of headline tones. Positive +1, negative -1, mixed or none 0.
- Scout: 1.5x volume on an up day +1, on a down day -1, under 0.7x -1, a 3-day volume streak +1, else 0.
- Charts: veto when levels are missing or not stop < entry < target, or the price is at or under the stop.
  +1 when reward/risk is at least 2 and risk is 8% or less. Else 0.
- Skeptic: one objection each for no fresh news, thin volume, stretched over the 20-day or 50-day
  average, 5% or more over the entry, the market check failed, and earnings within 7 days.
  No objections +1, one 0, two or more -1. Hard no at 3 objections, or 10% over the entry.
- Sentiment: hot flags for a 15% run in 5 days, 8% over MA10, 12% over MA20, a 5% gap, 6 up days,
  and 5 fresh headlines. No flags +1, one 0, two or more -1.

Chief: Charts veto is Skip. Total 2 or more with no hard no is Buy. Total 0 or more is Wait. Otherwise Skip.

## The page

One card per stock, Buy first, then Wait, then Skip. One column on a phone, two on an iPad, three
on a wide screen. Tap a stock for the same price chart the other pages use, with the entry, stop,
and target lines. No new alerts and no TradingView button.
