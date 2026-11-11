# Nick's India Stock Desk

A research screen for NSE stocks. It scores names, writes the tables, and shows them on a website.

It does not place trades. It does not call a broker. It does not pick option contracts. The liquid stocks page is a stock screen. Put and call walls are a mood gauge. Prices are in rupees. Times are shown in IST and PT.

## How the numbers get to the screen

```text
GitHub Action (stock_desk.py on a schedule)
        |  writes CSVs
        v
data/*.csv on GitHub
        |  Pages publishes data/ next to the html
        v
GitHub Pages (site/ and data/)
```

The pages do no scoring. The Python job does the work. On github.io the site loads `data/<file>` from the published site, including `data/trends.csv`. The scheduled jobs commit with the Actions token, and that push does not start another workflow, so those jobs start the Pages deploy after a commit that changes `data/` or `site/`. A normal push of those paths still publishes too.

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

## Relative strength

RS is a 1 to 99 rank of the past year, across every stock the desk covers. 99 is the strongest. RS 85 means the stock beat 85% of that list.

The year is four quarters of 63 trading days. The latest quarter counts 40%. Each older quarter counts 20%. A stock with less than a full year of daily prices is left blank. That blank is not a zero.

The rank is calculated only on the after-close run (16:30 IST, 3:00 AM PT, one hour later in summer) from prices already saved. No new download. The morning run and the late bhavcopy retry reuse it. Turn it off with `feature.rs_rank`.

The VCP trend template still checks the stock against the Nifty 50 (SENSEX for a BSE-only stock). The RS line is the stock's price divided by that index. It has to be higher than 126, 252, and 21 days ago, and above its own 50-day average. That check is not replaced by this rank, and it is not an IBD 1 to 99 rating. CANSLIM's L column is still strength versus the index. Minervini's line is the optional filter, RS 70 or higher.

## Stock scorecard CANSLIM

The stock scorecard shows a C A N S L I M card for every stock, not only the names that pass the price screen on the CANSLIM scanner page. The scanner, Leaders, and Buy setups stay exactly the same.

Each letter has a stored value and a pass, fail, or not verified mark:

- C: quarterly EPS versus the same quarter last year. Pass at +25% or more.
- A: yearly EPS versus the prior year. Pass at +25% or more. A 3-year streak is not verified.
- N: how far the close sits from the 52-week closing high. Pass within 15%. A news check is added when `feature.canslim_news` is on.
- S: 20-day average volume. Pass at 200,000 shares or more. Free float is 100 minus promoter percent when `feature.canslim_free_float` is on. If a share count is already saved, the card also shows about how many shares are free to trade.
- L: the 1 to 99 RS rank. Pass at 80 or higher. An industry group rank (median RS of the industry, ranked across groups) is added when `feature.canslim_industry_rank` is on.
- I: whether FII and DII holdings rose versus last quarter. Promoter change is not used for I.
- M: the same market check as the rest of the desk. It passes when the Nifty 50 or SENSEX is in an uptrend.

A missing number stays blank and says not verified. It is never stored as 0.

Switches in `config.json`: `feature.stock_canslim` (the whole card), `feature.canslim_industry_rank`, `feature.canslim_free_float`, and `feature.canslim_news`.

### Extra downloads

C, A, S (including free float), L (including industry rank), I, and M use files the desk already has. They add no new downloads.

News is the only new download. On the after-close run (`--close`), the job looks up the free Google News RSS feed for stocks that already passed the CANSLIM price checks and have no saved headline. The cap is `stock_canslim.news_per_run` (15) requests a run, at `stock_canslim.news_per_second` (1) request a second. The morning run and `--offline` do not request news. That is at most 15 extra network calls on an after-close run, and at most 15 a day, because the close job runs once. The answers are saved in `cache/canslim_news.csv` and reused for `stock_canslim.news_keep_days` (14) days.

The Shareholding box on the same scorecard is separate. It reads `data/institutional_13f.csv` and downloads nothing new.

## What is fetched, and how often

Daily prices come from the NSE bhavcopy. BSE bhavcopy, then Stooq, then a small Yahoo gap fill are the backups. The history stays in `cache/ohlcv.csv.gz` (about 3 years) and the site reads letter files in `data/ohlc/`. There is no hourly price download.

The main run is after the NSE close, weekdays at 16:30 IST. A retry at 18:30 IST picks up a late bhavcopy. A light morning run at 08:00 IST refreshes news and FII/DII only. Prices are not downloaded every hour.

Company statements, ratios, analyst numbers, and shareholding keep filling in a separate job, about every 30 minutes all week. It continues from `cache/backfill_cursor.json`. Liquid names come first, then the rest of the NSE list, then BSE-only names. At 40 names a run, the first pass of the full list is about 2 to 3 days when the free sources answer. After that it refreshes the oldest shareholding about every 90 days, and results after the next earnings date or every 90 days. Turn it off with `feature.fundamentals_backfill`. The price schedule does not change.

If a download stops halfway, the next run continues from the last chunk that was saved. Price files and the financial files are swapped in only after the write finishes, so a failed save leaves the previous file in place. A day is marked done only after that swap, and only when the NSE file for that day had bars. A day with only BSE or index bars stays pending. Two jobs on the same machine do not download the same prices or the same backfill at once. A source that fails three times in one run is left alone for 6 hours. A name that no source has is written down, with a date to try again, and is not asked every run. A job that saves nothing three runs in a row pauses and the Data updates page says a person should look. That pause does not repair a bad login, a blocked site, or a source that stays down. GitHub still stops two Actions jobs of the same workflow from running together. The numbers are `download_guard` in `config.json`.

Every stock chart has one plain line above it that says what the company does. The lines live in `data/company_lines.csv` (ticker, line, source, as_of). They come from Yahoo's business summary, which the backfill already reads for each name, then Screener.in's About text, then NSE and BSE industry and sector. A short rule keeps the first sentence, drops legal wording like "together with its subsidiaries", and cuts it at about 20 words. A stock with no summary gets a line built from its industry and sector, so none is blank. `company_lines.py` has the rule and `tests/test_company_lines.py` checks it. Turn it off with `feature.company_line`.

If a source fails, the job keeps the saved file and the Data updates page says CACHED.

## Self-healing schedule

GitHub's own cron sometimes skips or delays scheduled runs. Three layers keep both jobs going, all inside GitHub:

1. **The normal crons** in `update.yml` and `fundamentals-backfill.yml`.
2. **A watchdog** (`.github/workflows/watchdog.yml`). It wakes at 7, 22, 37 and 52 minutes past each hour and looks up the last runs through the GitHub API, using the built-in `GITHUB_TOKEN`. It starts a workflow with "Run workflow" only when nothing for that workflow is queued or running and:
   - **Financials backfill**: no run started in the last 45 minutes. When the last batch found no name due (refresh mode), it leaves the backfill to its cron.
   - **Daily update**: no close run worked since the latest weekday NSE close (10:30 UTC, checked from 11:30 UTC). It tries at most 3 times per close, 90 minutes apart, so a source that is down is not hammered. A watchdog start runs the full after-close update (`--close`). While an Update keeper is live (below), this check steps aside, because the keeper owns the daily slots and their one retry; it only covers for a broken keeper chain.
3. **Concurrency groups**, so two runs of the same job never overlap or pile up.

Switches in `config.json` under `self_heal_schedule`: `backfill_watchdog` and `daily_update_watchdog` (`true` or `false`), plus `backfill_overdue_minutes`, `backfill_skip_when_nothing_due`, `daily_update_close_utc`, `daily_update_grace_minutes`, `daily_update_retry_gap_minutes` and `daily_update_max_tries`. Set a switch to `false` to go back to GitHub's cron only for that job.

To test it by hand, open Actions, pick "Schedule watchdog", press "Run workflow", and set a small "backfill_overdue_minutes" (tick "dry_run" to only see what it would do). The run summary lists what it checked and started.

GitHub turns off scheduled workflows in a public repo after 60 days with no repo activity. The backfill and daily update commit data often, so this does not apply while they keep saving data.

## Update keeper (self-starting updates)

Switch: `features.self_heal_keeper`, on by default. Settings in the `keeper` block of `config.json`: `check_after_min` (10), `verify_after_min` (45), `recheck_min` (15), `chunk_min` (330), `min_gap_min` (50), `max_tries` (2). GitHub's cron in this repo often fires hours late (the 16:30 IST close cron has started around 22:30 IST) or not at all, and the watchdog is cron too, so the desk keeps its own clock entirely inside GitHub Actions. `.github/workflows/keeper.yml` runs one long job, `keeper.py keeper`:

| Slot (IST, Mon-Fri) | UTC | Mode | Make-up | Verify at +45 min |
|---|---|---|---|---|
| 08:00 | 02:30 | `morning` (news, FII/DII, no prices) | yes | failed: one retry |
| 16:30 | 11:00 | `close` (`--close`) | yes | failed: one retry; succeeded but `price_as_of` is not that IST date: warning only |
| 18:30 | 13:00 | `retry` (`--retry`, late bhavcopy) | only while `price_as_of` is still older than that IST date | failed or stale: warning only (it is already the retry) |

NSE trading holidays are skipped (2026 list from NSE's holiday page, segment CM; NSE had not published 2027 by 2 Nov 2026, so 2027 counts every weekday until `NSE_HOLIDAYS` in `keeper.py` is updated). At `check_after_min` past a slot, if no real update started since the slot, none is queued or running, and none started in the last `min_gap_min` minutes, it dispatches exactly one update with that slot's mode (`reason=keeper`). At `verify_after_min` it reads the slot's runs and `data/meta.json` on main; the retry count comes from the GitHub run list, so a restarted keeper never retries a slot twice. A run still going is looked at every `recheck_min` minutes, up to 3 hours. Warnings show as annotations and in the keeper run's summary; nothing is sent. A hosted job lives at most 6 hours, so every `chunk_min` minutes the keeper dispatches the next keeper and exits; the concurrency group `india-update-keeper` keeps one at a time, and a keeper steps aside if a newer one is waiting. Every update run and watchdog run ends with `keeper.py ensure-keeper`, which starts a keeper only if the switch is on and none is queued or running.

The update workflow has a `mode` input (`close` by default, so "Run workflow" and the watchdog still run the close update as before; also `morning` and `retry`) and a first step, `keeper.py guard`. For a scheduled run or a keeper make-up it skips the run when another real update already started for the same slot, so a cron that GitHub fires hours late after the keeper already made it up stops after a few seconds. A scheduled run belongs to the time its cron was due. Manual runs, watchdog starts, and the keeper's one retry are never skipped. If the run list cannot be read, the update runs as before. Turn the switch off and the running keeper stops at its next wake and starts no other; the watchdog's daily update check then works as before.

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
python tests/test_relative_strength.py
python stock_desk.py --close
```

`--morning` refreshes news and FII/DII and does not download prices. `--retry` refreshes the last few bhavcopy sessions. `--offline` rebuilds the pages from the cache and does not call the network.

Edit example holdings in `input/holdings.csv` and the watchlist in `input/my_watchlist.csv`. Switches live in `config.json`.
