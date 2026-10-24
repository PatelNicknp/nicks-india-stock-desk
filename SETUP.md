# Set up Nick's India Stock Desk

You do this once. After that, the files update themselves and you open the website.

This desk is research only. It will not place a trade, and it does not connect to a broker. Nothing is emailed or sent to a phone.

## 1. Turn on the automatic update

1. Open the GitHub repo `PatelNicknp/nicks-india-stock-desk`.
2. Tap **Actions**.
3. If GitHub asks you to enable Actions, tap the green button.
4. On the left, click **Update Nick's India Stock Desk**.
5. Click **Run workflow**, leave the branch on `main`, and click the green **Run workflow** button.
6. Wait until the yellow dot turns green. The first run is the long one. It reads prices and statements for Nifty 50, Next 50, and Midcap 150. Later runs during the day only refresh recent prices.

The schedule after that (Monday to Friday):

- Hourly from 09:15 IST through 15:15 IST, recent prices only.
- Once at 16:15 IST, the slow facts refresh (statements, shareholding, insiders, option chains, news).

If you do not see the workflow until it is on `main`, merge the pull request and look again. A copy of the workflow file is in `workflow_copy/update.yml`.

## 2. Turn on the website

GitHub Pages serves the `site/` folder. The hourly data commits show up without a new site build, because the pages read `data/*.csv` from the raw GitHub files.

If Pages is not on yet, open the repo **Settings**, then **Pages**, and set the source to **GitHub Actions**. The workflow that publishes the site is `.github/workflows/pages.yml`.

## 3. Change the example holdings

1. Open `input/holdings.csv`. The rows marked `example` are samples, not a real portfolio.
2. Put your own ticker, share count, and average cost in rupees. Use the NSE symbol without `.NS` (for example `RELIANCE`).
3. Open `input/my_watchlist.csv` for names you want scored even if they are not in the three index lists.
4. Open `config.json` to turn a page or an index list off. Set the matching feature to `false`.

The next after-close run picks up the new names. A name with no saved history gets a full price download. Statements refresh once a day.
