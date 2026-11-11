"""Live smoke test of official NSE/BSE statement endpoints. Not part of pytest.

Example: python scripts/smoke_nse_financials.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exchange_financials as xf
import netutil

SAMPLE = (
    ("INFY", "500209"),
    ("RELIANCE", "500325"),
    ("TCS", "532540"),
    ("HDFCBANK", "500180"),
    ("PRESTIGE", "533274"),
)


def load_cfg():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config.json")) as handle:
        return json.load(handle)


def main():
    cfg = load_cfg()
    cfg.setdefault("fundamentals_backfill", {})
    # Keep the smoke test to one XBRL file per side so it stays polite.
    cfg["fundamentals_backfill"]["nse_xbrl_quarters"] = 1
    cfg["fundamentals_backfill"]["nse_xbrl_annuals"] = 1
    cfg["fundamentals_backfill"]["nse_xbrl_pause_seconds"] = 0.4
    cfg["fundamentals_backfill"]["nse_results_max_age_days"] = 5000
    print("NSE homepage...")
    try:
        xf.http_get(xf.NSE_HOME, cfg, xf.NSE_HOME, timeout=20)
        print("  OK")
    except Exception as exc:
        print("  BLOCKED", type(exc).__name__, str(exc)[:160])
    print("BSE homepage...")
    try:
        xf.http_get(xf.BSE_HOME, cfg, xf.BSE_HOME, timeout=20)
        print("  OK")
    except Exception as exc:
        print("  BLOCKED", type(exc).__name__, str(exc)[:160])
    print("BSE results API INFY 500209...")
    try:
        payloads = xf.fetch_bse_payloads("500209", cfg)
        print("  payloads", len(payloads))
    except Exception as exc:
        print("  BLOCKED", type(exc).__name__, str(exc)[:160])
    for symbol, _code in SAMPLE:
        print("NSE list", symbol, "...")
        try:
            q = xf.nse_list_results(symbol, "Quarterly", cfg)
            a = xf.nse_list_results(symbol, "Annual", cfg)
            print("  quarterly", len(q), "annual", len(a))
            if q:
                q_ends = sorted({i.get("toDate") for i in q})
                print("  quarter range", q_ends[0], "->", q_ends[-1])
        except Exception as exc:
            print("  FAIL", type(exc).__name__, str(exc)[:160])
            continue
        try:
            bundle = xf.fetch_nse_statements(symbol, cfg)
        except Exception as exc:
            print("  fetch FAIL", type(exc).__name__, str(exc)[:160])
            continue
        if not bundle:
            print("  fetch empty or stale")
            continue
        latest_q = max(bundle["quarters"], key=lambda r: r["end"]) if bundle["quarters"] else None
        latest_a = max(bundle["annual"], key=lambda r: r["end"]) if bundle["annual"] else None
        if latest_q:
            print("  latest quarter", latest_q["end"], "rev", latest_q["revenue"], "eps", latest_q["eps"],
                  latest_q["currency"])
        if latest_a:
            print("  latest annual", latest_a["end"], "rev", latest_a["revenue"], "ocf", latest_a.get("ocf"),
                  latest_a["currency"])


if __name__ == "__main__":
    main()
