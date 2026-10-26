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

Daily prices come from the NSE bhavcopy. BSE bhavcopy, then Stooq, then a small Yahoo gap fill are the backups. The history stays in `cache/ohlcv.csv.gz` (about 3 years) and the site reads letter files in `data/ohlc/`. There is no hourly price download.

The main run is after the NSE close, weekdays at 16:30 IST. A retry at 18:30 IST picks up a late bhavcopy. A light morning run at 08:00 IST refreshes news and FII/DII only. Prices are not downloaded every hour.

Company statements, ratios, analyst numbers, and shareholding keep filling in a separate job, about every 30 minutes all week. It continues from `cache/backfill_cursor.json`. Liquid names come first, then the rest of the NSE list, then BSE-only names. At 40 names a run, the first pass of the full list is about 2 to 3 days when the free sources answer. After that it refreshes the oldest shareholding about every 90 days, and results after the next earnings date or every 90 days. Turn it off with `feature.fundamentals_backfill`. The price schedule does not change.

Every stock chart has one plain line above it that says what the company does. The lines live in `data/company_lines.csv` (ticker, line, source, as_of). They come from Yahoo's business summary, which the backfill already reads for each name, then Screener.in's About text, then NSE and BSE industry and sector. A short rule keeps the first sentence, drops legal wording like "together with its subsidiaries", and cuts it at about 20 words. A stock with no summary gets a line built from its industry and sector, so none is blank. `company_lines.py` has the rule and `tests/test_company_lines.py` checks it. Turn it off with `feature.company_line`.

If a source fails, the job keeps the saved file and the Data updates page says CACHED.

## Self-healing schedule

GitHub's own cron sometimes skips or delays scheduled runs. Three layers keep both jobs going, all inside GitHub:

1. **The normal crons** in `update.yml` and `fundamentals-backfill.yml`.
2. **A watchdog** (`.github/workflows/watchdog.yml`). It wakes at 7, 22, 37 and 52 minutes past each hour and looks up the last runs through the GitHub API, using the built-in `GITHUB_TOKEN`. It starts a workflow with "Run workflow" only when nothing for that workflow is queued or running and:
   - **Financials backfill**: no run started in the last 45 minutes. When the last batch found no name due (refresh mode), it leaves the backfill to its cron.
   - **Daily update**: no close run worked since the latest weekday NSE close (10:30 UTC, checked from 11:30 UTC). It tries at most 3 times per close, 90 minutes apart, so a source that is down is not hammered. A watchdog start runs the full after-close update (`--close`).
3. **Concurrency groups**, so two runs of the same job never overlap or pile up.

Switches in `config.json` under `self_heal_schedule`: `backfill_watchdog` and `daily_update_watchdog` (`true` or `false`), plus `backfill_overdue_minutes`, `backfill_skip_when_nothing_due`, `daily_update_close_utc`, `daily_update_grace_minutes`, `daily_update_retry_gap_minutes` and `daily_update_max_tries`. Set a switch to `false` to go back to GitHub's cron only for that job.

To test it by hand, open Actions, pick "Schedule watchdog", press "Run workflow", and set a small "backfill_overdue_minutes" (tick "dry_run" to only see what it would do). The run summary lists what it checked and started.

GitHub turns off scheduled workflows in a public repo after 60 days with no repo activity. The backfill and daily update commit data often, so this does not apply while they keep saving data.

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
python stock_desk.py --close
```

`--morning` refreshes news and FII/DII and does not download prices. `--retry` refreshes the last few bhavcopy sessions. `--offline` rebuilds the pages from the cache and does not call the network.

Edit example holdings in `input/holdings.csv` and the watchlist in `input/my_watchlist.csv`. Switches live in `config.json`.
