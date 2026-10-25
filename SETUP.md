# Set up Nick's India Stock Desk

You do this once. After that, the files update themselves and you open the website.

This desk is research only. It will not place a trade, and it does not connect to a broker. Nothing is emailed or sent to a phone.

## 1. Turn on the automatic update

1. Open the GitHub repo `PatelNicknp/nicks-india-stock-desk`.
2. Tap **Actions**.
3. If GitHub asks you to enable Actions, tap the green button.
4. On the left, click **Update Nick's India Stock Desk**.
5. Click **Run workflow**, leave the branch on `main`, and click the green **Run workflow** button.
6. Wait until the yellow dot turns green. The first run is the long one. It reads the NSE daily price files for about three years, then NSE and BSE names. Later runs only add the new session.

The schedule after that (Monday to Friday):

- 08:00 IST, a light run for news and FII/DII. No prices.
- 16:30 IST, the main run after the close. Daily prices, then statements, shareholding, and the rest.
- 18:30 IST, a short retry if the daily price file was late.

A second workflow, **Financials and shareholding backfill**, runs about every 30 minutes, including weekends. It does not download prices. It picks up where it stopped, saves the next batch of statements and shareholding, and commits. The first pass of the full list is about 2 to 3 days. The switch is `feature.fundamentals_backfill` in `config.json`, on by default. Progress is on the Data updates page.

If you do not see the workflow until it is on `main`, merge the pull request and look again. Copies of the workflow files are in `workflow_copy/`.

## 2. Turn on the website

GitHub Pages serves the `site/` folder. Data commits show up without a new site build, because the pages read `data/*.csv` from the raw GitHub files.

If Pages is not on yet, open the repo **Settings**, then **Pages**, and set the source to **GitHub Actions**. The workflow that publishes the site is `.github/workflows/pages.yml`.

## 3. Change the example holdings

1. Open `input/holdings.csv`. The rows marked `example` are samples, not a real portfolio.
2. Put your own ticker, share count, and average cost in rupees. Use the NSE symbol without `.NS` (for example `RELIANCE`).
3. Open `input/my_watchlist.csv` for names you want scored even if they are outside the index lists. You can also add symbols under `my_picks` in `config.json`.
4. Open `config.json` to turn a page or an index list off. Set the matching feature to `false`.

The next after-close run picks up the new names. A name with no saved history gets a full price download. Statements and shareholding also keep filling between closes, from the backfill workflow.
