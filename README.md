# Nick's India Stock Desk

A research screen for NSE stocks. It scores names, writes the tables, and shows them on a website.

It does not place trades. It does not call a broker. It does not pick option contracts. The liquid stocks page is a stock screen. Put and call walls are a mood gauge. Prices are in rupees. Times are shown in IST and PT.

## How the numbers get to the screen

```text
GitHub Action (stock_desk.py on a schedule)
        |  writes CSVs
        v
data/*.csv on GitHub
        |  the site reads the raw files
        v
GitHub Pages (site/)
```

The pages do no scoring. The Python job does the work. On github.io the site loads CSVs from raw.githubusercontent.com, so a data update does not need a new site build.

## The universe

Three lists, one row per ticker:

- Nifty 50
- Nifty Next 50
- Nifty Midcap 150

Lists come from the NSE archive CSV, then Wikipedia when that page exists. Each list has a switch in `config.json` (`nifty50`, `next50`, `midcap150`). Turning one off drops names that are only on that list. Holdings and the watchlist are always scored. A name outside the lists is tagged Focus. If a fetch fails, the saved list is reused and the Data updates page says CACHED.

## The score

Each piece is +1, 0, or -1 against that company's own recent history. A missing piece stays blank. It is not stored as 0.

The benchmark is the Nifty 50. Bank Nifty is shown beside it. Sector strength uses Nifty sector indexes (IT, Bank, Auto, Pharma, FMCG, and the rest), not US ETFs.

BUY, HOLD, and AVOID are research labels. They are not orders.

## What is fetched, and how often

Yahoo prices use one batched download for many tickers. The full history stays in `cache/ohlcv.csv.gz` (about 3 years). An hourly run only asks for the last few sessions and merges them in. Statements, profiles, shareholding, news, and option chains refresh at most once a day, on the after-close run.

If Yahoo or NSE fails, the job keeps the saved file and the Data updates page says CACHED.

Published candle files are about 3 years and are rewritten only when the text changed.

## Pages that can say "not available"

These stay on the site with a plain note when the free source does not answer:

- Shareholding FII and DII, when the filing split was not fetched. Promoter percent can still show.
- Insider counts, when the NSE PIT file is blocked.
- Put/call and option walls, when the NSE option chain is blocked.
- India 10-year yield, when FRED does not answer. CPI and GDP still come from the World Bank when that feed works. There is no forecast, so the surprise score stays blank.
- Official Nifty 50 P/E. The chart is the median of stocks on this desk.

## Run it on your computer

```text
pip install -r requirements.txt
python tests/test_net.py
python tests/test_scoring.py
python tests/test_fundamentals.py
python tests/test_universe.py
python tests/test_job.py
python tests/test_setups.py
python stock_desk.py --full
```

`--hourly` refreshes recent prices only. `--offline` rebuilds the pages from the cache and does not call the network.

Edit example holdings in `input/holdings.csv` and the watchlist in `input/my_watchlist.csv`. Switches live in `config.json`.
