# Trading Floor paper test rules (FAKE MONEY)

The Paper Test page (`paper-test.html`) follows the Trading Floor's Buy calls with a pretend
account, to see if the calls would have made or lost money. It is fake money. No real order is
ever placed, no broker is connected, no alert is sent, and nothing new is downloaded. It reads
the Trading Floor file of that run and the saved bhavcopy bars (open, high, low, close).

Code: `trading_floor_paper.py`. Tests: `tests/test_trading_floor_paper.py`.
Switch: `features.trading_floor_paper` (on). Settings: the `trading_floor_paper` block in `config.json`.

## Settings

| Setting | Value | Meaning |
|---|---|---|
| `start_cash` | 1000000 | Pretend rupees at the start (Rs 10,00,000). |
| `position_pct` | 10 | Each position is 10% of the starting cash: Rs 1,00,000. |
| `max_open` | 10 | At most 10 positions open or waiting at once. |
| `time_stop_days` | 20 | Sell at the close of the 20th trading day held (the entry day is day 1). |
| `fractional_shares` | true | Buy fractional shares (Rs 1,00,000 / open). |
| `share_decimals` | 4 | Fractional shares are rounded to 4 decimals. |
| `skip_if_held` | true | A Buy call is skipped when the stock is already held or waiting. |
| `skip_gap_past_plan` | true | A stock that opens at or under its stop, or at or over the target, is not bought. |

The account never borrows. Cash set aside for waiting calls is not spent twice.

## Start

The test starts on the first main run that has it, with Rs 10,00,000 and the Nifty 50 close that
day as the comparison. It only moves forward. Nothing before the start is replayed.

## Entries

Each main run reads that day's Trading Floor. Every Buy row becomes a call, highest total first.
It is skipped when the stop and target are not usable, the stock is already held, 10 positions
are already open or waiting, or free pretend cash is under Rs 1,00,000.

Otherwise it waits overnight and is bought at the next session's open from the bhavcopy.
Shares = 100000 / open, rounded to 4 decimals.

## Exits

Stop and target are frozen on the day of the call. On each later bar, in order:

1. Opened at or under the stop: sold at the open.
2. Opened at or over the target: sold at the open.
3. The low hit the stop and the high hit the target: counted as the stop.
4. The low hit the stop: sold at the stop.
5. The high hit the target: sold at the target.
6. Held 20 trading days: sold at that day's close.

## Numbers

The page shows open positions, closed trades, cash, total value versus the Nifty 50, win rate,
and the average gain and loss, in plain words. A closed trade with no gain counts as a loss.

## State

`data/paper_trades.csv`, `data/paper_equity.csv`, and `data/paper_summary.csv` are kept in the
repo so the account survives a restart. Only the main run, the late bhavcopy retry, and an
offline rebuild change them. A day's bar counts only after 15:30 IST. Running the same day twice
changes nothing. Turning the switch off hides the page and leaves the files as they were.
